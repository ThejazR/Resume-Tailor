"""Two-layer guardrail: only accept inputs that look like a job description."""
import re

import ollama

from src.config import OLLAMA_MODEL

# Cap the classifier call so a hung/loading Ollama can't block the pipeline forever.
# When the call times out we fall back to the heuristic (which has already passed).
_LLM_TIMEOUT_S = 20
_llm_client = ollama.Client(timeout=_LLM_TIMEOUT_S)


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
    try:
        resp = _llm_client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM},
                {"role": "user", "content": snippet},
            ],
            options={"temperature": 0.0, "num_predict": 16},
        )
    except Exception:
        # If the LLM is unavailable or slow (timeout), trust the heuristic.
        return True, ""
    verdict = resp["message"]["content"].strip().upper()
    # Only reject when the LLM clearly classifies as OTHER. Small models (phi4-mini)
    # frequently produce off-topic / garbage output for classification prompts;
    # treat anything that isn't an explicit OTHER as a pass since the heuristic
    # has already filtered the obvious non-JD inputs.
    if "OTHER" in verdict and "JOB_DESCRIPTION" not in verdict:
        return False, f"LLM classifier said: {verdict[:80]}"
    return True, ""


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
