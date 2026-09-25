"""
Deterministic Financial & Compensation Intelligence Engine for LexiGuard Phase 2 Feature 3.
Parses extracted document clauses and metadata to detect financial items, salary terms,
bonuses, allowances, reimbursements, deductions, currencies, payment frequencies, and completeness observations.
Zero LLM / Gemini calls during detection. Fully deterministic.
"""
import re
import uuid
import logging
from typing import List, Dict, Any, Optional
from app.models.schemas import Clause
from app.models.financial import FinancialItem
from app.analysis.entities import extract_monetary_values, extract_dates

logger = logging.getLogger(__name__)

# Patterns for financial and compensation detection
CURRENCY_PATTERNS = {
    "INR": re.compile(r'(?:₹|INR|Rs\.?|Rupees)', re.IGNORECASE),
    "USD": re.compile(r'(?:\$|USD|Dollars)', re.IGNORECASE),
    "EUR": re.compile(r'(?:€|EUR|Euros)', re.IGNORECASE),
    "GBP": re.compile(r'(?:£|GBP|Pounds)', re.IGNORECASE),
}

FREQUENCY_PATTERNS = {
    "annual": re.compile(r'\b(per annum|p\.a\.|annual|annually|year|yearly)\b', re.IGNORECASE),
    "monthly": re.compile(r'\b(per month|p\.m\.|monthly|month|each month)\b', re.IGNORECASE),
    "hourly": re.compile(r'\b(per hour|hourly|hour)\b', re.IGNORECASE),
    "one-time": re.compile(r'\b(one-time|lump sum|signing|joining)\b', re.IGNORECASE),
}

FINANCIAL_PATTERNS = {
    "salary": re.compile(r'\b(salary|base pay|fixed compensation|remuneration|stipend|base salary|ctc|cost to company|total ctc|annual ctc|compensation)\b', re.IGNORECASE),
    "bonus": re.compile(r'\b(performance bonus|joining bonus|signing bonus|discretionary bonus|annual bonus|bonus)\b', re.IGNORECASE),
    "commission": re.compile(r'\b(commission|incentive pay|incentive compensation|sales incentive)\b', re.IGNORECASE),
    "allowance": re.compile(r'\b(allowance|housing allowance|hra|conveyance|travel allowance|relocation allowance)\b', re.IGNORECASE),
    "reimbursement": re.compile(r'\b(reimbursement|reimburse|expense claim|business expenses)\b', re.IGNORECASE),
    "benefit": re.compile(r'\b(health insurance|medical insurance|provident fund|gratuity|pension|benefit)\b', re.IGNORECASE),
    "tax_withholding": re.compile(r'\b(tax at source|deducted at source|tax deducted at source|withholding tax|\btds\b|applicable withholding|client may deduct tax|tax withholding|withholding|tax deduction)\b', re.IGNORECASE),
    "deduction": re.compile(r'\b(salary deduction|payroll deduction|employee deduction|deduction from salary|deduction from compensation|deduction|deduct|liquidated damages)\b', re.IGNORECASE),
    "probation_comp": re.compile(r'\b(during probation|probationary salary|probation period compensation)\b', re.IGNORECASE),
    "termination_comp": re.compile(r'\b(severance|notice pay|pay in lieu of notice|termination payout|penalty equal to)\b', re.IGNORECASE),
}

def is_non_tax_deduction(text: str) -> bool:
    """
    Determines if text describes a non-tax monetary deduction (e.g. salary deduction, payroll deduction, liquidated damages).
    Tax withholding or tax deducted at source is categorized separately under TAX_WITHHOLDING.
    """
    non_tax_explicit = re.compile(
        r'\b(salary deduction|payroll deduction|employee deduction|deductions? from (?:salary|pay|compensation)|liquidated damages)\b',
        re.IGNORECASE
    )
    if non_tax_explicit.search(text):
        return True
    generic_deduction = re.compile(r'\b(deduction|deduct)\b', re.IGNORECASE)
    if generic_deduction.search(text) and not FINANCIAL_PATTERNS["tax_withholding"].search(text):
        return True
    return False

def is_salary_term(text: str) -> bool:
    """
    Returns True if text describes a base salary or compensation term.
    Avoids false positives where 'salary' or 'compensation' appears solely within a deduction phrase.
    """
    if not FINANCIAL_PATTERNS["salary"].search(text):
        return False
    deduction_context_pat = re.compile(
        r'\b(?:deductions?|reduction)\s+(?:from|of)\s+(?:salary|pay|compensation)\b|\b(?:salary|pay|compensation)\s+deductions?\b',
        re.IGNORECASE
    )
    if deduction_context_pat.search(text):
        stripped_text = deduction_context_pat.sub('', text)
        if not FINANCIAL_PATTERNS["salary"].search(stripped_text):
            return False
    return True

