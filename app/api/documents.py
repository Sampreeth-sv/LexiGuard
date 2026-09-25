"""
Document upload and management API endpoints for LexiGuard.
Handles file validation, parsing, clause segmentation, risk analysis,
TF-IDF index building, and SQLite storage.
Zero LLM calls in this module.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata
from app.models.evidence import EvidenceLocationResponse
from app.config import settings
from app.storage.database import (
    save_document, save_clause, save_risk_signal,
    get_document, get_clauses, get_clause_by_id, delete_document, list_documents
)
from app.ingestion.pdf_parser import extract_text_from_pdf
from app.ingestion.docx_parser import extract_text_from_docx
from app.ingestion.text_parser import extract_text_from_txt
from app.ingestion.structure import segment_document
from app.analysis.risk_engine import RiskEngine
from app.analysis.entities import extract_dates, extract_monetary_values, extract_parties
from app.retrieval.tfidf import TFIDFIndex
import uuid
import os
import re
import logging
from datetime import datetime
from typing import List, Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory TF-IDF index store: {document_id: TFIDFIndex}
# Shared with questions.py and other routers
tfidf_store: dict = {}

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}


def sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filename, limit length."""
    name = os.path.basename(filename)
    name = re.sub(r'[^a-zA-Z0-9._\-]', '_', name)
    return name[:100] if name else 'document'


def validate_extension(filename: str) -> str:
    """Validate file extension. Returns extension string or raises HTTPException."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Please upload a PDF, DOCX, or TXT document. Received: .{ext}"
        )
    return ext


def detect_file_type_by_magic(content: bytes, extension: str) -> str:
    """
    Validate file type using magic bytes, not just extension.
    Prevents MIME type spoofing attacks.
    """
    if content[:4] == b'%PDF':
        return 'pdf'
    elif content[:2] == b'PK':
        # ZIP-based formats (DOCX, XLSX, etc.)
        if extension == 'docx':
            return 'docx'
        raise HTTPException(
            status_code=400,
            detail="File content does not match the expected DOCX format."
        )
    elif extension == 'txt':
        # TXT has no magic bytes; trust extension after other checks pass
        return 'txt'
    else:
        raise HTTPException(
            status_code=400,
            detail="File content does not match the declared file type."
        )


@router.post("/", response_model=DocumentOverview)
async def upload_document(file: UploadFile = File(...)) -> DocumentOverview:
    """
    Upload and process a legal document (PDF, DOCX, or TXT).
    Performs: validation → parsing → segmentation → entity extraction →
    risk analysis → TF-IDF indexing → SQLite storage.
    Zero LLM calls.
    """
    content = await file.read()

    # File size validation
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"The document exceeds the {settings.max_upload_size_mb}MB supported size limit."
        )

    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    filename = file.filename or 'document.txt'
    ext = validate_extension(filename)
    file_type = detect_file_type_by_magic(content, ext)
    safe_filename = sanitize_filename(filename)
    doc_id = str(uuid.uuid4())

    logger.info("Processing upload: %s (%s bytes)", safe_filename, len(content))

    # Parse document into (page_num, text) tuples
    try:
        if file_type == 'pdf':
            pages = extract_text_from_pdf(content)
        elif file_type == 'docx':
            pages = extract_text_from_docx(content)
        else:
            pages = extract_text_from_txt(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Parsing error for %s: %s", safe_filename, type(e).__name__)
        raise HTTPException(status_code=400, detail="Could not parse the uploaded document.")

    if not pages:
        raise HTTPException(status_code=400, detail="The document appears to be empty or unreadable.")

    page_count = max(page_num for page_num, _ in pages) if pages else 1

    # Segment document into structured clauses
    clauses = segment_document(pages, doc_id)

    # Extract document-level entities from all text
    all_text = ' '.join(text for _, text in pages)
    doc_dates = extract_dates(all_text)
    doc_monetary = extract_monetary_values(all_text)
    doc_parties = extract_parties(clauses[:5])  # Parties usually in first few clauses

    # Create initial DocumentOverview
    doc = DocumentOverview(
        document_id=doc_id,
        filename=safe_filename,
        page_count=page_count,
        clause_count=len(clauses),
        signal_count=0,
        dates=doc_dates[:20],
        monetary_values=doc_monetary[:20],
        parties=doc_parties[:10],
        genai_available=settings.genai_available,
        created_at=datetime.utcnow(),
        processing_status='processing',
    )
    save_document(doc)

    # Save clauses and run risk analysis
    engine = RiskEngine()
    total_signals = 0

    for clause in clauses:
        save_clause(clause)
        signals = engine.analyze_clause(clause)
        for sig in signals:
            save_risk_signal(sig)
            total_signals += 1

    # Update signal count and mark complete
    doc.signal_count = total_signals
    doc.processing_status = 'complete'
    save_document(doc)

    # Build in-memory TF-IDF index for this document
    index = TFIDFIndex()
    index.build(clauses)
    tfidf_store[doc_id] = index

    # Save original file bytes to upload_temp_dir for evidence viewer / file serving
    try:
        os.makedirs(settings.upload_temp_dir, exist_ok=True)
        saved_path = os.path.join(settings.upload_temp_dir, f"{doc_id}.{file_type}")
        with open(saved_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.warning("Could not persist uploaded file for %s: %s", doc_id, e)

    logger.info(
        "Document processed: %s | %d clauses | %d signals",
        safe_filename, len(clauses), total_signals
    )
    return doc


@router.get("/", response_model=List[DocumentOverview])
def list_all_documents() -> List[DocumentOverview]:
    """Return a list of all uploaded documents."""
    docs_data = list_documents()
    result = []
    for d in docs_data:
        try:
            result.append(DocumentOverview(**d))
        except Exception:
            continue
    return result


@router.get("/{doc_id}", response_model=DocumentOverview)
def get_document_details(doc_id: str) -> DocumentOverview:
    """Get details for a specific document by ID."""
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentOverview(**doc_data)


@router.get("/{doc_id}/clauses", response_model=List[Clause])
def get_document_clauses(doc_id: str) -> List[Clause]:
    """Get all parsed clauses for a specific document."""
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")
    clauses_data = get_clauses(doc_id)
    result = []
    for c in clauses_data:
        try:
            meta = ClauseMetadata(**c['metadata']) if isinstance(c.get('metadata'), dict) else c['metadata']
            result.append(Clause(id=c['id'], metadata=meta, text=c['text']))
        except Exception as e:
            logger.debug("Skipping malformed clause: %s", e)
    return result


@router.get("/{doc_id}/file")
def get_document_file(doc_id: str):
    """
    Serve the original uploaded document file (PDF, DOCX, TXT) for inline browser viewing.
    Returns 404 if document or file does not exist.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    for ext in ['pdf', 'docx', 'txt']:
        file_path = os.path.join(settings.upload_temp_dir, f"{doc_id}.{ext}")
        if os.path.exists(file_path):
            media_types = {
                'pdf': 'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'txt': 'text/plain; charset=utf-8'
            }
            return FileResponse(
                path=file_path,
                media_type=media_types.get(ext, 'application/octet-stream'),
                filename=doc_data.get('filename', f"document.{ext}"),
                headers={"Content-Disposition": "inline"}
            )

    raise HTTPException(status_code=404, detail="Original document file not found on server.")


