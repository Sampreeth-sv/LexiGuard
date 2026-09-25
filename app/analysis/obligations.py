import re
from typing import List

OBLIGATION_VERBS = re.compile(
    r'\b(shall|must|agrees?\s+to|is\s+required\s+to|will\s+(?!not)|undertakes?\s+to)\b',
    re.IGNORECASE
)

def extract_obligation_sentences(text: str) -> List[str]:
    """
    Extract sentences from text that contain obligation language.
    Returns a list of obligation sentences (max 200 chars each).
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    obligations = []
    for sentence in sentences:
        if OBLIGATION_VERBS.search(sentence):
            cleaned = sentence.strip()
            if len(cleaned) > 200:
                cleaned = cleaned[:197] + "..."
            if cleaned:
                obligations.append(cleaned)
    return obligations

def summarize_obligations(clauses: list) -> List[dict]:
    """
    For a list of Clause objects, return a list of
    {'clause_id': ..., 'section_path': ..., 'obligations': [...]} dicts.
    """
    summary = []
    for clause in clauses:
        obs = extract_obligation_sentences(clause.text)
        if obs:
            summary.append({
                'clause_id': clause.id,
                'section_path': getattr(clause, 'section_path', ''),
                'obligations': obs
            })
    return summary
