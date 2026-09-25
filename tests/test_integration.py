"""
Comprehensive Phase 1 Integration Tests for LexiGuard.
Verifies API contract endpoints, CORS settings, database foreign keys, cascade deletion,
status route, unmatched route 404 JSON fallback, checklist, summary, and explain-diff.
"""
import pytest
import sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.storage.database import (
    get_db_connection, save_document, save_clause, save_risk_signal,
    get_document, get_clauses, get_risk_signals, delete_document
)
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata, RiskSignal, Severity
from datetime import datetime
import uuid


def upload_sample_doc(client, sample_txt_bytes, filename="test_doc.txt") -> str:
    res = client.post("/api/documents/", files={"file": (filename, sample_txt_bytes, "text/plain")})
    assert res.status_code == 200, f"Upload failed: {res.text}"
    return res.json()["document_id"]


# ── System Status & Router Fallback ──────────────────────────────────────────

def test_system_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "genai_available" in data
    assert "gemini_model" in data
    assert data["version"] == "1.0.0"


def test_unmatched_api_routes_return_404_json(client):
    """Unmatched /api/* routes must return 404 JSON, NOT 200 HTML index."""
    res = client.get("/api/nonexistent_endpoint_xyz")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")
    data = res.json()
    assert "error" in data
    assert data["error"] == "Not Found"


def test_cors_configuration(client):
    """Verify CORS headers are returned for allowed origins."""
    origin = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:8000"
    res = client.options(
        "/api/documents/",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    # Fastapi CORSMiddleware handles preflight
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


# ── Document Metadata & List Endpoints ────────────────────────────────────────

def test_document_list_metadata_fields(client, sample_txt_bytes):
    """Verify listDocuments response includes created_at and clause_count for dropdown disambiguation."""
    doc_id = upload_sample_doc(client, sample_txt_bytes)
    res = client.get("/api/documents/")
    assert res.status_code == 200
    docs = res.json()
    assert isinstance(docs, list)
    target = next((d for d in docs if d["document_id"] == doc_id), None)
    assert target is not None
    assert "created_at" in target
    assert "clause_count" in target
    assert target["clause_count"] >= 1


# ── Checklist & Summary Endpoints ─────────────────────────────────────────────

def test_checklist_endpoint(client, sample_txt_bytes):
    doc_id = upload_sample_doc(client, sample_txt_bytes)
    res = client.get(f"/api/documents/{doc_id}/checklist")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) > 0
    first_item = data["items"][0]
    assert "item" in first_item
    assert "category" in first_item


def test_summary_endpoint(client, sample_txt_bytes):
    doc_id = upload_sample_doc(client, sample_txt_bytes)
    res = client.post(f"/api/documents/{doc_id}/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == doc_id
    assert "summary" in data
    assert len(data["summary"]) > 0
    assert "genai_used" in data


def test_explain_diff_endpoint(client):
    payload = {
        "before_text": "Either party may terminate upon 30 days notice.",
        "after_text": "Either party may terminate upon 90 days notice with a 2-month fee penalty.",
        "section_path": "Article IV > Section 4.1"
    }
    res = client.post("/api/compare/explain-diff", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "explanation" in data
    assert len(data["explanation"]) > 0


# ── Database Isolation, Foreign Keys & Cascade Deletion ────────────────────────

def test_database_foreign_key_enforcement():
    """Verify that SQLite foreign key constraint blocks inserting a clause for a missing document."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO clauses (id, document_id, metadata, text) VALUES (?, ?, ?, ?)",
                ("c1", "nonexistent-doc-id", "{}", "Sample clause text")
            )


def test_database_cascade_deletion_no_orphans(client, sample_txt_bytes):
    """Verify that deleting a document cascades and leaves zero orphaned clauses or risk signals."""
    doc_id = upload_sample_doc(client, sample_txt_bytes)
    
    # Confirm clauses and signals were saved
    clauses_before = get_clauses(doc_id)
    signals_before = get_risk_signals(doc_id)
    assert len(clauses_before) > 0
    assert len(signals_before) >= 0

    # Delete via API
    res = client.delete(f"/api/documents/{doc_id}")
    assert res.status_code == 204

    # Verify no document, clauses, or risk signals remain
    assert get_document(doc_id) is None
    assert len(get_clauses(doc_id)) == 0
    assert len(get_risk_signals(doc_id)) == 0

    # Also query SQLite directly
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clauses WHERE document_id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM risk_signals WHERE document_id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 0


def test_spa_index_html_serving(client):
    """Verify that root / serves index.html containing frontend routing anchors and empty states."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "LexiGuard" in res.text
    assert "analyze-empty-state" in res.text
    assert "analyze-error-state" in res.text

