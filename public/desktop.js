const state = {
  status: null,
  folderPath: "",
  folderName: "",
  pywebviewReady: false,
};
const FOLDER_STORAGE_KEY = "music-studio-folder-path";

const elements = {
  sessionHeroStatus: document.querySelector("#sessionHeroStatus"),
  toolHeroStatus: document.querySelector("#toolHeroStatus"),
  jobHeroStatus: document.querySelector("#jobHeroStatus"),
  authStatusText: document.querySelector("#authStatusText"),
  browserSelect: document.querySelector("#browserSelect"),
  openSignInBtn: document.querySelector("#openSignInBtn"),
  syncSessionBtn: document.querySelector("#syncSessionBtn"),
  clearSessionBtn: document.querySelector("#clearSessionBtn"),
  folderStatus: document.querySelector("#folderStatus"),
  folderDetail: document.querySelector("#folderDetail"),
  chooseFolderBtn: document.querySelector("#chooseFolderBtn"),
  saveLatestBtn: document.querySelector("#saveLatestBtn"),
  directUrls: document.querySelector("#directUrls"),
  directExtractAudio: document.querySelector("#directExtractAudio"),
  directSummary: document.querySelector("#directSummary"),
  directDownloadBtn: document.querySelector("#directDownloadBtn"),
  youtubeSummary: document.querySelector("#youtubeSummary"),
  openLikesBtn: document.querySelector("#openLikesBtn"),
  downloadLikedBtn: document.querySelector("#downloadLikedBtn"),
  progressLabel: document.querySelector("#progressLabel"),
  progressValue: document.querySelector("#progressValue"),
  progressFill: document.querySelector("#progressFill"),
  progressDetail: document.querySelector("#progressDetail"),
  syncStatus: document.querySelector("#syncStatus"),
  syncDetail: document.querySelector("#syncDetail"),
  latestDownloadSummary: document.querySelector("#latestDownloadSummary"),
  fileLinks: document.querySelector("#fileLinks"),
  logs: document.querySelector("#logs"),
  stepBrowser: document.querySelector("#stepBrowser"),
  stepFolder: document.querySelector("#stepFolder"),
  stepDownload: document.querySelector("#stepDownload"),
};

window.addEventListener("pywebviewready", () => {
  state.pywebviewReady = true;
  renderAll();
});

if (window.pywebview && window.pywebview.api) {
  state.pywebviewReady = true;
}

try {
  const storedFolderPath = window.localStorage.getItem(FOLDER_STORAGE_KEY) || "";
  if (storedFolderPath) {
    state.folderPath = storedFolderPath;
    const parts = storedFolderPath.split(/[\\/]/).filter(Boolean);
    state.folderName = parts.length ? parts[parts.length - 1] : storedFolderPath;
  }
} catch {
  state.folderPath = "";
  state.folderName = "";
}

function hasDesktopBridge() {
  return Boolean(window.pywebview && window.pywebview.api);
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : "Not yet";
}

function formatNumber(value) {
  if (typeof value !== "number") {
    return "Unknown";
  }
  return new Intl.NumberFormat().format(value);
}

