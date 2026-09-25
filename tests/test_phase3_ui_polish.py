"""
Regression and verification tests for LexiGuard Phase 3 English UI Polish
and Temporal Obligation Duplicate Check.
"""
import pytest
from app.analysis.entities import extract_dates, classify_date_context
from app.analysis.multilingual import (
    get_translation, get_all_translations, UI_TRANSLATIONS, SUPPORTED_LANGUAGES
)
from app.models.schemas import Clause, ClauseMetadata, RiskSignal, ChecklistItem
from app.llm.prompts import build_qa_prompt, build_cross_qa_prompt


def test_temporal_date_deduplication_exact_clause_case():
    text = 'This agreement is made effective as of 1 October 2026 ("Effective Date").'
    dates = extract_dates(text)
    assert "1 October 2026" in dates
    assert "October 2026" not in dates
    assert len(dates) == 1


def test_temporal_distinct_dates_preserved():
    text = "Effective date is 1 October 2026 and termination date is 15 November 2027."
    dates = extract_dates(text)
    assert "1 October 2026" in dates
    assert "15 November 2027" in dates
    assert len(dates) == 2


def test_temporal_date_context_classification():
    assert classify_date_context("1 October 2026", "Notice must be served 30 days prior") == "notice_period"
    assert classify_date_context("1 October 2026", "Payment due date is 1 October 2026") == "payment_date"
    assert classify_date_context("1 October 2026", "Probation period ends 1 October 2026") == "probation_service_period"
    assert classify_date_context("1 October 2026", "Effective Date 1 October 2026") == "temporal_obligation"


def test_analyze_view_translation_keys_completeness():
    analyze_keys = [
        "doc_overview_title",
        "risk_signals",
        "monetary_values",
        "contracting_parties",
        "dates_temporal_title",
        "clauses",
        "important_dates",
        "key_obligations",
        "view_in_doc",
        "view_source",
        "why_seeing_this",
        "hide_explanation",
        "suggested_verification"
    ]
    t_dict = get_all_translations("en")
    for key in analyze_keys:
        assert key in t_dict
        assert len(t_dict[key].strip()) > 0


def test_analyze_labels_english_content():
    overview_t = get_translation("doc_overview_title", "en")
    signals_t = get_translation("risk_signals", "en")
    dates_t = get_translation("dates_temporal_title", "en")

    assert overview_t == "Document Understanding Overview"
    assert signals_t == "Risk Signals"
    assert dates_t == "Important Dates & Temporal Obligations"


def test_prepare_checklist_category_translation_keys():
    checklist_cat_keys = ["general_review", "payment_terms", "lawyer_questions", "review"]
    for key in checklist_cat_keys:
        val = get_translation(key, "en")
        assert len(val) > 0


def test_source_evidence_untranslated_in_views():
    raw_source_clause = "The Consultant shall not disclose any Proprietary Information to third parties without prior written consent."
    clause = Clause(
        id="c_nda_1",
        metadata=ClauseMetadata(
            clause_id="c_nda_1",
            document_id="doc_nda",
            section_path="Section 4. Confidentiality",
            page=2
        ),
        text=raw_source_clause
    )
    prompt = build_qa_prompt("What are confidentiality rules?", [clause], "NDA.pdf", language="en")
    assert raw_source_clause in prompt
    assert "Section: Section 4. Confidentiality" in prompt
    assert "Page: 2" in prompt


def test_citation_structure_untranslated():
    doc_map = {
        "Service_Agreement.pdf": [
            Clause(
                id="c_sa_1",
                metadata=ClauseMetadata(clause_id="c_sa_1", document_id="d1", section_path="Section 12", page=5),
                text="Payment is due within 30 days of invoice."
            )
        ]
    }
    prompt = build_cross_qa_prompt("When is payment due?", doc_map, language="en")
    assert "[Document: Filename, Section X, Page Y]" in prompt
    assert "Payment is due within 30 days of invoice." in prompt
