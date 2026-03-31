from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Arial Unicode for full Romanian character support
_ARIAL_PATH  = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_ARIAL_BOLD  = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_ARIAL_IT    = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
_ARIAL_BI    = "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"
pdfmetrics.registerFont(TTFont("Arial",        _ARIAL_PATH))
pdfmetrics.registerFont(TTFont("Arial-Bold",   _ARIAL_BOLD))
pdfmetrics.registerFont(TTFont("Arial-Italic", _ARIAL_IT))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", _ARIAL_BI))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                   italic="Arial-Italic", boldItalic="Arial-BoldItalic")

FONT      = "Arial"
FONT_BOLD = "Arial-Bold"
FONT_IT   = "Arial-Italic"

# ── Palette ──────────────────────────────────────────────────────────────────
NAVY   = HexColor("#1B2B4B")
GOLD   = HexColor("#F0A500")
LIGHT  = HexColor("#F5F7FA")
MID    = HexColor("#DDE3ED")
WHITE  = colors.white
DARK   = HexColor("#2D2D2D")
GREY   = HexColor("#6B7280")

W, H = A4

# ── Custom Flowables ──────────────────────────────────────────────────────────

class SectionHeader(Flowable):
    """Full-width navy band with gold accent bar + section number + title."""
    def __init__(self, number, title, width=None):
        super().__init__()
        self.number = number
        self.title  = title
        self.w      = width or (W - 30*mm)
        self.height = 18*mm

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(NAVY)
        c.roundRect(0, 0, self.w, self.height, 3, fill=1, stroke=0)
        # Gold accent left bar
        c.setFillColor(GOLD)
        c.rect(0, 0, 4, self.height, fill=1, stroke=0)
        # Number pill
        c.setFillColor(GOLD)
        c.roundRect(10, 4, 22, 10, 2, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(21, 7.5, self.number)
        # Title
        c.setFillColor(WHITE)
        c.setFont(FONT_BOLD, 11)
        c.drawString(40, 6, self.title.upper())

    def wrap(self, availW, availH):
        return self.w, self.height


class GoldDivider(Flowable):
    def __init__(self, width=None):
        super().__init__()
        self.w = width or (W - 30*mm)

    def draw(self):
        c = self.canv
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(0, 0, self.w, 0)

    def wrap(self, availW, availH):
        return self.w, 2


class MetricBox(Flowable):
    """Highlighted stat box."""
    def __init__(self, value, label, width=55*mm, height=22*mm):
        super().__init__()
        self.value  = value
        self.label  = label
        self.bw     = width
        self.bh     = height

    def draw(self):
        c = self.canv
        c.setFillColor(LIGHT)
        c.roundRect(0, 0, self.bw, self.bh, 4, fill=1, stroke=0)
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.roundRect(0, 0, self.bw, self.bh, 4, fill=0, stroke=1)
        c.setFillColor(GOLD)
        c.setFont(FONT_BOLD, 16)
        c.drawCentredString(self.bw/2, self.bh - 12, self.value)
        c.setFillColor(NAVY)
        c.setFont(FONT, 7)
        # wrap label
        words = self.label.split()
        line, lines = "", []
        for w in words:
            test = (line + " " + w).strip()
            if c.stringWidth(test, FONT, 7) < self.bw - 8:
                line = test
            else:
                lines.append(line); line = w
        lines.append(line)
        y = self.bh - 23
        for l in lines:
            c.drawCentredString(self.bw/2, y, l); y -= 9

    def wrap(self, availW, availH):
        return self.bw, self.bh


# ── Styles ────────────────────────────────────────────────────────────────────

def make_styles():
    base = getSampleStyleSheet()

    def s(name, **kw):
        return ParagraphStyle(name, **kw)

    styles = {
        "body": s("body", fontName=FONT, fontSize=9.5, leading=15,
                  textColor=DARK, alignment=TA_JUSTIFY, spaceAfter=6),
        "body_left": s("body_left", fontName=FONT, fontSize=9.5,
                       leading=15, textColor=DARK, alignment=TA_LEFT, spaceAfter=4),
        "h2": s("h2", fontName=FONT_BOLD, fontSize=11, textColor=NAVY,
                spaceBefore=10, spaceAfter=4, leading=16),
        "h3": s("h3", fontName=FONT_BOLD, fontSize=9.5, textColor=GOLD,
                spaceBefore=6, spaceAfter=3, leading=14),
        "bullet": s("bullet", fontName=FONT, fontSize=9.5, leading=14,
                    textColor=DARK, leftIndent=12, bulletIndent=0,
                    spaceAfter=3),
        "small": s("small", fontName=FONT, fontSize=8, leading=12,
                   textColor=GREY),
        "tag": s("tag", fontName=FONT_BOLD, fontSize=8, textColor=NAVY,
                 leading=12),
        "footer": s("footer", fontName=FONT, fontSize=7.5,
                    textColor=GREY, alignment=TA_CENTER),
        "quote": s("quote", fontName=FONT_IT, fontSize=10.5,
                   textColor=NAVY, leading=16, leftIndent=10, rightIndent=10,
                   spaceAfter=8, spaceBefore=8),
        "confidence": s("confidence", fontName=FONT_BOLD, fontSize=10,
                        textColor=WHITE, alignment=TA_CENTER),
    }
    return styles


# ── Page Template ─────────────────────────────────────────────────────────────

def on_page(canvas, doc):
    canvas.saveState()
    # Top accent line
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - 8, W, 8, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, H - 8, 60, 8, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(LIGHT)
    canvas.rect(0, 0, W, 14, fill=1, stroke=0)
    canvas.setFont(FONT, 7)
    canvas.setFillColor(GREY)
    canvas.drawString(15*mm, 4.5, "AI Workflow Intelligence — Romanian SME Market | Confidential")
    canvas.drawRightString(W - 15*mm, 4.5, f"March 2026  |  Page {doc.page}")
    canvas.restoreState()


def on_cover(canvas, doc):
    # Full navy background
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Gold top band
    canvas.setFillColor(GOLD)
    canvas.rect(0, H - 18*mm, W, 18*mm, fill=1, stroke=0)
    # Bottom band
    canvas.setFillColor(HexColor("#0F1E35"))
    canvas.rect(0, 0, W, 40*mm, fill=1, stroke=0)
    # Decorative vertical gold stripe
    canvas.setFillColor(GOLD)
    canvas.rect(18*mm, 0, 3, H, fill=1, stroke=0)
    # Footer text
    canvas.setFont(FONT, 8)
    canvas.setFillColor(HexColor("#8899BB"))
    canvas.drawString(26*mm, 12*mm, "CONFIDENTIAL — FOR PARTNER REVIEW ONLY  |  MARCH 2026")


# ── Cover Page ────────────────────────────────────────────────────────────────

def cover_page(styles):
    elems = []

    # Logo-area placeholder — thin gold line
    elems.append(Spacer(1, 22*mm))
    elems.append(HRFlowable(width="100%", thickness=0, color=WHITE))

    title_style = ParagraphStyle("cover_title", fontName=FONT_BOLD,
                                  fontSize=28, textColor=WHITE, leading=36,
                                  alignment=TA_LEFT, spaceAfter=4)
    sub_style   = ParagraphStyle("cover_sub", fontName=FONT,
                                  fontSize=13, textColor=GOLD, leading=18,
                                  alignment=TA_LEFT, spaceAfter=6)
    tag_style   = ParagraphStyle("cover_tag", fontName=FONT,
                                  fontSize=10, textColor=HexColor("#8899BB"),
                                  leading=15, alignment=TA_LEFT)

    elems.append(Spacer(1, 50*mm))
    elems.append(Paragraph("AI Workflow Intelligence", title_style))
    elems.append(Paragraph("A Consultancy Platform for the Romanian SME Market", sub_style))
    elems.append(Spacer(1, 6*mm))
    elems.append(GoldDivider(120*mm))
    elems.append(Spacer(1, 6*mm))
    elems.append(Paragraph("Strategic Business Assessment &amp; Partner Investment Opportunity", tag_style))
    elems.append(Spacer(1, 4*mm))
    elems.append(Paragraph("Prepared for Partner Review  ·  March 2026", tag_style))

    # Metric teasers at bottom
    elems.append(Spacer(1, 45*mm))

    metric_data = [
        ("€500K–750K", "Year 3 Revenue\nProjection"),
        ("~500K+", "Romanian SMEs\nAddressable"),
        ("85%", "Confidence in\n12-Month Viability"),
        ("€0", "External Funding\nNeeded at Launch"),
    ]
    boxes = []
    for val, lbl in metric_data:
        boxes.append(MetricBox(val, lbl, width=38*mm, height=22*mm))

    tbl = Table([boxes], colWidths=[42*mm]*4)
    tbl.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "CENTER"),
                              ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    elems.append(tbl)

    elems.append(PageBreak())
    return elems


