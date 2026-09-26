import re
from typing import List, Tuple, Optional
from app.models.schemas import Clause

def normalize_query(query: str) -> str:
    """Lowercase, strip punctuation, normalize whitespace."""
    query = query.lower()
    query = re.sub(r'[^\w\s]', ' ', query)
    query = re.sub(r'\s+', ' ', query)
    return query.strip()

def compute_lexical_score(
    query: str,
    clause: Clause,
    normalized_query: Optional[str] = None,
    query_set: Optional[set] = None,
) -> float:
    """
    Compute lexical overlap score between query and clause text.
    Returns float 0.0 - 1.0.
    
    Algorithm:
    1. Tokenize both query and clause text
    2. Compute unigram overlap: intersection / len(query_tokens)
    3. Check for exact phrase matches (boost by 0.3 per match)
    4. Cap at 1.0
    """
    if not query or not clause.text:
        return 0.0

    if normalized_query is None:
        normalized_query = normalize_query(query)
    
    if query_set is None:
        query_tokens = normalized_query.split()
        if not query_tokens:
            return 0.0
        query_set = set(query_tokens)
    elif not query_set:
        return 0.0

    normalized_clause = normalize_query(clause.text)
    clause_tokens = normalized_clause.split()
    if not clause_tokens:
        return 0.0
        
    clause_set = set(clause_tokens)
    
    overlap = query_set.intersection(clause_set)
    unigram_score = len(overlap) / len(query_set)
    
    # Exact phrase match boost
    phrase_boost = 0.0
    if normalized_query in normalized_clause:
        phrase_boost = 0.3
        
    final_score = min(1.0, unigram_score + phrase_boost)
    return final_score

def search_lexical(query: str, clauses: List[Clause], top_k: int = 8) -> List[Tuple[Clause, float]]:
    """Return top_k (clause, score) tuples by lexical score."""
    if not query or not clauses:
        return []
    
    norm_q = normalize_query(query)
    q_tokens = norm_q.split()
    if not q_tokens:
        return []
    q_set = set(q_tokens)

    scored_clauses = []
    for clause in clauses:
        score = compute_lexical_score(query, clause, normalized_query=norm_q, query_set=q_set)
        if score > 0.0:
            scored_clauses.append((clause, score))
            
    scored_clauses.sort(key=lambda x: x[1], reverse=True)
    return scored_clauses[:top_k]
