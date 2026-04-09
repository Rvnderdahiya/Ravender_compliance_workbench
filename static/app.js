const state = {
  data: null,
  activeTab: "analyst",
  activeCaseId: null,
  activePackId: null,
  toastTimer: null,
};

const elements = {
  heroStats: document.getElementById("hero-stats"),
  caseQueue: document.getElementById("case-queue"),
  pilotPosture: document.getElementById("pilot-posture"),
  workspace: document.getElementById("workspace"),
  toast: document.getElementById("toast"),
  tabRow: document.getElementById("tab-row"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  fetchBootstrap();
});

function bindEvents() {
  document.addEventListener("click", async (event) => {
    const tabButton = event.target.closest("[data-tab]");
    if (tabButton) {
      state.activeTab = tabButton.dataset.tab;
      render();
      return;
    }

    const caseCard = event.target.closest("[data-case-id]");
    if (caseCard) {
      state.activeCaseId = caseCard.dataset.caseId;
      render();
      return;
    }

    const packCard = event.target.closest("[data-pack-id]");
    if (packCard && state.activeTab === "packs") {
      state.activePackId = packCard.dataset.packId;
      render();
      return;
    }

    const action = event.target.closest("[data-action]");
    if (!action) {
      return;
    }

    const currentCase = getCurrentCase();
    if (!currentCase) {
      showToast("No case is selected right now.");
      return;
    }

    if (action.dataset.action === "run-pack") {
      await runPack(currentCase);
      return;
    }

    if (action.dataset.action === "resume-source") {
      await resumeSource(currentCase, action.dataset.sourceId);
      return;
    }

    if (action.dataset.action === "pick-decision") {
      currentCase.decision = action.dataset.decision;
      render();
      return;
    }

    if (action.dataset.action === "submit-decision") {
      await submitDecision(currentCase);
      return;
    }

    if (action.dataset.action === "download-evidence") {
      downloadEvidencePack(currentCase);
    }
  });

  document.addEventListener("change", (event) => {
    const currentCase = getCurrentCase();
    if (!currentCase) {
      return;
    }

    if (event.target.id === "pack-select") {
      currentCase.selectedPackId = event.target.value;
      state.activePackId = event.target.value;
      render();
    }
  });

  document.addEventListener("input", (event) => {
    const currentCase = getCurrentCase();
    if (!currentCase) {
      return;
    }

    if (event.target.id === "decision-notes") {
      currentCase.notes = event.target.value;
    }
  });
}

async function fetchBootstrap() {
  try {
    const response = await fetch("/api/bootstrap");
    state.data = await response.json();

    if (!state.activeCaseId && state.data.cases.length > 0) {
      state.activeCaseId = state.data.cases[0].id;
    }

    if (!state.activePackId && state.data.packs.length > 0) {
      state.activePackId = state.data.packs[0].id;
    }

    render();
  } catch (error) {
    showToast(`Unable to load the workbench: ${error.message}`);
  }
}

function render() {
  if (!state.data) {
    return;
  }

  renderTabs();
  renderHeroStats();
  renderQueue();
  renderPilotPosture();
  renderWorkspace();
}

function renderTabs() {
  elements.tabRow.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === state.activeTab);
  });
}

function renderHeroStats() {
  elements.heroStats.innerHTML = state.data.stats
    .map(
      (metric) => `
        <div class="metric-card">
          <strong>${escapeHtml(metric.value)}</strong>
          <span>${escapeHtml(metric.label)}</span>
        </div>
      `
    )
    .join("");
}

function renderQueue() {
  const cards = state.data.cases
    .map((caseRecord) => {
      const active = caseRecord.id === state.activeCaseId ? "is-active" : "";
      return `
        <article class="case-card ${active}" data-case-id="${escapeHtml(caseRecord.id)}">
          <div class="card-topline">
            <div>
              <p class="micro-label">${escapeHtml(caseRecord.id)}</p>
              <h3>${escapeHtml(caseRecord.subject)}</h3>
            </div>
            ${renderBadge(caseRecord.status)}
          </div>
          <p class="tiny">${escapeHtml(caseRecord.lineOfBusiness)} | ${escapeHtml(caseRecord.country)} | ${escapeHtml(caseRecord.riskLevel)} risk</p>
          <p class="muted">${escapeHtml(caseRecord.summary)}</p>
        </article>
      `;
    })
    .join("");

  elements.caseQueue.innerHTML = `<div class="case-list">${cards}</div>`;
}

