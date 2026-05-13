"""Background tailoring jobs with on-disk persistence under out/jobs/."""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src import customizer, email_extractor, guardrail, pdf_writer, rag
from src.config import OUT_DIR

JOBS_DIR = OUT_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

STEPS = [
    ("validate", "Validating job description"),
    ("extract", "Extracting recipient & company"),
    ("retrieve", "Retrieving resume chunks"),
    ("tailor", "Tailoring resume with phi4-mini"),
    ("email", "Composing application email"),
    ("render", "Rendering PDF"),
]


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class Job:
    id: str
    jd: str
    status: str = "pending"  # pending | running | done | error | rejected | sent
    step: int = 0  # index into STEPS that is currently active
    step_label: str = ""
    error: str = ""
    recipient: str = ""
    company: str = ""
    resume_text: str = ""
    email_subject: str = ""
    email_body: str = ""
    pdf_path: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    sent_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _job_dir(job_id: str) -> Path:
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(job: Job) -> None:
    job.updated_at = _now_iso()
    with _lock:
        _jobs[job.id] = job
    path = _job_dir(job.id) / "meta.json"
    path.write_text(json.dumps(job.to_dict(), indent=2))


def get(job_id: str) -> Job | None:
    with _lock:
        if job_id in _jobs:
            return _jobs[job_id]
    meta = JOBS_DIR / job_id / "meta.json"
    if meta.exists():
        job = Job.from_dict(json.loads(meta.read_text()))
        with _lock:
            _jobs[job.id] = job
        return job
    return None


def list_all() -> list[Job]:
    """List jobs from disk, newest first."""
    jobs: list[Job] = []
    for sub in JOBS_DIR.iterdir():
        if not sub.is_dir():
            continue
        meta = sub / "meta.json"
        if not meta.exists():
            continue
        try:
            jobs.append(Job.from_dict(json.loads(meta.read_text())))
        except Exception:
            continue
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


def delete(job_id: str) -> bool:
    d = JOBS_DIR / job_id
    if not d.exists():
        return False
    for p in d.iterdir():
        p.unlink()
    d.rmdir()
    with _lock:
        _jobs.pop(job_id, None)
    return True


def _run(job_id: str) -> None:
    job = get(job_id)
    if job is None:
        return
    job.status = "running"
    job.step = 0
    job.step_label = STEPS[0][1]
    _save(job)

    try:
        guardrail.assert_job_description(job.jd)
    except guardrail.NotAJobDescription as e:
        job.status = "rejected"
        job.error = str(e)
        _save(job)
        return

    job.step = 1
    job.step_label = STEPS[1][1]
    _save(job)
    try:
        recipient, company = email_extractor.extract_recipient(job.jd)
    except email_extractor.NoRecipientFound as e:
        job.status = "error"
        job.error = str(e)
        _save(job)
        return
    job.recipient = recipient
    job.company = company or ""

    job.step = 2
    job.step_label = STEPS[2][1]
    _save(job)
    chunks = rag.retrieve(job.jd, k=8)
    if not chunks:
        job.status = "error"
        job.error = "No resume chunks returned. Run `python -m src.ingest` first."
        _save(job)
        return

    job.step = 3
    job.step_label = STEPS[3][1]
    _save(job)
    try:
        job.resume_text = customizer.tailor(chunks, job.jd)
    except Exception as e:
        job.status = "error"
        job.error = f"Tailoring failed: {e}"
        _save(job)
        return

    job.step = 4
    job.step_label = STEPS[4][1]
    _save(job)
    try:
        subject, body = customizer.compose_email_body(job.jd, job.company or None)
    except Exception as e:
        job.status = "error"
        job.error = f"Email compose failed: {e}"
        _save(job)
        return
    job.email_subject = subject
    job.email_body = body

    job.step = 5
    job.step_label = STEPS[5][1]
    _save(job)
    pdf_default = pdf_writer.render(job.resume_text, job.company or None)
    # Move/copy PDF into the job's own directory so each job keeps its own copy.
    target = _job_dir(job.id) / "resume.pdf"
    target.write_bytes(Path(pdf_default).read_bytes())
    job.pdf_path = str(target)

    job.status = "done"
    job.step = len(STEPS)
    job.step_label = "Complete"
    _save(job)


