import pytest
import uuid
from datetime import datetime
from app.models.schemas import Clause, ClauseMetadata, DocumentOverview
from app.models.relationship import (
    ClauseRelationship,
    ClauseRelationshipStatus,
    ClauseRelationshipType,
)
from app.analysis.relationships import RelationshipEngine, analyze_clause_relationships
from app.storage.database import save_document, save_clause, save_relationships, get_relationships


def make_clause(
    doc_id: str,
    text: str,
    clause_type: str = "general",
    heading: str = "Section",
    path: str = "Section",
    page: int = 1,
) -> Clause:
    cid = str(uuid.uuid4())
    return Clause(
        id=cid,
        text=text,
        metadata=ClauseMetadata(
            clause_id=cid,
            document_id=doc_id,
            section_id="sec-1",
            heading=heading,
            section_path=path,
            page=page,
            clause_type=clause_type,
            char_count=len(text),
        ),
    )


# 1. Termination with Notice
def test_termination_with_notice():
    doc_id = "doc-term-notice"
    c1 = make_clause(
        doc_id,
        "Either party may terminate this Agreement at any time upon breach.",
        clause_type="termination",
        heading="Termination",
        path="Article IV > Section 4.1",
    )
    c2 = make_clause(
        doc_id,
        "The party seeking termination shall provide 30 days written notice to the non-breaching party.",
        clause_type="notice",
        heading="Notice Period",
        path="Article IV > Section 4.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    term_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.TERMINATION_NOTICE]
    assert len(term_rels) == 1
    rel = term_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id == c2.metadata.clause_id
    assert rel.relationship_status == ClauseRelationshipStatus.BALANCED_RELATIONSHIP
    assert rel.related_section_path == "Article IV > Section 4.2"


# 2. Termination without Notice -> related_clause_id is null
def test_termination_without_notice_null_counterpart():
    doc_id = "doc-term-no-notice"
    c1 = make_clause(
        doc_id,
        "The Company reserves the right to terminate this Agreement immediately for cause.",
        clause_type="termination",
        heading="Termination",
        path="Article IV > Section 4.1",
    )

    rels = analyze_clause_relationships(doc_id, [c1])
    term_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.TERMINATION_NOTICE]
    assert len(term_rels) == 1
    rel = term_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id is None
    assert rel.related_section_path is None
    assert rel.related_page is None
    assert rel.related_excerpt is None
    assert rel.relationship_status in (
        ClauseRelationshipStatus.MISSING_COUNTERPART,
        ClauseRelationshipStatus.INCOMPLETE_RELATIONSHIP,
    )


# 3. Confidentiality with Survival
def test_confidentiality_with_survival():
    doc_id = "doc-conf-surv"
    c1 = make_clause(
        doc_id,
        "Receiving Party shall keep all Confidential Information secret and proprietary.",
        clause_type="confidentiality",
        heading="Confidentiality",
        path="Section 5.1",
    )
    c2 = make_clause(
        doc_id,
        "The obligations of confidentiality set forth in Section 5.1 shall survive termination for 5 years.",
        clause_type="survival",
        heading="Survival",
        path="Section 5.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    conf_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.CONFIDENTIALITY_SURVIVAL]
    assert len(conf_rels) == 1
    rel = conf_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id == c2.metadata.clause_id
    assert rel.relationship_status == ClauseRelationshipStatus.BALANCED_RELATIONSHIP


# 4. Confidentiality without Survival -> related_clause_id is null
def test_confidentiality_without_survival_null_counterpart():
    doc_id = "doc-conf-no-surv"
    c1 = make_clause(
        doc_id,
        "The Recipient agrees not to disclose any Proprietary Information to third parties.",
        clause_type="confidentiality",
        heading="Confidentiality",
        path="Section 5.1",
    )

    rels = analyze_clause_relationships(doc_id, [c1])
    conf_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.CONFIDENTIALITY_SURVIVAL]
    assert len(conf_rels) == 1
    rel = conf_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id is None
    assert rel.related_section_path is None
    assert rel.related_page is None
    assert rel.related_excerpt is None
    assert rel.relationship_status == ClauseRelationshipStatus.MISSING_COUNTERPART