function renderPilotPosture() {
  const { product, serverTime } = state.data;
  elements.pilotPosture.innerHTML = `
    <div class="stack">
      <div class="summary-card">
        <p class="micro-label">Engine</p>
        <h3>${escapeHtml(product.engine)}</h3>
        <p class="muted">${escapeHtml(product.hostingMode)}</p>
      </div>
      <div class="summary-card">
        <p class="micro-label">Server time</p>
        <h3>${escapeHtml(serverTime)}</h3>
        <p class="muted">Pilot data resets when the server restarts.</p>
      </div>
    </div>
  `;
}

function renderWorkspace() {
  if (state.activeTab === "analyst") {
    elements.workspace.innerHTML = renderAnalystView();
    return;
  }

  if (state.activeTab === "packs") {
    elements.workspace.innerHTML = renderPacksView();
    return;
  }

  if (state.activeTab === "controls") {
    elements.workspace.innerHTML = renderControlsView();
    return;
  }

  elements.workspace.innerHTML = renderBlueprintView();
}

function renderAnalystView() {
  const currentCase = getCurrentCase();
  if (!currentCase) {
    return `<div class="empty-state">No case selected.</div>`;
  }

  const selectedPack = getPack(currentCase.selectedPackId);
  const canRun = selectedPack && selectedPack.status === "Published";

  const tasksHtml = currentCase.tasks
    .map(
      (task) => `
        <article class="source-card">
          <div class="row-split">
            <div>
              <p class="micro-label">${escapeHtml(task.mode)}</p>
              <h3>${escapeHtml(task.label)}</h3>
            </div>
            ${renderBadge(task.status)}
          </div>
          <p class="muted">Hits: <strong>${escapeHtml(String(task.hits))}</strong> | Evidence: <strong>${escapeHtml(String(task.evidenceCount))}</strong></p>
          <p class="tiny">Last run: ${escapeHtml(task.lastRun)}</p>
          ${
            task.status === "Needs assist"
              ? `<button class="btn btn-soft" data-action="resume-source" data-source-id="${escapeHtml(task.sourceId)}">Resume Source</button>`
              : ""
          }
        </article>
      `
    )
    .join("");

  const evidenceHtml =
    currentCase.evidence.length > 0
      ? currentCase.evidence
          .map(
            (item) => `
              <article class="evidence-card">
                <div class="row-split">
                  <div>
                    <p class="micro-label">${escapeHtml(getSourceName(item.sourceId))}</p>
                    <h3>${escapeHtml(item.title)}</h3>
                  </div>
                  ${renderBadge(item.confidence)}
                </div>
                <p class="muted">${escapeHtml(item.summary)}</p>
                <div class="fields-grid">
                  ${Object.entries(item.fields)
                    .map(
                      ([label, value]) => `
                        <div class="field-pair">
                          <strong>${escapeHtml(label)}</strong>
                          <span>${escapeHtml(String(value))}</span>
                        </div>
                      `
                    )
                    .join("")}
                </div>
                <p class="tiny">Captured ${escapeHtml(item.capturedAt)}</p>
              </article>
            `
          )
          .join("")
      : `<div class="empty-state">Run a certified Search Pack to generate evidence cards for this case.</div>`;

  const auditHtml = currentCase.auditTrail
    .slice(0, 5)
    .map(
      (entry) => `
        <article class="timeline-card">
          <div class="row-split">
            <h3>${escapeHtml(entry.actor)}</h3>
            <span class="tiny">${escapeHtml(entry.time)}</span>
          </div>
          <p class="muted">${escapeHtml(entry.message)}</p>
        </article>
      `
    )
    .join("");

  return `
    <div class="analyst-layout">
      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Case workspace</p>
            <h2>${escapeHtml(currentCase.subject)}</h2>
          </div>
          ${renderBadge(currentCase.status)}
        </div>
        <div class="pill-row">
          <div class="pill"><strong>Case ID</strong><span>${escapeHtml(currentCase.id)}</span></div>
          <div class="pill"><strong>DOB</strong><span>${escapeHtml(currentCase.dob)}</span></div>
          <div class="pill"><strong>Country</strong><span>${escapeHtml(currentCase.country)}</span></div>
          <div class="pill"><strong>LOB</strong><span>${escapeHtml(currentCase.lineOfBusiness)}</span></div>
          <div class="pill"><strong>Risk</strong><span>${escapeHtml(currentCase.riskLevel)}</span></div>
          <div class="pill"><strong>Suggested</strong><span>${escapeHtml(currentCase.recommendedDecision)}</span></div>
        </div>
        <p class="muted">${escapeHtml(currentCase.summary)}</p>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Run certified pack</p>
            <h2>${escapeHtml(selectedPack ? selectedPack.name : "No pack selected")}</h2>
          </div>
          ${selectedPack ? renderBadge(selectedPack.status) : ""}
        </div>
        <div class="toolbar">
          <div class="field">
            <label for="pack-select">Certified Search Pack</label>
            <select id="pack-select">
              ${state.data.packs
                .map(
                  (pack) => `
                    <option value="${escapeHtml(pack.id)}" ${pack.id === currentCase.selectedPackId ? "selected" : ""}>
                      ${escapeHtml(pack.name)} (${escapeHtml(pack.status)})
                    </option>
                  `
                )
                .join("")}
            </select>
          </div>
          <div class="button-row">
            <button class="btn btn-primary" data-action="run-pack" ${canRun ? "" : "disabled"}>
              Run Certified Pack
            </button>
            <button class="btn btn-ghost" data-action="download-evidence" ${currentCase.evidence.length ? "" : "disabled"}>
              Download Evidence Pack
            </button>
          </div>
        </div>
        ${
          !canRun
            ? `<p class="tiny">Only published packs are runnable from the analyst workbench.</p>`
            : `<p class="tiny">This pilot runs a deterministic engine now and is structured to map to Schrute later.</p>`
        }
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Source status</p>
            <h2>Certified source board</h2>
          </div>
        </div>
        <div class="card-grid three-up">
          ${tasksHtml}
        </div>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Evidence</p>
            <h2>Analyst review cards</h2>
          </div>
        </div>
        <div class="stack">
          ${evidenceHtml}
        </div>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Disposition</p>
            <h2>Submit analyst decision</h2>
          </div>
        </div>
        <div class="button-row">
          ${["No Match", "Potential Match", "Escalate"].map((decision) => `
            <button
              class="decision-chip ${currentCase.decision === decision ? "is-active" : ""}"
              data-action="pick-decision"
              data-decision="${escapeHtml(decision)}"
            >
              ${escapeHtml(decision)}
            </button>
          `).join("")}
        </div>
        <div class="field">
          <label for="decision-notes">Analyst notes</label>
          <textarea id="decision-notes" placeholder="Capture why this case should close, escalate, or move to reviewer queue.">${escapeHtml(currentCase.notes || "")}</textarea>
        </div>
        <div class="button-row">
          <button class="btn btn-secondary" data-action="submit-decision" ${currentCase.decision ? "" : "disabled"}>
            Submit For Review
          </button>
        </div>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Audit trail</p>
            <h2>Recent workflow events</h2>
          </div>
        </div>
        <div class="timeline">
          ${auditHtml}
        </div>
      </section>
    </div>
  `;
}