def submit(jd: str) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], jd=jd)
    _save(job)

    def _worker() -> None:
        try:
            _run(job.id)
        except Exception as e:
            j = get(job.id) or job
            j.status = "error"
            j.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            _save(j)

    threading.Thread(target=_worker, daemon=True).start()
    return job


def mark_sent(job_id: str, info: dict[str, Any]) -> Job | None:
    job = get(job_id)
    if job is None:
        return None
    job.status = "sent"
    job.sent_at = _now_iso()
    job.error = ""
    _save(job)
    return job


def update_email(job_id: str, subject: str | None, body: str | None,
                 recipient: str | None) -> Job | None:
    job = get(job_id)
    if job is None:
        return None
    if subject is not None:
        job.email_subject = subject
    if body is not None:
        job.email_body = body
    if recipient is not None:
        job.recipient = recipient
    _save(job)
    return job


def rerender(job_id: str, resume_text: str | None = None, ats: bool = False) -> Job | None:
    """Re-render the PDF (with optional updated resume text and/or ATS mode)."""
    job = get(job_id)
    if job is None:
        return None
    if resume_text is not None:
        job.resume_text = resume_text
    pdf_default = pdf_writer.render(job.resume_text, job.company or None, ats=ats)
    target = _job_dir(job.id) / "resume.pdf"
    target.write_bytes(Path(pdf_default).read_bytes())
    job.pdf_path = str(target)
    _save(job)
    return job


SKILLS_HEADER_RE = re.compile(r"^\s*skills\s*:?\s*$", re.IGNORECASE)
ANY_HEADER_RE = re.compile(
    r"^\s*(summary|skills|experience|education|projects|certifications)\s*:?\s*$",
    re.IGNORECASE,
)


def parse_skills(resume_text: str) -> list[str]:
    """Best-effort: pull every line of the SKILLS section, split by , / ; / bullets."""
    if not resume_text:
        return []
    lines = resume_text.splitlines()
    in_skills = False
    block: list[str] = []
    for line in lines:
        if SKILLS_HEADER_RE.match(line):
            in_skills = True
            continue
        if in_skills and ANY_HEADER_RE.match(line) and not SKILLS_HEADER_RE.match(line):
            break
        if in_skills:
            block.append(line)
    raw = "\n".join(block)
    # Strip leading bullets, then split on commas / semicolons / pipes / newlines.
    items: list[str] = []
    for piece in re.split(r"[\n,;|/]+", raw):
        s = re.sub(r"^[\s\-\*•·]+", "", piece).strip()
        if s and not ANY_HEADER_RE.match(s):
            items.append(s)
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def set_skills(job_id: str, skills: list[str]) -> Job | None:
    """Replace the SKILLS section in resume_text with the given list."""
    job = get(job_id)
    if job is None:
        return None
    text = job.resume_text or ""
    lines = text.splitlines()
    new_lines: list[str] = []
    i = 0
    inserted = False
    while i < len(lines):
        line = lines[i]
        if SKILLS_HEADER_RE.match(line):
            new_lines.append("SKILLS")
            for s in skills:
                new_lines.append(f"- {s}")
            inserted = True
            # Skip until next section header
            i += 1
            while i < len(lines) and not ANY_HEADER_RE.match(lines[i]):
                i += 1
            continue
        new_lines.append(line)
        i += 1
    if not inserted:
        # No existing SKILLS section — append one at the end.
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("SKILLS")
        for s in skills:
            new_lines.append(f"- {s}")
    job.resume_text = "\n".join(new_lines)
    _save(job)
    return job


def total_steps() -> int:
    return len(STEPS)
