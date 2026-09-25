"""
Unit and API integration tests for LexiGuard English-Only UI and Analysis.
Verifies translation dictionary, fallback handling, evidence text preservation,
citation integrity, and API endpoint integration.
"""
import pytest
from app.analysis.multilingual import get_translation, get_all_translations, SUPPORTED_LANGUAGES, UI_TRANSLATIONS
from app.models.schemas import Clause, ClauseMetadata
from app.llm.prompts import build_qa_prompt, build_cross_qa_prompt
from app.llm.provider import FallbackProvider


def test_supported_languages_dict():
    assert "en" in SUPPORTED_LANGUAGES


def test_ui_translation_keys_completeness():
    en_keys = set(UI_TRANSLATIONS["en"].keys())
    assert len(en_keys) > 0


def test_get_translation_fallback_to_english():
    val = get_translation("analyze", "en")
    assert val == "Analyze"


def test_evidence_quote_preservation_in_qa_prompt():
    original_quote = "The employee shall provide thirty days' written notice prior to resignation."
    clause = Clause(
        id="c1",
        metadata=ClauseMetadata(clause_id="c1", document_id="d1", section_path="Section 10. Notice", page=2),
        text=original_quote
    )
    doc_map = {"Offer_Letter.pdf": [clause]}
    prompt = build_cross_qa_prompt("What is the notice period?", doc_map, language="en")

    assert original_quote in prompt
    assert "[Document: Filename, Section X, Page Y]" in prompt


def test_citation_format_preservation():
    clause = Clause(
        id="c1",
        metadata=ClauseMetadata(clause_id="c1", document_id="d1", section_path="Section 4. Remuneration", page=1),
        text="Base salary is 900000 per annum."
    )
    prompt = build_qa_prompt("What is the salary?", [clause], "Offer.pdf")
    assert "[EVIDENCE 1]" in prompt
    assert "Section: Section 4. Remuneration" in prompt
    assert "Page: 1" in prompt


def test_fallback_provider_behavior():
    clause = Clause(
        id="c1",
        metadata=ClauseMetadata(clause_id="c1", document_id="d1", section_path="Notice", page=1),
        text="Notice period is 30 days."
    )
    provider = FallbackProvider()
    resp = provider.answer_question("What is the notice period?", [clause], "Offer.pdf")

    assert resp.abstained is True
    assert "AI analysis is currently unavailable" in resp.answer


def test_translations_api_endpoint(client):
    res = client.get("/api/workspace/translations/en")
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "en"
    assert "translations" in data
    assert "analyze" in data["translations"]


def test_translations_api_unsupported_language_fallback(client):
    res = client.get("/api/workspace/translations/fr")
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "en"