function renderPacksView() {
  const activePack = getPack(state.activePackId) || getPack(getCurrentCase()?.selectedPackId) || state.data.packs[0];
  const packCards = state.data.packs
    .map(
      (pack) => `
        <article class="pack-card ${pack.id === activePack.id ? "is-active" : ""}" data-pack-id="${escapeHtml(pack.id)}">
          <div class="row-split">
            <div>
              <p class="micro-label">${escapeHtml(pack.version)}</p>
              <h3>${escapeHtml(pack.name)}</h3>
            </div>
            ${renderBadge(pack.status)}
          </div>
          <p class="muted">${escapeHtml(pack.description)}</p>
          <p class="tiny">Owner: ${escapeHtml(pack.owner)}</p>
        </article>
      `
    )
    .join("");

  return `
    <div class="packs-layout">
      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Admin surface</p>
            <h2>Search Pack Studio</h2>
          </div>
          ${renderBadge(activePack.status)}
        </div>
        <p class="muted">
          This is where technical admins define, validate, certify, and publish analyst-safe search packs. Analysts should never see raw automation internals here.
        </p>
      </section>

      <section class="card-grid two-up">
        <div class="stack">${packCards}</div>
        <article class="summary-card">
          <p class="section-label">Selected pack</p>
          <h2>${escapeHtml(activePack.name)}</h2>
          <p class="muted">${escapeHtml(activePack.description)}</p>

          <p class="micro-label">Inputs</p>
          <ul class="list-clean">
            ${activePack.inputs.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>

          <p class="micro-label">Steps</p>
          <ul class="list-clean">
            ${activePack.steps.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>

          <p class="micro-label">Controls</p>
          <ul class="list-clean">
            ${activePack.controls.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>
        </article>
      </section>
    </div>
  `;
}

