"""Report building and export (PDF, DOCX, XLSX).

A report is first assembled as a format-neutral :class:`ReportDoc` (blocks of headings, text, tables
and images) from the analysis :class:`~businesspilot.pipeline.Bundle`; the three renderers then
turn the *same* document into files, so every format shows the same numbers as the app.
"""
from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from . import report_charts as rc
from .ai_insights import KINDS, SECTION_TITLES
from .metrics import Metric, money, pct
from .schema import ROLES

PCT_KEYS = {"margin", "growth", "repeat_rate", "concentration", "ctr", "conv_rate"}
MONEY_KEYS = {"revenue", "expenses", "cogs", "gross_profit", "net_profit", "aov", "mkt_spend", "cpa"}


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ReportError(RuntimeError):
    """Raised when a report cannot be produced; the UI must show this instead of offering a file."""


# --------------------------------------------------------------------------- structure
@dataclass
class Block:
    kind: str            # h1 | h2 | p | bullets | table | image | note
    text: str = ""
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)   # first row = header
    image: bytes = b""
    widths: Optional[list[float]] = None


@dataclass
class ReportDoc:
    title: str
    business: str
    period: str
    generated: str
    blocks: list[Block] = field(default_factory=list)
    report_type: str = ""

    def has_content(self) -> bool:
        return any(b.kind in ("table", "bullets", "image") or (b.kind == "p" and b.text) for b in self.blocks)


SECTION_DEFS: dict[str, tuple[str, str]] = {   # id -> (title, requires-key or "")
    "summary": ("Executive summary", ""),
    "kpis": ("Key figures", ""),
    "trends": ("Trends over time", "time"),
    "products": ("Product performance", "products"),
    "expenses": ("Expense breakdown", "expense_breakdown"),
    "customers": ("Customer analysis", "customers"),
    "marketing": ("Marketing performance", "marketing"),
    "inventory": ("Inventory", "inventory"),
    "forecast": ("Forecast", "forecast"),
    "risks": ("Risks and unusual patterns", ""),
    "recommendations": ("Recommendations and next steps", ""),
    "quality": ("Data quality", ""),
    "assumptions": ("Assumptions and limitations", ""),
    "appendix": ("Data preview", ""),
}

DEFAULT_SECTIONS: dict[str, list[str]] = {
    "Executive Business Report": ["summary", "kpis", "trends", "products", "forecast", "risks", "recommendations", "assumptions"],
    "Financial Performance Report": ["summary", "kpis", "trends", "expenses", "risks", "recommendations", "quality", "assumptions"],
    "Sales Analysis Report": ["summary", "kpis", "trends", "products", "customers", "recommendations", "assumptions"],
    "Profit and Loss Report": ["summary", "kpis", "trends", "expenses", "assumptions"],
    "Business Growth Report": ["summary", "kpis", "trends", "forecast", "risks", "recommendations", "assumptions"],
    "Customer Analysis Report": ["summary", "customers", "products", "recommendations", "quality", "assumptions"],
    "Marketing Performance Report": ["summary", "marketing", "trends", "recommendations", "assumptions"],
    "Inventory Analysis Report": ["summary", "inventory", "products", "recommendations", "quality", "assumptions"],
    "Forecast and Risk Report": ["summary", "forecast", "risks", "assumptions"],
    "General Data Analysis Report": ["summary", "kpis", "quality", "assumptions", "appendix"],
}


def available_sections(avail: dict) -> list[str]:
    return [sid for sid, (_, req) in SECTION_DEFS.items() if not req or avail.get(req)]


def default_sections(report_type: str, avail: dict) -> list[str]:
    ok = set(available_sections(avail))
    return [s for s in DEFAULT_SECTIONS.get(report_type, DEFAULT_SECTIONS["General Data Analysis Report"]) if s in ok]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "report"


def make_filename(business: str, report_type: str, ext: str) -> str:
    return f"{_slug(business)}_{_slug(report_type)}_{datetime.now():%Y%m%d}.{ext}"


def _table(df: pd.DataFrame, fmt: dict | None = None, max_rows: int = 25) -> list[list[str]]:
    fmt = fmt or {}
    rows = [[str(c) for c in df.columns]]
    for _, r in df.head(max_rows).iterrows():
        rows.append([fmt.get(c, lambda v: "" if pd.isna(v) else str(v))(r[c]) for c in df.columns])
    return rows


