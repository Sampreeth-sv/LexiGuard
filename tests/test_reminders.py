"""
Unit and API integration tests for LexiGuard Phase 3 Checkpoint 5: Document Reminders & ICS Export.
Verifies date and temporal obligation extraction, RFC 5545 iCalendar (.ics) generation,
provenance preservation, zero date invention, document isolation, and API endpoints.
"""
import pytest
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata
from app.storage.database import save_document, save_clause
from app.analysis.reminders import extract_document_reminders, generate_ics_calendar, _parse_to_iso_date


def populate_reminder_doc(doc_id: str, filename: str) -> DocumentOverview:
    doc = DocumentOverview(
        document_id=doc_id,
        filename=filename,
        document_type="Employment",
        page_count=3,
        clause_count=3
    )
    save_document(doc)

    c1 = Clause(
        id=f"{doc_id}-c1",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c1", document_id=doc_id, section_path="1. Notice", page=1),
        text="Either party may terminate by providing written notice 30 days prior to October 1, 2026."
    )
    c2 = Clause(
        id=f"{doc_id}-c2",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c2", document_id=doc_id, section_path="2. Probation", page=2),
        text="The employee shall remain on probation until March 31, 2027."
    )
    c3 = Clause(
        id=f"{doc_id}-c3",
        metadata=ClauseMetadata(clause_id=f"{doc_id}-c3", document_id=doc_id, section_path="3. Renewal", page=3),
        text="This agreement shall automatically renew unless terminated prior to 15 December 2026."
    )
    save_clause(c1)
    save_clause(c2)
    save_clause(c3)

    return doc


def test_extract_document_reminders_only_explicit_dates():
    doc_id = "doc-rem-1"
    populate_reminder_doc(doc_id, "Contract_Dates.pdf")

    clauses = [
        Clause(id="c1", metadata=ClauseMetadata(clause_id="c1", document_id=doc_id, section_path="1. Notice", page=1), text="Written notice required 30 days prior to October 1, 2026."),
        Clause(id="c2", metadata=ClauseMetadata(clause_id="c2", document_id=doc_id, section_path="2. Probation", page=2), text="Probation period ends on March 31, 2027.")
    ]

    rems = extract_document_reminders(doc_id, clauses, "Contract_Dates.pdf")

    assert len(rems) >= 2
    dates_found = [r.date_str for r in rems]
    assert "October 1, 2026" in dates_found
    assert "March 31, 2027" in dates_found

    # Check provenance
    r1 = next(r for r in rems if "October 1, 2026" in r.date_str)
    assert r1.clause_id == "c1"
    assert r1.section_path == "1. Notice"
    assert r1.page == 1
    assert "October 1, 2026" in r1.evidence_text


def test_zero_date_invention_when_no_dates():
    doc_id = "doc-no-dates"
    clauses = [
        Clause(id="c1", metadata=ClauseMetadata(clause_id="c1", document_id=doc_id, section_path="General", page=1), text="The employee shall maintain strict confidentiality of company materials.")
    ]

    rems = extract_document_reminders(doc_id, clauses, "No_Dates.pdf")
    assert len(rems) == 0


def test_generate_ics_calendar_rfc_5545():
    doc_id = "doc-ics-1"
    clauses = [
        Clause(id="c1", metadata=ClauseMetadata(clause_id="c1", document_id=doc_id, section_path="Notice", page=1), text="Termination notice by October 1, 2026.")
    ]
    rems = extract_document_reminders(doc_id, clauses, "Sample_Agreement.pdf")

    ics_str = generate_ics_calendar(rems, "Sample_Agreement.pdf")

    assert "BEGIN:VCALENDAR" in ics_str
    assert "END:VCALENDAR" in ics_str
    assert "BEGIN:VEVENT" in ics_str
    assert "END:VEVENT" in ics_str
    assert "UID:" in ics_str
    assert "SUMMARY:" in ics_str
    assert "DESCRIPTION:" in ics_str
    assert "Sample_Agreement.pdf" in ics_str


def test_parse_to_iso_date():
    assert _parse_to_iso_date("October 1, 2026") == "20261001"
    assert _parse_to_iso_date("15 December 2026") == "20261215"
    assert _parse_to_iso_date("2026-10-01") == "20261001"


def test_reminders_api_get_endpoint(client):
    doc_id = "doc-rem-api-1"
    populate_reminder_doc(doc_id, "Offer_Reminders.pdf")

    res = client.get(f"/api/documents/{doc_id}/reminders")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    assert data[0]["clause_id"] is not None


def test_reminders_api_ics_endpoint(client):
    doc_id = "doc-rem-api-2"
    populate_reminder_doc(doc_id, "Offer_Reminders_ICS.pdf")

    res = client.get(f"/api/documents/{doc_id}/reminders/ics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in res.text
    assert "BEGIN:VEVENT" in res.text


def test_reminders_api_nonexistent_doc_returns_404(client):
    res = client.get("/api/documents/nonexistent-rem-999/reminders")
    assert res.status_code == 404
    res_ics = client.get("/api/documents/nonexistent-rem-999/reminders/ics")
    assert res_ics.status_code == 404
