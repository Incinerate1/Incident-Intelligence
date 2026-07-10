// Dynamic Multi-Cloud API Endpoint Routing (`Phase 6: Vercel & Railway`)
const API_BASE = window.API_BASE_URL || (
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000/api/v1"
    : "/api/v1"
);

// Dynamic Atlassian Cloud Base URL (`settings.atlassian_cloud_url` from backend)
let ATLASSIAN_CLOUD_URL = window.ATLASSIAN_CLOUD_URL || "https://amanshende652.atlassian.net/";

// Fetch health check on app load to get active Atlassian Cloud URL from backend
async function fetchAtlassianConfig() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      if (data.atlassian_cloud_url) {
        ATLASSIAN_CLOUD_URL = data.atlassian_cloud_url;
      }
    }
  } catch (e) {
    console.warn("Could not fetch atlassian_cloud_url from health endpoint, using default:", e);
  }
}
fetchAtlassianConfig();

// Helper to construct full clickable Atlassian Jira URL (`browse/KEY` or `KEY`)
function getJiraIssueUrl(ticketRef) {
  if (!ticketRef) return "#";
  const refStr = String(ticketRef).trim();
  if (refStr.startsWith("http://") || refStr.startsWith("https://")) {
    return refStr;
  }
  const baseUrl = ATLASSIAN_CLOUD_URL.replace(/\/+$/, "");
  if (refStr.startsWith("browse/")) {
    return `${baseUrl}/${refStr}`;
  }
  return `${baseUrl}/browse/${refStr}`;
}

// Open Atlassian Jira issue in new tab
function openAtlassianJira(ticketRef, event) {
  if (event) event.preventDefault();
  const targetUrl = getJiraIssueUrl(ticketRef);
  window.open(targetUrl, "_blank", "noopener,noreferrer");
}


// Tab navigation
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

  if (tabId === 'triage') {
    document.querySelectorAll('.tab-btn')[0].classList.add('active');
    document.getElementById('triage-tab').classList.add('active');
  } else {
    document.querySelectorAll('.tab-btn')[1].classList.add('active');
    document.getElementById('summary-tab').classList.add('active');
    loadWeeklySummary();
  }
}

// Quick Sample input
function insertSample(text) {
  document.getElementById('alert-trace-input').value = text;
}

// Execute Triage (`Step 4.2`)
async function executeTriage() {
  const alertTrace = document.getElementById('alert-trace-input').value.trim();
  if (alertTrace.length < 10) {
    alert("EC-1.2 Query Ambiguity: Please enter at least 10 characters of alert trace or exception header.");
    return;
  }

  const resultCard = document.getElementById('triage-result-card');
  const loading = document.getElementById('triage-loading');
  const warningBanner = document.getElementById('status-warning-banner');
  const submitBtn = document.getElementById('triage-submit-btn');

  resultCard.style.display = 'none';
  warningBanner.style.display = 'none';
  loading.style.display = 'block';
  submitBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/triage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alert_trace: alertTrace })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || "Triage pipeline error");
    }

    const data = await res.json();
    renderTriageCard(data.pattern, data.meta);
  } catch (err) {
    alert(`Triage Error: ${err.message}`);
  } finally {
    loading.style.display = 'none';
    submitBtn.disabled = false;
  }
}

// Render Triage Card (`Step 4.2`)
function renderTriageCard(pattern, meta) {
  const resultCard = document.getElementById('triage-result-card');
  const warningBanner = document.getElementById('status-warning-banner');
  const warningText = document.getElementById('warning-banner-text');

  // Status & Warning Banner (`EC-2.1`, `EC-3.1`, `EC-4.1`)
  if (pattern.warning_message) {
    warningText.innerText = pattern.warning_message;
    warningBanner.style.display = 'flex';
  } else {
    warningBanner.style.display = 'none';
  }

  // Status Badge
  const badge = document.getElementById('card-status-badge');
  badge.innerText = pattern.status;
  badge.className = `status-badge badge-${pattern.status}`;

  // SLA Latency Badge
  document.getElementById('card-sla-badge').innerText = `SLA Latency: ${meta?.elapsed_seconds || 0.45}s (Target: < 15.0s)`;

  // Main Fields
  document.getElementById('card-precursor-text').innerText = pattern.precursor_condition || "N/A";
  document.getElementById('card-owner-text').innerText = pattern.escalation_owner || "Unassigned";
  document.getElementById('card-recurrence-text').innerText = pattern.summary_stats || `${pattern.pattern_count} historical matches`;
  document.getElementById('card-daterange-text').innerText = pattern.date_range || "N/A";

  // Clickable Tickets (`browse/CREP-104`)
  const ticketsContainer = document.getElementById('tickets-container');
  const ticketsList = document.getElementById('tickets-links-list');
  ticketsList.innerHTML = "";

  if (pattern.matched_tickets && pattern.matched_tickets.length > 0) {
    pattern.matched_tickets.forEach(url => {
      const link = document.createElement('a');
      link.className = 'ticket-link';
      const targetUrl = getJiraIssueUrl(url);
      link.href = targetUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.innerText = url;
      link.onclick = (e) => openAtlassianJira(url, e);
      ticketsList.appendChild(link);
    });
    ticketsContainer.style.display = 'block';
  } else {
    ticketsContainer.style.display = 'none';
  }

  // Resolution Steps (`EC-4.2`)
  const resContainer = document.getElementById('resolution-steps-container');
  const resPre = document.getElementById('card-resolution-steps');
  if (pattern.resolution_steps) {
    resPre.innerText = pattern.resolution_steps;
    resContainer.style.display = 'block';
  } else {
    resContainer.style.display = 'none';
  }

  resultCard.style.display = 'block';
}

