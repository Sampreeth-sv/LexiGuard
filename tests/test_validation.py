"""
Citation validation and grounding status tests.
Tests the validator's ability to extract citations, match them to clauses,
and compute accurate grounding status.
"""
import pytest
from app.llm.validator import extract_citations_from_text, validate_citations, parse_qa_response
from app.models.schemas import Clause, ClauseMetadata, GroundingStatus
import uuid


def make_clause(section_id: str, section_path: str = None, page: int = 1, heading: str = None) -> Clause:
    cid = str(uuid.uuid4())
    return Clause(
        id=cid,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id="doc1",
            section_id=section_id,
            heading=heading or "Test Heading",
            section_path=section_path or f"Section {section_id}",
            page=page,
            clause_type="general",
            char_count=50,
        ),
        text=f"This is the text of section {section_id} on page {page}.",
    )


# ── Citation Extraction ───────────────────────────────────────────────────────

def test_extract_citations_section_only():
    citations = extract_citations_from_text("Based on [Section 3.2], the answer is clear.")
    assert len(citations) > 0
    section_refs = [c[0] for c in citations]
    assert "3.2" in section_refs


def test_extract_citations_with_page():
    citations = extract_citations_from_text("See [Section 3.2, Page 4] for details.")
    assert len(citations) > 0
    assert citations[0] == ("3.2", 4)


def test_extract_citations_multiple():
    text = "As per [Section 2.1] and [Section 3.2, Page 5], the obligations are clear."
    citations = extract_citations_from_text(text)
    assert len(citations) >= 2


def test_extract_citations_no_citations():
    citations = extract_citations_from_text("There are no citations in this text.")
    assert citations == []


def test_extract_citations_text_based_section_name():
    """REGRESSION: LLM cites [Section General, Page 1] for DOCX docs with no numeric IDs."""
    citations = extract_citations_from_text(
        "The probation period is six months [Section General, Page 1]."
    )
    assert len(citations) == 1
    assert citations[0][0].strip() == "General"
    assert citations[0][1] == 1


def test_extract_citations_text_section_compensation():
    """REGRESSION: Text-based section name 'Compensation' is extracted correctly."""
    citations = extract_citations_from_text(
        "Annual salary is ₹8,00,000 [Section Compensation, Page 2]."
    )
    assert len(citations) == 1
    assert "Compensation" in citations[0][0]
    assert citations[0][1] == 2


def test_extract_citations_text_section_no_page():
    """Text-based section name without page number is extracted."""
    citations = extract_citations_from_text(
        "See [Section Employment Terms] for the definition."
    )
    assert len(citations) == 1
    assert "Employment Terms" in citations[0][0]
    assert citations[0][1] is None


# ── Citation Validation ───────────────────────────────────────────────────────

def test_validate_citations_valid_match():
    clause = make_clause("3.2", section_path="Section 3.2", page=4)
    text = "Based on [Section 3.2], the automatic renewal applies."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert status in [GroundingStatus.STRONGLY_GROUNDED, GroundingStatus.SUPPORTED]
    assert len(evidences) >= 1


def test_validate_citations_invalid_reference():
    clause = make_clause("3.2", section_path="Section 3.2")
    text = "Based on [Section 9.9], something happens."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert status in [GroundingStatus.LIMITED_EVIDENCE, GroundingStatus.INSUFFICIENT_EVIDENCE]


def test_validate_citations_no_citations_in_text():
    clause = make_clause("3.2")
    text = "The agreement requires written notice."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert status == GroundingStatus.INSUFFICIENT_EVIDENCE
    assert evidences == []


def test_validate_citations_multiple_valid():
    clause_a = make_clause("2.1", section_path="Section 2.1")
    clause_b = make_clause("3.2", section_path="Section 3.2")
    text = "Per [Section 2.1] and [Section 3.2], both obligations apply."
    cleaned, evidences, status = validate_citations(text, [clause_a, clause_b])
    assert status == GroundingStatus.STRONGLY_GROUNDED
    assert len(evidences) == 2


