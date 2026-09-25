"""
Document comparison API endpoints for LexiGuard.
Deterministic diff uses TF-IDF + difflib (zero LLM calls).
LLM is only invoked when user explicitly requests a diff explanation.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.storage.database import get_clauses, get_document
from app.comparison.comparator import compare_documents
from app.llm.provider import get_llm_provider
from app.models.schemas import ComparisonResult, Clause, ClauseMetadata
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str


class ExplainDiffRequest(BaseModel):
    before_text: str
    after_text: str
    section_path: str


def _deserialize_clauses(clauses_data: List[Dict[str, Any]]) -> List[Clause]:
    result = []
    for c in clauses_data:
        try:
            meta = ClauseMetadata(**c['metadata']) if isinstance(c.get('metadata'), dict) else c['metadata']
            result.append(Clause(id=c['id'], metadata=meta, text=c['text']))
        except Exception as e:
            logger.debug("Skipping malformed clause: %s", e)
    return result


@router.post("/compare", response_model=ComparisonResult)
def compare_docs_endpoint(request: CompareRequest) -> ComparisonResult:
    """
    Deterministically compare two documents and identify added, removed, and modified clauses.
    Uses TF-IDF cosine similarity + difflib. Zero LLM calls.
    """
    doc_a = get_document(request.document_id_a)
    doc_b = get_document(request.document_id_b)

    if not doc_a:
        raise HTTPException(status_code=404, detail=f"Document A not found: {request.document_id_a}")
    if not doc_b:
        raise HTTPException(status_code=404, detail=f"Document B not found: {request.document_id_b}")

    clauses_a = _deserialize_clauses(get_clauses(request.document_id_a))
    clauses_b = _deserialize_clauses(get_clauses(request.document_id_b))

    if not clauses_a:
        raise HTTPException(status_code=400, detail="Document A has no parseable clauses.")
    if not clauses_b:
        raise HTTPException(status_code=400, detail="Document B has no parseable clauses.")

    result = compare_documents(
        clauses_a=clauses_a,
        clauses_b=clauses_b,
        document_id_a=request.document_id_a,
        document_id_b=request.document_id_b,
    )
    return result


@router.post("/compare/explain-diff")
def explain_difference(request: ExplainDiffRequest) -> Dict[str, str]:
    """
    Generate a plain-language explanation of what changed between two clause versions.
    Requires 1 LLM call — only triggered by explicit user request.
    """
    provider = get_llm_provider()
    explanation = provider.explain_difference(
        request.before_text,
        request.after_text,
        request.section_path,
    )
    return {"explanation": explanation}


from app.analysis.consistency_engine import ConsistencyEngine, ConsistencyReport

@router.post("/comparison/consistency", response_model=ConsistencyReport)
def compare_consistency_endpoint(request: CompareRequest) -> ConsistencyReport:
    """
    Deterministically compare two related documents (e.g. Offer Letter vs Employment Agreement)
    for consistency across 17 categories. Zero LLM calls.
    """
    if request.document_id_a == request.document_id_b:
        raise HTTPException(status_code=400, detail="Cannot compare a document against itself for consistency.")

    doc_a = get_document(request.document_id_a)
    doc_b = get_document(request.document_id_b)

    if not doc_a:
        raise HTTPException(status_code=404, detail=f"Document A not found: {request.document_id_a}")
    if not doc_b:
        raise HTTPException(status_code=404, detail=f"Document B not found: {request.document_id_b}")

    clauses_a = _deserialize_clauses(get_clauses(request.document_id_a))
    clauses_b = _deserialize_clauses(get_clauses(request.document_id_b))

    engine = ConsistencyEngine()
    return engine.compare_documents(
        doc_id_a=request.document_id_a,
        filename_a=doc_a.get("filename", "Document A"),
        clauses_a=clauses_a,
        doc_id_b=request.document_id_b,
        filename_b=doc_b.get("filename", "Document B"),
        clauses_b=clauses_b,
    )

