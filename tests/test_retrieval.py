"""
Retrieval system tests: lexical search, TF-IDF, hybrid search, reranker.
All tests are deterministic — no LLM calls.
"""
import pytest
from app.retrieval.lexical import normalize_query, compute_lexical_score, search_lexical
from app.retrieval.tfidf import TFIDFIndex
from app.retrieval.hybrid import hybrid_search, expand_query
from app.retrieval.reranker import rerank
from app.ingestion.text_parser import extract_text_from_txt
from app.ingestion.structure import segment_document
from app.models.schemas import Clause, ClauseMetadata
import uuid


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_clause(text: str, clause_type: str = "general", section_path: str = "General") -> Clause:
    cid = str(uuid.uuid4())
    return Clause(
        id=cid,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id="test-doc",
            section_id="sec1",
            heading=text[:40],
            section_path=section_path,
            page=1,
            clause_type=clause_type,
            char_count=len(text),
        ),
        text=text,
    )


def get_sample_clauses(sample_txt_bytes) -> list:
    pages = extract_text_from_txt(sample_txt_bytes)
    return segment_document(pages, "eval-doc")


# ── Normalize Query ───────────────────────────────────────────────────────────

def test_normalize_query_lowercase():
    assert normalize_query("Hello World!") == "hello world"


def test_normalize_query_strips_punctuation():
    result = normalize_query("test, query!")
    assert "," not in result
    assert "!" not in result


def test_normalize_query_whitespace():
    result = normalize_query("  extra   spaces  ")
    assert result == result.strip()
    assert "  " not in result


# ── Lexical Score ─────────────────────────────────────────────────────────────

def test_lexical_score_exact_match():
    clause = make_clause("this agreement shall automatically renew")
    score = compute_lexical_score("automatically renew", clause)
    assert score > 0.5


def test_lexical_score_no_match():
    clause = make_clause("banana orange pineapple fruit salad")
    score = compute_lexical_score("arbitration dispute", clause)
    assert score < 0.2


def test_lexical_score_partial_match():
    clause = make_clause("payment shall be made within 30 days of invoice")
    score = compute_lexical_score("payment invoice deadline", clause)
    assert 0.0 < score < 1.0


def test_lexical_score_phrase_boost():
    clause = make_clause("binding arbitration shall resolve all disputes")
    score = compute_lexical_score("binding arbitration", clause)
    assert score > 0.3  # Phrase match should give a boost


def test_search_lexical_returns_top_k():
    clauses = [
        make_clause("automatic renewal clause"),
        make_clause("termination rights"),
        make_clause("payment schedule"),
    ]
    results = search_lexical("automatic renewal", clauses, top_k=2)
    assert len(results) <= 2


def test_search_lexical_ordered():
    clauses = [
        make_clause("automatic renewal clause is important"),
        make_clause("some unrelated content about other topics"),
    ]
    results = search_lexical("automatic renewal", clauses, top_k=5)
    if len(results) >= 2:
        assert results[0][1] >= results[1][1]


# ── TF-IDF Index ──────────────────────────────────────────────────────────────

def test_tfidf_build_and_search():
    renewal_clause = make_clause(
        "This agreement shall automatically renew for successive one-year terms upon automatic renewal notice.",
        clause_type="renewal"
    )
    index = TFIDFIndex()
    index.build([renewal_clause])
    results = index.search("automatic renewal", top_k=1)
    assert len(results) == 1
    assert results[0][0].id == renewal_clause.id


def test_tfidf_search_unrelated():
    clause = make_clause("The parties agree to the following payment terms and conditions.")
    index = TFIDFIndex()
    index.build([clause])
    results = index.search("basketball game score", top_k=1)
    # Either no results or very low score
    assert len(results) == 0 or results[0][1] < 0.2


def test_tfidf_search_empty_index():
    index = TFIDFIndex()
    results = index.search("any query")
    assert results == []


def test_tfidf_is_built_flag():
    index = TFIDFIndex()
    assert not index.is_built()
    index.build([make_clause("some text")])
    assert index.is_built()


# ── Hybrid Search ─────────────────────────────────────────────────────────────

def test_hybrid_search_finds_renewal_clause(sample_txt_bytes):
    clauses = get_sample_clauses(sample_txt_bytes)
    index = TFIDFIndex()
    index.build(clauses)
    results = hybrid_search("automatic renewal", clauses, tfidf_index=index, top_k=5)
    assert len(results) > 0
    # Top result should have renewal-related content
    top_text = results[0][0].text.lower()
    assert "renew" in top_text or "renewal" in top_text


def test_hybrid_search_irrelevant_low_score(sample_txt_bytes):
    clauses = get_sample_clauses(sample_txt_bytes)
    index = TFIDFIndex()
    index.build(clauses)
    results = hybrid_search("basketball scores playoffs", clauses, tfidf_index=index, top_k=5)
    assert len(results) == 0 or all(score < 0.4 for _, score in results)


def test_hybrid_search_empty_query():
    clause = make_clause("some text")
    index = TFIDFIndex()
    index.build([clause])
    results = hybrid_search("", [clause], tfidf_index=index)
    assert results == []


# ── Query Expansion ───────────────────────────────────────────────────────────

def test_expand_query_terminate():
    expanded = expand_query("terminate")
    assert "termination" in expanded or "cancel" in expanded


def test_expand_query_renew():
    expanded = expand_query("renew")
    assert "renewal" in expanded or "auto-renew" in expanded


# ── Reranker ──────────────────────────────────────────────────────────────────

def test_reranker_deduplication():
    clause = make_clause("This agreement shall automatically renew.")
    results = [(clause, 1.0), (clause, 0.9)]  # Same clause twice
    reranked = rerank(results, "renew", top_k=5)
    assert len(reranked) == 1  # Deduplication should remove the duplicate


def test_reranker_top_k():
    clauses = [make_clause(f"clause {i}") for i in range(10)]
    results = [(c, float(i) / 10) for i, c in enumerate(clauses)]
    reranked = rerank(results, "query", top_k=3)
    assert len(reranked) <= 3


def test_reranker_sorted_by_score():
    c1 = make_clause("high score content renewal")
    c2 = make_clause("medium score content")
    c3 = make_clause("low score content")
    results = [(c1, 0.9), (c2, 0.5), (c3, 0.1)]
    reranked = rerank(results, "renewal", top_k=5)
    scores = [s for _, s in reranked]
    assert scores == sorted(scores, reverse=True)


def test_reranker_empty_input():
    reranked = rerank([], "query", top_k=5)
    assert reranked == []
