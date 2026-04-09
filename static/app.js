const state = {
  data: null,
  activeTab: "public",
  activeCaseId: null,
  activePackId: null,
  activePublicRunId: null,
  toastTimer: null,
  publicRunning: false,
};

const elements = {
  heroStats: document.getElementById("hero-stats"),
  heroTitle: document.getElementById("hero-title"),
  heroText: document.getElementById("hero-text"),
  caseQueue: document.getElementById("case-queue"),
  pilotPosture: document.getElementById("pilot-posture"),
  workspace: document.getElementById("workspace"),
  toast: document.getElementById("toast"),
  tabRow: document.getElementById("tab-row"),
  sidebarPrimaryLabel: document.getElementById("sidebar-primary-label"),
  sidebarSecondaryLabel: document.getElementById("sidebar-secondary-label"),
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

    const publicRunCard = event.target.closest("[data-public-run-id]");
    if (publicRunCard) {
      state.activePublicRunId = publicRunCard.dataset.publicRunId;
      render();
      return;
    }

    const action = event.target.closest("[data-action]");
    if (!action) {
      return;
    }

    if (action.dataset.action === "run-public") {
      await runPublicInvestigator();
      return;
    }

    if (action.dataset.action === "download-public") {
      downloadJson(
        getActivePublicRun(),
        "public-site-investigation.json",
        "No public investigation result is available yet."
      );
      return;
    }

    if (action.dataset.action === "use-public-preset") {
      state.data.publicInvestigator.form.url = action.dataset.url;
      state.data.publicInvestigator.form.query = action.dataset.query;
      render();
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
      downloadJson(
        currentCase,
        `${currentCase.id.toLowerCase()}-evidence-pack.json`,
        "No case data is available to export."
      );
    }
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!state.data) {
      return;
    }

    if (target.id === "pack-select") {
      const currentCase = getCurrentCase();
      if (!currentCase) {
        return;
      }
      currentCase.selectedPackId = target.value;
      state.activePackId = target.value;
      render();
      return;
    }

    if (target.id === "public-max-pages") {
      state.data.publicInvestigator.form.maxPages = Number(target.value);
      render();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!state.data) {
      return;
    }

    if (target.id === "decision-notes") {
      const currentCase = getCurrentCase();
      if (currentCase) {
        currentCase.notes = target.value;
      }
      return;
    }

    if (target.id === "public-url") {
      state.data.publicInvestigator.form.url = target.value;
      return;
    }

    if (target.id === "public-query") {
      state.data.publicInvestigator.form.query = target.value;
    }
  });
}

async function fetchBootstrap() {
  const response = await fetch("/api/bootstrap");
  state.data = await response.json();

  if (!state.activeCaseId && state.data.cases.length > 0) {
    state.activeCaseId = state.data.cases[0].id;
  }

  if (!state.activePackId && state.data.packs.length > 0) {
    state.activePackId = state.data.packs[0].id;
  }

  const publicRuns = state.data.publicInvestigator.runs || [];
  const runStillExists = publicRuns.some((run) => run.id === state.activePublicRunId);
  if ((!state.activePublicRunId || !runStillExists) && publicRuns.length > 0) {
    state.activePublicRunId = publicRuns[0].id;
  }

  render();
}

function render() {
  if (!state.data) {
    return;
  }

  renderTabs();
  renderHero();
  renderHeroStats();
  renderSidebar();
  renderWorkspace();
}

function renderTabs() {
  elements.tabRow.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === state.activeTab);
  });
}

function renderHero() {
  elements.heroTitle.textContent = state.data.product.name;
  elements.heroText.textContent =
    state.activeTab === "public"
      ? "Live public-website research with same-site crawling, matching, extraction, and export."
      : state.data.product.tagline;
}

function renderHeroStats() {
  elements.heroStats.innerHTML = state.data.stats
    .map(
      (metric) => `
        <div class="metric-card">
          <span>${escapeHtml(metric.label)}</span>
          <strong>${escapeHtml(metric.value)}</strong>
        </div>
      `
    )
    .join("");
}

function renderSidebar() {
  if (state.activeTab === "public") {
    elements.sidebarPrimaryLabel.textContent = "Recent runs";
    elements.sidebarSecondaryLabel.textContent = "Coverage";
    renderRecentRunsSidebar();
    renderCoverageSidebar();
    return;
  }

  elements.sidebarPrimaryLabel.textContent = "Queue";
  elements.sidebarSecondaryLabel.textContent = "Pilot posture";
  renderCaseQueueSidebar();
  renderPilotPostureSidebar();
}

