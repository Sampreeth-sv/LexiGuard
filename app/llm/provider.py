"""
LLM Provider abstraction for LexiGuard.
Defines the abstract LLMProvider interface and two concrete implementations:
  - GeminiProvider: uses Google Gemini cloud API
  - FallbackProvider: deterministic responses when no API key is configured

The application NEVER crashes when the API key is missing.
All document parsing, search, and risk analysis continue working without an API key.
Only generative features (summary, Q&A, explanations, checklists) require the API.
"""
from abc import ABC, abstractmethod
import logging
import re
import textwrap
from datetime import datetime
from typing import List, Optional, Tuple

from app.config import settings
from app.llm.validator import _clause_matches_citation, extract_citations_from_text
from app.models.schemas import (
    Checklist, ChecklistItem, ClaimEvidence, Clause, GroundingStatus,
    QAResponse, RiskSignal, SummaryResponse
)

logger = logging.getLogger(__name__)


def format_clause_reference(section_path: Optional[str], page: Optional[int], clause_id: Optional[str] = None) -> Optional[str]:
    """Format section, page, and clause_id into a standardized clause reference string."""
    parts = []
    if section_path:
        sec_str = section_path if section_path.lower().startswith("section") else f"Section {section_path}"
        parts.append(sec_str)
    if page is not None:
        parts.append(f"Page {page}")
    if clause_id and not section_path and page is None:
        parts.append(f"Clause {clause_id}")
    return " | ".join(parts) if parts else None


def truncate_word_boundary(text: str, max_len: int = 150) -> str:
    """Truncate text at word boundaries without cutting words halfway."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return textwrap.shorten(text, width=max_len, placeholder="...")


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_summary(self, clauses: List[Clause], document_name: str) -> str:
        """Generate a plain-language summary of the document."""
        ...

    @abstractmethod
    def answer_question(
        self,
        question: str,
        evidence_clauses: List[Clause],
        document_name: str,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en",
    ) -> QAResponse:
        """Answer a question grounded in the retrieved evidence clauses and conversation context."""
        ...

    @abstractmethod
    def answer_cross_document_question(
        self,
        question: str,
        doc_evidence_map: dict,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en"
    ) -> QAResponse:
        """Answer a question grounded in evidence retrieved across multiple documents."""
        ...

    @abstractmethod
    def explain_signal(self, signal: RiskSignal, clause: Clause) -> str:
        """Explain a detected risk signal in plain language."""
        ...

    @abstractmethod
    def explain_difference(self, before_text: str, after_text: str, section_path: str) -> str:
        """Explain what changed between two versions of a clause."""
        ...

    @abstractmethod
    def generate_checklist(
        self,
        signals: List[RiskSignal],
        obligations: List[str],
        dates: List[str],
        clauses: Optional[List[Clause]] = None,
    ) -> Checklist:
        """Generate a legal review checklist from signals, obligations, dates, and clauses."""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is ready to make API calls."""
        ...





