"""
Deterministic document comparison engine for LexiGuard Phase 2 Feature 4.
Uses TF-IDF cosine similarity to align clauses across two document versions,
then classifies differences into 15 structured categories, financial changes,
and relationship changes. Preserves page and section_path provenance for both documents.
Zero LLM calls. All deterministic.
"""
import re
import difflib
import logging
import numpy as np
from typing import List, Set, Optional, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.schemas import Clause, ClauseDiff, DiffType, ComparisonResult
from app.models.financial import FinancialItem
from app.analysis.entities import extract_monetary_values, extract_dates
from app.analysis.financial_engine import analyze_document_financials
from app.analysis.relationships import RelationshipEngine

logger = logging.getLogger(__name__)

# Cosine similarity thresholds
SIMILARITY_THRESHOLD_SAME = 0.95    # above this → UNCHANGED
SIMILARITY_THRESHOLD_MATCH = 0.35   # between match and same → MODIFIED


def compute_clause_similarity_matrix(
    clauses_a: List[Clause],
    clauses_b: List[Clause],
) -> np.ndarray:
    """Compute pairwise TF-IDF cosine similarity between all clauses in doc A and doc B."""
    if not clauses_a or not clauses_b:
        return np.zeros((len(clauses_a), len(clauses_b)))

    texts_a = [c.text for c in clauses_a]
    texts_b = [c.text for c in clauses_b]

    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=10000)
        vectorizer.fit(texts_a + texts_b)
        tfidf_a = vectorizer.transform(texts_a)
        tfidf_b = vectorizer.transform(texts_b)
        return cosine_similarity(tfidf_a, tfidf_b)
    except ValueError as e:
        logger.warning("TF-IDF similarity matrix failed: %s", e)
        return np.zeros((len(clauses_a), len(clauses_b)))


def compute_text_diff_summary(text_a: str, text_b: str) -> str:
    """Use difflib.unified_diff to produce a short human-readable summary of text changes."""
    diff = list(difflib.unified_diff(
        text_a.splitlines(),
        text_b.splitlines(),
        lineterm='',
    ))
    if not diff:
        return "No text differences."

    summary_lines = []
    for line in diff:
        if line.startswith('+') and not line.startswith('+++'):
            summary_lines.append(f"Added: {line[1:].strip()}")
        elif line.startswith('-') and not line.startswith('---'):
            summary_lines.append(f"Removed: {line[1:].strip()}")

    summary_text = " | ".join(summary_lines)
    if len(summary_text) > 300:
        return summary_text[:297] + "..."
    return summary_text if summary_text else "Minor formatting changes."


