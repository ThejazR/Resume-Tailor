"""Render tailored resume text to a clean PDF via reportlab.

Two modes:
- Default: lightly styled (bold headings, slight color), still very ATS-safe.
- ATS strict (`ats=True`): single-column plain text, Helvetica only, no color,
  bullet points normalized to "- ", section headers in plain uppercase.
  This is the format ATS parsers (Workday, Greenhouse, Lever) like best.
"""
import re
import unicodedata
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.config import OUT_DIR

KNOWN_HEADINGS = {"SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION", "PROJECTS", "CERTIFICATIONS"}

OUTPUT_FILENAME = "resume.pdf"


def _styles(ats: bool = False):
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=11 if ats else 10.5,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=4,
        textColor="#000000" if ats else "#222222",
    )
    heading = ParagraphStyle(
        "Heading",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12 if ats else 13,
        leading=16,
        spaceBefore=12 if ats else 10,
        spaceAfter=6 if ats else 4,
        textColor="#000000" if ats else "#222222",
    )
    return body, heading


def _is_heading(line: str) -> bool:
    stripped = line.strip().rstrip(":").upper()
    return stripped in KNOWN_HEADINGS


def _output_path() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / OUTPUT_FILENAME


def _ats_sanitize(text: str) -> str:
    """Strip characters that confuse ATS parsers: smart quotes, emoji, fancy
    bullets, non-breaking spaces. Normalize bullet markers to "- ".
    """
    text = unicodedata.normalize("NFKC", text)
    # Replace fancy bullets and quotes with ASCII equivalents.
    replacements = {
        "•": "-",  # •
        "●": "-",  # ●
        "◦": "-",
        "∘": "-",
        "‣": "-",
        "⁃": "-",
        " ": " ",  # nbsp
        "–": "-",  # en dash
        "—": "-",  # em dash
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Drop non-printable / emoji characters outside basic Latin + extended Latin.
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in ("\n", "\t") or (cat[0] in {"L", "N", "P", "S", "Z"} and ord(ch) < 0x2000):
            cleaned.append(ch)
        elif ord(ch) < 0x80:
            cleaned.append(ch)
        # else drop
    text = "".join(cleaned)
    # Normalize bullets at start of lines: "* foo", "- foo", "• foo" → "- foo".
    out_lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(\s*)([\*\-•])\s+(.*)$", line)
        if m:
            line = f"{m.group(1)}- {m.group(3)}"
        out_lines.append(line)
    # Collapse 3+ blank lines.
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def render(text: str, company: str | None = None, ats: bool = False) -> Path:
    if ats:
        text = _ats_sanitize(text)
    out_path = _output_path()
    body_style, heading_style = _styles(ats=ats)
    margin = (0.6 if ats else 0.75) * inch
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="Resume",
    )

    flowables: list = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            flowables.append(Spacer(1, 6))
            continue
        if _is_heading(line):
            flowables.append(Paragraph(line.strip().rstrip(":").upper(), heading_style))
        else:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            flowables.append(Paragraph(safe, body_style))

    doc.build(flowables)
    return out_path
