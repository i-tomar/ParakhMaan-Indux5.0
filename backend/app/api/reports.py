import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.api.deps import get_org_inspection, require
from app.core.database import get_db
from app.models.all_models import User
from app.services.pdf_report_service import pdf_report_service

router = APIRouter(prefix="/inspections", tags=["Reports"])

@router.get("/{id}/report")
def get_pdf_report(id: str, db: Session = Depends(get_db), current_user: User = Depends(require("inspection:read"))):
    insp = get_org_inspection(db, id, current_user)

    if insp.inspection_mode == "DEFECT":
        from app.api.defects import get_defect_report
        return get_defect_report(insp, db)

    # If PDF exists, serve it, otherwise generate it
    if insp.report_path and os.path.exists(insp.report_path):
        return FileResponse(
            insp.report_path,
            media_type="application/pdf",
            filename=os.path.basename(insp.report_path)
        )

    # Generate on the fly
    insp_dict = {
        "id": insp.id,
        "inspection_number": insp.inspection_number,
        "product_name": insp.product_name,
        "brand_name": insp.brand_name,
        "category": insp.category,
        "status": insp.status,
        "overall_outcome": insp.overall_outcome,
        "created_at": insp.created_at,
        "final_remarks": insp.final_remarks,
        "compliance_results": [r.__dict__ for r in insp.compliance_results],
        "declarations": [d.__dict__ for d in insp.declarations],
        "reviewer_actions": [a.__dict__ for a in insp.reviewer_actions]
    }
    path = pdf_report_service.generate_inspection_report(insp_dict)
    insp.report_path = path
    db.commit()

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path)
    )
