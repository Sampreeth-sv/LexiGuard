"""
Checklist generation API endpoint for LexiGuard.
Generates legal review checklists, lawyer questions, and obligation summaries.
Requires 1 LLM call — only triggered by explicit user request.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.storage.database import get_document, get_risk_signals, get_clauses
from app.llm.provider import get_llm_provider
from app.models.schemas import Checklist, RiskSignal, Clause
from app.analysis.entities import extract_obligations
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _deserialize_signals(signals_data: List[Dict[str, Any]]) -> List[RiskSignal]:
    result = []
    for s in signals_data:
        try:
            result.append(RiskSignal(**s))
        except Exception as e:
            logger.debug("Skipping malformed signal: %s", e)
    return result


def _deserialize_clauses(clauses_data: List[Dict[str, Any]]) -> List[Clause]:
    result = []
    for c in clauses_data:
        try:
            result.append(Clause(**c))
        except Exception as e:
            logger.debug("Skipping malformed clause: %s", e)
    return result


@router.get("/documents/{doc_id}/checklist", response_model=Checklist)
def get_document_checklist(doc_id: str) -> Checklist:
    """
    Generate a legal review checklist for the document.
    Uses detected risk signals and obligations as context for the LLM.
    Requires 1 LLM call — only triggered by user request.
    Falls back to deterministic checklist when LLM is unavailable.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    signals_data = get_risk_signals(doc_id)
    signals = _deserialize_signals(signals_data)

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    # Extract obligations and dates from clause text
    all_obligations: list = []
    all_dates: list = []

    for clause in clauses:
        all_obligations.extend(extract_obligations(clause.text))
        if clause.metadata.dates:
            all_dates.extend(clause.metadata.dates)

    # Deduplicate
    all_obligations = list(dict.fromkeys(all_obligations))[:20]
    all_dates = list(dict.fromkeys(all_dates))[:15]

    provider = get_llm_provider()
    checklist = provider.generate_checklist(signals, all_obligations, all_dates, clauses=clauses)

    logger.info(
        "Generated checklist for %s: %d items, %d signals used",
        doc_id, len(checklist.items), len(signals)
    )
    return checklist
