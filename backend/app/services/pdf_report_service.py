import os
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from app.core.config import settings

class PDFReportService:
    """
    Generates official Legal Metrology inspection reports using ReportLab.
    Ensures 100% font safety and statutory formatting.
    """

    def _sanitize_pdf_text(self, text: Any) -> str:
        if text is None:
            return ""
        s = str(text)
        # Replace unicode rupee symbol with 'Rs. ' to prevent glyph errors in standard Helvetica font
        s = s.replace("₹", "Rs. ")
        # Escape XML characters for ReportLab Paragraph
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return s

    def generate_inspection_report(self, inspection_data: Dict[str, Any]) -> str:
        insp_id = inspection_data.get("id", "unknown")
        insp_num = inspection_data.get("inspection_number", f"INSP-{insp_id[:8]}")
        
        filename = f"Inspection_Report_{insp_num}.pdf"
        output_path = os.path.join(settings.REPORTS_DIR, filename)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'GovTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=18,
            textColor=colors.HexColor('#0F172A'),
            alignment=1  # Centered
        )
        subtitle_style = ParagraphStyle(
            'GovSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#475569'),
            alignment=1
        )
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#1E3A8A'),
            spaceBefore=8,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#334155')
        )
        badge_pass = ParagraphStyle(
            'BadgePass',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#166534')
        )
        badge_review = ParagraphStyle(
            'BadgeReview',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#854D0E')
        )
        badge_fail = ParagraphStyle(
            'BadgeFail',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#991B1B')
        )

        elements = []

        # 1. Government Header
        elements.append(Paragraph("GOVERNMENT OF INDIA", subtitle_style))
        elements.append(Paragraph("MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION", subtitle_style))
        elements.append(Paragraph("DEPARTMENT OF CONSUMER AFFAIRS - LEGAL METROLOGY DIVISION", title_style))
        elements.append(Paragraph("LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011 INSPECTION CERTIFICATE", ParagraphStyle('CertSub', parent=subtitle_style, fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#1E293B'))))
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceBefore=2, spaceAfter=8))

        # 2. Metadata Table
        created_at = inspection_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        outcome = inspection_data.get("overall_outcome", "PENDING")
        outcome_color = '#166534' if outcome == "PASS" else ('#854D0E' if outcome == "REVIEW" else '#991B1B')
        
        meta_data = [
            [
                Paragraph("<b>Inspection ID:</b>", body_style),
                Paragraph(self._sanitize_pdf_text(insp_num), body_style),
                Paragraph("<b>Date & Time:</b>", body_style),
                Paragraph(self._sanitize_pdf_text(str(created_at)[:19]), body_style)
            ],
            [
                Paragraph("<b>Product Name:</b>", body_style),
                Paragraph(self._sanitize_pdf_text(inspection_data.get("product_name") or "Packaged Commodity"), body_style),
                Paragraph("<b>Category:</b>", body_style),
                Paragraph(self._sanitize_pdf_text(inspection_data.get("category", "GENERAL")), body_style)
            ],
            [
                Paragraph("<b>Inspector ID:</b>", body_style),
                Paragraph(self._sanitize_pdf_text(inspection_data.get("inspector_name") or "Officer #LM-8421"), body_style),
                Paragraph("<b>Status:</b>", body_style),
                Paragraph(f"<b><font color='{outcome_color}'>{self._sanitize_pdf_text(outcome)}</font></b>", body_style)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[100, 170, 90, 180])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 10))

        # 3. Compliance Matrix
        elements.append(Paragraph("STATUTORY COMPLIANCE EVALUATION MATRIX", section_style))
        
        matrix_rows = [
            [
                Paragraph("<b>Rule ID</b>", body_style),
                Paragraph("<b>Field / Requirement</b>", body_style),
                Paragraph("<b>Detected Value</b>", body_style),
                Paragraph("<b>Statutory Reference</b>", body_style),
                Paragraph("<b>Outcome</b>", body_style)
            ]
        ]

        results = inspection_data.get("compliance_results", [])
        if not results:
            matrix_rows.append([
                Paragraph("-", body_style),
                Paragraph("No evaluations recorded", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("PENDING", body_style)
            ])
        else:
            for r in results:
                r_out = r.get("outcome", "PENDING")
                b_style = badge_pass if r_out == "PASS" else (badge_review if r_out == "REVIEW" else badge_fail)
                
                det_val = self._sanitize_pdf_text(r.get("normalized_value") or r.get("detected_value") or "Missing")
                ref_val = self._sanitize_pdf_text(r.get("legal_reference", "PCR 2011"))

                matrix_rows.append([
                    Paragraph(self._sanitize_pdf_text(r.get("rule_id", "")), body_style),
                    Paragraph(self._sanitize_pdf_text(r.get("field", "").replace("_", " ").title()), body_style),
                    Paragraph(det_val[:45], body_style),
                    Paragraph(ref_val[:50], body_style),
                    Paragraph(self._sanitize_pdf_text(r_out), b_style)
                ])

        matrix_table = Table(matrix_rows, colWidths=[75, 120, 135, 140, 70])
        matrix_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elements.append(matrix_table)
        elements.append(Spacer(1, 10))

        # 4. Extracted Package Declarations Summary
        elements.append(Paragraph("EXTRACTED STATUTORY DECLARATIONS", section_style))
        decl_rows = [
            [
                Paragraph("<b>Declaration Field</b>", body_style),
                Paragraph("<b>Extracted Text (OCR)</b>", body_style),
                Paragraph("<b>Normalized Value</b>", body_style),
                Paragraph("<b>Confidence</b>", body_style)
            ]
        ]
        decls = inspection_data.get("declarations", [])
        for d in decls:
            conf = d.get("confidence", 1.0)
            det_val = self._sanitize_pdf_text(d.get("detected_value", ""))
            norm_val = self._sanitize_pdf_text(d.get("normalized_value", ""))

            decl_rows.append([
                Paragraph(self._sanitize_pdf_text(d.get("field_name", "").replace("_", " ").title()), body_style),
                Paragraph(det_val[:45], body_style),
                Paragraph(norm_val[:45], body_style),
                Paragraph(f"{conf*100:.0f}%", body_style)
            ])
        
        if len(decl_rows) > 1:
            decl_table = Table(decl_rows, colWidths=[120, 180, 180, 60])
            decl_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                ('PADDING', (0,0), (-1,-1), 4),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elements.append(decl_table)
            elements.append(Spacer(1, 10))

        # 5. Inspector Actions & Notes
        if inspection_data.get("reviewer_actions"):
            elements.append(Paragraph("MANUAL REVIEW & CORRECTIONS LOG", section_style))
            action_rows = [
                [Paragraph("<b>Target Field</b>", body_style), Paragraph("<b>Action</b>", body_style), Paragraph("<b>Previous Value</b>", body_style), Paragraph("<b>New Value</b>", body_style), Paragraph("<b>Reason / Remarks</b>", body_style)]
            ]
            for act in inspection_data.get("reviewer_actions", []):
                action_rows.append([
                    Paragraph(self._sanitize_pdf_text(act.get("target_field", "")), body_style),
                    Paragraph(self._sanitize_pdf_text(act.get("action_type", "")), body_style),
                    Paragraph(self._sanitize_pdf_text(str(act.get("previous_value") or "-")), body_style),
                    Paragraph(self._sanitize_pdf_text(str(act.get("new_value") or "-")), body_style),
                    Paragraph(self._sanitize_pdf_text(str(act.get("reason") or "-")), body_style)
                ])
            action_table = Table(action_rows, colWidths=[90, 75, 110, 110, 155])
            action_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                ('PADDING', (0,0), (-1,-1), 4),
            ]))
            elements.append(action_table)
            elements.append(Spacer(1, 10))

        # 6. Statutory Declaration & Signature Seal
        elements.append(Paragraph("OFFICIAL DETERMINATION & SIGN-OFF", section_style))
        remarks = inspection_data.get("final_remarks") or "Inspection verified according to the deterministic rule engine of the Legal Metrology (Packaged Commodities) Rules, 2011."
        elements.append(Paragraph(f"<b>Inspector Remarks:</b> {self._sanitize_pdf_text(remarks)}", body_style))
        elements.append(Spacer(1, 12))
        
        sig_data = [
            [
                Paragraph("<b>Verified by:</b> Legal Metrology Inspectorate<br/>Automated Rule Engine v1.0 (SIH26034)", body_style),
                Paragraph("<b>Official Digital Seal:</b><br/>[GOVERNMENT OF INDIA SECURE AUDIT LEDGER]", body_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[270, 270])
        sig_table.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor('#94A3B8')),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        return output_path

    def generate_defect_report(self, data: Dict[str, Any]) -> str:
        """
        Defect Inspection mode report: summary, annotated evidence images,
        detection log, root-cause hints, and sign-off.
        `data["overlay_paths"]` holds annotated JPEGs to embed (one per analysed image).
        """
        insp_num = data.get("inspection_number", "DEF-UNKNOWN")
        output_path = os.path.join(settings.REPORTS_DIR, f"Defect_Report_{insp_num}.pdf")
        doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('DefTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=colors.HexColor('#0F172A'), alignment=1)
        subtitle_style = ParagraphStyle('DefSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13, textColor=colors.HexColor('#475569'), alignment=1)
        section_style = ParagraphStyle('DefSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.HexColor('#1E3A8A'), spaceBefore=8, spaceAfter=4)
        body_style = ParagraphStyle('DefBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor('#334155'))
        severity_colours = {"CRITICAL": "#991B1B", "HIGH": "#C2410C", "MEDIUM": "#854D0E", "LOW": "#166534"}
        outcome_colours = {"PASS": "#166534", "REVIEW": "#854D0E", "DEFECTIVE": "#991B1B"}

        elements = []
        elements.append(Paragraph("AI &amp; COMPUTER-VISION BASED SURFACE &amp; PRODUCT DEFECT INSPECTION", title_style))
        elements.append(Paragraph("Automated Quality Inspection Report", subtitle_style))
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceBefore=2, spaceAfter=8))

        outcome = data.get("overall_outcome", "PENDING")
        oc = outcome_colours.get(outcome, '#334155')
        meta = [
            [Paragraph("<b>Inspection ID:</b>", body_style), Paragraph(self._sanitize_pdf_text(insp_num), body_style),
             Paragraph("<b>Date &amp; Time:</b>", body_style), Paragraph(self._sanitize_pdf_text(str(data.get("created_at", ""))[:19]), body_style)],
            [Paragraph("<b>Product / Part:</b>", body_style), Paragraph(self._sanitize_pdf_text(data.get("product_name") or "Unnamed Product"), body_style),
             Paragraph("<b>Batch / Lot:</b>", body_style), Paragraph(self._sanitize_pdf_text(data.get("brand_name") or "-"), body_style)],
            [Paragraph("<b>Product Line:</b>", body_style), Paragraph(self._sanitize_pdf_text(str(data.get("category", "")).replace("_", " ")), body_style),
             Paragraph("<b>Station:</b>", body_style), Paragraph(self._sanitize_pdf_text(data.get("location") or "-"), body_style)],
            [Paragraph("<b>Inspector:</b>", body_style), Paragraph(self._sanitize_pdf_text(data.get("inspector_name") or "Quality Inspector"), body_style),
             Paragraph("<b>Outcome:</b>", body_style), Paragraph(f"<b><font color='{oc}'>{self._sanitize_pdf_text(outcome)}</font></b>", body_style)],
        ]
        meta_table = Table(meta, colWidths=[90, 180, 80, 190])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 10))

        detections = [d for d in data.get("defect_detections", []) if d.get("reviewer_status") != "REJECTED"]

        # Summary by defect type
        elements.append(Paragraph("DEFECT SUMMARY", section_style))
        summary: Dict[str, Dict[str, int]] = {}
        for d in detections:
            row = summary.setdefault(d.get("defect_type", "UNKNOWN"), {"count": 0, "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
            row["count"] += 1
            row[d.get("severity", "MEDIUM")] = row.get(d.get("severity", "MEDIUM"), 0) + 1
        summary_rows = [[Paragraph(f"<b>{h}</b>", body_style) for h in ("Defect Type", "Count", "Critical", "High", "Medium", "Low")]]
        if not summary:
            summary_rows.append([Paragraph("No defects detected", body_style)] + [Paragraph("-", body_style)] * 5)
        for dtype, row in sorted(summary.items(), key=lambda kv: kv[1]["count"], reverse=True):
            summary_rows.append([Paragraph(self._sanitize_pdf_text(dtype.replace("_", " ").title()), body_style)] +
                                [Paragraph(str(row[k]), body_style) for k in ("count", "CRITICAL", "HIGH", "MEDIUM", "LOW")])
        summary_table = Table(summary_rows, colWidths=[160, 76, 76, 76, 76, 76])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 10))

        # Annotated evidence images
        overlay_paths = [p for p in data.get("overlay_paths", []) if p and os.path.exists(p)]
        if overlay_paths:
            from reportlab.platypus import Image as RLImage
            from reportlab.lib.utils import ImageReader
            elements.append(Paragraph("ANNOTATED VISUAL EVIDENCE", section_style))
            for path in overlay_paths[:6]:
                iw, ih = ImageReader(path).getSize()
                width = 400.0
                height = width * ih / float(iw)
                if height > 260:
                    height = 260.0
                    width = height * iw / float(ih)
                elements.append(RLImage(path, width=width, height=height))
                elements.append(Spacer(1, 6))

        # Detection log
        elements.append(Paragraph("DETECTION LOG", section_style))
        log_rows = [[Paragraph(f"<b>{h}</b>", body_style) for h in ("#", "Type", "Severity", "Confidence", "Location (px)", "Detector", "Review")]]
        for idx, d in enumerate(detections, start=1):
            sev = d.get("severity", "MEDIUM")
            bbox = d.get("bbox") or []
            loc = f"{int(bbox[0])},{int(bbox[1])} - {int(bbox[2])},{int(bbox[3])}" if len(bbox) == 4 else "-"
            if d.get("frame_index") is not None:
                loc += f" (frame {d['frame_index']})"
            log_rows.append([
                Paragraph(str(idx), body_style),
                Paragraph(self._sanitize_pdf_text(d.get("defect_type", "").replace("_", " ").title()), body_style),
                Paragraph(f"<b><font color='{severity_colours.get(sev, '#334155')}'>{sev}</font></b>", body_style),
                Paragraph(f"{d.get('confidence', 0) * 100:.0f}%", body_style),
                Paragraph(loc, body_style),
                Paragraph(self._sanitize_pdf_text(d.get("detector", "")), body_style),
                Paragraph(self._sanitize_pdf_text(d.get("reviewer_status", "PENDING")), body_style),
            ])
        if len(log_rows) == 1:
            log_rows.append([Paragraph("-", body_style), Paragraph("No defects detected", body_style)] + [Paragraph("-", body_style)] * 5)
        log_table = Table(log_rows, colWidths=[24, 110, 62, 62, 150, 62, 70], repeatRows=1)
        log_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(log_table)
        elements.append(Spacer(1, 10))

        # Root-cause hints
        root_causes = data.get("root_causes", [])
        if root_causes:
            elements.append(Paragraph("ROOT-CAUSE HINTS", section_style))
            for rc in root_causes:
                elements.append(Paragraph(f"<b>{self._sanitize_pdf_text(rc['defect_type'].replace('_', ' ').title())}</b> ({rc['count']})", body_style))
                for cause in rc.get("likely_causes", [])[:3]:
                    elements.append(Paragraph(f"&bull; {self._sanitize_pdf_text(cause)}", body_style))
                for action in rc.get("recommended_actions", [])[:2]:
                    elements.append(Paragraph(f"&rarr; {self._sanitize_pdf_text(action)}", body_style))
                elements.append(Spacer(1, 4))

        elements.append(Paragraph("DETERMINATION &amp; SIGN-OFF", section_style))
        remarks = data.get("final_remarks") or "Automated computer-vision inspection; detections are subject to inspector confirmation."
        elements.append(Paragraph(f"<b>Inspector Remarks:</b> {self._sanitize_pdf_text(remarks)}", body_style))
        elements.append(Spacer(1, 12))
        sig_table = Table([[
            Paragraph(f"<b>Analysed by:</b> Defect Inspection Engine ({self._sanitize_pdf_text(data.get('detector_backend', 'OPENCV'))})", body_style),
            Paragraph("<b>Quality Sign-off:</b><br/>________________________", body_style),
        ]], colWidths=[270, 270])
        sig_table.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        return output_path

    def generate_batch_report(self, data: Dict[str, Any]) -> str:
        output_path = os.path.join(settings.REPORTS_DIR, f"Batch_Report_{data['batch']}.pdf".replace("/", "_"))
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        safe = self._sanitize_pdf_text
        k = data["kpis"]
        percent = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"

        def table(rows: List[List[Any]]) -> Table:
            t = Table(rows, hAlign="LEFT")
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f5f4")), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                   ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e6e6e6")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
            return t

        story: List[Any] = [
            Paragraph("ParakhMaan Batch Quality Report", styles["Title"]),
            Paragraph(f"Batch {safe(data['batch'])} | Product: {safe(data['product'])} | Status: {safe(data['status'])}", styles["Normal"]),
            Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M}", styles["Normal"]), Spacer(1, 10),
        ]
        if data.get("is_synthetic"):
            story += [Paragraph("<b>SIMULATED BATCH.</b> Part images are real; production context is simulated.", styles["Normal"]), Spacer(1, 8)]
        story += [table([["Units", "Accepted", "Rejected", "Manual review", "First-pass yield", "Rejection rate"],
                         [k["units"], k["accepted"], k["rejected"], k["manual_review"], percent(k["first_pass_yield"]), percent(k["rejection_rate"])]]),
                  Spacer(1, 12), Paragraph("Defects by type", styles["Heading2"])]
        story.append(table([["Defect", "Count", "Share", "Cumulative"]] + [[safe(r["defect_type"]), r["count"], percent(r["share"]), percent(r["cumulative"])] for r in data["pareto"]])
                     if data["pareto"] else Paragraph("No defects recorded.", styles["Normal"]))
        for title, key in (("By machine", "by_machine"), ("By shift", "by_shift")):
            if data[key]:
                story += [Spacer(1, 12), Paragraph(title, styles["Heading2"]),
                          table([["Group", "Units", "Rejected", "Rate"]] + [[safe(r["group"]), r["units"], r["rejected"], percent(r["rejection_rate"])] for r in data[key]])]
        doc.build(story)
        return output_path


pdf_report_service = PDFReportService()
