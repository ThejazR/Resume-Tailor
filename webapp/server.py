"""FastAPI server for the Resume Tailor web UI.

Run: python -m webapp.server
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src import mcp_client
from src.config import PROJECT_ROOT, RESUME_PDF
from webapp import jobs

WEBAPP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEBAPP_DIR / "templates"))

app = FastAPI(title="Resume Tailor", version="1.0")
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")


class SubmitBody(BaseModel):
    jd: str


class SendBody(BaseModel):
    subject: str | None = None
    body: str | None = None
    recipient: str | None = None


class RenderBody(BaseModel):
    resume_text: str | None = None
    ats: bool = False


class SkillsBody(BaseModel):
    skills: list[str]
    ats: bool = False


def _job_payload(job: jobs.Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "step": job.step,
        "total_steps": jobs.total_steps(),
        "step_label": job.step_label,
        "error": job.error,
        "recipient": job.recipient,
        "company": job.company,
        "email_subject": job.email_subject,
        "email_body": job.email_body,
        "resume_text": job.resume_text,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "sent_at": job.sent_at,
        "has_pdf": bool(job.pdf_path and Path(job.pdf_path).exists()),
    }


# --- Pages -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return TEMPLATES.TemplateResponse(request, "dashboard.html", {"page": "dashboard"})


@app.get("/tailor", response_class=HTMLResponse)
async def page_tailor(request: Request):
    return TEMPLATES.TemplateResponse(request, "tailor.html", {"page": "tailor"})


@app.get("/progress/{job_id}", response_class=HTMLResponse)
async def page_progress(request: Request, job_id: str):
    if jobs.get(job_id) is None:
        raise HTTPException(404, detail="Job not found")
    return TEMPLATES.TemplateResponse(
        request, "progress.html", {"job_id": job_id, "page": "tailor"}
    )


@app.get("/preview/{job_id}", response_class=HTMLResponse)
async def page_preview(request: Request, job_id: str):
    if jobs.get(job_id) is None:
        raise HTTPException(404, detail="Job not found")
    return TEMPLATES.TemplateResponse(
        request, "preview.html", {"job_id": job_id, "page": "preview"}
    )


@app.get("/review/{job_id}", response_class=HTMLResponse)
async def page_review(request: Request, job_id: str):
    if jobs.get(job_id) is None:
        raise HTTPException(404, detail="Job not found")
    return TEMPLATES.TemplateResponse(
        request, "review.html", {"job_id": job_id, "page": "tailor"}
    )


@app.get("/history", response_class=HTMLResponse)
async def page_history(request: Request):
    return TEMPLATES.TemplateResponse(request, "history.html", {"page": "history"})


# --- API -------------------------------------------------------------------

@app.post("/api/jobs")
async def api_create_job(payload: SubmitBody):
    jd = (payload.jd or "").strip()
    if not jd:
        raise HTTPException(400, detail="jd is required")
    job = jobs.submit(jd)
    return _job_payload(job)


@app.get("/api/jobs")
async def api_list_jobs():
    return {"jobs": [_job_payload(j) for j in jobs.list_all()]}


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return _job_payload(job)


@app.delete("/api/jobs/{job_id}")
async def api_delete_job(job_id: str):
    if not jobs.delete(job_id):
        raise HTTPException(404, detail="Job not found")
    return {"deleted": job_id}


@app.patch("/api/jobs/{job_id}")
async def api_update_job(job_id: str, payload: SendBody):
    job = jobs.update_email(job_id, payload.subject, payload.body, payload.recipient)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return _job_payload(job)


@app.get("/api/jobs/{job_id}/pdf")
async def api_job_pdf(job_id: str):
    job = jobs.get(job_id)
    if job is None or not job.pdf_path or not Path(job.pdf_path).exists():
        raise HTTPException(404, detail="PDF not found")
    return FileResponse(
        job.pdf_path,
        media_type="application/pdf",
        filename=f"resume_{job.company or 'tailored'}.pdf".replace(" ", "_"),
    )


@app.get("/api/jobs/{job_id}/skills")
async def api_get_skills(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return {"skills": jobs.parse_skills(job.resume_text or "")}


@app.put("/api/jobs/{job_id}/skills")
async def api_set_skills(job_id: str, payload: SkillsBody):
    job = jobs.set_skills(job_id, [s for s in payload.skills if s and s.strip()])
    if job is None:
        raise HTTPException(404, detail="Job not found")
    job = jobs.rerender(job_id, ats=payload.ats)
    return {"skills": jobs.parse_skills(job.resume_text), "job": _job_payload(job)}


@app.post("/api/jobs/{job_id}/render")
async def api_render(job_id: str, payload: RenderBody):
    job = jobs.rerender(job_id, payload.resume_text, ats=payload.ats)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    return _job_payload(job)


@app.post("/api/jobs/{job_id}/send")
def api_send(job_id: str, payload: SendBody):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")
    if job.status not in {"done", "sent"}:
        raise HTTPException(400, detail=f"Job is not ready to send (status={job.status})")
    # Apply any last-minute edits.
    job = jobs.update_email(job_id, payload.subject, payload.body, payload.recipient) or job
    if not job.recipient or not job.email_subject or not job.email_body or not job.pdf_path:
        raise HTTPException(400, detail="Missing recipient / subject / body / pdf")
    try:
        result = mcp_client.send_via_mcp(
            job.recipient, job.email_subject, job.email_body, job.pdf_path
        )
    except Exception as e:
        raise HTTPException(500, detail=f"send_email failed: {e}") from e
    jobs.mark_sent(job_id, result)
    return {"sent": True, "result": result, "job": _job_payload(jobs.get(job_id))}


@app.post("/api/resume/upload")
async def api_upload_resume(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="Only .pdf is accepted")
    target = RESUME_PDF
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"uploaded": True, "path": str(target), "size": target.stat().st_size}


@app.post("/api/ingest")
async def api_ingest():
    """Run the ingest script to (re)index resume.pdf into Qdrant."""
    from src import ingest
    try:
        ingest.main()
    except SystemExit as e:
        raise HTTPException(400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(500, detail=f"ingest failed: {e}") from e
    return {"ingested": True}


@app.get("/api/health")
async def api_health():
    out: dict[str, Any] = {"ok": True}
    try:
        from qdrant_client import QdrantClient

        from src.config import COLLECTION_NAME, QDRANT_HOST, QDRANT_PORT
        c = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=2)
        out["qdrant"] = c.collection_exists(COLLECTION_NAME)
    except Exception as e:
        out["ok"] = False
        out["qdrant_error"] = str(e)
    try:
        import ollama

        from src.config import OLLAMA_MODEL
        models = [m["model"] for m in ollama.list().get("models", [])]
        out["ollama_models"] = models
        out["ollama_model_ready"] = any(OLLAMA_MODEL in m for m in models)
        if not out["ollama_model_ready"]:
            out["ok"] = False
    except Exception as e:
        out["ok"] = False
        out["ollama_error"] = str(e)
    out["resume_pdf_exists"] = RESUME_PDF.exists()
    return JSONResponse(out)


def main() -> None:
    import uvicorn
    uvicorn.run("webapp.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
