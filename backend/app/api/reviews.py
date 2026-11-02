from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_org_inspection, require
from app.models.all_models import User, Inspection, Declaration, ComplianceResult, ReviewerAction, AuditEvent
from app.schemas.all_schemas import ReviewActionRequest, ReviewActionResponse, InspectionDetailResponse
from app.services.rule_engine import rule_engine

router = APIRouter(prefix="/inspections", tags=["Review Queue"])

@router.post("/{id}/review", response_model=ReviewActionResponse)
def submit_review_action(
    id: str,
    req: ReviewActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("review:write"))
):
    insp = get_org_inspection(db, id, current_user)

    # 1. Record Reviewer Action
    action = ReviewerAction(
        inspection_id=id,
        reviewer_id=current_user.id,
        action_type=req.action_type,
        target_field=req.target_field,
        previous_value=req.previous_value,
        new_value=req.new_value,
        reason=req.reason
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    # 2. Update Declaration if corrected or confirmed
    decl = db.query(Declaration).filter(
        Declaration.inspection_id == id,
        Declaration.field_name == req.target_field
    ).first()

    if decl:
        if req.action_type == "CORRECT":
            decl.reviewer_value = req.new_value
            decl.normalized_value = req.new_value
            decl.is_verified = True
        elif req.action_type == "CONFIRM":
            decl.is_verified = True
        elif req.action_type == "REJECT":
            decl.is_verified = False
        db.commit()

    # 3. Update corresponding ComplianceResult
    comp_result = db.query(ComplianceResult).filter(
        ComplianceResult.inspection_id == id,
        ComplianceResult.field == req.target_field
    ).first()

    if comp_result:
        if req.action_type == "CONFIRM":
            comp_result.outcome = "PASS"
            comp_result.reviewer_status = "CONFIRMED"
            comp_result.explanation = f"Confirmed by Inspector {current_user.full_name}: {req.reason or 'Verified compliant'}"
        elif req.action_type == "CORRECT":
            comp_result.outcome = "PASS"
            comp_result.normalized_value = req.new_value
            comp_result.reviewer_status = "OVERRIDDEN"
            comp_result.explanation = f"Corrected by Inspector {current_user.full_name} to '{req.new_value}': {req.reason}"
        elif req.action_type == "REJECT":
            comp_result.outcome = "POSSIBLE_NON_COMPLIANCE"
            comp_result.reviewer_status = "CONFIRMED"
            comp_result.explanation = f"Marked non-compliant by Inspector {current_user.full_name}: {req.reason}"
        db.commit()

    # 4. Recompute overall inspection outcome
    all_results = db.query(ComplianceResult).filter(ComplianceResult.inspection_id == id).all()
    results_dicts = [r.__dict__ for r in all_results]
    new_outcome = rule_engine.compute_overall_outcome(results_dicts)
    insp.overall_outcome = new_outcome
    db.commit()

    # 5. Audit Event
    audit = AuditEvent(
        inspection_id=id,
        user_id=current_user.id,
        event_type="REVIEWER_ACTION",
        description=f"Action '{req.action_type}' applied to field '{req.target_field}' by {current_user.full_name}",
        state_before={"field": req.target_field, "value": req.previous_value},
        state_after={"action": req.action_type, "new_value": req.new_value, "overall_outcome": new_outcome}
    )
    db.add(audit)
    db.commit()

    return action
