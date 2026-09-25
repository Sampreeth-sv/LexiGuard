"""
Regression tests for LexiGuard Phase 2 Financial Intelligence Data Quality Fixes.
Verifies Indian monetary amount parsing (₹9,00,000 → 900000), effective date precision,
condition precision, and complete provenance tracking.
"""
import pytest
from app.models.schemas import Clause, ClauseMetadata
from app.analysis.entities import extract_monetary_values, normalize_monetary_amount
from app.analysis.financial_engine import FinancialEngine, analyze_document_financials


def make_clause(c_id: str, text: str, section_path: str = "Compensation", page: int = 1) -> Clause:
    meta = ClauseMetadata(
        clause_id=c_id,
        document_id="doc-dq-100",
        section_path=section_path,
        page=page,
        clause_type="compensation"
    )
    return Clause(id=c_id, metadata=meta, text=text)


def test_inr_monetary_amount_parsing_900000():
    text = "Your annual CTC will be ₹9,00,000."
    monies = extract_monetary_values(text)

    assert len(monies) >= 1
    raw_extracted = monies[0]
    assert raw_extracted == "₹9,00,000"
    assert normalize_monetary_amount(raw_extracted) == "900000"

    # Verify via FinancialEngine
    clause = make_clause("c-inr-1", text)
    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause], "doc-dq-100")

    assert len(items) >= 1
    salary_item = items[0]
    assert salary_item.amount == "₹9,00,000"
    assert normalize_monetary_amount(salary_item.amount) == "900000"
    assert salary_item.currency == "INR"
    assert salary_item.frequency == "annual"
    assert salary_item.clause_id == "c-inr-1"
    assert salary_item.page == 1
    assert "9,00,000" in salary_item.evidence_text


def test_indian_monetary_formatting_variants():
    # Rs 9,00,000 → 900000
    m_rs = extract_monetary_values("Base pay is Rs 9,00,000 per annum.")
    assert m_rs[0] in ("Rs 9,00,000", "9,00,000")
    assert normalize_monetary_amount(m_rs[0]) == "900000"

    # Rs. 9,00,000 → 900000
    m_rs_dot = extract_monetary_values("Fixed pay is Rs. 9,00,000.")
    assert normalize_monetary_amount(m_rs_dot[0]) == "900000"

    # INR 9,00,000 → 900000
    m_inr = extract_monetary_values("Remuneration INR 9,00,000 annually.")
    assert normalize_monetary_amount(m_inr[0]) == "900000"

    # ₹12,50,000.50 → 1250000.50
    m_decimal = extract_monetary_values("Annual salary ₹12,50,000.50.")
    assert normalize_monetary_amount(m_decimal[0]) == "1250000.50"

    # 900000 → 900000
    m_plain = extract_monetary_values("Annual salary INR 900000.")
    assert normalize_monetary_amount(m_plain[0]) == "900000"

    # 9,00,000 → 900000
    m_comma = extract_monetary_values("Annual compensation 9,00,000 rupees.")
    assert normalize_monetary_amount(m_comma[0]) == "900000"


def test_usd_eur_gbp_preservation():
    assert extract_monetary_values("Salary $5,000 per month.")[0] == "$5,000"
    assert extract_monetary_values("Allowance €1,200 per month.")[0] == "€1,200"
    assert extract_monetary_values("Base pay £80,000 per annum.")[0] == "£80,000"


def test_effective_date_precision_joining_date_not_assigned():
    # Joining date should NOT be assigned to FinancialItem.effective_date
    clause = make_clause(
        "c-date-1",
        "The Employee shall join the Company on October 1, 2026 and shall receive an annual CTC of ₹9,00,000."
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) >= 1
    salary_item = items[0]
    assert salary_item.effective_date is None


def test_effective_date_precision_explicit_date_assigned():
    # Explicit financial effective date SHOULD be assigned
    clause = make_clause(
        "c-date-2",
        "Base salary of ₹9,00,000 per annum, effective from 01 January 2027."
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) >= 1
    salary_item = items[0]
    assert salary_item.effective_date == "01 January 2027"


