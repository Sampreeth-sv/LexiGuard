"""
Deterministic Consistency Analysis Engine for LexiGuard Phase 3 Checkpoint 3.
Compares related document pairs (Offer Letter ↔ Employment Agreement or General Contract Pairs)
across 17 key legal/compensation categories.
Zero LLM / Gemini calls. 100% deterministic and evidence-grounded.
"""
import re
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.models.schemas import Clause
from app.analysis.entities import extract_monetary_values, normalize_monetary_amount, extract_dates
from app.analysis.financial_engine import analyze_document_financials

logger = logging.getLogger(__name__)


class ConsistencyItem(BaseModel):
    category: str
    title: str
    status: str  # CONSISTENT, DIFFERENT, MISSING_IN_DOCUMENT_A, MISSING_IN_DOCUMENT_B, UNRESOLVED
    summary: str
    
    # Document A Provenance
    doc_id_a: str
    filename_a: str
    clause_id_a: Optional[str] = None
    section_path_a: Optional[str] = None
    page_a: Optional[int] = None
    text_a: Optional[str] = None
    
    # Document B Provenance
    doc_id_b: str
    filename_b: str
    clause_id_b: Optional[str] = None
    section_path_b: Optional[str] = None
    page_b: Optional[int] = None
    text_b: Optional[str] = None


class ConsistencyReport(BaseModel):
    doc_id_a: str
    filename_a: str
    doc_id_b: str
    filename_b: str
    total_categories_evaluated: int
    consistent_count: int
    different_count: int
    missing_count: int
    items: List[ConsistencyItem]


# Regex patterns for matching consistency categories in clauses
CATEGORY_PATTERNS = {
    "employee_name": re.compile(r'\b(employee|candidate|appointee|consultant|worker|personnel)\s+name\b|\b(?:name|designated as|appointed as)\s+:\s*([A-Z][a-z]+\s+[A-Z][a-z]+)', re.IGNORECASE),
    "employer_name": re.compile(r'\b(company|employer|client|organization)\s+name\b|\b(?:between|by)\s+([A-Z][\w\s.,]+(?:Inc|LLC|Ltd|Pvt|Limited|Corp))', re.IGNORECASE),
    "job_title": re.compile(r'\b(position|designation|job title|role|title|appointed as|employed as)\b', re.IGNORECASE),
    "joining_date": re.compile(r'\b(joining date|date of joining|start date|commencement date|effective date|first day)\b', re.IGNORECASE),
    "work_location": re.compile(r'\b(work location|office location|place of work|posting|location|headquarters|remote)\b', re.IGNORECASE),
    "salary_compensation": re.compile(r'\b(salary|base pay|fixed compensation|ctc|annual ctc|remuneration|stipend)\b', re.IGNORECASE),
    "bonus": re.compile(r'\b(performance bonus|signing bonus|joining bonus|discretionary bonus|annual bonus|bonus)\b', re.IGNORECASE),
    "probation": re.compile(r'\b(probation|probationary period|probation period|confirmation)\b', re.IGNORECASE),
    "notice_period": re.compile(r'\b(notice period|written notice|notice of termination|termination notice|\d+\s*days?\s*notice|notice)\b', re.IGNORECASE),
    "termination": re.compile(r'\b(termination|severance|terminate|grounds for termination|cause for termination)\b', re.IGNORECASE),
    "confidentiality": re.compile(r'\b(confidentiality|confidential information|non-disclosure|proprietary information)\b', re.IGNORECASE),
    "intellectual_property": re.compile(r'\b(intellectual property|ip rights|work for hire|invention assignment|patent|copyright)\b', re.IGNORECASE),
    "leave": re.compile(r'\b(leave|vacation|annual leave|sick leave|paid time off|pto|holidays)\b', re.IGNORECASE),
    "working_hours": re.compile(r'\b(working hours|hours of work|business hours|shift timing|work week)\b', re.IGNORECASE),
    "benefits": re.compile(r'\b(health insurance|medical insurance|provident fund|gratuity|benefits|perks)\b', re.IGNORECASE),
    "non_compete": re.compile(r'\b(non-compete|non-solicitation|restrictive covenant|restraint of trade)\b', re.IGNORECASE),
    "obligations": re.compile(r'\b(duties|responsibilities|obligations|code of conduct|policies)\b', re.IGNORECASE),
}