class GeminiProvider(LLMProvider):
    """Google Gemini implementation of LLMProvider."""

    def __init__(self) -> None:
        import google.generativeai as genai
        from app.llm.prompts import (
            build_checklist_prompt, build_diff_explanation_prompt,
            build_qa_prompt, build_signal_explanation_prompt,
            build_summary_prompt
        )
        self._build_summary_prompt = build_summary_prompt
        self._build_qa_prompt = build_qa_prompt
        self._build_signal_explanation_prompt = build_signal_explanation_prompt
        self._build_diff_explanation_prompt = build_diff_explanation_prompt
        self._build_checklist_prompt = build_checklist_prompt

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(settings.gemini_model)
        self._is_available = True
        logger.info("GeminiProvider initialized with model: %s", settings.gemini_model)

    def _call(self, prompt: str) -> str:
        """Make a single LLM API call and return the text response."""
        response = self._model.generate_content(prompt)
        return response.text

    def generate_summary(self, clauses: List[Clause], document_name: str) -> str:
        prompt = self._build_summary_prompt(clauses, document_name)
        try:
            return self._call(prompt)
        except Exception as e:
            logger.error("Gemini generate_summary error: %s", type(e).__name__)
            return "AI summarization is temporarily unavailable. Please try again later."

    def answer_question(
        self,
        question: str,
        evidence_clauses: List[Clause],
        document_name: str,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en",
    ) -> QAResponse:
        from app.llm.validator import parse_qa_response
        prompt = self._build_qa_prompt(question, evidence_clauses, document_name, conversation_history, language=language)
        try:
            raw = self._call(prompt)
            return parse_qa_response(raw, evidence_clauses, question)
        except Exception as e:
            err_name = type(e).__name__
            err_str = str(e)

            if 'ResourceExhausted' in err_name or '429' in err_str or 'quota' in err_str.lower():
                logger.warning("Gemini answer_question: API quota exhausted (429). Retry after rate-limit window.")
                return QAResponse(
                    answer=(
                        "The Gemini API daily quota has been reached. "
                        "Please wait a few minutes and try again, or check your API billing details at https://ai.dev/rate-limit."
                    ),
                    grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
                    abstained=True,
                )
            logger.error("Gemini answer_question error: %s: %s", type(e).__name__, str(e))
            return QAResponse(
                answer="AI analysis is temporarily unavailable. Please try again later.",
                grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
                abstained=True,
            )

    def answer_cross_document_question(
        self,
        question: str,
        doc_evidence_map: dict,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en"
    ) -> QAResponse:
        from app.llm.validator import parse_qa_response
        from app.llm.prompts import build_cross_qa_prompt
        prompt = build_cross_qa_prompt(question, doc_evidence_map, conversation_history, language)
        try:
            raw = self._call(prompt)
            all_clauses = [c for clauses in doc_evidence_map.values() for c in clauses]
            return parse_qa_response(raw, all_clauses, question)
        except Exception as e:
            logger.error("Gemini answer_cross_document_question error: %s", type(e).__name__)
            fallback = FallbackProvider()
            return fallback.answer_cross_document_question(question, doc_evidence_map, conversation_history, language)

    def explain_signal(self, signal: RiskSignal, clause: Clause) -> str:
        prompt = self._build_signal_explanation_prompt(signal, clause)
        try:
            return self._call(prompt)
        except Exception as e:
            logger.error("Gemini explain_signal error: %s", type(e).__name__)
            return signal.plain_explanation

    def explain_difference(self, before_text: str, after_text: str, section_path: str) -> str:
        prompt = self._build_diff_explanation_prompt(before_text, after_text, section_path)
        try:
            return self._call(prompt)
        except Exception as e:
            logger.error("Gemini explain_difference error: %s", type(e).__name__)
            return "AI explanation is temporarily unavailable. Please try again later."

    def generate_checklist(
        self,
        signals: List[RiskSignal],
        obligations: List[str],
        dates: List[str],
        clauses: Optional[List[Clause]] = None,
    ) -> Checklist:
        prompt = self._build_checklist_prompt(signals, obligations, dates, clauses)
        try:
            raw = self._call(prompt)
            items = _parse_checklist_text(raw, available_clauses=clauses)
            return Checklist(title="Legal Review Checklist", items=items, generated_at=datetime.utcnow())
        except Exception as e:
            logger.error("Gemini generate_checklist error: %s", type(e).__name__)
            return _deterministic_checklist(signals, obligations, dates, clauses)

    @property
    def is_available(self) -> bool:
        return self._is_available