def _metric_rows(ms: list[Metric], keys: Optional[set] = None) -> list[list[str]]:
    rows = [["Metric", "Value", "How it is calculated"]]
    for m in ms:
        if keys is None or m.key in keys:
            rows.append([m.label, m.display, m.formula])
    return rows


# --------------------------------------------------------------------------- builder
def build_report(bundle, report_type: str, sections: list[str], business: str = "My Business",
                 include_llm: bool = True) -> ReportDoc:
    """Assemble a report from selected sections. Raises ReportError if nothing meaningful is available."""
    b, cur = bundle, bundle.currency
    ins = b.insights
    doc = ReportDoc(title=report_type, business=business, period=b.period, generated=f"{datetime.now():%d %b %Y %H:%M}", report_type=report_type)
    P = lambda t: doc.blocks.append(Block("p", text=t))        # noqa: E731
    H1 = lambda t: doc.blocks.append(Block("h1", text=t))      # noqa: E731
    H2 = lambda t: doc.blocks.append(Block("h2", text=t))      # noqa: E731
    BL = lambda items: doc.blocks.append(Block("bullets", items=items))   # noqa: E731
    TB = lambda rows, widths=None: doc.blocks.append(Block("table", rows=rows, widths=widths))  # noqa: E731
    IM = lambda img, cap="": doc.blocks.append(Block("image", image=img, text=cap)) if img else None  # noqa: E731
    NOTE = lambda t: doc.blocks.append(Block("note", text=t))  # noqa: E731
    tag = lambda i: f"{i.text} [{KINDS[i.kind]}]"              # noqa: E731

    if b.filters_note:
        NOTE(b.filters_note)

    for sid in sections:
        if sid == "summary":
            H1("Executive summary")
            items = ins.by_section("summary")
            if items:
                BL([tag(i) for i in items])
            if include_llm and ins.llm_status == "used" and ins.llm_text:
                H2("AI-generated commentary")
                NOTE("Written by an external language model using only the aggregated figures in this report. It is interpretation, not a verified calculation.")
                P(ins.llm_text)
        elif sid == "kpis":
            H1("Key figures")
            if b.metrics:
                TB(_metric_rows(b.metrics), [2.1, 1.5, 3.0])
                H2("What these figures mean")
                BL([f"{m.label}: {m.explanation}" for m in b.metrics if m.explanation])
            else:
                NOTE("No financial or operational figures could be calculated because the required columns were not mapped.")
        elif sid == "trends" and b.avail.get("time"):
            H1("Trends over time")
            IM(rc.trend_chart(b.monthly, cur), "Monthly revenue, expenses and profit")
            m = b.monthly.copy()
            cols = [c for c in ("revenue", "expenses", "calc_profit") if c in m]
            if cols:
                t = m[["period"] + cols].tail(12).copy()
                t["period"] = t["period"].astype(str)
                t = t.rename(columns={"period": "Month", "revenue": "Revenue", "expenses": "Expenses", "calc_profit": "Profit"})
                f = {c: (lambda v: "" if pd.isna(v) else f"{v:,.2f}") for c in t.columns if c != "Month"}
                P("Most recent months (empty cells mean no data for that month):")
                TB(_table(t, f, 12))
        elif sid == "products" and b.avail.get("products") and not b.products.empty:
            H1("Product performance")
            val = b.products.columns[1]
            IM(rc.bar_chart(b.products, "product", val, f"Top products by {val}", cur), f"Top products by {val}")
            t = b.products.rename(columns={"product": "Product", val: val.title(), "share": "Share of total"})
            TB(_table(t, {val.title(): lambda v: f"{v:,.2f}", "Share of total": lambda v: f"{v:.1%}"}))
        elif sid == "expenses" and b.avail.get("expense_breakdown") and not b.expenses.empty:
            H1("Expense breakdown")
            IM(rc.bar_chart(b.expenses, "category", "expenses", "Expenses by category", cur), "Expenses by category")
            t = b.expenses.rename(columns={"category": "Category", "expenses": "Expenses", "share": "Share of total"})
            TB(_table(t, {"Expenses": lambda v: f"{v:,.2f}", "Share of total": lambda v: f"{v:.1%}"}))
        elif sid == "customers" and b.avail.get("customers"):
            H1("Customer analysis")
            keys = {"customers", "repeat_rate", "concentration", "aov"}
            rows = _metric_rows(b.metrics, keys)
            if len(rows) > 1:
                TB(rows, [2.1, 1.5, 3.0])
            else:
                P("Customer columns are present but too sparse for customer metrics.")
        elif sid == "marketing" and b.avail.get("marketing"):
            H1("Marketing performance")
            rows = _metric_rows(b.metrics, {"mkt_spend", "roas", "cpa", "ctr", "conv_rate"})
            TB(rows, [2.1, 1.5, 3.0]) if len(rows) > 1 else P("Marketing columns are present but there is not enough to calculate returns.")
        elif sid == "inventory" and b.avail.get("inventory"):
            H1("Inventory")
            rows = _metric_rows(b.metrics, {"stock_total", "out_of_stock", "stock_cover"})
            TB(rows, [2.1, 1.5, 3.0]) if len(rows) > 1 else None
        elif sid == "forecast" and b.avail.get("forecast"):
            H1("Forecast")
            fc = b.forecast
            if fc is None or not fc.available:
                P("A forecast could not be produced: " + (fc.reason if fc else "not enough data."))
            else:
                IM(rc.forecast_chart(fc, cur), "Actual monthly values, back-test and forecast")
                P(f"Selected model: {fc.model}. {fc.model_description}")
                f = fc.forecast.copy()
                f["timestamp"] = f["timestamp"].dt.strftime("%b %Y")
                f = f.rename(columns={"timestamp": "Month", "point": "Forecast", "lower": "Lower bound", "upper": "Upper bound"})
                TB(_table(f, {c: (lambda v: f"{v:,.2f}") for c in ("Forecast", "Lower bound", "Upper bound")}))
                mt = fc.metrics
                H2("How accurate has this approach been?")
                BL([f"Back-tested on {mt['backtest_points']} past months using only earlier data for each forecast.",
                    f"Average error (MAE): {mt['MAE']:,.2f}; typical percentage error (MAPE): {mt['MAPE']:.1f}%.",
                    (f"Improvement over the naive baseline: {mt['improvement_vs_baseline_pct']:.0f}%." if mt["beats_baseline"]
                     else "No tested model beat the naive baseline, so this forecast simply carries the latest value forward; treat it with extra caution."),
                    f"{mt['interval_coverage']:.0%} of past actual values fell inside the {int(fc.interval_level*100)}% interval."])
                H2("Assumptions")
                BL(fc.assumptions)
                H2("Limitations")
                BL(fc.limitations)
        elif sid == "risks":
            H1("Risks and unusual patterns")
            if b.risk:
                TB([["Indicator", "Level", "Detail"]] + [[r["indicator"], r["level"], r["detail"]] for r in b.risk], [1.8, 0.8, 4.0])
                NOTE("Risk indicators are rule-based checks on your history. They are not probabilities of future events.")
            items = ins.by_section("risks") + ins.by_section("anomalies") + ins.by_section("factors")
            if items:
                BL([tag(i) for i in items])
            if not b.risk and not items:
                P("No notable risks or unusual patterns were detected in the available data.")
        elif sid == "recommendations":
            H1("Recommendations and next steps")
            recs = ins.by_section("recommendations")
            if recs:
                H2("Recommendations"); BL([tag(i) for i in recs])
            nxt = ins.by_section("next_steps")
            if nxt:
                H2("Suggested next steps"); BL([i.text for i in nxt])
        elif sid == "quality":
            H1("Data quality")
            q = b.quality
            P(f"Rows: {q.rows:,}. Columns: {q.columns}. Blank cells: {q.missing_cells:,} ({q.missing_pct:.1%}). Duplicate rows: {q.duplicate_rows:,}. "
              f"Data-quality score: {q.score}/100 (starts at 100 and loses points for blanks, duplicates and unreadable values).")
            BL(q.issues) if q.issues else P("No data-quality issues were detected.")
            TB(_table(q.per_column, None, 20))
        elif sid == "assumptions":
            H1("Assumptions and limitations")
            BL([f"Period analysed: {b.period}.", f"Currency label: {cur or 'not set'}."] + [i.text for i in ins.by_section("limitations")])
            mp = [["Business field", "Source column"]] + [[ROLES[r]["label"], c] for r, c in b.std.mapping.columns.items()]
            H2("Column mapping used"); TB(mp, [2.5, 3.0])
            NOTE("Verified calculations are computed directly from your data by software. Interpretations and forecasts are labelled and are not guarantees.")
        elif sid == "appendix":
            H1("Data preview")
            d = b.data.copy()
            d.columns = [str(c).replace("other::", "") for c in d.columns]
            TB(_table(d.iloc[:, :8], None, 25))
    if not doc.has_content():
        raise ReportError("The selected sections have no content for this data. Choose different sections or map more columns.")
    clean = lambda t: _ILLEGAL.sub("", t) if isinstance(t, str) else t   # noqa: E731 - uploads are untrusted text
    for blk in doc.blocks:
        blk.text = clean(blk.text)
        blk.items = [clean(i) for i in blk.items]
        blk.rows = [[clean(c) for c in r] for r in blk.rows]
    return doc