def test_validate_citations_text_section_matches_clause():
    """REGRESSION: [Section General, Page 1] must match a clause with section_path='General'."""
    clause = make_clause("general", section_path="General", page=1)
    text = "The probation period is six months [Section General, Page 1]."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert status in [GroundingStatus.STRONGLY_GROUNDED, GroundingStatus.SUPPORTED], (
        f"Expected STRONGLY GROUNDED or SUPPORTED, got {status}. "
        f"Evidences: {evidences}"
    )
    assert len(evidences) == 1
    assert evidences[0].section_path == "General"


def test_validate_citations_text_section_compensation_matches():
    """REGRESSION: [Section Compensation, Page 2] must match a clause with section_path='Compensation'."""
    clause = make_clause("compensation", section_path="Compensation", page=2)
    text = "Annual salary is ₹8,00,000 [Section Compensation, Page 2]."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert len(evidences) == 1
    assert status in [GroundingStatus.STRONGLY_GROUNDED, GroundingStatus.SUPPORTED]


def test_validate_citations_unrelated_section_does_not_match():
    """[Section General] must NOT match a clause whose section_path is 'Compensation'."""
    clause = make_clause("compensation", section_path="Compensation", page=1)
    text = "See [Section General, Page 1] for details."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert len(evidences) == 0, (
        "Citation 'General' must not match a clause with section_path='Compensation'"
    )
    assert status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_validate_citations_page_mismatch_not_matched():
    """[Section General, Page 3] must NOT match a General clause on page 1 (page enforcement)."""
    clause = make_clause("general", section_path="General", page=1)
    text = "See [Section General, Page 3]."
    cleaned, evidences, status = validate_citations(text, [clause])
    assert len(evidences) == 0, (
        "Page mismatch must prevent the citation from being validated"
    )


def test_validate_citations_text_section_two_clauses_strongly_grounded():
    """Two text-based citations that both resolve → STRONGLY GROUNDED."""
    clause_a = make_clause("general", section_path="General", page=1)
    clause_b = make_clause("compensation", section_path="Compensation", page=2)
    text = (
        "The probation period is 6 months [Section General, Page 1]. "
        "The annual salary is ₹8,00,000 [Section Compensation, Page 2]."
    )
    cleaned, evidences, status = validate_citations(text, [clause_a, clause_b])
    assert status == GroundingStatus.STRONGLY_GROUNDED
    assert len(evidences) == 2


# ── Parse QA Response ─────────────────────────────────────────────────────────

def test_parse_qa_response_abstention_detected():
    response = "I couldn't find sufficient evidence in the uploaded document to answer this reliably."
    result = parse_qa_response(response, [], "What is the payment term?")
    assert result.abstained is True
    assert result.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_parse_qa_response_normal():
    clause = make_clause("3.2", section_path="Section 3.2")
    response = "The renewal clause [Section 3.2] states that the agreement automatically renews."
    result = parse_qa_response(response, [clause], "Does this auto-renew?")
    assert result is not None
    assert result.answer is not None
    assert result.grounding_status is not None


def test_parse_qa_response_returns_qa_response_type():
    from app.models.schemas import QAResponse
    response = "The payment is due within 30 days."
    result = parse_qa_response(response, [], "When is payment due?")
    assert isinstance(result, QAResponse)


def test_parse_qa_response_text_section_grounded():
    """REGRESSION: LLM response with [Section General, Page 1] → grounded if clause matches."""
    clause = make_clause("general", section_path="General", page=1)
    response = (
        "Answer: The probation period is six months [Section General, Page 1].\n"
        "Grounding Status: STRONGLY GROUNDED"
    )
    result = parse_qa_response(response, [clause], "What is the probation period?")
    assert result.grounding_status in [GroundingStatus.STRONGLY_GROUNDED, GroundingStatus.SUPPORTED]
    assert len(result.evidences) == 1


