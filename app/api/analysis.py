"""
Analysis API endpoints for LexiGuard.
Provides risk signals, entity extraction, and AI summary generation.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.storage.database import get_document, get_risk_signals, get_clauses
from app.models.schemas import RiskSignal, SummaryResponse, Clause, ClauseMetadata
from app.analysis.entities import (
    extract_dates, extract_monetary_values, extract_parties, extract_obligations,
    detect_document_type, classify_date_context
)
from app.llm.provider import get_llm_provider

import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _deserialize_clauses(clauses_data: List[Dict[str, Any]]) -> List[Clause]:
    """Safely deserialize clause dicts from DB into Clause objects."""
    result = []
    for c in clauses_data:
        try:
            meta = ClauseMetadata(**c['metadata']) if isinstance(c.get('metadata'), dict) else c['metadata']
            result.append(Clause(id=c['id'], metadata=meta, text=c['text']))
        except Exception as e:
            logger.debug("Skipping malformed clause: %s", e)
    return result


def _deserialize_signals(signals_data: List[Dict[str, Any]]) -> List[RiskSignal]:
    """Safely deserialize signal dicts from DB into RiskSignal objects."""
    result = []
    for s in signals_data:
        try:
            result.append(RiskSignal(**s))
        except Exception as e:
            logger.debug("Skipping malformed signal: %s", e)
    return result


@router.get("/{doc_id}/signals", response_model=List[RiskSignal])
def get_document_signals(doc_id: str) -> List[RiskSignal]:
    """
    Return all detected risk signals for a document.
    Purely deterministic — no LLM calls.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")
    signals_data = get_risk_signals(doc_id)
    return _deserialize_signals(signals_data)


@router.get("/{doc_id}/entities", response_model=Dict[str, Any])
def get_document_entities(doc_id: str) -> Dict[str, Any]:
    """
    Return extracted entities: dates, monetary values, parties, obligations, document_type, temporal_obligations.
    Purely deterministic — no LLM calls.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    all_dates: set = set()
    all_monetary: set = set()
    all_obligations: list = []
    temporal_obs: list = []
    seen_dates: set = set()

    for clause in clauses:
        d_list = extract_dates(clause.text)
        all_dates.update(d_list)
        for d in d_list:
            key = (d.lower(), clause.id)
            if key not in seen_dates:
                seen_dates.add(key)
                temporal_obs.append({
                    "date": d,
                    "context_type": classify_date_context(d, clause.text),
                    "description": clause.text[:150].strip() + ("..." if len(clause.text) > 150 else ""),
                    "clause_id": clause.id,
                    "section_path": clause.metadata.section_path,
                    "page": clause.metadata.page,
                })

        all_monetary.update(extract_monetary_values(clause.text))
        all_obligations.extend(extract_obligations(clause.text))

    parties = extract_parties(clauses[:5])
    doc_type = detect_document_type(clauses)

    return {
        "document_type": doc_type,
        "dates": sorted(list(all_dates))[:30],
        "monetary_values": sorted(list(all_monetary))[:30],
        "parties": parties[:10],
        "obligations": list(dict.fromkeys(all_obligations))[:30],  # deduplicated, ordered
        "temporal_obligations": temporal_obs[:30],
    }


@router.get("/{doc_id}/dashboard", response_model=Dict[str, Any])
def get_document_dashboard(doc_id: str) -> Dict[str, Any]:
    """
    Return complete Document Understanding Dashboard data.
    Purely deterministic — zero LLM calls.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    signals_data = get_risk_signals(doc_id)
    signals = _deserialize_signals(signals_data)

    doc_type = detect_document_type(clauses)

    temporal_obs = []
    seen_dates = set()
    financial_refs = []
    seen_monetary = set()

    for c in clauses:
        d_list = extract_dates(c.text)
        for d in d_list:
            ctx_type = classify_date_context(d, c.text)
            key = (d.lower(), c.id)
            if key not in seen_dates:
                seen_dates.add(key)
                temporal_obs.append({
                    "date": d,
                    "context_type": ctx_type,
                    "description": c.text[:150].strip() + ("..." if len(c.text) > 150 else ""),
                    "clause_id": c.id,
                    "section_path": c.metadata.section_path,
                    "page": c.metadata.page,
                })

        m_list = extract_monetary_values(c.text)
        for m in m_list:
            m_key = (m.lower(), c.id)
            if m_key not in seen_monetary:
                seen_monetary.add(m_key)
                financial_refs.append({
                    "value": m,
                    "context": c.text[:150].strip() + ("..." if len(c.text) > 150 else ""),
                    "clause_id": c.id,
                    "section_path": c.metadata.section_path,
                    "page": c.metadata.page,
                })

    parties = extract_parties(clauses[:5])
    unique_dates = list({t['date'] for t in temporal_obs})
    unique_monetary = list({f['value'] for f in financial_refs})
    entity_count = len(parties) + len(unique_dates) + len(unique_monetary)

    return {
        "document_id": doc_id,
        "filename": doc_data.get("filename", "document"),
        "document_type": doc_type,
        "clause_count": len(clauses),
        "signal_count": len(signals),
        "entity_count": entity_count,
        "important_date_count": len(unique_dates),
        "monetary_reference_count": len(unique_monetary),
        "attention_areas": [s.model_dump() for s in signals],
        "important_dates": temporal_obs[:30],
        "financial_references": financial_refs[:30],
        "important_entities": parties[:10],
    }


