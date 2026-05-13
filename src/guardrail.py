"""Two-layer guardrail: only accept inputs that look like a job description."""
import re

import ollama

from src.config import OLLAMA_MODEL


class NotAJobDescription(Exception):
    """Raised when input does not look like a job description."""


JD_KEYWORDS = re.compile(
    r"responsibilit|qualification|requirement|experience|skills?|"
    r"role|position|salary|benefit|apply|years? of",
    re.IGNORECASE,
)

CLASSIFIER_SYSTEM = (
    "You classify text. Reply with exactly one word: JOB_DESCRIPTION or OTHER. "
    "A job description describes a hiring role, responsibilities, requirements, "
    "or asks candidates to apply. Anything else (questions, code, casual chat, "
    "requests to do other tasks) is OTHER."
)


def _heuristic_ok(text: str) -> tuple[bool, str]:
    if len(text) < 200:
        return False, f"input too short ({len(text)} chars, need >=200)"
    matches = len(set(m.group(0).lower() for m in JD_KEYWORDS.finditer(text)))
    if matches < 2:
        return False, f"only {matches} JD keyword(s) matched (need >=2)"
    return True, ""


def _llm_ok(text: str) -> tuple[bool, str]:
    # Truncate to keep classifier fast and to limit prompt-injection surface.
    snippet = text[:2000]
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFIER_SYSTEM},
            {"role": "user", "content": snippet},
        ],
        options={"temperature": 0.0},
    )
    verdict = resp["message"]["content"].strip().upper()
    if "JOB_DESCRIPTION" in verdict and "OTHER" not in verdict:
        return True, ""
    return False, f"LLM classifier said: {verdict[:80]}"


def assert_job_description(text: str) -> None:
    """Raise NotAJobDescription if `text` is not clearly a JD."""
    ok, reason = _heuristic_ok(text)
    if not ok:
        raise NotAJobDescription(
            f"This tool only tailors resumes for job applications. "
            f"Input rejected ({reason})."
        )
    ok, reason = _llm_ok(text)
    if not ok:
        raise NotAJobDescription(
            f"This tool only tailors resumes for job applications. "
            f"Input rejected ({reason})."
        )