function formatBytes(value) {
  if (typeof value !== "number") {
    return "";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

function parseDirectUrls(rawValue) {
  return [...new Set(
    String(rawValue || "")
      .split(/\s+/)
      .map((value) => value.trim())
      .filter(Boolean)
  )];
}

function getDirectUrls() {
  return parseDirectUrls(elements.directUrls ? elements.directUrls.value : "");
}

function getBrowserSession() {
  return state.status && state.status.browserSession
    ? state.status.browserSession
    : { imported: false, cookieCount: 0 };
}

function getLatestDownload() {
  return state.status && state.status.latestDownload ? state.status.latestDownload : null;
}

function getDownloadJob() {
  return state.status && state.status.download ? state.status.download : {};
}

function getProgress() {
  return state.status && state.status.progress ? state.status.progress : null;
}

function getLocalSave() {
  const latest = getLatestDownload();
  return latest && latest.localSave ? latest.localSave : null;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed: ${response.status}`);
  }
  return payload;
}

async function openExternal(url) {
  if (hasDesktopBridge() && typeof window.pywebview.api.open_external === "function") {
    return window.pywebview.api.open_external(url);
  }

  window.open(url, "_blank", "noopener,noreferrer");
  return true;
}

function setStepComplete(element, complete) {
  if (!element) {
    return;
  }
  element.classList.toggle("is-complete", complete);
}

function renderHero() {
  const tools = state.status && state.status.tools ? state.status.tools : {};
  const latest = getLatestDownload();
  const browserSession = getBrowserSession();
  const ytDlpAvailable = Boolean(tools.ytDlp && tools.ytDlp.available);
  const audioReady = Boolean(tools.audioExtraction && tools.audioExtraction.available);

  elements.sessionHeroStatus.textContent = browserSession.imported
    ? `${formatNumber(browserSession.cookieCount)} cookies ready`
    : "Need browser session";
  elements.toolHeroStatus.textContent = ytDlpAvailable
    ? (audioReady ? "Media + MP3 ready" : "Media ready")
    : "Unavailable";
  elements.jobHeroStatus.textContent = latest
    ? `Finished ${formatTime(latest.savedAt)}`
    : getDownloadJob().running
      ? "Running now"
      : "Waiting";
}

function renderAuth() {
  const browserSession = getBrowserSession();
  if (browserSession.imported) {
    const source = browserSession.source ? ` from ${browserSession.source}` : "";
    elements.authStatusText.textContent =
      `Browser session imported${source} at ${formatTime(browserSession.updatedAt)}. Music Studio will reuse it for protected YouTube downloads and your likes playlist.`;
    return;
  }

  elements.authStatusText.textContent =
    "Open YouTube in your normal browser, sign in there, then import the current browser session into Music Studio.";
}

function renderFolder() {
  if (state.folderPath) {
    elements.folderStatus.textContent = `Saving into "${state.folderName}" on this device.`;
    elements.folderDetail.textContent =
      "Finished files will be copied into this folder automatically whenever a job completes.";
    return;
  }

  elements.folderStatus.textContent = hasDesktopBridge()
    ? "No local folder chosen yet."
    : "Open Music Studio inside the desktop app to choose a folder.";
  elements.folderDetail.textContent = hasDesktopBridge()
    ? "Choose a folder now so Music Studio can copy completed files there."
    : "The native folder picker is only available inside the packaged desktop app.";
}

function renderDirectSummary() {
  const urls = getDirectUrls();
  if (!urls.length) {
    elements.directSummary.textContent = "Paste one or more URLs to begin.";
    return;
  }

  const folderNote = state.folderPath ? ` and save into "${state.folderName}"` : "";
  elements.directSummary.textContent =
    `${formatNumber(urls.length)} URL(s) ready${elements.directExtractAudio.checked ? " with MP3 extraction enabled" : ""}${folderNote}.`;
}

function renderYouTubeSummary() {
  const browserSession = getBrowserSession();
  elements.youtubeSummary.textContent = browserSession.imported
    ? "Your browser session is imported. Music Studio can now pull the real likes playlist locally."
    : "Import your browser session first so Music Studio can read your YouTube likes.";
}

function renderSteps() {
  const browserReady = Boolean(getBrowserSession().imported);
  const folderReady = Boolean(state.folderPath);
  const downloadStarted = Boolean(getDownloadJob().last_started_at || getLatestDownload());

  setStepComplete(elements.stepBrowser, browserReady);
  setStepComplete(elements.stepFolder, folderReady);
  setStepComplete(elements.stepDownload, downloadStarted);
}

function renderProgress() {
  const progress = getProgress();
  if (!progress) {
    elements.progressLabel.textContent = "Ready";
    elements.progressValue.textContent = "Idle";
    elements.progressDetail.textContent = "Music Studio is waiting for the next job.";
    elements.progressFill.classList.remove("is-indeterminate");
    elements.progressFill.style.width = "0%";
    return;
  }

  elements.progressLabel.textContent = progress.label || "Working...";
  elements.progressDetail.textContent = progress.detail || "Music Studio is processing your request.";

  if (typeof progress.percent === "number") {
    elements.progressValue.textContent = `${Math.round(progress.percent)}%`;
    elements.progressFill.classList.remove("is-indeterminate");
    elements.progressFill.style.width = `${Math.max(2, Math.min(100, progress.percent))}%`;
    return;
  }

  elements.progressValue.textContent = progress.running ? "Live" : "Idle";
  if (progress.running) {
    elements.progressFill.classList.add("is-indeterminate");
    elements.progressFill.style.width = "";
  } else {
    elements.progressFill.classList.remove("is-indeterminate");
    elements.progressFill.style.width = "0%";
  }
}

function renderSyncPanel() {
  const localSave = getLocalSave();
  if (localSave && localSave.folderPath) {
    elements.syncStatus.textContent = `Saved ${localSave.savedFileCount || 0} file(s) locally.`;
    elements.syncDetail.textContent = `Latest files were copied into ${localSave.folderPath} at ${formatTime(localSave.savedAt)}.`;
    return;
  }

  if (state.folderPath) {
    elements.syncStatus.textContent = `Ready to save into "${state.folderName}".`;
    elements.syncDetail.textContent = "Finished downloads will be copied into the selected folder as soon as they complete.";
    return;
  }

  elements.syncStatus.textContent = "Choose a local folder for finished files.";
  elements.syncDetail.textContent = "Music Studio can still prepare files without one, but choosing a folder keeps the flow easy for the user.";
}

function renderFiles() {
  const latest = getLatestDownload();
  if (!latest || !latest.files || !latest.files.length) {
    elements.latestDownloadSummary.textContent = "No completed job yet.";
    elements.fileLinks.className = "file-links empty-state";
    elements.fileLinks.textContent = "Finished files will appear here.";
    return;
  }

  const sourceLabel = latest.sourceKind === "youtube-liked-videos"
    ? "your YouTube likes"
    : "your pasted links";
  const localSave = latest.localSave && latest.localSave.folderPath
    ? ` They were also copied into ${latest.localSave.folderPath}.`
    : "";
  elements.latestDownloadSummary.textContent =
    `Latest job prepared ${formatNumber(latest.completedFileCount)} file(s) from ${sourceLabel} at ${formatTime(latest.savedAt)}.${localSave}`;

  elements.fileLinks.className = "file-links";
  elements.fileLinks.innerHTML = latest.files
    .map((file, index) => `
      <button type="button" class="file-pill" data-file-index="${index}">
        <strong>${escapeHtml(file.name)}</strong>
        <span>${escapeHtml(file.relativePath || file.name)}</span>
        <span>${formatBytes(file.sizeBytes)}</span>
        <em>${state.folderPath ? "Open manual download" : "Manual download"}</em>
      </button>
    `)
    .join("");
}

function renderLogs() {
  const logs = state.status && state.status.logs ? state.status.logs : [];
  if (!logs.length) {
    elements.logs.className = "logs empty-state";
    elements.logs.textContent = "Waiting for activity...";
    return;
  }

  elements.logs.className = "logs";
  elements.logs.innerHTML = logs
    .map((log) => `
      <div class="log-line ${log.kind}">
        <span class="log-time">${new Date(log.timestamp).toLocaleTimeString()}</span>
        <span class="log-message">${escapeHtml(log.message)}</span>
      </div>
    `)
    .join("");
  elements.logs.scrollTop = elements.logs.scrollHeight;
}

function syncActionButtons() {
  const tools = state.status && state.status.tools ? state.status.tools : {};
  const jobRunning = Boolean(getDownloadJob().running);
  const hasDirectUrls = getDirectUrls().length > 0;
  const latest = getLatestDownload();
  const browserSessionImported = Boolean(getBrowserSession().imported);
  const ytDlpAvailable = Boolean(tools.ytDlp && tools.ytDlp.available);

  elements.openSignInBtn.disabled = false;
  elements.openLikesBtn.disabled = false;
  elements.syncSessionBtn.disabled = jobRunning;
  elements.clearSessionBtn.disabled = jobRunning || !browserSessionImported;
  elements.chooseFolderBtn.disabled = !hasDesktopBridge();
  elements.saveLatestBtn.disabled = !latest || !latest.files || !latest.files.length || !state.folderPath;
  elements.directUrls.disabled = jobRunning;
  elements.directExtractAudio.disabled = jobRunning || !ytDlpAvailable;
  elements.directDownloadBtn.disabled = jobRunning || !ytDlpAvailable || !hasDirectUrls;
  elements.downloadLikedBtn.disabled = jobRunning || !ytDlpAvailable || !browserSessionImported;
}

function renderAll() {
  renderHero();
  renderAuth();
  renderFolder();
  renderDirectSummary();
  renderYouTubeSummary();
  renderSteps();
  renderProgress();
  renderSyncPanel();
  renderFiles();
  renderLogs();
  syncActionButtons();
}

async function refreshStatus() {
  try {
    state.status = await fetchJson("/api/status");
  } catch (error) {
    state.status = {
      tools: {},
      logs: [
        {
          kind: "error",
          message: error instanceof Error ? error.message : String(error),
          timestamp: new Date().toISOString(),
        },
      ],
      progress: {
        running: false,
        label: "Connection problem",
        detail: error instanceof Error ? error.message : String(error),
      },
    };
  }
  renderAll();
}

async function invokeAction(url, body, button, idleLabel, busyLabel) {
  const previousLabel = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    await fetchJson(url, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    await refreshStatus();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  } finally {
    button.disabled = false;
    button.textContent = idleLabel || previousLabel;
    renderAll();
  }
}

async function chooseLocalFolder() {
  if (!hasDesktopBridge() || typeof window.pywebview.api.choose_download_folder !== "function") {
    throw new Error("Open Music Studio inside the desktop app to choose a local folder.");
  }

  const folderPath = await window.pywebview.api.choose_download_folder();
  if (!folderPath) {
    return;
  }

  state.folderPath = String(folderPath);
  const parts = state.folderPath.split(/[\\/]/).filter(Boolean);
  state.folderName = parts.length ? parts[parts.length - 1] : state.folderPath;
  try {
    window.localStorage.setItem(FOLDER_STORAGE_KEY, state.folderPath);
  } catch {
    // Ignore localStorage write issues and keep the in-memory folder selection.
  }
  renderAll();
}

async function importBrowserSession() {
  const browserName = elements.browserSelect ? elements.browserSelect.value : "auto";
  const payload = await fetchJson("/api/browser-session/import", {
    method: "POST",
    body: JSON.stringify({ browserName }),
  });
  if (payload && payload.browserSession) {
    state.status = {
      ...(state.status || {}),
      browserSession: payload.browserSession,
    };
  }
  await refreshStatus();
}

elements.openSignInBtn.addEventListener("click", async () => {
  try {
    await openExternal("https://accounts.google.com/ServiceLogin?service=youtube");
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.openLikesBtn.addEventListener("click", async () => {
  try {
    await openExternal("https://www.youtube.com/playlist?list=LL");
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.syncSessionBtn.addEventListener("click", async () => {
  try {
    await importBrowserSession();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.clearSessionBtn.addEventListener("click", async () => {
  try {
    await fetchJson("/api/browser-session/clear", { method: "POST" });
    await refreshStatus();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.chooseFolderBtn.addEventListener("click", async () => {
  try {
    await chooseLocalFolder();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.saveLatestBtn.addEventListener("click", async () => {
  if (!state.folderPath) {
    try {
      await chooseLocalFolder();
    } catch (error) {
      alert(error instanceof Error ? error.message : String(error));
      return;
    }
  }

  if (!state.folderPath) {
    return;
  }

  await invokeAction(
    "/api/latest-download/save",
    { folderPath: state.folderPath },
    elements.saveLatestBtn,
    "Save Latest Files Now",
    "Saving..."
  );
});

elements.directUrls.addEventListener("input", () => {
  renderDirectSummary();
  syncActionButtons();
});

elements.directExtractAudio.addEventListener("change", () => {
  renderDirectSummary();
});

elements.directDownloadBtn.addEventListener("click", async () => {
  await invokeAction(
    "/api/direct-download",
    {
      urls: getDirectUrls(),
      extractAudio: elements.directExtractAudio.checked,
      saveFolderPath: state.folderPath || undefined,
    },
    elements.directDownloadBtn,
    "Download Pasted Links",
    "Starting..."
  );
});

elements.downloadLikedBtn.addEventListener("click", async () => {
  await invokeAction(
    "/api/youtube/download-liked",
    {
      extractAudio: elements.directExtractAudio.checked,
      saveFolderPath: state.folderPath || undefined,
    },
    elements.downloadLikedBtn,
    "Download My Likes",
    "Starting..."
  );
});

elements.fileLinks.addEventListener("click", async (event) => {
  const button = event.target instanceof Element
    ? event.target.closest("[data-file-index]")
    : null;
  const latest = getLatestDownload();
  if (!button || !latest || !latest.files) {
    return;
  }

  const index = Number(button.getAttribute("data-file-index"));
  const file = latest.files[index];
  if (!file) {
    return;
  }

  try {
    await openExternal(new URL(file.url, window.location.origin).toString());
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

await refreshStatus();
renderAll();
window.setInterval(refreshStatus, 2500);