# ── Helpers ───────────────────────────────────────────────────────────────────

def section(number, title):
    return [Spacer(1, 5*mm), SectionHeader(number, title), Spacer(1, 4*mm)]

def h2(text, styles):
    return Paragraph(text, styles["h2"])

def h3(text, styles):
    return Paragraph(text, styles["h3"])

def body(text, styles, mode="body"):
    return Paragraph(text, styles[mode])

def bullet(items, styles, symbol="•"):
    return [Paragraph(f"{symbol}  {t}", styles["bullet"]) for t in items]

def sp(n=1):
    return Spacer(1, n * 3*mm)

def gold_box(text, styles):
    """A highlighted quote/call-out box."""
    tbl = Table([[Paragraph(text, styles["quote"])]],
                colWidths=[W - 30*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), LIGHT),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING",   (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LINEAFTER",  (0,0), (0,-1), 3, GOLD),
    ]))
    return tbl


# ── Document Sections ─────────────────────────────────────────────────────────

def exec_summary(styles):
    elems = section("00", "Executive Summary")
    elems.append(gold_box(
        '"We map how your business actually works, identify where AI can save '
        'time and money, and give you a prioritised action plan — with a '
        'business case your accountant can read."',
        styles))
    elems.append(sp())
    elems.append(body(
        "This document presents the strategic assessment of <b>AI Workflow Intelligence</b>, "
        "a consultancy platform targeting Romanian small and mid-sized enterprises (SMEs). "
        "The platform provides structured workflow mapping and AI automation opportunity "
        "identification — delivered as a proprietary consulting tool, not a product sold to clients.",
        styles))
    elems.append(body(
        "The assessment validates the idea using four enterprise frameworks: "
        "<b>Business Model Canvas, Blue Ocean Strategy, Innovator's Dilemma, and Lean Startup</b>. "
        "A critical thinking audit stress-tests five core assumptions. The conclusion: this is a "
        "viable, capital-light consultancy business with a clear path to a scalable platform "
        "asset, rated <b>~85% viable within 12 months</b> of launch.",
        styles))
    elems.append(sp())
    elems.append(h3("Key Highlights", styles))
    elems += bullet([
        "Global AI adoption gap: 65% of organisations experiment with AI, fewer than 11% capture meaningful value",
        "Romanian SMEs are 5–7 years behind Western Europe on digitalisation — the market is at inflection point",
        "PNRR EU funding unlocks willingness-to-pay, removing the primary commercial objection",
        "No structured AI workflow consultancy exists at SME price point in Romania today",
        "Zero external capital required to launch; consulting fees self-fund tool development",
        "Year 3 revenue projection: €500,000–€750,000 with 5 consultants + methodology licensing",
    ], styles)
    elems.append(PageBreak())
    return elems