# ── Frontend Grounding CSS Map (unit-level contract test) ─────────────────────

def test_grounding_css_map_covers_all_statuses():
    """Every GroundingStatus enum value must map to a CSS class in the frontend GROUNDING_CSS map."""
    # This mirrors the frontend JS constant — kept in sync manually.
    GROUNDING_CSS = {
        'STRONGLY GROUNDED':    'grounding-strong',
        'SUPPORTED':            'grounding-supported',
        'LIMITED EVIDENCE':     'grounding-limited',
        'INSUFFICIENT EVIDENCE':'grounding-insufficient-evidence',
    }
    for status in GroundingStatus:
        assert status.value in GROUNDING_CSS, (
            f"GroundingStatus.{status.name} ('{status.value}') has no CSS class mapping. "
            f"Add it to app.js GROUNDING_CSS and styles.css."
        )


# ── ABSTENTION_PHRASES regression (secondary defence) ─────────────────────────

def test_abstention_phrase_does_not_exist_in():
    """REGRESSION: 'does not exist in the uploaded document' → abstained=True."""
    response = "Section 999, Page 999 does not exist in the uploaded document."
    result = parse_qa_response(response, [], "According to Section 999, what is the salary?")
    assert result.abstained is True, (
        "'does not exist in' must trigger abstention"
    )
    assert result.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_abstention_phrase_not_present_in_the_document():
    """REGRESSION: 'not present in the document' → abstained=True."""
    response = "The referenced section is not present in the document."
    result = parse_qa_response(response, [], "What does Section 999 say?")
    assert result.abstained is True
    assert result.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_abstention_phrase_not_found_in_the_uploaded():
    """REGRESSION: 'not found in the uploaded document/file' → abstained=True."""
    response = "Section 999 is not found in the uploaded document."
    result = parse_qa_response(response, [], "What does Section 999 say?")
    assert result.abstained is True
    assert result.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_abstention_phrase_no_such_section():
    """REGRESSION: 'no such section exists' → abstained=True."""
    response = "No such section exists in this document."
    result = parse_qa_response(response, [], "What does Section 999 say?")
    assert result.abstained is True
    assert result.grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE


def test_abstention_phrase_not_false_positive_on_normal_clause_text():
    """
    Guard: 'this clause does not apply' must NOT trigger false abstention.
    Ensures none of the new phrases match on incidental occurrences.
    """
    clause = make_clause("3.2", section_path="Section 3.2", page=1)
    # This text discusses something not existing but in a benign clause context
    response = (
        "The renewal clause [Section 3.2] states that automatic renewal applies. "
        "A termination penalty does not apply in this case."
    )
    result = parse_qa_response(response, [clause], "Does a penalty apply?")
    # "does not apply" should not match any abstention phrase
    assert result.abstained is False, (
        "'does not apply' must not match abstention phrases and cause false abstention"
    )


def test_parse_qa_response_structured_json():
    clause = make_clause("3.2", section_path="Section 3.2", page=1)
    json_response = """{
      "answer_text": "The salary is USD 100,000 per year [Section 3.2, Page 1].",
      "evidence_list": [{"section": "3.2", "page": 1, "quote": "Salary is USD 100,000"}],
      "grounding_status": "STRONGLY GROUNDED",
      "suggested_follow_up": "Is bonus guaranteed?"
    }"""
    result = parse_qa_response(json_response, [clause], "What is the salary?")
    assert "Evidence Citations:" not in result.answer
    assert "Grounding Status:" not in result.answer
    assert "USD 100,000" in result.answer
    assert result.suggested_followup == "Is bonus guaranteed?"
    assert len(result.evidences) == 1


def test_parse_qa_response_malformed_json_fallback():
    clause = make_clause("3.2", section_path="Section 3.2", page=1)
    malformed_response = "{ invalid json structure [Section 3.2, Page 1] }"
    result = parse_qa_response(malformed_response, [clause], "What is the salary?")
    assert result is not None
    assert isinstance(result.answer, str)