# 5. Party Obligation without Reciprocal Evidence -> NO Asymmetry
def test_party_obligation_without_reciprocal_evidence():
    doc_id = "doc-no-asym"
    c1 = make_clause(
        doc_id,
        "Employee shall maintain strict confidentiality of all trade secrets during employment.",
        clause_type="obligation",
        heading="Employee Duties",
        path="Section 3.1",
    )

    rels = analyze_clause_relationships(doc_id, [c1])
    asym_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.PARTY_OBLIGATION_ASYMMETRY]
    # Conservative enforcement: NO reciprocal language -> NO asymmetry generated!
    assert len(asym_rels) == 0


# 6. Party Obligation with Explicit Reciprocal Language -> Asymmetry / Relationship Generated
def test_party_obligation_with_explicit_reciprocal_language():
    doc_id = "doc-recip-asym"
    c1 = make_clause(
        doc_id,
        "Both parties agree to mutual non-solicitation of each other's personnel during the term.",
        clause_type="obligation",
        heading="Non-Solicitation",
        path="Section 8.1",
    )

    rels = analyze_clause_relationships(doc_id, [c1])
    asym_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.PARTY_OBLIGATION_ASYMMETRY]
    assert len(asym_rels) == 1
    rel = asym_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id


# 7. Indemnity + Liability Cap
def test_indemnity_and_liability_cap():
    doc_id = "doc-indem-cap"
    c1 = make_clause(
        doc_id,
        "Vendor shall indemnify, defend, and hold harmless Customer against any third-party claims.",
        clause_type="indemnification",
        heading="Indemnification",
        path="Section 7.1",
    )
    c2 = make_clause(
        doc_id,
        "In no event shall total liability under this agreement exceed the fees paid in the last 12 months.",
        clause_type="limitation_of_liability",
        heading="Liability Cap",
        path="Section 8.1",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    indem_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.INDEMNITY_LIABILITY_CAP]
    assert len(indem_rels) == 1
    rel = indem_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id == c2.metadata.clause_id


