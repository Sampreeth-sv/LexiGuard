"""
Comparison engine tests.
Tests deterministic clause alignment, diff classification, result structure, and similarity threshold bounds.
Zero LLM calls.
"""
import pytest
from app.comparison.comparator import compare_documents, compute_text_diff_summary, SIMILARITY_THRESHOLD_MATCH, SIMILARITY_THRESHOLD_SAME
from app.models.schemas import DiffType, Clause, ClauseMetadata
import uuid


def make_clause(text: str, id_suffix: str = None, doc_id: str = "doc", section_path: str = "Section 1.1") -> Clause:
    cid = f"c-{id_suffix}" if id_suffix else str(uuid.uuid4())
    return Clause(
        id=cid,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id=doc_id,
            section_id="sec1",
            heading="Test Heading",
            section_path=section_path,
            page=1,
            clause_type="general",
            char_count=len(text),
        ),
        text=text,
    )


# ── Identical Documents ───────────────────────────────────────────────────────

def test_compare_identical_documents():
    text = "This is a standard confidentiality clause that protects proprietary information."
    clauses_a = [make_clause(text, "1", "docA"), make_clause("Payment shall be due within 30 days.", "2", "docA")]
    clauses_b = [make_clause(text, "3", "docB"), make_clause("Payment shall be due within 30 days.", "4", "docB")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")
    assert result.unchanged_count == 2
    assert len(result.added) == 0
    assert len(result.removed) == 0
    assert len(result.modified) == 0


# ── Added Clause ──────────────────────────────────────────────────────────────

def test_compare_added_clause():
    clauses_a = [make_clause("Confidentiality obligations apply.", "1", "docA")]
    clauses_b = [
        make_clause("Confidentiality obligations apply.", "2", "docB"),
        make_clause("New data security requirements added here.", "3", "docB"),
    ]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")
    assert len(result.added) >= 1


# ── Removed Clause ────────────────────────────────────────────────────────────

def test_compare_removed_clause():
    clauses_a = [
        make_clause("Confidentiality obligations apply.", "1", "docA"),
        make_clause("Non-compete clause restricts competitive activity.", "2", "docA"),
    ]
    clauses_b = [make_clause("Confidentiality obligations apply.", "3", "docB")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")
    assert len(result.removed) >= 1


# ── Modified Clause ───────────────────────────────────────────────────────────

def test_compare_modified_clause():
    clauses_a = [make_clause("The fee shall be $10,000 per month payable within 30 days.", "1", "docA")]
    clauses_b = [make_clause("The fee shall be $12,500 per month payable within 30 days.", "2", "docB")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")
    assert len(result.modified) >= 1
    assert result.modified[0].diff_type == DiffType.MODIFIED


# ── Threshold Boundary Tests (0.35 Match Threshold) ─────────────────────────

def test_threshold_0_35_classifies_moderately_modified_clause_as_modified():
    """Wording changes yielding similarity >= 0.35 must be classified as MODIFIED."""
    text_a = "XYZ TECHNOLOGIES PRIVATE LIMITED ILLUSTRATIVE OFFER LETTER & EMPLOYMENT TERMS REPORT FICTIONAL SAMPLE NOT A REAL OFFER"
    text_b = "XYZ TECHNOLOGIES PRIVATE LIMITED ILLUSTRATIVE OFFER LETTER & EMPLOYMENT TERMS AUDIT DRAFT FICTIONAL EDUCATIONAL SAMPLE"
    clauses_a = [make_clause(text_a, "1", "docA", "General")]
    clauses_b = [make_clause(text_b, "2", "docB", "General")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")

    assert len(result.modified) == 1
    assert result.modified[0].diff_type == DiffType.MODIFIED
    assert result.modified[0].similarity_score >= SIMILARITY_THRESHOLD_MATCH
    assert result.modified[0].text_a == text_a
    assert result.modified[0].text_b == text_b


def test_threshold_below_0_35_remains_added_and_removed():
    """Unrelated clauses with similarity < 0.35 must remain REMOVED and ADDED, NOT incorrectly matched."""
    text_a = "Employee notice period for resignation is thirty calendar days in writing."
    text_b = "All employees shall wear professional formal office attire on company premises."
    clauses_a = [make_clause(text_a, "1", "docA", "Section 12. Notice")]
    clauses_b = [make_clause(text_b, "2", "docB", "Section 13. Dress Code")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")

    assert len(result.modified) == 0
    assert len(result.removed) == 1
    assert len(result.added) == 1


def test_threshold_above_0_95_remains_unchanged():
    """Clauses with identical text (similarity >= 0.95) remain UNCHANGED."""
    text = "The employee agrees to maintain confidentiality of all proprietary company data."
    clauses_a = [make_clause(text, "1", "docA")]
    clauses_b = [make_clause(text, "2", "docB")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")

    assert result.unchanged_count == 1
    assert len(result.modified) == 0


# ── Result Structure ──────────────────────────────────────────────────────────

def test_compare_result_structure():
    clauses_a = [make_clause("Some legal text here.", "1", "docA")]
    clauses_b = [make_clause("Some different legal text here.", "2", "docB")]
    result = compare_documents(clauses_a, clauses_b, "docA", "docB")
    assert result.document_id_a == "docA"
    assert result.document_id_b == "docB"
    assert isinstance(result.added, list)
    assert isinstance(result.removed, list)
    assert isinstance(result.modified, list)
    assert isinstance(result.unchanged_count, int)


# ── Diff Summary ──────────────────────────────────────────────────────────────

def test_diff_summary_detects_change():
    before = "Payment shall be due within 30 days of invoice."
    after = "Payment shall be due within 60 days of invoice."
    summary = compute_text_diff_summary(before, after)
    assert len(summary) > 0
    assert summary != "No text differences."


def test_diff_summary_identical_text():
    text = "This clause is identical in both versions."
    summary = compute_text_diff_summary(text, text)
    assert summary == "No text differences."


# ── Empty Documents ───────────────────────────────────────────────────────────

def test_compare_empty_documents():
    result = compare_documents([], [], "docA", "docB")
    assert len(result.added) == 0
    assert len(result.removed) == 0
    assert len(result.modified) == 0
    assert result.unchanged_count == 0


def test_compare_one_empty_document():
    clauses_a = [make_clause("Some legal content.", "1", "docA")]
    result = compare_documents(clauses_a, [], "docA", "docB")
    assert len(result.removed) >= 1
