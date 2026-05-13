# Resume Tailor — Web UI + CLI

Tailor your resume to any job description, render a clean PDF, and email it to the
hiring contact via an MCP server.

- **Local-only LLM:** [`phi4-mini`](https://ollama.com/library/phi4-mini) through Ollama — no data leaves your laptop.
- **RAG over your resume:** Qdrant + sentence-transformers, so the tailor only uses real facts from your `resume.pdf`.
- **Guardrails:** two-layer JD validation (keyword heuristic + LLM classifier). Off-task or prompt-injected inputs are refused.
- **MCP email:** a stdio MCP server exposes exactly one tool (`send_email`).
- **Two front-doors:** a polished web UI (FastAPI + Tailwind) and the original CLI.

---

## Prerequisites

| Need              | Why                              |
| ----------------- | -------------------------------- |
| Python 3.11+      | Backend + ingest                 |
| Docker            | Runs the Qdrant vector DB        |
| Ollama            | Hosts `phi4-mini` locally        |
| Outlook account   | SMTP send via the MCP server     |
| Modern browser    | Chrome/Safari/Firefox, any recent |

---

## Step-by-step setup

### 1. Clone & enter the project
```bash
cd resume-tailor
```

### 2. Start Qdrant (vector DB)
```bash
docker compose up -d
# Verify:
curl -s http://localhost:6333/collections   # should return JSON
```

### 3. Install Ollama + pull the model
```bash
# macOS:
brew install ollama
ollama serve &           # leave this running
ollama pull phi4-mini
```

### 4. Create the Python virtualenv & install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs:
- Pipeline: `qdrant-client`, `sentence-transformers`, `pypdf`, `ollama`, `reportlab`, `mcp`
- Web UI: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`

### 5. Configure SMTP
```bash
cp .env.example .env
# Edit .env and set:
#   SMTP_USER=your.email@outlook.com
#   SMTP_APP_PASSWORD=<app password from account.live.com → Security → App passwords>
#   SMTP_FROM_NAME=Your Name        (optional)
```

### 6. Drop your resume into the project root
Replace [resume.pdf](resume.pdf) with your own — same filename.

### 7. Index your resume into Qdrant
```bash
python -m src.ingest
# Output: "Stored N chunks in Qdrant."
```

You only need to re-run this when you replace `resume.pdf`. The web UI also
exposes a one-click **Re-index** button on the Tailor page.

---

## Running the web UI

```bash
source .venv/bin/activate
python -m webapp.server
# Server starts at http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> in your browser.

### What you'll see

| Page                         | Path                | Purpose                                                                  |
| ---------------------------- | ------------------- | ------------------------------------------------------------------------ |
| **Dashboard**                | `/`                 | Welcome hero, stats (total tailored, drafts, service health), Recent Activity table. |
| **Tailor**                   | `/tailor`           | Paste JD or load `sample_jd.txt`. Upload a new `resume.pdf` and trigger re-index. |
| **Tailoring Progress**       | `/progress/<id>`    | Animated 6-step pipeline view: validate → extract → retrieve → tailor → email → render. |
| **Resume Preview**           | `/preview/<id>`     | Full split-screen: tailored resume on the left, AI insights (match score, recipient, status) on the right. |
| **Final Review**             | `/review/<id>`      | Edit the outreach email (To / Subject / Body), see the document preview thumbnail, click **Send Application**. |
| **History**                  | `/history`          | All past jobs with PDF download, preview, review, and delete actions.    |

A health pill in the top right turns green when Qdrant, Ollama, and `resume.pdf` are all ready.

### Typical web flow

1. Visit the **Dashboard** → click **Tailor New Resume**.
2. On the **Tailor** page, paste a JD (or click *Load sample_jd.txt*) → **Tailor Resume**.
3. The **Progress** page polls the backend every second. Each step lights up as the pipeline advances; if the JD is rejected by the guardrail, you'll see the rejection message inline.
4. When the run completes, you're redirected to **Final Review**. Edit anything, then click **Send Application** to push it through the MCP email server.
5. After sending (or at any time), open **History** to download the PDF or revisit any previous run.

### Web API (for power users / scripting)

| Method | Path                          | Body                                                | Description                          |
| ------ | ----------------------------- | --------------------------------------------------- | ------------------------------------ |
| `GET`  | `/api/health`                 | —                                                   | Status of Qdrant, Ollama, resume.pdf |
| `GET`  | `/api/jobs`                   | —                                                   | List all jobs                        |
| `POST` | `/api/jobs`                   | `{"jd": "<text>"}`                                  | Submit a new tailoring job           |
| `GET`  | `/api/jobs/{id}`              | —                                                   | Poll job status                      |
| `PATCH`| `/api/jobs/{id}`              | `{"subject":..., "body":..., "recipient":...}`      | Edit the draft email                 |
| `POST` | `/api/jobs/{id}/send`         | (optional patch body)                               | Send via MCP                         |
| `GET`  | `/api/jobs/{id}/pdf`          | —                                                   | Download the tailored PDF            |
| `DELETE`| `/api/jobs/{id}`             | —                                                   | Delete the job and its PDF           |
| `POST` | `/api/resume/upload`          | multipart `file=<resume.pdf>`                       | Replace `resume.pdf`                 |
| `POST` | `/api/ingest`                 | —                                                   | Re-index resume into Qdrant          |

---

## Running the CLI (still supported)

```bash
# From a file
python -m src.main --jd path/to/jd.txt

# From stdin
cat jd.txt | python -m src.main --jd-stdin

# Interactive paste mode
python -m src.main

# Skip the confirm-before-send prompt
python -m src.main --jd jd.txt --yes
```

---

## Project layout

```
resume-tailor/
├── docker-compose.yml      # Qdrant
├── resume.pdf              # Your source resume (replace me)
├── requirements.txt
├── sample_jd.txt           # Example JD for testing
├── src/                    # Core pipeline
│   ├── config.py           # env-loaded settings
│   ├── ingest.py           # PDF → chunks → Qdrant
│   ├── rag.py              # Qdrant retrieval
│   ├── guardrail.py        # JD validation (heuristic + LLM)
│   ├── email_extractor.py  # recipient + company from JD
│   ├── customizer.py       # phi4-mini prompts (tailor + compose email)
│   ├── pdf_writer.py       # reportlab PDF rendering
│   ├── mcp_client.py       # stdio MCP client
│   └── main.py             # CLI orchestrator
├── mcp_server/
│   └── email_server.py     # FastMCP stdio server, single send_email tool
├── webapp/                 # FastAPI web UI (NEW)
│   ├── server.py           # Routes + page handlers
│   ├── jobs.py             # Background tailoring + on-disk persistence
│   ├── templates/          # Jinja2 templates
│   │   ├── _base.html
│   │   ├── dashboard.html
│   │   ├── tailor.html
│   │   ├── progress.html
│   │   ├── preview.html
│   │   ├── review.html
│   │   └── history.html
│   └── static/
│       ├── css/app.css
│       └── js/{api,app,tailwind-config}.js
└── out/
    ├── resume.pdf          # latest rendered PDF
    └── jobs/<id>/          # per-job meta.json + resume.pdf
```

---

## Design system

The UI follows the **Modern Professional Minimalist** spec (Inter font, deep
blue + slate primaries, success-green accents). All design tokens are mirrored
in [webapp/static/js/tailwind-config.js](webapp/static/js/tailwind-config.js).

---

## Troubleshooting

| Symptom                                            | Fix                                                                                       |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Health pill shows "Missing: Qdrant"                | `docker compose up -d` and wait a few seconds.                                            |
| Health pill shows "Missing: Ollama model"          | `ollama serve` then `ollama pull phi4-mini`.                                              |
| Health pill shows "Missing: resume.pdf"            | Place a PDF named `resume.pdf` in the project root, then click **Re-index**.              |
| Job stuck on "Retrieving resume chunks (RAG)"      | The Qdrant collection is empty. Click **Re-index** on the Tailor page or run `python -m src.ingest`. |
| `REJECTED` from the guardrail                      | Input was too short (<200 chars) or failed the LLM classifier. Paste a fuller JD.         |
| `send_email failed` on Send                        | Check `.env`: SMTP_USER and SMTP_APP_PASSWORD must be set. App passwords ≠ your login password. |

---

## Guardrails (recap)

- **Input-level**: keyword heuristic + phi4-mini classifier rejects non-JD input.
- **Prompt-level**: tailor and email-compose system prompts reply `REFUSED:` to off-task requests (even prompt-injected ones inside the JD).
- **MCP-level**: the server exposes only `send_email`; the attachment must be a `.pdf` resolving inside the project directory.