function renderCaseQueueSidebar() {
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

function renderPilotPostureSidebar() {
  const { product, serverTime } = state.data;
  elements.pilotPosture.innerHTML = `
    <div class="stack">
      <div class="summary-card accent-card accent-dark">
        <p class="micro-label">Engine</p>
        <h3>${escapeHtml(product.engine)}</h3>
        <p class="muted">${escapeHtml(product.hostingMode)}</p>
      </div>
      <div class="summary-card">
        <p class="micro-label">Server time</p>
        <h3>${escapeHtml(serverTime)}</h3>
        <p class="muted">Case and investigation data reset when the server restarts.</p>
      </div>
    </div>
  `;
}

function renderRecentRunsSidebar() {
  const runs = state.data.publicInvestigator.recentRuns;
  elements.caseQueue.innerHTML =
    runs.length > 0
      ? `<div class="stack">
          ${runs
            .map(
              (run) => `
                <article class="summary-card sidebar-run-card ${run.id === state.activePublicRunId ? "is-active" : ""}" data-public-run-id="${escapeHtml(run.id)}">
                  <p class="micro-label">${escapeHtml(run.domain)}</p>
                  <h3>${escapeHtml(run.pagesCrawled)} pages | ${escapeHtml(run.matchedPages)} matches</h3>
                  <p class="tiny">${escapeHtml((run.queryTerms || []).join(", ") || "Site profile only")}</p>
                  <p class="muted">${escapeHtml(run.summary)}</p>
                  <p class="tiny">${escapeHtml(run.completedAt)}</p>
                </article>
              `
            )
            .join("")}
        </div>`
      : `<div class="empty-state">Run a public website investigation to build recent history here.</div>`;
}

function renderCoverageSidebar() {
  const investigator = state.data.publicInvestigator;
  elements.pilotPosture.innerHTML = `
    <div class="stack">
      <div class="summary-card accent-card accent-emerald">
        <p class="micro-label">Supports now</p>
        <ul class="list-clean compact-list">
          ${investigator.capabilities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </div>
      <div class="summary-card">
        <p class="micro-label">Known limits</p>
        <ul class="list-clean compact-list">
          ${investigator.limits.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </div>
    </div>
  `;
}

function renderWorkspace() {
  if (state.activeTab === "public") {
    elements.workspace.innerHTML = renderPublicView();
    return;
  }

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

function renderPublicView() {
  const investigator = state.data.publicInvestigator;
  const activeRun = getActivePublicRun();

  const summaryMetrics = activeRun
    ? `
      <div class="metric-strip">
        <div class="pill"><strong>Domain</strong><span>${escapeHtml(activeRun.domain)}</span></div>
        <div class="pill"><strong>Pages crawled</strong><span>${escapeHtml(String(activeRun.pagesCrawled))}</span></div>
        <div class="pill"><strong>Matched pages</strong><span>${escapeHtml(String(activeRun.matchedPages))}</span></div>
        <div class="pill"><strong>Duration</strong><span>${escapeHtml(String(activeRun.durationMs))} ms</span></div>
      </div>
    `
    : `<div class="empty-state">No public website run has been completed yet.</div>`;

  const contactBlock = activeRun
    ? `
      <div class="chip-list">
        ${renderChipGroup("Emails", activeRun.emails)}
        ${renderChipGroup("Phones", activeRun.phones)}
      </div>
    `
    : "";

  const pagesBlock = activeRun
    ? activeRun.pages
        .map(
          (page) => `
            <article class="result-card">
              <div class="row-split">
                <div class="result-copy">
                  <p class="micro-label">${escapeHtml(page.contentType)}</p>
                  <h3>${escapeHtml(page.title)}</h3>
                  <a class="result-link" href="${escapeAttribute(page.url)}" target="_blank" rel="noreferrer">${escapeHtml(page.url)}</a>
                </div>
                ${renderBadge(page.matchCount > 0 ? `${page.matchCount} match${page.matchCount === 1 ? "" : "es"}` : "Profile")}
              </div>
              ${page.description ? `<p class="muted">${escapeHtml(page.description)}</p>` : `<p class="muted">${escapeHtml(page.textPreview)}</p>`}
              ${
                page.matchedTerms.length
                  ? `<div class="chip-list">${page.matchedTerms.map((term) => `<span class="chip chip-strong">${escapeHtml(term)}</span>`).join("")}</div>`
                  : ""
              }
              <div class="stack tight-stack">
                ${page.snippets.map((snippet) => `<div class="snippet-card">${escapeHtml(snippet)}</div>`).join("")}
              </div>
              ${
                page.headings.length
                  ? `<p class="tiny">Headings: ${escapeHtml(page.headings.join(" | "))}</p>`
                  : ""
              }
            </article>
          `
        )
        .join("")
    : `<div class="empty-state">Enter a public website, set the terms you care about, and run the investigation.</div>`;

  const crawlNotes = activeRun
    ? activeRun.crawlNotes
        .map(
          (note) => `
            <article class="timeline-card">
              <div class="row-split">
                <h3>${escapeHtml(note.type)}</h3>
              </div>
              <p class="muted">${escapeHtml(note.message)}</p>
            </article>
          `
        )
        .join("")
    : "";

  const limitations = activeRun ? activeRun.limitations : investigator.limits;

  return `
    <div class="public-layout">
      <section class="command-deck">
        <article class="summary-card accent-card accent-dark hero-card">
          <p class="section-label">Public Website Investigator</p>
          <h2>Research any open website from one screen</h2>
          <p class="muted">
            Crawl a public site, follow same-site links, extract visible text and contact details, and surface direct snippets for the terms that matter to the analyst.
          </p>
          <div class="preset-row">
            ${investigator.presets
              .map(
                (preset) => `
                  <button
                    class="btn btn-ghost preset-button"
                    data-action="use-public-preset"
                    data-url="${escapeAttribute(preset.url)}"
                    data-query="${escapeAttribute(preset.query)}"
                  >
                    ${escapeHtml(preset.label)}
                  </button>
                `
              )
              .join("")}
          </div>
        </article>

        <article class="summary-card command-form-card">
          <div class="form-grid">
            <div class="field field-wide">
              <label for="public-url">Website URL</label>
              <input id="public-url" class="text-input" value="${escapeAttribute(investigator.form.url)}" placeholder="https://www.python.org/" />
            </div>
            <div class="field field-wide">
              <label for="public-query">Terms to find</label>
              <textarea id="public-query" placeholder="company, regulation, contact, adverse media">${escapeHtml(investigator.form.query)}</textarea>
            </div>
            <div class="field field-compact">
              <label for="public-max-pages">Page cap</label>
              <select id="public-max-pages">
                ${[3, 5, 6, 8, 10, 12, 15]
                  .map(
                    (count) => `
                      <option value="${count}" ${Number(investigator.form.maxPages) === count ? "selected" : ""}>${count} pages</option>
                    `
                  )
                  .join("")}
              </select>
            </div>
          </div>
          <div class="button-row">
            <button class="btn btn-primary" data-action="run-public" ${state.publicRunning ? "disabled" : ""}>
              ${state.publicRunning ? "Running Investigation..." : "Run Live Investigation"}
            </button>
            <button class="btn btn-ghost" data-action="download-public" ${activeRun ? "" : "disabled"}>
              Export Result JSON
            </button>
          </div>
          <p class="tiny">
            This mode is built for public HTML websites. It will not fully cover authenticated portals, CAPTCHA flows, or heavy JavaScript-only pages.
          </p>
        </article>
      </section>

      <section class="card-grid two-up">
        <article class="summary-card">
          <p class="section-label">Run summary</p>
          <h2>${activeRun ? escapeHtml(activeRun.summary) : "No live result yet"}</h2>
          ${
            activeRun
              ? `<p class="tiny">Target: ${escapeHtml(activeRun.targetUrl)} | Completed: ${escapeHtml(activeRun.completedAt)} | Terms: ${escapeHtml((activeRun.queryTerms || []).join(", ") || "Site profile only")}</p>`
              : ""
          }
          ${summaryMetrics}
          ${contactBlock}
        </article>

        <article class="summary-card">
          <p class="section-label">Operational notes</p>
          <h2>What this mode does well</h2>
          <ul class="list-clean">
            ${investigator.capabilities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>
        </article>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Results</p>
            <h2>Matched pages and site profile</h2>
          </div>
          ${activeRun ? renderBadge(`${activeRun.pages.length} page cards`) : ""}
        </div>
        <div class="stack">
          ${pagesBlock}
        </div>
      </section>

      <section class="card-grid two-up">
        <article class="summary-card">
          <p class="section-label">Crawl notes</p>
          <h2>How the investigator moved through the site</h2>
          <div class="timeline">
            ${crawlNotes || `<div class="empty-state">Notes will appear after the first run.</div>`}
          </div>
        </article>
        <article class="summary-card">
          <p class="section-label">Limitations</p>
          <h2>Explicitly called out instead of hidden</h2>
          <ul class="list-clean">
            ${limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>
        </article>
      </section>
    </div>
  `;
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
              <article class="result-card">
                <div class="row-split">
                  <div class="result-copy">
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
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Source board</p>
            <h2>Certified source status</h2>
          </div>
        </div>
        <div class="card-grid three-up">${tasksHtml}</div>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Evidence</p>
            <h2>Analyst review cards</h2>
          </div>
        </div>
        <div class="stack">${evidenceHtml}</div>
      </section>

      <section class="summary-card">
        <div class="title-line">
          <div>
            <p class="section-label">Disposition</p>
            <h2>Submit analyst decision</h2>
          </div>
        </div>
        <div class="button-row">
          ${["No Match", "Potential Match", "Escalate"]
            .map(
              (decision) => `
                <button
                  class="decision-chip ${currentCase.decision === decision ? "is-active" : ""}"
                  data-action="pick-decision"
                  data-decision="${escapeHtml(decision)}"
                >
                  ${escapeHtml(decision)}
                </button>
              `
            )
            .join("")}
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
        <div class="timeline">${auditHtml}</div>
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
          This is where technical admins define, validate, certify, and publish analyst-safe packs. Analysts should never see raw automation internals here.
        </p>
      </section>

      <section class="card-grid two-up">
        <div class="stack">${packCards}</div>
        <article class="summary-card">
          <p class="section-label">Selected pack</p>
          <h2>${escapeHtml(activePack.name)}</h2>
          <p class="muted">${escapeHtml(activePack.description)}</p>
          <p class="micro-label">Inputs</p>
          <ul class="list-clean">${activePack.inputs.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          <p class="micro-label">Steps</p>
          <ul class="list-clean">${activePack.steps.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          <p class="micro-label">Controls</p>
          <ul class="list-clean">${activePack.controls.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
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

  return `
    <div class="controls-layout">
      <section class="summary-card">
        <p class="section-label">Governance</p>
        <h2>Certified source registry</h2>
        <p class="muted">
          Every source is explicitly classified before analysts can use it. Internal credentialed systems stay separate from public-site mode.
        </p>
      </section>
      <section class="card-grid two-up">
        <div class="card-grid two-up">${sourceCards}</div>
        <article class="summary-card">
          <p class="section-label">Mandatory controls</p>
          <h2>Operating rules</h2>
          <ul class="list-clean">${state.data.blueprint.controls.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </article>
      </section>
    </div>
  `;
}

function renderBlueprintView() {
  return `
    <div class="blueprint-layout">
      <section class="summary-card">
        <p class="section-label">Blueprint</p>
        <h2>How the product grows from live public-web coverage into the broader platform</h2>
        <ul class="list-clean">${state.data.blueprint.principles.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </section>
      <section class="timeline">
        ${state.data.blueprint.phases
          .map(
            (phase) => `
              <article class="timeline-card">
                <p class="micro-label">${escapeHtml(phase.name)}</p>
                <h3>${escapeHtml(phase.focus)}</h3>
                <p class="muted">${escapeHtml(phase.outcome)}</p>
              </article>
            `
          )
          .join("")}
      </section>
    </div>
  `;
}

async function runPublicInvestigator() {
  try {
    state.publicRunning = true;
    render();
    const form = state.data.publicInvestigator.form;
    const response = await postJson("/api/public-investigator/run", {
      url: form.url,
      query: form.query,
      maxPages: Number(form.maxPages),
    });
    state.activePublicRunId = response.investigation.id;
    await fetchBootstrap();
    showToast(response.message);
  } catch (error) {
    showToast(`Public investigation failed: ${error.message}`);
  } finally {
    state.publicRunning = false;
    render();
  }
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

function getActivePublicRun() {
  if (!state.data) {
    return null;
  }
  const runs = state.data.publicInvestigator.runs || [];
  if (runs.length === 0) {
    return state.data.publicInvestigator.latestRun || null;
  }
  return runs.find((run) => run.id === state.activePublicRunId) || runs[0];
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

function downloadJson(payload, filename, emptyMessage) {
  if (!payload) {
    showToast(emptyMessage);
    return;
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("Export downloaded.");
}

function renderBadge(value) {
  return `<span class="badge ${badgeTone(value)}">${escapeHtml(value)}</span>`;
}

function badgeTone(value) {
  const normalized = String(value).toLowerCase();
  if (["complete", "published", "certified", "high", "profile"].includes(normalized) || normalized.includes("match")) {
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

function renderChipGroup(label, values) {
  if (!values || values.length === 0) {
    return `
      <div class="chip-group">
        <strong>${escapeHtml(label)}</strong>
        <span class="chip chip-muted">None found</span>
      </div>
    `;
  }

  return `
    <div class="chip-group">
      <strong>${escapeHtml(label)}</strong>
      <div class="chip-list">
        ${values.map((value) => `<span class="chip">${escapeHtml(value)}</span>`).join("")}
      </div>
    </div>
  `;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 2800);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}
