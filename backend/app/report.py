"""Version-bound PDF report (ReportLab). DRAFT watermark unless an active approval exists for that revision."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .repo import Conflict, NotFound

_FONT = "Helvetica"
_FONT_B = "Helvetica-Bold"
_UNICODE = False


def _setup_fonts() -> None:
    global _FONT, _FONT_B, _UNICODE
    if _UNICODE:
        return
    for reg, bold in (("arial.ttf", "arialbd.ttf"), ("calibri.ttf", "calibrib.ttf")):
        r, b = Path("C:/Windows/Fonts") / reg, Path("C:/Windows/Fonts") / bold
        if r.exists() and b.exists():
            try:
                pdfmetrics.registerFont(TTFont("VerityBody", str(r)))
                pdfmetrics.registerFont(TTFont("VerityBold", str(b)))
                _FONT, _FONT_B, _UNICODE = "VerityBody", "VerityBold", True
                return
            except Exception:
                continue


def _t(v: Any) -> str:
    """Escape for Paragraph; without a Unicode font, degrade symbols that Helvetica cannot draw."""
    s = "" if v is None else str(v)
    if not _UNICODE:
        s = s.replace("\u20b9", "INR ").encode("latin-1", "replace").decode("latin-1")
    return escape(s)


def _money(v: Any) -> str:
    if v in (None, ""):
        return "unresolved"
    try:
        from decimal import Decimal

        d = Decimal(str(v))
        return f"INR {d:,.2f}"
    except Exception:
        return _t(v)


CHIP = {"observed": "OBSERVED", "reported": "REPORTED", "computed": "COMPUTED", "inferred": "INFERRED", "human": "HUMAN"}
CHIP_COL = {"observed": "#1F7F72", "reported": "#4B53C9", "computed": "#2F6EA8", "inferred": "#8A6A1E", "human": "#333333"}


def build_pdf(repo, case_id: str, rev: Optional[int] = None) -> bytes:
    _setup_fonts()
    case = repo.case(case_id)
    rev = rev if rev is not None else case["current_rev"]
    if not rev:
        raise Conflict("no analysed revision yet; nothing to report", code="no_revision")
    row = repo.revision_row(case_id, rev)
    state = repo.get_state(case_id, rev)
    if not row or state is None:
        raise NotFound(f"revision {rev} not found")
    approvals = repo.approvals(case_id)
    active = [a for a in approvals if a["rev"] == rev and a["status"] == "active" and a["decision"] == "approve"]
    approval = active[-1] if active else None
    evidence = {e["id"]: e for e in repo.evidence_list(case_id)}

    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName=_FONT, fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#444444"))
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName=_FONT_B, fontSize=16, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=_FONT_B, fontSize=11.5, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#111111"))
    cell = ParagraphStyle("c", parent=body, fontSize=8, leading=10)
    cellb = ParagraphStyle("cb", parent=cell, fontName=_FONT_B)

    def P(txt, st=body):
        return Paragraph(txt, st)

    def table(data, widths, header=True):
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if header:
            st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")))
        t.setStyle(TableStyle(st))
        return t

    story: list = []
    story.append(P("Verity claims investigation report", h1))
    story.append(P("SYNTHETIC DATA - demonstration only. Nothing here is a real claim, policy or person. The system never denies a claim, "
                   "labels anyone as dishonest, or releases payment: a human decision is required.", small))
    story.append(Spacer(1, 4))
    status_txt = (f"APPROVED by {_t(approval['reviewer'])} ({_t(approval['authority_role'])})" if approval else "DRAFT - no active approval for this revision")
    head = [
        [P("Case", cellb), P(f"{_t(case['case_no'])} - {_t(case['title'])}", cell)],
        [P("Revision", cellb), P(f"{rev} (created {_t(row['created_at'])}; trigger: {_t(row['trigger'])})", cell)],
        [P("Revision hash", cellb), P(f"<font name='Courier' size='7'>{_t(row['hash'])}</font>", cell)],
        [P("Previous hash", cellb), P(f"<font name='Courier' size='7'>{_t(row['prev_hash'])}</font>", cell)],
        [P("Approval", cellb), P(status_txt, cell)],
        [P("Approval hash", cellb), P(f"<font name='Courier' size='7'>{_t(approval['hash']) if approval else 'none'}</font>", cell)],
        [P("Generated", cellb), P(_t(datetime.now(timezone.utc).isoformat(timespec="seconds")), cell)],
    ]
    story.append(table(head, [32 * mm, 138 * mm], header=False))

    story.append(P("Summary", h2))
    story.append(P(_t(state.get("summary") or "(no summary)")))
    if state.get("recommendation"):
        story.append(P(f"<b>Recommendation (neutral, for the human reviewer):</b> {_t(state['recommendation'])}"))
    if state.get("injection_flags"):
        story.append(P("<b>Embedded instructions detected and ignored:</b> " + "; ".join(_t(f.get("text", f)) + f" ({_t(f.get('evidence_id', ''))})" if isinstance(f, dict) else _t(f) for f in state["injection_flags"])))

    story.append(P("Evidence", h2))
    ev_rows = [[P("ID", cellb), P("File", cellb), P("Kind", cellb), P("Source", cellb), P("SHA-256 (first 16)", cellb), P("Status", cellb)]]
    for eid in state.get("evidence_ids") or list(evidence):
        e = evidence.get(eid)
        if e:
            ev_rows.append([P(_t(e["id"]), cell), P(_t(e["filename"]), cell), P(_t(e["kind"]), cell), P(_t(e["source_class"]), cell), P(_t(e["sha256"][:16]), cell), P(_t(e["status"]), cell)])
    story.append(table(ev_rows, [20 * mm, 52 * mm, 20 * mm, 24 * mm, 36 * mm, 18 * mm]))

    story.append(P("Findings", h2))
    findings = state.get("findings") or []
    if not findings:
        story.append(P("No findings recorded in this revision."))
    for f in findings:
        ep = f.get("epistemic", "inferred")
        chip = f"<font color='{CHIP_COL.get(ep, '#333333')}'><b>[{CHIP.get(ep, _t(ep).upper())}]</b></font>"
        stale = f"  <font color='#777777'>[{_t(str(f.get('status')).upper())}{': ' + _t(f.get('stale_reason')) if f.get('stale_reason') else ''}]</font>" if f.get("status") not in (None, "active") else ""
        parts = [P(f"<b>{_t(f.get('id'))}</b> {_t(str(f.get('type', '')).upper())} - {_t(f.get('title'))} {chip}{stale}", body), P(_t(f.get("body")), body)]

        def refs(label, items):
            for r in items or []:
                bits = [f"{_t(r.get('evidence_id'))}"]
                if r.get("page"):
                    bits.append(f"p.{_t(r['page'])}")
                if r.get("zone"):
                    bits.append(f"zone {_t(r['zone'])}")
                q = f" \"{_t(r['quote'])}\"" if r.get("quote") else ""
                parts.append(P(f"{label}: {' '.join(bits)}{q} [receipt: {_t(r.get('receipt', 'n/a'))}]", small))

        refs("Supports", f.get("supports"))
        refs("Contradicts", f.get("contradicts"))
        if f.get("alternatives"):
            parts.append(P("Alternatives: " + "; ".join(_t(a) for a in f["alternatives"]), small))
        if f.get("uncertainty"):
            parts.append(P(f"Uncertainty: {_t(f['uncertainty'])}", small))
        if f.get("action"):
            parts.append(P(f"Suggested action: {_t(f['action'])}", small))
        parts.append(Spacer(1, 4))
        story.append(KeepTogether(parts))

    story.append(P("Hypotheses (ordinal ranking by fewest inconsistencies; no probabilities)", h2))
    hy = state.get("hypotheses") or []
    if hy:
        rows = [[P("ID", cellb), P("Hypothesis", cellb), P("Type", cellb), P("Inconsistencies", cellb), P("Rank", cellb)]]
        for h in hy:
            rows.append([P(_t(h.get("id")), cell), P(_t(h.get("text")), cell), P(_t(h.get("kind", "") + (" / benign" if h.get("benign") else "")), cell),
                         P(_t(h.get("inconsistencies")), cell), P(_t(h.get("rank")), cell)])
        story.append(table(rows, [14 * mm, 92 * mm, 32 * mm, 22 * mm, 10 * mm]))
    else:
        story.append(P("No hypotheses recorded."))

    story.append(P("Settlement calculation", h2))
    calc = state.get("calc")
    if calc and (calc.get("lines") or calc.get("quoted_total")):
        rows = [[P("Step", cellb), P("Amount", cellb), P("Basis", cellb), P("Flag", cellb)]]
        for ln in calc.get("lines") or []:
            rows.append([P(_t(ln.get("label")), cell), P(_money(ln.get("amount")), cell), P(_t(ln.get("basis")), cell), P(_t(ln.get("flag") or ""), cell)])
        story.append(table(rows, [60 * mm, 30 * mm, 60 * mm, 20 * mm]))
        story.append(P(f"Quoted total: {_money(calc.get('quoted_total'))} | Recomputed total: {_money(calc.get('recomputed_total'))} | "
                       f"<b>Proposed settlement: {_money(calc.get('proposed_settlement'))}</b>", body))
    else:
        story.append(P("No settlement could be computed from the evidence provided."))
    unresolved = (calc or {}).get("unresolved") or []
    if unresolved or state.get("unresolved"):
        story.append(P("<b>Unresolved (the settlement is not final until these are answered):</b>", body))
        for u in unresolved:
            story.append(P(f"- {_t(u.get('term'))}: {_t(u.get('why'))} Needs: {_t(u.get('needs'))}", small))
        for u in state.get("unresolved") or []:
            story.append(P(f"- {_t(u)}", small))
    for c in (calc or {}).get("conditional") or []:
        story.append(P(f"Under {_t(c.get('hypothesis_id'))}: {_money(c.get('settlement'))} {_t(c.get('note'))}", small))

    story.append(P("Evidence requests", h2))
    reqs = state.get("requests") or []
    if reqs:
        rows = [[P("ID", cellb), P("Request", cellb), P("Separates", cellb), P("INR at stake", cellb), P("Status", cellb)]]
        for r in reqs:
            pred = r.get("prediction") or {}
            txt = _t(r.get("text")) + (f"<br/><font size='7'>If supports: {_t(pred.get('if_supports'))} | If contradicts: {_t(pred.get('if_contradicts'))}</font>" if pred else "")
            rows.append([P(_t(r.get("id")), cell), P(txt, cell), P(_t(r.get("pairs_separated", 0)), cell), P(_money(r.get("rupees_at_stake")) if r.get("rupees_at_stake") else "n/a", cell),
                         P(_t(r.get("status")) + (f" / {_t(r.get('outcome'))}" if r.get("outcome") not in (None, "pending") else ""), cell)])
        story.append(table(rows, [14 * mm, 90 * mm, 20 * mm, 26 * mm, 20 * mm]))
    else:
        story.append(P("No open evidence requests."))

    story.append(P("Reviewer decisions", h2))
    mine = [a for a in approvals if a["rev"] == rev]
    if mine:
        rows = [[P("Decision", cellb), P("Reviewer (typed label, not authentication)", cellb), P("Authority", cellb), P("Status", cellb), P("Note", cellb)]]
        for a in mine:
            rows.append([P(_t(a["decision"]), cell), P(_t(a["reviewer"]), cell), P(_t(a["authority_role"]), cell),
                         P(_t(a["status"]) + (f"<br/>{_t(a['void_reason'])}" if a.get("void_reason") else ""), cell), P(_t(a["note"]), cell)])
        story.append(table(rows, [24 * mm, 40 * mm, 26 * mm, 40 * mm, 40 * mm]))
    else:
        story.append(P("No reviewer decision has been recorded for this revision."))
    story.append(Spacer(1, 6))
    story.append(P(f"Reviewer signature: ______________________   Date: ____________   (document bound to revision {rev}, hash {_t(row['hash'][:16])}...)", small))

    draft = approval is None
    label = f"{case['case_no']} | rev {rev} | {row['hash'][:12]}"

    def decorate(canvas, doc):
        canvas.saveState()
        if draft:
            canvas.setFont(_FONT_B, 90)
            canvas.setFillColor(colors.Color(0.5, 0.5, 0.5, alpha=0.13))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "DRAFT")
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont(_FONT, 7)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(15 * mm, 8 * mm, f"Verity | {label} | SYNTHETIC DATA")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Verity report {case['case_no']} rev {rev}", author="Verity (synthetic demo)")
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()