def section1(styles):
    elems = section("01", "The Opportunity")
    elems.append(h2("Global AI Adoption: A Market Defined by Failure to Capture Value", styles))
    elems.append(body(
        "AI investment is accelerating at an unprecedented rate. Yet according to McKinsey's 2024 "
        "State of AI report, <b>65% of organisations are experimenting with generative AI</b> — but "
        "fewer than <b>11% report meaningful revenue or cost impact</b>. The gap between adoption "
        "and value realisation is vast, persistent, and structural. It is also the market.",
        styles))
    elems.append(sp(0.5))

    # Stat boxes
    stats = [
        ("65%", "Organisations\nexperimenting with AI"),
        ("<11%", "Report meaningful\nbusiness impact"),
        ("$500K+", "Typical Big Four AI\nengagement cost"),
        ("5–7 yrs", "Romania behind\nWestern Europe"),
    ]
    boxes = [MetricBox(v, l, width=38*mm, height=22*mm) for v, l in stats]
    tbl = Table([boxes], colWidths=[42*mm]*4)
    tbl.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),
                              ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    elems.append(tbl)
    elems.append(sp())

    elems.append(h2("Why Romania? Four Structural Tailwinds", styles))

    reasons = [
        ("PNRR & EU Digitalistion Funding",
         "Romania's National Recovery and Resilience Plan allocates billions to SME digitalisation. "
         "Companies can access non-reimbursable grants for digital transformation. This converts the "
         "hardest sales objection — price — into a near-zero net cost for early clients."),
        ("Low AI Consultancy Penetration at SME Level",
         "Big Four AI practices exist in Bucharest but target corporations. Regional consultants "
         "have no structured AI offering. The sub-€50M revenue company has essentially zero access "
         "to quality AI strategy advice. The field is open."),
        ("High Process Inefficiency Density",
         "Romanian SMEs in manufacturing, professional services, logistics, and retail carry enormous "
         "manual process overhead — paper workflows, Excel-driven operations, WhatsApp as business "
         "infrastructure. The automation delta between current state and achievable state is very large, "
         "which means ROI cases write themselves."),
        ("Trust Economy Dynamics",
         "Romanian business culture is relationship-driven. A strong outcome for one client in an "
         "industry cluster — manufacturing in Cluj, logistics in Timișoara — propagates rapidly "
         "through referral networks. Customer acquisition cost drops as reputation builds."),
    ]
    for title, desc in reasons:
        elems.append(h3(f"▸  {title}", styles))
        elems.append(body(desc, styles))

    elems.append(PageBreak())
    return elems


def section2(styles):
    elems = section("02", "The Problem — 7 Core Pain Points")
    elems.append(body(
        "Before assessing the solution, we must be precise about the problem. "
        "These seven pain points are ranked by frequency and severity across mid-market organisations. "
        "Pain points 1–3 are <b>pre-implementation</b> blockers; points 4–7 are <b>post-implementation</b> failures. "
        "The platform targets points 1–3 as its primary scope.",
        styles))
    elems.append(sp())

    pain_points = [
        ("01", "Strategy Vacuum",
         "C-suites know they must act on AI but lack vocabulary and frameworks to translate board "
         "pressure into operational decisions. Each department runs isolated pilots; no one owns the "
         "aggregate picture. The CEO cannot answer: \"What is our AI roadmap?\""),
        ("02", "Workflow Opacity",
         "Organisations have ISO-certified documentation describing the <i>intended</i> workflow, not the "
         "<i>actual</i> one. The delta is enormous. Process mining tools (Celonis, UiPath Process Mining) "
         "are a $2B+ market precisely because 'we don't know our own processes' is a universal problem."),
        ("03", "ROI Measurement Problem",
         "The #1 blocker for mid-market AI adoption. Finance requires a business case before budget "
         "approval. AI ROI is notoriously hard to quantify upfront: benefits are diffuse, baselines "
         "are poorly measured, and attribution is contested. Without a credible ROI model, proposals die."),
        ("04", "Change Management & Fear",
         "Technology adoption fails at the human layer more often than the technical layer. Employees "
         "fear job displacement and resist adoption — or adopt without governance, creating shadow-AI "
         "risk with sensitive data."),
        ("05", "The Integration Problem",
         "AI pilots succeed in sandboxes but fail on real data infrastructure: legacy ERP systems, "
         "fragmented silos, inconsistent data quality, and IT governance that moves slower than business."),
        ("06", "Talent Gap",
         "Mid-market companies cannot hire AI engineers and cannot afford Big Four consultants "
         "(€500K–€2M+ per engagement). The gap between 'we need help' and 'we can afford help' "
         "is exactly the market being addressed."),
        ("07", "Measurement Drift",
         "Organisations that successfully deploy AI often lack instrumentation to track whether it "
         "continues working. Models drift. Business context changes. Yesterday's AI win becomes "
         "today's silent failure."),
    ]

    for num, title, desc in pain_points:
        row = Table(
            [[Paragraph(num, ParagraphStyle("pnum", fontName=FONT_BOLD,
                                             fontSize=14, textColor=GOLD, alignment=TA_CENTER)),
              Paragraph(f"<b>{title}</b><br/><font size=9>{desc}</font>",
                        ParagraphStyle("pdesc", fontName=FONT, fontSize=9.5,
                                       leading=14, textColor=DARK))]],
            colWidths=[18*mm, W - 30*mm - 18*mm])
        row.setStyle(TableStyle([
            ("VALIGN",       (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING",  (0,0), (0,-1),  4),
            ("RIGHTPADDING", (0,0), (0,-1),  8),
            ("TOPPADDING",   (0,0), (-1,-1), 6),
            ("BOTTOMPADDING",(0,0), (-1,-1), 6),
            ("LINEBELOW",    (0,0), (-1,-1), 0.5, MID),
        ]))
        elems.append(row)

    elems.append(PageBreak())
    return elems


def section3(styles):
    elems = section("03", "The Solution")
    elems.append(gold_box(
        "A <b>consultant-owned workflow intelligence tool</b> — a structured methodology encoded in "
        "software that makes the consultant faster, more credible, and more consistent when running "
        "client engagements. This is NOT a SaaS product sold to clients.",
        styles))
    elems.append(sp())
    elems.append(body(
        "The client deliverable is a <b>workflow map + automation opportunity report</b>. The software "
        "is the internal lever that enables a single consultant to deliver McKinsey-quality structured "
        "analysis at a price Romanian SMEs can afford — and in days, not months.",
        styles))
    elems.append(sp())
    elems.append(h2("The 5-Module Platform Architecture", styles))

    modules = [
        ("Module 1", "Pre-Engagement Intake",
         "Structured questionnaire sent to client before the workshop. Collects: company size, "
         "industry, departments, existing tools, known pain points. Ensures workshop time is used "
         "for insight, not data collection."),
        ("Module 2", "Workshop Facilitation Layer",
         "Guided interview protocol per business function (Finance, Operations, Sales, HR, etc.). "
         "The consultant follows a structured screen-based flow, capturing: tasks, owners, duration, "
         "frequency, inputs/outputs, exception rates, current tools."),
        ("Module 3", "Process Map Builder",
         "As tasks are captured, the tool structures them into a visual workflow. The map is a "
         "byproduct of structured data — not a drawing the consultant makes manually. Consistent, "
         "professional output every time."),
        ("Module 4", "AI Analysis Layer",
         "The LLM core. Each captured task is evaluated against automation criteria: rules-based vs "
         "judgment-based, data availability, repetition frequency, error cost. Output: scored task "
         "inventory with automation feasibility tiers (quick wins / medium-term / not suitable)."),
        ("Module 5", "Opportunity Report Generator",
         "Transforms the scored inventory into a client-ready report: executive summary, process maps, "
         "automation opportunity matrix, estimated time/cost savings, recommended next steps. "
         "Workshop to polished report in hours, not weeks."),
    ]

    for mod, title, desc in modules:
        row = Table(
            [[Paragraph(f"<b>{mod}</b>",
                        ParagraphStyle("mnum", fontName=FONT_BOLD, fontSize=8,
                                       textColor=WHITE, alignment=TA_CENTER, leading=10)),
              Paragraph(f"<b>{title}</b><br/><font size=9 color='#2D2D2D'>{desc}</font>",
                        ParagraphStyle("mdesc", fontName=FONT, fontSize=9.5,
                                       leading=14, textColor=DARK))]],
            colWidths=[22*mm, W - 30*mm - 22*mm])
        row.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (0,-1), NAVY),
            ("BACKGROUND",   (1,0), (1,-1), LIGHT),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING",   (0,0), (-1,-1), 8),
            ("BOTTOMPADDING",(0,0), (-1,-1), 8),
            ("LINEBELOW",    (0,0), (-1,-1), 2, WHITE),
        ]))
        elems.append(row)

    elems.append(PageBreak())
    return elems


