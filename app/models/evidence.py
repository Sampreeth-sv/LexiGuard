"""
Evidence Location Schema for LexiGuard Phase 2.
Defines structured data models for click-to-evidence navigation and PDF page anchoring.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class EvidenceLocationResponse(BaseModel):
    """
    Response model for GET /api/documents/{doc_id}/evidence/{clause_id}.
    Provides minimum deterministic provenance required for frontend PDF/document navigation.
    """
    model_config = ConfigDict(extra='ignore')

    document_id: str
    clause_id: str
    page_number: int = Field(default=1, description="1-indexed page number in the original document")
    section_path: str = Field(default="General", description="Hierarchical section path (e.g. Article I > Section 1.1)")
    evidence_quote: Optional[str] = Field(default=None, description="Exact text quote cited as evidence")
    clause_text: str = Field(default="", description="Full text of the containing clause")
    file_type: str = Field(default="pdf", description="Document file extension (pdf, docx, txt)")
    match_status: str = Field(
        default="page_level_available",
        description="One of: 'exact_highlight_available', 'page_level_available', 'location_unavailable'"
    )
    char_start: Optional[int] = Field(default=None, description="Optional character start index within clause text")
    char_end: Optional[int] = Field(default=None, description="Optional character end index within clause text")
