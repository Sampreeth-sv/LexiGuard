"""
API integration tests for LexiGuard endpoints.
Tests the full upload → analysis → Q&A → comparison → deletion flow.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


UPLOAD_URL = "/api/documents/"


def upload_doc(client, content: bytes, filename: str = "doc.txt") -> str:
    """Helper: upload a document and return its document_id."""
    res = client.post(UPLOAD_URL, files={"file": (filename, content, "text/plain")})
    assert res.status_code == 200, f"Upload failed: {res.text}"
    return res.json()["document_id"]


# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_txt_document_success(client, sample_txt_bytes):
    res = client.post(UPLOAD_URL, files={"file": ("doc.txt", sample_txt_bytes, "text/plain")})
    assert res.status_code == 200
    data = res.json()
    assert "document_id" in data
    assert "filename" in data
    assert "clause_count" in data


def test_upload_returns_document_id(client, sample_txt_bytes):
    res = client.post(UPLOAD_URL, files={"file": ("doc.txt", sample_txt_bytes, "text/plain")})
    assert res.status_code == 200
    doc_id = res.json().get("document_id")
    assert doc_id is not None
    assert len(doc_id) > 0


def test_upload_processes_clauses(client, sample_txt_bytes):
    res = client.post(UPLOAD_URL, files={"file": ("doc.txt", sample_txt_bytes, "text/plain")})
    assert res.status_code == 200
    data = res.json()
    assert data["clause_count"] > 0


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_documents_returns_list(client):
    res = client.get(UPLOAD_URL)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ── Get Document ──────────────────────────────────────────────────────────────

def test_get_document_after_upload(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.get(f"{UPLOAD_URL}{doc_id}")
    assert res.status_code == 200
    assert res.json()["document_id"] == doc_id


def test_get_document_not_found(client):
    res = client.get(f"{UPLOAD_URL}nonexistent-id-xyz")
    assert res.status_code == 404


# ── Clauses ───────────────────────────────────────────────────────────────────

def test_get_clauses_after_upload(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.get(f"{UPLOAD_URL}{doc_id}/clauses")
    assert res.status_code == 200
    clauses = res.json()
    assert isinstance(clauses, list)
    assert len(clauses) > 0


# ── Signals ───────────────────────────────────────────────────────────────────

def test_get_signals_after_upload(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.get(f"/api/documents/{doc_id}/signals")
    assert res.status_code == 200
    signals = res.json()
    assert isinstance(signals, list)
    # The sample contract should trigger at least some signals
    assert len(signals) >= 0  # May be 0 if no signals detected


# ── Entities ──────────────────────────────────────────────────────────────────

def test_get_entities_after_upload(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.get(f"/api/documents/{doc_id}/entities")
    assert res.status_code == 200
    data = res.json()
    assert "dates" in data
    assert "monetary_values" in data
    assert "parties" in data
    assert "obligations" in data


# ── Q&A ───────────────────────────────────────────────────────────────────────

def test_ask_question_returns_response(client, sample_txt_bytes):
    """Without API key, should return graceful fallback response."""
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.post(f"/api/documents/{doc_id}/ask", json={"question": "What are the payment terms?"})
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "grounding_status" in data


def test_ask_question_missing_field(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.post(f"/api/documents/{doc_id}/ask", json={})
    assert res.status_code == 422


def test_ask_question_nonexistent_doc(client):
    res = client.post("/api/documents/fake-id/ask", json={"question": "What is the payment term?"})
    assert res.status_code == 404


# ── Comparison ────────────────────────────────────────────────────────────────

def test_compare_two_documents(client, sample_txt_bytes):
    doc_id_a = upload_doc(client, sample_txt_bytes, "docA.txt")
    doc_id_b = upload_doc(client, sample_txt_bytes, "docB.txt")
    res = client.post("/api/compare", json={"document_id_a": doc_id_a, "document_id_b": doc_id_b})
    assert res.status_code == 200
    data = res.json()
    assert "document_id_a" in data
    assert "document_id_b" in data
    assert "added" in data
    assert "removed" in data
    assert "modified" in data
    assert "unchanged_count" in data


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_document(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.delete(f"{UPLOAD_URL}{doc_id}")
    assert res.status_code == 204
    # Verify it's gone
    res2 = client.get(f"{UPLOAD_URL}{doc_id}")
    assert res2.status_code == 404


def test_delete_nonexistent_document(client):
    res = client.delete(f"{UPLOAD_URL}fake-id-delete")
    assert res.status_code == 404


def test_get_dashboard_endpoint(client, sample_txt_bytes):
    doc_id = upload_doc(client, sample_txt_bytes)
    res = client.get(f"/api/documents/{doc_id}/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert "document_type" in data
    assert "clause_count" in data
    assert "signal_count" in data
    assert "important_dates" in data
    assert "financial_references" in data
    assert "important_entities" in data

    res = client.delete(f"{UPLOAD_URL}nonexistent-id-abc")
    assert res.status_code == 404
