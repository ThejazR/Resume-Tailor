// Thin fetch wrapper.
const API = {
  async _fetch(path, init = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(init.headers || {}) },
      ...init,
    });
    let body = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      body = await res.json().catch(() => null);
    } else {
      body = await res.text().catch(() => null);
    }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : (typeof body === "string" ? body : res.statusText);
      throw new Error(detail || `HTTP ${res.status}`);
    }
    return body;
  },
  health: () => API._fetch("/api/health"),
  listJobs: () => API._fetch("/api/jobs"),
  getJob: (id) => API._fetch(`/api/jobs/${id}`),
  createJob: (jd, recipient, ats) => API._fetch("/api/jobs", { method: "POST", body: JSON.stringify({ jd, recipient: recipient || null, ats: !!ats }) }),
  deleteJob: (id) => API._fetch(`/api/jobs/${id}`, { method: "DELETE" }),
  updateJob: (id, patch) => API._fetch(`/api/jobs/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  send: (id, patch) => API._fetch(`/api/jobs/${id}/send`, { method: "POST", body: JSON.stringify(patch || {}) }),
  getSkills: (id) => API._fetch(`/api/jobs/${id}/skills`),
  setSkills: (id, skills, ats) => API._fetch(`/api/jobs/${id}/skills`, { method: "PUT", body: JSON.stringify({ skills, ats: !!ats }) }),
  rerender: (id, ats, resume_text) => API._fetch(`/api/jobs/${id}/render`, { method: "POST", body: JSON.stringify({ ats: !!ats, resume_text: resume_text ?? null }) }),
  ingest: () => API._fetch("/api/ingest", { method: "POST" }),
  uploadResume: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/resume/upload", { method: "POST", body: fd });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
};
