"""
Regression tests for the pre-retrieval explicit section/page constraint check.

Tests cover:
  - Constraint extraction from bracket and prose formats
  - Constraint satisfaction checking against real clauses
  - API-level behaviour: nonexistent section → INSUFFICIENT_EVIDENCE, no LLM call
  - API-level behaviour: existing section → normal answer pipeline
  - API-level behaviour: normal unconstrained question → unaffected
  - No false positives on incidental section mentions
"""
import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.api.questions import (
    _extract_question_constraints,
    _constraint_satisfied,
    _format_constraint,
)
from app.models.schemas import Clause, ClauseMetadata, GroundingStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_clause(section_id: str, section_path: str, page: int = 1, heading: str = "") -> Clause:
    cid = str(uuid.uuid4())
    return Clause(
        id=cid,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id="test-doc",
            section_id=section_id,
            heading=heading or section_path,
            section_path=section_path,
            page=page,
            clause_type="general",
            char_count=80,
        ),
        text=f"Content of {section_path} on page {page}.",
    )


SAMPLE_CLAUSES = [
    make_clause("2", "Section 2", page=1, heading="Compensation"),
    make_clause("3", "Section 3", page=1, heading="General Terms"),
    make_clause("general", "General", page=1),
]

UPLOAD_URL = "/api/documents/"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def upload_doc(client, content: bytes = None, filename: str = "doc.txt") -> str:
    if content is None:
        content = (
            b"ARTICLE I - COMPENSATION\n\n"
            b"Section 2. The employee's annual salary shall be 800000 INR.\n\n"
            b"ARTICLE II - GENERAL TERMS\n\n"
            b"Section 3. The probation period shall be six months.\n"
        )
    res = client.post(UPLOAD_URL, files={"file": (filename, content, "text/plain")})
    assert res.status_code == 200, f"Upload failed: {res.text}"
    return res.json()["document_id"]


# ── Unit: _extract_question_constraints ──────────────────────────────────────

class TestExtractQuestionConstraints:

    def test_no_constraint_normal_question(self):
        """Normal semantic question must return no constraints."""
        constraints = _extract_question_constraints("What is the employee's salary?")
        assert constraints == [], f"Expected no constraints, got {constraints}"

    def test_no_constraint_incidental_section_mention(self):
        """Incidental section mention without citation-intent preposition must not be a constraint."""
        constraints = _extract_question_constraints(
            "The salary is described somewhere in section 2 of the document."
        )
        assert constraints == [], (
            "Incidental 'in section 2' mention should not produce a constraint"
        )

    def test_bracket_numeric_constraint(self):
        """[Section 999, Page 999] in question → extracted as constraint."""
        q = "What does [Section 999, Page 999] say about the salary?"
        constraints = _extract_question_constraints(q)
        assert len(constraints) == 1
        sec, page = constraints[0]
        assert "999" in sec
        assert page == 999

    def test_bracket_text_constraint(self):
        """[Section General, Page 1] → extracted as constraint."""
        q = "According to [Section General, Page 1], what is the policy?"
        constraints = _extract_question_constraints(q)
        assert any("general" in s.lower() for s, p in constraints)

    def test_prose_according_to_numeric(self):
        """'According to Section 999, Page 999' → constraint extracted."""
        q = "According to Section 999, Page 999, what is the salary?"
        constraints = _extract_question_constraints(q)
        assert len(constraints) >= 1
        sec, page = constraints[0]
        assert "999" in sec
        assert page == 999

    def test_prose_according_to_text_section(self):
        """'According to Section General, Page 1' → text-based constraint extracted."""
        q = "According to Section General, Page 1, what are the terms?"
        constraints = _extract_question_constraints(q)
        assert len(constraints) >= 1
        sec, page = constraints[0]
        assert "general" in sec.lower()
        assert page == 1

    def test_prose_per_section(self):
        """'Per Section 3.2' → constraint extracted."""
        q = "Per Section 3.2, what are the renewal terms?"
        constraints = _extract_question_constraints(q)
        assert len(constraints) >= 1
        assert "3.2" in constraints[0][0]

    def test_prose_under_section_no_page(self):
        """'Under Section 5' without page → constraint with page=None."""
        q = "Under Section 5, what are the confidentiality obligations?"
        constraints = _extract_question_constraints(q)
        assert len(constraints) >= 1
        sec, page = constraints[0]
        assert "5" in sec
        assert page is None

    def test_deduplication(self):
        """Same constraint from bracket and prose forms must not be duplicated."""
        q = "According to Section 2, Page 1, and also [Section 2, Page 1], what is the fee?"
        constraints = _extract_question_constraints(q)
        keys = [(s.lower().strip(), p) for s, p in constraints]
        assert len(keys) == len(set(keys)), "Duplicate constraints should be deduplicated"


# ── Unit: _constraint_satisfied ───────────────────────────────────────────────

