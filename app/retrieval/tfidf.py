from typing import List, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from app.models.schemas import Clause
import logging

logger = logging.getLogger(__name__)

class TFIDFIndex:
    """
    In-memory TF-IDF index for a set of clauses.
    Built once per document. Lives in Python process memory.
    No files written to disk.
    """
    
    def __init__(self):
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.matrix = None  # sparse matrix
        self.clauses: List[Clause] = []
    
    def build(self, clauses: List[Clause]) -> None:
        """Build TF-IDF index from clause list. Unigrams + bigrams, sublinear TF."""
        self.clauses = clauses
        if not clauses:
            self.vectorizer = None
            self.matrix = None
            return
            
        texts = [c.text for c in clauses]
        self.vectorizer = TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True, max_features=5000, stop_words='english')
        self.matrix = self.vectorizer.fit_transform(texts)
    
    def search(self, query: str, top_k: int = 8) -> List[Tuple[Clause, float]]:
        """
        Search the index for query.
        Returns top_k (clause, cosine_score) tuples.
        Returns empty list if index not built or no results above threshold.
        """
        if not self.is_built() or not query.strip():
            return []
            
        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.matrix).flatten()
        
        # Get indices of top results
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.0:
                results.append((self.clauses[idx], score))
                
        return results
    
    def is_built(self) -> bool:
        """Return True if index has been built."""
        return self.vectorizer is not None and self.matrix is not None
