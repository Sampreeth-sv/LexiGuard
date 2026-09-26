"""
Structure-aware document parser for LexiGuard.
Detects hierarchical sections (Articles, Sections, numbered clauses) using regex.
Falls back to paragraph segmentation when structure cannot be detected.
Zero LLM calls.
"""
import re
from typing import List, Tuple
from app.models.schemas import Clause, ClauseMetadata
import uuid
import logging

logger = logging.getLogger(__name__)

# Article patterns: ARTICLE I, ARTICLE 1, Article I - PARTIES
ARTICLE_PATTERN = re.compile(
    r'^(?:ARTICLE|Article)\s+([IVXLCDM]+|\d+)\.?\s*[-—]?\s*(.*)$'
)

# Section patterns: Section 1.2, Section 1.2 Heading
SECTION_PATTERN = re.compile(
    r'^(?:Section|SECTION|SEC\.|Sec\.)\s*(\d+(?:\.\d+)*)\.?\s*(.*)$'
)

# Numbered patterns: 1.1 Title or 1.1.2 Title
NUMBERED_PATTERN = re.compile(
    r'^(\d+(?:\.\d+){1,3})\.?\s+([A-Z][^\n]{0,80})$'
)

# ALL CAPS HEADINGS (at least 4 chars, no lowercase)
CAPS_HEADING_PATTERN = re.compile(
    r'^([A-Z][A-Z\s\-]{3,60})$'
)

# Markdown headings: # Heading or ## Heading (emitted by docx_parser for Word heading styles)
MARKDOWN_HEADING_PATTERN = re.compile(
    r'^(#{1,6})\s+(.+)$'
)

CLAUSE_TYPE_KEYWORDS = [
    ('termination', ('terminat', 'cancel', 'exit the agreement')),
    ('renewal', ('renew', 'auto-renew', 'evergreen')),
    ('indemnity', ('indemn', 'hold harmless')),
    ('liability', ('liabilit', 'liable', 'damages')),
    ('arbitration', ('arbitrat', 'dispute resolution')),
    ('jurisdiction', ('jurisdict', 'governing law', 'choice of law')),
    ('confidentiality', ('confidential', 'non-disclosure', 'nda', 'proprietary')),
    ('ip', ('intellectual property', 'copyright', 'work made for hire', 'assigns all rights')),
    ('payment', ('payment', 'fee', 'compensat', 'invoice', 'remunerat')),
    ('privacy', ('privacy', 'personal data', 'data protection', 'gdpr')),
    ('modification', ('modif', 'amend', 'change the terms')),
    ('warranty', ('warrant', 'representat', 'as is', 'merchantab')),
    ('non_compete', ('compete', 'solicit', 'non-competition')),
    ('notice', ('notice', 'notification', 'written notice')),
    ('obligation', ('obligat', 'responsibil', 'shall', 'must')),
    ('parties', ('parties', 'between', 'hereinafter')),
    ('definitions', ('definit', 'means', 'refers to')),
]


def detect_clause_type(text: str, heading: str) -> str:
    """
    Classify a clause into one of the predefined legal categories
    based on keyword matching in text and heading.

    Returns a string category name.
    """
    combined = f"{heading} {text}".lower()
    for cat, keywords in CLAUSE_TYPE_KEYWORDS:
        if any(k in combined for k in keywords):
            return cat
    return 'general'


def _build_clause(
    text_lines: List[str],
    article: str,
    section: str,
    heading: str,
    page_num: int,
    document_id: str,
) -> Clause | None:
    """Build a Clause object from accumulated text lines. Returns None if text is empty."""
    text = '\n'.join(text_lines).strip()
    if not text or len(text) < 10:
        return None

    path_parts = [p for p in [article, section] if p]
    section_path = ' > '.join(path_parts) if path_parts else 'General'
    section_id = section or article or 'general'
    clause_type = detect_clause_type(text, heading or '')

    clause_id = str(uuid.uuid4())
    meta = ClauseMetadata(
        clause_id=clause_id,
        document_id=document_id,
        section_id=section_id,
        heading=heading or section_path,
        section_path=section_path,
        page=page_num,
        clause_type=clause_type,
        char_count=len(text),
    )
    return Clause(id=clause_id, metadata=meta, text=text)