def _bmc_cell(text, bold=False, color=DARK, size=9):
    """Paragraph cell for BMC table."""
    fn = FONT_BOLD if bold else FONT
    return Paragraph(text, ParagraphStyle(
        "bmc", fontName=fn, fontSize=size, leading=size*1.45,
        textColor=color, wordWrap="CJK", spaceAfter=0))

def _status_badge(text, bg, fg):
    tbl = Table([[Paragraph(text, ParagraphStyle(
        "badge", fontName=FONT_BOLD, fontSize=7.5, textColor=fg,
        leading=10, alignment=TA_CENTER))]],
        colWidths=[26*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), bg),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("ROUNDEDCORNERS", [3]),
    ]))
    return tbl

def section4(styles):
    elems = section("04", "Business Model Canvas")

    GREEN = HexColor("#2E7D32"); GREEN_BG = HexColor("#E8F5E9")
    AMBER = HexColor("#E65100"); AMBER_BG = HexColor("#FFF3E0")
    BLUE  = HexColor("#1565C0"); BLUE_BG  = HexColor("#E3F2FD")

    rows = [
        ("Customer\nSegments",
         "SMEs €1M–€50M revenue, 10–200 employees. Buyer: Owner / CEO "
         "(not CTO — most don't have one). Priority verticals: manufacturing, "
         "professional services, logistics.",
         "Defined", GREEN_BG, GREEN),
        ("Value\nProposition",
         "Workflow map + automation opportunity report + ROI business case. "
         "Delivered in days at a price point inaccessible via Big Four.",
         "Painkiller", GREEN_BG, GREEN),
        ("Channels",
         "Direct outreach · Accountant/tax advisor referrals · PNRR grant "
         "facilitators · Industry associations · Chamber of Commerce",
         "Clear path", BLUE_BG, BLUE),
        ("Customer\nRelationships",
         "Per-engagement (land) → multi-department expansion → annual "
         "re-assessment subscription.",
         "Defined", GREEN_BG, GREEN),
        ("Revenue\nStreams",
         "€2,000–€8,000 per single-department assessment. "
         "€5,000–€20,000 full-company assessment. "
         "Follow-on implementation projects at higher fees.",
         "Validated", GREEN_BG, GREEN),
        ("Key\nResources",
         "Proprietary methodology + the tool that encodes it. "
         "This IS the unfair advantage — it compounds with every engagement.",
         "Must build", AMBER_BG, AMBER),
        ("Key\nPartnerships",
         "PNRR consultants (distribution) · Accounting firms · Regional "
         "business associations · Automation tool vendors (UiPath, Make, n8n)",
         "To develop", AMBER_BG, AMBER),
        ("Key\nActivities",
         "Client workshops · Methodology refinement · Tool development · "
         "Report delivery · Benchmark data accumulation",
         "Defined", GREEN_BG, GREEN),
        ("Cost\nStructure",
         "Tool development (one-time + maintenance) · Consultant time · "
         "Travel · AI inference costs",
         "Low & controllable", GREEN_BG, GREEN),
    ]

    # Column widths: block 22%, description 58%, status 20%
    TW = W - 30*mm
    cw = [TW * 0.18, TW * 0.60, TW * 0.22]

    header_ps = ParagraphStyle("hdr", fontName=FONT_BOLD, fontSize=9,
                                textColor=WHITE, leading=13, alignment=TA_CENTER)
    table_data = [[Paragraph("BLOCK", header_ps),
                   Paragraph("DESCRIPTION", header_ps),
                   Paragraph("STATUS", header_ps)]]

    for block, desc, status, sbg, sfg in rows:
        table_data.append([
            _bmc_cell(block, bold=True, color=NAVY, size=9),
            _bmc_cell(desc, size=9),
            _status_badge(status, sbg, sfg),
        ])

    tbl = Table(table_data, colWidths=cw, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  NAVY),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, LIGHT]),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
        ("ALIGN",         (2,0),  (2,-1),  "CENTER"),
        ("GRID",          (0,0),  (-1,-1), 0.3, MID),
        ("TOPPADDING",    (0,0),  (-1,-1), 7),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 7),
        ("LEFTPADDING",   (0,0),  (-1,-1), 8),
        ("RIGHTPADDING",  (0,0),  (-1,-1), 6),
        ("LINEBEFORE",    (0,0),  (0,-1),  3, GOLD),
    ]))
    elems.append(tbl)
    elems.append(PageBreak())
    return elems


