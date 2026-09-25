from typing import List, Tuple
from app.models.schemas import Clause

def rerank(
    results: List[Tuple[Clause, float]],
    query: str,
    top_k: int = 8,
    max_total_chars: int = 8000,
) -> List[Tuple[Clause, float]]:
    """
    Post-retrieval reranking and context trimming.
    
    Steps:
    1. Remove exact duplicate clause texts.
    2. Prefer complete clauses over very short fragments (<50 chars).
    3. Prefer clauses that contain query terms in their heading.
    4. Sort by combined score descending.
    5. Trim to top_k results.
    6. Trim total chars to max_total_chars (drop lowest scoring if needed).
    
    Returns reranked list of (clause, score) tuples.
    """
    if not results:
        return []

    query_terms = set(query.lower().split())
    seen_texts = set()
    deduped = []
    
    # 1. Remove exact duplicate clause texts
    for clause, score in results:
        if clause.text not in seen_texts:
            seen_texts.add(clause.text)
            deduped.append((clause, score))
            
    adjusted = []
    for clause, score in deduped:
        new_score = score
        
        # 2. Penalize very short fragments
        if len(clause.text) < 50:
            new_score *= 0.5
            
        # 3. Boost clauses that contain query terms in their heading
        if clause.heading:
            heading_terms = set(clause.heading.lower().split())
            if query_terms.intersection(heading_terms):
                new_score *= 1.2
                
        adjusted.append((clause, new_score))
        
    # 4. Sort by combined score descending
    adjusted.sort(key=lambda x: x[1], reverse=True)
    
    # 5. Trim to top_k
    top_results = adjusted[:top_k]
    
    # 6. Trim total chars
    final_results = []
    total_chars = 0
    for clause, score in top_results:
        if total_chars + len(clause.text) <= max_total_chars:
            final_results.append((clause, score))
            total_chars += len(clause.text)
        else:
            # Reached char limit
            break
            
    return final_results