@router.post("/{doc_id}/summary", response_model=SummaryResponse)
def create_document_summary(doc_id: str) -> SummaryResponse:
    """
    Generate a plain-language AI summary of the document.
    Retrieves top clauses by importance and sends evidence pack to LLM.
    Requires 1 LLM call — only triggered by user request.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    if not clauses:
        raise HTTPException(status_code=404, detail="No clauses found for this document.")

    signals_data = get_risk_signals(doc_id)
    signal_clause_ids = {s['clause_id'] for s in signals_data}

    # Score clauses: prefer those with signals, then by length (up to reasonable max)
    def score_clause(c: Clause) -> float:
        signal_boost = 50.0 if c.id in signal_clause_ids else 0.0
        length_score = min(len(c.text), 1000) / 1000.0
        return signal_boost + length_score

    top_clauses = sorted(clauses, key=score_clause, reverse=True)[:20]

    provider = get_llm_provider()
    filename = doc_data.get('filename', 'document')

    summary_text = provider.generate_summary(top_clauses, filename)
    genai_used = provider.is_available

    return SummaryResponse(
        document_id=doc_id,
        summary=summary_text,
        genai_used=genai_used,
    )


from app.models.schemas import ClauseRelationship, ClauseRelationshipStatus, ClauseRelationshipType
from app.analysis.relationships import RelationshipEngine
from typing import Optional


@router.get("/{doc_id}/relationships", response_model=List[ClauseRelationship])
def get_document_relationships(
    doc_id: str,
    relationship_type: Optional[str] = None
) -> List[ClauseRelationship]:
    """
    Return detected clause relationships, missing counterparts, and structural asymmetries.
    Purely deterministic — zero LLM calls.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    engine = RelationshipEngine()
    relationships = engine.analyze_document_relationships(clauses, doc_id)

    if relationship_type and relationship_type.strip():
        target_type = relationship_type.strip().upper()
        relationships = [r for r in relationships if r.relationship_type.value == target_type]

    return relationships


from app.storage.database import get_relationship_by_id


@router.post("/{doc_id}/relationships/{relationship_id}/explain")
def explain_relationship_with_ai(doc_id: str, relationship_id: str):
    """
    Explain a specific clause relationship using AI.
    Triggered ONLY on explicit user request.
    Uses strict evidence pack context.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    engine = RelationshipEngine()
    relationships = engine.analyze_document_relationships(clauses, doc_id)

    rel = next((r for r in relationships if r.relationship_id == relationship_id), None)
    if not rel:
        db_rel = get_relationship_by_id(relationship_id)
        if db_rel:
            raise HTTPException(
                status_code=400,
                detail=f"Relationship '{relationship_id}' does not belong to document '{doc_id}'."
            )
        raise HTTPException(status_code=404, detail="Relationship not found.")

    provider = get_llm_provider()

    source_c = next((c for c in clauses if c.id == rel.source_clause_id), None)
    related_c = next((c for c in clauses if c.id == rel.related_clause_id), None) if rel.related_clause_id else None

    source_text = source_c.text if source_c else rel.source_excerpt
    related_text = related_c.text if related_c else (rel.related_excerpt or "No counterpart clause identified.")

    explanation = provider.explain_difference(source_text, related_text, rel.source_section_path)
    return {"explanation": explanation}


from app.models.financial import FinancialItem
from app.analysis.financial_engine import analyze_document_financials
from app.storage.database import save_financial_items, get_financial_item_by_id


@router.get("/{doc_id}/financial", response_model=List[FinancialItem])
def get_document_financials(doc_id: str) -> List[FinancialItem]:
    """
    Return detected financial and compensation items for a document.
    Purely deterministic — zero LLM calls.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    items = analyze_document_financials(doc_id, clauses)
    try:
        save_financial_items(doc_id, items)
    except Exception as e:
        logger.warning("Failed to save financial items to DB: %s", e)

    return items


@router.post("/{doc_id}/financial/explain")
def explain_financial_with_ai(doc_id: str, item_id: Optional[str] = None):
    """
    Explain compensation structure or specific financial item using AI.
    Triggered ONLY on explicit user request.
    """
    doc_data = get_document(doc_id)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found.")

    clauses_data = get_clauses(doc_id)
    clauses = _deserialize_clauses(clauses_data)

    items = analyze_document_financials(doc_id, clauses)

    if item_id:
        target_item = next((it for it in items if it.item_id == item_id), None)
        if not target_item:
            stored_item = get_financial_item_by_id(item_id)
            if stored_item and stored_item.get('document_id') != doc_id:
                raise HTTPException(status_code=400, detail=f"Financial item '{item_id}' does not belong to document '{doc_id}'.")
            raise HTTPException(status_code=404, detail="Financial item not found.")
        evidence = target_item.evidence_text
        section = target_item.section_path or "Compensation Section"
        prompt_text = f"Explain the compensation provision for {target_item.item_type}: {target_item.amount or 'unspecified amount'} ({target_item.frequency or 'unspecified frequency'})."
    else:
        evidence = "\n".join([f"[{it.item_type}] {it.amount or 'Amount unspecified'} ({it.frequency or 'Frequency unspecified'}) - Section {it.section_path}" for it in items])
        section = "Financial & Compensation Overview"
        prompt_text = "Explain the overall compensation and financial structure of this document."

    provider = get_llm_provider()
    explanation = provider.explain_difference(prompt_text, evidence, section)
    return {"explanation": explanation}