def classify_change_category(
    clause_a: Optional[Clause],
    clause_b: Optional[Clause],
    diff_type: DiffType,
    fin_item_a: Optional[FinancialItem] = None,
    fin_item_b: Optional[FinancialItem] = None,
) -> Tuple[str, Optional[str]]:
    """
    Deterministically classify difference into one of 15 change categories
    and produce factual financial comparison if applicable.
    """
    if diff_type == DiffType.ADDED:
        return "Added provision", None
    if diff_type == DiffType.REMOVED:
        return "Removed provision", None
    if diff_type == DiffType.UNCHANGED:
        return "Unchanged provision", None

    text_a = clause_a.text if clause_a else ""
    text_b = clause_b.text if clause_b else ""
    combined_text = f"{text_a} {text_b}"

    # Financial intelligence comparison
    financial_change_msg = None
    if fin_item_a and fin_item_b:
        if fin_item_a.amount != fin_item_b.amount or fin_item_a.frequency != fin_item_b.frequency:
            amt_a = fin_item_a.amount or "unspecified amount"
            amt_b = fin_item_b.amount or "unspecified amount"
            financial_change_msg = f"{fin_item_a.item_type.replace('_', ' ').title()} changed from {amt_a} to {amt_b}."
            return "Changed amount", financial_change_msg

    # Monetary values change
    monies_a = extract_monetary_values(text_a)
    monies_b = extract_monetary_values(text_b)
    if monies_a != monies_b and (monies_a or monies_b):
        m_a = ", ".join(monies_a) if monies_a else "unspecified"
        m_b = ", ".join(monies_b) if monies_b else "unspecified"
        financial_change_msg = f"Monetary value changed from {m_a} to {m_b}."
        return "Changed amount", financial_change_msg

    # Date change
    dates_a = extract_dates(text_a)
    dates_b = extract_dates(text_b)
    if dates_a != dates_b and (dates_a or dates_b):
        return "Changed date", None

    # Duration change (e.g., 30 days vs 60 days, 1 year vs 2 years)
    dur_pat = re.compile(r'\b(\d+)\s*(days?|months?|years?|weeks?)\b', re.IGNORECASE)
    durs_a = dur_pat.findall(text_a)
    durs_b = dur_pat.findall(text_b)
    if durs_a != durs_b and (durs_a or durs_b):
        return "Changed duration", None

    # Specific Legal Categories
    if re.search(r'\b(terminate|termination|severance|notice pay)\b', combined_text, re.I):
        return "Changed termination language", None
    if re.search(r'\b(notice|days notice|written notice|notice period)\b', combined_text, re.I):
        return "Changed notice language", None
    if re.search(r'\b(confidential|nondisclosure|secrecy|trade secret)\b', combined_text, re.I):
        return "Changed confidentiality language", None
    if re.search(r'\b(liability|limitation of liability|liability cap|aggregate liability)\b', combined_text, re.I):
        return "Changed liability language", None
    if re.search(r'\b(indemnify|indemnification|hold harmless)\b', combined_text, re.I):
        return "Changed indemnity language", None
    if re.search(r'\b(compensation|salary|pay|remuneration|bonus|allowance|reimbursement|commission)\b', combined_text, re.I):
        return "Changed payment/compensation language", None
    if re.search(r'\b(subject to|contingent|provided that|conditional)\b', combined_text, re.I):
        return "Changed condition", None
    if re.search(r'\b(responsibility|duty|duties|role|party)\b', combined_text, re.I):
        return "Changed party responsibility", None
    if re.search(r'\b(shall|must|agrees to|required to|will)\b', combined_text, re.I):
        return "Changed obligation", None

    return "Modified provision", None


def _make_diff(
    clause_a: Optional[Clause],
    clause_b: Optional[Clause],
    diff_type: DiffType,
    similarity: float = 0.0,
    diff_summary: Optional[str] = None,
    fin_item_a: Optional[FinancialItem] = None,
    fin_item_b: Optional[FinancialItem] = None,
    rel_change_msg: Optional[str] = None,
) -> ClauseDiff:
    """Create a ClauseDiff with complete provenance and change category."""
    cat, fin_msg = classify_change_category(
        clause_a, clause_b, diff_type, fin_item_a, fin_item_b
    )

    return ClauseDiff(
        diff_type=diff_type,
        clause_id_a=clause_a.id if clause_a else None,
        clause_id_b=clause_b.id if clause_b else None,
        section_path_a=clause_a.metadata.section_path if clause_a else None,
        section_path_b=clause_b.metadata.section_path if clause_b else None,
        page_a=clause_a.metadata.page if clause_a else None,
        page_b=clause_b.metadata.page if clause_b else None,
        text_a=clause_a.text if clause_a else None,
        text_b=clause_b.text if clause_b else None,
        similarity_score=round(similarity, 4),
        diff_summary=diff_summary,
        change_category=cat,
        financial_change=fin_msg,
        relationship_change=rel_change_msg,
    )


