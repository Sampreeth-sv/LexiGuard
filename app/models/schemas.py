"""
LexiGuard Pydantic data schemas.
Central source of truth for all data models used across the application.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid
from datetime import datetime


class Severity(str, Enum):
    HIGH = 'HIGH ATTENTION'
    MEDIUM = 'MEDIUM ATTENTION'
    LOW = 'LOW ATTENTION'
    INFORMATIONAL = 'INFORMATIONAL'


class GroundingStatus(str, Enum):
    STRONGLY_GROUNDED = 'STRONGLY GROUNDED'
    SUPPORTED = 'SUPPORTED'
    LIMITED_EVIDENCE = 'LIMITED EVIDENCE'
    INSUFFICIENT_EVIDENCE = 'INSUFFICIENT EVIDENCE'


class DiffType(str, Enum):
    ADDED = 'ADDED'
    REMOVED = 'REMOVED'
    MODIFIED = 'MODIFIED'
    UNCHANGED = 'UNCHANGED'


from pydantic import BaseModel, Field, ConfigDict

class ClauseMetadata(BaseModel):
    model_config = ConfigDict(extra='ignore')
    clause_id: str
    document_id: str
    document_filename: Optional[str] = None
    section_id: Optional[str] = None
    heading: Optional[str] = None
    section_path: Optional[str] = None
    page: int = 1
    clause_type: str = 'general'
    char_count: int = 0
    dates: List[str] = Field(default_factory=list)
    monetary_values: List[str] = Field(default_factory=list)
    obligations: List[str] = Field(default_factory=list)


class Clause(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    metadata: ClauseMetadata
    text: str

    @property
    def heading(self) -> Optional[str]:
        return self.metadata.heading

    @property
    def section_path(self) -> Optional[str]:
        return self.metadata.section_path

    @property
    def clause_type(self) -> str:
        return self.metadata.clause_type

    @property
    def page(self) -> int:
        return self.metadata.page


class RiskSignal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    clause_id: str
    document_id: str
    category: str
    severity: Severity
    matched_pattern: Optional[str] = None
    evidence_text: str
    section_path: Optional[str] = None
    page: int = 1
    plain_explanation: str
    question_to_ask: Optional[str] = None


class ClaimEvidence(BaseModel):
    clause_id: str
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    section_path: Optional[str] = None
    page: Optional[int] = None
    quoted_text: str


class QAResponse(BaseModel):
    answer: str
    evidences: List[ClaimEvidence] = Field(default_factory=list)
    grounding_status: GroundingStatus = GroundingStatus.INSUFFICIENT_EVIDENCE
    suggested_followup: Optional[str] = None
    abstained: bool = False


class TemporalObligation(BaseModel):
    date: str
    context_type: str
    description: str
    clause_id: Optional[str] = None
    section_path: Optional[str] = None
    page: int = 1


class DocumentOverview(BaseModel):
    document_id: str
    filename: str
    document_type: str = 'General Legal/Business Document'
    page_count: int = 0
    clause_count: int = 0
    signal_count: int = 0
    entity_count: int = 0
    dates: List[str] = Field(default_factory=list)
    monetary_values: List[str] = Field(default_factory=list)
    parties: List[str] = Field(default_factory=list)
    genai_available: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processing_status: str = 'complete'



class ClauseDiff(BaseModel):
    diff_type: DiffType
    clause_id_a: Optional[str] = None
    clause_id_b: Optional[str] = None
    section_path_a: Optional[str] = None
    section_path_b: Optional[str] = None
    page_a: Optional[int] = None
    page_b: Optional[int] = None
    text_a: Optional[str] = None
    text_b: Optional[str] = None
    similarity_score: float = 0.0
    diff_summary: Optional[str] = None
    change_category: Optional[str] = None
    financial_change: Optional[str] = None
    relationship_change: Optional[str] = None


class ComparisonResult(BaseModel):
    document_id_a: str
    document_id_b: str
    added: List[ClauseDiff] = Field(default_factory=list)
    removed: List[ClauseDiff] = Field(default_factory=list)
    modified: List[ClauseDiff] = Field(default_factory=list)
    unchanged_count: int = 0


class ChecklistItem(BaseModel):
    item: str
    category: str = 'general'
    done: bool = False
    clause_reference: Optional[str] = None


class Checklist(BaseModel):
    title: str
    items: List[ChecklistItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SummaryResponse(BaseModel):
    document_id: str
    summary: str
    genai_used: bool = False


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


from app.models.evidence import EvidenceLocationResponse
from app.models.relationship import (
    ClauseRelationship,
    ClauseRelationshipStatus,
    ClauseRelationshipType,
)
from app.models.financial import FinancialItem


