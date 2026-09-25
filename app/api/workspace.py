"""
Workspace API endpoints for LexiGuard Phase 3.
Provides multi-document listing, selection metadata, and cascading document deletion.
"""
from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any
from app.storage.database import list_workspace_documents, get_document, delete_document

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("", response_model=List[Dict[str, Any]])
def get_workspace():
    """Retrieve all uploaded documents in the workspace with complete analysis metrics."""
    return list_workspace_documents()


@router.get("/{doc_id}", response_model=Dict[str, Any])
def get_workspace_document(doc_id: str = Path(..., description="Document ID")):
    """Get metadata and analysis metrics for a specific document in the workspace."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    docs = list_workspace_documents()
    for d in docs:
        if d["document_id"] == doc_id:
            return d
    return doc


@router.delete("/{doc_id}")
def delete_workspace_document(doc_id: str = Path(..., description="Document ID")):
    """Cascading deletion of a document and all related clauses, signals, relationships, and financial items."""
    deleted = delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": f"Document {doc_id} and associated records successfully deleted", "document_id": doc_id}


from app.analysis.multilingual import get_all_translations, SUPPORTED_LANGUAGES

@router.get("/translations/{lang}")
def get_ui_translations(lang: str = Path(..., description="Language code (en, hi, kn, te)")):
    """Retrieve localized static UI string dictionary for specified language."""
    if lang.lower() not in SUPPORTED_LANGUAGES:
        return {"language": "en", "translations": get_all_translations("en"), "fallback_notice": f"Language '{lang}' not supported. Defaulting to English."}
    return {"language": lang.lower(), "translations": get_all_translations(lang)}