def build_section_hierarchy(
    pages: List[Tuple[int, str]],
    document_id: str,
) -> List[Clause]:
    """
    Parse a list of (page_num, text) tuples into a structured list of Clauses.
    Detects Articles, Sections, numbered clauses, and ALL CAPS headings.
    Falls back to paragraph segmentation when structure cannot be determined.
    Never silently loses text.
    """
    clauses: List[Clause] = []

    current_article = ''
    current_section = ''
    current_heading = ''
    current_page = 1
    current_lines: List[str] = []

    for page_num, page_text in pages:
        lines = page_text.split('\n')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            art_match = ARTICLE_PATTERN.match(stripped)
            sec_match = SECTION_PATTERN.match(stripped)
            num_match = NUMBERED_PATTERN.match(stripped)
            caps_match = CAPS_HEADING_PATTERN.match(stripped)
            md_match = MARKDOWN_HEADING_PATTERN.match(stripped)

            is_heading = False

            if art_match:
                # Save previous clause
                clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
                if clause:
                    clauses.append(clause)
                current_lines = []
                current_article = f"Article {art_match.group(1)}"
                current_heading = art_match.group(2).strip() or current_article
                current_section = ''
                current_page = page_num
                is_heading = True

            elif sec_match:
                clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
                if clause:
                    clauses.append(clause)
                current_lines = []
                current_section = f"Section {sec_match.group(1)}"
                current_heading = sec_match.group(2).strip() or current_section
                current_page = page_num
                is_heading = True

            elif num_match:
                clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
                if clause:
                    clauses.append(clause)
                current_lines = []
                current_section = f"Section {num_match.group(1)}"
                current_heading = num_match.group(2).strip()
                current_page = page_num
                is_heading = True

            elif md_match:
                # Markdown heading from docx_parser (Word heading styles -> # prefix)
                clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
                if clause:
                    clauses.append(clause)
                current_lines = []
                level = len(md_match.group(1))  # number of # chars = heading level
                heading_text = md_match.group(2).strip()
                if level == 1:
                    current_article = heading_text
                    current_section = ''
                else:
                    current_section = heading_text
                current_heading = heading_text
                current_page = page_num
                is_heading = True

            elif caps_match and len(stripped) >= 5:
                # Only treat as heading if it looks like a real heading (not ALL CAPS body text)
                clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
                if clause:
                    clauses.append(clause)
                current_lines = []
                current_heading = stripped
                current_page = page_num
                is_heading = True

            # Always accumulate the line (heading line becomes part of its own clause text)
            current_lines.append(stripped)

    # Save last accumulated clause
    clause = _build_clause(current_lines, current_article, current_section, current_heading, current_page, document_id)
    if clause:
        clauses.append(clause)

    # Fallback: if no clauses detected, use paragraph segmentation
    if not clauses:
        logger.warning("Structure detection failed, falling back to paragraph segmentation.")
        clauses = _paragraph_fallback(pages, document_id)

    return clauses


def _paragraph_fallback(pages: List[Tuple[int, str]], document_id: str) -> List[Clause]:
    """
    Fallback paragraph-level segmentation when no structure is detected.
    Splits on double newlines into paragraphs.
    Pages are joined with double newlines so the split pattern fires correctly.
    """
    clauses = []
    # Join pages with \n\n so the double-newline split below fires across page boundaries
    all_text = '\n\n'.join(text for _, text in pages)
    paragraphs = re.split(r'\n{2,}', all_text)

    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para or len(para) < 20:
            continue
        clause_id = str(uuid.uuid4())
        # Estimate page: every ~3000 chars is one page
        page_num = max(1, (sum(len(p) for p in paragraphs[:i]) // 3000) + 1)
        heading = para[:60].split('\n')[0]
        clause_type = detect_clause_type(para, heading)
        meta = ClauseMetadata(
            clause_id=clause_id,
            document_id=document_id,
            section_id=f'para-{i+1}',
            heading=heading,
            section_path=f'Paragraph {i+1}',
            page=page_num,
            clause_type=clause_type,
            char_count=len(para),
        )
        clauses.append(Clause(id=clause_id, metadata=meta, text=para))

    return clauses


def segment_document(pages: List[Tuple[int, str]], document_id: str) -> List[Clause]:
    """
    Main entry point for document segmentation.
    Parses pages into a structured list of Clauses with full metadata.
    Zero LLM calls.

    Args:
        pages: List of (page_number, text) tuples from document parsers.
        document_id: UUID string for the parent document.

    Returns:
        List of Clause objects with populated metadata.
    """
    if not pages:
        return []
    return build_section_hierarchy(pages, document_id)
