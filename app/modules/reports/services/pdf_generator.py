"""
PDF Generator — renders an AuditReportResponse into a PDF using ReportLab Platypus.

Structure:
1. Cover Header: URL, domain, scanned_at, pages_crawled, overall_score + grade badge.
2. Executive Summary: overall score breakdown table + category summary table.
3. Category Details: per-category breakdown of issues and affected pages.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.logger import logger
from app.schemas.report_schemas import AuditReportResponse, Category, Issue

# Color Constants
COLOR_PRIMARY = colors.HexColor("#1A202C")
COLOR_SECONDARY = colors.HexColor("#2B6CB0")
COLOR_CRITICAL = colors.HexColor("#E53E3E")
COLOR_WARNING = colors.HexColor("#DD6B20")
COLOR_GOOD = colors.HexColor("#38A169")
COLOR_INFO = colors.HexColor("#4A5568")
COLOR_LIGHT_BG = colors.HexColor("#F7FAFC")
COLOR_BORDER = colors.HexColor("#E2E8F0")


def render_audit_report_pdf(report: AuditReportResponse, output_path: str) -> str:
    """
    Render an AuditReportResponse object to a PDF file at output_path.

    Args:
        report: AuditReportResponse object containing structured report data.
        output_path: Target filepath for saving the PDF (e.g. app/output/reports/domain_auditid.pdf).

    Returns:
        The output_path string where the PDF was written.
    """
    logger.info(f"render_audit_report_pdf: generating PDF for scan_id={report.scan_id} at {output_path}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    style_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=COLOR_PRIMARY,
        alignment=0,
        spaceAfter=6,
    )
    style_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=COLOR_INFO,
        spaceAfter=15,
    )
    style_heading1 = ParagraphStyle(
        "SectionHeading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=COLOR_PRIMARY,
        spaceBefore=12,
        spaceAfter=8,
    )
    style_heading2 = ParagraphStyle(
        "SectionHeading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=COLOR_SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
    )
    style_body = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=COLOR_PRIMARY,
    )
    style_body_bold = ParagraphStyle(
        "ReportBodyBold",
        parent=style_body,
        fontName="Helvetica-Bold",
    )
    style_table_header = ParagraphStyle(
        "TableHeader",
        parent=style_body,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    story = []

    # ── 1. COVER / HEADER SECTION ─────────────────────────────────────
    story.append(Paragraph(f"SEO Audit Report — {report.url}", style_title))
    story.append(
        Paragraph(
            f"<b>Domain:</b> {report.url} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Category:</b> {report.site_category} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Scanned At:</b> {report.scanned_at} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Pages Crawled:</b> {report.pages_crawled}",
            style_subtitle,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_BORDER, spaceAfter=15))

    # Overall Score Box
    overall_val = report.overall_score.value if report.overall_score else 0.0
    overall_grade = report.overall_score.grade if report.overall_score else "F"
    score_color = COLOR_GOOD if overall_val >= 80 else (COLOR_WARNING if overall_val >= 60 else COLOR_CRITICAL)

    score_card_data = [
        [
            Paragraph(f"<font size=28 color='{score_color.hexval()}'><b>{overall_val:.1f} / 100</b></font>", style_body),
            Paragraph(f"<font size=28 color='{score_color.hexval()}'><b>Grade: {overall_grade}</b></font>", style_body),
            Paragraph(
                f"<b>Checks Run:</b> {report.overall_score.checks_run}<br/>"
                f"<b>Passed:</b> {report.overall_score.passed}<br/>"
                f"<b>Critical:</b> {report.overall_score.critical_issues}<br/>"
                f"<b>Warnings:</b> {report.overall_score.warnings}",
                style_body,
            ),
        ]
    ]
    score_table = Table(score_card_data, colWidths=[200, 150, 190])
    score_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(score_table)
    story.append(Spacer(1, 15))

    # ── 2. EXECUTIVE SUMMARY (CATEGORIES TABLE) ──────────────────────
    story.append(Paragraph("Executive Summary — Category Breakdown", style_heading1))

    cat_table_data = [[
        Paragraph("Category", style_table_header),
        Paragraph("Score", style_table_header),
        Paragraph("Grade", style_table_header),
        Paragraph("Status", style_table_header),
        Paragraph("Critical", style_table_header),
        Paragraph("Warnings", style_table_header),
    ]]

    for cat in report.categories:
        if not cat.applicable:
            cat_table_data.append([
                Paragraph(cat.label, style_body_bold),
                Paragraph("N/A", style_body),
                Paragraph("N/A", style_body),
                Paragraph("Not Applicable", style_body),
                Paragraph("-", style_body),
                Paragraph("-", style_body),
            ])
            continue

        c_val = cat.score.value if cat.score and cat.score.value is not None else 0.0
        c_grade = cat.score.grade if cat.score else "-"
        c_status = (cat.status or "unknown").replace("_", " ").title()
        crit_cnt = cat.issue_count.critical if cat.issue_count else 0
        warn_cnt = cat.issue_count.warning if cat.issue_count else 0

        cat_table_data.append([
            Paragraph(cat.label, style_body_bold),
            Paragraph(f"{c_val:.1f}", style_body),
            Paragraph(c_grade, style_body),
            Paragraph(c_status, style_body),
            Paragraph(str(crit_cnt), style_body),
            Paragraph(str(warn_cnt), style_body),
        ])

    cat_table = Table(cat_table_data, colWidths=[160, 60, 60, 110, 75, 75])
    cat_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_BG]),
        ])
    )
    story.append(cat_table)
    story.append(Spacer(1, 20))

    # ── 3. CATEGORY DETAILS & ISSUES ───────────────────────────────────
    story.append(Paragraph("Category Details & Audit Issues", style_heading1))

    for cat in report.categories:
        if not cat.applicable:
            continue
        if not cat.issues:
            continue

        cat_elements = []
        cat_elements.append(Paragraph(f"{cat.label} Issues", style_heading2))

        for issue in cat.issues:
            sev_color = COLOR_CRITICAL if issue.severity == "critical" else (COLOR_WARNING if issue.severity == "warning" else COLOR_INFO)
            issue_header = Paragraph(
                f"<b>[{issue.severity.upper()}]</b> {issue.title} "
                f"<font color='{COLOR_INFO.hexval()}'>({issue.affected_page_count} page(s) affected)</font>",
                ParagraphStyle("IssueTitle", parent=style_body_bold, textColor=sev_color, fontSize=10),
            )

            issue_details = [
                Paragraph(f"<b>Description:</b> {issue.description}", style_body),
            ]
            if issue.recommendation:
                issue_details.append(Paragraph(f"<b>Recommendation:</b> {issue.recommendation}", style_body))

            # Affected pages table (limit to REPORT_MAX_AFFECTED_PAGES_SHOWN)
            pages_shown = issue.affected_pages[: settings.REPORT_MAX_AFFECTED_PAGES_SHOWN]
            if pages_shown:
                page_rows = [[
                    Paragraph("Page URL", style_table_header),
                    Paragraph("Found / Evidence", style_table_header),
                ]]
                for p in pages_shown:
                    ev_str = str(p.found_value) if p.found_value is not None else str(p.evidence or "")
                    page_rows.append([
                        Paragraph(p.url, style_body),
                        Paragraph(ev_str[:120], style_body),
                    ])
                p_table = Table(page_rows, colWidths=[270, 250])
                p_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
                        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ])
                )
                issue_details.append(Spacer(1, 4))
                issue_details.append(p_table)

            cat_elements.append(KeepTogether([
                issue_header,
                Spacer(1, 2),
                *issue_details,
                Spacer(1, 8),
            ]))

        story.append(KeepTogether(cat_elements))
        story.append(Spacer(1, 10))

    # ── 4. NON-APPLICABLE CATEGORIES SUMMARY ──────────────────────────
    skipped_cats = [c for c in report.categories if not c.applicable]
    if skipped_cats:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Non-Applicable Categories", style_heading2))
        for sc in skipped_cats:
            story.append(
                Paragraph(
                    f"• <b>{sc.label}:</b> {sc.reason_not_applicable or 'Not applicable'}",
                    style_body,
                )
            )

    # Footer note
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceAfter=8))
    story.append(
        Paragraph(
            f"Report generated by <b>{settings.APP_NAME}</b>.",
            ParagraphStyle("Footer", parent=style_body, textColor=COLOR_INFO, alignment=1),
        )
    )

    doc.build(story)
    logger.info(f"render_audit_report_pdf: successfully generated PDF at {output_path}")

    return str(out_file)
