"""
Grounded Q&A API endpoint for LexiGuard.
Implements document-grounded question answering with hybrid retrieval,
citation validation, and explicit abstention when evidence is insufficient.

Includes pre-retrieval constraint checking: if the user's question explicitly
references a section/page that does not exist in the document, the system
returns INSUFFICIENT_EVIDENCE immediately without calling the LLM or retrieval.
"""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Tuple
from app.storage.database import get_document, get_clauses
from app.api.documents import tfidf_store
from app.retrieval.hybrid import hybrid_search
from app.retrieval.reranker import rerank
from app.retrieval.tfidf import TFIDFIndex
from app.llm.provider import get_llm_provider
from app.models.schemas import QAResponse, GroundingStatus, ClaimEvidence, Clause, ClauseMetadata
from app.config import settings
from app.llm.validator import SECTION_CITATION_PATTERN, _clause_matches_citation
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Prose-style section constraint pattern.
# Matches: "According to Section 999, Page 999..." / "Per Section General, Page 1..."
# Requires a citation-intent preposition so incidental mentions ("the clause in section 2")
# are NOT treated as constraints.
_PROSE_SECTION_CONSTRAINT = re.compile(
    r'(?:according\s+to|per|under|from)\s+'
    r'[Ss]ection\s+'
    r'([\w][\w\s\.]{0,40}?)'
    r'(?:,?\s*[Pp]age?\s*(\d+))?'
    r'(?=[,\?!\n]'                 # comma, ?, !, newline — NOT "." (would truncate "3.2")
    r'|\s+(?:what|which|how|when|where|who|the|a|an|is|are|was|were|will|would|should'
    r'|can|could|does|do|did|has|have|had|that|this)\b'
    r'|$)',
    re.IGNORECASE,
)


class QuestionRequest(BaseModel):
    question: str
    conversation_history: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    language: Optional[str] = "en"


# ── Pre-retrieval constraint helpers ──────────────────────────────────────────

def _extract_question_constraints(question: str) -> List[Tuple[str, Optional[int]]]:
    """
    Extract explicit section/page constraints from the user's question.

    Returns a list of (section_ref, page_or_None) tuples.

    Supported formats:
      [Section 999, Page 999]              — bracket style (reuses validator pattern)
      According to Section 999, Page 999   — prose, numeric section
      Per Section General, Page 1          — prose, text section name
      Under Section 3.2                    — prose, no page

    NOT triggered by:
      "What is the salary?"                — no constraint, proceeds normally
      "The salary described in section 2"  — no citation-intent preposition
    """
    constraints: List[Tuple[str, Optional[int]]] = []
    seen: set = set()

    # 1. Bracket-style: [Section X, Page Y] — reuse validator's compiled pattern
    for match in SECTION_CITATION_PATTERN.findall(question):
        sec = match[0].strip()
        page = int(match[1]) if match[1] else None
        key = (sec.lower(), page)
        if sec and key not in seen:
            seen.add(key)
            constraints.append((sec, page))

    # 2. Prose-style: "According to Section X, Page Y"
    for match in _PROSE_SECTION_CONSTRAINT.findall(question):
        sec = match[0].strip()
        page = int(match[1]) if match[1] else None
        key = (sec.lower(), page)
        if sec and key not in seen:
            seen.add(key)
            constraints.append((sec, page))

    return constraints


def _constraint_satisfied(sec_ref: str, page: Optional[int], clauses: List[Clause]) -> bool:
    """
    Return True if at least one clause in the document matches the constraint.
    Reuses _clause_matches_citation from validator.py to keep matching logic consistent.
    """
    return any(_clause_matches_citation(c, sec_ref, page) for c in clauses)


def _format_constraint(sec: str, page: Optional[int]) -> str:
    """Human-readable label for a constraint, e.g. 'Section 999, Page 999'."""
    if page is not None:
        return f"Section {sec}, Page {page}"
    return f"Section {sec}"


# ── Clause deserialization / TF-IDF helpers ───────────────────────────────────

def _deserialize_clauses(clauses_data: List[Dict[str, Any]]) -> List[Clause]:
    """Safely deserialize clause dicts from DB into Clause objects."""
    result = []
    for c in clauses_data:
        try:
            meta = ClauseMetadata(**c['metadata']) if isinstance(c.get('metadata'), dict) else c['metadata']
            result.append(Clause(id=c['id'], metadata=meta, text=c['text']))
        except Exception as e:
            logger.debug("Skipping malformed clause: %s", e)
    return result


def _get_or_rebuild_index(doc_id: str, clauses: List[Clause]) -> TFIDFIndex:
    """Return existing TF-IDF index or rebuild it if not in memory."""
    if doc_id in tfidf_store and tfidf_store[doc_id].is_built():
        return tfidf_store[doc_id]
    logger.info("Rebuilding TF-IDF index for document %s", doc_id)
    index = TFIDFIndex()
    index.build(clauses)
    tfidf_store[doc_id] = index
    return index


# ── Q&A endpoint ──────────────────────────────────────────────────────────────

