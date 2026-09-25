"""
Report Generation API endpoints for LexiGuard Phase 3 Checkpoint 4.
Generates exportable JSON and downloadable PDF document intelligence reports.
"""
from fastapi import APIRouter, HTTPException, Response
from typing import Dict, Any
from app.analysis.reporting import ReportRequest, generate_json_report, generate_pdf_report
from app.storage.database import get_document
import logging

router = APIRouter(prefix="/api/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


@router.post("/generate")
def generate_report_endpoint(request: ReportRequest):
    """
    Generate an evidence-grounded document intelligence report.
    Supports 'json' (structured dict) and 'pdf' (downloadable PDF document).
    """
    if not request.doc_ids:
        raise HTTPException(status_code=400, detail="At least one document_id must be provided.")

    valid_docs = [doc_id for doc_id in request.doc_ids if get_document(doc_id)]
    if not valid_docs:
        raise HTTPException(status_code=404, detail="None of the specified document IDs were found.")

    fmt = request.format.lower()
    lang = request.language.lower() if request.language else "en"

    if fmt == "pdf":
        try:
            pdf_bytes = generate_pdf_report(valid_docs, language=lang)
            filename = f"LexiGuard_Report_{valid_docs[0][:8]}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            logger.error("Error generating PDF report: %s", e)
            raise HTTPException(status_code=500, detail="Failed to generate PDF report.")
    else:
        return generate_json_report(valid_docs, language=lang)
