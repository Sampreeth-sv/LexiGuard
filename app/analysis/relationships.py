"""
Deterministic Clause Relationship & Asymmetry Detection Engine for LexiGuard.
Parses extracted document clauses and metadata to detect structural relationships,
missing counterparts, and potential asymmetries.
Zero LLM / Gemini calls during detection. Fully deterministic and testable.
"""
import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.models.schemas import (
    Clause,
    ClauseRelationship,
    ClauseRelationshipStatus,
    ClauseRelationshipType,
)

logger = logging.getLogger(__name__)

# Patterns for relationship detection
PATTERNS = {
    "termination": re.compile(r'\b(terminat|cancellation|exit the agreement|resignation)\b', re.IGNORECASE),
    "notice": re.compile(r'\b(\d+\s*days?\s*(?:written\s*)?notice|written notice|prior notice|notice period)\b', re.IGNORECASE),
    "obligation": re.compile(r'\b(shall|must|agrees to|is required to|undertakes to)\b', re.IGNORECASE),
    "deadline": re.compile(r'\b(within\s+\d+\s*(?:days|business days|months|weeks)|no later than|by\s+[A-Z][a-z]+\s+\d+|deadline)\b', re.IGNORECASE),
    "payment": re.compile(r'\b(payment|fee|invoice|remunerat|compensation|pay\s+the)\b', re.IGNORECASE),
    "payment_deadline": re.compile(r'\b(due within|net\s*\d+|payable within|due date|upon receipt of invoice)\b', re.IGNORECASE),
    "confidentiality": re.compile(r'\b(confidential|non-disclosure|proprietary information)\b', re.IGNORECASE),
    "survival": re.compile(r'\b(survive|survival|continue after termination|survive for \d+ years|indefinite survival)\b', re.IGNORECASE),
    "indemnity": re.compile(r'\b(indemnify|hold harmless|indemnification)\b', re.IGNORECASE),
    "liability_cap": re.compile(r'\b(limitation of liability|aggregate liability|maximum liability|cap on liability)\b', re.IGNORECASE),
    "cap_exclusion": re.compile(r'\b(excluding indemnification|shall not apply to|except for indemnification|carve-out|claims arising under section)\b', re.IGNORECASE),
    "reciprocal_marker": re.compile(r'\b(each party|both parties|mutual|mutually|reciprocal)\b', re.IGNORECASE),
    "condition_prereq": re.compile(r'\b(provided that|subject to|in the event of breach|liquidated damages|penalty)\b', re.IGNORECASE),
}


def generate_relationship_id(document_id: str, rel_type: str, source_id: str, related_id: Optional[str]) -> str:
    key = f"{document_id}:{rel_type}:{source_id}:{related_id or 'none'}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