@router.post("/documents/{doc_id}/ask", response_model=QAResponse)
def ask_document_question(doc_id: str, request: QuestionRequest) -> QAResponse:
    """
    Answer a question grounded in the document content.
    Supports multi-turn conversational follow-ups and cross-references.

    Flow:
      1. Pre-retrieval constraint check — if question explicitly names a
         section/page that does not exist, return INSUFFICIENT_EVIDENCE immediately.
      2. Follow-up query resolution using conversation history context.
      3. Hybrid retrieval → reranking → evidence pack.
      4. LLM answer generation → citation validation.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    if not clauses:
        return QAResponse(
            answer="I couldn't find sufficient evidence in the uploaded document to answer this reliably. The document may not have been parsed successfully.",
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
        )

    # ── Pre-retrieval: explicit section/page constraint check ─────────────────
    question_constraints = _extract_question_constraints(request.question)
    if question_constraints:
        failed_constraints = [
            (sec, page) for sec, page in question_constraints
            if not _constraint_satisfied(sec, page, clauses)
        ]
        if failed_constraints:
            desc = "; ".join(_format_constraint(s, p) for s, p in failed_constraints)
            logger.info(
                "Explicit section constraint not satisfied in document %s: [%s]",
                doc_id, desc,
            )
            return QAResponse(
                answer=(
                    f"The explicitly referenced {desc} does not exist in the uploaded document. "
                    f"No answer can be provided based on a non-existent evidence location. "
                    f"Consider rephrasing your question without a specific section reference "
                    f"to retrieve the most relevant content from the document."
                ),
                grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
                abstained=True,
                suggested_followup=(
                    "Try asking without the section constraint — for example: "
                    "\"What is the employee's salary?\" or "
                    "\"What is the probation period?\""
                ),
            )
    # ── End constraint check ──────────────────────────────────────────────────

    # Follow-up resolution logic
    search_query = request.question
    q_lower = request.question.lower()

    is_cross_reference = any(kw in q_lower for kw in (
        "mentioned elsewhere", "other clause", "another clause", "somewhere else", "other section"
    ))
    is_short_followup = len(request.question.split()) <= 6 or any(kw in q_lower for kw in (
        "that", "it", "this", "notice period", "after that", "same thing"
    ))

    if request.conversation_history and (is_short_followup or is_cross_reference):
        last_user_q = next((turn.get("content", "") for turn in reversed(request.conversation_history) if turn.get("role") == "user"), "")
        if last_user_q:
            search_query = f"{last_user_q} {request.question}"

    # Build or reuse TF-IDF index
    tfidf_index = _get_or_rebuild_index(doc_id, clauses)

    # Run hybrid retrieval
    raw_results = hybrid_search(
        query=search_query,
        clauses=clauses,
        tfidf_index=tfidf_index,
        top_k=settings.retrieval_top_k * 2 if is_cross_reference else settings.retrieval_top_k,
    )

    # Rerank and trim context
    ranked_results = rerank(raw_results, search_query, top_k=settings.retrieval_top_k)

    if is_cross_reference and len(ranked_results) <= 1:
        return QAResponse(
            answer="No additional matching provision was identified in the analyzed document.",
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
            suggested_followup="Try asking about a specific section or clause type.",
        )

    # Check retrieval confidence
    if not ranked_results or ranked_results[0][1] < settings.retrieval_min_score:
        logger.info("Insufficient retrieval confidence for question on doc %s", doc_id)
        return QAResponse(
            answer=(
                "I couldn't find sufficient evidence in the uploaded document to answer this reliably. "
                "Consider asking a legal professional about: " + request.question
            ),
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
            suggested_followup="Consider asking a legal professional to review this specific topic.",
        )

    evidence_clauses = [clause for clause, _ in ranked_results]
    filename = doc_data.get('filename', 'document')

    provider = get_llm_provider()
    qa_response = provider.answer_question(
        request.question,
        evidence_clauses,
        filename,
        conversation_history=request.conversation_history,
        language=request.language or "en",
    )

    return qa_response


class CrossQARequest(BaseModel):
    doc_ids: List[str]
    question: str
    language: Optional[str] = "en"
    conversation_history: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


@router.post("/questions/cross-document", response_model=QAResponse)
def ask_cross_document_question(request: CrossQARequest) -> QAResponse:
    """
    Answer a question comparing or referencing multiple selected documents.
    Retrieves evidence separately per document to ensure strict document isolation.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    if not request.doc_ids:
        raise HTTPException(status_code=400, detail="At least one document ID must be provided.")

    doc_evidence_map = {}
    all_retrieved_clauses = []

    for doc_id in request.doc_ids:
        doc_data = get_document(doc_id)
        if not doc_data:
            continue
        filename = doc_data.get("filename", doc_id)
        clauses_data = get_clauses(doc_id)
        clauses = _deserialize_clauses(clauses_data)
        if not clauses:
            doc_evidence_map[filename] = []
            continue

        tfidf_index = _get_or_rebuild_index(doc_id, clauses)
        raw_results = hybrid_search(
            query=request.question,
            clauses=clauses,
            tfidf_index=tfidf_index,
            top_k=settings.retrieval_top_k,
        )
        ranked_results = rerank(raw_results, request.question, top_k=settings.retrieval_top_k)
        matching_clauses = [c for c, score in ranked_results if score >= settings.retrieval_min_score]
        doc_evidence_map[filename] = matching_clauses
        all_retrieved_clauses.extend(matching_clauses)

    if not all_retrieved_clauses:
        return QAResponse(
            answer="No corresponding evidence was identified across the selected documents.",
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
            suggested_followup="Try rephrasing your question or checking if the documents contain relevant terms."
        )

    provider = get_llm_provider()
    return provider.answer_cross_document_question(
        request.question,
        doc_evidence_map,
        conversation_history=request.conversation_history,
        language=request.language or "en"
    )

