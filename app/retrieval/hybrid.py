from typing import List, Tuple, Optional, Set
import heapq
from app.models.schemas import Clause
from app.retrieval.lexical import compute_lexical_score, normalize_query
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

def compute_structural_score(query: str, clause: Clause, query_terms: Optional[Set[str]] = None, struct_terms: Optional[Set[str]] = None) -> float:
    """Score based on heading/section_path match with query terms. Returns 0.0-1.0."""
    if not query:
        return 0.0
    if query_terms is None:
        query_terms = set(re.findall(r'\w+', query.lower()))
    if not query_terms:
        return 0.0

    if struct_terms is None:
        structural_text = f"{clause.heading} {clause.section_path}".lower()
        struct_terms = set(re.findall(r'\w+', structural_text))
    
    if not struct_terms:
        return 0.0
        
    overlap = query_terms.intersection(struct_terms)
    return len(overlap) / len(query_terms)

def compute_clause_type_score(query: str, clause: Clause, query_terms: Optional[Set[str]] = None, type_terms: Optional[Set[str]] = None) -> float:
    """Score based on clause_type match with query terms. Returns 0.0-1.0."""
    if not query or (type_terms is None and not clause.clause_type):
        return 0.0
    if query_terms is None:
        query_terms = set(re.findall(r'\w+', query.lower()))
    if not query_terms:
        return 0.0

    if type_terms is None:
        type_terms = set(re.findall(r'\w+', clause.clause_type.lower())) if clause.clause_type else set()
    
    if not type_terms:
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

    # Pre-compute query structures once per hybrid search call
    norm_expanded_q = normalize_query(expanded_q)
    exp_q_tokens = norm_expanded_q.split()
    exp_q_set = set(exp_q_tokens) if exp_q_tokens else set()

    orig_query_terms = set(re.findall(r'\w+', query.lower()))

    # Pre-extract clause structural and type terms once across target clauses
    clause_struct_map = {}
    clause_type_map = {}
    for c in clauses:
        s_text = f"{c.heading or ''} {c.section_path or ''}".lower()
        clause_struct_map[c.id] = set(re.findall(r'\w+', s_text))
        clause_type_map[c.id] = set(re.findall(r'\w+', c.clause_type.lower())) if c.clause_type else set()

    scored_clauses = []
    w_lex = settings.weight_lexical
    w_tf = settings.weight_tfidf
    w_struct = settings.weight_structural
    w_type = settings.weight_clause_type
    min_score = settings.retrieval_min_score

    for clause in clauses:
        c_id = clause.id
        lex_score = compute_lexical_score(expanded_q, clause, normalized_query=norm_expanded_q, query_set=exp_q_set)
        tf_score = tfidf_results.get(c_id, 0.0)
        struct_score = compute_structural_score(query, clause, query_terms=orig_query_terms, struct_terms=clause_struct_map[c_id])
        type_score = compute_clause_type_score(query, clause, query_terms=orig_query_terms, type_terms=clause_type_map[c_id])
        
        combined_score = (
            lex_score * w_lex +
            tf_score * w_tf +
            struct_score * w_struct +
            type_score * w_type
        )
        
        if combined_score >= min_score:
            scored_clauses.append((clause, combined_score))
            
    if len(scored_clauses) > top_k:
        return heapq.nlargest(top_k, scored_clauses, key=lambda x: x[1])
    
    scored_clauses.sort(key=lambda x: x[1], reverse=True)
    return scored_clauses
