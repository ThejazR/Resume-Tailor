"""Pull recipient email and (best-effort) company name from a job description."""
import re

import ollama

from src.config import OLLAMA_MODEL


class NoRecipientFound(Exception):
    """Raised when no usable contact email is found in the JD."""


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

NOREPLY_PATTERNS = ("noreply", "no-reply", "donotreply", "do-not-reply")

COMPANY_SYSTEM = (
    "You extract the hiring company name from a job description. "
    "Reply with ONLY the company name on a single line, no punctuation, "
    "no explanation. If the company name is not clearly stated, reply UNKNOWN."
)


def pick_email(text: str) -> str:
    found = EMAIL_RE.findall(text)
    if not found:
        raise NoRecipientFound("No email address found in job description.")
    for addr in found:
        if not any(p in addr.lower() for p in NOREPLY_PATTERNS):
            return addr
    raise NoRecipientFound(
        "Only no-reply addresses found; cannot send application there."
    )


def guess_company(text: str) -> str | None:
    snippet = text[:2000]
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": COMPANY_SYSTEM},
            {"role": "user", "content": snippet},
        ],
        options={"temperature": 0.0},
    )
    name = resp["message"]["content"].strip().splitlines()[0].strip()
    if not name or name.upper() == "UNKNOWN" or len(name) > 80:
        return None
    return name


def extract_recipient(jd: str) -> tuple[str, str | None]:
    email = pick_email(jd)
    company = guess_company(jd)
    return email, company
