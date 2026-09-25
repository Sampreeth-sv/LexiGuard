"""
Unit and API integration tests for LexiGuard Phase 3 Checkpoint 4: Exportable Analysis Reports.
Verifies JSON report structure, PDF report generation, legal disclaimer inclusion,
multi-document reporting, missing section safety, and API endpoints.
"""
import pytest
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata, RiskSignal, Severity
from app.models.financial import FinancialItem
from app.storage.database import save_document, save_clause, save_risk_signal, save_financial_items
from app.analysis.reporting import generate_json_report, generate_pdf_report, LEGAL_DISCLAIMER


def populate_report_doc(doc_id: str, filename: str) -> DocumentOverview:
    doc = DocumentOverview(
        document_id=doc_id,
        filename=filename,
        document_type="Employment",
        page_count=2,
        clause_count=2
    )
    save_document(doc)

    c1 = Clause(
        id=f"{doc_id}-c1",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c1", document_id=doc_id, section_path="Section 1. Salary", page=1),
        text="Base salary is ₹9,00,000 per annum."
    )
    c2 = Clause(
        id=f"{doc_id}-c2",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c2", document_id=doc_id, section_path="Section 2. Notice", page=2),
        text="Notice period shall be 30 days."
    )
    save_clause(c1)
    save_clause(c2)

    sig = RiskSignal(
        id=f"{doc_id}-s1",
        clause_id=f"{doc_id}-c2",
        document_id=doc_id,
        category="notice",
        severity=Severity.HIGH,
        evidence_text="30 days notice",
        section_path="Section 2. Notice",
        page=2,
        plain_explanation="30 days notice period required."
    )
    save_risk_signal(sig)

    fin = FinancialItem(
        item_id=f"{doc_id}-f1",
        document_id=doc_id,
        item_type="ANNUAL_SALARY",
        amount="₹9,00,000",
        currency="INR",
        frequency="annual",
        clause_id=f"{doc_id}-c1",
        section_path="Section 1. Salary",
        page=1,
        evidence_text="Base salary is ₹9,00,000"
    )
    save_financial_items(doc_id, [fin])

    return doc


def test_generate_json_report_structure():
    doc_id = "doc-rep-json-1"
    populate_report_doc(doc_id, "Offer_Letter_Report.pdf")

    report = generate_json_report([doc_id], language="en")

    assert report["report_title"] == "LexiGuard Document Intelligence Report"
    assert report["disclaimer"] == LEGAL_DISCLAIMER
    assert len(report["documents"]) == 1
    doc_sec = report["documents"][0]
    assert doc_sec["filename"] == "Offer_Letter_Report.pdf"
    assert len(doc_sec["attention_signals"]) == 1
    assert len(doc_sec["financial_items"]) == 1


def test_generate_pdf_report_bytes():
    doc_id = "doc-rep-pdf-1"
    populate_report_doc(doc_id, "Agreement_Report.pdf")

    pdf_bytes = generate_pdf_report([doc_id], language="en")

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_reports_api_json_endpoint(client):
    doc_id = "doc-rep-api-1"
    populate_report_doc(doc_id, "API_Report.pdf")

    res = client.post("/api/reports/generate", json={"doc_ids": [doc_id], "format": "json"})
    assert res.status_code == 200
    data = res.json()
    assert data["report_title"] == "LexiGuard Document Intelligence Report"
    assert "disclaimer" in data


def test_reports_api_pdf_endpoint(client):
    doc_id = "doc-rep-api-2"
    populate_report_doc(doc_id, "API_PDF_Report.pdf")

    res = client.post("/api/reports/generate", json={"doc_ids": [doc_id], "format": "pdf"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")


def test_reports_api_missing_doc_ids_returns_400(client):
    res = client.post("/api/reports/generate", json={"doc_ids": [], "format": "json"})
    assert res.status_code == 400


def test_reports_api_nonexistent_doc_returns_404(client):
    res = client.post("/api/reports/generate", json={"doc_ids": ["nonexistent-id-888"], "format": "json"})
    assert res.status_code == 404


def test_multi_document_report_with_consistency():
    d1 = "doc-rep-multi-1"
    d2 = "doc-rep-multi-2"
    populate_report_doc(d1, "Doc1.pdf")
    populate_report_doc(d2, "Doc2.pdf")

    report = generate_json_report([d1, d2], language="en")

    assert len(report["documents"]) == 2
    assert "consistency_findings" in report
    pdf = generate_pdf_report([d1, d2], language="en")
    assert pdf.startswith(b"%PDF")
