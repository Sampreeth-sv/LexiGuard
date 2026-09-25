"""
Tests for LexiGuard Phase 2 Feature 3: Financial & Compensation Intelligence.
Verifies deterministic extraction of financial items, salary, bonuses, allowances,
reimbursements, deductions, currencies, completeness observations, and provenance.
"""
import pytest
from app.models.schemas import Clause, ClauseMetadata
from app.analysis.financial_engine import FinancialEngine, analyze_document_financials


def make_clause(c_id: str, text: str, section_path: str = "Compensation", page: int = 1) -> Clause:
    meta = ClauseMetadata(
        clause_id=c_id,
        document_id="doc-test-100",
        section_path=section_path,
        page=page,
        clause_type="compensation"
    )
    return Clause(id=c_id, metadata=meta, text=text)


def test_annual_salary_extraction():
    clause = make_clause("c1", "The Employee shall receive a base salary of ₹12,000,000 per annum, payable monthly.")
    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause], "doc-test-100")

    assert len(items) >= 1
    salary_item = next(i for i in items if i.item_type in ("ANNUAL_SALARY", "BASE_SALARY"))
    assert salary_item.amount == "₹12,000,000"
    assert salary_item.currency == "INR"
    assert salary_item.frequency == "annual"
    assert salary_item.clause_id == "c1"
    assert salary_item.section_path == "Compensation"
    assert salary_item.page == 1
    assert "12,000,000" in salary_item.evidence_text


def test_monthly_salary_extraction():
    clause = make_clause("c2", "The monthly salary for this role is $5,000 USD paid on the 1st of each month.")
    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause], "doc-test-100")

    assert len(items) >= 1
    monthly_item = next(i for i in items if i.item_type == "MONTHLY_SALARY")
    assert monthly_item.amount in ("$5,000", "5,000 USD")
    assert monthly_item.currency == "USD"
    assert monthly_item.frequency == "monthly"


def test_bonus_and_performance_bonus():
    clause = make_clause("c3", "The Employee is eligible for an annual performance bonus of up to ₹250,000 subject to performance target completion.")
    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause], "doc-test-100")

    bonus_item = next(i for i in items if i.item_type in ("PERFORMANCE_BONUS", "BONUS"))
    assert bonus_item.amount == "₹250,000"
    assert bonus_item.currency == "INR"
    assert bonus_item.condition is not None
    assert "subject to" in bonus_item.condition.lower()


def test_missing_compensation_attribute_completeness_observation():
    clause = make_clause("c4", "The Company may pay an annual discretionary bonus depending on corporate profit.")
    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause], "doc-test-100")

    bonus_item = next(i for i in items if "BONUS" in i.item_type)
    assert bonus_item.amount is None
    assert bonus_item.completeness_note is not None
    assert "Bonus provision identified, but fixed amount is not specified" in bonus_item.completeness_note


def test_commission_and_allowance():
    clause1 = make_clause("c5", "Sales representatives earn a 5% commission on net revenue.")
    clause2 = make_clause("c6", "The Company provides a monthly housing allowance of €1,200.")

    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause1, clause2], "doc-test-100")

    item_types = [i.item_type for i in items]
    assert "COMMISSION" in item_types
    assert "ALLOWANCE" in item_types

    allowance = next(i for i in items if i.item_type == "ALLOWANCE")
    assert allowance.amount == "€1,200"
    assert allowance.currency == "EUR"
    assert allowance.frequency == "monthly"


def test_reimbursement_and_deduction():
    clause1 = make_clause("c7", "Business travel expense claim reimbursement will be processed within 14 days.")
    clause2 = make_clause("c8", "Any unreturned company property will result in a tax deduction or penalty equal to $500.")

    engine = FinancialEngine()
    items = engine.analyze_document_financials([clause1, clause2], "doc-test-100")

    types = [i.item_type for i in items]
    assert "REIMBURSEMENT" in types
    assert "DEDUCTION" in types or "TERMINATION_MONETARY" in types


def test_probation_and_termination_monetary():
    c_prob = make_clause("c9", "During probation, the probationary salary shall be ₹50,000 per month.")
    c_term = make_clause("c10", "Upon termination without cause, severance of 2 months salary shall be paid.")

    items = analyze_document_financials("doc-test-100", [c_prob, c_term])
    types = [i.item_type for i in items]

    assert "PROBATION_COMPENSATION" in types
    assert "TERMINATION_MONETARY" in types


def test_provenance_and_deterministic_repeatability():
    clause = make_clause("c11", "Base salary of £80,000 per annum starting 01 January 2027.", section_path="Schedule 1", page=3)
    
    items1 = analyze_document_financials("doc-test-100", [clause])
    items2 = analyze_document_financials("doc-test-100", [clause])

    assert len(items1) == len(items2)
    assert items1[0].item_id == items2[0].item_id
    assert items1[0].clause_id == "c11"
    assert items1[0].section_path == "Schedule 1"
    assert items1[0].page == 3
    assert items1[0].currency == "GBP"


def test_api_financial_endpoint(client):
    from app.storage.database import save_document, save_clause
    from app.models.schemas import DocumentOverview

    doc = DocumentOverview(
        document_id="doc-fin-api-1",
        filename="offer_letter.pdf",
        page_count=2,
        clause_count=1,
        signal_count=0
    )
    save_document(doc)

    clause = make_clause("c-api-1", "Fixed compensation of ₹1,500,000 per annum payable monthly.")
    clause.metadata.document_id = "doc-fin-api-1"
    save_clause(clause)

    res = client.get("/api/documents/doc-fin-api-1/financial")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["currency"] == "INR"
    assert data[0]["amount"] == "₹1,500,000"
    assert data[0]["clause_id"] == "c-api-1"
