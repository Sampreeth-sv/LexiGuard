"""
Financial and Compensation Data Models for LexiGuard Phase 2 Feature 3.
Defines structured schemas for deterministic financial, salary, bonus, allowance,
reimbursement, and monetary attribute extraction.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import uuid


class FinancialItem(BaseModel):
    """
    Structured financial or compensation item extracted from document clauses.
    Fully groundable with clause_id, section_path, page, and evidence_text provenance.
    """
    model_config = ConfigDict(extra='ignore')

    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    item_type: str = Field(description="Category: BASE_SALARY, ANNUAL_SALARY, MONTHLY_SALARY, HOURLY_COMPENSATION, VARIABLE_COMPENSATION, BONUS, PERFORMANCE_BONUS, COMMISSION, ALLOWANCE, REIMBURSEMENT, BENEFIT, DEDUCTION, TAX_WITHHOLDING, PROBATION_COMPENSATION, TERMINATION_MONETARY, NOTICE_COMPENSATION")
    amount: Optional[str] = Field(default=None, description="Extracted numerical or textual amount")
    currency: Optional[str] = Field(default=None, description="Extracted currency (e.g. INR, USD, EUR, GBP, ₹, $, £, €)")
    frequency: Optional[str] = Field(default=None, description="Payment frequency: annual, monthly, hourly, one-time, per annum, per month")
    condition: Optional[str] = Field(default=None, description="Extracted condition or dependency (e.g., subject to performance)")
    effective_date: Optional[str] = Field(default=None, description="Extracted effective date for compensation")
    payment_timing: Optional[str] = Field(default=None, description="Payment date or timing (e.g., within 30 days, 5th of each month)")

    # Provenance
    clause_id: str
    section_path: Optional[str] = "General"
    page: int = 1
    evidence_text: str = ""

    # Completeness Observation
    completeness_note: Optional[str] = Field(default=None, description="Factual completeness note if attribute is unspecified")
