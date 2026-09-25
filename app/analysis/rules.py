from dataclasses import dataclass, field
from typing import List, Pattern
import re
from app.models.schemas import Severity

@dataclass
class RiskRule:
    rule_id: str
    category: str
    display_name: str
    severity: Severity
    patterns: List[str]  # raw regex strings
    explanation_template: str  # plain language explanation
    question_template: str  # suggested lawyer question
    
    def get_compiled_patterns(self) -> List[Pattern]:
        return [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.patterns]

AUTO_RENEWAL_001 = RiskRule(
    rule_id="AUTO_RENEWAL_001",
    category="renewal",
    display_name="Automatic Renewal",
    severity=Severity.MEDIUM,
    patterns=[r'automatically\s+renew', r'auto.?renew', r'renewal\s+term', r'shall\s+renew', r'evergreen\s+clause'],
    explanation_template="The agreement appears to renew automatically unless proper notice of cancellation is provided before the renewal deadline.",
    question_template="What is the required notice period to prevent automatic renewal, and when does it begin?"
)

TERMINATION_RESTRICTION_001 = RiskRule(
    rule_id="TERMINATION_RESTRICTION_001",
    category="termination",
    display_name="Termination Restriction",
    severity=Severity.HIGH,
    patterns=[r'sole\s+discretion.*terminat', r'without\s+cause.*terminat', r'penalty.*early\s+terminat', r'liquidated\s+damages.*terminat'],
    explanation_template="The agreement may include restrictions on when or how it can be terminated, or penalties for early termination.",
    question_template="Under what conditions can I terminate this agreement, and are there financial penalties for doing so?"
)

BROAD_INDEMNIFICATION_001 = RiskRule(
    rule_id="BROAD_INDEMNIFICATION_001",
    category="indemnity",
    display_name="Broad Indemnification",
    severity=Severity.HIGH,
    patterns=[r'indemnif.*hold\s+harmless', r'defend.*indemnif', r'indemnif.*any\s+(and\s+all)?\s*(loss|claim|damage|cost)', r'hold.*harmless.*from.*any'],
    explanation_template="This clause may require you to protect and pay for another party\'s losses, claims, or legal costs in a broad range of circumstances.",
    question_template="What specific events trigger my indemnification obligation, and is there a cap on my exposure?"
)

LIABILITY_LIMITATION_001 = RiskRule(
    rule_id="LIABILITY_LIMITATION_001",
    category="liability",
    display_name="Liability Limitation",
    severity=Severity.MEDIUM,
    patterns=[r'aggregate\s+liability.*shall\s+not\s+exceed', r'in\s+no\s+event.*liable', r'consequential.*damages.*excluded', r'limitation\s+of\s+liability', r'cap\s+on\s+liability'],
    explanation_template="The agreement may limit the total financial responsibility of one or more parties, potentially capping the amount you could recover if something goes wrong.",
    question_template="What is the liability cap, which party does it apply to, and does it cover all types of damages?"
)

UNILATERAL_MODIFICATION_001 = RiskRule(
    rule_id="UNILATERAL_MODIFICATION_001",
    category="modification",
    display_name="Unilateral Modification",
    severity=Severity.HIGH,
    patterns=[r'reserve.*right.*modify.*at\s+any\s+time', r'may\s+amend.*at\s+(its|their)\s+sole', r'unilateral.*modif', r'change.*terms.*without\s+notice', r'right\s+to\s+change.*terms'],
    explanation_template="One party may have the right to change the terms of this agreement without your consent or with limited notice.",
    question_template="Can the terms be changed without my agreement, and what notice must be given?"
)

ARBITRATION_001 = RiskRule(
    rule_id="ARBITRATION_001",
    category="arbitration",
    display_name="Arbitration clause",
    severity=Severity.MEDIUM,
    patterns=[r'binding\s+arbitration', r'waive.*right.*jury\s+trial', r'class\s+action\s+waiver', r'arbitration.*mandatory', r'dispute.*resolved.*arbitration'],
    explanation_template="Disputes under this agreement may be required to go through arbitration rather than court litigation, and you may be waiving your right to a jury trial or class action.",
    question_template="Am I waiving my right to sue in court or join a class action, and who pays for arbitration?"
)

