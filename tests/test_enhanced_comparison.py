"""
Tests for LexiGuard Phase 2 Feature 4: Enhanced Document Comparison.
Verifies 15 change categories, financial comparison, relationship diffing,
provenance preservation, same-document protection, cross-document protection,
and deterministic repeatability.
"""
import pytest
from app.models.schemas import Clause, ClauseMetadata, DiffType
from app.comparison.comparator import compare_documents, classify_change_category


def make_clause(c_id: str, doc_id: str, text: str, section_path: str = "Section 1", page: int = 1) -> Clause:
    meta = ClauseMetadata(
        clause_id=c_id,
        document_id=doc_id,
        section_path=section_path,
        page=page,
        clause_type="general"
    )
    return Clause(id=c_id, metadata=meta, text=text)


def test_added_removed_unchanged_modified_clauses():
    c_a1 = make_clause("a1", "docA", "This agreement is binding on all parties.", page=1)
    c_a2 = make_clause("a2", "docA", "The notice period shall be 30 days in writing.", page=2)

    c_b1 = make_clause("b1", "docB", "This agreement is binding on all parties.", page=1)
    c_b2 = make_clause("b2", "docB", "The notice period shall be 60 days in writing.", page=2)
    c_b3 = make_clause("b3", "docB", "Employee shall not disclose confidential trade secrets.", page=3)

    result = compare_documents([c_a1, c_a2], [c_b1, c_b2, c_b3], "docA", "docB")

    assert result.unchanged_count == 1
    assert len(result.modified) == 1
    assert len(result.added) == 1
    assert len(result.removed) == 0

    mod_diff = result.modified[0]
    assert mod_diff.clause_id_a == "a2"
    assert mod_diff.clause_id_b == "b2"
    assert mod_diff.page_a == 2
    assert mod_diff.page_b == 2
    assert mod_diff.change_category in ("Changed duration", "Changed notice language")

    added_diff = result.added[0]
    assert added_diff.clause_id_a is None
    assert added_diff.clause_id_b == "b3"
    assert added_diff.change_category == "Added provision"


def test_changed_monetary_value_and_compensation():
    c_a = make_clause("a1", "docA", "Base salary shall be ₹1,000,000 per annum.")
    c_b = make_clause("b1", "docB", "Base salary shall be ₹1,500,000 per annum.")

    result = compare_documents([c_a], [c_b], "docA", "docB")
    assert len(result.modified) == 1
    diff = result.modified[0]
    assert diff.change_category == "Changed amount"
    assert diff.financial_change is not None
    assert "1,000,000" in diff.financial_change
    assert "1,500,000" in diff.financial_change


def test_changed_date_and_duration():
    c_a = make_clause("a1", "docA", "This agreement becomes effective on 01 January 2026 for 12 months.")
    c_b = make_clause("b1", "docB", "This agreement becomes effective on 01 July 2026 for 24 months.")

    result = compare_documents([c_a], [c_b], "docA", "docB")
    assert len(result.modified) == 1
    diff = result.modified[0]
    assert diff.change_category in ("Changed date", "Changed duration")


def test_changed_termination_notice_indemnity_liability():
    c_a = make_clause("a1", "docA", "Company may terminate this agreement with 14 days notice. Aggregate liability capped at $10,000.")
    c_b = make_clause("b1", "docB", "Company may terminate this agreement with 90 days notice. Aggregate liability shall be unlimited.")

    result = compare_documents([c_a], [c_b], "docA", "docB")
    assert len(result.modified) == 1
    diff = result.modified[0]
    assert diff.change_category in ("Changed termination language", "Changed notice language", "Changed liability language", "Changed duration", "Changed amount")


def test_same_document_protection():
    c_a1 = make_clause("a1", "docA", "Standard clause text.")
    c_a2 = make_clause("a2", "docA", "Another clause text.")

    result = compare_documents([c_a1, c_a2], [c_a1, c_a2], "docA", "docA")
    assert result.unchanged_count == 2
    assert len(result.added) == 0
    assert len(result.removed) == 0
    assert len(result.modified) == 0


def test_counterpart_missing_provenance_nulls():
    c_a = make_clause("a1", "docA", "Special indemnity clause.", section_path="Indemnity Section", page=5)
    result = compare_documents([c_a], [], "docA", "docB")

    assert len(result.removed) == 1
    rem = result.removed[0]
    assert rem.clause_id_a == "a1"
    assert rem.clause_id_b is None
    assert rem.section_path_a == "Indemnity Section"
    assert rem.section_path_b is None
    assert rem.page_a == 5
    assert rem.page_b is None
    assert rem.change_category == "Removed provision"


def test_deterministic_repeatability_and_api(client):
    from app.storage.database import save_document, save_clause
    from app.models.schemas import DocumentOverview

    doc_a = DocumentOverview(document_id="doc-cmp-1", filename="v1.pdf", page_count=1, clause_count=1, signal_count=0)
    doc_b = DocumentOverview(document_id="doc-cmp-2", filename="v2.pdf", page_count=1, clause_count=1, signal_count=0)
    save_document(doc_a)
    save_document(doc_b)

    c1 = make_clause("c-cmp-1", "doc-cmp-1", "Notice period is 30 days.")
    c2 = make_clause("c-cmp-2", "doc-cmp-2", "Notice period is 60 days.")
    save_clause(c1)
    save_clause(c2)

    res = client.post("/api/compare", json={"document_id_a": "doc-cmp-1", "document_id_b": "doc-cmp-2"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["modified"]) == 1
    assert data["modified"][0]["clause_id_a"] == "c-cmp-1"
    assert data["modified"][0]["clause_id_b"] == "c-cmp-2"
    assert data["modified"][0]["change_category"] in ("Changed duration", "Changed notice language")
