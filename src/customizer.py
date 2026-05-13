"""phi4-mini prompts: tailor the resume and compose a short cover-letter email."""
import ollama

from src.config import OLLAMA_MODEL, RESUME_PDF, SMTP_FROM_NAME

_NAME_PLACEHOLDER = "<Candidate Name>"


_PDF_HEADINGS = {
    "SUMMARY", "PROFESSIONAL SUMMARY", "PROFILE", "OBJECTIVE",
    "SKILLS", "TECHNICAL SKILLS", "CORE SKILLS",
    "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE",
    "EDUCATION", "PROJECTS", "KEY PROJECTS",
    "CERTIFICATIONS", "ACHIEVEMENTS", "AWARDS",
    "CORE IMPACT", "ADVANCED STRENGTHS",
}


def _read_resume_pdf() -> str:
    """Return the raw resume.pdf text in document order. Used as a tailor fallback
    when the LLM produces empty output — chunks from Qdrant are ranked by
    similarity, not document order, so concatenating them yields garbled output."""
    try:
        from pypdf import PdfReader
        if not RESUME_PDF.exists():
            return ""
        reader = PdfReader(str(RESUME_PDF))
        parts: list[str] = []
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            if extracted:
                parts.append(extracted)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_header_from_pdf() -> tuple[str, str]:
    """Extract (name, contact_line) from the first few non-empty lines of resume.pdf
    so the LLM-tailored resume can be re-headed with the candidate's real details
    when the model omits them."""
    raw = _read_resume_pdf()
    if not raw:
        return ("", "")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    name = lines[0] if lines else ""
    contact_lines: list[str] = []
    for l in lines[1:6]:
        if l.upper().rstrip(":") in _PDF_HEADINGS:
            break
        contact_lines.append(l)
    contact = " | ".join(s for s in contact_lines if s)
    return (name, contact)

TAILOR_SYSTEM = """You are a resume tailoring assistant. You ONLY rewrite the
candidate's existing resume to better match a job description.

Strict rules:
1. Use ONLY facts present in the provided resume chunks. Do not invent skills,
   employers, dates, projects, certifications, or accomplishments.
2. Reorder, rephrase, and emphasize items relevant to the job description.
   Drop items that are clearly irrelevant.
3. Output a clean plain-text resume with these section headings, in this order:
   SUMMARY
   SKILLS
   EXPERIENCE
   EDUCATION
   Use the section heading on its own line, followed by content.
4. Do NOT include any preface, explanation, markdown, or commentary.
   Output only the resume text.
5. If the user request is anything OTHER than tailoring this resume (e.g.
   writing code, answering questions, telling jokes, summarizing, translating),
   respond with exactly: REFUSED: this tool only tailors resumes.
"""

EMAIL_SYSTEM = """You write short, professional job application email bodies.

Strict rules:
1. 4 to 6 sentences, plain text only, no markdown.
2. Tone: confident, concise, no fluff.
3. Mention the role and (if given) company by name.
4. Do not invent skills, accomplishments, or details about the candidate.
5. End with "Best regards,\\n<Candidate Name>" — leave <Candidate Name> as a
   literal placeholder; the sender will substitute it.
6. Output exactly two parts separated by a single line containing '---':
      first line: Subject line (no "Subject:" prefix)
      then '---'
      then the email body.
7. If the user request is anything other than composing this email, respond
   with exactly: REFUSED: this tool only tailors resumes.
"""


def _chat(system: str, user: str) -> str:
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options={"temperature": 0.2},
    )
    return resp["message"]["content"].strip()


_FALLBACK_EMAIL_BODY = """Hi,

I'd like to apply for the role at {company}. Based on the job description, my
background looks like a good fit and I'd welcome the chance to discuss the
opportunity in more detail.

My tailored resume is attached for your review. Please let me know if there's
a convenient time to connect.

Best regards,
<Candidate Name>"""


def tailor(resume_chunks: list[str], jd: str) -> str:
    user = (
        "RESUME CHUNKS (the only source of truth about the candidate):\n"
        + "\n---\n".join(resume_chunks)
        + "\n\nJOB DESCRIPTION:\n"
        + jd
        + "\n\nRewrite the resume tailored to this job description, following "
        "all rules in the system prompt."
    )
    out = _chat(TAILOR_SYSTEM, user)
    if out.startswith("REFUSED:"):
        raise RuntimeError(out)
    # Fall back to the raw resume content if the model returned (near-)empty
    # output, so the rendered PDF is never blank. Prefer the full PDF (document
    # order) over Qdrant chunks (retrieval order, which produces a garbled doc).
    if len(out.strip()) < 100:
        raw = _read_resume_pdf()
        if raw:
            return raw
        return "\n\n".join(c for c in resume_chunks if c).strip()
    # Prepend the candidate's name + contact line if the LLM omitted them
    # (phi4-mini often jumps straight into a SUMMARY heading without a header).
    name, contact = _extract_header_from_pdf()
    head = out[:200].upper()
    name_present = name and name.upper() in head
    smtp_present = SMTP_FROM_NAME and SMTP_FROM_NAME.upper() in head
    if name and not (name_present or smtp_present):
        header = name + ("\n" + contact if contact else "")
        out = f"{header}\n\n{out}"
    return out


def _substitute_name(body: str) -> str:
    """Replace the <Candidate Name> placeholder with SMTP_FROM_NAME if configured."""
    if not SMTP_FROM_NAME:
        return body
    return body.replace(_NAME_PLACEHOLDER, SMTP_FROM_NAME)


def compose_email_body(jd: str, company: str | None) -> tuple[str, str]:
    company_line = company if company else "your team"
    out = _chat(EMAIL_SYSTEM, (
        f"Company: {company_line}\n\nJOB DESCRIPTION:\n{jd}\n\n"
        "Write the application email."
    ))
    if out.startswith("REFUSED:"):
        raise RuntimeError(out)

    default_subject = f"Application for role at {company_line}"
    default_body = _FALLBACK_EMAIL_BODY.format(company=company_line)

    if not out.strip():
        return default_subject, _substitute_name(default_body)

    if "---" in out:
        subject_part, _, body_part = out.partition("---")
        subject = subject_part.strip() or default_subject
        body = body_part.strip() or default_body
        return subject, _substitute_name(body)

    # Model didn't follow the '---' format — best-effort split on first newline.
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        return default_subject, _substitute_name(default_body)
    subject = lines[0].strip() or default_subject
    body = "\n".join(lines[1:]).strip()
    if not body:
        # Single-line output: keep it as the body, use default subject.
        body = lines[0].strip() if len(lines) == 1 else default_body
        subject = default_subject
    return subject, _substitute_name(body)