CONDITION_PATTERNS = re.compile(r'\b(subject to|provided that|upon completion|contingent on|conditional upon|at sole discretion)\b', re.IGNORECASE)
TIMING_PATTERNS = re.compile(r'\b(payable on|due within|paid by the|on or before|end of each month|net \d+)\b', re.IGNORECASE)

FINANCIAL_CONDITION_PATTERNS = [
    re.compile(r'\b(subject\s+to\s+[^,;\n.]{5,80})', re.IGNORECASE),
    re.compile(r'\b(provided\s+that\s+[^,;\n.]{5,80})', re.IGNORECASE),
    re.compile(r'\b(contingent\s+(?:on|upon)\s+[^,;\n.]{5,80})', re.IGNORECASE),
    re.compile(r'\b(conditional\s+(?:on|upon)\s+[^,;\n.]{5,80})', re.IGNORECASE),
    re.compile(r'\b(upon\s+(?:successful\s+)?completion\s+of\s+[^,;\n.]{5,80})', re.IGNORECASE),
    re.compile(r'\b(at\s+the\s+sole\s+discretion\s+of\s+[^,;\n.]{5,80})', re.IGNORECASE),
]

GENERIC_DISCARD_PHRASES = {
    "subject to", "provided that", "as applicable", "in accordance with",
    "subject to company policy", "in accordance with company policy",
    "in accordance with company payroll practices", "as per company policy"
}


def extract_financial_condition(text: str) -> Optional[str]:
    """
    Extract substantive financial condition attached to the compensation term.
    Rejects isolated trigger phrases ("subject to", "provided that") and general payroll boilerplate.
    """
    if not text:
        return None
    for pattern in FINANCIAL_CONDITION_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r'\s+(?:and|or|with|by|the|a|an)$', '', candidate, flags=re.IGNORECASE).strip()
            if candidate.lower() in GENERIC_DISCARD_PHRASES:
                return None
            words = candidate.split()
            if len(words) <= 2 and words[0].lower() in ('subject', 'provided', 'contingent', 'conditional'):
                return None
            return candidate
    return None


def extract_financial_effective_date(text: str, dates: List[str]) -> Optional[str]:
    """
    Extract date only if explicitly connected to financial/compensation effective date.
    Leaves effective_date as None if the date is merely a general employee joining/start date.
    """
    if not dates or not text:
        return None
    for dt in dates:
        dt_escaped = re.escape(dt)
        p1 = re.compile(
            r'(?:effective|commencing|w\.e\.f\.?|applicable|starting)\s+(?:from|as\s+of|on)?\s*:?\s*' + dt_escaped,
            re.IGNORECASE
        )
        if p1.search(text):
            return dt
        p2 = re.compile(r'with\s+effect\s+from\s+' + dt_escaped, re.IGNORECASE)
        if p2.search(text):
            return dt
        p3 = re.compile(
            r'(?:salary|compensation|pay|remuneration|stipend|bonus|allowance)\s+(?:effective|starting|commencing)\s+(?:from|on)?\s+' + dt_escaped,
            re.IGNORECASE
        )
        if p3.search(text):
            return dt
    return None


def generate_financial_item_id(doc_id: str, item_type: str, clause_id: str, amount: str) -> str:
    key = f"{doc_id}:{item_type}:{clause_id}:{amount or 'none'}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