class TestConstraintSatisfied:

    def test_existing_numeric_section_satisfied(self):
        """Section 2, Page 1 exists in SAMPLE_CLAUSES → satisfied."""
        assert _constraint_satisfied("2", 1, SAMPLE_CLAUSES) is True

    def test_existing_text_section_satisfied(self):
        """Section 'General', Page 1 exists in SAMPLE_CLAUSES → satisfied."""
        assert _constraint_satisfied("General", 1, SAMPLE_CLAUSES) is True

    def test_nonexistent_section_not_satisfied(self):
        """Section 999 does not exist → not satisfied."""
        assert _constraint_satisfied("999", 999, SAMPLE_CLAUSES) is False

    def test_page_mismatch_not_satisfied(self):
        """Section 2 exists but not on Page 99 → not satisfied."""
        assert _constraint_satisfied("2", 99, SAMPLE_CLAUSES) is False

    def test_unrelated_section_not_satisfied(self):
        """'Section 999' must not be satisfied by the 'General' clause."""
        general_only = [make_clause("general", "General", page=1)]
        assert _constraint_satisfied("999", 999, general_only) is False

    def test_empty_clauses_not_satisfied(self):
        """No clauses → constraint cannot be satisfied."""
        assert _constraint_satisfied("2", 1, []) is False


# ── Unit: _format_constraint ──────────────────────────────────────────────────

def test_format_constraint_with_page():
    assert _format_constraint("999", 999) == "Section 999, Page 999"

def test_format_constraint_no_page():
    assert _format_constraint("General", None) == "Section General"


# ── API integration: nonexistent section constraint ───────────────────────────

class TestConstraintCheckAPI:

    def test_nonexistent_section_returns_insufficient_evidence(self, client):
        """
        REGRESSION: 'According to Section 999, Page 999, what is the salary?'
        → grounding_status = INSUFFICIENT_EVIDENCE, abstained = True.
        Gemini must NOT be called (determined by FallbackProvider being used in tests).
        """
        doc_id = upload_doc(client)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "According to Section 999, Page 999, what is the salary?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["grounding_status"] == GroundingStatus.INSUFFICIENT_EVIDENCE.value, (
            f"Expected INSUFFICIENT_EVIDENCE, got {data['grounding_status']}"
        )
        assert data["abstained"] is True
        assert "999" in data["answer"] or "does not exist" in data["answer"].lower(), (
            "Answer should reference the nonexistent section"
        )
        assert data["evidences"] == [], "No evidence should be returned for nonexistent section"

    def test_nonexistent_section_answer_does_not_mention_other_sections(self, client):
        """
        REGRESSION: Nonexistent section constraint must NOT produce an answer
        derived from another section (e.g. Section 2's salary data).
        """
        doc_id = upload_doc(client)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "According to Section 999, Page 999, what is the salary?"},
        )
        data = res.json()
        # The answer must not contain a derived salary figure from Section 2
        # It should only say the section doesn't exist
        assert "800000" not in data["answer"]
        assert "8,00,000" not in data["answer"]
        assert data["abstained"] is True

    def test_bracket_nonexistent_section_also_triggers_abstention(self, client):
        """[Section 999, Page 999] bracket format also triggers constraint check."""
        doc_id = upload_doc(client)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "What does [Section 999, Page 999] say about salary?"},
        )
        data = res.json()
        assert data["grounding_status"] == GroundingStatus.INSUFFICIENT_EVIDENCE.value
        assert data["abstained"] is True

    def test_nonexistent_section_suggested_followup_present(self, client):
        """Abstention response for nonexistent section must include a suggested followup."""
        doc_id = upload_doc(client)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "According to Section 999, Page 999, what is the salary?"},
        )
        data = res.json()
        assert data.get("suggested_followup") is not None, (
            "Abstention for nonexistent section should suggest rephrasing"
        )

    def test_normal_unconstrained_question_proceeds(self, client):
        """
        REGRESSION GUARD: Normal question 'What is the salary?' must NOT be blocked.
        It has no section constraint → retrieval proceeds normally.
        """
        doc_id = upload_doc(client)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "What is the salary?"},
        )
        assert res.status_code == 200
        data = res.json()
        # The fallback provider is used in tests (no API key), so answer is generic
        # but the request must succeed and NOT be wrongly blocked by constraint check
        assert "answer" in data
        assert "grounding_status" in data
        # Crucially, this should NOT be a nonexistent-section abstention
        # (it may still abstain via fallback/retrieval, but not due to constraint check)
        if data["abstained"]:
            assert "does not exist" not in data["answer"].lower() or \
                   "999" not in data["answer"], (
                "Normal question must not be blocked by the section constraint check"
            )

    def test_existing_section_constraint_proceeds(self, client, sample_txt_bytes):
        """
        'According to Section 3.2, what are the renewal terms?' — Section 3.2 exists
        in the sample contract → constraint passes, pipeline proceeds normally.
        Result is NOT blocked by the constraint check.
        """
        doc_id = upload_doc(client, sample_txt_bytes)
        res = client.post(
            f"/api/documents/{doc_id}/ask",
            json={"question": "According to Section 3.2, what are the renewal terms?"},
        )
        assert res.status_code == 200
        data = res.json()
        # Must not be a constraint-check abstention (answer would reference "does not exist")
        assert "does not exist in the uploaded document" not in data["answer"], (
            "Existing section 3.2 should not be blocked by constraint check"
        )
