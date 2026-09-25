import re
from typing import List
from app.models.schemas import Clause

# Date patterns: January 1, 2024 / 01 January 2024 / 01/01/2024 / 2024-01-01 / January 2024
DATE_PATTERNS = [
    re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', re.IGNORECASE),
    re.compile(r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b', re.IGNORECASE),
    re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'),
    re.compile(r'\b\d{4}-\d{2}-\d{2}\b'),
    re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b', re.IGNORECASE),
]

# Money patterns supporting Indian (₹9,00,000 / Rs 9,00,000 / INR 9,00,000 / ₹12,50,000.50) and Western ($1,000,000.00 / €1,200) formatting
MONEY_PATTERNS = [
    re.compile(r'(?:₹|INR|Rs\.?)\s*\d+(?:,\d{2,3})*(?:\.\d{1,2})?', re.IGNORECASE),
    re.compile(r'\$\s*\d+(?:,\d{2,3})*(?:\.\d{1,2})?'),
    re.compile(r'USD\s*\d+(?:,\d{2,3})*(?:\.\d{1,2})?', re.IGNORECASE),
    re.compile(r'[£€¥]\s*\d+(?:,\d{2,3})*(?:\.\d{1,2})?'),
    re.compile(r'\b\d+(?:,\d{2,3})*(?:\.\d{1,2})?\s*(?:dollars|USD|euros|EUR|pounds|GBP|rupees|INR|lakhs?|crores?)\b', re.IGNORECASE),
    re.compile(r'\b\d{1,3}(?:,\d{2,3})+\b'),
]

def extract_dates(text: str) -> List[str]:
    raw_dates = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            val = match.group(0).strip()
            if val and val not in raw_dates:
                raw_dates.append(val)

    # Deduplicate: filter out partial date substring matches when a more specific date is present
    # e.g., "October 2026" matched inside "1 October 2026"
    final_dates = []
    for d in raw_dates:
        is_sub = any(
            (d.lower() != other.lower() and d.lower() in other.lower())
            for other in raw_dates
        )
        if not is_sub and d not in final_dates:
            final_dates.append(d)

    return final_dates

def extract_monetary_values(text: str) -> List[str]:
    monies = []
    seen = set()
    for pattern in MONEY_PATTERNS:
        for match in pattern.finditer(text):
            val = match.group(0).strip()
            if val and val not in seen:
                seen.add(val)
                monies.append(val)
    return monies

def normalize_monetary_amount(val: str) -> str:
    """
    Normalize monetary string into plain numeric representation.
    Examples:
      ₹9,00,000    → 900000
      Rs 9,00,000  → 900000
      Rs. 9,00,000 → 900000
      INR 9,00,000 → 900000
      ₹12,50,000.50 → 1250000.50
    """
    if not val:
        return ""
    # Strip currency prefixes like "Rs.", "Rs", "INR", "$", "₹"
    val_clean = re.sub(r'^(?:₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP)\s*', '', val, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'[^\d.]', '', val_clean)
    if cleaned.endswith('.00'):
        cleaned = cleaned[:-3]
    return cleaned

def extract_parties(clauses: List[Clause]) -> List[str]:
    parties = []
    # typically parties are found in the first few clauses, looks like "between X and Y"
    pattern = re.compile(r'(?:between|by and between|among)\s+(.+?)\s+(?:and|&)\s+(.+?)(?:,|\.|\n|dated)', re.IGNORECASE)
    for clause in clauses[:5]:
        match = pattern.search(clause.text)
        if match:
            for group in match.groups():
                cleaned = re.sub(r'\(.*?\)', '', group).strip()
                if cleaned:
                    parties.append(cleaned)
    return list(set(parties))

def extract_obligations(text: str) -> List[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    ob_pattern = re.compile(r'\b(shall|must|agrees?\s+to|is\s+required\s+to|will)\b', re.IGNORECASE)
    obligations = []
    for sentence in sentences:
        if ob_pattern.search(sentence):
            obligations.append(sentence.strip())
    return obligations

def detect_document_type(clauses: List[Clause]) -> str:
    """
    Conservatively classify document type based on clause evidence.
    Classifications:
      - Employment
      - NDA
      - Commercial/Project
      - Terms & Conditions
      - General Legal/Business Document
      - Unknown
    Returns 'General Legal/Business Document' if evidence is insufficient or ambiguous.
    """
    if not clauses:
        return "Unknown"

    full_text = " ".join(c.text for c in clauses[:10]).lower()

    if any(term in full_text for term in ["offer letter", "employment agreement", "employment contract", "position of", "probation period", "annual salary", "joining bonus"]):
        return "Employment"
    if any(term in full_text for term in ["non-disclosure agreement", "confidentiality agreement", "disclosing party", "receiving party", "proprietary information agreement"]):
        return "NDA"
    if any(term in full_text for term in ["master services agreement", "statement of work", "service level agreement", "consulting agreement", "vendor agreement"]):
        return "Commercial/Project"
    if any(term in full_text for term in ["terms of service", "terms and conditions", "privacy policy", "end user license", "eula"]):
        return "Terms & Conditions"

    return "General Legal/Business Document"

def classify_date_context(date_str: str, clause_text: str) -> str:
    """
    Categorize a date based on surrounding clause text context.
    Categories:
      - deadline
      - notice_period
      - renewal_date
      - payment_date
      - probation_service_period
      - temporal_obligation
    """
    text_lower = clause_text.lower()
    if any(k in text_lower for k in ["notice", "days prior", "advance notice", "written notice"]):
        return "notice_period"
    if any(k in text_lower for k in ["renew", "automatic renewal", "expiration date", "expiry"]):
        return "renewal_date"
    if any(k in text_lower for k in ["pay", "due date", "invoice", "payable", "salary", "compensation"]):
        return "payment_date"
    if any(k in text_lower for k in ["probation", "minimum service", "service period", "bond"]):
        return "probation_service_period"
    if any(k in text_lower for k in ["deadline", "due on or before", "no later than"]):
        return "deadline"
    return "temporal_obligation"

