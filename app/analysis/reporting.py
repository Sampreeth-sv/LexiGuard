"""
Exportable Analysis Reports Engine for LexiGuard Phase 3 Checkpoint 4.
Generates evidence-grounded JSON and PDF document intelligence reports.
Includes legal disclaimer and exact evidence provenance citations.
"""
import io
import datetime
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.storage.database import get_document, get_clauses, get_risk_signals, get_relationships, get_financial_items
from app.analysis.consistency_engine import ConsistencyEngine

logger = logging.getLogger(__name__)

LEGAL_DISCLAIMER = (
    "LexiGuard provides document analysis and evidence-grounded explanations for informational "
    "purposes. It does not provide legal advice or determine legal validity or enforceability. "
    "For legal decisions, consult a qualified professional."
)


class ReportRequest(BaseModel):
    doc_ids: List[str]
    format: str = "json"  # "json" or "pdf"
    language: str = "en"


def generate_json_report(doc_ids: List[str], language: str = "en") -> Dict[str, Any]:
    """Generate a structured JSON document intelligence report for one or more documents."""
    report_data = {
        "report_title": "LexiGuard Document Intelligence Report",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "language": language,
        "disclaimer": LEGAL_DISCLAIMER,
        "documents": []
    }

    for doc_id in doc_ids:
        doc = get_document(doc_id)
        if not doc:
            continue

        clauses = get_clauses(doc_id)
        signals = get_risk_signals(doc_id)
        relationships = get_relationships(doc_id)
        financials = get_financial_items(doc_id)

        doc_section = {
            "document_id": doc_id,
            "filename": doc.get("filename", "Document"),
            "document_type": doc.get("document_type", "General Legal/Business Document"),
            "overview": {
                "page_count": doc.get("page_count", 1),
                "clause_count": len(clauses),
                "dates": doc.get("dates", []),
                "monetary_values": doc.get("monetary_values", []),
                "parties": doc.get("parties", [])
            },
            "attention_signals": [
                {
                    "category": s.get("category"),
                    "severity": s.get("severity"),
                    "section_path": s.get("section_path", "General"),
                    "page": s.get("page", 1),
                    "evidence_text": s.get("evidence_text"),
                    "explanation": s.get("plain_explanation")
                }
                for s in signals
            ],
            "clause_relationships": [
                {
                    "relationship_type": r.get("relationship_type"),
                    "relationship_status": r.get("relationship_status"),
                    "title": r.get("title"),
                    "explanation": r.get("plain_explanation"),
                    "source_section": r.get("source_section_path"),
                    "source_page": r.get("source_page"),
                    "related_section": r.get("related_section_path"),
                    "related_page": r.get("related_page")
                }
                for r in relationships
            ],
            "financial_items": [
                {
                    "item_type": f.get("item_type"),
                    "amount": f.get("amount"),
                    "currency": f.get("currency"),
                    "frequency": f.get("frequency"),
                    "condition": f.get("condition"),
                    "section_path": f.get("section_path"),
                    "page": f.get("page"),
                    "evidence_text": f.get("evidence_text")
                }
                for f in financials
            ]
        }
        report_data["documents"].append(doc_section)

    # Multi-document consistency findings if 2 or more documents
    if len(doc_ids) >= 2:
        doc_a = get_document(doc_ids[0])
        doc_b = get_document(doc_ids[1])
        if doc_a and doc_b:
            clauses_a_raw = get_clauses(doc_ids[0])
            clauses_b_raw = get_clauses(doc_ids[1])
            from app.api.questions import _deserialize_clauses
            ca = _deserialize_clauses(clauses_a_raw)
            cb = _deserialize_clauses(clauses_b_raw)
            engine = ConsistencyEngine()
            try:
                consistency_rep = engine.compare_documents(
                    doc_ids[0], doc_a.get("filename", "Doc A"), ca,
                    doc_ids[1], doc_b.get("filename", "Doc B"), cb
                )
                report_data["consistency_findings"] = consistency_rep.model_dump()
            except Exception as e:
                logger.error("Error computing consistency report section: %s", e)

    return report_data


def generate_pdf_report(doc_ids: List[str], language: str = "en") -> bytes:
    """Generate a downloadable PDF document intelligence report with legal disclaimer and citations."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc_template = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom LexiGuard Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#6B46C1')  # Purple Accent
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2D3748'),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4A5568')
    )

    disclaimer_style = ParagraphStyle(
        'Disclaimer_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#718096')
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("LexiGuard Document Intelligence Report", title_style))
    story.append(Spacer(1, 4))
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated on {now_str} | Language: {language.upper()}", body_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0'), spaceBefore=4, spaceAfter=8))

    json_report = generate_json_report(doc_ids, language)

    # Disclaimer Block
    story.append(Paragraph("<b>LEGAL DISCLAIMER:</b>", h2_style))
    story.append(Paragraph(LEGAL_DISCLAIMER, disclaimer_style))
    story.append(Spacer(1, 10))

    # Documents Content
    for d_info in json_report.get("documents", []):
        fn = d_info.get("filename", "Document")
        dtype = d_info.get("document_type", "General")
        story.append(Paragraph(f"Document: {fn} ({dtype})", h2_style))

        # Overview Table
        ov = d_info.get("overview", {})
        ov_data = [
            ["Metric / Attribute", "Value"],
            ["Page Count", str(ov.get("page_count", 1))],
            ["Clause Count", str(ov.get("clause_count", 0))],
            ["Attention Signals", str(len(d_info.get("attention_signals", [])))],
            ["Relationships Detected", str(len(d_info.get("clause_relationships", [])))],
            ["Financial Items", str(len(d_info.get("financial_items", [])))]
        ]
        t = Table(ov_data, colWidths=[200, 300])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (1,0), colors.HexColor('#EDF2F7')),
            ('TEXTCOLOR', (0,0), (1,0), colors.HexColor('#2D3748')),
            ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

        # Attention Signals Section
        signals = d_info.get("attention_signals", [])
        if signals:
            story.append(Paragraph("Attention Signals Detected", h2_style))
            for s in signals[:5]:
                cat = s.get("category", "Notice")
                sev = s.get("severity", "ATTENTION")
                sec = s.get("section_path", "General")
                pg = s.get("page", 1)
                exp = s.get("explanation", "")
                story.append(Paragraph(f"• <b>[{sev}] {cat}</b> (Section: {sec} | Page {pg}): {exp}", body_style))
            story.append(Spacer(1, 8))

        # Financial Items Section
        financials = d_info.get("financial_items", [])
        if financials:
            story.append(Paragraph("Financial & Compensation Provisions", h2_style))
            for f in financials[:5]:
                itype = f.get("item_type", "FINANCIAL")
                amt = f.get("amount") or "Unspecified"
                sec = f.get("section_path", "General")
                pg = f.get("page", 1)
                story.append(Paragraph(f"• <b>{itype}</b>: Amount {amt} (Section: {sec} | Page {pg})", body_style))
            story.append(Spacer(1, 8))

    # Consistency Findings (if present)
    if "consistency_findings" in json_report:
        c_findings = json_report["consistency_findings"]
        story.append(Paragraph("Cross-Document Consistency Findings", h2_style))
        for item in c_findings.get("items", [])[:8]:
            st = item.get("status")
            title = item.get("title")
            summary = item.get("summary")
            story.append(Paragraph(f"• <b>[{st}] {title}</b>: {summary}", body_style))
        story.append(Spacer(1, 8))

    doc_template.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