def section5(styles):
    elems = section("05", "Market Positioning — Blue Ocean Strategy")
    elems.append(body(
        "The current competitive landscape has three zones — none of which serve the Romanian SME "
        "AI assessment need. This platform occupies white space that none of the existing players "
        "will move into: the intersection of structured methodology, AI-native analysis, and "
        "SME-accessible pricing.",
        styles))
    elems.append(sp())

    elems.append(h2("Competitive Landscape", styles))

    def cp(text, bold=False, color=DARK, align=TA_LEFT, size=8.5):
        return Paragraph(text, ParagraphStyle("cp2", fontName=FONT_BOLD if bold else FONT,
            fontSize=size, textColor=color, leading=size*1.45, alignment=align))

    def check_cell(val):
        if val == "Yes":     return HexColor("#E8F5E9"), HexColor("#2E7D32"), "Yes"
        if val == "No":      return HexColor("#FFEBEE"), HexColor("#C62828"), "No"
        return HexColor("#FFF8E1"), HexColor("#E65100"), "Partial"

    TW = W - 30*mm
    cw = [TW*0.33, TW*0.155, TW*0.145, TW*0.155, TW*0.215]

    hdr_ps  = ParagraphStyle("ch2", fontName=FONT_BOLD, fontSize=8.5, textColor=WHITE,
                              leading=12, alignment=TA_CENTER)
    gold_ps = ParagraphStyle("cg2", fontName=FONT_BOLD, fontSize=8.5, textColor=NAVY,
                              leading=12, alignment=TA_CENTER)
    headers = [cp("", size=8.5),
               Paragraph("Big Four\nConsultants",    hdr_ps),
               Paragraph("RPA / AI\nVendors",         hdr_ps),
               Paragraph("Generic\nConsultants",      hdr_ps),
               Paragraph("AI Workflow\nIntelligence", gold_ps)]

    raw_rows = [
        ("Structured AI methodology", "No",  "No",      "No",      "Yes"),
        ("SME-accessible pricing",    "No",  "Partial", "Yes",     "Yes"),
        ("Romanian market focus",     "No",  "No",      "Partial", "Yes"),
        ("ROI quantification",        "Yes", "No",      "No",      "Yes"),
        ("Fast turnaround (days)",    "No",  "No",      "Partial", "Yes"),
        ("Tool-agnostic advice",      "Yes", "No",      "Yes",     "Yes"),
        ("PNRR integration",          "No",  "No",      "Partial", "Yes"),
    ]

    comp_data = [headers]
    cell_colors = []
    for ri, (feat, *vals) in enumerate(raw_rows, 1):
        row = [cp(feat, bold=True, color=NAVY)]
        for ci, v in enumerate(vals, 1):
            bg, fg, label = check_cell(v)
            row.append(cp(label, bold=True, color=fg, align=TA_CENTER))
            cell_colors.append((ri, ci, bg))
        comp_data.append(row)

    tbl = Table(comp_data, colWidths=cw, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0,0),  (-1,0),  NAVY),
        ("BACKGROUND",    (-1,0), (-1,0),  GOLD),
        ("ALIGN",         (1,0),  (-1,-1), "CENTER"),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
        ("GRID",          (0,0),  (-1,-1), 0.3, MID),
        ("TOPPADDING",    (0,0),  (-1,-1), 6),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 6),
        ("LEFTPADDING",   (0,0),  (-1,-1), 6),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, LIGHT]),
    ]
    for ri, ci, bg in cell_colors:
        style_cmds.append(("BACKGROUND", (ci,ri), (ci,ri), bg))
    tbl.setStyle(TableStyle(style_cmds))
    elems.append(tbl)
    elems.append(sp())

    elems.append(h2("Four Actions Framework (Blue Ocean)", styles))
    actions = [
        ("ELIMINATE", GOLD, NAVY,
         "6-month engagement timelines · Army-of-consultants delivery model · "
         "Generic 'AI strategy deck' outputs with no operational specificity"),
        ("REDUCE", NAVY, WHITE,
         "Dependency on senior human expert time · Client data preparation burden · "
         "Time from workshop to actionable output"),
        ("RAISE", HexColor("#1565C0"), WHITE,
         "ROI quantification credibility — auditable, benchmarked, CFO-ready · "
         "Methodology consistency across engagements · Speed of discovery"),
        ("CREATE", HexColor("#2E7D32"), WHITE,
         "Romanian SME automation benchmark database (network effect moat) · "
         "PNRR-integrated service packaging · Methodology franchise model"),
    ]
    act_rows = []
    for label, bg, fg, text in actions:
        act_rows.append([
            Paragraph(f"<b>{label}</b>",
                      ParagraphStyle("al", fontName=FONT_BOLD, fontSize=9,
                                     textColor=fg, alignment=TA_CENTER)),
            Paragraph(text, ParagraphStyle("ad", fontName=FONT, fontSize=9,
                                            leading=13, textColor=DARK))
        ])
    act_tbl = Table(act_rows, colWidths=[28*mm, W - 30*mm - 28*mm])
    act_style = [
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LINEBELOW",    (0,0), (-1,-1), 1.5, WHITE),
    ]
    for i, (_, bg, _, _) in enumerate(actions):
        act_style.append(("BACKGROUND", (0,i), (0,i), bg))
        act_style.append(("BACKGROUND", (1,i), (1,i), LIGHT if i % 2 == 0 else WHITE))
    act_tbl.setStyle(TableStyle(act_style))
    elems.append(act_tbl)
    elems.append(PageBreak())
    return elems


