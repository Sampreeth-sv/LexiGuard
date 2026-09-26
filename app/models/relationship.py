"""
Clause Relationship Data Models for LexiGuard Phase 2 Feature 2.
Defines structured schemas for deterministic clause relationships, missing counterparts,
and structural asymmetry detection.
"""
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import Optional
import uuid


class ClauseRelationshipStatus(str, Enum):
    BALANCED_RELATIONSHIP = "BALANCED_RELATIONSHIP"
    RELATED = "BALANCED_RELATIONSHIP"
    POTENTIAL_ASYMMETRY = "POTENTIAL_ASYMMETRY"
    MISSING_COUNTERPART = "MISSING_COUNTERPART"
    INCOMPLETE_RELATIONSHIP = "INCOMPLETE_RELATIONSHIP"
    UNRESOLVED = "UNRESOLVED"


class ClauseRelationshipType(str, Enum):
    TERMINATION_NOTICE = "TERMINATION_NOTICE"
    OBLIGATION_DEADLINE = "OBLIGATION_DEADLINE"
    PAYMENT_DEADLINE = "PAYMENT_DEADLINE"
    CONFIDENTIALITY_SURVIVAL = "CONFIDENTIALITY_SURVIVAL"
    INDEMNITY_LIABILITY_CAP = "INDEMNITY_LIABILITY_CAP"
    PARTY_OBLIGATION_ASYMMETRY = "PARTY_OBLIGATION_ASYMMETRY"
    RIGHT_CONDITION = "RIGHT_CONDITION"


class ClauseRelationship(BaseModel):
    """
    Structured relationship between document clauses.
    Supports both two-clause relationships and one-clause missing counterpart relationships.
    """
    model_config = ConfigDict(extra='ignore')

    relationship_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    relationship_type: ClauseRelationshipType
    relationship_status: ClauseRelationshipStatus
    confidence: str = Field(default="HIGH", description="Detection confidence: HIGH, MEDIUM, LOW")
    title: str
    explanation: str
    verification_question: Optional[str] = None

    # Source Clause Provenance (Mandatory)
    source_clause_id: str
    source_section_path: str = "General"
    source_page: int = 1
    source_excerpt: str = ""

    # Related Clause Provenance (Optional / Null-capable for missing counterparts)
    related_clause_id: Optional[str] = Field(default=None, description="Clause ID of related clause, or None if counterpart is missing")
    related_section_path: Optional[str] = Field(default=None, description="Section path of related clause, or None")
    related_page: Optional[int] = Field(default=None, description="Page number of related clause, or None")
    related_excerpt: Optional[str] = Field(default=None, description="Excerpt quote of related clause, or None")

    @property
    def plain_explanation(self) -> str:
        return self.explanation

    @property
    def question_to_ask(self) -> Optional[str]:
        return self.verification_question or ""