JURISDICTION_001 = RiskRule(
    rule_id="JURISDICTION_001",
    category="jurisdiction",
    display_name="Jurisdiction / Governing Law",
    severity=Severity.LOW,
    patterns=[r'governed\s+by.*laws\s+of', r'exclusive\s+jurisdiction', r'courts\s+of.*shall\s+have', r'venue.*shall\s+be', r'choice\s+of\s+law'],
    explanation_template="The agreement specifies a particular state or country\'s laws and/or courts for resolving disputes.",
    question_template="Is the governing jurisdiction convenient for me, and what does it mean if disputes must be resolved there?"
)

CONFIDENTIALITY_001 = RiskRule(
    rule_id="CONFIDENTIALITY_001",
    category="confidentiality",
    display_name="Confidentiality",
    severity=Severity.LOW,
    patterns=[r'confidential\s+information', r'non.disclosure', r'proprietary\s+information', r'trade\s+secret', r'shall\s+not\s+disclose'],
    explanation_template="This agreement imposes obligations to keep certain information confidential. Review the scope of what is considered confidential and for how long.",
    question_template="What information is covered, for how long does the obligation last, and what are the exceptions?"
)

NON_COMPETE_001 = RiskRule(
    rule_id="NON_COMPETE_001",
    category="non_compete",
    display_name="Non-Compete",
    severity=Severity.HIGH,
    patterns=[r'shall\s+not.*compete', r'non.competition', r'non.solicitation', r'shall\s+not\s+solicit.*employee', r'restrict.*competitive.*activit'],
    explanation_template="This agreement may restrict your ability to work in competing roles, start a competing business, or solicit employees/clients after the agreement ends.",
    question_template="What activities are restricted, for how long, and in what geographic area?"
)

PAYMENT_OBLIGATION_001 = RiskRule(
    rule_id="PAYMENT_OBLIGATION_001",
    category="payment",
    display_name="Payment Terms",
    severity=Severity.LOW,
    patterns=[r'due\s+within\s+\d+\s+days', r'net\s+\d+', r'payment.*due.*upon', r'invoice.*payable', r'fees.*payable'],
    explanation_template="The agreement specifies payment terms including due dates and amounts.",
    question_template="What are the exact payment amounts, due dates, and accepted payment methods?"
)

LATE_FEE_001 = RiskRule(
    rule_id="LATE_FEE_001",
    category="payment",
    display_name="Late Fee",
    severity=Severity.MEDIUM,
    patterns=[r'late\s+(fee|charge|payment)', r'interest.*per.*month', r'penalty.*overdue', r'\d+%.*per\s+(month|annum).*overdue', r'past\s+due.*interest'],
    explanation_template="Late payments may incur fees or interest charges.",
    question_template="What is the late fee rate, when does it begin accruing, and is there a grace period?"
)

IP_OWNERSHIP_001 = RiskRule(
    rule_id="IP_OWNERSHIP_001",
    category="ip",
    display_name="Intellectual Property Ownership",
    severity=Severity.HIGH,
    patterns=[r'work.*made.*for.*hire', r'assigns?\s+all\s+rights', r'intellectual\s+property.*shall.*belong', r'exclusive.*license.*perpetual', r'assigns?.*copyright'],
    explanation_template="This agreement may transfer ownership of intellectual property you create, or grant broad rights to your work product.",
    question_template="Who owns the intellectual property created under this agreement, and do I retain any rights?"
)

WARRANTY_DISCLAIMER_001 = RiskRule(
    rule_id="WARRANTY_DISCLAIMER_001",
    category="warranty",
    display_name="Warranty Disclaimer",
    severity=Severity.MEDIUM,
    patterns=[r'as.is', r'without.*warranty.*of.*any.*kind', r'disclaim.*all.*warrant', r'merchantabilit', r'fitness.*for.*particular.*purpose'],
    explanation_template="The agreement may disclaim warranties, meaning you accept goods or services without guarantees about their quality or fitness for purpose.",
    question_template="What warranties are being disclaimed, and what remedies do I have if something does not work as expected?"
)

