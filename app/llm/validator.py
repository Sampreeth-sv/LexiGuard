"""
Citation validator and grounding status calculator for LexiGuard.
Validates that LLM-generated citations reference real clauses from the document.
Provides structured grounding status: STRONGLY GROUNDED → INSUFFICIENT EVIDENCE.

Supported citation formats (all case-insensitive):
  [Section 3.2, Page 4]          — numeric section with page
  [Section General, Page 1]      — text-based section name with page
  [Section Compensation]         — text-based section name, no page
  [Sec. IV]                      — roman-numeral section abbreviation
  [Section 2.1]                  — numeric section, no page
"""
import re
from typing import List, Tuple, Optional
from app.models.schemas import Clause, QAResponse, GroundingStatus, ClaimEvidence

# Captures both numeric (3.2, IV) and text-based (General, Compensation) section names.
# Group 1: section identifier (alphanumeric words, dots, hyphens)
# Group 2: optional page number
SECTION_CITATION_PATTERN = re.compile(
    r'\[(?:Section|Sec\.?)\s+'
    r'(.*?)(?:,\s*[Pp]age?\s*(\d+))?\s*\]',
    re.IGNORECASE
)

ABSTENTION_PHRASES = [
    "couldn't find sufficient evidence",
    "insufficient evidence",
    "not mentioned in",
    "unable to locate",
    "cannot find",
    "not found in the document",
    "no information about",
    "does not appear in",
    "not addressed in",
    # Phrases produced when LLM acknowledges an explicitly nonexistent section/page
    "does not exist in",
    "not present in the document",
    "not found in the uploaded",
    "no such section",
]


def extract_citations_from_text(text: str) -> List[Tuple[str, Optional[int]]]:
    """
    Extract (section_ref, page_num) tuples from LLM output text.
    Supports both numeric IDs (3.2, IV) and text-based names (General, Compensation).
    """
    results = []
    seen = set()

    for match in SECTION_CITATION_PATTERN.findall(text):
        sec = match[0].strip()
        page = int(match[1]) if match[1] else None
        key = (sec.lower(), page)
        if sec and key not in seen:
            seen.add(key)
            results.append((sec, page))

    return results


def _clause_matches_citation(clause: Clause, sec_ref: str, page: Optional[int]) -> bool:
    """
    Check if a clause matches a section reference and optional page number.
    """
    section_path = clause.metadata.section_path or ''
    section_id = clause.metadata.section_id or ''
    heading = clause.metadata.heading or ''

    # Normalize everything to lowercase, strip whitespace
    sec_ref_norm = sec_ref.lower().strip()
    path_norm = section_path.lower().strip()
    id_norm = section_id.lower().strip()
    heading_norm = heading.lower().strip()

    path_match = (
        sec_ref_norm in path_norm          # "general" ⊆ "general terms"
        or path_norm in sec_ref_norm       # "general terms" ⊆ "general terms and conditions"
        or id_norm == sec_ref_norm         # exact section_id match
        or sec_ref_norm in id_norm         # "3.2" ⊆ "3.2.1"
        or sec_ref_norm in heading_norm    # text name matches heading
    )

    if not path_match:
        return False

    if page is not None:
        return clause.metadata.page == page
    return True


def validate_citations(
    text: str,
    available_clauses: List[Clause],
) -> Tuple[str, List[ClaimEvidence], GroundingStatus]:
    """
    Validate that citations in LLM output text refer to real clauses in the document.

    Returns:
        cleaned_text: text with invalid citations flagged with (INVALID REFERENCE)
        valid_evidences: list of ClaimEvidence for valid citations
        grounding_status: GroundingStatus enum value
    """
    citations = extract_citations_from_text(text)
    valid_evidences: List[ClaimEvidence] = []
    invalid_count = 0
    cleaned_text = text

    if not citations:
        return cleaned_text, [], GroundingStatus.INSUFFICIENT_EVIDENCE

    for sec, page in citations:
        matched_clause = None
        for clause in available_clauses:
            if _clause_matches_citation(clause, sec, page):
                matched_clause = clause
                break

        if matched_clause:
            valid_evidences.append(ClaimEvidence(
                clause_id=matched_clause.id,
                document_id=matched_clause.metadata.document_id,
                document_filename=getattr(matched_clause.metadata, 'document_filename', None),
                section_path=matched_clause.metadata.section_path,
                page=matched_clause.metadata.page,
                quoted_text=matched_clause.text[:200],
            ))
        else:
            invalid_count += 1
            # Flag invalid citation in text
            page_suffix = f", Page {page}" if page else ""
            cit_pattern = re.compile(
                rf'\[(?:Section\s*)?{re.escape(sec)}{re.escape(page_suffix)}?\]',
                re.IGNORECASE
            )
            cleaned_text = cit_pattern.sub(f"[Section {sec}{page_suffix}] (UNVERIFIED REFERENCE)", cleaned_text)

    total = len(citations)
    valid_count = total - invalid_count

    if invalid_count == total:
        status = GroundingStatus.INSUFFICIENT_EVIDENCE
    elif invalid_count > 0:
        status = GroundingStatus.LIMITED_EVIDENCE
    elif valid_count >= 2:
        status = GroundingStatus.STRONGLY_GROUNDED
    else:
        status = GroundingStatus.SUPPORTED

    total = len(citations)
    valid_count = total - invalid_count

    if invalid_count == total:
        status = GroundingStatus.INSUFFICIENT_EVIDENCE
    elif invalid_count > 0:
        status = GroundingStatus.LIMITED_EVIDENCE
    elif valid_count >= 2:
        status = GroundingStatus.STRONGLY_GROUNDED
    else:
        status = GroundingStatus.SUPPORTED

    return cleaned_text, valid_evidences, status


