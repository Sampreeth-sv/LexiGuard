from typing import List, Tuple
from app.models.schemas import Clause
from app.retrieval.lexical import compute_lexical_score
from app.retrieval.tfidf import TFIDFIndex
from app.config import settings
import logging
import re

logger = logging.getLogger(__name__)

# Legal term synonyms for query expansion
LEGAL_SYNONYMS: dict = {
    'terminate': ['termination', 'cancel', 'cancellation', 'end', 'exit'],
    'renew': ['renewal', 'auto-renew', 'automatically renew', 'evergreen'],
    'indemnify': ['indemnification', 'hold harmless', 'defend'],
    'liability': ['liable', 'responsible', 'damages', 'limitation of liability'],
    'arbitration': ['arbitrate', 'dispute resolution', 'binding arbitration'],
    'confidential': ['confidentiality', 'non-disclosure', 'NDA', 'proprietary'],
    'payment': ['pay', 'invoice', 'fees', 'compensation', 'remuneration'],
    'intellectual property': ['IP', 'copyright', 'patent', 'trademark', 'work product'],
    'govern': ['governing law', 'jurisdiction', 'applicable law'],
}

def expand_query(query: str) -> str:
    """Expand query using legal synonym dictionary."""
    expanded_terms = set(query.lower().split())
    
    for term in list(expanded_terms):
        for key, synonyms in LEGAL_SYNONYMS.items():
            if term == key or term in synonyms:
                expanded_terms.add(key)
                expanded_terms.update(synonyms)
                
    return " ".join(expanded_terms)

def compute_structural_score(query: str, clause: Clause) -> float:
    """Score based on heading/section_path match with query terms. Returns 0.0-1.0."""
    if not query:
        return 0.0
    query_terms = set(re.findall(r'\w+', query.lower()))
    structural_text = f"{clause.heading} {clause.section_path}".lower()
    structural_terms = set(re.findall(r'\w+', structural_text))
    
    if not query_terms or not structural_terms:
        return 0.0
        
    overlap = query_terms.intersection(structural_terms)
    return len(overlap) / len(query_terms)

def compute_clause_type_score(query: str, clause: Clause) -> float:
    """Score based on clause_type match with query terms. Returns 0.0-1.0."""
    if not query or not clause.clause_type:
        return 0.0
    query_terms = set(re.findall(r'\w+', query.lower()))
    type_terms = set(re.findall(r'\w+', clause.clause_type.lower()))
    
    if not query_terms or not type_terms:
        return 0.0
        
    overlap = query_terms.intersection(type_terms)
    return len(overlap) / len(query_terms)

def hybrid_search(
    query: str,
    clauses: List[Clause],
    tfidf_index: TFIDFIndex,
    top_k: int | None = None,
) -> List[Tuple[Clause, float]]:
    """
    Main retrieval function.
    Combines:
      - lexical score (weight from settings.weight_lexical)
      - TF-IDF score (weight from settings.weight_tfidf)
      - structural score (weight from settings.weight_structural)
      - clause type score (weight from settings.weight_clause_type)
    Returns top_k (clause, combined_score) tuples above min_score threshold.
    All weights come from settings (config.py), not hardcoded.
    """
    if not clauses or not query:
        return []
        
    if top_k is None:
        top_k = settings.retrieval_top_k
        
    expanded_q = expand_query(query)
    
    # Pre-compute TF-IDF scores indexed by clause ID for O(1) lookup
    tfidf_raw = tfidf_index.search(expanded_q, top_k=len(clauses))
    tfidf_results: dict = {c.id: score for c, score in tfidf_raw}

    scored_clauses = []
    for clause in clauses:
        lex_score = compute_lexical_score(expanded_q, clause)
        tf_score = tfidf_results.get(clause.id, 0.0)
        struct_score = compute_structural_score(query, clause) # original query for exact struct matches
        type_score = compute_clause_type_score(query, clause)
        
        combined_score = (
            lex_score * settings.weight_lexical +
            tf_score * settings.weight_tfidf +
            struct_score * settings.weight_structural +
            type_score * settings.weight_clause_type
        )
        
        if combined_score >= settings.retrieval_min_score:
            scored_clauses.append((clause, combined_score))
            
    scored_clauses.sort(key=lambda x: x[1], reverse=True)
    return scored_clauses[:top_k]
