/**
 * Campus Lost and Found NLP System - Frontend Application Logic
 */

const API_BASE = "";

// State
let allItems = [];
let allNotifications = [];
let activeTab = "dashboard";
let currentFilterType = "all";
let currentFilterCategory = "all";
let searchResults = null;
let searchRequestId = 0;
let searchDebounceTimer = null;
let nlpDebounceTimer = null;
let nlpRequestId = 0;
let csrfToken = "";
let signedInUser = null;

// Speech Recognition instance
let recognition = null;
let isListening = false;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initSearchAndFilters();
  initReportForm();
  initNLPComparator();
  initVoiceInput();
  initGlobalActions();
  initAuth();
  restoreSession();
  setInterval(() => { if (signedInUser) fetchNotifications(); }, 15000);
});

async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && signedInUser) {
    csrfToken = "";
    showSignedOut();
  }
  return response;
}

function setAuthError(message = "") {
  const error = document.getElementById("authError");
  error.textContent = message;
  error.hidden = !message;
}

function switchAuthMode(mode) {
  const registering = mode === "register";
  document.getElementById("loginForm").hidden = registering;
  document.getElementById("registerForm").hidden = !registering;
  document.getElementById("authLoginTab").classList.toggle("active", !registering);
  document.getElementById("authRegisterTab").classList.toggle("active", registering);
  document.getElementById("authLoginTab").setAttribute("aria-selected", String(!registering));
  document.getElementById("authRegisterTab").setAttribute("aria-selected", String(registering));
  document.getElementById("authTitle").textContent = registering ? "Create your student account" : "Campus Lost & Found";
  setAuthError("");
}

function showSignedIn(user) {
  signedInUser = user;
  document.body.classList.add("authenticated");
  document.getElementById("authScreen").hidden = true;
  document.getElementById("appMain").hidden = false;
  document.getElementById("accountName").textContent = user.display_name;
  fetchAllData();
  loadSavedSearches();
}

function showSignedOut() {
  signedInUser = null;
  allItems = [];
  allNotifications = [];
  document.body.classList.remove("authenticated");
  document.getElementById("appMain").hidden = true;
  document.getElementById("authScreen").hidden = false;
  document.getElementById("accountName").textContent = "";
  document.getElementById("notificationsList").innerHTML = "";
  document.getElementById("itemsGrid").innerHTML = "";
  document.getElementById("loginForm").reset();
  document.getElementById("registerForm").reset();
  switchAuthMode("login");
}

async function restoreSession() {
  try {
    const tokenRes = await apiFetch(`${API_BASE}/api/auth/csrf`, { credentials: "same-origin" });
    const tokenData = await tokenRes.json();
    csrfToken = tokenData.csrf_token || "";
    const configRes = await apiFetch(`${API_BASE}/api/auth/config`);
    const config = await configRes.json();
    const notice = document.getElementById("authNotice");
    if (!config.registration_enabled) notice.textContent = "Student sign-up is currently disabled. Ask the project administrator to set the university email domain.";
    else notice.textContent = `Registration accepts @${config.email_domain}. Email ownership is not verified by this project demo.`;
    const res = await apiFetch(`${API_BASE}/api/auth/me`, { credentials: "same-origin" });
    const data = await res.json();
    if (res.ok && data.success) showSignedIn(data.user);
    else showSignedOut();
  } catch (error) {
    console.error("Account setup error:", error);
    showSignedOut();
    setAuthError("Could not connect to the campus server. Please try again when it is available.");
  }
}