# --------------------------------------------------------------------------- renderers
def _pdf_text(s: str) -> str:
    s = (s or "").replace("−", "-").replace("≤", "<=").replace("≥", ">=").replace("→", "->").replace("÷", "/")
    return html.escape(s.encode("cp1252", "replace").decode("cp1252"))


def render_pdf(doc: ReportDoc) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    NAVY, BLUE = colors.HexColor("#0B1F3A"), colors.HexColor("#2563EB")
    ss = getSampleStyleSheet()
    st = {
        "title": ParagraphStyle("t", parent=ss["Title"], textColor=NAVY, fontSize=24, leading=28, alignment=TA_LEFT, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=ss["Normal"], textColor=colors.HexColor("#475569"), fontSize=10.5, leading=14),
        "h1": ParagraphStyle("h1", parent=ss["Heading2"], textColor=NAVY, fontSize=14, spaceBefore=14, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=ss["Heading3"], textColor=BLUE, fontSize=11, spaceBefore=8, spaceAfter=4, keepWithNext=1),
        "p": ParagraphStyle("p", parent=ss["BodyText"], fontSize=9.5, leading=13.5, spaceAfter=4),
        "cell": ParagraphStyle("c", parent=ss["BodyText"], fontSize=8, leading=10),
        "cellh": ParagraphStyle("ch", parent=ss["BodyText"], fontSize=8, leading=10, textColor=colors.white, fontName="Helvetica-Bold"),
        "note": ParagraphStyle("n", parent=ss["BodyText"], fontSize=8.5, leading=12, textColor=colors.HexColor("#475569"), backColor=colors.HexColor("#F1F5F9"), borderPadding=5, spaceAfter=6),
        "cap": ParagraphStyle("cap", parent=ss["BodyText"], fontSize=8, textColor=colors.HexColor("#64748B")),
    }
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title=_pdf_text(doc.title), author="BusinessPilot AI")
    width = A4[0] - 1.5 * inch
    story = [Paragraph(_pdf_text(doc.title), st["title"]),
             Paragraph(_pdf_text(f"{doc.business}  |  Period: {doc.period}"), st["sub"]),
             Paragraph(_pdf_text(f"Generated {doc.generated} by BusinessPilot AI"), st["sub"]), Spacer(1, 10)]
    for b in doc.blocks:
        if b.kind == "h1":
            story.append(Paragraph(_pdf_text(b.text), st["h1"]))
        elif b.kind == "h2":
            story.append(Paragraph(_pdf_text(b.text), st["h2"]))
        elif b.kind == "p":
            story.append(Paragraph(_pdf_text(b.text).replace("\n", "<br/>"), st["p"]))
        elif b.kind == "note":
            story.append(Paragraph(_pdf_text(b.text), st["note"]))
        elif b.kind == "bullets":
            for it in b.items:
                story.append(Paragraph("&bull; " + _pdf_text(it), st["p"]))
        elif b.kind == "image":
            from PIL import Image as PILImage
            w, h = PILImage.open(io.BytesIO(b.image)).size
            iw = width
            story.append(KeepTogether([Image(io.BytesIO(b.image), width=iw, height=iw * h / w), Paragraph(_pdf_text(b.text), st["cap"]), Spacer(1, 6)]))
        elif b.kind == "table" and len(b.rows) > 0:
            ncol = len(b.rows[0])
            rows = [[Paragraph(_pdf_text(c), st["cellh"]) for c in b.rows[0]]] + \
                   [[Paragraph(_pdf_text(c), st["cell"]) for c in r] for r in b.rows[1:]]
            if b.widths and len(b.widths) == ncol:
                tot = sum(b.widths); cw = [width * w / tot for w in b.widths]
            else:
                cw = [width / ncol] * ncol
            t = Table(rows, colWidths=cw, repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
            story += [t, Spacer(1, 8)]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(0.75 * inch, 0.5 * inch, _pdf_text("BusinessPilot AI - " + doc.business).replace("&amp;", "&"))
        canvas.drawRightString(A4[0] - 0.75 * inch, 0.5 * inch, f"Page {d.page}")
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise ReportError("PDF generation failed.")
    return data


def render_docx(doc: ReportDoc) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    d = Document()
    sec = d.sections[0]
    sec.left_margin = sec.right_margin = Inches(0.9)
    sec.top_margin = sec.bottom_margin = Inches(0.8)
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    t = d.add_heading(doc.title, 0)
    for r in t.runs:
        r.font.color.rgb = RGBColor(0x0B, 0x1F, 0x3A)
    p = d.add_paragraph(f"{doc.business}  |  Period: {doc.period}")
    p.runs[0].font.color.rgb = RGBColor(0x47, 0x55, 0x69)
    p = d.add_paragraph(f"Generated {doc.generated} by BusinessPilot AI")
    p.runs[0].font.size = Pt(9)
    for b in doc.blocks:
        if b.kind == "h1":
            h = d.add_heading(b.text, 1)
            for r in h.runs: r.font.color.rgb = RGBColor(0x0B, 0x1F, 0x3A)
        elif b.kind == "h2":
            h = d.add_heading(b.text, 2)
            for r in h.runs: r.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        elif b.kind == "p":
            d.add_paragraph(b.text)
        elif b.kind == "note":
            p = d.add_paragraph(); run = p.add_run(b.text); run.italic = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(0x47, 0x55, 0x69)
        elif b.kind == "bullets":
            for it in b.items:
                d.add_paragraph(it, style="List Bullet")
        elif b.kind == "image":
            d.add_picture(io.BytesIO(b.image), width=Inches(6.4))
            d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            c = d.add_paragraph(b.text); c.alignment = WD_ALIGN_PARAGRAPH.CENTER; c.runs[0].font.size = Pt(8.5) if c.runs else None
        elif b.kind == "table" and b.rows:
            tb = d.add_table(rows=1, cols=len(b.rows[0]))
            tb.style = "Table Grid"
            for j, h in enumerate(b.rows[0]):
                cell = tb.rows[0].cells[j]; cell.text = ""
                run = cell.paragraphs[0].add_run(h); run.bold = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(255, 255, 255)
                shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "0B1F3A"); cell._tc.get_or_add_tcPr().append(shd)
            for r in b.rows[1:]:
                cells = tb.add_row().cells
                for j, v in enumerate(r):
                    cells[j].text = ""; cells[j].paragraphs[0].add_run(str(v)[:300]).font.size = Pt(9)
            d.add_paragraph()
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