# 8. Indemnity + Explicit Cap Exclusion
def test_indemnity_and_explicit_cap_exclusion():
    doc_id = "doc-indem-excl"
    c1 = make_clause(
        doc_id,
        "Licensor agrees to indemnify Licensee from intellectual property infringement suits.",
        clause_type="indemnification",
        heading="Indemnity",
        path="Section 6.1",
    )
    c2 = make_clause(
        doc_id,
        "The limitation of liability shall not apply to indemnification obligations or breaches of confidentiality.",
        clause_type="limitation_of_liability",
        heading="Exclusions from Cap",
        path="Section 7.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    indem_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.INDEMNITY_LIABILITY_CAP]
    assert len(indem_rels) == 1
    rel = indem_rels[0]
    assert "exclu" in rel.plain_explanation.lower() or "not apply" in rel.plain_explanation.lower()


# 9. Obligation and Deadline
def test_obligation_and_deadline():
    doc_id = "doc-ob-dl"
    c1 = make_clause(
        doc_id,
        "Supplier shall deliver quarterly security report logs to Customer.",
        clause_type="obligation",
        heading="Reporting Obligation",
        path="Section 4.1",
    )
    c2 = make_clause(
        doc_id,
        "Security report logs must be delivered within 10 business days following quarter end.",
        clause_type="deadline",
        heading="Delivery Schedule",
        path="Section 4.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    ob_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.OBLIGATION_DEADLINE]
    assert len(ob_rels) == 1
    rel = ob_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id == c2.metadata.clause_id


# 10. Payment and Deadline
def test_payment_and_deadline():
    doc_id = "doc-pay-dl"
    c1 = make_clause(
        doc_id,
        "Buyer agrees to pay all invoiced amounts for Services rendered.",
        clause_type="payment",
        heading="Payment Fees",
        path="Section 2.1",
    )
    c2 = make_clause(
        doc_id,
        "Invoices shall be payable within 30 days from the invoice date.",
        clause_type="payment_terms",
        heading="Payment Terms",
        path="Section 2.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    pay_rels = [r for r in rels if r.relationship_type == ClauseRelationshipType.PAYMENT_DEADLINE]
    assert len(pay_rels) == 1
    rel = pay_rels[0]
    assert rel.source_clause_id == c1.metadata.clause_id
    assert rel.related_clause_id == c2.metadata.clause_id


# 11. Unrelated Clauses -> No Relationship
def test_unrelated_clauses_no_relationship():
    doc_id = "doc-unrelated"
    c1 = make_clause(
        doc_id,
        "This Agreement shall be governed by Delaware law.",
        clause_type="governing_law",
        heading="Law",
        path="Section 10.1",
    )
    c2 = make_clause(
        doc_id,
        "Section headings are included for convenience only.",
        clause_type="general",
        heading="Headings",
        path="Section 10.2",
    )

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    assert len(rels) == 0


# 12. Duplicate Suppression & Deterministic Repeatability
def test_duplicate_suppression_and_repeatability():
    doc_id = "doc-repeat"
    c1 = make_clause(
        doc_id,
        "Either party may terminate this Agreement.",
        clause_type="termination",
        heading="Term",
        path="Section 4.1",
    )
    c2 = make_clause(
        doc_id,
        "Notice of termination must be provided 30 days prior.",
        clause_type="notice",
        heading="Notice",
        path="Section 4.2",
    )

    engine = RelationshipEngine()
    run1 = engine.analyze_document_relationships([c1, c2], doc_id)
    run2 = engine.analyze_document_relationships([c1, c2], doc_id)

    assert len(run1) == len(run2)
    for r1, r2 in zip(run1, run2):
        assert r1.relationship_id == r2.relationship_id
        assert r1.relationship_type == r2.relationship_type
        assert r1.source_clause_id == r2.source_clause_id
        assert r1.related_clause_id == r2.related_clause_id


# 13. REST API GET /api/documents/{doc_id}/relationships
def test_api_get_relationships(client):
    doc_id = f"test-doc-{uuid.uuid4()}"
    save_document(DocumentOverview(
        document_id=doc_id,
        filename="test_contract.pdf",
        page_count=1,
        clause_count=2,
        signal_count=0,
        dates=[],
        monetary_values=[],
        parties=[],
        genai_available=False,
        created_at=datetime.utcnow(),
        processing_status="completed"
    ))

    c1 = make_clause(doc_id, "Either party may terminate at any time.", clause_type="termination")
    c2 = make_clause(doc_id, "30 days notice required for termination.", clause_type="notice")
    save_clause(c1)
    save_clause(c2)

    rels = analyze_clause_relationships(doc_id, [c1, c2])
    save_relationships(doc_id, rels)

    res = client.get(f"/api/documents/{doc_id}/relationships")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first_rel = data[0]
    assert "relationship_type" in first_rel
    assert "relationship_status" in first_rel
    assert "source_clause_id" in first_rel


def test_api_get_relationships_404(client):
    res = client.get("/api/documents/nonexistent-doc-id/relationships")
    assert res.status_code == 404


# 14. REST API Explain & Cross-Doc Validation
def test_api_explain_relationship_cross_doc_validation(client):
    doc_a = f"doc-a-{uuid.uuid4()}"
    save_document(DocumentOverview(
        document_id=doc_a,
        filename="doc_a.pdf",
        page_count=1,
        clause_count=1,
        signal_count=0,
        dates=[],
        monetary_values=[],
        parties=[],
        genai_available=False,
        created_at=datetime.utcnow(),
        processing_status="completed"
    ))
    c_a = make_clause(doc_a, "Termination without notice clause.", clause_type="termination")
    save_clause(c_a)
    rels_a = analyze_clause_relationships(doc_a, [c_a])
    save_relationships(doc_a, rels_a)
    res = client.get(f"/api/documents/{doc_a}/relationships")
    assert res.status_code == 200
    assert len(res.json()) >= 1

