/* ==========================================================================
   Pulse — Sentiment Analyzer frontend logic
   ========================================================================== */

const API = {
  analyze: "/api/analyze",
  analyzeBulk: "/api/analyze/bulk",
  results: "/api/results",
  dashboard: "/api/dashboard",
};

const state = {
  resultsPage: 1,
  resultsLimit: 10,
  resultsFilter: "all",
  pieChart: null,
  barChart: null,
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function qs(selector, scope = document) {
  return scope.querySelector(selector);
}

function showToast(message, isError = false) {
  const toast = qs("#toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.hidden = false;
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => { toast.hidden = true; }, 3800);
}

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

function formatWhen(isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "—";
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function sentimentClass(sentiment) {
  if (!sentiment) return "neutral";
  return sentiment.toLowerCase();
}

async function apiRequest(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (networkErr) {
    throw new Error("Could not reach the server. Is Flask running?");
  }

  let payload;
  try {
    payload = await response.json();
  } catch (parseErr) {
    throw new Error("The server returned an unexpected response.");
  }

  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || `Request failed (${response.status}).`);
  }
  return payload;
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");

      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("is-active"));
      qs(`#panel-${btn.dataset.tab}`).classList.add("is-active");

      if (btn.dataset.tab === "dashboard") {
        loadDashboard();
        loadResultsTable();
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Single analyze
// ---------------------------------------------------------------------------

function renderSingleResult(data) {
  const el = qs("#single-result");
  const cls = sentimentClass(data.sentiment);
  const scores = data.scores || {};

  const rows = ["Positive", "Neutral", "Negative"]
    .map((label) => {
      const value = scores[label] ?? 0;
      const rowCls = label.toLowerCase();
      return `
        <div class="score-bar-row">
          <span>${label}</span>
          <div class="score-bar-track">
            <div class="score-bar-fill score-bar-fill--${rowCls}" style="width:${Math.round(value * 100)}%"></div>
          </div>
          <span>${formatPercent(value)}</span>
        </div>`;
    })
    .join("");

  el.classList.remove("result-card--empty");
  el.innerHTML = `
    <div class="result-headline">
      <span class="sentiment-pill sentiment-pill--${cls}">${data.sentiment}</span>
      <span class="confidence-figure">${formatPercent(data.confidence)}<span> confidence</span></span>
    </div>
    <div class="score-bars">${rows}</div>
  `;
}

function initSingleForm() {
  const form = qs("#single-form");
  const textarea = qs("#single-text");
  const charCount = qs("#single-char-count");
  const submitBtn = qs("#single-submit");
  const errorBox = qs("#single-error");

  textarea.addEventListener("input", () => {
    charCount.textContent = `${textarea.value.length} / 10,000`;
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;

    const text = textarea.value.trim();
    if (!text) {
      errorBox.textContent = "Please enter some text to analyze.";
      errorBox.hidden = false;
      return;
    }

    submitBtn.disabled = true;
    submitBtn.querySelector(".btn-label").textContent = "Analyzing…";

    try {
      const payload = await apiRequest(API.analyze, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      renderSingleResult(payload.data);
      if (payload.warning) showToast(payload.warning, true);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.querySelector(".btn-label").textContent = "Analyze sentiment";
    }
  });
}

// ---------------------------------------------------------------------------
// Bulk analyze
// ---------------------------------------------------------------------------

function renderBulkResults(payload) {
  const summaryEl = qs("#bulk-summary");
  const resultsEl = qs("#bulk-results");
  const s = payload.summary;

  summaryEl.hidden = false;
  summaryEl.innerHTML = `
    <span class="bulk-summary-chip">${s.total_submitted} submitted</span>
    <span class="bulk-summary-chip">${s.analyzed} analyzed</span>
    <span class="bulk-summary-chip">${s.saved} saved</span>
    ${s.failed ? `<span class="bulk-summary-chip">${s.failed} failed</span>` : ""}
  `;

  if (!payload.results.length) {
    resultsEl.innerHTML = `<p class="empty-note">No results.</p>`;
    return;
  }

  resultsEl.innerHTML = payload.results
    .map((r) => {
      if (r.error) {
        return `
          <div class="bulk-row">
            <div class="bulk-row-text">
              ${escapeHtml(r.text || "(empty)")}
              <div class="bulk-row-error">${escapeHtml(r.error)}</div>
            </div>
          </div>`;
      }
      const cls = sentimentClass(r.sentiment);
      return `
        <div class="bulk-row">
          <span class="sentiment-pill sentiment-pill--${cls}">${r.sentiment}</span>
          <div class="bulk-row-text">${escapeHtml(r.text)}</div>
          <span class="char-count">${formatPercent(r.confidence)}</span>
        </div>`;
    })
    .join("");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function initBulkForm() {
  const form = qs("#bulk-form");
  const fileInput = qs("#bulk-file");
  const dropzone = qs("#bulk-dropzone");
  const filenameEl = qs("#bulk-filename");
  const textarea = qs("#bulk-text");
  const submitBtn = qs("#bulk-submit");
  const errorBox = qs("#bulk-error");

  fileInput.addEventListener("change", () => {
    filenameEl.textContent = fileInput.files.length ? fileInput.files[0].name : "";
  });

  ["dragover", "dragenter"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      filenameEl.textContent = e.dataTransfer.files[0].name;
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;

    const hasFile = fileInput.files.length > 0;
    const lines = textarea.value
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

    if (!hasFile && lines.length === 0) {
      errorBox.textContent = "Choose a file or paste at least one line of text.";
      errorBox.hidden = false;
      return;
    }

    submitBtn.disabled = true;
    submitBtn.querySelector(".btn-label").textContent = "Analyzing…";

    try {
      let payload;
      if (hasFile) {
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        payload = await apiRequest(API.analyzeBulk, { method: "POST", body: formData });
      } else {
        payload = await apiRequest(API.analyzeBulk, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texts: lines }),
        });
      }
      renderBulkResults(payload);
      showToast(`Analyzed ${payload.summary.analyzed} of ${payload.summary.total_submitted} entries.`);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.querySelector(".btn-label").textContent = "Analyze all";
    }
  });
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function loadDashboard() {
  try {
    const payload = await apiRequest(API.dashboard);
    const data = payload.data;

    qs("#stat-total").textContent = data.total_reviews;
    qs("#stat-positive").textContent = `${data.sentiments.Positive.percentage}%`;
    qs("#stat-negative").textContent = `${data.sentiments.Negative.percentage}%`;
    qs("#stat-neutral").textContent = `${data.sentiments.Neutral.percentage}%`;

    renderPieChart(data.sentiments);
    renderBarChart(data.sentiments);
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderPieChart(sentiments) {
  const ctx = qs("#pie-chart");
  const values = [sentiments.Positive.count, sentiments.Negative.count, sentiments.Neutral.count];

  if (state.pieChart) {
    state.pieChart.data.datasets[0].data = values;
    state.pieChart.update();
    return;
  }

  state.pieChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Positive", "Negative", "Neutral"],
      datasets: [
        {
          data: values,
          backgroundColor: ["#5AA575", "#C1502E", "#A69A7C"],
          borderColor: "#1C2325",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#ECE7DA", font: { family: "Inter", size: 12.5 }, padding: 16 },
        },
      },
    },
  });
}

