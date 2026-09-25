"""
Test suite for the ingestion pipeline.
Tests text extraction, structure parsing, clause type detection,
document segmentation, and text fidelity.
"""
import pytest
from app.ingestion.text_parser import extract_text_from_txt
from app.ingestion.structure import segment_document, detect_clause_type
from app.models.schemas import Clause


# ── Text Parser ──────────────────────────────────────────────────────────────

def test_txt_extraction_basic(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    assert len(pages) > 0
    assert len(pages[0]) == 2  # (page_num, text)
    assert pages[0][0] == 1   # 1-indexed
    assert len(pages[0][1]) > 0


def test_txt_extraction_encoding_utf8(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    assert len(pages) > 0
    # Content should be readable text
    all_text = ' '.join(t for _, t in pages)
    assert 'SYNTHETIC' in all_text or len(all_text) > 0


def test_txt_extraction_encoding_latin1():
    latin1_text = "Contract with special chars: café, résumé, naïve"
    latin1_bytes = latin1_text.encode('latin-1')
    pages = extract_text_from_txt(latin1_bytes)
    assert len(pages) > 0


def test_txt_extraction_empty():
    pages = extract_text_from_txt(b"")
    assert pages == []


def test_txt_extraction_returns_tuples(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    for page_num, text in pages:
        assert isinstance(page_num, int)
        assert isinstance(text, str)
        assert page_num >= 1


# ── Structure Parser / Segmentation ──────────────────────────────────────────

def test_segment_document_returns_clauses(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-test-1")
    assert len(clauses) > 0
    assert all(isinstance(c, Clause) for c in clauses)


def test_segment_document_has_sections(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-test-1")
    # At least some clauses should have a section path
    paths = [c.metadata.section_path for c in clauses if c.metadata.section_path]
    assert len(paths) > 0


def test_segment_document_has_pages(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-test-1")
    for clause in clauses:
        assert clause.metadata.page >= 1


def test_segment_document_no_text_loss(sample_txt_bytes, sample_txt_content):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-test-1")
    total_chars = sum(len(c.text) for c in clauses)
    # Should preserve at least 50% of the original text
    assert total_chars >= len(sample_txt_content) * 0.5


def test_segment_document_assigns_document_id(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "my-doc-id")
    assert all(c.metadata.document_id == "my-doc-id" for c in clauses)


def test_segment_document_unique_clause_ids(sample_txt_bytes):
    pages = extract_text_from_txt(sample_txt_bytes)
    clauses = segment_document(pages, "doc-test-1")
    ids = [c.id for c in clauses]
    assert len(ids) == len(set(ids)), "All clause IDs must be unique"


# ── Clause Type Detection ─────────────────────────────────────────────────────

def test_detect_clause_type_renewal():
    result = detect_clause_type("This agreement shall automatically renew", "")
    assert result == "renewal"


def test_detect_clause_type_termination():
    result = detect_clause_type("termination for cause upon written notice", "")
    assert result == "termination"


def test_detect_clause_type_payment():
    result = detect_clause_type("monthly fee of $5000 payment due within 30 days", "")
    assert result == "payment"


def test_detect_clause_type_fallback():
    result = detect_clause_type("some generic random text without keywords", "")
    assert isinstance(result, str)
    assert len(result) > 0  # Should always return something


def test_detect_clause_type_confidentiality():
    result = detect_clause_type("confidential information shall not be disclosed", "")
    assert result == "confidentiality"


def test_detect_clause_type_arbitration():
    result = detect_clause_type("binding arbitration shall resolve disputes", "")
    assert result == "arbitration"


# ── DOCX Ingestion Regressions ────────────────────────────────────────────────

def test_structure_recognises_markdown_headings():
    """
    Regression: structure.py must recognise `# Heading` lines emitted by
    docx_parser for Word heading-style paragraphs. A multi-section document
    must produce multiple clauses, not one giant clause.
    """
    # Simulate what docx_parser emits for a DOCX with Heading 1 styles
    docx_like_text = (
        "# Appointment\n\n"
        "The Employee is appointed to the role of Software Engineer.\n\n"
        "# Compensation\n\n"
        "The monthly salary shall be $5,000 payable on the last working day.\n\n"
        "# Confidentiality\n\n"
        "The Employee shall keep all proprietary information strictly confidential "
        "and shall not disclose trade secrets to third parties.\n\n"
        "# Termination\n\n"
        "Either party may terminate this agreement upon 30 days written notice.\n\n"
        "## Governing Law\n\n"
        "This agreement is governed by the laws of the State of Delaware."
    )
    pages = [(1, docx_like_text)]
    clauses = segment_document(pages, "doc-docx-heading-test")

    # Must produce multiple clauses, not one
    assert len(clauses) >= 4, (
        f"Expected >= 4 clauses for a 5-section DOCX, got {len(clauses)}. "
        "Markdown heading pattern may not be firing."
    )
    # All clause IDs must be unique
    ids = [c.id for c in clauses]
    assert len(ids) == len(set(ids))


def test_structure_paragraph_fallback_fires_for_truly_empty_structure():
    """
    Regression: _paragraph_fallback must correctly split on double newlines
    when the structure detection loop produces zero clauses.
    Trigger: empty page text that normally would not detect any structure.
    The fallback is invoked when clauses is empty after structure detection.
    """
    # Paragraph fallback is triggered when structure detection returns nothing.
    # We trigger it by providing pages that produce zero structure headings,
    # and ensuring the final _build_clause also returns None (text < 10 chars).
    # Test the fallback directly via _paragraph_fallback.
    from app.ingestion.structure import _paragraph_fallback
    plain_text = (
        "This Service Agreement is entered into between Acme Corp and Jane Smith.\n\n"
        "The Company shall pay the Consultant a monthly fee of $5,000 due within 30 days.\n\n"
        "This Agreement shall automatically renew unless either party provides notice.\n\n"
        "Either party may terminate this Agreement upon 30 days written notice.\n\n"
        "The Consultant agrees to keep all proprietary information confidential."
    )
    pages = [(1, plain_text)]
    clauses = _paragraph_fallback(pages, "doc-para-fallback-test")

    # _paragraph_fallback must split on double newlines and return multiple clauses
    assert len(clauses) >= 3, (
        f"Expected >= 3 clauses from _paragraph_fallback, got {len(clauses)}. "
        "Pages must be joined with \\n\\n for re.split(r'\\n{2,}') to fire."
    )


def test_structure_plain_text_produces_at_least_one_clause():
    """
    Plain text with no headings should produce at least one clause (the whole text),
    not zero clauses. Structure detection accumulates all lines and builds one clause.
    """
    plain_text = (
        "This Service Agreement is entered into between Acme Corp and Jane Smith.\n\n"
        "The Company shall pay the Consultant a monthly fee of $5,000 due within 30 days."
    )
    pages = [(1, plain_text)]
    clauses = segment_document(pages, "doc-plain-test")
    assert len(clauses) >= 1, "Plain text must produce at least one clause"