function initAuth() {
  document.getElementById("authLoginTab").addEventListener("click", () => switchAuthMode("login"));
  document.getElementById("authRegisterTab").addEventListener("click", () => switchAuthMode("register"));
  document.getElementById("loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    setAuthError("");
    try {
      const res = await apiFetch(`${API_BASE}/api/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: document.getElementById("loginEmail").value.trim(), password: document.getElementById("loginPassword").value })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Sign in failed.");
      csrfToken = data.csrf_token;
      showSignedIn(data.user);
    } catch (error) { setAuthError(error.message); }
  });
  document.getElementById("registerForm").addEventListener("submit", async event => {
    event.preventDefault();
    setAuthError("");
    try {
      const res = await apiFetch(`${API_BASE}/api/auth/register`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: document.getElementById("registerName").value.trim(),
          email: document.getElementById("registerEmail").value.trim(),
          password: document.getElementById("registerPassword").value
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Account creation failed.");
      csrfToken = data.csrf_token;
      document.getElementById("registerForm").reset();
      showSignedIn(data.user);
    } catch (error) { setAuthError(error.message); }
  });
  document.getElementById("btnSignOut").addEventListener("click", async () => {
    try { await apiFetch(`${API_BASE}/api/auth/logout`, { method: "POST" }); } catch (error) { console.warn("Sign-out request failed:", error); }
    csrfToken = "";
    showSignedOut();
  });
}

// ==========================================================================
// Navigation & Tab Switching
// ==========================================================================

function initNavigation() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-tab");
      switchTab(target);
    });
  });
}

function switchTab(tabId) {
  if (!signedInUser) return;
  activeTab = tabId;

  // Update nav buttons
  document.querySelectorAll(".nav-tab").forEach(t => {
    t.classList.toggle("active", t.getAttribute("data-tab") === tabId);
  });

  // Update panes
  document.querySelectorAll(".tab-pane").forEach(p => {
    p.classList.toggle("active", p.id === `pane-${tabId}`);
  });

  // Lazy refresh based on tab
  if (tabId === "dashboard") {
    renderItemsFeed();
  } else if (tabId === "notifications") {
    fetchNotifications();
  } else if (tabId === "analytics") {
    fetchStats();
  }
}

// ==========================================================================
// Data Fetching
// ==========================================================================

async function fetchAllData() {
  if (!signedInUser) return;
  await Promise.all([fetchItems(), fetchNotifications(), fetchStats()]);
}

async function fetchItems() {
  try {
    const res = await apiFetch(`${API_BASE}/api/items`);
    const data = await res.json();
    if (data.success) {
      allItems = data.items;
      updateDashboardCounts();
      const activeQuery = document.getElementById("searchInput").value.trim();
      if (activeQuery) {
        runSearch(activeQuery);
      } else {
        searchResults = null;
        renderItemsFeed();
      }
    }
  } catch (err) {
    console.error("Error fetching items:", err);
    showToast("Failed to load campus items", "error");
  }
}

async function fetchNotifications() {
  try {
    const res = await apiFetch(`${API_BASE}/api/notifications`);
    const data = await res.json();
    if (data.success) {
      allNotifications = data.notifications;
      const countBadge = document.getElementById("navNotifCount");
      const statAlerts = document.getElementById("statMatchAlerts");

      countBadge.textContent = data.unread_count;
      countBadge.style.display = data.unread_count > 0 ? "inline-block" : "none";

      if (statAlerts) statAlerts.textContent = data.total;
      renderNotifications();
    }
  } catch (err) {
    console.error("Error fetching notifications:", err);
  }
}

async function fetchStats() {
  try {
    const res = await apiFetch(`${API_BASE}/api/stats`);
    const data = await res.json();
    if (data.success) {
      const stats = data.stats;
      const elTotal = document.getElementById("anTotalItems");
      const elLost = document.getElementById("anLostCount");
      const elFound = document.getElementById("anFoundCount");
      const elNotif = document.getElementById("anNotifCount");

      if (elTotal) elTotal.textContent = stats.total_items;
      if (elLost) elLost.textContent = stats.total_lost;
      if (elFound) elFound.textContent = stats.total_found;
      if (elNotif) elNotif.textContent = stats.match_notifications;
    }
  } catch (err) {
    console.error("Error fetching stats:", err);
  }
}

function updateDashboardCounts() {
  const statTotal = document.getElementById("statTotalItems");
  if (statTotal) statTotal.textContent = allItems.filter(item => item.status === "Active").length;
}

// ==========================================================================
// Search & Filter Operations
// ==========================================================================

function initSearchAndFilters() {
  const searchInput = document.getElementById("searchInput");
  const searchClear = document.getElementById("searchClear");
  const typePills = document.querySelectorAll("#typePills .pill");
  const catFilter = document.getElementById("categoryFilter");

  searchInput.addEventListener("input", (e) => {
    const val = e.target.value.trim();
    searchClear.style.display = val ? "block" : "none";

    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      runSearch(val);
    }, 280);
  });

  searchClear.addEventListener("click", () => {
    searchInput.value = "";
    searchClear.style.display = "none";
    runSearch("");
  });

  typePills.forEach(pill => {
    pill.addEventListener("click", () => {
      typePills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentFilterType = pill.getAttribute("data-type");
      renderItemsFeed();
    });
  });

  catFilter.addEventListener("change", (e) => {
    currentFilterCategory = e.target.value;
    renderItemsFeed();
  });

  document.getElementById("btnSaveSearchAlert").addEventListener("click", saveCurrentSearch);
}

async function saveCurrentSearch() {
  const query = document.getElementById("searchInput").value.trim();
  if (query.length < 3) {
    showToast("Search for an item first, then save its alert.", "error");
    return;
  }
  try {
    const res = await apiFetch(`${API_BASE}/api/saved-searches`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, type: "Lost" })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not save this search.");
    showToast(data.existing_matches ? `Alert saved — ${data.existing_matches} existing match${data.existing_matches === 1 ? "" : "es"} found.` : "Search alert saved. We’ll notify you when a matching found report is posted.", "success");
    await loadSavedSearches();
  } catch (error) { showToast(error.message, "error"); }
}

async function loadSavedSearches() {
  if (!signedInUser) return;
  try {
    const res = await apiFetch(`${API_BASE}/api/saved-searches`);
    const data = await res.json();
    if (data.success) renderSavedSearches(data.saved_searches);
  } catch (error) { console.error("Saved searches error:", error); }
}

function renderSavedSearches(searches) {
  const list = document.getElementById("savedSearchesList");
  if (!searches.length) {
    list.innerHTML = `<p class="saved-search-empty">No saved alerts yet. Search for an item above and choose “Save search alert”.</p>`;
    return;
  }
  list.innerHTML = searches.map(search => `
    <div class="saved-search-row">
      <div><strong>${escapeHtml(search.query)}</strong><small>Watching for a matching found report</small></div>
      <button class="btn btn-secondary btn-sm" type="button" onclick="deleteSavedSearch('${search.id}')">Remove</button>
    </div>
  `).join("");
}

async function deleteSavedSearch(searchId) {
  try {
    const res = await apiFetch(`${API_BASE}/api/saved-searches/${encodeURIComponent(searchId)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not remove alert.");
    await loadSavedSearches();
    showToast("Saved alert removed.", "success");
  } catch (error) { showToast(error.message, "error"); }
}

async function runSearch(query) {
  const requestId = ++searchRequestId;
  const cleanedQuery = query.trim();
  if (!cleanedQuery) {
    searchResults = null;
    fetchItems();
    return;
  }

  try {
    const res = await apiFetch(`${API_BASE}/api/items?q=${encodeURIComponent(cleanedQuery)}`);
    if (!res.ok) throw new Error(`Search failed with status ${res.status}`);
    const data = await res.json();
    if (requestId !== searchRequestId) return;
    if (data.success && Array.isArray(data.items)) {
      searchResults = data.items;
      renderItemsFeed();
    }
  } catch (err) {
    if (requestId !== searchRequestId) return;
    console.error("Search error:", err);
    showToast("Search could not be completed. Please try again.", "error");
  }
}

// ==========================================================================
// Render Dashboard Feed Grid
// ==========================================================================

function renderItemsFeed() {
  const grid = document.getElementById("itemsGrid");
  const countBadge = document.getElementById("feedCountBadge");

  let filtered = searchResults === null ? allItems : searchResults;
  if (currentFilterType !== "all") {
    filtered = filtered.filter(i => i.type.toLowerCase() === currentFilterType.toLowerCase());
  }
  if (currentFilterCategory !== "all") {
    filtered = filtered.filter(i => i.category.toLowerCase() === currentFilterCategory.toLowerCase());
  }

  countBadge.textContent = `${filtered.length} reports`;

  if (filtered.length === 0) {
    const query = document.getElementById("searchInput").value.trim();
    grid.innerHTML = `
      <div class="item-empty-state">
        <span class="empty-state-mark" aria-hidden="true">⌕</span>
        <p>${query ? `No reports found for “${escapeHtml(query)}”.` : "No reports match these filters."}</p>
        <small>Try “ID card”, “student badge”, or “charger”, or broaden the filters.</small>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map(item => {
    const isLost = item.type === "Lost";
    const badgeClass = isLost ? "tag-lost" : "tag-found";
    const badgeText = isLost ? "🔍 Lost Item" : "✨ Found Item";
    const dateStr = formatDate(item.created_at);
    const nlpEnt = item.nlp_entities || {};

    const colorChips = (nlpEnt.colors || []).map(c => `<span class="meta-chip">${c}</span>`).join("");
    const brandChips = (nlpEnt.brands || []).map(b => `<span class="meta-chip">${b}</span>`).join("");
    const conceptChip = nlpEnt.canonical_item && nlpEnt.canonical_item !== "Unspecified Item"
      ? `<span class="meta-chip chip-nlp" title="Semantic Concept">${nlpEnt.canonical_item}</span>`
      : "";

    return `
      <div class="item-card" data-id="${item.id}">
        <div>
          <div class="item-card-top">
            <span class="tag-badge ${badgeClass}">${badgeText}</span>
            <span class="item-status-pill">${item.status || "Active"}</span>
          </div>

          <h4 class="item-card-title" style="margin-top: 10px;">${escapeHtml(item.title)}</h4>
          <p class="item-card-desc" style="margin-top: 6px;">${escapeHtml(item.description)}</p>

          <div class="item-meta-chips" style="margin-top: 12px;">
            <span class="meta-chip chip-loc">📍 ${escapeHtml(item.location || "Campus")}</span>
            <span class="meta-chip">📁 ${escapeHtml(item.category || "General")}</span>
            ${conceptChip}
            ${colorChips}
            ${brandChips}
          </div>
        </div>

        <div class="item-card-footer">
          <div class="item-author-info">
            <span class="author-name">${escapeHtml(item.student_name || "Student")}</span>
            <span class="item-time">${dateStr}</span>
          </div>
          <button class="btn-match-view" onclick="openMatchesModal('${item.id}')">
            View Matches ⚡
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// ==========================================================================
// Reporting Form & Live NLP Entity Extractor
// ==========================================================================

function initReportForm() {
  const descInput = document.getElementById("reportDesc");
  const form = document.getElementById("reportForm");

  document.querySelectorAll('input[name="reportType"]').forEach(typeInput => {
    typeInput.addEventListener("change", () => {
      const requestId = ++nlpRequestId;
      const description = descInput.value.trim();
      if (description.length >= 4) checkLiveMatchesInDatabase(description, requestId);
    });
  });

  descInput.addEventListener("input", (e) => {
    const requestId = ++nlpRequestId;
    clearTimeout(nlpDebounceTimer);
    const val = e.target.value.trim();
    if (!val) {
      renderEmptyNLPLive();
      return;
    }
    nlpDebounceTimer = setTimeout(() => triggerLiveNLPAnalysis(val, requestId), 250);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await handleFormSubmit();
  });
}

async function triggerLiveNLPAnalysis(text, requestId) {
  try {
    const res = await apiFetch(`${API_BASE}/api/nlp/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    if (requestId !== nlpRequestId) return;
    if (data.success && data.analysis) {
      renderLiveNLPFeatures(data.analysis);
      checkLiveMatchesInDatabase(text, requestId);
    }
  } catch (err) {
    console.error("Live NLP analysis error:", err);
  }
}

function renderLiveNLPFeatures(analysis) {
  const container = document.getElementById("nlpLiveFeatures");
  const ent = analysis.entities || {};

  const autoCat = document.getElementById("reportCategory");
  if (ent.category && ent.category !== "General Item" && autoCat.value === "") {
    autoCat.value = ent.category;
  }

  const autoLoc = document.getElementById("reportLocation");
  if (ent.location_detail && !autoLoc.value) {
    autoLoc.value = ent.location_detail;
  }

  const synPills = (analysis.tokens || []).slice(0, 8)
    .map(t => `<span class="syn-pill">${escapeHtml(t)}</span>`).join("");

  container.innerHTML = `
    <div class="nlp-parsed-list">
      <div class="nlp-row">
        <span class="nlp-row-key">Canonical Semantic Concept:</span>
        <span class="nlp-row-val nlp-val-tag">${escapeHtml(ent.canonical_item || "General Object")}</span>
      </div>
      <div class="nlp-row">
        <span class="nlp-row-key">Predicted Category:</span>
        <span class="nlp-row-val">${escapeHtml(ent.category || "General Item")}</span>
      </div>
      <div class="nlp-row">
        <span class="nlp-row-key">Detected Colors:</span>
        <span class="nlp-row-val">${(ent.colors && ent.colors.length) ? ent.colors.join(", ") : "None specified"}</span>
      </div>
      <div class="nlp-row">
        <span class="nlp-row-key">Detected Brands:</span>
        <span class="nlp-row-val">${(ent.brands && ent.brands.length) ? ent.brands.join(", ") : "None specified"}</span>
      </div>
      <div class="nlp-row">
        <span class="nlp-row-key">Campus Zone:</span>
        <span class="nlp-row-val">${escapeHtml(ent.location_zone || "Unspecified")}</span>
      </div>
      <div>
        <span class="nlp-row-key" style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:4px;">Token Stream:</span>
        <div class="nlp-synonyms-cloud">${synPills}</div>
      </div>
    </div>
  `;
}

function renderEmptyNLPLive() {
  document.getElementById("nlpLiveFeatures").innerHTML = `
    <div class="empty-state-nlp">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path></svg>
      <p>Type in the description field to see semantic entity extraction and synonym ontology mapping in real-time.</p>
    </div>
  `;
  document.getElementById("liveMatchBox").style.display = "none";
}

// Live NLP match search, using the same counterpart scoring as submitted reports.
async function checkLiveMatchesInDatabase(text, requestId) {
  const selectedType = document.querySelector('input[name="reportType"]:checked').value;
  const liveBox = document.getElementById("liveMatchBox");
  const liveContent = document.getElementById("liveMatchContent");
  if (text.trim().length < 4) { liveBox.style.display = "none"; return; }
  try {
    const params = new URLSearchParams({ q: text, type: selectedType });
    const response = await apiFetch(`${API_BASE}/api/matches/search?${params}`);
    const data = await response.json();
    if (requestId !== nlpRequestId) return;
    const candidate = data.matches?.[0];
    if (!response.ok || !candidate) { liveBox.style.display = "none"; return; }
    const item = candidate.matched_item;
    const score = Math.round(candidate.match_data.total_score);
    liveBox.style.display = "block";
    liveContent.innerHTML = `
      <div style="font-size: 0.85rem; color: var(--text-main);">
        <strong>${escapeHtml(item.title)}</strong> reported at <em>${escapeHtml(item.location)}</em>.
        <br><span style="color: var(--accent-emerald); font-weight: 600;">${score}% NLP match</span>
        <button type="button" class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="openMatchesModal('${item.id}')">Review possible match</button>
      </div>
    `;
  } catch (error) {
    console.error("Live match search error:", error);
    liveBox.style.display = "none";
  }
}

async function handleFormSubmit() {
  const btn = document.getElementById("btnSubmitReport");
  const btnText = btn.querySelector(".btn-text");
  const spinner = btn.querySelector(".btn-spinner");

  const type = document.querySelector('input[name="reportType"]:checked').value;
  const title = document.getElementById("reportTitle").value.trim();
  const desc = document.getElementById("reportDesc").value.trim();
  const location = document.getElementById("reportLocation").value.trim();
  const category = document.getElementById("reportCategory").value;

  btnText.textContent = "Processing NLP Analysis...";
  btn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/api/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, title, description: desc, location, category })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Item reported! NLP matched against campus reports.`, "success");

      // Reset form
      document.getElementById("reportForm").reset();
      renderEmptyNLPLive();

      // Refresh items and notifications
      await fetchAllData();

      // If immediate matches were found, open modal immediately
      if (data.immediate_matches && data.immediate_matches.length > 0) {
        openMatchesModal(data.item.id);
      } else {
        switchTab("dashboard");
      }
    } else {
      showToast(data.error || "Failed to submit report", "error");
    }
  } catch (err) {
    console.error("Submission error:", err);
    showToast("Server communication error", "error");
  } finally {
    btnText.textContent = "Submit Report & Search Matches";
    btn.disabled = false;
  }
}

function fillPrompt(type, title, desc) {
  document.querySelector(`input[name="reportType"][value="${type}"]`).checked = true;
  document.getElementById("reportTitle").value = title;
  const descInput = document.getElementById("reportDesc");
  descInput.value = desc;
  descInput.dispatchEvent(new Event("input"));
}

// ==========================================================================
// Voice Input (Web Speech API)
// ==========================================================================

function initVoiceInput() {
  const btnVoice = document.getElementById("btnVoiceInput");
  const statusText = document.getElementById("voiceStatusText");
  const descInput = document.getElementById("reportDesc");

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    btnVoice.title = "Voice recognition not supported in this browser";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    isListening = true;
    btnVoice.classList.add("listening");
    statusText.textContent = "Listening...";
  };

  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    descInput.value = (descInput.value ? descInput.value + " " : "") + transcript;
    descInput.dispatchEvent(new Event("input"));
    showToast("Voice input transcribed!", "success");
  };

  recognition.onerror = (e) => {
    console.warn("Speech error:", e.error);
    isListening = false;
    btnVoice.classList.remove("listening");
    statusText.textContent = "Voice Input";
  };

  recognition.onend = () => {
    isListening = false;
    btnVoice.classList.remove("listening");
    statusText.textContent = "Voice Input";
  };

  btnVoice.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
    } else {
      try {
        recognition.start();
      } catch (err) {
        console.error("Recognition start error:", err);
      }
    }
  });
}