class FallbackProvider(LLMProvider):
    """
    Deterministic fallback provider used when no API key is configured.
    All document browsing, search, and risk analysis continue working.
    Only AI-generated text features are unavailable.
    """

    def generate_summary(self, clauses: List[Clause], document_name: str) -> str:
        lines = [f"Document: {document_name}", "", "Sections found:"]
        seen_paths = set()
        for c in clauses:
            path = c.metadata.section_path or 'General'
            if path not in seen_paths:
                seen_paths.add(path)
                heading = c.metadata.heading or path
                lines.append(f"  • {heading}")
        lines.append("")
        lines.append("AI summarization is unavailable. Configure a GEMINI_API_KEY to enable this feature.")
        lines.append("You can still browse the document map, view attention signals, and use the search feature.")
        return "\n".join(lines)

    def answer_question(
        self,
        question: str,
        evidence_clauses: List[Clause],
        document_name: str,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en",
    ) -> QAResponse:
        return QAResponse(
            answer=(
                "AI analysis is currently unavailable. Please configure a Gemini API key to enable this feature. "
                "You can still browse the document map, attention signals, and search results."
            ),
            evidences=[],
            grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
            abstained=True,
        )

    def answer_cross_document_question(
        self,
        question: str,
        doc_evidence_map: dict,
        conversation_history: Optional[List[dict]] = None,
        language: str = "en"
    ) -> QAResponse:
        evidences = []
        ans_parts = ["Cross-Document Analysis:"]
        for doc_name, clauses in doc_evidence_map.items():
            if clauses:
                ans_parts.append(f"\nDocument: {doc_name}")
                for c in clauses[:2]:
                    sec = c.metadata.section_path or "General"
                    page = c.metadata.page
                    ans_parts.append(f"  • [Document: {doc_name}, Section {sec}, Page {page}] {c.text[:120]}...")
                    evidences.append(ClaimEvidence(
                        clause_id=c.id,
                        section_path=sec,
                        page=page,
                        quoted_text=c.text[:150]
                    ))
            else:
                ans_parts.append(f"\nNo corresponding provision was identified in {doc_name}.")

        ans_text = "\n".join(ans_parts)
        if not evidences:
            return QAResponse(
                answer="No corresponding evidence was identified across the selected documents.",
                grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
                abstained=True
            )
        return QAResponse(
            answer=ans_text,
            evidences=evidences,
            grounding_status=GroundingStatus.SUPPORTED
        )

    def explain_signal(self, signal: RiskSignal, clause: Clause) -> str:
        return signal.plain_explanation

    def explain_difference(self, before_text: str, after_text: str, section_path: str) -> str:
        return "AI explanation unavailable. Configure a GEMINI_API_KEY to enable this feature."

    def generate_checklist(
        self,
        signals: List[RiskSignal],
        obligations: List[str],
        dates: List[str],
        clauses: Optional[List[Clause]] = None,
    ) -> Checklist:
        return _deterministic_checklist(signals, obligations, dates, clauses)

    @property
    def is_available(self) -> bool:
        return False


def _parse_checklist_text(text: str, available_clauses: Optional[List[Clause]] = None) -> List[ChecklistItem]:
    """Parse LLM checklist text into structured ChecklistItem list with citation validation."""
    items = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith(('[ ]', '- ', '* ', '•', '✓')) or re.match(r'^\d+\.\s+', stripped):
            item_text = re.sub(r'^(?:\[\s*\]|[-*•✓]|\d+\.)\s*', '', stripped).strip()
            if item_text and len(item_text) > 3:
                clause_ref = None
                if available_clauses:
                    citations = extract_citations_from_text(item_text)
                    for sec_ref, page in citations:
                        for clause in available_clauses:
                            if _clause_matches_citation(clause, sec_ref, page):
                                clause_ref = format_clause_reference(
                                    clause.metadata.section_path,
                                    clause.metadata.page,
                                    clause.metadata.clause_id,
                                )
                                break
                        if clause_ref:
                            break

                category = 'general'
                lower = item_text.lower()
                if any(k in lower for k in ['date', 'deadline', 'renew', 'notice']):
                    category = 'dates'
                elif any(k in lower for k in ['pay', 'fee', 'invoice', 'amount', 'salary', 'compensation']):
                    category = 'payment'
                elif any(k in lower for k in ['question', 'ask', 'lawyer', 'verify', 'consult']):
                    category = 'lawyer_questions'
                elif any(k in lower for k in ['obligation', 'shall', 'must', 'responsible', 'require']):
                    category = 'obligations'

                items.append(ChecklistItem(
                    item=item_text,
                    category=category,
                    clause_reference=clause_ref,
                ))
    return items if items else [ChecklistItem(item="Review the full document with a legal professional.", category="general")]


from app.analysis.entities import detect_document_type