class RelationshipEngine:
    """
    Deterministic engine for detecting clause relationships, missing counterparts, and structural asymmetries.
    Zero LLM calls. Fully deterministic.
    """

    def analyze_document_relationships(
        self,
        clauses: List[Clause],
        document_id: str
    ) -> List[ClauseRelationship]:
        """
        Analyze structured document clauses and return a list of detected ClauseRelationships.
        Guarantees deterministic output and dual-clause provenance tracking.
        """
        if not clauses:
            return []

        relationships: List[ClauseRelationship] = []
        seen_keys: set = set()

        def add_relationship(rel: ClauseRelationship):
            rel_type_val = rel.relationship_type.value if hasattr(rel.relationship_type, 'value') else str(rel.relationship_type)
            rel.relationship_id = generate_relationship_id(document_id, rel_type_val, rel.source_clause_id, rel.related_clause_id)
            key = (rel_type_val, rel.source_clause_id, rel.related_clause_id)
            if key not in seen_keys:
                seen_keys.add(key)
                relationships.append(rel)

        # ── 1. TERMINATION ↔ NOTICE ───────────────────────────────────────────
        term_clauses = [
            c for c in clauses
            if c.clause_type in ("termination", "cancellation") or PATTERNS["termination"].search(c.text)
        ]
        notice_clauses = [
            c for c in clauses
            if c.clause_type in ("notice", "notice_period") or PATTERNS["notice"].search(c.text)
        ]

        for term_c in term_clauses:
            # Check if term_c itself contains notice language
            notice_match_in_term = PATTERNS["notice"].search(term_c.text)
            matching_notice_c = next((nc for nc in notice_clauses if nc.id != term_c.id), None)

            if matching_notice_c:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.TERMINATION_NOTICE,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Termination & Notice Requirement",
                    explanation="A termination right and a corresponding written notice requirement were identified in separate clauses.",
                    verification_question="What notice requirements apply before each termination right can be exercised?",
                    source_clause_id=term_c.id,
                    source_section_path=term_c.metadata.section_path or "General",
                    source_page=term_c.metadata.page,
                    source_excerpt=self._snippet(term_c.text, PATTERNS["termination"]),
                    related_clause_id=matching_notice_c.id,
                    related_section_path=matching_notice_c.metadata.section_path or "General",
                    related_page=matching_notice_c.metadata.page,
                    related_excerpt=self._snippet(matching_notice_c.text, PATTERNS["notice"]),
                ))
            elif notice_match_in_term:
                # Embedded notice requirement within termination clause
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.TERMINATION_NOTICE,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Termination & Embedded Notice Requirement",
                    explanation="A termination right and its associated notice requirement were identified within the same clause.",
                    verification_question="Is the notice timeframe sufficient for the terminating party?",
                    source_clause_id=term_c.id,
                    source_section_path=term_c.metadata.section_path or "General",
                    source_page=term_c.metadata.page,
                    source_excerpt=self._snippet(term_c.text, PATTERNS["termination"]),
                    related_clause_id=None,
                ))
            else:
                # Missing notice counterpart
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.TERMINATION_NOTICE,
                    relationship_status=ClauseRelationshipStatus.MISSING_COUNTERPART,
                    confidence="MEDIUM",
                    title="Termination Provision Without Identified Notice Period",
                    explanation="A termination right was identified, but no corresponding written notice requirement was detected in the analyzed clauses.",
                    verification_question="What notice requirements apply before this termination right can be exercised?",
                    source_clause_id=term_c.id,
                    source_section_path=term_c.metadata.section_path or "General",
                    source_page=term_c.metadata.page,
                    source_excerpt=self._snippet(term_c.text, PATTERNS["termination"]),
                    related_clause_id=None,
                ))

        # ── 2. OBLIGATION ↔ DEADLINE ──────────────────────────────────────────
        deadline_clauses = [
            c for c in clauses
            if c.clause_type == "deadline" or PATTERNS["deadline"].search(c.text)
        ]
        ob_clauses = [
            c for c in clauses
            if c.clause_type in ("obligation", "duties") or (PATTERNS["obligation"].search(c.text) and c.clause_type != "deadline")
        ]

        for ob_c in ob_clauses:
            dl_match_in_ob = PATTERNS["deadline"].search(ob_c.text)
            matching_dl_c = next((dc for dc in deadline_clauses if dc.id != ob_c.id), None)

            if dl_match_in_ob:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.OBLIGATION_DEADLINE,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Obligation & Associated Deadline",
                    explanation="An obligation and its associated deadline or timeframe were identified.",
                    verification_question="What is the specific deadline for completing this obligation?",
                    source_clause_id=ob_c.id,
                    source_section_path=ob_c.metadata.section_path or "General",
                    source_page=ob_c.metadata.page,
                    source_excerpt=self._snippet(ob_c.text, PATTERNS["obligation"]),
                    related_clause_id=None,
                ))
            elif matching_dl_c:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.OBLIGATION_DEADLINE,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="MEDIUM",
                    title="Obligation & Related Deadline Provision",
                    explanation="An obligation and a related deadline provision were identified in separate clauses.",
                    verification_question="Does the deadline provision specifically govern this obligation?",
                    source_clause_id=ob_c.id,
                    source_section_path=ob_c.metadata.section_path or "General",
                    source_page=ob_c.metadata.page,
                    source_excerpt=self._snippet(ob_c.text, PATTERNS["obligation"]),
                    related_clause_id=matching_dl_c.id,
                    related_section_path=matching_dl_c.metadata.section_path or "General",
                    related_page=matching_dl_c.metadata.page,
                    related_excerpt=self._snippet(matching_dl_c.text, PATTERNS["deadline"]),
                ))

        # ── 3. PAYMENT ↔ PAYMENT DEADLINE ─────────────────────────────────────
        pay_dl_clauses = [
            c for c in clauses
            if c.clause_type in ("payment_terms", "payment_deadline") or PATTERNS["payment_deadline"].search(c.text)
        ]
        pay_clauses = [
            c for c in clauses
            if c.clause_type in ("payment", "fees", "compensation") or (PATTERNS["payment"].search(c.text) and c.clause_type not in ("payment_terms", "payment_deadline"))
        ]

        for pay_c in pay_clauses:
            pay_dl_in_clause = PATTERNS["payment_deadline"].search(pay_c.text)
            matching_pay_dl = next((pdc for pdc in pay_dl_clauses if pdc.id != pay_c.id), None)

            if pay_dl_in_clause or matching_pay_dl:
                related_c = matching_pay_dl if (matching_pay_dl and not pay_dl_in_clause) else None
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.PAYMENT_DEADLINE,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Payment Obligation & Payment Deadline",
                    explanation="A payment obligation and a corresponding payment deadline were identified in the document.",
                    verification_question="What is the grace period or penalty if payment is not made by the deadline?",
                    source_clause_id=pay_c.id,
                    source_section_path=pay_c.metadata.section_path or "General",
                    source_page=pay_c.metadata.page,
                    source_excerpt=self._snippet(pay_c.text, PATTERNS["payment"]),
                    related_clause_id=related_c.id if related_c else None,
                    related_section_path=related_c.metadata.section_path if related_c else None,
                    related_page=related_c.metadata.page if related_c else None,
                    related_excerpt=self._snippet(related_c.text, PATTERNS["payment_deadline"]) if related_c else None,
                ))

        # ── 4. CONFIDENTIALITY ↔ SURVIVAL ─────────────────────────────────────
        conf_clauses = [
            c for c in clauses
            if c.clause_type in ("confidentiality", "non_disclosure") or PATTERNS["confidentiality"].search(c.text)
        ]
        surv_clauses = [
            c for c in clauses
            if c.clause_type in ("survival", "term_survival") or PATTERNS["survival"].search(c.text)
        ]

        for conf_c in conf_clauses:
            surv_match_in_conf = PATTERNS["survival"].search(conf_c.text)
            matching_surv_c = next((sc for sc in surv_clauses if sc.id != conf_c.id), None)

            if matching_surv_c:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.CONFIDENTIALITY_SURVIVAL,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Confidentiality Obligation & Survival Period",
                    explanation="Confidentiality obligations and a corresponding post-termination survival period were identified in separate clauses.",
                    verification_question="Does the survival period apply to all categories of confidential information?",
                    source_clause_id=conf_c.id,
                    source_section_path=conf_c.metadata.section_path or "General",
                    source_page=conf_c.metadata.page,
                    source_excerpt=self._snippet(conf_c.text, PATTERNS["confidentiality"]),
                    related_clause_id=matching_surv_c.id,
                    related_section_path=matching_surv_c.metadata.section_path or "General",
                    related_page=matching_surv_c.metadata.page,
                    related_excerpt=self._snippet(matching_surv_c.text, PATTERNS["survival"]),
                ))
            elif surv_match_in_conf:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.CONFIDENTIALITY_SURVIVAL,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Confidentiality & Embedded Survival Period",
                    explanation="A confidentiality obligation and its post-termination survival period were identified within the same clause.",
                    verification_question="How long do confidentiality obligations remain in effect after termination?",
                    source_clause_id=conf_c.id,
                    source_section_path=conf_c.metadata.section_path or "General",
                    source_page=conf_c.metadata.page,
                    source_excerpt=self._snippet(conf_c.text, PATTERNS["confidentiality"]),
                    related_clause_id=None,
                ))
            else:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.CONFIDENTIALITY_SURVIVAL,
                    relationship_status=ClauseRelationshipStatus.MISSING_COUNTERPART,
                    confidence="MEDIUM",
                    title="Confidentiality Provision Without Identified Survival Period",
                    explanation="A confidentiality obligation was identified, but no explicit post-termination survival period was identified in the analyzed clauses.",
                    verification_question="Does the confidentiality obligation continue after contract termination, and for how long?",
                    source_clause_id=conf_c.id,
                    source_section_path=conf_c.metadata.section_path or "General",
                    source_page=conf_c.metadata.page,
                    source_excerpt=self._snippet(conf_c.text, PATTERNS["confidentiality"]),
                    related_clause_id=None,
                ))

        # ── 5. INDEMNITY ↔ LIABILITY CAP ──────────────────────────────────────
        indem_clauses = [
            c for c in clauses
            if c.clause_type in ("indemnity", "indemnification") or (
                PATTERNS["indemnity"].search(c.text) and c.clause_type not in ("liability", "limitation_of_liability", "liability_cap")
            )
        ]
        cap_clauses = [
            c for c in clauses
            if c.clause_type in ("liability", "limitation_of_liability", "liability_cap") or PATTERNS["liability_cap"].search(c.text)
        ]


        for indem_c in indem_clauses:
            matching_cap_c = next((cap_c for cap_c in cap_clauses if cap_c.id != indem_c.id), None)

            # Check for explicit cap exclusion wording in cap clause or indemnity clause
            has_exclusion = (
                PATTERNS["cap_exclusion"].search(indem_c.text) or
                (matching_cap_c and PATTERNS["cap_exclusion"].search(matching_cap_c.text))
            )

            if matching_cap_c and has_exclusion:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.INDEMNITY_LIABILITY_CAP,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Indemnification & Liability Cap Exclusion",
                    explanation="An indemnification provision was identified, and liability cap terms explicitly reference an exclusion for indemnification obligations.",
                    verification_question="Are indemnification claims capped or expressly excluded from the liability cap?",
                    source_clause_id=indem_c.id,
                    source_section_path=indem_c.metadata.section_path or "General",
                    source_page=indem_c.metadata.page,
                    source_excerpt=self._snippet(indem_c.text, PATTERNS["indemnity"]),
                    related_clause_id=matching_cap_c.id,
                    related_section_path=matching_cap_c.metadata.section_path or "General",
                    related_page=matching_cap_c.metadata.page,
                    related_excerpt=self._snippet(matching_cap_c.text, PATTERNS["liability_cap"]),
                ))
            elif matching_cap_c:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.INDEMNITY_LIABILITY_CAP,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="HIGH",
                    title="Indemnification & Liability Cap Terms",
                    explanation="An indemnification provision and a general liability cap were identified in separate clauses. Review is required to determine whether indemnification is subject to the cap.",
                    verification_question="Does the general liability cap apply to indemnification obligations?",
                    source_clause_id=indem_c.id,
                    source_section_path=indem_c.metadata.section_path or "General",
                    source_page=indem_c.metadata.page,
                    source_excerpt=self._snippet(indem_c.text, PATTERNS["indemnity"]),
                    related_clause_id=matching_cap_c.id,
                    related_section_path=matching_cap_c.metadata.section_path or "General",
                    related_page=matching_cap_c.metadata.page,
                    related_excerpt=self._snippet(matching_cap_c.text, PATTERNS["liability_cap"]),
                ))
            else:
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.INDEMNITY_LIABILITY_CAP,
                    relationship_status=ClauseRelationshipStatus.INCOMPLETE_RELATIONSHIP,
                    confidence="MEDIUM",
                    title="Indemnification Without Identified Liability Cap",
                    explanation="An indemnification obligation was identified, but no general limitation of liability or cap clause was detected in the document.",
                    verification_question="Is there an overall cap on liability that applies to indemnification obligations?",
                    source_clause_id=indem_c.id,
                    source_section_path=indem_c.metadata.section_path or "General",
                    source_page=indem_c.metadata.page,
                    source_excerpt=self._snippet(indem_c.text, PATTERNS["indemnity"]),
                    related_clause_id=None,
                ))

        # ── 6. PARTY OBLIGATION ASYMMETRY (VERY CONSERVATIVE) ─────────────────
        # RULE: Only generate asymmetry if explicit reciprocal intent markers exist
        # ("each party", "both parties", "mutual", "reciprocal")
        for c in clauses:
            if PATTERNS["reciprocal_marker"].search(c.text):
                # Reciprocal marker present — check if clause describes a unilateral restriction
                if c.clause_type in {"non_compete", "confidentiality", "ip", "obligation"}:
                    add_relationship(ClauseRelationship(
                        document_id=document_id,
                        relationship_type=ClauseRelationshipType.PARTY_OBLIGATION_ASYMMETRY,
                        relationship_status=ClauseRelationshipStatus.POTENTIAL_ASYMMETRY,
                        confidence="HIGH",
                        title="Potential Asymmetric Obligation Pattern",
                        explanation="An obligation with reciprocal intent markers (e.g. mutual obligations) was identified for one party, requiring verification of counterparty reciprocity.",
                        verification_question="Is the difference in obligations intentional and expected in this agreement?",
                        source_clause_id=c.id,
                        source_section_path=c.metadata.section_path or "General",
                        source_page=c.metadata.page,
                        source_excerpt=self._snippet(c.text, PATTERNS["reciprocal_marker"]),
                        related_clause_id=None,
                    ))

        # ── 7. RIGHT ↔ CONDITION / CONSEQUENCE ────────────────────────────────
        for c in clauses:
            if PATTERNS["condition_prereq"].search(c.text):
                add_relationship(ClauseRelationship(
                    document_id=document_id,
                    relationship_type=ClauseRelationshipType.RIGHT_CONDITION,
                    relationship_status=ClauseRelationshipStatus.BALANCED_RELATIONSHIP,
                    confidence="MEDIUM",
                    title="Contractual Right & Conditional Prerequisite",
                    explanation="A contractual right or consequence and its conditional prerequisite were identified in the clause text.",
                    verification_question="Have all conditions precedent been satisfied prior to exercising this right?",
                    source_clause_id=c.id,
                    source_section_path=c.metadata.section_path or "General",
                    source_page=c.metadata.page,
                    source_excerpt=self._snippet(c.text, PATTERNS["condition_prereq"]),
                    related_clause_id=None,
                ))

        # Sort deterministically by page and source_clause_id
        relationships.sort(key=lambda r: (r.source_page, r.source_clause_id, r.relationship_type.value))

        logger.info(
            "Relationship analysis complete: %d relationships detected across %d clauses.",
            len(relationships), len(clauses)
        )
        return relationships

    def _snippet(self, text: str, pattern: re.Pattern, pre_match: Optional[re.Match] = None) -> str:
        """Extract a clean 150-char snippet around the regex pattern match."""
        match = pre_match if pre_match is not None else pattern.search(text)
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


def analyze_clause_relationships(
    document_id: str,
    clauses: List[Clause]
) -> List[ClauseRelationship]:
    """Helper wrapper function to run RelationshipEngine analysis."""
    engine = RelationshipEngine()
    return engine.analyze_document_relationships(clauses, document_id)

