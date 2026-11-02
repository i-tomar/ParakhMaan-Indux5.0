import os
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models.all_models import (
    User, Inspection, Image as ImageModel, Declaration, ComplianceResult, AuditEvent
)
from app.services.rule_engine import rule_engine
from app.services.pdf_report_service import pdf_report_service

router = APIRouter(prefix="/demo", tags=["Demo Datasets"])

def create_synthetic_image(filename: str, text_lines: list[str], is_blurry: bool = False, is_glare: bool = False) -> str:
    demo_dir = os.path.join(settings.STORAGE_DIR, "demo_images")
    os.makedirs(demo_dir, exist_ok=True)
    file_path = os.path.join(demo_dir, filename)

    # 800x600 synthetic image
    img = np.full((600, 800, 3), 245, dtype=np.uint8)

    # Draw border and package frame
    cv2.rectangle(img, (20, 20), (780, 580), (30, 41, 59), 3)
    cv2.rectangle(img, (25, 25), (775, 100), (30, 58, 138), -1)
    
    # Title
    cv2.putText(img, "LEGAL METROLOGY INSPECTION SAMPLE", (40, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

    y = 150
    for line in text_lines:
        cv2.putText(img, line, (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (15, 23, 42), 2)
        y += 45

    if is_glare:
        cv2.circle(img, (400, 300), 120, (255, 255, 255), -1)

    if is_blurry:
        img = cv2.GaussianBlur(img, (31, 31), 0)

    cv2.imwrite(file_path, img)
    return file_path

@router.post("/seed")
def seed_demo_endpoint(db: Session = Depends(get_db)):
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo seeding is only available with DEMO_MODE=true")
    return seed_demo_data(db)


def seed_demo_data(db: Session):
    # Check if demo data already seeded
    existing = db.query(Inspection).filter(Inspection.inspection_number.like("INSP-DEMO-%")).first()
    if existing:
        return {"message": "Demo data already initialized", "count": db.query(Inspection).count()}

    inspector = db.query(User).filter(User.email == "inspector@gov.in").first()
    if not inspector:
        inspector = User(
            email="inspector@gov.in",
            full_name="Senior Legal Metrology Inspector",
            hashed_password="!",  # no login: demo accounts come from ensure_demo_accounts
            role="INSPECTOR",
            badge_number="LM-IND-01"
        )
        db.add(inspector)
        db.commit()
        db.refresh(inspector)

    # --- Scenario 1: Fully Compliant Packaged Snack ---
    img1_path = create_synthetic_image("demo_compliant_front.jpg", [
        "Brand: TASTY BITES CRUNCHY POTATO WAFERS",
        "Net Quantity: 500 g",
        "MRP Rs. 60.00 (Inclusive of all taxes)",
        "Unit Sale Price: Rs. 0.12 / g"
    ])
    img2_path = create_synthetic_image("demo_compliant_back.jpg", [
        "Mfd by: ABC Foods India Pvt Ltd, Plot 42, Noida UP",
        "Date of Mfg: 06/2026 | Best Before 6 Months",
        "Country of Origin: India",
        "Consumer Care: Phone 1800-111-222, care@abcfoods.in"
    ])

    insp1 = Inspection(
        inspection_number="INSP-DEMO-0001",
        product_name="Tasty Bites Potato Wafers (500g)",
        brand_name="Tasty Bites",
        category="PACKAGED_FOOD",
        status="FINALIZED",
        overall_outcome="PASS",
        created_by_id=inspector.id,
        location="Supermarket Shelf 4A, New Delhi",
        notes="Standard retail packaging audit for FMCG snack food.",
        final_remarks="All mandatory declarations compliant with Rule 6 and Schedule II."
    )
    db.add(insp1)
    db.commit()

    # Add images
    image1 = ImageModel(
        inspection_id=insp1.id,
        surface_type="FRONT",
        file_path=img1_path,
        original_filename="front_panel.jpg",
        quality_score=0.98,
        quality_metadata={"blur": False, "glare": False, "resolution_ok": True, "perspective_ok": True},
        ocr_raw_data=[
            {"text": "TASTY BITES CRUNCHY POTATO WAFERS", "confidence": 0.98, "bbox": [100, 150, 700, 220]},
            {"text": "Net Quantity: 500 g", "confidence": 0.97, "bbox": [100, 240, 450, 280]},
            {"text": "MRP Rs. 60.00 (Inclusive of all taxes)", "confidence": 0.99, "bbox": [100, 300, 650, 350]},
            {"text": "Unit Sale Price: Rs. 0.12 / g", "confidence": 0.95, "bbox": [100, 370, 500, 420]},
        ]
    )
    image2 = ImageModel(
        inspection_id=insp1.id,
        surface_type="BACK",
        file_path=img2_path,
        original_filename="back_panel.jpg",
        quality_score=0.96,
        quality_metadata={"blur": False, "glare": False, "resolution_ok": True, "perspective_ok": True},
        ocr_raw_data=[
            {"text": "Mfd by: ABC Foods India Pvt Ltd, Plot 42, Noida UP", "confidence": 0.96, "bbox": [50, 120, 750, 180]},
            {"text": "Date of Mfg: 06/2026", "confidence": 0.95, "bbox": [50, 200, 350, 250]},
            {"text": "Country of Origin: India", "confidence": 0.97, "bbox": [50, 270, 400, 320]},
            {"text": "Consumer Care: Phone 1800-111-222, care@abcfoods.in", "confidence": 0.96, "bbox": [50, 340, 700, 400]}
        ]
    )
    db.add_all([image1, image2])
    db.commit()

    # Add Declarations
    decls1 = [
        Declaration(inspection_id=insp1.id, image_id=image1.id, field_name="product_name", detected_value="Tasty Bites Potato Wafers", normalized_value="Potato Wafers", confidence=0.98, bbox=[100, 150, 700, 220], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image1.id, field_name="net_quantity", detected_value="Net Quantity: 500 g", normalized_value="500 g", confidence=0.97, bbox=[100, 240, 450, 280], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image1.id, field_name="mrp", detected_value="MRP Rs. 60.00 (Inclusive of all taxes)", normalized_value="₹ 60.00 (Incl. of all taxes)", confidence=0.99, bbox=[100, 300, 650, 350], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image1.id, field_name="unit_sale_price", detected_value="Unit Sale Price: Rs. 0.12 / g", normalized_value="₹ 0.12 / g", confidence=0.95, bbox=[100, 370, 500, 420], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image2.id, field_name="manufacturer", detected_value="ABC Foods India Pvt Ltd, Plot 42, Noida UP", normalized_value="ABC Foods India Pvt Ltd", confidence=0.96, bbox=[50, 120, 750, 180], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image2.id, field_name="manufacturing_date", detected_value="06/2026", normalized_value="06/2026", confidence=0.95, bbox=[50, 200, 350, 250], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image2.id, field_name="consumer_care", detected_value="Phone 1800-111-222, care@abcfoods.in", normalized_value="1800-111-222 / care@abcfoods.in", confidence=0.96, bbox=[50, 340, 700, 400], is_verified=True),
        Declaration(inspection_id=insp1.id, image_id=image2.id, field_name="country_of_origin", detected_value="India", normalized_value="India", confidence=0.97, bbox=[50, 270, 400, 320], is_verified=True)
    ]
    db.add_all(decls1)

    # Compliance Results
    c_res1 = [
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-APP-001", field="applicability", detected_value="Retail Pre-packaged Commodity", normalized_value="RETAIL_SALE", confidence=1.0, outcome="PASS", severity="HIGH", legal_reference="Rule 3 & Rule 6, PCR 2011", explanation="Package within scope of Chapter II."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-007", field="mrp", detected_value="MRP Rs. 60.00 (Inclusive of all taxes)", normalized_value="₹ 60.00 (Incl. of all taxes)", confidence=0.99, outcome="PASS", severity="CRITICAL", legal_reference="Rule 6(1)(e), PCR 2011", evidence={"image_id": image1.id, "bbox": [100, 300, 650, 350]}, explanation="MRP in INR with tax inclusive indication."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-004", field="net_quantity", detected_value="Net Quantity: 500 g", normalized_value="500 g", confidence=0.97, outcome="PASS", severity="CRITICAL", legal_reference="Rule 6(1)(b) & Rule 11, PCR 2011", evidence={"image_id": image1.id, "bbox": [100, 240, 450, 280]}, explanation="Net quantity in standard metric unit (g)."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-008", field="unit_sale_price", detected_value="Unit Sale Price: Rs. 0.12 / g", normalized_value="₹ 0.12 / g", confidence=0.95, outcome="PASS", severity="HIGH", legal_reference="Rule 6(11), PCR 2011", evidence={"image_id": image1.id, "bbox": [100, 370, 500, 420]}, explanation="USP correctly calculated and displayed."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-001", field="manufacturer", detected_value="ABC Foods India Pvt Ltd", normalized_value="ABC Foods India Pvt Ltd", confidence=0.96, outcome="PASS", severity="HIGH", legal_reference="Rule 6(1)(a), PCR 2011", evidence={"image_id": image2.id, "bbox": [50, 120, 750, 180]}, explanation="Manufacturer name and full address declared."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-005", field="manufacturing_date", detected_value="06/2026", normalized_value="06/2026", confidence=0.95, outcome="PASS", severity="HIGH", legal_reference="Rule 6(1)(d), PCR 2011", evidence={"image_id": image2.id, "bbox": [50, 200, 350, 250]}, explanation="Month and year of manufacture declared."),
        ComplianceResult(inspection_id=insp1.id, rule_id="PC-DEC-010", field="consumer_care", detected_value="Phone 1800-111-222, care@abcfoods.in", normalized_value="1800-111-222 / care@abcfoods.in", confidence=0.96, outcome="PASS", severity="HIGH", legal_reference="Rule 6(1)(n), PCR 2011", evidence={"image_id": image2.id, "bbox": [50, 340, 700, 400]}, explanation="Consumer care contacts present.")
    ]
    db.add_all(c_res1)
    db.commit()

    # --- Scenario 2: Missing Mandatory MRP & Consumer Care (Possible Non-Compliance) ---
    img3_path = create_synthetic_image("demo_noncompliant_front.jpg", [
        "Brand: CRUNCHY NUTS MIX",
        "Net Quantity: 200 g",
        "Mfd by: Quick Packagers, Delhi"
    ])
    insp2 = Inspection(
        inspection_number="INSP-DEMO-0002",
        product_name="Crunchy Nuts Mix (200g)",
        brand_name="Quick Packagers",
        category="PACKAGED_FOOD",
        status="FINALIZED",
        overall_outcome="POSSIBLE_NON_COMPLIANCE",
        created_by_id=inspector.id,
        location="Grocery Store, Sector 18, Noida",
        notes="Non-compliant sample missing statutory MRP and consumer care details."
    )
    db.add(insp2)
    db.commit()

    image3 = ImageModel(
        inspection_id=insp2.id,
        surface_type="FRONT",
        file_path=img3_path,
        original_filename="nuts_front.jpg",
        quality_score=0.95,
        quality_metadata={"blur": False, "glare": False, "resolution_ok": True},
        ocr_raw_data=[
            {"text": "Brand: CRUNCHY NUTS MIX", "confidence": 0.96, "bbox": [100, 150, 600, 200]},
            {"text": "Net Quantity: 200 g", "confidence": 0.95, "bbox": [100, 250, 450, 300]}
        ]
    )
    db.add(image3)
    db.commit()

    c_res2 = [
        ComplianceResult(inspection_id=insp2.id, rule_id="PC-DEC-007", field="mrp", detected_value=None, normalized_value="MISSING", confidence=0.95, outcome="POSSIBLE_NON_COMPLIANCE", severity="CRITICAL", legal_reference="Rule 6(1)(e), PCR 2011", explanation="Mandatory Retail Sale Price (MRP) missing from retail package."),
        ComplianceResult(inspection_id=insp2.id, rule_id="PC-DEC-010", field="consumer_care", detected_value=None, normalized_value="MISSING", confidence=0.92, outcome="POSSIBLE_NON_COMPLIANCE", severity="HIGH", legal_reference="Rule 6(1)(n), PCR 2011", explanation="Mandatory Consumer Care contact information missing.")
    ]
    db.add_all(c_res2)
    db.commit()

    # --- Scenario 3: Blurry Image Defect (Needs Review) ---
    img4_path = create_synthetic_image("demo_blurry.jpg", ["DEFECTIVE BLURRY TEXT 500g ₹45"], is_blurry=True)
    insp3 = Inspection(
        inspection_number="INSP-DEMO-0003",
        product_name="Herbal Soap Bar (Unclear Image)",
        brand_name="AyurClean",
        category="COSMETICS",
        status="REVIEW",
        overall_outcome="REVIEW",
        created_by_id=inspector.id,
        location="Warehouse Bay 2, Mumbai",
        notes="Image quality degraded by camera blur during warehouse inspection."
    )
    db.add(insp3)
    db.commit()

    image4 = ImageModel(
        inspection_id=insp3.id,
        surface_type="FRONT",
        file_path=img4_path,
        original_filename="blurry_soap.jpg",
        quality_score=0.42,
        quality_metadata={"blur": True, "glare": False, "resolution_ok": True, "sharpness_score": 28.4, "issues": ["Image is blurry. Sharpness index: 28.4 < threshold 65.0"]},
        ocr_raw_data=[
            {"text": "DEFECTIVE BLURRY TEXT", "confidence": 0.52, "bbox": [100, 200, 500, 280]}
        ]
    )
    db.add(image4)
    db.commit()

    c_res3 = [
        ComplianceResult(inspection_id=insp3.id, rule_id="PC-VIS-001", field="image_visibility", detected_value="Severe camera blur detected", normalized_value="QUALITY_DEGRADED", confidence=0.45, outcome="REVIEW", severity="HIGH", legal_reference="Rule 9(1), PCR 2011", explanation="Package image is blurry; declarations cannot be verified with legal certainty. Re-capture recommended.")
    ]
    db.add_all(c_res3)
    db.commit()

    # --- Scenario 4: Front vs Back Net Qty Contradiction (Review) ---
    insp4 = Inspection(
        inspection_number="INSP-DEMO-0004",
        product_name="Premium Basmati Rice",
        brand_name="Royal Grains",
        category="PACKAGED_FOOD",
        status="REVIEW",
        overall_outcome="REVIEW",
        created_by_id=inspector.id,
        location="Central Distribution Depot, Haryana",
        notes="Cross-surface contradiction detected between Front (5 kg) and Back label (4.5 kg)."
    )
    db.add(insp4)
    db.commit()

    c_res4 = [
        ComplianceResult(inspection_id=insp4.id, rule_id="PC-CON-001", field="cross_surface_consistency", detected_value="Front: 5 kg vs Back: 4.5 kg", normalized_value="CONTRADICTORY_DECLARATIONS", confidence=0.98, outcome="REVIEW", severity="CRITICAL", legal_reference="Rule 6, PCR 2011", explanation="Contradictory Net Quantity declarations found across package surfaces. Inspector review required.")
    ]
    db.add_all(c_res4)
    db.commit()

    return {"message": "Demo datasets seeded successfully", "inspections_created": 4}
