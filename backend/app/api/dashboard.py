from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.api.deps import require
from app.core.database import get_db
from app.models.all_models import Inspection, ComplianceResult, User
from app.schemas.all_schemas import DashboardSummaryResponse, InspectionResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(require("inspection:read"))):
    org_id = current_user.organization_id
    legal = db.query(Inspection).filter(
        Inspection.inspection_mode == "LEGAL_METROLOGY", Inspection.organization_id == org_id
    )
    total = legal.count()
    compliant = legal.filter(Inspection.overall_outcome == "PASS").count()
    needs_review = legal.filter(Inspection.overall_outcome == "REVIEW").count()
    non_compliant = legal.filter(Inspection.overall_outcome == "POSSIBLE_NON_COMPLIANCE").count()
    draft = legal.filter(Inspection.status == "DRAFT").count()

    recent = legal.order_by(Inspection.created_at.desc()).limit(8).all()
    recent_responses = [
        InspectionResponse(
            id=i.id,
            inspection_number=i.inspection_number,
            inspection_mode=i.inspection_mode,
            product_name=i.product_name,
            brand_name=i.brand_name,
            category=i.category,
            status=i.status,
            overall_outcome=i.overall_outcome,
            created_by_id=i.created_by_id,
            location=i.location,
            notes=i.notes,
            final_remarks=i.final_remarks,
            report_path=i.report_path,
            image_count=len(i.images),
            created_at=i.created_at,
            updated_at=i.updated_at
        ) for i in recent
    ]

    # Category distribution
    cat_counts = (
        db.query(Inspection.category, func.count(Inspection.id))
        .filter(Inspection.inspection_mode == "LEGAL_METROLOGY", Inspection.organization_id == org_id)
        .group_by(Inspection.category)
        .all()
    )
    category_distribution = [{"category": c[0] or "OTHER", "count": c[1]} for c in cat_counts]

    # Common violations/issues from compliance results
    violations = (
        db.query(ComplianceResult.field, ComplianceResult.rule_id, func.count(ComplianceResult.id))
        .join(Inspection, Inspection.id == ComplianceResult.inspection_id)
        .filter(ComplianceResult.outcome.in_(["POSSIBLE_NON_COMPLIANCE", "REVIEW"]), Inspection.organization_id == org_id)
        .group_by(ComplianceResult.field, ComplianceResult.rule_id)
        .order_by(func.count(ComplianceResult.id).desc())
        .limit(5)
        .all()
    )
    common_violations = [
        {"field": v[0], "rule_id": v[1], "count": v[2]} for v in violations
    ]

    return {
        "total_inspections": total,
        "compliant_count": compliant,
        "needs_review_count": needs_review,
        "non_compliance_count": non_compliant,
        "draft_count": draft,
        "recent_inspections": recent_responses,
        "common_violations": common_violations,
        "category_distribution": category_distribution
    }