def section6(styles):
    elems = section("06", "Strategic Framework Validation")

    elems.append(h2("Innovator's Dilemma — Disruptive Innovation Profile", styles))
    elems.append(body(
        "This venture follows a classic <b>disruptive innovation pattern</b>. Big Four AI consulting is "
        "a sustaining innovation for large enterprise clients — better, more comprehensive, and more "
        "expensive. AI Workflow Intelligence is disruptive: it is simpler, faster, and cheaper than "
        "the incumbent offering, and it targets a segment (Romanian SMEs) that the incumbents "
        "<i>cannot and will not serve</i> at this price point. Incumbents have no incentive to respond "
        "because the segment is beneath their margin floor.",
        styles))
    elems.append(sp())

    elems.append(h2("Technology Adoption Lifecycle — Beachhead Strategy", styles))
    elems.append(body(
        "The beachhead segment is <b>manufacturing SMEs in Cluj-Napoca / Transylvania region</b> or "
        "<b>professional services firms (accounting, legal) in Bucharest</b>. These segments have: "
        "(a) high process density, (b) measurable and quantifiable tasks, (c) existing digitisation "
        "pressure from clients and regulators, and (d) cluster dynamics enabling rapid referral growth. "
        "Crossing the Chasm from early adopters to pragmatists is enabled by the benchmark database — "
        "pragmatists need social proof ('other companies like us achieved X'), which the platform generates.",
        styles))
    elems.append(sp())

    elems.append(h2("ROIC > WACC — Path to Value Creation", styles))
    elems.append(body(
        "The capital-light model means WACC is effectively the opportunity cost of the founders' time. "
        "At €4,000 average engagement fee and 2 engagements per month, Year 1 generates €96,000 from "
        "a single consultant. Tool development costs are bounded and one-time. This clears ROIC > WACC "
        "within 6 months of first paid engagement — an unusually fast path to value creation for a "
        "technology-backed business.",
        styles))
    elems.append(sp())

    elems.append(h2("Lean Startup — Validated Learning Protocol", styles))
    elems.append(body(
        "The recommended launch sequence follows strict Lean Startup discipline: <b>validate the "
        "methodology before encoding it in software</b>. The first three engagements are run manually "
        "(spreadsheet + Miro board). Only after observing what works, what clients value, and where "
        "the process breaks down does software development begin. This prevents the most common "
        "failure mode in this category: building a platform before knowing what it needs to do.",
        styles))
    elems.append(PageBreak())
    return elems


def section7(styles):
    elems = section("07", "Critical Risk Assessment")
    elems.append(body(
        "Each assumption underlying this business was stress-tested using inversion analysis, "
        "pre-mortem thinking, and steelmanning of the opposing view.",
        styles))
    elems.append(sp())

    risks = [
        ("HIGH", "Willingness to Pay (€3K–€8K per engagement)",
         "Romanian SME owners are cost-conscious and sceptical of consultants who deliver decks. "
         "Without tangible output, price resistance is significant.",
         "Two levers neutralise this: (1) PNRR grant integration — client's net cost can be near zero. "
         "(2) Frame the deliverable as a <i>decision tool</i>, not a report. Pilot pricing at "
         "€1,500–€2,000 for first engagement eliminates perceived risk entirely."),
        ("MEDIUM", "Methodology Scalability Across Verticals",
         "A Finance workflow map looks different from a Manufacturing or Logistics map. "
         "Building a fully generic tool risks being mediocre at everything.",
         "The underlying data model is universal (inputs → tasks → decisions → outputs → handoffs). "
         "Vertical-specific content libraries (question banks, task taxonomies) are layered on top. "
         "Launch with one vertical, expand after 10+ validated engagements."),
        ("MEDIUM", "Scale Constraint: Consultants as Bottleneck",
         "A single consultant can realistically run 2–3 engagements/month. Revenue ceiling at "
         "solo operation is ~€150K–€200K/year — insufficient for a platform business.",
         "The tool is the franchise asset. After 20 engagements, begin training other consultants "
         "who license the methodology. This transforms a solo practice into a network model without "
         "raising capital."),
        ("LOW", "Large Platform Incumbents (Microsoft, SAP, ServiceNow)",
         "A major vendor could theoretically add AI workflow assessment to their existing platforms.",
         "Incumbents are horizontally oriented — they cannot go deep enough in methodology to produce "
         "a CFO-credible, Romania-specific ROI analysis. Their tools are for their own ecosystems. "
         "The moat is methodology depth and benchmark data, not technology."),
    ]

    severity_colors = {"HIGH": HexColor("#C62828"), "MEDIUM": HexColor("#E65100"), "LOW": HexColor("#2E7D32")}

    for severity, title, risk, mitigation in risks:
        col = severity_colors[severity]
        row = Table([
            [Paragraph(f"<b>{severity}</b>",
                       ParagraphStyle("sev", fontName=FONT_BOLD, fontSize=8,
                                      textColor=WHITE, alignment=TA_CENTER)),
             Paragraph(f"<b>{title}</b>", styles["h3"])],
            ["",
             Paragraph(f"<b>Risk:</b> {risk}", styles["body_left"])],
            ["",
             Paragraph(f"<b>Mitigation:</b> {mitigation}", styles["body_left"])],
        ], colWidths=[18*mm, W - 30*mm - 18*mm])
        row.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (0,-1), col),
            ("BACKGROUND",   (1,0), (1,-1), LIGHT),
            ("SPAN",         (0,0), (0,-1)),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING",   (0,0), (0,-1),  6),
            ("BOTTOMPADDING",(0,0), (0,-1),  6),
            ("LINEBELOW",    (0,0), (-1,-1), 2, WHITE),
        ]))
        elems.append(row)
        elems.append(sp(0.5))

    elems.append(PageBreak())
    return elems


