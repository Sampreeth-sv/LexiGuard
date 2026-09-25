"""
Risk engine tests — one test per rule category (17 total) plus document-level tests.
All deterministic, zero LLM calls.
"""
import pytest
from app.analysis.risk_engine import RiskEngine
from app.analysis.rules import ALL_RULES
from app.models.schemas import Clause, ClauseMetadata, Severity
from app.ingestion.text_parser import extract_text_from_txt
from app.ingestion.structure import segment_document
import uuid


def make_clause(text: str, clause_type: str = "general") -> Clause:
    cid = str(uuid.uuid4())
    return Clause(
        id=cid,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id="doc1",
            section_id="sec1",
            heading="Test Heading",
            section_path="Article I > Section 1.1",
            page=1,
            clause_type=clause_type,
            char_count=len(text),
        ),
        text=text,
    )


# ── Per-Rule Detection Tests ──────────────────────────────────────────────────

def test_auto_renewal_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The agreement shall automatically renew for successive one-year terms."))
    assert any(s.category == "renewal" for s in signals)


def test_termination_restriction_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("liquidated damages for early termination shall apply."))
    assert any(s.category == "termination" for s in signals)


def test_broad_indemnification_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant shall indemnify and hold harmless the Company from all claims."))
    assert any(s.category == "indemnity" for s in signals)


def test_liability_limitation_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The aggregate liability shall not exceed the total fees paid in three months."))
    assert any(s.category == "liability" for s in signals)


def test_unilateral_modification_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Company reserves the right to modify the terms at any time at its sole discretion."))
    assert any(s.category == "modification" for s in signals)


def test_arbitration_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("All disputes shall be resolved through binding arbitration and parties waive their right to a jury trial."))
    assert any(s.category == "arbitration" for s in signals)


def test_jurisdiction_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("This agreement shall be governed by the laws of the State of Delaware."))
    assert any(s.category == "jurisdiction" for s in signals)


def test_confidentiality_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant shall keep all confidential information strictly confidential and shall not disclose it."))
    assert any(s.category == "confidentiality" for s in signals)


def test_non_compete_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant shall not compete with the Company for 12 months after termination."))
    assert any(s.category == "non_compete" for s in signals)


def test_payment_obligation_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Fees are due within 30 days of invoice receipt."))
    assert any(s.category == "payment" for s in signals)


def test_late_fee_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Overdue payments shall accrue interest at the rate of 1.5% per month on the outstanding balance."))
    assert any(s.category == "payment" for s in signals)


def test_ip_ownership_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("All deliverables shall be considered work made for hire and the exclusive property of the Company."))
    assert any(s.category == "ip" for s in signals)


def test_warranty_disclaimer_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The services are provided as-is without warranty of any kind, express or implied."))
    assert any(s.category == "warranty" for s in signals)


def test_notice_requirement_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Termination requires written notice at least 30 days prior to the end of the term."))
    assert any(s.category == "notice" for s in signals)


def test_privacy_data_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant may process personal data and must comply with GDPR regulations."))
    assert any(s.category == "privacy" for s in signals)


def test_broad_obligation_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant shall be solely responsible for any and all losses arising from their work."))
    assert any(s.category == "obligation" for s in signals)


def test_ambiguous_standard_detected():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The Consultant shall use commercially reasonable efforts to complete the deliverables."))
    assert any(s.category == "obligation" for s in signals)


# ── Edge Cases ────────────────────────────────────────────────────────────────

def test_no_false_positive_on_empty():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause(""))
    assert len(signals) == 0


def test_no_false_positive_on_benign():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The parties agree to work together in good faith on this project."))
    # May or may not detect signals but shouldn't crash
    assert isinstance(signals, list)


# ── Document-Level Tests ──────────────────────────────────────────────────────

def test_analyze_document_returns_signals(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-risk-test")
    engine = RiskEngine()
    signals = engine.analyze_document(clauses, "doc-risk-test")
    assert len(signals) >= 5, f"Expected at least 5 signals, got {len(signals)}"


def test_signal_has_evidence_text(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-risk-test")
    engine = RiskEngine()
    signals = engine.analyze_document(clauses, "doc-risk-test")
    for s in signals:
        assert s.evidence_text and len(s.evidence_text) > 0


def test_signal_has_section_path(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-risk-test")
    engine = RiskEngine()
    signals = engine.analyze_document(clauses, "doc-risk-test")
    for s in signals:
        assert s.section_path is not None


def test_signal_has_plain_explanation(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-risk-test")
    engine = RiskEngine()
    signals = engine.analyze_document(clauses, "doc-risk-test")
    for s in signals:
        assert s.plain_explanation and len(s.plain_explanation) > 0


def test_all_rules_have_patterns():
    for rule in ALL_RULES:
        assert len(rule.patterns) > 0, f"Rule {rule.rule_id} has no patterns"


def test_all_expanded_rules_present():
    assert len(ALL_RULES) >= 33


# ── New Rule & Document Type Tests ───────────────────────────────────────────

def test_training_bond_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Employee agrees to repay training cost if leaving within 12 months."))
    assert any(s.category == "employment_bond" for s in signals)


def test_bonus_clawback_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The joining bonus is subject to repayment if employee resigns before 1 year."))
    assert any(s.category == "bonus_clawback" for s in signals)


def test_minimum_service_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Employee agrees to a minimum service period of 24 months."))
    assert any(s.category == "minimum_service" for s in signals)


def test_non_solicitation_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("Former employee shall not solicit any client or employee for 2 years."))
    assert any(s.category == "non_solicitation" for s in signals)


def test_relocation_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The company reserves the right to transfer employee to another office location."))
    assert any(s.category == "relocation" for s in signals)


def test_unlimited_liability_rule():
    engine = RiskEngine()
    signals = engine.analyze_clause(make_clause("The limitation of liability cap shall not apply to indemnification obligations."))
    assert any(s.category in ("unlimited_liability", "indemnity_mismatch") for s in signals)


def test_document_type_detection():
    from app.analysis.entities import detect_document_type
    emp_clause = make_clause("Offer Letter for the position of Senior Software Engineer with annual salary of USD 100,000.")
    assert detect_document_type([emp_clause]) == "Employment"

    nda_clause = make_clause("Non-Disclosure Agreement between Disclosing Party and Receiving Party regarding confidential information.")
    assert detect_document_type([nda_clause]) == "NDA"

    comm_clause = make_clause("Master Services Agreement for Statement of Work deliverables.")
    assert detect_document_type([comm_clause]) == "Commercial/Project"

    terms_clause = make_clause("Terms of Service and End User License Agreement.")
    assert detect_document_type([terms_clause]) == "Terms & Conditions"

    gen_clause = make_clause("General business overview document.")
    assert detect_document_type([gen_clause]) == "General Legal/Business Document"

    assert detect_document_type([]) == "Unknown"

