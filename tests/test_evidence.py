"""
Tests for LexiGuard Phase 2 Feature 1: Click-to-Evidence PDF Highlighting.
Verifies evidence provenance lookup, cross-document security validation,
file serving, exact/fallback match statuses, and safe error handling.
"""
import pytest
import uuid
import os
from fastapi.testclient import TestClient
from app.main import app
from app.storage.database import save_document, save_clause
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata
from app.config import settings


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_doc_with_file(temp_dir):
    """Fixture creating a document record and saving a sample PDF/TXT file on disk."""
    doc_id = str(uuid.uuid4())
    doc = DocumentOverview(
        document_id=doc_id,
        filename="sample_contract.pdf",
        page_count=3,
        clause_count=2,
        signal_count=1,
    )
    save_document(doc)

    clause_id1 = str(uuid.uuid4())
    meta1 = ClauseMetadata(
        clause_id=clause_id1,
        document_id=doc_id,
        section_id="sec-1-1",
        heading="Section 1.1 Confidentiality",
        section_path="Article I > Section 1.1",
        page=2,
        clause_type="confidentiality",
        char_count=150,
    )
    clause1 = Clause(
        id=clause_id1,
        metadata=meta1,
        text="The recipient agrees to keep all proprietary information strictly confidential for three years."
    )
    save_clause(clause1)

    clause_id2 = str(uuid.uuid4())
    meta2 = ClauseMetadata(
        clause_id=clause_id2,
        document_id=doc_id,
        section_id="sec-2-1",
        heading="Section 2.1 Liability",
        section_path="Article II > Section 2.1",
        page=3,
        clause_type="liability",
        char_count=120,
    )
    clause2 = Clause(
        id=clause_id2,
        metadata=meta2,
        text="Neither party shall be liable for indirect, special, or consequential damages."
    )
    save_clause(clause2)

    # Save mock file bytes in upload_temp_dir
    os.makedirs(settings.upload_temp_dir, exist_ok=True)
    pdf_path = os.path.join(settings.upload_temp_dir, f"{doc_id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 Mock PDF file content for testing evidence viewer.")

    return {
        "doc_id": doc_id,
        "clause_id1": clause_id1,
        "clause_id2": clause_id2,
        "clause1": clause1,
        "clause2": clause2,
        "pdf_path": pdf_path,
    }


def test_get_evidence_location_valid(client, sample_doc_with_file):
    """1. Valid document + valid clause returns 200 with provenance details."""
    doc_id = sample_doc_with_file["doc_id"]
    clause_id = sample_doc_with_file["clause_id1"]

    res = client.get(f"/api/documents/{doc_id}/evidence/{clause_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == doc_id
    assert data["clause_id"] == clause_id
    assert data["page_number"] == 2
    assert data["section_path"] == "Article I > Section 1.1"
    assert "strictly confidential" in data["clause_text"]
    assert data["file_type"] == "pdf"


def test_get_evidence_location_invalid_doc(client, sample_doc_with_file):
    """2. Invalid document ID returns 404."""
    clause_id = sample_doc_with_file["clause_id1"]
    res = client.get(f"/api/documents/non-existent-doc-id/evidence/{clause_id}")
    assert res.status_code == 404
    assert "Document not found" in res.json()["detail"]


def test_get_evidence_location_invalid_clause(client, sample_doc_with_file):
    """3. Invalid clause ID returns 404."""
    doc_id = sample_doc_with_file["doc_id"]
    res = client.get(f"/api/documents/{doc_id}/evidence/non-existent-clause-id")
    assert res.status_code == 404
    assert "Clause not found" in res.json()["detail"]


def test_get_evidence_location_cross_document(client, sample_doc_with_file):
    """4. Clause belonging to a different document is rejected with 400 (Security)."""
    # Create second doc
    other_doc_id = str(uuid.uuid4())
    other_doc = DocumentOverview(document_id=other_doc_id, filename="other.pdf")
    save_document(other_doc)

    clause_id = sample_doc_with_file["clause_id1"]
    # Request clause_id under other_doc_id
    res = client.get(f"/api/documents/{other_doc_id}/evidence/{clause_id}")
    assert res.status_code == 400
    assert "does not belong" in res.json()["detail"]


def test_get_document_file_endpoint_valid(client, sample_doc_with_file):
    """5. GET /api/documents/{doc_id}/file serves saved file content."""
    doc_id = sample_doc_with_file["doc_id"]
    res = client.get(f"/api/documents/{doc_id}/file")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert b"%PDF-1.4" in res.content


def test_get_document_file_endpoint_invalid_doc(client):
    """6. GET /api/documents/{doc_id}/file with invalid doc ID returns 404."""
    res = client.get("/api/documents/invalid-doc-id/file")
    assert res.status_code == 404


def test_evidence_exact_text_match(client, sample_doc_with_file):
    """7. Exact evidence quote returns match_status == 'exact_highlight_available' and offsets."""
    doc_id = sample_doc_with_file["doc_id"]
    clause_id = sample_doc_with_file["clause_id1"]
    quote = "strictly confidential"

    res = client.get(f"/api/documents/{doc_id}/evidence/{clause_id}?evidence_quote={quote}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "exact_highlight_available"
    assert data["char_start"] is not None
    assert data["char_end"] == data["char_start"] + len(quote)


def test_evidence_quote_not_found_on_page(client, sample_doc_with_file):
    """8. Unmatched quote falls back safely to 'page_level_available' without crashing."""
    doc_id = sample_doc_with_file["doc_id"]
    clause_id = sample_doc_with_file["clause_id1"]
    quote = "unrelated phrase not present in clause text"

    res = client.get(f"/api/documents/{doc_id}/evidence/{clause_id}?evidence_quote={quote}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "page_level_available"
    assert data["char_start"] is None
    assert data["char_end"] is None


def test_missing_page_provenance_fallback(client):
    """9. Missing/invalid page provenance (< 1) returns 'location_unavailable'."""
    doc_id = str(uuid.uuid4())
    doc = DocumentOverview(document_id=doc_id, filename="nopage.pdf")
    save_document(doc)

    clause_id = str(uuid.uuid4())
    meta = ClauseMetadata(
        clause_id=clause_id,
        document_id=doc_id,
        page=0,  # Invalid page
    )
    clause = Clause(id=clause_id, metadata=meta, text="Some clause text with no valid page.")
    save_clause(clause)

    res = client.get(f"/api/documents/{doc_id}/evidence/{clause_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "location_unavailable"


def test_upload_persists_file(client):
    """10. File upload persists file bytes to upload_temp_dir."""
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "ARTICLE I - PERSISTENCE TEST\n\nSection 1.1 Test clause for persistence.")
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/documents/",
        files={"file": ("persist_test.pdf", pdf_bytes, "application/pdf")}
    )
    assert res.status_code == 200
    doc_id = res.json()["document_id"]

    # Verify file endpoint can serve it
    file_res = client.get(f"/api/documents/{doc_id}/file")
    assert file_res.status_code == 200
    assert file_res.content == pdf_bytes
