"""Printable PDF report generation for MediScan AI."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2469A6")
PALE = colors.HexColor("#EEF4FA")
MUTED = colors.HexColor("#536579")


def _safe(value) -> str:
    """Escape user-provided text for ReportLab Paragraph markup."""
    if pd.isna(value):
        return ""
    return escape(str(value)).replace("\n", "<br/>")


def build_pdf_report(df: pd.DataFrame, source_name: str, summary: str,
                     created_at: str | None = None, report_id: int | None = None) -> bytes:
    """Create a printable A4 PDF using only the supplied/analyzed report data."""
    required = {"test", "value", "unit", "min", "max", "status"}
    if df is None or df.empty or not required.issubset(set(df.columns)):
        raise ValueError("Cannot create a PDF: analyzed report data is missing required columns or rows.")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=13*mm, leftMargin=13*mm,
        topMargin=16*mm, bottomMargin=17*mm, title="MediScan AI - Lab Report Summary",
        author="MediScan AI"
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=20, leading=24, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallMuted", parent=styles["Normal"], fontSize=8, leading=11, textColor=MUTED))
    styles.add(ParagraphStyle(name="Cell", parent=styles["Normal"], fontSize=8, leading=10, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CellHead", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=colors.white))
    styles.add(ParagraphStyle(name="Summary", parent=styles["Normal"], fontSize=9, leading=13, spaceAfter=4))

    low = int((df["status"] == "Low").sum())
    normal = int((df["status"] == "In range").sum())
    high = int((df["status"] == "High").sum())
    story = [
        Paragraph("MediScan AI", styles["ReportTitle"]),
        Paragraph("Laboratory report comparison - printable summary", styles["Heading2"]),
        Spacer(1, 3*mm),
        Paragraph(f"<b>Source file:</b> {_safe(source_name)}", styles["Normal"]),
        Paragraph(f"<b>Generated:</b> {_safe(created_at or pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'))}" +
                  (f" &nbsp;&nbsp; <b>Report ID:</b> {int(report_id)}" if report_id is not None else ""), styles["SmallMuted"]),
        Spacer(1, 4*mm),
    ]
    summary_data = [["Tests analyzed", "Low", "In range", "High"], [str(len(df)), str(low), str(normal), str(high)]]
    summary_table = Table(summary_data, colWidths=[55*mm]*4, hAlign="LEFT")
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BACKGROUND", (0,1), (-1,1), PALE), ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("BOX", (0,0), (-1,-1), .5, colors.HexColor("#D5E0EA")),
        ("INNERGRID", (0,0), (-1,-1), .4, colors.HexColor("#D5E0EA")),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story += [summary_table, Spacer(1, 5*mm), Paragraph("Result details", styles["Heading2"])]

    headers = ["Test", "Result", "Unit", "Reference minimum", "Reference maximum", "Comparison", "Review note"]
    table_data = [[Paragraph(_safe(h), styles["CellHead"]) for h in headers]]
    for _, row in df.iterrows():
        value = f"{float(row['value']):g}"
        min_value = f"{float(row['min']):g}"
        max_value = f"{float(row['max']):g}"
        note = row.get("review_flag", "")
        table_data.append([
            Paragraph(_safe(row["test"]), styles["Cell"]), Paragraph(value, styles["Cell"]),
            Paragraph(_safe(row["unit"]), styles["Cell"]), Paragraph(min_value, styles["Cell"]),
            Paragraph(max_value, styles["Cell"]), Paragraph(_safe(row["status"]), styles["Cell"]),
            Paragraph(_safe(note), styles["Cell"]),
        ])
    widths = [44*mm, 22*mm, 25*mm, 30*mm, 30*mm, 25*mm, 75*mm]
    result_table = Table(table_data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table_commands = [
        ("BACKGROUND", (0,0), (-1,0), NAVY), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#D5E0EA")),
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5), ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        table_commands.append(("BACKGROUND", (0,idx), (-1,idx), colors.white if idx % 2 else PALE))
        status = str(row["status"])
        tint = {"Low": colors.HexColor("#FFF0EE"), "High": colors.HexColor("#FFF0EE"),
                "In range": colors.HexColor("#EAF7EF")}.get(status, colors.white)
        table_commands.append(("BACKGROUND", (5,idx), (5,idx), tint))
    result_table.setStyle(TableStyle(table_commands))
    story += [result_table, Spacer(1, 5*mm), Paragraph("Summary", styles["Heading2"])]
    for paragraph in str(summary).split("\n\n"):
        if paragraph.strip():
            story.append(Paragraph(_safe(paragraph), styles["Summary"]))

    story += [Spacer(1, 3*mm), Paragraph(
        "Important: MediScan AI is a hackathon prototype and is not clinically validated. "
        "Low / In range / High labels only compare values with the reference ranges supplied in the input file. "
        "They are not diagnoses and do not replace professional medical advice. Verify source values and ranges with a qualified healthcare professional.",
        styles["SmallMuted"])]

    def page_decor(canvas, document):
        canvas.saveState()
        page_w, page_h = document.pagesize
        canvas.setStrokeColor(colors.HexColor("#D5E0EA"))
        canvas.line(document.leftMargin, 11*mm, page_w-document.rightMargin, 11*mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 7*mm, "MediScan AI | Prototype - not for diagnosis")
        canvas.drawRightString(page_w-document.rightMargin, 7*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    return buffer.getvalue()
