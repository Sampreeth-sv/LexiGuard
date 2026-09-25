"""
Deterministic risk signal detection engine for LexiGuard.
Runs 17-category regex pattern rules against clause text.
Zero LLM calls. Fully deterministic and testable.
"""
from typing import List
from app.models.schemas import Clause, RiskSignal
from app.analysis.rules import ALL_RULES
import uuid
import logging
import re

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Deterministic rule-based engine for detecting legal risk signals.
    Applies all defined rules to each clause and returns structured RiskSignal objects.
    """

    def __init__(self) -> None:
        self.rules = ALL_RULES
        logger.info("RiskEngine initialized with %d rules.", len(self.rules))

    def analyze_clause(self, clause: Clause) -> List[RiskSignal]:
        """
        Run all rules against a single Clause object.
        Returns list of detected RiskSignals.
        Each rule can produce at most one signal per clause (deduplication at rule level).
        No LLM calls.
        """
        signals: List[RiskSignal] = []
        for rule in self.rules:
            patterns = rule.get_compiled_patterns()
            for pattern in patterns:
                match = pattern.search(clause.text)
                if match:
                    evidence = self._extract_matched_text(pattern, clause.text)
                    signal = RiskSignal(
                        id=str(uuid.uuid4()),
                        clause_id=clause.id,
                        document_id=clause.metadata.document_id,
                        category=rule.category,
                        severity=rule.severity,
                        matched_pattern=rule.rule_id,
                        evidence_text=evidence,
                        section_path=clause.metadata.section_path,
                        page=clause.metadata.page,
                        plain_explanation=rule.explanation_template,
                        question_to_ask=rule.question_template,
                    )
                    signals.append(signal)
                    break  # One signal per rule per clause
        return signals

    def analyze_document(self, clauses: List[Clause], document_id: str) -> List[RiskSignal]:
        """
        Run risk analysis across all clauses in a document.
        Returns all detected signals.
        Deduplicates overlapping signals from the same clause+category combination.
        """
        all_signals: List[RiskSignal] = []
        seen: set = set()  # (clause_id, category) deduplication

        for clause in clauses:
            signals = self.analyze_clause(clause)
            for sig in signals:
                key = (sig.clause_id, sig.category)
                if key not in seen:
                    seen.add(key)
                    all_signals.append(sig)

        logger.info(
            "Risk analysis complete: %d signals across %d clauses.",
            len(all_signals), len(clauses)
        )
        return all_signals

    def _extract_matched_text(self, pattern: re.Pattern, text: str) -> str:
        """
        Extract a short quoted snippet (max 150 chars) centered around the regex match.
        Used as evidence_text in RiskSignal.
        """
        match = pattern.search(text)
        if not match:
            return text[:150]

        start_idx = match.start()
        end_idx = match.end()

        snippet_start = max(0, start_idx - 60)
        snippet_end = min(len(text), end_idx + 60)

        snippet = text[snippet_start:snippet_end]

        if snippet_start > 0:
            snippet = '...' + snippet
        if snippet_end < len(text):
            snippet = snippet + '...'

        return snippet.strip()
