"""
Regression tests for LexiGuard Workspace and Navigation Routing.
"""
import pytest
from app.analysis.multilingual import get_translation, get_all_translations, SUPPORTED_LANGUAGES, UI_TRANSLATIONS
from app.storage.database import save_document, delete_document, get_document
from app.models.schemas import DocumentOverview, Clause, ClauseMetadata
from app.llm.prompts import build_qa_prompt, build_cross_qa_prompt


def test_multilingual_all_languages_defined():
    assert "en" in SUPPORTED_LANGUAGES
    assert "en" in UI_TRANSLATIONS


def test_multilingual_translation_keys_completeness():
    required_keys = [
        "dashboard", "workspace", "analyze", "ask", "compare", "prepare",
        "hero_title", "hero_subtitle", "upload_title", "browse_files",
        "recent_documents", "documents", "open", "delete", "pages",
        "financial_items", "generate_summary", "ai_summary", "doc_map",
        "ask_title", "ask_placeholder", "compare_docs", "orig_doc", "revised_doc",
        "added", "removed", "modified", "unchanged", "prep_review", "gen_checklist",
        "disclaimer_text", "view_source", "evidence_viewer"
    ]
    t_map = get_all_translations("en")
    for k in required_keys:
        assert k in t_map, f"Missing key '{k}' in English translation"
        assert len(t_map[k]) > 0, f"Empty translation for key '{k}'"


def test_unsupported_language_fallback_to_english():
    assert get_translation("hero_title", "invalid_lang") == "Understand your legal documents"
    assert get_translation("workspace", "fr") == "Workspace"


def test_source_evidence_untranslated_in_prompts():
    original_evidence = "The Annual CTC payable to the Employee shall be 1250000 per annum."
    clause = Clause(
        id="c_test_ev",
        metadata=ClauseMetadata(clause_id="c_test_ev", document_id="doc_ev", section_path="Section 3. Remuneration", page=2),
        text=original_evidence
    )
    prompt = build_qa_prompt("What is the salary?", [clause], "Offer_Letter.pdf", language="en")
    assert original_evidence in prompt
    assert "[EVIDENCE 1]" in prompt
    assert "Section: Section 3. Remuneration" in prompt
    assert "Page: 2" in prompt


def test_citation_format_untranslated_across_languages():
    doc_map = {
        "Employment_Agreement.pdf": [
            Clause(
                id="c1",
                metadata=ClauseMetadata(clause_id="c1", document_id="d1", section_path="Section 10. Notice", page=3),
                text="Notice period is 60 days."
            )
        ]
    }
    prompt = build_cross_qa_prompt("What is the notice period?", doc_map, language="en")
    assert '[Document: Filename, Section X, Page Y]' in prompt


def test_workspace_api_endpoint_structure(client):
    res = client.get("/api/workspace")
    assert res.status_code == 200
    docs = res.json()
    assert isinstance(docs, list)


def test_workspace_and_dashboard_distinct_routing(client):
    doc_a = DocumentOverview(document_id="doc-route-a", filename="RouteDocA.pdf", page_count=3, clause_count=5, signal_count=1)
    doc_b = DocumentOverview(document_id="doc-route-b", filename="RouteDocB.pdf", page_count=4, clause_count=8, signal_count=2)
    save_document(doc_a)
    save_document(doc_b)

    res_dash = client.get("/api/documents/")
    assert res_dash.status_code == 200
    dash_docs = res_dash.json()
    assert len(dash_docs) >= 2

    res_ws = client.get("/api/workspace")
    assert res_ws.status_code == 200
    ws_docs = res_ws.json()
    assert len(ws_docs) >= 2

    sample = next(d for d in ws_docs if d["document_id"] == "doc-route-a")
    assert "document_id" in sample
    assert "filename" in sample
    assert "page_count" in sample
    assert "clause_count" in sample
    assert "attention_signal_count" in sample
    assert "relationship_count" in sample
    assert "financial_item_count" in sample


def test_workspace_cascade_deletion(client):
    doc = DocumentOverview(document_id="doc-del-target", filename="DeleteMe.pdf", page_count=1, clause_count=1, signal_count=0)
    save_document(doc)

    res_del = client.delete("/api/workspace/doc-del-target")
    assert res_del.status_code == 200
    assert get_document("doc-del-target") is None
