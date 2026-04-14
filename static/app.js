const state = {
  data: null,
  toastTimer: null,
  creating: false,
  domainSaving: false,
  runningJobId: "",
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
  approvedDomains: document.getElementById("approved-domains"),
  blockedDomains: document.getElementById("blocked-domains"),
  approvedDomainInput: document.getElementById("approved-domain-input"),
  blockedDomainInput: document.getElementById("blocked-domain-input"),
  addApprovedDomainButton: document.getElementById("add-approved-domain"),
  addBlockedDomainButton: document.getElementById("add-blocked-domain"),
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

  elements.addApprovedDomainButton.addEventListener("click", async () => {
    await addDomainRule("approved", elements.approvedDomainInput.value);
  });

  elements.addBlockedDomainButton.addEventListener("click", async () => {
    await addDomainRule("blocked", elements.blockedDomainInput.value);
  });

  elements.approvedDomainInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await addDomainRule("approved", elements.approvedDomainInput.value);
    }
  });

  elements.blockedDomainInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await addDomainRule("blocked", elements.blockedDomainInput.value);
    }
  });

  document.addEventListener("click", async (event) => {
    const runButton = event.target.closest("[data-action='run-job']");
    if (runButton) {
      await runSearchRequest(runButton.dataset.jobId);
      return;
    }

    const removeButton = event.target.closest("[data-action='remove-domain']");
    if (!removeButton) {
      return;
    }
    await removeDomainRule(removeButton.dataset.listType, removeButton.dataset.domain);
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

  elements.heroTitle.textContent = state.data.product.name;
  elements.heroCopy.textContent = `${v1.workflowName}. ${state.data.product.tagline}`;

  elements.subjectType.value = form.subjectType;
  elements.subjectName.value = form.subjectName;
  elements.subjectDetails.value = form.subjectDetails;
  elements.googlePages.value = String(form.googlePages);
  elements.photoCheckRequired.checked = Boolean(form.photoCheckRequired);

  elements.workspacePath.textContent = v1.outputRoot;
  elements.approvedDomains.innerHTML = renderDomainList(v1.approvedDomains, "approved");
  elements.blockedDomains.innerHTML = renderDomainList(v1.blockedDomains, "blocked");

  elements.createRequestButton.disabled = state.creating;
  elements.createRequestButton.textContent = state.creating ? "Creating..." : "Create Request Folder";
  elements.addApprovedDomainButton.disabled = state.domainSaving;
  elements.addBlockedDomainButton.disabled = state.domainSaving;

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
          ${job.lastRunAt ? `<p><strong>Last run:</strong> ${escapeHtml(job.lastRunAt)}</p>` : ""}
          ${renderRunSummary(job.lastRunSummary)}
          <p><strong>Folder:</strong> ${escapeHtml(job.folderPath)}</p>
          <div class="button-row">
            <button
              class="btn-outline"
              data-action="run-job"
              data-job-id="${escapeHtml(job.id)}"
              ${state.runningJobId === job.id ? "disabled" : ""}
            >
              ${state.runningJobId === job.id ? "Running..." : "Run Search"}
            </button>
          </div>
        </article>
      `
    )
    .join("");
}

function renderRunSummary(summary) {
  if (!summary || Object.keys(summary).length === 0) {
    return `<p class="run-note"><strong>Execution:</strong> Not run yet.</p>`;
  }
  if (summary.error) {
    return `<p class="run-note"><strong>Execution:</strong> Failed - ${escapeHtml(summary.error)}</p>`;
  }
  return `
    <div class="run-summary">
      <p><strong>Search path:</strong> ${escapeHtml(summary.searchPath || "Google")}</p>
      <p><strong>Results seen:</strong> ${escapeHtml(String(summary.googleResultsFound ?? 0))}</p>
      <p><strong>Approved candidates:</strong> ${escapeHtml(String(summary.approvedCandidates ?? 0))}</p>
      <p><strong>Strong matches:</strong> ${escapeHtml(String(summary.strongMatches ?? 0))} | <strong>Possible:</strong> ${escapeHtml(String(summary.possibleMatches ?? 0))}</p>
      <p><strong>Blocked skipped:</strong> ${escapeHtml(String(summary.blockedSkipped ?? 0))}</p>
      <p><strong>PDF captured:</strong> ${escapeHtml(String(summary.pdfCaptured ?? 0))} | <strong>Screenshots:</strong> ${escapeHtml(String(summary.screenshotsCaptured ?? 0))}</p>
    </div>
  `;
}

function renderDomainList(domains, listType) {
  if (!domains || domains.length === 0) {
    return `<li class="domain-empty">No domains configured yet.</li>`;
  }
  return domains
    .map(
      (domain) => `
        <li>
          <span>${escapeHtml(domain)}</span>
          <button
            class="remove-chip"
            data-action="remove-domain"
            data-list-type="${escapeHtml(listType)}"
            data-domain="${escapeHtml(domain)}"
            title="Remove domain"
          >
            Remove
          </button>
        </li>
      `
    )
    .join("");
}

async function createRequest() {
  if (!state.data) {
    return;
  }

  try {
    const payload = {
      subjectType: elements.subjectType.value,
      subjectName: elements.subjectName.value,
      subjectDetails: elements.subjectDetails.value,
      googlePages: Number(elements.googlePages.value),
      photoCheckRequired: elements.photoCheckRequired.checked,
    };

    state.creating = true;
    render();

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

async function addDomainRule(listType, domainValue) {
  if (!domainValue || !domainValue.trim()) {
    showToast("Enter a domain before adding.");
    return;
  }

  try {
    state.domainSaving = true;
    render();
    const response = await postJson("/api/v1/domain-rules", {
      listType,
      action: "add",
      domain: domainValue,
    });
    state.data.v1Simple = response.v1Simple;
    if (listType === "approved") {
      elements.approvedDomainInput.value = "";
    } else {
      elements.blockedDomainInput.value = "";
    }
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Unable to add domain: ${error.message}`);
  } finally {
    state.domainSaving = false;
    render();
  }
}

async function removeDomainRule(listType, domainValue) {
  try {
    state.domainSaving = true;
    render();
    const response = await postJson("/api/v1/domain-rules", {
      listType,
      action: "remove",
      domain: domainValue,
    });
    state.data.v1Simple = response.v1Simple;
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Unable to remove domain: ${error.message}`);
  } finally {
    state.domainSaving = false;
    render();
  }
}

async function runSearchRequest(jobId) {
  if (!jobId) {
    return;
  }
  try {
    state.runningJobId = jobId;
    render();
    const response = await postJson(`/api/v1/search-requests/${encodeURIComponent(jobId)}/run`, {});
    state.data.v1Simple = response.v1Simple;
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Unable to run search: ${error.message}`);
  } finally {
    state.runningJobId = "";
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
