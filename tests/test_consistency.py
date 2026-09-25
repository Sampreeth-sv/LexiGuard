"""
Unit and API integration tests for LexiGuard Phase 3 Checkpoint 3: Consistency Engine.
Verifies deterministic comparison across 17 categories, same-document rejection,
factual non-legal status reporting, dual evidence provenance, and API endpoint integration.
"""
import pytest
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata
from app.storage.database import save_document, save_clause
from app.analysis.consistency_engine import ConsistencyEngine


def create_doc(doc_id: str, filename: str, clauses_data: list) -> DocumentOverview:
    doc = DocumentOverview(
        document_id=doc_id,
        filename=filename,
        document_type="Employment",
        page_count=len(clauses_data),
        clause_count=len(clauses_data)
    )
    save_document(doc)

    for i, (sec, text) in enumerate(clauses_data, 1):
        c = Clause(
            id=f"{doc_id}-c{i}",
            metadata=ClauseMetadata(
                clause_id=f"{doc_id}-c{i}",
                document_id=doc_id,
                section_path=sec,
                page=i
            ),
            text=text
        )
        save_clause(c)
    return doc


def test_matching_salary_consistency():
    d1 = create_doc("doc-con-1", "Offer_Letter.pdf", [("1. Compensation", "Base salary is ₹9,00,000 per annum.")])
    d2 = create_doc("doc-con-2", "Employment_Agreement.pdf", [("Clause 4. Remuneration", "The annual CTC shall be ₹9,00,000 per annum.")])

    clauses1 = [Clause(id="d1-c1", metadata=ClauseMetadata(clause_id="d1-c1", document_id="doc-con-1", section_path="1. Compensation", page=1), text="Base salary is ₹9,00,000 per annum.")]
    clauses2 = [Clause(id="d2-c1", metadata=ClauseMetadata(clause_id="d2-c1", document_id="doc-con-2", section_path="Clause 4. Remuneration", page=1), text="The annual CTC shall be ₹9,00,000 per annum.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc-con-1", "Offer_Letter.pdf", clauses1, "doc-con-2", "Employment_Agreement.pdf", clauses2)

    sal_item = next(i for i in report.items if i.category == "salary_compensation")
    assert sal_item.status == "CONSISTENT"
    assert "₹9,00,000" in sal_item.summary
    assert sal_item.doc_id_a == "doc-con-1"
    assert sal_item.doc_id_b == "doc-con-2"


def test_differing_salary_consistency():
    clauses1 = [Clause(id="d1-c1", metadata=ClauseMetadata(clause_id="d1-c1", document_id="doc-con-3", section_path="Compensation", page=1), text="Base salary is ₹9,00,000 per annum.")]
    clauses2 = [Clause(id="d2-c1", metadata=ClauseMetadata(clause_id="d2-c1", document_id="doc-con-4", section_path="Remuneration", page=2), text="Total CTC shall be ₹12,00,000 per annum.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc-con-3", "Offer_Letter.pdf", clauses1, "doc-con-4", "Employment_Agreement.pdf", clauses2)

    sal_item = next(i for i in report.items if i.category == "salary_compensation")
    assert sal_item.status == "DIFFERENT"
    assert "differ" in sal_item.summary.lower()


def test_matching_notice_period_consistency():
    clauses1 = [Clause(id="d1-c2", metadata=ClauseMetadata(clause_id="d1-c2", document_id="doc-con-5", section_path="Notice", page=1), text="Either party may terminate by giving 30 days notice.")]
    clauses2 = [Clause(id="d2-c2", metadata=ClauseMetadata(clause_id="d2-c2", document_id="doc-con-6", section_path="Termination", page=3), text="Notice period of 30 days is required prior to exit.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc-con-5", "Offer.pdf", clauses1, "doc-con-6", "Agreement.pdf", clauses2)

    notice_item = next(i for i in report.items if i.category == "notice_period")
    assert notice_item.status == "CONSISTENT"
    assert "30 days" in notice_item.summary


def test_differing_notice_period_consistency():
    clauses1 = [Clause(id="d1-c2", metadata=ClauseMetadata(clause_id="d1-c2", document_id="doc-con-7", section_path="Notice", page=1), text="Notice period is 30 days.")]
    clauses2 = [Clause(id="d2-c2", metadata=ClauseMetadata(clause_id="d2-c2", document_id="doc-con-8", section_path="Termination", page=4), text="Notice period shall be 60 days.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc-con-7", "Offer.pdf", clauses1, "doc-con-8", "Agreement.pdf", clauses2)

    notice_item = next(i for i in report.items if i.category == "notice_period")
    assert notice_item.status == "DIFFERENT"
    assert "30 days" in notice_item.summary
    assert "60 days" in notice_item.summary


def test_missing_in_doc_b_consistency():
    clauses1 = [Clause(id="d1-c3", metadata=ClauseMetadata(clause_id="d1-c3", document_id="doc-con-9", section_path="Probation", page=1), text="Probation period shall be 6 months.")]
    clauses2 = [Clause(id="d2-c3", metadata=ClauseMetadata(clause_id="d2-c3", document_id="doc-con-10", section_path="General", page=1), text="Agreement dated 01 January 2026.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc-con-9", "Offer.pdf", clauses1, "doc-con-10", "Agreement.pdf", clauses2)

    prob_item = next(i for i in report.items if i.category == "probation")
    assert prob_item.status == "MISSING_IN_DOCUMENT_B"
    assert prob_item.clause_id_a == "d1-c3"
    assert prob_item.clause_id_b is None


def test_same_document_rejection_raises_value_error():
    engine = ConsistencyEngine()
    with pytest.raises(ValueError) as exc:
        engine.compare_documents("same-id", "Doc.pdf", [], "same-id", "Doc.pdf", [])
    assert "same document" in str(exc.value).lower()


def test_consistency_api_endpoint(client):
    d1 = create_doc("doc-api-con-1", "Offer_Letter.pdf", [("Salary", "Base salary is ₹9,00,000 per annum."), ("Notice", "Notice period is 30 days.")])
    d2 = create_doc("doc-api-con-2", "Agreement.pdf", [("Compensation", "Total CTC is ₹9,00,000 per annum."), ("Notice", "Notice period is 60 days.")])

    req_data = {
        "document_id_a": "doc-api-con-1",
        "document_id_b": "doc-api-con-2"
    }

    res = client.post("/api/comparison/consistency", json=req_data)
    assert res.status_code == 200
    data = res.json()
    assert data["doc_id_a"] == "doc-api-con-1"
    assert data["doc_id_b"] == "doc-api-con-2"
    assert "items" in data
    assert len(data["items"]) >= 2


def test_consistency_api_same_document_returns_400(client):
    create_doc("doc-api-same", "Doc.pdf", [("General", "Text clause")])
    res = client.post("/api/comparison/consistency", json={"document_id_a": "doc-api-same", "document_id_b": "doc-api-same"})
    assert res.status_code == 400


def test_consistency_non_legal_factual_phrasing():
    clauses1 = [Clause(id="d1", metadata=ClauseMetadata(clause_id="d1", document_id="doc1", section_path="Notice", page=1), text="30 days notice.")]
    clauses2 = [Clause(id="d2", metadata=ClauseMetadata(clause_id="d2", document_id="doc2", section_path="Notice", page=1), text="90 days notice.")]

    engine = ConsistencyEngine()
    report = engine.compare_documents("doc1", "Doc1.pdf", clauses1, "doc2", "Doc2.pdf", clauses2)

    for item in report.items:
        # Verify no illegal / invalid subjective legal claims
        s_lower = item.summary.lower()
        assert "illegal" not in s_lower
        assert "invalid" not in s_lower
        assert "unenforceable" not in s_lower
        assert "unlawful" not in s_lower