def _deterministic_checklist(
    signals: List[RiskSignal],
    obligations: List[str],
    dates: List[str],
    clauses: Optional[List[Clause]] = None,
) -> Checklist:
    """Build a document-specific deterministic checklist from signals, document type, and metadata."""
    items = []
    seen_keys = set()

    doc_type = detect_document_type(clauses or [])

    # Add signal review items
    for sig in signals:
        key = ("review", sig.category.lower(), sig.plain_explanation.strip().lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        truncated_exp = truncate_word_boundary(sig.plain_explanation, max_len=150)
        clause_ref = format_clause_reference(sig.section_path, sig.page, sig.clause_id)

        items.append(ChecklistItem(
            item=f"Review: {sig.category.replace('_', ' ').title()} — {truncated_exp}",
            category='review',
            clause_reference=clause_ref,
        ))

    # Document-specific key items
    doc_specific_items = []
    if doc_type == "Employment":
        doc_specific_items = [
            ("review", "Verify compensation, bonus structures, and payment frequency."),
            ("review", "Check notice period requirements for both employee and employer."),
            ("review", "Review probation period terms and evaluation criteria."),
            ("review", "Confirm IP assignment and ownership of created work product."),
            ("review", "Check post-employment non-compete and non-solicitation restrictions."),
        ]
    elif doc_type == "NDA":
        doc_specific_items = [
            ("review", "Verify scope and definition of Confidential Information."),
            ("review", "Check confidentiality obligations duration and term end."),
            ("review", "Confirm standard exclusions (public knowledge, prior possession)."),
            ("review", "Review return or destruction requirements for confidential data."),
        ]
    elif doc_type == "Commercial/Project":
        doc_specific_items = [
            ("review", "Confirm clear scope of work, deliverables, and acceptance criteria."),
            ("review", "Verify payment milestones, invoice terms, and late fee penalties."),
            ("review", "Check limitation of liability caps and indemnification obligations."),
            ("review", "Review termination for convenience and termination for cause terms."),
        ]
    elif doc_type == "Terms & Conditions":
        doc_specific_items = [
            ("review", "Verify automatic renewal and cancellation notice deadlines."),
            ("review", "Check unilateral price change and fee adjustment clauses."),
            ("review", "Review refund policies and restriction clauses."),
            ("review", "Confirm third-party data processing and privacy terms."),
        ]

    for cat, desc in doc_specific_items:
        k = (cat, desc.lower())
        if k not in seen_keys:
            seen_keys.add(k)
            items.append(ChecklistItem(item=desc, category=cat))

    for d in dates[:5]:
        k = ("dates", f"track important date: {d}".lower())
        if k not in seen_keys:
            seen_keys.add(k)
            items.append(ChecklistItem(item=f"Track important date: {d}", category='dates'))

    for ob in obligations[:5]:
        snippet = truncate_word_boundary(ob, max_len=150)
        k = ("obligations", f"confirm obligation: {snippet}".lower())
        if k not in seen_keys:
            seen_keys.add(k)
            ob_ref = None
            if clauses:
                ob_lower = ob[:30].lower()
                for c in clauses:
                    if ob_lower in c.text.lower():
                        ob_ref = format_clause_reference(c.metadata.section_path, c.metadata.page, c.metadata.clause_id)
                        break
            items.append(ChecklistItem(item=f"Confirm obligation: {snippet}", category='obligations', clause_reference=ob_ref))

    general_item = "Consult a qualified legal professional before signing or acting on this document."
    k = ("general", general_item.lower())
    if k not in seen_keys:
        seen_keys.add(k)
        items.append(ChecklistItem(item=general_item, category='general'))

    title = f"Legal Review Checklist ({doc_type})" if doc_type not in ("General Legal/Business Document", "Unknown") else "Legal Review Checklist"

    return Checklist(
        title=title,
        items=items,
        generated_at=datetime.utcnow(),
    )



def get_llm_provider() -> LLMProvider:
    """
    Return the appropriate LLM provider based on configuration.
    Returns GeminiProvider if API key is configured, FallbackProvider otherwise.
    Never raises — always returns a working provider.
    """
    if settings.genai_available:
        try:
            return GeminiProvider()
        except Exception as e:
            logger.warning("Gemini provider initialization failed (%s). Using fallback.", type(e).__name__)
    return FallbackProvider()