@router.get("/{doc_id}/evidence/{clause_id}", response_model=EvidenceLocationResponse)
def get_evidence_location(
    doc_id: str,
    clause_id: str,
    evidence_quote: Optional[str] = None
) -> EvidenceLocationResponse:
    """
    Get evidence location and provenance details for a document clause.
    Validates document existence, clause existence, and document-clause ownership.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clause_data = get_clause_by_id(clause_id)
    if not clause_data:
        raise HTTPException(status_code=404, detail="Clause not found.")

    meta = clause_data.get('metadata', {})
    if isinstance(meta, str):
        import json
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    # Security: validate clause belongs to requested document
    clause_doc_id = meta.get('document_id') if isinstance(meta, dict) else None
    if clause_doc_id != doc_id:
        raise HTTPException(
            status_code=400,
            detail="Clause does not belong to the specified document."
        )

    filename = doc_data.get('filename', '')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'pdf'
    if ext not in {'pdf', 'docx', 'txt'}:
        ext = 'pdf'

    page_num = meta.get('page', 1) if isinstance(meta, dict) else 1
    sec_path = (meta.get('section_path') or meta.get('heading') or 'General') if isinstance(meta, dict) else 'General'
    clause_text = clause_data.get('text', '')

    char_start = None
    char_end = None
    match_status = "page_level_available"

    if evidence_quote and evidence_quote.strip():
        quote_strip = evidence_quote.strip()
        idx = clause_text.find(quote_strip)
        if idx != -1:
            char_start = idx
            char_end = idx + len(quote_strip)
            match_status = "exact_highlight_available"
        else:
            # Case-insensitive fallback match check
            idx_lower = clause_text.lower().find(quote_strip.lower())
            if idx_lower != -1:
                char_start = idx_lower
                char_end = idx_lower + len(quote_strip)
                match_status = "exact_highlight_available"

    if page_num < 1:
        match_status = "location_unavailable"

    return EvidenceLocationResponse(
        document_id=doc_id,
        clause_id=clause_id,
        page_number=page_num,
        section_path=sec_path,
        evidence_quote=evidence_quote,
        clause_text=clause_text,
        file_type=ext,
        match_status=match_status,
        char_start=char_start,
        char_end=char_end,
    )


@router.delete("/{doc_id}", status_code=204)
def remove_document(doc_id: str) -> None:
    """Delete a document and all associated data."""
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")
    delete_document(doc_id)
    if doc_id in tfidf_store:
        del tfidf_store[doc_id]

    # Delete persisted original file if present
    for ext in ['pdf', 'docx', 'txt']:
        file_p = os.path.join(settings.upload_temp_dir, f"{doc_id}.{ext}")
        if os.path.exists(file_p):
            try:
                os.remove(file_p)
            except Exception as e:
                logger.warning("Failed to remove file %s: %s", file_p, e)

    logger.info("Deleted document: %s", doc_id)
