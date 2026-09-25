"""
Reminders & iCalendar (.ics) API endpoints for LexiGuard Phase 3 Checkpoint 5.
"""
from fastapi import APIRouter, HTTPException, Path, Response
from typing import List, Dict, Any
from app.storage.database import get_document, get_clauses
from app.api.questions import _deserialize_clauses
from app.analysis.reminders import extract_document_reminders, generate_ics_calendar, ReminderItem
import logging

router = APIRouter(prefix="/api/documents", tags=["Reminders"])
logger = logging.getLogger(__name__)


@router.get("/{doc_id}/reminders", response_model=List[ReminderItem])
def get_reminders_endpoint(doc_id: str = Path(..., description="Document ID")) -> List[ReminderItem]:
    """Retrieve all explicit date and deadline reminders extracted from the document."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)
    filename = doc.get("filename", "document")
    return extract_document_reminders(doc_id, clauses, filename)


@router.get("/{doc_id}/reminders/ics")
def export_reminders_ics_endpoint(doc_id: str = Path(..., description="Document ID")):
    """Export document date/deadline reminders as an RFC 5545 compliant .ics calendar file."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)
    filename = doc.get("filename", "document")
    reminders = extract_document_reminders(doc_id, clauses, filename)

    ics_content = generate_ics_calendar(reminders, filename)
    ics_filename = f"LexiGuard_Reminders_{doc_id[:8]}.ics"
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{ics_filename}"'}
    )