def section8(styles):
    elems = section("08", "Go-To-Market Roadmap")

    phases = [
        ("Phase 0", "Months 1–3", "Validate the Methodology — No Software",
         GOLD, NAVY,
         [
             "Run 3 paid engagements manually (spreadsheet + Miro board)",
             "Charge €1,500–€2,000 per engagement",
             "Deliverable: workflow map + automation opportunity report as PDF",
             "Learn: What questions were wrong? What did clients value? Where did the process break down?",
             "Success signal: a client asks 'Can you do this for another department?'",
         ]),
        ("Phase 1", "Months 4–9", "Build the Tool — Beachhead Vertical",
         NAVY, WHITE,
         [
             "Encode the validated methodology into the 5-module platform",
             "Focus on Finance & Accounting vertical (highest process density, ROI speaks to CFO)",
             "Run 10+ engagements using the tool — refine based on real usage",
             "Establish first PNRR facilitator partnerships for distribution",
             "Target: €60,000–€80,000 revenue by end of Phase 1",
         ]),
        ("Phase 2", "Months 10–18", "Benchmark Network — Building the Moat",
         HexColor("#1565C0"), WHITE,
         [
             "Anonymised data from all engagements populates a Romanian SME benchmark database",
             "Benchmarks make ROI models more credible ('top quartile companies achieve X%')",
             "Network effect: more clients → better benchmarks → stronger sales proposition → more clients",
             "Expand to second vertical (manufacturing or logistics)",
             "Target: €150,000–€200,000 cumulative revenue",
         ]),
        ("Phase 3", "Months 18–30", "Scale — Franchise the Methodology",
         HexColor("#2E7D32"), WHITE,
         [
             "Train 2–4 additional consultants who license and use the platform",
             "White-label option for regional accounting/consulting firms",
             "Evaluate self-serve product for the largest, most standardised use cases",
             "Consider Series A or strategic partnership only after methodology is proven at scale",
             "Target: €400,000–€500,000 annual run rate",
         ]),
    ]

    for phase, timing, title, bg, fg, bullets in phases:
        header = Table([[
            Paragraph(f"<b>{phase}</b>",
                      ParagraphStyle("ph", fontName=FONT_BOLD, fontSize=10,
                                     textColor=fg, alignment=TA_CENTER)),
            Paragraph(f"<b>{title}</b>  <font size=8 color='#888888'>{timing}</font>",
                      ParagraphStyle("pt", fontName=FONT_BOLD, fontSize=10,
                                     textColor=DARK, leading=14)),
        ]], colWidths=[22*mm, W - 30*mm - 22*mm])
        header.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (0,-1), bg),
            ("BACKGROUND",   (1,0), (1,-1), MID),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("TOPPADDING",   (0,0), (-1,-1), 7),
            ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ]))
        elems.append(header)
        for b in bullets:
            elems.append(Paragraph(
                f"    •  {b}",
                ParagraphStyle("rb", fontName=FONT, fontSize=9, leading=14,
                               textColor=DARK, leftIndent=28, spaceAfter=2)))
        elems.append(sp())

    elems.append(PageBreak())
    return elems


def section9(styles):
    elems = section("09", "Financial Projections")

    elems.append(h2("Conservative Revenue Model — Consulting Fees", styles))

    def fp(text, bold=False, color=DARK, align=TA_LEFT, size=9):
        return Paragraph(text, ParagraphStyle("fp", fontName=FONT_BOLD if bold else FONT,
            fontSize=size, textColor=color, leading=size*1.5, alignment=align))

    TW = W - 30*mm
    cw = [TW*0.40, TW*0.20, TW*0.20, TW*0.20]

    proj_rows = [
        ("", "Year 1", "Year 2", "Year 3", False, False),
        ("Consultants",                      "1",           "2",     "5",           False, False),
        ("Engagements / consultant / year",  "20–24",       "24",    "20",          False, False),
        ("Average engagement fee",           "€4,000",      "€5,000","€6,000",      False, False),
        ("Consulting Revenue",               "€80K–€96K",   "€240K", "€600K",       False, False),
        ("Methodology licensing",            "—",           "—",     "€100K–€150K", False, False),
        ("Total Revenue",                    "€80K–€96K",   "€240K", "€500K–€750K", True,  True),
        ("Est. Operating Costs",             "€20K–€30K",   "€60K–€80K","€180K–€220K", False, False),
        ("Est. EBITDA",                      "€50K–€70K",   "€160K", "€320K–€530K", True,  True),
    ]

    proj_data = []
    for i, (label, y1, y2, y3, is_hdr, is_total) in enumerate(proj_rows):
        if i == 0:
            ps = ParagraphStyle("fphdr", fontName=FONT_BOLD, fontSize=9,
                                 textColor=WHITE, leading=13, alignment=TA_CENTER)
            proj_data.append([fp(""), Paragraph("Year 1", ps),
                               Paragraph("Year 2", ps), Paragraph("Year 3", ps)])
        elif is_total:
            gc = HexColor("#1B5E20")
            proj_data.append([fp(label, bold=True, color=gc),
                               fp(y1, bold=True, color=gc, align=TA_CENTER),
                               fp(y2, bold=True, color=gc, align=TA_CENTER),
                               fp(y3, bold=True, color=gc, align=TA_CENTER)])
        else:
            proj_data.append([fp(label, bold=True, color=NAVY),
                               fp(y1, align=TA_CENTER),
                               fp(y2, align=TA_CENTER),
                               fp(y3, align=TA_CENTER)])

    tbl = Table(proj_data, colWidths=cw, repeatRows=1)
    # Find total rows indices
    total_rows = [i for i, r in enumerate(proj_rows) if r[4]]
    style_list = [
        ("BACKGROUND",    (0,0),  (-1,0),  NAVY),
        ("ALIGN",         (1,0),  (-1,-1), "CENTER"),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, LIGHT]),
        ("GRID",          (0,0),  (-1,-1), 0.3, MID),
        ("TOPPADDING",    (0,0),  (-1,-1), 6),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 6),
        ("LEFTPADDING",   (0,0),  (-1,-1), 8),
    ]
    for ri in total_rows:
        style_list += [
            ("BACKGROUND", (0,ri), (-1,ri), HexColor("#E8F5E9")),
            ("LINEABOVE",  (0,ri), (-1,ri), 1.5, GOLD),
        ]
    tbl.setStyle(TableStyle(style_list))
    elems.append(tbl)
    elems.append(sp())

    elems.append(h3("Key Assumptions", styles))
    elems += bullet([
        "Year 1 engagements priced conservatively at €4,000 avg; PNRR-linked deals may exceed this",
        "Operating costs include tool hosting, travel, AI inference, and minimal marketing",
        "No external capital required at any stage through Year 2",
        "Methodology licensing assumes white-label agreements with 2–3 regional consulting firms in Year 3",
        "These are conservative estimates; a single anchor partnership with a PNRR facilitator could double Year 1 revenue",
    ], styles)
    elems.append(sp())

    elems.append(h2("Path to Platform", styles))
    elems.append(body(
        "After 50+ completed engagements, the benchmark database reaches statistical significance "
        "for 2–3 verticals. At this point, a self-serve assessment product becomes viable — clients "
        "pay a subscription fee (€200–€500/month) to run their own assessments using validated benchmarks. "
        "This is the transition from consulting business to software platform, and the point at which "
        "external investment becomes relevant.",
        styles))
    elems.append(PageBreak())
    return elems