import json

def _strip_metadata_headers(text: str) -> str:
    """Strip metadata labels such as 'Evidence Citations:', 'Grounding Status:', 'Suggested Follow-up:' from answer text."""
    patterns = [
        r'(?i)\n?\s*Evidence Citations:.*$',
        r'(?i)\n?\s*Grounding Status:.*$',
        r'(?i)\n?\s*Suggested Follow-up:.*$',
        r'(?i)^\s*Answer:\s*',
    ]
    cleaned = text
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.DOTALL | re.MULTILINE)
    return cleaned.strip()


def parse_qa_response(
    raw_response: str,
    available_clauses: List[Clause],
    question: str,
) -> QAResponse:
    """
    Parse an LLM Q&A response into a structured QAResponse.
    Supports structured JSON responses and legacy text responses with citation validation.

    Args:
        raw_response: Raw text output or JSON string from the LLM.
        available_clauses: Clauses available in the document for citation validation.
        question: Original user question (for context).

    Returns:
        QAResponse with validated citations and grounding status.
    """
    if not raw_response or not raw_response.strip():
        return QAResponse(
            answer="I couldn't find sufficient evidence in the uploaded document to answer this reliably.",
            evidences=[],
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
        )

    answer_text = raw_response
    suggested_followup = None
    structured_json = None

    # Attempt to parse as JSON
    trimmed = raw_response.strip()
    if trimmed.startswith('{') and trimmed.endswith('}'):
        try:
            structured_json = json.loads(trimmed)
        except Exception:
            pass

    if not structured_json:
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            try:
                structured_json = json.loads(json_match.group(1))
            except Exception:
                pass

    if structured_json and isinstance(structured_json, dict):
        answer_text = structured_json.get("answer_text") or structured_json.get("answer") or raw_response
        suggested_followup = structured_json.get("suggested_follow_up") or structured_json.get("suggested_followup")

        ev_list = structured_json.get("evidence_list") or []
        if isinstance(ev_list, list) and ev_list:
            cit_strings = []
            for ev in ev_list:
                if isinstance(ev, dict):
                    sec = ev.get("section") or ""
                    pg = ev.get("page")
                    if sec and pg:
                        cit_strings.append(f"[Section {sec}, Page {pg}]")
                    elif sec:
                        cit_strings.append(f"[Section {sec}]")
            if cit_strings and not SECTION_CITATION_PATTERN.search(str(answer_text)):
                answer_text = str(answer_text) + " " + " ".join(cit_strings)

    clean_answer = _strip_metadata_headers(str(answer_text))

    response_lower = raw_response.lower()
    abstained = any(phrase in response_lower for phrase in ABSTENTION_PHRASES)

    cleaned_text, evidences, grounding = validate_citations(clean_answer, available_clauses)

    if abstained:
        grounding = GroundingStatus.INSUFFICIENT_EVIDENCE

    if not suggested_followup:
        followup_match = re.search(
            r'(?:Suggested Follow-up|Follow-up question|Consider asking)[:\s]+(.+?)(?:\n|$)',
            raw_response,
            re.IGNORECASE
        )
        if followup_match:
            suggested_followup = followup_match.group(1).strip()

    return QAResponse(
        answer=cleaned_text,
        evidences=evidences,
        grounding_status=grounding,
        suggested_followup=suggested_followup,
        abstained=abstained,
    )

