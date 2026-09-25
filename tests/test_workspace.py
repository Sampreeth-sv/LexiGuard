"""
Unit and API integration tests for LexiGuard Phase 3 Checkpoint 1: Multi-Document Workspace.
Verifies workspace document listing, metric calculations, selection, cascade deletion,
document switching isolation, invalid ID safety, and multi-document state handling.
"""
import pytest
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata, RiskSignal, Severity
from app.models.relationship import ClauseRelationship, ClauseRelationshipStatus, ClauseRelationshipType
from app.models.financial import FinancialItem
from app.storage.database import (
    save_document, save_clause, save_risk_signal, save_relationships,
    save_financial_items, get_document, get_clauses, get_risk_signals,
    get_relationships, get_financial_items, delete_document, list_workspace_documents
)


def create_mock_doc(doc_id: str, filename: str) -> DocumentOverview:
    doc = DocumentOverview(
        document_id=doc_id,
        filename=filename,
        document_type="Employment",
        page_count=3,
        clause_count=2,
        signal_count=1
    )
    save_document(doc)
    return doc


def populate_mock_doc_data(doc_id: str):
    c1 = Clause(
        id=f"{doc_id}-c1",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c1", document_id=doc_id, section_path="1. Salary", page=1),
        text="The annual CTC is ₹9,00,000."
    )
    c2 = Clause(
        id=f"{doc_id}-c2",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c2", document_id=doc_id, section_path="2. Notice", page=2),
        text="Notice period is 30 days."
    )
    save_clause(c1)
    save_clause(c2)

    sig = RiskSignal(
        id=f"{doc_id}-sig1",
        clause_id=f"{doc_id}-c2",
        document_id=doc_id,
        category="notice",
        severity=Severity.HIGH,
        evidence_text="30 days notice",
        section_path="2. Notice",
        page=2,
        plain_explanation="Short notice period"
    )
    save_risk_signal(sig)

    rel = ClauseRelationship(
        relationship_id=f"{doc_id}-rel1",
        document_id=doc_id,
        relationship_type=ClauseRelationshipType.TERMINATION_NOTICE,
        relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
        source_clause_id=f"{doc_id}-c2",
        source_section_path="2. Notice",
        source_page=2,
        source_excerpt="30 days notice",
        title="Termination Notice Pair",
        explanation="Termination notice requirement"
    )
    save_relationships(doc_id, [rel])

    fin = FinancialItem(
        item_id=f"{doc_id}-fin1",
        document_id=doc_id,
        item_type="ANNUAL_SALARY",
        amount="₹9,00,000",
        currency="INR",
        frequency="annual",
        clause_id=f"{doc_id}-c1",
        section_path="1. Salary",
        page=1,
        evidence_text="annual CTC is ₹9,00,000"
    )
    save_financial_items(doc_id, [fin])


def test_empty_workspace_returns_empty_list():
    # Workspace returns empty list when no documents exist (or filtered)
    docs = list_workspace_documents()
    assert isinstance(docs, list)


def test_workspace_listing_includes_document_metrics():
    doc_id = "doc-ws-1"
    create_mock_doc(doc_id, "Offer_Letter_1.pdf")
    populate_mock_doc_data(doc_id)

    docs = list_workspace_documents()
    target = next((d for d in docs if d["document_id"] == doc_id), None)
    assert target is not None
    assert target["filename"] == "Offer_Letter_1.pdf"
    assert target["page_count"] == 3
    assert target["clause_count"] == 2
    assert target["attention_signal_count"] == 1
    assert target["relationship_count"] == 1
    assert target["financial_item_count"] == 1


def test_workspace_api_endpoint(client):
    doc_id = "doc-ws-api-1"
    create_mock_doc(doc_id, "Employment_Agreement.docx")
    populate_mock_doc_data(doc_id)

    res = client.get("/api/workspace")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    target = next((d for d in data if d["document_id"] == doc_id), None)
    assert target is not None
    assert target["filename"] == "Employment_Agreement.docx"


def test_workspace_get_specific_document_api(client):
    doc_id = "doc-ws-api-2"
    create_mock_doc(doc_id, "NDA_Contract.txt")

    res = client.get(f"/api/workspace/{doc_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == doc_id
    assert data["filename"] == "NDA_Contract.txt"


def test_workspace_get_nonexistent_document_returns_404(client):
    res = client.get("/api/workspace/nonexistent-id-999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_workspace_delete_document_cascades_properly(client):
    doc_id = "doc-ws-del-1"
    create_mock_doc(doc_id, "Temporary_Doc.pdf")
    populate_mock_doc_data(doc_id)

    # Verify data exists before delete
    assert get_document(doc_id) is not None
    assert len(get_clauses(doc_id)) == 2
    assert len(get_risk_signals(doc_id)) == 1
    assert len(get_relationships(doc_id)) == 1
    assert len(get_financial_items(doc_id)) == 1

    # Delete via API
    res = client.delete(f"/api/workspace/{doc_id}")
    assert res.status_code == 200

    # Verify cascading cleanup
    assert get_document(doc_id) is None
    assert len(get_clauses(doc_id)) == 0
    assert len(get_risk_signals(doc_id)) == 0
    assert len(get_relationships(doc_id)) == 0
    assert len(get_financial_items(doc_id)) == 0


def test_delete_nonexistent_workspace_document_returns_404(client):
    res = client.delete("/api/workspace/fake-nonexistent-doc")
    assert res.status_code == 404


def test_multi_document_isolation():
    doc_a = "doc-iso-A"
    doc_b = "doc-iso-B"

    create_mock_doc(doc_a, "Doc_A.pdf")
    populate_mock_doc_data(doc_a)

    create_mock_doc(doc_b, "Doc_B.pdf")
    populate_mock_doc_data(doc_b)

    clauses_a = get_clauses(doc_a)
    clauses_b = get_clauses(doc_b)

    assert len(clauses_a) == 2
    assert len(clauses_b) == 2
    assert all(c["document_id"] == doc_a for c in clauses_a)
    assert all(c["document_id"] == doc_b for c in clauses_b)

    # Deleting Doc A does not delete Doc B
    delete_document(doc_a)
    assert get_document(doc_a) is None
    assert get_document(doc_b) is not None
    assert len(get_clauses(doc_b)) == 2


def test_workspace_repeated_listing_determinism():
    doc_id = "doc-ws-rep"
    create_mock_doc(doc_id, "Repeated_List_Test.pdf")

    list1 = list_workspace_documents()
    list2 = list_workspace_documents()

    assert len(list1) == len(list2)
    t1 = next(d for d in list1 if d["document_id"] == doc_id)
    t2 = next(d for d in list2 if d["document_id"] == doc_id)
    assert t1["filename"] == t2["filename"]
