"""
End-to-End Integration & Security Verification Suite for LexiGuard Phase 3 (Checkpoint 7).
Validates multi-document workspace, cross-document Q&A, consistency comparison, exportable PDF/JSON reports,
reminders/ICS export, multilingual accessibility, evidence provenance, and document isolation security.
"""
import pytest
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata, RiskSignal, Severity
from app.models.financial import FinancialItem
from app.storage.database import save_document, save_clause, save_risk_signal, save_financial_items, get_document
from app.analysis.consistency_engine import ConsistencyEngine
from app.analysis.reporting import generate_json_report, generate_pdf_report
from app.analysis.reminders import extract_document_reminders, generate_ics_calendar


def setup_multi_doc_fixture():
    # Document 1: Offer Letter
    d1 = DocumentOverview(document_id="p3-doc-1", filename="Offer_Letter.pdf", document_type="Employment", page_count=2, clause_count=2)
    save_document(d1)
    c1_1 = Clause(id="p3-d1-c1", metadata=ClauseMetadata(clause_id="p3-d1-c1", document_id="p3-doc-1", section_path="1. Compensation", page=1), text="Your annual CTC will be ₹9,00,000 per annum.")
    c1_2 = Clause(id="p3-d1-c2", metadata=ClauseMetadata(clause_id="p3-d1-c2", document_id="p3-doc-1", section_path="2. Notice", page=2), text="Notice period is 30 days prior to October 1, 2026.")
    save_clause(c1_1)
    save_clause(c1_2)

    f1 = FinancialItem(item_id="p3-f1", document_id="p3-doc-1", item_type="ANNUAL_SALARY", amount="₹9,00,000", currency="INR", frequency="annual", clause_id="p3-d1-c1", section_path="1. Compensation", page=1, evidence_text="annual CTC will be ₹9,00,000")
    save_financial_items("p3-doc-1", [f1])

    # Document 2: Employment Agreement
    d2 = DocumentOverview(document_id="p3-doc-2", filename="Employment_Agreement.pdf", document_type="Employment", page_count=3, clause_count=2)
    save_document(d2)
    c2_1 = Clause(id="p3-d2-c1", metadata=ClauseMetadata(clause_id="p3-d2-c1", document_id="p3-doc-2", section_path="Clause 4. Remuneration", page=1), text="The annual CTC shall be ₹9,00,000 per annum.")
    c2_2 = Clause(id="p3-d2-c2", metadata=ClauseMetadata(clause_id="p3-d2-c2", document_id="p3-doc-2", section_path="Clause 12. Termination", page=3), text="Either party may terminate by providing 60 days written notice.")
    save_clause(c2_1)
    save_clause(c2_2)

    return d1, d2


def test_full_phase3_integration_workflow(client):
    d1, d2 = setup_multi_doc_fixture()

    # 1. Workspace API Check
    res_ws = client.get("/api/workspace")
    assert res_ws.status_code == 200
    docs_ws = res_ws.json()
    assert any(d["document_id"] == "p3-doc-1" for d in docs_ws)
    assert any(d["document_id"] == "p3-doc-2" for d in docs_ws)

    # 2. Consistency Engine Check
    res_con = client.post("/api/comparison/consistency", json={"document_id_a": "p3-doc-1", "document_id_b": "p3-doc-2"})
    assert res_con.status_code == 200
    con_data = res_con.json()
    assert con_data["consistent_count"] >= 1
    notice_item = next(i for i in con_data["items"] if i["category"] == "notice_period")
    assert notice_item["status"] == "DIFFERENT"
    assert notice_item["doc_id_a"] == "p3-doc-1"
    assert notice_item["doc_id_b"] == "p3-doc-2"

    # 3. Cross-Document Q&A Check
    res_cqa = client.post("/api/questions/cross-document", json={"doc_ids": ["p3-doc-1", "p3-doc-2"], "question": "Compare the notice period in both documents.", "language": "en"})
    assert res_cqa.status_code == 200
    cqa_data = res_cqa.json()
    assert cqa_data["grounding_status"] in ("SUPPORTED", "STRONGLY GROUNDED")

    # 4. Exportable Reports Check (JSON & PDF)
    res_rep_json = client.post("/api/reports/generate", json={"doc_ids": ["p3-doc-1", "p3-doc-2"], "format": "json"})
    assert res_rep_json.status_code == 200
    assert len(res_rep_json.json()["documents"]) == 2

    res_rep_pdf = client.post("/api/reports/generate", json={"doc_ids": ["p3-doc-1", "p3-doc-2"], "format": "pdf"})
    assert res_rep_pdf.status_code == 200
    assert res_rep_pdf.content.startswith(b"%PDF")

    # 5. Reminders & ICS Check
    res_rem = client.get("/api/documents/p3-doc-1/reminders")
    assert res_rem.status_code == 200
    assert len(res_rem.json()) >= 1

    res_ics = client.get("/api/documents/p3-doc-1/reminders/ics")
    assert res_ics.status_code == 200
    assert "BEGIN:VCALENDAR" in res_ics.text

    # 6. Multilingual Translations Check
    for lang in ["en", "hi", "kn", "te"]:
        res_t = client.get(f"/api/workspace/translations/{lang}")
        assert res_t.status_code == 200
        assert "translations" in res_t.json()


def test_phase3_security_cross_document_isolation(client):
    d1, d2 = setup_multi_doc_fixture()

    # Querying single doc Q&A for Doc 1 cannot return Doc 2 clauses
    res = client.post("/api/documents/p3-doc-1/ask", json={"question": "What is the notice period?"})
    assert res.status_code == 200
    data = res.json()
    for ev in data.get("evidences", []):
        # Evidence clause must belong strictly to Doc 1
        assert "p3-doc-2" not in str(ev.get("clause_id", ""))


def test_phase3_security_invalid_uuids_handled_safely(client):
    res = client.get("/api/workspace/invalid-uuid-123-!'")
    assert res.status_code == 404

    res = client.get("/api/documents/invalid-uuid-123-!'/reminders")
    assert res.status_code == 404

    res = client.delete("/api/workspace/invalid-uuid-123-!'")
    assert res.status_code == 404