def test_condition_precision_generic_isolated_phrase_eliminated():
    # Payroll boilerplate should NOT result in condition = "subject to"
    clause = make_clause(
        "c-cond-1",
        "Salary will be paid monthly in accordance with Company payroll practices."
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) >= 1
    salary_item = items[0]
    assert salary_item.condition is None


def test_condition_precision_substantive_condition_preserved():
    # Substantive condition SHOULD be extracted in full
    clause = make_clause(
        "c-cond-2",
        "Annual performance bonus of ₹1,00,000 subject to successful completion of the performance review."
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) >= 1
    bonus_item = next(i for i in items if "BONUS" in i.item_type)
    assert bonus_item.condition is not None
    assert bonus_item.condition != "subject to"
    assert "successful completion of the performance review" in bonus_item.condition


def test_tax_withholding_commercial_agreement_tax_at_source():
    """Commercial agreement with 'Client may deduct tax at source...' must yield TAX_WITHHOLDING, not DEDUCTION."""
    clause = make_clause(
        "c-tax-1",
        "Applicable GST and other indirect taxes. Client may deduct tax at source where legally required under applicable tax laws.",
        section_path="Taxes & Payments",
        page=4
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) == 1
    tax_item = items[0]
    assert tax_item.item_type == "TAX_WITHHOLDING"
    assert tax_item.amount is None
    assert tax_item.currency is None
    assert tax_item.frequency is None
    assert tax_item.completeness_note is None
    assert tax_item.clause_id == "c-tax-1"
    assert tax_item.section_path == "Taxes & Payments"
    assert tax_item.page == 4
    assert "deduct tax at source" in tax_item.evidence_text.lower()


def test_tax_withholding_shall_apply():
    """'Withholding tax shall apply...' must yield TAX_WITHHOLDING."""
    clause = make_clause(
        "c-tax-2",
        "Withholding tax shall apply to all gross fee payments under this Master Services Agreement.",
        section_path="Section 5. Fees and Taxes",
        page=2
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) == 1
    tax_item = items[0]
    assert tax_item.item_type == "TAX_WITHHOLDING"
    assert tax_item.amount is None
    assert tax_item.completeness_note is None
    assert tax_item.clause_id == "c-tax-2"


def test_tax_withholding_vs_salary_deduction_employment_document():
    """Employment document with 'Applicable deductions from salary...' must yield DEDUCTION, not TAX_WITHHOLDING."""
    clause = make_clause(
        "c-deduct-1",
        "Applicable deductions from salary will be made in accordance with local labor and payroll regulations.",
        section_path="Payroll & Compensation",
        page=3
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) == 1
    deduction_item = items[0]
    assert deduction_item.item_type == "DEDUCTION"
    assert deduction_item.item_type != "TAX_WITHHOLDING"
    assert deduction_item.clause_id == "c-deduct-1"


def test_tax_withholding_without_amount_provenance():
    """Tax withholding without an explicit monetary amount must preserve evidence and provenance without misleading completeness warning."""
    clause = make_clause(
        "c-tax-3",
        "TDS shall be withheld from all consultant payouts in accordance with the Income Tax Act.",
        section_path="Taxation",
        page=5
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) == 1
    tax_item = items[0]
    assert tax_item.item_type == "TAX_WITHHOLDING"
    assert tax_item.amount is None
    assert tax_item.completeness_note is None
    assert tax_item.clause_id == "c-tax-3"
    assert tax_item.section_path == "Taxation"
    assert tax_item.page == 5
    assert "tds" in tax_item.evidence_text.lower()


def test_tax_withholding_with_explicit_tds_amount():
    """Tax withholding with explicit TDS amount preserves extracted monetary amount and currency."""
    clause = make_clause(
        "c-tax-4",
        "Client shall deduct 10% TDS amounting to ₹50,000 from the final invoice payment.",
        section_path="Invoice & Tax",
        page=6
    )
    items = analyze_document_financials("doc-dq-100", [clause])

    assert len(items) >= 1
    tax_item = next(i for i in items if i.item_type == "TAX_WITHHOLDING")
    assert tax_item.amount == "₹50,000"
    assert tax_item.currency == "INR"
    assert tax_item.clause_id == "c-tax-4"