def _cell(v):
    """Convert any pandas/numpy value into something openpyxl accepts (NA -> blank, no control characters)."""
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().replace(tzinfo=None)
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str):
        return _ILLEGAL.sub("", v)[:32000]
    return v


def render_xlsx(doc: ReportDoc, bundle, sections: list[str]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    b = bundle
    wb = Workbook()
    HEAD = PatternFill("solid", fgColor="0B1F3A")

    def sheet(name: str, df: pd.DataFrame, formats: dict | None = None, first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = name[:31]
        ws.append([str(c) for c in df.columns])
        for row in df.itertuples(index=False):
            ws.append([_cell(v) for v in row])
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions
        for i, col in enumerate(df.columns, 1):
            fmt = (formats or {}).get(col)
            if fmt:
                for cell in ws.iter_cols(min_col=i, max_col=i, min_row=2).__next__():
                    cell.number_format = fmt
            width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)] + [8])
            ws.column_dimensions[get_column_letter(i)].width = min(width + 3, 60)
        return ws

    cover = pd.DataFrame({"Item": ["Report", "Business", "Period", "Generated", "Rows analysed", "Data-quality score"],
                          "Value": [doc.title, doc.business, doc.period, doc.generated, len(b.data), f"{b.quality.score}/100"]})
    ws = sheet("Summary", cover, first=True)
    ws.column_dimensions["B"].width = 50

    if b.metrics:
        rows = []
        for m in b.metrics:
            rows.append({"Metric": m.label, "Value": m.value, "Formula": m.formula, "Basis / assumptions": m.basis, "Meaning": m.explanation})
        df = pd.DataFrame(rows)
        ws = sheet("KPIs", df)
        for i, m in enumerate(b.metrics, 2):
            ws.cell(row=i, column=2).number_format = "0.0%" if m.key in PCT_KEYS else ("#,##0.00" if m.key in MONEY_KEYS else "#,##0.##")
    if "trends" in sections and not b.monthly.empty:
        cols = ["period"] + [c for c in ("revenue", "expenses", "cogs", "calc_profit", "quantity") if c in b.monthly]
        m = b.monthly[cols].copy(); m["period"] = m["period"].astype(str)
        m = m.rename(columns={"period": "Month", "revenue": "Revenue", "expenses": "Expenses", "cogs": "COGS", "calc_profit": "Profit", "quantity": "Units"})
        ws = sheet("Monthly", m, {c: "#,##0.00" for c in m.columns if c != "Month"})
        if len(m) >= 2 and "Revenue" in m:
            ch = LineChart(); ch.title = "Monthly trend"; ch.height, ch.width = 8, 18
            ch.add_data(Reference(ws, min_col=2, max_col=len(m.columns), min_row=1, max_row=len(m) + 1), titles_from_data=True)
            ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(m) + 1))
            ws.add_chart(ch, f"{get_column_letter(len(m.columns) + 2)}2")
    if "products" in sections and not b.products.empty:
        sheet("Products", b.products.rename(columns={"product": "Product", "share": "Share of total"}), {"Share of total": "0.0%", b.products.columns[1]: "#,##0.00"})
    if "expenses" in sections and not b.expenses.empty:
        sheet("Expenses", b.expenses.rename(columns={"category": "Category", "expenses": "Expenses", "share": "Share of total"}), {"Expenses": "#,##0.00", "Share of total": "0.0%"})
    if "forecast" in sections and b.forecast is not None and b.forecast.available:
        f = b.forecast.forecast.rename(columns={"timestamp": "Month", "point": "Forecast", "lower": "Lower bound", "upper": "Upper bound"}).copy()
        f["Month"] = f["Month"].dt.strftime("%Y-%m")
        sheet("Forecast", f, {c: "#,##0.00" for c in ("Forecast", "Lower bound", "Upper bound")})
        sheet("Model comparison", b.forecast.comparison, {"MAE": "#,##0.00", "RMSE": "#,##0.00", "MAPE": "0.0"})
    ins = [{"Section": SECTION_TITLES[i.section], "Type": KINDS[i.kind], "Insight": i.text} for i in b.insights.insights]
    if b.insights.llm_status == "used":
        ins.append({"Section": "AI-generated commentary", "Type": "Interpretation (external AI)", "Insight": b.insights.llm_text})
    if ins:
        ws = sheet("Insights", pd.DataFrame(ins)); ws.column_dimensions["C"].width = 100
        for row in ws.iter_rows(min_row=2):
            row[2].alignment = Alignment(wrap_text=True, vertical="top")
    sheet("Data quality", b.quality.per_column)
    sheet("Column mapping", pd.DataFrame([{"Business field": ROLES[r]["label"], "Source column": c} for r, c in b.std.mapping.columns.items()]))
    data = b.data.head(100_000).copy()
    data.columns = [str(c).replace("other::", "") for c in data.columns]
    sheet("Data", data)
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- one call for the UI
def export_all(bundle, report_type: str, sections: list[str], business: str, include_llm: bool = True) -> dict[str, tuple[str, bytes]]:
    """Return {'pdf': (filename, bytes), 'docx': ..., 'xlsx': ...}. Raises ReportError on any failure."""
    doc = build_report(bundle, report_type, sections, business, include_llm)
    out: dict[str, tuple[str, bytes]] = {}
    for ext, fn in (("pdf", lambda: render_pdf(doc)), ("docx", lambda: render_docx(doc)), ("xlsx", lambda: render_xlsx(doc, bundle, sections))):
        try:
            data = fn()
        except ReportError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ReportError(f"Could not create the {ext.upper()} file ({type(exc).__name__}: {str(exc)[:150]}).") from exc
        if not data:
            raise ReportError(f"The {ext.upper()} file came out empty.")
        out[ext] = (make_filename(business, report_type, ext), data)
    return out