def section10(styles):
    elems = section("10", "Why Now — Why This Team")

    reasons = [
        ("The PNRR Window Is Time-Limited",
         "EU digitalisation funding under Romania's PNRR creates a finite window of subsidised demand. "
         "Companies actively seeking to spend grant money on digital transformation represent an "
         "unusually low-friction sales environment. This window will not exist in 3–4 years."),
        ("AI Literacy Gap = First-Mover Advantage",
         "Romanian SMEs are navigating an AI landscape without guides. The first credible, "
         "structured methodology to reach this market will compound — every engagement builds "
         "benchmark data, every satisfied client generates referrals, every vertical mastered "
         "raises the barrier for a late entrant."),
        ("The Tool Becomes the Moat",
         "Unlike a pure services business, this model generates a proprietary data asset: "
         "Romanian SME automation benchmarks. This benchmark database cannot be replicated by "
         "a new entrant starting today — it requires engagements. It is built, not bought."),
        ("No Structural Capital Barrier",
         "This business does not require raising venture capital, hiring a large team, or "
         "building infrastructure before generating revenue. The first €80K–€96K funds "
         "everything needed for Year 2. The model is self-reinforcing from day one."),
    ]

    for title, desc in reasons:
        elems.append(h3(f"▸  {title}", styles))
        elems.append(body(desc, styles))
        elems.append(sp(0.5))

    elems.append(sp())

    # Confidence box
    conf_tbl = Table([[
        Paragraph("OVERALL CONFIDENCE ASSESSMENT", ParagraphStyle(
            "cl", fontName=FONT_BOLD, fontSize=9, textColor=GOLD,
            alignment=TA_CENTER, spaceAfter=4)),
    ], [
        Paragraph("~85% Viable as a Consulting Business Within 12 Months", ParagraphStyle(
            "cv", fontName=FONT_BOLD, fontSize=16, textColor=WHITE,
            alignment=TA_CENTER)),
    ], [
        Paragraph(
            "Primary unknowns: (1) client willingness to pay in Phase 0 validation, "
            "(2) speed of benchmark network seeding. Both are testable within 90 days at negligible cost.",
            ParagraphStyle("cn", fontName=FONT, fontSize=9, textColor=MID,
                           alignment=TA_CENTER, leading=14)),
    ]], colWidths=[W - 30*mm])
    conf_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LINEBEFORE",    (0,0), (0,-1),  4, GOLD),
        ("LINEAFTER",     (0,0), (0,-1),  4, GOLD),
        ("LINEABOVE",     (0,0), (-1,0),  4, GOLD),
        ("LINEBELOW",     (0,-1),(-1,-1), 4, GOLD),
    ]))
    elems.append(conf_tbl)
    elems.append(sp())

    elems.append(h2("Immediate Next Actions — For Partner Discussion", styles))
    next_steps = [
        ("This week", "Agree on beachhead vertical (manufacturing vs professional services) and target geography (Cluj / Bucharest / Timișoara)"),
        ("Month 1", "Identify 5 target SMEs for outreach. Approach via personal network or Chamber of Commerce contacts"),
        ("Month 1–2", "Run first manual engagement at €1,500–€2,000. Deliver report. Measure: Did they pay? Did they see value? What was missing?"),
        ("Month 2–3", "Map the PNRR access path — identify 2–3 active grant facilitators and structure a referral partnership"),
        ("Month 3", "Decision gate: if 2 of 3 manual engagements result in a repeat request, begin tool development"),
    ]
    ns_data = [[Paragraph(f"<b>{t}</b>", ParagraphStyle("nst", fontName=FONT_BOLD,
                                                         fontSize=8.5, textColor=NAVY, leading=13)),
                Paragraph(a, ParagraphStyle("nsa", fontName=FONT, fontSize=9,
                                             textColor=DARK, leading=13))]
               for t, a in next_steps]
    ns_tbl = Table(ns_data, colWidths=[28*mm, W - 30*mm - 28*mm])
    ns_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LIGHT]),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 6),
        ("LEFTPADDING",    (0,0), (-1,-1), 8),
        ("LINEBEFORE",     (0,0), (0,-1),  3, GOLD),
    ]))
    elems.append(ns_tbl)
    return elems


# ── Build Document ────────────────────────────────────────────────────────────

def build():
    output = "/Users/alex/Desktop/AI_Workflow_Intelligence_Pitch.pdf"
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=16*mm,  bottomMargin=16*mm,
        title="AI Workflow Intelligence — Romanian SME Market",
        author="AI Workflow Intelligence",
        subject="Strategic Business Assessment & Investment Opportunity",
    )

    styles = make_styles()
    story  = []

    story += cover_page(styles)
    story += exec_summary(styles)
    story += section1(styles)
    story += section2(styles)
    story += section3(styles)
    story += section4(styles)
    story += section5(styles)
    story += section6(styles)
    story += section7(styles)
    story += section8(styles)
    story += section9(styles)
    story += section10(styles)

    def on_page_wrap(canvas, doc):
        if doc.page == 1:
            on_cover(canvas, doc)
        else:
            on_page(canvas, doc)

    doc.build(story, onFirstPage=on_page_wrap, onLaterPages=on_page_wrap)
    print(f"PDF written to: {output}")

if __name__ == "__main__":
    build()
