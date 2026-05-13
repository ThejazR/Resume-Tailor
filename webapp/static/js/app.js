// Shared UI helpers: toasts, health pill, status chip mapping, nav helpers.

function toast(message, kind = "info") {
  const host = document.getElementById("toast-host");
  if (!host) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="material-symbols-outlined text-[18px]">${
    kind === "error" ? "error" : kind === "success" ? "check_circle" : "info"
  }</span><span class="font-label-md text-label-md">${escapeHtml(message)}</span>`;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.3s";
    setTimeout(() => el.remove(), 300);
  }, 4500);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function statusChip(status) {
  const map = {
    pending: "Pending",
    running: "Running",
    done: "Optimized",
    sent: "Sent",
    error: "Error",
    rejected: "Rejected",
  };
  const label = map[status] || status;
  return `<span class="chip ${status}">${label}</span>`;
}

function fmtDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleDateString();
  } catch (e) {
    return iso;
  }
}

async function refreshHealth() {
  const pill = document.getElementById("health-pill");
  const dot = document.getElementById("health-dot");
  const text = document.getElementById("health-text");
  if (!pill) return;
  try {
    const h = await API.health();
    const ok = h.ok && h.qdrant && h.ollama_model_ready && h.resume_pdf_exists;
    if (ok) {
      dot.classList.remove("bg-outline", "bg-error");
      dot.classList.add("bg-on-tertiary-container");
      text.textContent = "All services ready";
    } else {
      dot.classList.remove("bg-outline", "bg-on-tertiary-container");
      dot.classList.add("bg-error");
      const probs = [];
      if (!h.qdrant) probs.push("Qdrant");
      if (!h.ollama_model_ready) probs.push("Ollama model");
      if (!h.resume_pdf_exists) probs.push("resume.pdf");
      text.textContent = probs.length ? `Missing: ${probs.join(", ")}` : "Issue";
    }
    pill.title = JSON.stringify(h, null, 2);
  } catch (e) {
    dot.classList.add("bg-error");
    text.textContent = "Offline";
  }
}

async function goLatestPreview(e) {
  if (e && e.preventDefault) e.preventDefault();
  try {
    const { jobs } = await API.listJobs();
    const ready = jobs.find((j) => ["done", "sent"].includes(j.status));
    if (!ready) {
      toast("No tailored resume yet — start one first.", "info");
      window.location.href = "/tailor";
      return;
    }
    window.location.href = `/preview/${ready.id}`;
  } catch (e) {
    toast("Could not load history.", "error");
  }
}

window.addEventListener("DOMContentLoaded", refreshHealth);