// ==========================================================================
// Notifications Center
// ==========================================================================

function renderNotifications() {
  const list = document.getElementById("notificationsList");
  if (!allNotifications || allNotifications.length === 0) {
    list.innerHTML = `
      <div class="card" style="text-align: center; padding: 48px 20px; color: var(--text-dim);">
        <p style="font-size: 1.1rem; margin-bottom: 6px;">No match alerts yet.</p>
        <small>We check new reports against your reports and saved searches, then add a private in-app alert for a strong match.</small>
      </div>
    `;
    return;
  }

  list.innerHTML = allNotifications.map(notif => {
    const isUnread = !notif.read;
    const dateStr = formatDate(notif.created_at);
    const score = Math.round(notif.match_score);
    const savedAlert = notif.kind === "saved_search_match";
    const targetItemId = notif.own_item_id || notif.found_item_id || notif.lost_item_id;

    return `
      <div class="notif-card ${isUnread ? 'unread' : ''}">
        <div>
          <div class="notif-header-row">
            <span class="notif-match-badge">${score}% ${escapeHtml(notif.verdict || "Match")}</span>
            <span class="notif-time">${dateStr}</span>
          </div>

          <div class="notif-comparison-preview">
            <div class="notif-item-half">
              <span style="color: #fb7185; font-weight:700;">${savedAlert ? "SAVED LOST-ITEM SEARCH" : "LOST REPORT"}</span>
              <strong>${escapeHtml(notif.lost_title)}</strong>
              <span>Reported by ${escapeHtml(notif.lost_student)}</span>
            </div>

            <div class="notif-connector">↔</div>

            <div class="notif-item-half">
              <span style="color: #34d399; font-weight:700;">FOUND REPORT</span>
              <strong>${escapeHtml(notif.found_title)}</strong>
              <span>Found by ${escapeHtml(notif.found_student)}</span>
            </div>
          </div>

            <div style="margin-top: 10px; font-size: 0.8rem; color: var(--text-muted);">
            <strong>NLP reason:</strong> ${escapeHtml(notif.breakdown?.cluster_explanation || "High semantic text similarity")}
          </div>
          ${notif.other_contact ? `<a class="btn btn-secondary btn-sm" style="margin-top:10px" href="mailto:${escapeHtml(notif.other_contact)}?subject=${encodeURIComponent("Campus Lost and Found match")}">Contact report owner</a>` : ""}
        </div>

        <div class="notif-score-box">
          <span class="notif-score-num">${score}%</span>
          <span class="notif-score-lbl">Match Score</span>
          <button class="btn btn-secondary btn-sm" style="margin-top: 10px; width: 100%;" onclick="openMatchesModal('${targetItemId}')">
            View Details
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// ==========================================================================
// Matches Modal
// ==========================================================================

async function openMatchesModal(itemId) {
  const modal = document.getElementById("matchesModal");
  const targetSummary = document.getElementById("modalTargetSummary");
  const matchesList = document.getElementById("modalMatchesList");
  const countBadge = document.getElementById("modalMatchesCount");

  modal.style.display = "flex";
  matchesList.innerHTML = `<div style="text-align: center; padding: 24px; color: var(--text-dim);">Running NLP Semantic Matching...</div>`;

  try {
    const res = await apiFetch(`${API_BASE}/api/items/${itemId}/matches`);
    const data = await res.json();
    if (data.success) {
      const target = data.target_item;
      const matches = data.matches;

      document.getElementById("modalTargetTitle").textContent = target.title;
      document.getElementById("modalTargetSubtitle").textContent = `${target.type} Item Analysis`;

      targetSummary.innerHTML = `
        <div style="font-size: 0.9rem;">
          <p style="color: #fff; margin-bottom: 6px;">"${escapeHtml(target.description)}"</p>
          <div style="display: flex; gap: 14px; font-size: 0.78rem; color: var(--text-muted);">
            <span>📍 ${escapeHtml(target.location)}</span>
            <span>📁 ${escapeHtml(target.category)}</span>
            <span>👤 ${escapeHtml(target.student_name)}</span>
          </div>
        </div>
      `;

      countBadge.textContent = `${matches.length} candidate matches`;

      if (matches.length === 0) {
        matchesList.innerHTML = `
          <div style="text-align: center; padding: 30px; color: var(--text-dim);">
            No counter-part items found with high semantic similarity yet.
          </div>
        `;
        return;
      }

      matchesList.innerHTML = matches.map(m => {
        const itm = m.matched_item;
        const md = m.match_data;
        const score = md.total_score;
        const bd = md.breakdown;

        return `
          <div class="modal-match-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <div>
                <span class="tag-badge ${itm.type === 'Lost' ? 'tag-lost' : 'tag-found'}">${itm.type}</span>
                <strong style="color: #fff; font-size: 1.05rem; margin-left: 8px;">${escapeHtml(itm.title)}</strong>
              </div>
              <span style="font-size: 1.3rem; font-weight: 800; font-family: var(--font-mono); color: var(--accent-emerald);">
                ${score}%
              </span>
            </div>

            <p style="font-size: 0.86rem; color: var(--text-muted); line-height: 1.4;">
              "${escapeHtml(itm.description)}"
            </p>

            <div style="background: rgba(10, 15, 26, 0.5); padding: 10px 12px; border-radius: 6px; font-size: 0.78rem; display: flex; flex-direction: column; gap: 4px;">
              <div><strong>Semantic Explanation:</strong> ${escapeHtml(bd.cluster_explanation)}</div>
              <div><strong>Location Alignment:</strong> ${escapeHtml(bd.location_explanation)}</div>
              <div><strong>Report owner:</strong> ${escapeHtml(itm.student_name)}</div>
            </div>

            <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px;">
              ${itm.student_contact ? `<a class="btn btn-secondary btn-sm" href="mailto:${escapeHtml(itm.student_contact)}?subject=${encodeURIComponent("Campus Lost and Found match")}">Contact report owner</a>` : ""}
              ${target.can_resolve ? `<button class="btn btn-primary btn-sm" onclick="resolveItemMatch('${target.id}', '${itm.id}', '${target.type}', '${itm.type}')">Mark reunited</button>` : ""}
            </div>
          </div>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Matches error:", err);
    matchesList.innerHTML = `<div style="color: var(--accent-rose); padding: 20px;">Failed to load matches</div>`;
  }
}

function closeMatchesModal() {
  document.getElementById("matchesModal").style.display = "none";
}

async function resolveItemMatch(itemId1, itemId2, type1, type2) {
  try {
    const pair = type1 === "Lost"
      ? { lost_item_id: itemId1, found_item_id: itemId2 }
      : { lost_item_id: itemId2, found_item_id: itemId1 };
    const response = await apiFetch(`${API_BASE}/api/matches/resolve`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pair)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to resolve this match.");
    showToast("Items marked as Reunited & Resolved!", "success");
    closeMatchesModal();
    fetchAllData();
  } catch (err) {
    showToast("Failed to resolve item", "error");
  }
}

// ==========================================================================
// Interactive NLP Laboratory
// ==========================================================================

const LAB_PRESETS = {
  1: {
    t1: "Charger is missing, black color 65W with USB-C cable.",
    loc1: "Central Library",
    t2: "Charging adapter has been found in library near reading table 12 on ground floor.",
    loc2: "Central Library"
  },
  2: {
    t1: "Lost my reading specs with dark brown rectangular frame during morning lecture in CS block.",
    loc1: "Academic Block",
    t2: "Found spectacles with brown frame left behind on desk in classroom 302 of CS department.",
    loc2: "Academic Block"
  },
  3: {
    t1: "Misplaced my white airpods pro in the cafeteria near nescafe stall during lunch.",
    loc1: "Cafeteria",
    t2: "Discovered wireless earbuds with white charging pod sitting on canteen table.",
    loc2: "Cafeteria"
  },
  4: {
    t1: "Left my dark blue hydro flask metal water bottle near badminton court bench.",
    loc1: "Sports Complex",
    t2: "Found a blue steel water bottle / tumbler at sports ground pavilion.",
    loc2: "Sports Complex"
  },
  5: {
    t1: "Lost my blue water bottle near library reading hall.",
    loc1: "Central Library",
    t2: "Found charging adapter in library near reference section.",
    loc2: "Central Library"
  }
};

function initNLPComparator() {
  const btn = document.getElementById("btnRunLabCompare");
  btn.addEventListener("click", () => {
    runLabComparison();
  });
}

function loadLabPreset(presetId) {
  const p = LAB_PRESETS[presetId];
  if (!p) return;

  document.getElementById("labText1").value = p.t1;
  document.getElementById("labLoc1").value = p.loc1;
  document.getElementById("labText2").value = p.t2;
  document.getElementById("labLoc2").value = p.loc2;

  runLabComparison();
}

async function runLabComparison() {
  const t1 = document.getElementById("labText1").value.trim();
  const loc1 = document.getElementById("labLoc1").value.trim();
  const t2 = document.getElementById("labText2").value.trim();
  const loc2 = document.getElementById("labLoc2").value.trim();

  if (!t1 || !t2) {
    showToast("Please enter both Description A and Description B", "error");
    return;
  }

  const btn = document.getElementById("btnRunLabCompare");
  btn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/api/nlp/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text1: t1, text2: t2, loc1, loc2 })
    });

    const data = await res.json();
    if (data.success) {
      renderLabResults(data.result);
    }
  } catch (err) {
    console.error("Lab compare error:", err);
    showToast("Failed to run comparison", "error");
  } finally {
    btn.disabled = false;
  }
}