function renderBarChart(sentiments) {
  const ctx = qs("#bar-chart");
  const values = [
    Math.round(sentiments.Positive.avg_confidence * 100),
    Math.round(sentiments.Negative.avg_confidence * 100),
    Math.round(sentiments.Neutral.avg_confidence * 100),
  ];

  if (state.barChart) {
    state.barChart.data.datasets[0].data = values;
    state.barChart.update();
    return;
  }

  state.barChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Positive", "Negative", "Neutral"],
      datasets: [
        {
          data: values,
          backgroundColor: ["#5AA575", "#C1502E", "#A69A7C"],
          borderRadius: 6,
          maxBarThickness: 56,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: "#9BA6A2", callback: (v) => `${v}%` },
          grid: { color: "#303939" },
        },
        x: {
          ticks: { color: "#ECE7DA" },
          grid: { display: false },
        },
      },
    },
  });
}

async function loadResultsTable() {
  const tbody = qs("#results-tbody");
  tbody.innerHTML = `<tr><td colspan="4" class="empty-note">Loading…</td></tr>`;

  try {
    const url = `${API.results}?page=${state.resultsPage}&limit=${state.resultsLimit}&sentiment=${state.resultsFilter}`;
    const payload = await apiRequest(url);
    const { data, pagination } = payload;

    if (!data.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-note">No results yet — analyze something first.</td></tr>`;
    } else {
      tbody.innerHTML = data
        .map(
          (r) => `
        <tr>
          <td><div class="cell-text">${escapeHtml(r.text)}</div></td>
          <td><span class="sentiment-pill sentiment-pill--${sentimentClass(r.sentiment)}">${r.sentiment}</span></td>
          <td>${formatPercent(r.confidence)}</td>
          <td class="cell-when">${formatWhen(r.created_at)}</td>
        </tr>`
        )
        .join("");
    }

    renderPagination(pagination);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-note">${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderPagination(pagination) {
  const el = qs("#pagination");
  const { page, total_pages } = pagination;
  if (total_pages <= 1) {
    el.innerHTML = "";
    return;
  }

  let html = `<button ${page <= 1 ? "disabled" : ""} data-page="${page - 1}">Prev</button>`;
  for (let p = 1; p <= total_pages; p++) {
    if (p === 1 || p === total_pages || Math.abs(p - page) <= 1) {
      html += `<button class="${p === page ? "is-active" : ""}" data-page="${p}">${p}</button>`;
    } else if (Math.abs(p - page) === 2) {
      html += `<span class="char-count">…</span>`;
    }
  }
  html += `<button ${page >= total_pages ? "disabled" : ""} data-page="${page + 1}">Next</button>`;
  el.innerHTML = html;

  el.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.resultsPage = Number(btn.dataset.page);
      loadResultsTable();
    });
  });
}

function initDashboardControls() {
  qs("#refresh-dashboard").addEventListener("click", () => {
    loadDashboard();
    loadResultsTable();
  });
  qs("#results-filter").addEventListener("change", (e) => {
    state.resultsFilter = e.target.value;
    state.resultsPage = 1;
    loadResultsTable();
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initSingleForm();
  initBulkForm();
  initDashboardControls();
  loadDashboard();
  loadResultsTable();
});