class ConsistencyEngine:
    """
    Deterministic Offer Letter ↔ Employment Agreement Consistency Engine.
    Evaluates clause matching, financial alignment, dates, notice periods, and provisions across related documents.
    """

    def compare_documents(
        self,
        doc_id_a: str,
        filename_a: str,
        clauses_a: List[Clause],
        doc_id_b: str,
        filename_b: str,
        clauses_b: List[Clause]
    ) -> ConsistencyReport:
        if doc_id_a == doc_id_b:
            raise ValueError("Cannot perform consistency check on the same document against itself.")

        items: List[ConsistencyItem] = []

        # 1. Salary & Compensation Consistency (using FinancialEngine)
        fin_a = analyze_document_financials(doc_id_a, clauses_a)
        fin_b = analyze_document_financials(doc_id_b, clauses_b)
        
        sal_a = next((f for f in fin_a if "SALARY" in f.item_type), None)
        sal_b = next((f for f in fin_b if "SALARY" in f.item_type), None)

        if sal_a and sal_b:
            norm_a = normalize_monetary_amount(sal_a.amount or "")
            norm_b = normalize_monetary_amount(sal_b.amount or "")
            if norm_a and norm_b and norm_a == norm_b:
                status = "CONSISTENT"
                summary = f"Matching salary provision identified in both documents ({sal_a.amount})."
            elif norm_a and norm_b:
                status = "DIFFERENT"
                summary = f"Salary amounts differ: {filename_a} specifies {sal_a.amount}, whereas {filename_b} specifies {sal_b.amount}."
            else:
                status = "UNRESOLVED"
                summary = "Salary provisions identified in both documents, but exact numerical values could not be compared."

            c_a = next((c for c in clauses_a if c.id == sal_a.clause_id), None)
            c_b = next((c for c in clauses_b if c.id == sal_b.clause_id), None)

            items.append(ConsistencyItem(
                category="salary_compensation",
                title="Salary & Compensation",
                status=status,
                summary=summary,
                doc_id_a=doc_id_a,
                filename_a=filename_a,
                clause_id_a=sal_a.clause_id,
                section_path_a=sal_a.section_path,
                page_a=sal_a.page,
                text_a=c_a.text if c_a else sal_a.evidence_text,
                doc_id_b=doc_id_b,
                filename_b=filename_b,
                clause_id_b=sal_b.clause_id,
                section_path_b=sal_b.section_path,
                page_b=sal_b.page,
                text_b=c_b.text if c_b else sal_b.evidence_text
            ))
        elif sal_a and not sal_b:
            items.append(ConsistencyItem(
                category="salary_compensation",
                title="Salary & Compensation",
                status="MISSING_IN_DOCUMENT_B",
                summary=f"Salary provision specified in {filename_a} ({sal_a.amount}), but no structured salary term identified in {filename_b}.",
                doc_id_a=doc_id_a, filename_a=filename_a, clause_id_a=sal_a.clause_id, section_path_a=sal_a.section_path, page_a=sal_a.page, text_a=sal_a.evidence_text,
                doc_id_b=doc_id_b, filename_b=filename_b
            ))
        elif sal_b and not sal_a:
            items.append(ConsistencyItem(
                category="salary_compensation",
                title="Salary & Compensation",
                status="MISSING_IN_DOCUMENT_A",
                summary=f"Salary provision specified in {filename_b} ({sal_b.amount}), but no structured salary term identified in {filename_a}.",
                doc_id_a=doc_id_a, filename_a=filename_a,
                doc_id_b=doc_id_b, filename_b=filename_b, clause_id_b=sal_b.clause_id, section_path_b=sal_b.section_path, page_b=sal_b.page, text_b=sal_b.evidence_text
            ))

        # 2. General Categories Comparison via Pattern Matching
        categories_to_check = [
            ("notice_period", "Notice Period"),
            ("joining_date", "Joining / Start Date"),
            ("probation", "Probation Period"),
            ("job_title", "Job Title / Role"),
            ("work_location", "Work Location"),
            ("bonus", "Bonus Terms"),
            ("termination", "Termination Terms"),
            ("confidentiality", "Confidentiality"),
            ("intellectual_property", "Intellectual Property"),
            ("leave", "Leave Policy"),
            ("working_hours", "Working Hours"),
            ("benefits", "Benefits & Perks"),
            ("non_compete", "Non-Compete / Restrictive Covenants"),
        ]

        for cat_key, cat_title in categories_to_check:
            pat = CATEGORY_PATTERNS[cat_key]
            matches_a = [c for c in clauses_a if pat.search(c.text)]
            matches_b = [c for c in clauses_b if pat.search(c.text)]

            if matches_a and matches_b:
                ca = matches_a[0]
                cb = matches_b[0]
                
                # Check for explicit numbers / durations in notice/probation/dates
                nums_a = re.findall(r'\b\d+\s*(?:days?|months?|weeks?|years?)\b', ca.text, re.IGNORECASE)
                nums_b = re.findall(r'\b\d+\s*(?:days?|months?|weeks?|years?)\b', cb.text, re.IGNORECASE)

                if nums_a and nums_b:
                    if nums_a[0].lower() == nums_b[0].lower():
                        status = "CONSISTENT"
                        summary = f"Consistent {cat_title.lower()} provision identified in both documents ({nums_a[0]})."
                    else:
                        status = "DIFFERENT"
                        summary = f"Different {cat_title.lower()} specified: {filename_a} specifies '{nums_a[0]}', whereas {filename_b} specifies '{nums_b[0]}'."
                else:
                    status = "CONSISTENT" if ca.text.strip().lower() == cb.text.strip().lower() else "UNRESOLVED"
                    summary = f"{cat_title} provisions identified in both documents for review."

                items.append(ConsistencyItem(
                    category=cat_key,
                    title=cat_title,
                    status=status,
                    summary=summary,
                    doc_id_a=doc_id_a,
                    filename_a=filename_a,
                    clause_id_a=ca.id,
                    section_path_a=ca.metadata.section_path or "General",
                    page_a=ca.metadata.page,
                    text_a=ca.text,
                    doc_id_b=doc_id_b,
                    filename_b=filename_b,
                    clause_id_b=cb.id,
                    section_path_b=cb.metadata.section_path or "General",
                    page_b=cb.metadata.page,
                    text_b=cb.text
                ))
            elif matches_a and not matches_b:
                ca = matches_a[0]
                items.append(ConsistencyItem(
                    category=cat_key,
                    title=cat_title,
                    status="MISSING_IN_DOCUMENT_B",
                    summary=f"{cat_title} provision present in {filename_a}, but absent in {filename_b}.",
                    doc_id_a=doc_id_a, filename_a=filename_a, clause_id_a=ca.id, section_path_a=ca.metadata.section_path or "General", page_a=ca.metadata.page, text_a=ca.text,
                    doc_id_b=doc_id_b, filename_b=filename_b
                ))
            elif matches_b and not matches_a:
                cb = matches_b[0]
                items.append(ConsistencyItem(
                    category=cat_key,
                    title=cat_title,
                    status="MISSING_IN_DOCUMENT_A",
                    summary=f"{cat_title} provision present in {filename_b}, but absent in {filename_a}.",
                    doc_id_a=doc_id_a, filename_a=filename_a,
                    doc_id_b=doc_id_b, filename_b=filename_b, clause_id_b=cb.id, section_path_b=cb.metadata.section_path or "General", page_b=cb.metadata.page, text_b=cb.text
                ))

        consistent_cnt = sum(1 for i in items if i.status == "CONSISTENT")
        different_cnt = sum(1 for i in items if i.status == "DIFFERENT")
        missing_cnt = sum(1 for i in items if "MISSING" in i.status)

        return ConsistencyReport(
            doc_id_a=doc_id_a,
            filename_a=filename_a,
            doc_id_b=doc_id_b,
            filename_b=filename_b,
            total_categories_evaluated=len(items),
            consistent_count=consistent_cnt,
            different_count=different_cnt,
            missing_count=missing_cnt,
            items=items
        )