function renderControlsView() {
  const sourceCards = state.data.sources
    .map(
      (source) => `
        <article class="governance-card">
          <div class="row-split">
            <div>
              <p class="micro-label">${escapeHtml(source.category)}</p>
              <h3>${escapeHtml(source.name)}</h3>
            </div>
            ${renderBadge(source.approvalState)}
          </div>
          <p class="muted">Auth: ${escapeHtml(source.authModel)}</p>
          <p class="muted">Execution: ${escapeHtml(source.executionMode)}</p>
        </article>
      `
    )
    .join("");

  const controls = state.data.blueprint.controls
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  return `
    <div class="controls-layout">
      <section class="summary-card">
        <p class="section-label">Governance</p>
        <h2>Certified source registry</h2>
        <p class="muted">
          Every source is explicitly classified before analysts can use it. Phase 1 remains read-only across public and internal portals.
        </p>
      </section>
      <section class="card-grid two-up">
        <div class="card-grid two-up">${sourceCards}</div>
        <article class="summary-card">
          <p class="section-label">Mandatory controls</p>
          <h2>Non-negotiable operating rules</h2>
          <ul class="list-clean">${controls}</ul>
        </article>
      </section>
    </div>
  `;
}

function renderBlueprintView() {
  const principles = state.data.blueprint.principles
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  const phases = state.data.blueprint.phases
    .map(
      (phase) => `
        <article class="timeline-card">
          <p class="micro-label">${escapeHtml(phase.name)}</p>
          <h3>${escapeHtml(phase.focus)}</h3>
          <p class="muted">${escapeHtml(phase.outcome)}</p>
        </article>
      `
    )
    .join("");

  return `
    <div class="blueprint-layout">
      <section class="summary-card">
        <p class="section-label">Blueprint</p>
        <h2>How this pilot grows into the enterprise product</h2>
        <ul class="list-clean">${principles}</ul>
      </section>
      <section class="timeline">
        ${phases}
      </section>
    </div>
  `;
}

async function runPack(caseRecord) {
  try {
    const response = await postJson(`/api/cases/${encodeURIComponent(caseRecord.id)}/run-pack`, {
      packId: caseRecord.selectedPackId,
    });
    replaceCase(response.case);
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Pack run failed: ${error.message}`);
  }
}

async function resumeSource(caseRecord, sourceId) {
  try {
    const response = await postJson(`/api/cases/${encodeURIComponent(caseRecord.id)}/resume-source`, {
      sourceId,
    });
    replaceCase(response.case);
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Source resume failed: ${error.message}`);
  }
}

async function submitDecision(caseRecord) {
  try {
    const response = await postJson(`/api/cases/${encodeURIComponent(caseRecord.id)}/decision`, {
      decision: caseRecord.decision,
      notes: caseRecord.notes || "",
    });
    replaceCase(response.case);
    showToast(response.message);
    render();
  } catch (error) {
    showToast(`Unable to submit decision: ${error.message}`);
  }
}

function replaceCase(updatedCase) {
  const index = state.data.cases.findIndex((caseRecord) => caseRecord.id === updatedCase.id);
  if (index >= 0) {
    state.data.cases[index] = updatedCase;
  }
}

function getCurrentCase() {
  if (!state.data) {
    return null;
  }
  return state.data.cases.find((caseRecord) => caseRecord.id === state.activeCaseId) || null;
}

function getPack(packId) {
  if (!state.data) {
    return null;
  }
  return state.data.packs.find((pack) => pack.id === packId) || null;
}

function getSourceName(sourceId) {
  const source = state.data.sources.find((entry) => entry.id === sourceId);
  return source ? source.name : sourceId;
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

function downloadEvidencePack(caseRecord) {
  const blob = new Blob([JSON.stringify(caseRecord, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${caseRecord.id.toLowerCase()}-evidence-pack.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("Evidence pack downloaded.");
}

function renderBadge(value) {
  return `<span class="badge ${badgeTone(value)}">${escapeHtml(value)}</span>`;
}

function badgeTone(value) {
  const normalized = value.toLowerCase();
  if (["complete", "published", "certified", "high"].includes(normalized)) {
    return "tone-success";
  }
  if (["needs assist", "pilot", "needs review", "medium"].includes(normalized)) {
    return "tone-warn";
  }
  if (["draft", "draft pack only", "low"].includes(normalized)) {
    return "tone-danger";
  }
  if (["submitted for review"].includes(normalized)) {
    return "tone-brand";
  }
  return "tone-neutral";
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;

  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }

  state.toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 2400);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
