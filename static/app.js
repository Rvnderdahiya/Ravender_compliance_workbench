const state = {
  data: null,
  toastTimer: null,
  creating: false,
};

const elements = {
  heroTitle: document.getElementById("hero-title"),
  heroCopy: document.getElementById("hero-copy"),
  subjectType: document.getElementById("subject-type"),
  subjectName: document.getElementById("subject-name"),
  subjectDetails: document.getElementById("subject-details"),
  googlePages: document.getElementById("google-pages"),
  photoCheckRequired: document.getElementById("photo-check-required"),
  createRequestButton: document.getElementById("create-request"),
  workspacePath: document.getElementById("workspace-path"),
  allowedDomains: document.getElementById("allowed-domains"),
  blockedDomains: document.getElementById("blocked-domains"),
  jobsList: document.getElementById("jobs-list"),
  toast: document.getElementById("toast"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  fetchBootstrap();
});

function bindEvents() {
  elements.createRequestButton.addEventListener("click", async () => {
    await createRequest();
  });
}

async function fetchBootstrap() {
  const response = await fetch("/api/bootstrap");
  state.data = await response.json();
  render();
}

function render() {
  if (!state.data) {
    return;
  }

  const v1 = state.data.v1Simple;
  const form = v1.form;

  elements.heroTitle.textContent = `${state.data.product.name} - ${v1.workflowName}`;
  elements.heroCopy.textContent = state.data.product.tagline;

  elements.subjectType.value = form.subjectType;
  elements.subjectName.value = form.subjectName;
  elements.subjectDetails.value = form.subjectDetails;
  elements.googlePages.value = String(form.googlePages);
  elements.photoCheckRequired.checked = Boolean(form.photoCheckRequired);

  elements.workspacePath.textContent = v1.outputRoot;
  elements.allowedDomains.innerHTML = v1.allowedDomainHints.map((domain) => `<li>${escapeHtml(domain)}</li>`).join("");
  elements.blockedDomains.innerHTML = v1.blockedDomains.map((domain) => `<li>${escapeHtml(domain)}</li>`).join("");

  elements.createRequestButton.disabled = state.creating;
  elements.createRequestButton.textContent = state.creating ? "Creating..." : "Create Request Folder";

  if (v1.jobs.length === 0) {
    elements.jobsList.innerHTML = `<div class="empty-state">No requests yet. Create the first request folder from the form above.</div>`;
    return;
  }

  elements.jobsList.innerHTML = v1.jobs
    .map(
      (job) => `
        <article class="job-card">
          <div class="job-head">
            <h3>${escapeHtml(job.subjectName)}</h3>
            <span class="job-badge">${escapeHtml(job.status)}</span>
          </div>
          <p><strong>Type:</strong> ${escapeHtml(job.subjectType)} | <strong>Google depth:</strong> Page ${escapeHtml(String(job.googlePages))}</p>
          <p><strong>Photo check:</strong> ${job.photoCheckRequired ? "Yes" : "No"}</p>
          <p><strong>Created:</strong> ${escapeHtml(job.createdAt)}</p>
          <p><strong>Folder:</strong> ${escapeHtml(job.folderPath)}</p>
        </article>
      `
    )
    .join("");
}

async function createRequest() {
  if (!state.data) {
    return;
  }

  try {
    state.creating = true;
    render();

    const payload = {
      subjectType: elements.subjectType.value,
      subjectName: elements.subjectName.value,
      subjectDetails: elements.subjectDetails.value,
      googlePages: Number(elements.googlePages.value),
      photoCheckRequired: elements.photoCheckRequired.checked,
    };

    const response = await postJson("/api/v1/search-requests", payload);
    state.data.v1Simple = response.v1Simple;
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Unable to create request: ${error.message}`);
  } finally {
    state.creating = false;
    render();
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unexpected server error");
  }
  return payload;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 3200);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