function renderLabResults(res) {
  const card = document.getElementById("labResultCard");
  card.style.display = "block";

  const score = Math.round(res.total_score);
  const bd = res.breakdown;
  const ent1 = res.entities_1;
  const ent2 = res.entities_2;

  // Verdict Banner
  const vBanner = document.getElementById("labVerdictBanner");
  const vBadge = document.getElementById("labVerdictBadge");
  const vText = document.getElementById("labVerdictText");
  const gauge = document.getElementById("labScoreGauge");
  const gaugeVal = document.getElementById("labGaugeValue");

  gauge.style.setProperty("--gauge-pct", score);
  gaugeVal.textContent = `${score}%`;
  vText.textContent = `${res.total_score}% Semantic Similarity Score`;
  vBadge.textContent = res.verdict;

  if (score >= 75) {
    vBadge.className = "verdict-badge status-exact";
  } else if (score >= 50) {
    vBadge.className = "verdict-badge status-partial";
  } else {
    vBadge.className = "verdict-badge status-mismatch";
  }

  // Metric Bars
  document.getElementById("valTextSim").textContent = `${bd.text_similarity_score}%`;
  document.getElementById("fillProgText").style.width = `${bd.text_similarity_score}%`;

  document.getElementById("valCluster").textContent = `${bd.cluster_score}%`;
  document.getElementById("fillProgCluster").style.width = `${bd.cluster_score}%`;
  document.getElementById("explCluster").textContent = bd.cluster_explanation;

  document.getElementById("valLocation").textContent = `${bd.location_score}%`;
  document.getElementById("fillProgLocation").style.width = `${bd.location_score}%`;
  document.getElementById("explLocation").textContent = bd.location_explanation;

  document.getElementById("valAttr").textContent = `${bd.attribute_score}%`;
  document.getElementById("fillProgAttr").style.width = `${bd.attribute_score}%`;
  document.getElementById("explAttr").textContent = bd.attribute_explanation;

  // Comparison Table
  const tbody = document.getElementById("entityTableBody");
  tbody.innerHTML = `
    <tr>
      <td><strong>Canonical Object Concept</strong></td>
      <td>${escapeHtml(ent1.canonical_item || "Unspecified")}</td>
      <td>${escapeHtml(ent2.canonical_item || "Unspecified")}</td>
      <td>${getStatusPill(ent1.item_cluster === ent2.item_cluster && ent1.item_cluster !== null)}</td>
    </tr>
    <tr>
      <td><strong>Category Classification</strong></td>
      <td>${escapeHtml(ent1.category || "General")}</td>
      <td>${escapeHtml(ent2.category || "General")}</td>
      <td>${getStatusPill(ent1.category === ent2.category && ent1.category !== "General Item")}</td>
    </tr>
    <tr>
      <td><strong>Detected Colors</strong></td>
      <td>${(ent1.colors || []).join(", ") || "None"}</td>
      <td>${(ent2.colors || []).join(", ") || "None"}</td>
      <td>${getColorMatchStatus(ent1.colors, ent2.colors)}</td>
    </tr>
    <tr>
      <td><strong>Campus Location Zone</strong></td>
      <td>${escapeHtml(ent1.location_zone || "Campus")}</td>
      <td>${escapeHtml(ent2.location_zone || "Campus")}</td>
      <td>${getStatusPill(ent1.location_zone === ent2.location_zone && ent1.location_zone !== "Unknown Campus Zone")}</td>
    </tr>
  `;

  // Scroll smoothly to results
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function getStatusPill(matched) {
  if (matched) {
    return `<span class="match-status-pill status-exact">Exact Match</span>`;
  }
  return `<span class="match-status-pill status-mismatch">Difference</span>`;
}

function getColorMatchStatus(c1, c2) {
  const set1 = new Set(c1 || []);
  const set2 = new Set(c2 || []);
  const intersection = [...set1].filter(x => set2.has(x));
  if (intersection.length > 0) {
    return `<span class="match-status-pill status-exact">Matches (${intersection.join(", ")})</span>`;
  }
  if (set1.size === 0 || set2.size === 0) {
    return `<span class="match-status-pill status-partial">Neutral (Unspecified)</span>`;
  }
  return `<span class="match-status-pill status-mismatch">Mismatch</span>`;
}

// ==========================================================================
// Global Actions
// ==========================================================================

function initGlobalActions() {
  const btnMarkRead = document.getElementById("btnMarkAllRead");
  if (btnMarkRead) {
    btnMarkRead.addEventListener("click", async () => {
      try {
        await apiFetch(`${API_BASE}/api/notifications/mark-read`, { method: "POST" });
        showToast("All notifications marked as read", "success");
        fetchNotifications();
      } catch (err) {
        showToast("Failed to mark notifications read", "error");
      }
    });
  }

  // Close modal on click outside
  const modal = document.getElementById("matchesModal");
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeMatchesModal();
  });
}

function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : '⚠️'}</span>
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(40px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

function formatDate(isoStr) {
  if (!isoStr) return "Recently";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "Recently";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