def align_clauses(
    clauses_a: List[Clause],
    clauses_b: List[Clause],
    similarity_matrix: np.ndarray,
    fin_items_a: Optional[List[FinancialItem]] = None,
    fin_items_b: Optional[List[FinancialItem]] = None,
) -> Tuple[List[ClauseDiff], List[ClauseDiff], List[ClauseDiff], int]:
    """Greedily align clauses from doc A to doc B using similarity matrix."""
    added: List[ClauseDiff] = []
    removed: List[ClauseDiff] = []
    modified: List[ClauseDiff] = []
    unchanged_count = 0
    matched_b: Set[int] = set()

    fin_map_a = {item.clause_id: item for item in (fin_items_a or [])}
    fin_map_b = {item.clause_id: item for item in (fin_items_b or [])}

    for i, clause_a in enumerate(clauses_a):
        if len(clauses_b) == 0:
            removed.append(_make_diff(clause_a, None, DiffType.REMOVED))
            continue

        row = similarity_matrix[i]
        best_j = int(np.argmax(row))
        best_sim = float(row[best_j])

        fin_a = fin_map_a.get(clause_a.id)

        if best_sim >= SIMILARITY_THRESHOLD_SAME:
            unchanged_count += 1
            matched_b.add(best_j)

        elif best_sim >= SIMILARITY_THRESHOLD_MATCH:
            clause_b = clauses_b[best_j]
            fin_b = fin_map_b.get(clause_b.id)
            diff_summary = compute_text_diff_summary(clause_a.text, clause_b.text)
            
            modified.append(_make_diff(
                clause_a,
                clause_b,
                DiffType.MODIFIED,
                similarity=best_sim,
                diff_summary=diff_summary,
                fin_item_a=fin_a,
                fin_item_b=fin_b,
            ))
            matched_b.add(best_j)

        else:
            removed.append(_make_diff(clause_a, None, DiffType.REMOVED, similarity=best_sim))

    # Unmatched clauses from B are ADDED
    for j, clause_b in enumerate(clauses_b):
        if j not in matched_b:
            added.append(_make_diff(None, clause_b, DiffType.ADDED))

    return added, removed, modified, unchanged_count


def compare_documents(
    clauses_a: List[Clause],
    clauses_b: List[Clause],
    document_id_a: str,
    document_id_b: str,
) -> ComparisonResult:
    """
    Main comparison entry point.
    Supports same-document protection, financial-aware diffing, and relationship diffing.
    Zero LLM calls.
    """
    logger.info(
        "Comparing %d clauses (A) vs %d clauses (B)",
        len(clauses_a), len(clauses_b)
    )

    # Same-document protection
    if document_id_a and document_id_a == document_id_b:
        return ComparisonResult(
            document_id_a=document_id_a,
            document_id_b=document_id_b,
            added=[],
            removed=[],
            modified=[],
            unchanged_count=len(clauses_a),
        )

    if not clauses_a and not clauses_b:
        return ComparisonResult(
            document_id_a=document_id_a,
            document_id_b=document_id_b,
            added=[], removed=[], modified=[], unchanged_count=0,
        )

    # Financial items extraction for detailed monetary diffing
    fin_items_a = analyze_document_financials(document_id_a, clauses_a) if clauses_a else []
    fin_items_b = analyze_document_financials(document_id_b, clauses_b) if clauses_b else []

    matrix = compute_clause_similarity_matrix(clauses_a, clauses_b)
    added, removed, modified, unchanged_count = align_clauses(
        clauses_a, clauses_b, matrix, fin_items_a, fin_items_b
    )

    # Relationship-aware comparison check
    if clauses_a and clauses_b:
        rel_engine = RelationshipEngine()
        rels_a = rel_engine.analyze_document_relationships(clauses_a, document_id_a)
        rels_b = rel_engine.analyze_document_relationships(clauses_b, document_id_b)
        
        # Check if a relationship missing counterpart in B was complete in A
        rel_types_a = {r.relationship_type.value for r in rels_a if r.related_clause_id}
        rel_types_b = {r.relationship_type.value for r in rels_b if r.related_clause_id}
        
        missing_in_b = rel_types_a - rel_types_b
        if missing_in_b:
            for diff in modified:
                if any(kw in (diff.text_a or '').lower() for kw in ('termination', 'notice', 'indemnify', 'liability')):
                    diff.relationship_change = f"Relationship provision identified in Document A ({', '.join(missing_in_b)}) modified or counterpart missing in Document B."
                    break

    logger.info(
        "Comparison complete: +%d added, -%d removed, ~%d modified, =%d unchanged",
        len(added), len(removed), len(modified), unchanged_count
    )

    return ComparisonResult(
        document_id_a=document_id_a,
        document_id_b=document_id_b,
        added=added,
        removed=removed,
        modified=modified,
        unchanged_count=unchanged_count,
    )