class FinancialEngine:
    """
    Deterministic Financial and Compensation Intelligence Engine.
    Structures financial items with provenance and factual completeness observations.
    """

    def analyze_document_financials(
        self,
        clauses: List[Clause],
        document_id: str
    ) -> List[FinancialItem]:
        if not clauses:
            return []

        items: List[FinancialItem] = []
        seen_keys: set = set()

        def add_item(item: FinancialItem):
            key = (item.item_type, item.clause_id, item.amount, item.currency)
            if key not in seen_keys:
                seen_keys.add(key)
                items.append(item)

        for clause in clauses:
            text = clause.text
            monies = extract_monetary_values(text)
            dates = extract_dates(text)

            # Currency Detection
            detected_currency = None
            for curr_code, curr_pat in CURRENCY_PATTERNS.items():
                if curr_pat.search(text):
                    detected_currency = curr_code
                    break

            # Frequency Detection
            detected_freq = None
            for freq_code, freq_pat in FREQUENCY_PATTERNS.items():
                if freq_pat.search(text):
                    detected_freq = freq_code
                    break

            # Condition & Timing Detection
            extracted_cond = extract_financial_condition(text)
            timing_match = TIMING_PATTERNS.search(text)

            extracted_timing = timing_match.group(0) if timing_match else None
            effective_dt = extract_financial_effective_date(text, dates)

            # 1. Base Salary / Fixed Compensation
            if is_salary_term(text):
                item_type = "ANNUAL_SALARY" if detected_freq == "annual" else ("MONTHLY_SALARY" if detected_freq == "monthly" else ("HOURLY_COMPENSATION" if detected_freq == "hourly" else "BASE_SALARY"))
                amount = monies[0] if monies else None
                completeness = None
                if not amount:
                    completeness = "Salary or compensation term identified, but fixed monetary amount is not specified."
                elif not detected_freq:
                    completeness = "Compensation amount specified, but payment frequency is not explicitly stated."

                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, item_type, clause.id, amount or ""),
                    document_id=document_id,
                    item_type=item_type,
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["salary"]),
                    completeness_note=completeness,
                ))

            # 2. Bonus & Performance Bonus
            if FINANCIAL_PATTERNS["bonus"].search(text):
                amount = monies[0] if monies else None
                completeness = None if amount else "Bonus provision identified, but fixed amount is not specified."
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "BONUS", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="PERFORMANCE_BONUS" if "performance" in text.lower() else "BONUS",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq or "one-time",
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["bonus"]),
                    completeness_note=completeness,
                ))

            # 3. Commission / Incentive Compensation
            if FINANCIAL_PATTERNS["commission"].search(text):
                amount = monies[0] if monies else None
                completeness = None if amount else "Commission or incentive terms referenced, but specific calculation or fixed amount is not specified."
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "COMMISSION", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="COMMISSION",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["commission"]),
                    completeness_note=completeness,
                ))

            # 4. Allowances
            if FINANCIAL_PATTERNS["allowance"].search(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "ALLOWANCE", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="ALLOWANCE",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["allowance"]),
                ))

            # 5. Reimbursements
            if FINANCIAL_PATTERNS["reimbursement"].search(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "REIMBURSEMENT", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="REIMBURSEMENT",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["reimbursement"]),
                ))

            # 6. Tax Withholding (Tax Deducted at Source / Withholding Tax)
            if FINANCIAL_PATTERNS["tax_withholding"].search(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "TAX_WITHHOLDING", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="TAX_WITHHOLDING",
                    amount=amount,
                    currency=detected_currency if amount else None,
                    frequency=detected_freq if amount else None,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["tax_withholding"]),
                    completeness_note=None,  # No completeness warning for absent withholding amount
                ))

            # 7. Deductions / Liquidated Damages (Non-tax deductions)
            if is_non_tax_deduction(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "DEDUCTION", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="DEDUCTION",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["deduction"]),
                ))

            # 7. Probation Compensation
            if FINANCIAL_PATTERNS["probation_comp"].search(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "PROBATION_COMPENSATION", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="PROBATION_COMPENSATION",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["probation_comp"]),
                ))

            # 8. Termination Monetary Provisions
            if FINANCIAL_PATTERNS["termination_comp"].search(text):
                amount = monies[0] if monies else None
                add_item(FinancialItem(
                    item_id=generate_financial_item_id(document_id, "TERMINATION_MONETARY", clause.id, amount or ""),
                    document_id=document_id,
                    item_type="TERMINATION_MONETARY",
                    amount=amount,
                    currency=detected_currency,
                    frequency=detected_freq,
                    condition=extracted_cond,
                    effective_date=effective_dt,
                    payment_timing=extracted_timing,
                    clause_id=clause.id,
                    section_path=clause.metadata.section_path or "General",
                    page=clause.metadata.page,
                    evidence_text=self._snippet(text, FINANCIAL_PATTERNS["termination_comp"]),
                ))

        # Sort deterministically by page and item_id
        items.sort(key=lambda item: (item.page, item.item_id))

        logger.info(
            "Financial intelligence analysis complete: %d items extracted from %d clauses.",
            len(items), len(clauses)
        )
        return items

    def _snippet(self, text: str, pattern: re.Pattern) -> str:
        match = pattern.search(text)
        if not match:
            return text[:150].strip()

        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet.strip()


def analyze_document_financials(document_id: str, clauses: List[Clause]) -> List[FinancialItem]:
    engine = FinancialEngine()
    return engine.analyze_document_financials(clauses, document_id)