// Modal handling
function openCaptureModal() {
  document.getElementById('modal-validation-error').style.display = 'none';
  const alertTrace = document.getElementById('alert-trace-input').value.trim();
  if (alertTrace && !document.getElementById('modal-alert-signature').value) {
    document.getElementById('modal-alert-signature').value = alertTrace.substring(0, 80);
  }
  document.getElementById('capture-modal').classList.add('active');
}

function closeCaptureModal() {
  document.getElementById('capture-modal').classList.remove('active');
}

// Submit Resolution (`EC-5.1`, `EC-5.2`, `EC-5.3`)
async function submitResolution() {
  const alertSignature = document.getElementById('modal-alert-signature').value.trim();
  const precursor = document.getElementById('modal-precursor').value.trim();
  const narrative = document.getElementById('modal-resolution').value.trim();
  const owner = document.getElementById('modal-owner').value.trim() || "Unassigned";
  const issueKey = document.getElementById('modal-issue-key').value.trim() || null;

  const errorBox = document.getElementById('modal-validation-error');
  errorBox.style.display = 'none';

  // Client-side quick check
  if (alertSignature.length < 10 || precursor.length < 15 || narrative.length < 30) {
    errorBox.innerHTML = `<strong>Validation Error (\`EC-5.3\`):</strong><br>` +
      `• Alert Signature must be min 10 chars (${alertSignature.length}/10)<br>` +
      `• Precursor Condition must be min 15 chars (${precursor.length}/15)<br>` +
      `• Resolution Narrative must be min 30 chars (${narrative.length}/30)`;
    errorBox.style.display = 'block';
    return;
  }

  const payload = {
    alert_signature: alertSignature,
    precursor_condition: precursor,
    resolution_narrative: narrative,
    escalation_owner: owner,
    existing_issue_key: issueKey
  };

  const submitBtn = document.getElementById('modal-submit-btn');
  submitBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/capture-resolution`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    // Intercept 422 Unprocessable Entity (`EC-5.3`)
    if (res.status === 422) {
      const errData = await res.json();
      errorBox.innerHTML = `<strong>Pydantic v2 Validation Rejected (\`EC-5.3\`):</strong><br>` +
        (errData.details || [errData.message]).join("<br>");
      errorBox.style.display = 'block';
      return;
    }

    if (!res.ok) {
      throw new Error("Failed to capture resolution");
    }

    const data = await res.json();
    closeCaptureModal();

    // Show Toast (`EC-5.1`, `EC-5.2`)
    const toast = document.getElementById('toast-message');
    const toastText = document.getElementById('toast-text');
    
    if (data.status === "DUPLICATE_DEDUPLICATED") {
      toastText.innerText = `⚠️ Deduplicated against recent write-back ${data.kb_id} (\`EC-5.1\`)!`;
      toast.style.backgroundColor = "#d29922";
    } else if (data.status === "LOCAL_FALLBACK_SAVED") {
      toastText.innerText = `⚠️ Saved directly to local store (\`sync_status=PENDING_JIRA_SYNC\`) (\`EC-5.2\`)`;
      toast.style.backgroundColor = "#d29922";
    } else {
      toastText.innerText = `✅ Resolution Documented & Indexed via Atlassian MCP! (${data.kb_id})`;
      toast.style.backgroundColor = "#238636";
    }

    toast.classList.add('active');
    setTimeout(() => { toast.classList.remove('active'); }, 5000);
  } catch (err) {
    errorBox.innerText = `Error: ${err.message}`;
    errorBox.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
  }
}

// Load Shift Manager Weekly Summary (`Step 4.3`)
async function loadWeeklySummary() {
  const project = document.getElementById('summary-project-select').value;
  const days = document.getElementById('summary-days-select').value;

  const loading = document.getElementById('summary-loading');
  const grid = document.getElementById('summary-grid');

  grid.style.display = 'none';
  loading.style.display = 'block';

  try {
    const res = await fetch(`${API_BASE}/weekly-summary?project=${project}&days=${days}`);
    const data = await res.json();

    grid.innerHTML = "";
    if (data.clusters && data.clusters.length > 0) {
      data.clusters.forEach((cluster, idx) => {
        const card = document.createElement('div');
        card.className = 'cluster-card';
        card.innerHTML = `
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
              <span style="font-weight: 700; color: var(--accent-blue);">#${idx + 1} Alert Frequency</span>
              <span class="freq-badge">${cluster.frequency_count} incidents</span>
            </div>
            <h3>${cluster.cluster_title}</h3>
            <p style="color: var(--text-main); font-size: 0.95rem; margin-bottom: 1rem;">${cluster.dominant_root_cause}</p>
          </div>
          <div>
            <div style="font-size: 0.85rem; color: #bc8cff; margin-bottom: 0.75rem;">
              <strong>Primary Assignees:</strong> ${(cluster.affected_assignees || []).join(", ") || "Unassigned"}
            </div>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
              ${(cluster.sample_tickets || []).map(t => {
                const targetUrl = getJiraIssueUrl(t);
                return `<a class="ticket-link" href="${targetUrl}" target="_blank" rel="noopener noreferrer" onclick="openAtlassianJira('${t}', event)">${t}</a>`;
              }).join("")}
            </div>
          </div>
        `;
        grid.appendChild(card);
      });
    } else {
      grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">No recurring incident clusters found for [${project}] over the last ${days} days.</div>`;
    }
    grid.style.display = 'grid';
  } catch (err) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--status-red);">Error loading weekly summary: ${err.message}</div>`;
    grid.style.display = 'grid';
  } finally {
    loading.style.display = 'none';
  }
}
