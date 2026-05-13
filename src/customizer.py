"""phi4-mini prompts: tailor the resume and compose a short cover-letter email."""
import ollama

from src.config import OLLAMA_MODEL

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
    return out


def compose_email_body(jd: str, company: str | None) -> tuple[str, str]:
    company_line = company if company else "your team"
    user = (
        f"Company: {company_line}\n\nJOB DESCRIPTION:\n{jd}\n\n"
        "Write the application email."
    )
    out = _chat(EMAIL_SYSTEM, user)
    if out.startswith("REFUSED:"):
        raise RuntimeError(out)
    if "---" not in out:
        # Model didn't follow format — fall back to a safe split.
        lines = out.splitlines()
        subject = lines[0].strip() if lines else f"Application for role at {company_line}"
        body = "\n".join(lines[1:]).strip() or out
        return subject, body
    subject_part, _, body_part = out.partition("---")
    return subject_part.strip(), body_part.strip()
