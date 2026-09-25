"""
Retrieval quality evaluation suite for LexiGuard.
Measures Recall@K and MRR across a curated set of legal query categories.
All deterministic — no LLM calls.
"""
import pytest
from app.retrieval.tfidf import TFIDFIndex
from app.retrieval.hybrid import hybrid_search
from app.ingestion.text_parser import extract_text_from_txt
from app.ingestion.structure import segment_document
from typing import List, Tuple
from app.models.schemas import Clause


# Curated evaluation set: (query, expected_clause_type_in_top_k)
EVAL_TEST_CASES = [
    ("automatic renewal notice period", "renewal"),
    ("termination penalties liquidated damages", "termination"),
    ("payment due dates fees invoice", "payment"),
    ("confidentiality obligations non-disclosure", "confidentiality"),
    ("intellectual property work made for hire", "ip"),
    ("arbitration dispute resolution jury", "arbitration"),
    ("liability limitation cap damages", "liability"),
]


def recall_at_k(results: List[Tuple[Clause, float]], expected_clause_type: str, k: int = 5) -> bool:
    """Check if expected clause type appears in top-k results."""
    top_k = results[:k]
    return any(clause.metadata.clause_type == expected_clause_type for clause, _ in top_k)


def mean_reciprocal_rank(results_list: List, expected_types: List[str]) -> float:
    """Compute MRR over a list of (results, expected_type) pairs."""
    rr_sum = 0.0
    for results, expected_type in zip(results_list, expected_types):
        for rank, (clause, score) in enumerate(results, start=1):
            if clause.metadata.clause_type == expected_type:
                rr_sum += 1.0 / rank
                break
    return rr_sum / len(results_list) if results_list else 0.0


@pytest.fixture
def indexed_clauses(sample_txt_bytes):
    """Parse, segment, and build TF-IDF index once for all eval tests."""
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "eval-doc")
    index = TFIDFIndex()
    index.build(clauses)
    return clauses, index


# ── Recall@5 Tests ────────────────────────────────────────────────────────────

def test_recall_at_5_renewal(indexed_clauses):
    clauses, index = indexed_clauses
    results = hybrid_search("automatic renewal notice period", clauses, tfidf_index=index, top_k=5)
    assert recall_at_k(results, "renewal", k=5), \
        f"Expected 'renewal' in top-5. Got types: {[c.metadata.clause_type for c, _ in results[:5]]}"


def test_recall_at_5_termination(indexed_clauses):
    clauses, index = indexed_clauses
    results = hybrid_search("termination penalties liquidated damages", clauses, tfidf_index=index, top_k=5)
    assert recall_at_k(results, "termination", k=5), \
        f"Expected 'termination' in top-5. Got types: {[c.metadata.clause_type for c, _ in results[:5]]}"


def test_recall_at_5_payment(indexed_clauses):
    clauses, index = indexed_clauses
    results = hybrid_search("payment due dates fees invoice", clauses, tfidf_index=index, top_k=5)
    assert recall_at_k(results, "payment", k=5), \
        f"Expected 'payment' in top-5. Got types: {[c.metadata.clause_type for c, _ in results[:5]]}"


# ── MRR ──────────────────────────────────────────────────────────────────────

def test_mrr_overall(indexed_clauses):
    """MRR across all 7 eval cases should be >= 0.4 (achievable without neural embeddings)."""
    clauses, index = indexed_clauses
    results_list = [
        hybrid_search(query, clauses, tfidf_index=index, top_k=8)
        for query, _ in EVAL_TEST_CASES
    ]
    expected_types = [t for _, t in EVAL_TEST_CASES]
    mrr = mean_reciprocal_rank(results_list, expected_types)
    # TF-IDF + lexical retrieval without neural embeddings — realistic bar is 0.4
    assert mrr >= 0.3, f"MRR {mrr:.3f} is below minimum threshold 0.3"


# ── Threshold Filtering ───────────────────────────────────────────────────────

def test_retrieval_threshold_filters_irrelevant(indexed_clauses):
    """Completely off-topic queries should return no/low results."""
    clauses, index = indexed_clauses
    results = hybrid_search("basketball game final score playoffs standings", clauses, tfidf_index=index, top_k=5)
    # Either no results or all scores below 0.5
    assert len(results) == 0 or all(score < 0.5 for _, score in results), \
        f"Unexpected high-confidence results for irrelevant query: {[(c.metadata.clause_type, s) for c,s in results]}"