NOTICE_REQUIREMENT_001 = RiskRule(
    rule_id="NOTICE_REQUIREMENT_001",
    category="notice",
    display_name="Notice Requirement",
    severity=Severity.LOW,
    patterns=[r'written\s+notice.*\d+\s+days', r'days.*prior.*written.*notice', r'notice.*shall.*be.*given', r'notice.*period', r'days.*advance.*notice'],
    explanation_template="The agreement requires formal written notice for certain actions. Failure to provide notice within the required period may have consequences.",
    question_template="What actions require written notice, and what is the required notice period for each?"
)

PRIVACY_DATA_001 = RiskRule(
    rule_id="PRIVACY_DATA_001",
    category="privacy",
    display_name="Privacy and Data Protection",
    severity=Severity.MEDIUM,
    patterns=[r'personal\s+data', r'personal\s+information', r'data\s+processing', r'gdpr', r'ccpa', r'privacy\s+policy', r'data\s+protection'],
    explanation_template="This agreement includes provisions related to the collection, use, or processing of personal data.",
    question_template="What personal data is collected, how is it used, who can access it, and how can I request deletion?"
)

BROAD_OBLIGATION_001 = RiskRule(
    rule_id="BROAD_OBLIGATION_001",
    category="obligation",
    display_name="Broad Obligation",
    severity=Severity.MEDIUM,
    patterns=[r'comply.*all\s+applicable.*law', r'unrestricted\s+right', r'all\s+costs.*associated', r'sole\s+responsibility.*for.*all', r'responsible\s+for.*any\s+and\s+all'],
    explanation_template="This clause may impose broad or open-ended obligations that could be difficult to scope or limit.",
    question_template="What is the full scope of this obligation, and are there any limits on what I am responsible for?"
)

AMBIGUOUS_STANDARD_001 = RiskRule(
    rule_id="AMBIGUOUS_STANDARD_001",
    category="obligation",
    display_name="Ambiguous Standard",
    severity=Severity.INFORMATIONAL,
    patterns=[r'reasonable\s+best\s+efforts', r'commercially\s+reasonable\s+efforts', r'best\s+efforts', r'good\s+faith\s+efforts', r'diligent\s+efforts'],
    explanation_template="This clause uses a standard such as 'best efforts' or 'commercially reasonable efforts', which can be interpreted differently by different parties.",
    question_template="What specifically is expected of me under this standard, and how will compliance be measured?"
)

TRAINING_BOND_001 = RiskRule(
    rule_id="TRAINING_BOND_001",
    category="employment_bond",
    display_name="Training Bond / Reimbursement",
    severity=Severity.HIGH,
    patterns=[r'training\s+(cost|fee|expense|reimbursement)', r'repay\s+training', r'training\s+bond', r'reimburse.*training'],
    explanation_template="This clause requires reimbursement of training costs if employment ends within a specified timeframe.",
    question_template="What is the exact amount of training costs subject to repayment, and how does the repayment obligation decrease over time?"
)

BONUS_CLAWBACK_001 = RiskRule(
    rule_id="BONUS_CLAWBACK_001",
    category="bonus_clawback",
    display_name="Bonus Clawback",
    severity=Severity.HIGH,
    patterns=[r'clawback', r'repay.*bonus', r'refund.*bonus', r'bonus.*subject\s+to\s+repayment', r'forfeit.*bonus'],
    explanation_template="This clause contains a clawback provision requiring repayment of a joining, retention, or performance bonus if certain conditions occur.",
    question_template="Under what specific circumstances must a bonus be repaid, and for how long is the clawback active?"
)

MINIMUM_SERVICE_001 = RiskRule(
    rule_id="MINIMUM_SERVICE_001",
    category="minimum_service",
    display_name="Minimum Service Period",
    severity=Severity.MEDIUM,
    patterns=[r'minimum\s+service\s+period', r'agree.*to\s+serve\s+for\s+at\s+least', r'lock.in\s+period', r'minimum\s+commitment\s+of'],
    explanation_template="This clause specifies a minimum period of service or commitment before which resignation or termination may trigger penalties.",
    question_template="What is the minimum service period, and what are the consequences of leaving prior to completing it?"
)

NON_SOLICITATION_001 = RiskRule(
    rule_id="NON_SOLICITATION_001",
    category="non_solicitation",
    display_name="Non-Solicitation Obligation",
    severity=Severity.MEDIUM,
    patterns=[r'shall\s+not\s+solicit\s+(any\s+)?(customer|client|employee)', r'non.solicitation', r'refrain\s+from\s+soliciting'],
    explanation_template="This clause restricts soliciting employees, clients, or business partners during or after the relationship.",
    question_template="Who am I restricted from soliciting, in what capacity, and for how long after termination?"
)

RELOCATION_OBLIGATION_001 = RiskRule(
    rule_id="RELOCATION_OBLIGATION_001",
    category="relocation",
    display_name="Relocation Obligation",
    severity=Severity.MEDIUM,
    patterns=[r'relocat(e|ion)', r're-location', r'transfer.*to\s+another\s+(office|location|city|country)', r'transfer\s+to\s+another'],
    explanation_template="This clause may require you to relocate or transfer to a different work location at the company's request.",
    question_template="Is relocation mandatory, who bears the costs of relocation, and what notice must be given?"
)


BROAD_TERMINATION_EMP_001 = RiskRule(
    rule_id="BROAD_TERMINATION_EMP_001",
    category="termination",
    display_name="Broad Employer Termination",
    severity=Severity.HIGH,
    patterns=[r'terminate\s+at\s+will', r'terminate.*without\s+cause', r'terminate.*sole\s+discretion'],
    explanation_template="The employer reserves broad rights to terminate employment without cause or at their sole discretion.",
    question_template="What severance or notice is guaranteed if employment is terminated without cause?"
)

EXCLUSIVITY_001 = RiskRule(
    rule_id="EXCLUSIVITY_001",
    category="exclusivity",
    display_name="Exclusivity Obligation",
    severity=Severity.MEDIUM,
    patterns=[r'exclusive\s+(provider|partner|relationship|rights)', r'shall\s+not\s+engage\s+any\s+other', r'exclusivity\s+period'],
    explanation_template="This clause restricts either party from engaging competitors or working with other providers exclusively.",
    question_template="What is the scope and duration of exclusivity, and are there permitted exceptions?"
)

MILESTONE_OBLIGATION_001 = RiskRule(
    rule_id="MILESTONE_OBLIGATION_001",
    category="milestones",
    display_name="Milestone / Payment Deliverables",
    severity=Severity.LOW,
    patterns=[r'milestone\s+payment', r'upon\s+acceptance\s+of\s+deliverable', r'payment\s+schedule', r'deliverable\s+acceptance'],
    explanation_template="Payments or obligations under this agreement are tied to specific milestones or deliverable acceptance.",
    question_template="What are the objective criteria for milestone acceptance and payment release?"
)

TERMINATION_ASYMMETRY_001 = RiskRule(
    rule_id="TERMINATION_ASYMMETRY_001",
    category="termination_asymmetry",
    display_name="Asymmetric Termination Rights",
    severity=Severity.HIGH,
    patterns=[r'client\s+may\s+terminate.*vendor\s+may\s+not', r'company\s+may\s+terminate.*employee\s+must', r'one-sided\s+termination'],
    explanation_template="Termination rights appear uneven, giving one party significantly broader termination flexibility than the other.",
    question_template="Does each party have equivalent rights to terminate with or without cause?"
)

PAYMENT_PENALTY_001 = RiskRule(
    rule_id="PAYMENT_PENALTY_001",
    category="payment_penalty",
    display_name="Payment Delay Penalty",
    severity=Severity.MEDIUM,
    patterns=[r'default\s+interest', r'penalty\s+for\s+delayed\s+payment', r'suspension\s+of\s+services.*non-payment'],
    explanation_template="Late payments may trigger service suspension or punitive interest rates.",
    question_template="What grace period applies before payment default penalties or service suspensions take effect?"
)

CANCELLATION_RESTRICTION_001 = RiskRule(
    rule_id="CANCELLATION_RESTRICTION_001",
    category="cancellation",
    display_name="Cancellation Restriction",
    severity=Severity.MEDIUM,
    patterns=[r'non-cancellable', r'no\s+cancellation', r'cannot\s+be\s+cancelled', r'cancellation\s+fee'],
    explanation_template="The agreement restricts cancellation or imposes a fee for cancelling before term end.",
    question_template="How and when can this agreement be cancelled, and what cancellation fees apply?"
)

REFUND_RESTRICTION_001 = RiskRule(
    rule_id="REFUND_RESTRICTION_001",
    category="refund_restriction",
    display_name="Refund Restriction / No Refunds",
    severity=Severity.MEDIUM,
    patterns=[r'non-refundable', r'no\s+refunds?', r'fees\s+are\s+final'],
    explanation_template="All payments under this agreement are designated non-refundable regardless of usage or termination.",
    question_template="Are there any exceptions to the non-refundable policy, such as breach of contract?"
)

UNILATERAL_PRICE_CHANGE_001 = RiskRule(
    rule_id="UNILATERAL_PRICE_CHANGE_001",
    category="price_change",
    display_name="Unilateral Fee Increase",
    severity=Severity.HIGH,
    patterns=[r'increase\s+fees\s+upon', r'adjust\s+prices\s+at\s+any\s+time', r'reserve.*right\s+to\s+change\s+fees', r'price\s+adjustment'],
    explanation_template="One party reserves the right to increase fees or prices unilaterally during the term.",
    question_template="What notice or capping mechanism applies to fee increases, and can I cancel if prices increase?"
)

DATA_SHARING_001 = RiskRule(
    rule_id="DATA_SHARING_001",
    category="data_sharing",
    display_name="Third-Party Data Sharing",
    severity=Severity.MEDIUM,
    patterns=[r'share\s+(data|information)\s+with\s+third', r'third.party\s+vendors', r'transfer\s+data\s+to'],
    explanation_template="This clause allows your data to be shared with or processed by third-party entities.",
    question_template="What third parties receive data, for what purpose, and what security controls apply?"
)

UNLIMITED_LIABILITY_001 = RiskRule(
    rule_id="UNLIMITED_LIABILITY_001",
    category="unlimited_liability",
    display_name="Unlimited Liability / Carve-outs",
    severity=Severity.HIGH,
    patterns=[r'shall\s+not\s+apply\s+to.*(indemnification|confidentiality|gross\s+negligence|willful)', r'uncapped\s+liability', r'exclusion\s+from\s+liability\s+cap'],
    explanation_template="Certain claims (such as indemnification or confidentiality breach) are explicitly excluded from liability caps, exposing parties to unlimited financial liability.",
    question_template="Which obligations are excluded from the liability cap, and what is the maximum potential exposure?"
)

INDEMNITY_LIABILITY_MISMATCH_001 = RiskRule(
    rule_id="INDEMNITY_LIABILITY_MISMATCH_001",
    category="indemnity_mismatch",
    display_name="Indemnity / Liability Cap Mismatch",
    severity=Severity.HIGH,
    patterns=[r'indemnification.*excluded\s+from.*limitation\s+of\s+liability', r'liability\s+cap.*shall\s+not\s+apply\s+to.*indemni'],
    explanation_template="Indemnification obligations are excluded from the general liability limitation, creating asymmetric risk.",
    question_template="Is my indemnification obligation capped by the general limitation of liability?"
)

ALL_RULES: List[RiskRule] = [
    AUTO_RENEWAL_001,
    TERMINATION_RESTRICTION_001,
    BROAD_INDEMNIFICATION_001,
    LIABILITY_LIMITATION_001,
    UNILATERAL_MODIFICATION_001,
    ARBITRATION_001,
    JURISDICTION_001,
    CONFIDENTIALITY_001,
    NON_COMPETE_001,
    PAYMENT_OBLIGATION_001,
    LATE_FEE_001,
    IP_OWNERSHIP_001,
    WARRANTY_DISCLAIMER_001,
    NOTICE_REQUIREMENT_001,
    PRIVACY_DATA_001,
    BROAD_OBLIGATION_001,
    AMBIGUOUS_STANDARD_001,
    TRAINING_BOND_001,
    BONUS_CLAWBACK_001,
    MINIMUM_SERVICE_001,
    NON_SOLICITATION_001,
    RELOCATION_OBLIGATION_001,
    BROAD_TERMINATION_EMP_001,
    EXCLUSIVITY_001,
    MILESTONE_OBLIGATION_001,
    TERMINATION_ASYMMETRY_001,
    PAYMENT_PENALTY_001,
    CANCELLATION_RESTRICTION_001,
    REFUND_RESTRICTION_001,
    UNILATERAL_PRICE_CHANGE_001,
    DATA_SHARING_001,
    UNLIMITED_LIABILITY_001,
    INDEMNITY_LIABILITY_MISMATCH_001,
]

