const state = {
  status: null,
  folderHandle: null,
  folderName: '',
  sync: {
    running: false,
    completedRunId: null,
    failedRunId: null,
    status: 'Waiting for a completed download job.',
    detail: 'Choose a local folder so Music Studio can save finished files automatically when the server job completes.',
  },
};

const elements = {
  authHeroStatus: document.querySelector('#authHeroStatus'),
  toolHeroStatus: document.querySelector('#toolHeroStatus'),
  jobHeroStatus: document.querySelector('#jobHeroStatus'),
  authStatusText: document.querySelector('#authStatusText'),
  authSignInBtn: document.querySelector('#authSignInBtn'),
  authSignOutBtn: document.querySelector('#authSignOutBtn'),
  folderStatus: document.querySelector('#folderStatus'),
  folderDetail: document.querySelector('#folderDetail'),
  chooseFolderBtn: document.querySelector('#chooseFolderBtn'),
  saveLatestBtn: document.querySelector('#saveLatestBtn'),
  directUrls: document.querySelector('#directUrls'),
  directExtractAudio: document.querySelector('#directExtractAudio'),
  directSummary: document.querySelector('#directSummary'),
  directDownloadBtn: document.querySelector('#directDownloadBtn'),
  likedExtractAudio: document.querySelector('#likedExtractAudio'),
  youtubeSummary: document.querySelector('#youtubeSummary'),
  downloadLikedBtn: document.querySelector('#downloadLikedBtn'),
  progressLabel: document.querySelector('#progressLabel'),
  progressValue: document.querySelector('#progressValue'),
  progressFill: document.querySelector('#progressFill'),
  progressDetail: document.querySelector('#progressDetail'),
  syncStatus: document.querySelector('#syncStatus'),
  syncDetail: document.querySelector('#syncDetail'),
  latestDownloadSummary: document.querySelector('#latestDownloadSummary'),
  fileLinks: document.querySelector('#fileLinks'),
  logs: document.querySelector('#logs'),
};

function supportsLocalFolder() {
  return typeof window.showDirectoryPicker === 'function';
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : 'Not yet';
}

function formatNumber(value) {
  if (typeof value !== 'number') {
    return 'Unknown';
  }
  return new Intl.NumberFormat().format(value);
}

function formatBytes(value) {
  if (typeof value !== 'number') {
    return '';
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
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function parseDirectUrls(rawValue) {
  return [...new Set(
    String(rawValue || '')
      .split(/\s+/)
      .map((value) => value.trim())
      .filter(Boolean),
  )];
}

function getDirectUrls() {
  return parseDirectUrls(elements.directUrls?.value || '');
}

function getLatestDownload() {
  return state.status?.latestDownload || null;
}

function getAuth() {
  return state.status?.auth || { configured: false, authenticated: false };
}

function getDownloadJob() {
  return state.status?.download || {};
}

function getProgress() {
  return state.status?.progress || null;
}

async function fetchJson(url, options = {}) {
  const requestOptions = {
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    ...options,
  };

  const response = await fetch(url, requestOptions);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed: ${response.status}`);
  }
  return payload;
}

function setSyncState(status, detail, extra = {}) {
  state.sync = {
    ...state.sync,
    status,
    detail,
    ...extra,
  };
  renderSyncPanel();
}

function renderHero() {
  const auth = getAuth();
  const tools = state.status?.tools || {};
  const latest = getLatestDownload();
  const ytDlpAvailable = Boolean(tools?.ytDlp?.available);
  const audioReady = Boolean(tools?.audioExtraction?.available);

  elements.authHeroStatus.textContent = auth.authenticated
    ? 'Connected'
    : auth.configured
      ? 'Ready to sign in'
      : 'Needs setup';
  elements.toolHeroStatus.textContent = ytDlpAvailable
    ? audioReady ? 'Media + MP3 ready' : 'Media ready'
    : 'Unavailable';
  elements.jobHeroStatus.textContent = latest
    ? `Finished ${formatTime(latest.savedAt)}`
    : getDownloadJob().running
      ? 'Running now'
      : 'Waiting';
}

function renderAuth() {
  const auth = getAuth();
  if (!auth.configured) {
    elements.authStatusText.textContent =
      'Google sign-in is not configured on the server yet. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and OAUTH_REDIRECT_URI on Render.';
    elements.authSignInBtn.style.display = 'none';
    elements.authSignOutBtn.style.display = 'none';
    return;
  }

  if (auth.authenticated) {
    elements.authStatusText.textContent =
      'Google is connected. Music Studio can now read your YouTube liked videos.';
    elements.authSignInBtn.style.display = 'none';
    elements.authSignOutBtn.style.display = 'inline-flex';
  } else {
    elements.authStatusText.textContent =
      'Sign in with Google if you want to pull from your YouTube likes. Pasted links can still be downloaded without signing in.';
    elements.authSignInBtn.style.display = 'inline-flex';
    elements.authSignOutBtn.style.display = 'none';
  }
}

function renderFolder() {
  if (!supportsLocalFolder()) {
    elements.folderStatus.textContent = 'Direct folder saving is unavailable in this browser.';
    elements.folderDetail.textContent =
      'Use Chrome or Edge for folder-based saving. You can still download the finished files manually below.';
    return;
  }

  if (state.folderHandle && state.folderName) {
    elements.folderStatus.textContent = `Saving into "${state.folderName}" on this device.`;
    elements.folderDetail.textContent =
      'Music Studio will automatically write finished files into this folder when each job completes.';
    return;
  }

  elements.folderStatus.textContent = 'No local folder chosen yet.';
  elements.folderDetail.textContent =
    'Choose a folder now so finished files can be saved there automatically.';
}

function renderDirectSummary() {
  const urls = getDirectUrls();
  if (!urls.length) {
    elements.directSummary.textContent = 'Paste one or more URLs to begin.';
    return;
  }
  elements.directSummary.textContent =
    `${formatNumber(urls.length)} URL(s) ready${elements.directExtractAudio.checked ? ' with MP3 extraction enabled' : ''}.`;
}

function renderYouTubeSummary() {
  const auth = getAuth();
  if (!auth.configured) {
    elements.youtubeSummary.textContent = 'Google sign-in must be configured on the server first.';
    return;
  }
  elements.youtubeSummary.textContent = auth.authenticated
    ? `Music Studio will read your liked YouTube videos and ${elements.likedExtractAudio.checked ? 'extract MP3 audio' : 'prepare media files'} for local saving.`
    : 'Sign in with Google to enable downloading from your YouTube likes.';
}

function renderProgress() {
  const progress = getProgress();
  if (!progress) {
    elements.progressLabel.textContent = 'Ready';
    elements.progressValue.textContent = 'Idle';
    elements.progressDetail.textContent = 'Paste links or connect YouTube to start.';
    elements.progressFill.classList.remove('is-indeterminate');
    elements.progressFill.style.width = '0%';
    return;
  }

  elements.progressLabel.textContent = progress.label || 'Working...';
  elements.progressDetail.textContent = progress.detail || 'Music Studio is processing your request.';

  if (typeof progress.percent === 'number') {
    elements.progressValue.textContent = `${Math.round(progress.percent)}%`;
    elements.progressFill.classList.remove('is-indeterminate');
    elements.progressFill.style.width = `${Math.max(2, Math.min(100, progress.percent))}%`;
    return;
  }

  elements.progressValue.textContent = progress.running ? 'Live' : 'Idle';
  if (progress.running) {
    elements.progressFill.classList.add('is-indeterminate');
    elements.progressFill.style.width = '';
  } else {
    elements.progressFill.classList.remove('is-indeterminate');
    elements.progressFill.style.width = '0%';
  }
}

function renderSyncPanel() {
  elements.syncStatus.textContent = state.sync.status;
  elements.syncDetail.textContent = state.sync.detail;
}

function renderFiles() {
  const latest = getLatestDownload();
  if (!latest?.files?.length) {
    elements.latestDownloadSummary.textContent = 'No completed job yet.';
    elements.fileLinks.className = 'file-links empty-state';
    elements.fileLinks.textContent = 'Finished files will appear here.';
    return;
  }

  const sourceLabel = latest.sourceKind === 'youtube-liked-videos'
    ? 'your YouTube likes'
    : 'your pasted links';
  elements.latestDownloadSummary.textContent =
    `Latest job prepared ${formatNumber(latest.completedFileCount)} file(s) from ${sourceLabel} at ${formatTime(latest.savedAt)}.`;

  elements.fileLinks.className = 'file-links';
  elements.fileLinks.innerHTML = latest.files
    .map(
      (file) => `
        <a class="file-pill" href="${file.url}" download>
          <strong>${escapeHtml(file.name)}</strong>
          <span>${formatBytes(file.sizeBytes)}</span>
        </a>
      `,
    )
    .join('');
}

function renderLogs() {
  const logs = state.status?.logs || [];
  if (!logs.length) {
    elements.logs.className = 'logs empty-state';
    elements.logs.textContent = 'Waiting for activity...';
    return;
  }

  elements.logs.className = 'logs';
  elements.logs.innerHTML = logs
    .map(
      (log) => `
        <div class="log-line ${log.kind}">
          <span class="log-time">${new Date(log.timestamp).toLocaleTimeString()}</span>
          <span class="log-message">${escapeHtml(log.message)}</span>
        </div>
      `,
    )
    .join('');
  elements.logs.scrollTop = elements.logs.scrollHeight;
}

function syncActionButtons() {
  const auth = getAuth();
  const jobRunning = Boolean(getDownloadJob().running);
  const ytDlpAvailable = Boolean(state.status?.tools?.ytDlp?.available);
  const hasDirectUrls = getDirectUrls().length > 0;
  const latest = getLatestDownload();

  elements.authSignInBtn.disabled = jobRunning || !auth.configured;
  elements.authSignOutBtn.disabled = jobRunning;
  elements.chooseFolderBtn.disabled = state.sync.running || !supportsLocalFolder();
  elements.saveLatestBtn.disabled = state.sync.running || !latest?.files?.length;
  elements.directUrls.disabled = jobRunning;
  elements.directExtractAudio.disabled = jobRunning || !ytDlpAvailable;
  elements.likedExtractAudio.disabled = jobRunning || !ytDlpAvailable || !auth.authenticated;
  elements.directDownloadBtn.disabled = jobRunning || !ytDlpAvailable || !hasDirectUrls;
  elements.downloadLikedBtn.disabled = jobRunning || !ytDlpAvailable || !auth.authenticated;
}

function renderAll() {
  renderHero();
  renderAuth();
  renderFolder();
  renderDirectSummary();
  renderYouTubeSummary();
  renderProgress();
  renderSyncPanel();
  renderFiles();
  renderLogs();
  syncActionButtons();
}

async function chooseLocalFolder() {
  if (!supportsLocalFolder()) {
    throw new Error('This browser does not support direct folder saving. Use Chrome or Edge, or download files manually from the list below.');
  }

  const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
  state.folderHandle = handle;
  state.folderName = handle.name || 'Selected folder';
  setSyncState(
    'Local folder ready.',
    `Finished files will be saved into "${state.folderName}" on this device.`,
    { failedRunId: null },
  );
  renderAll();
}

async function ensureLocalFolderIfPossible() {
  if (!supportsLocalFolder() || state.folderHandle) {
    return;
  }
  await chooseLocalFolder();
}

async function syncLatestDownload(manifest, { manual = false } = {}) {
  if (!manifest?.files?.length) {
    throw new Error('There are no finished files to save yet.');
  }

  if (!state.folderHandle) {
    if (!manual) {
      return;
    }
    await chooseLocalFolder();
  }

  if (!state.folderHandle) {
    return;
  }

  state.sync.running = true;
  state.sync.failedRunId = null;
  renderAll();

  try {
    for (let index = 0; index < manifest.files.length; index += 1) {
      const file = manifest.files[index];
      setSyncState(
        `Saving ${index + 1} of ${manifest.files.length} locally...`,
        `Writing ${file.name} into "${state.folderName}".`,
      );
      const response = await fetch(file.url);
      if (!response.ok) {
        throw new Error(`Could not download ${file.name} from the server.`);
      }
      const fileHandle = await state.folderHandle.getFileHandle(file.name, { create: true });
      const writable = await fileHandle.createWritable();
      if (response.body && writable) {
        await response.body.pipeTo(writable);
      } else {
        const blob = await response.blob();
        await writable.write(blob);
        await writable.close();
      }
    }

    state.sync.completedRunId = manifest.runId;
    state.sync.failedRunId = null;
    setSyncState(
      `Saved ${manifest.files.length} file(s) locally.`,
      `Everything from the latest job is now in "${state.folderName}".`,
    );
  } catch (error) {
    state.sync.failedRunId = manifest.runId;
    setSyncState(
      'Local save needs attention.',
      error instanceof Error ? error.message : String(error),
    );
    if (manual) {
      throw error;
    }
  } finally {
    state.sync.running = false;
    renderAll();
  }
}

async function maybeAutoSaveLatest() {
  const latest = getLatestDownload();
  if (!latest?.files?.length || !state.folderHandle || state.sync.running) {
    return;
  }
  if (latest.runId === state.sync.completedRunId || latest.runId === state.sync.failedRunId) {
    return;
  }
  await syncLatestDownload(latest);
}

async function refreshStatus() {
  try {
    state.status = await fetchJson('/api/status');
    renderAll();
    await maybeAutoSaveLatest();
  } catch (error) {
    setSyncState(
      'Connection problem.',
      error instanceof Error ? error.message : String(error),
    );
  }
}

async function invokeAction(url, body, button, idleLabel, busyLabel) {
  const previousLabel = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    await fetchJson(url, {
      method: 'POST',
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

elements.authSignInBtn?.addEventListener('click', async () => {
  try {
    const data = await fetchJson('/api/auth/start');
    const width = 540;
    const height = 680;
    const left = Math.max(40, Math.round((window.innerWidth - width) / 2));
    const top = Math.max(40, Math.round((window.innerHeight - height) / 2));
    const popup = window.open(
      data.auth_url,
      'MusicStudioGoogleSignIn',
      `width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) {
      throw new Error('The Google sign-in window was blocked. Please allow pop-ups for this site and try again.');
    }
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.authSignOutBtn?.addEventListener('click', async () => {
  await invokeAction('/api/auth/logout', null, elements.authSignOutBtn, 'Sign Out', 'Signing Out...');
});

window.addEventListener('message', async (event) => {
  if (event.origin !== window.location.origin) {
    return;
  }
  if (event.data?.type !== 'music-studio-auth') {
    return;
  }
  await refreshStatus();
});

elements.chooseFolderBtn?.addEventListener('click', async () => {
  try {
    await chooseLocalFolder();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.saveLatestBtn?.addEventListener('click', async () => {
  try {
    await syncLatestDownload(getLatestDownload(), { manual: true });
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  }
});

elements.directUrls?.addEventListener('input', () => {
  renderDirectSummary();
  syncActionButtons();
});

elements.directExtractAudio?.addEventListener('change', () => {
  renderDirectSummary();
});

elements.likedExtractAudio?.addEventListener('change', () => {
  renderYouTubeSummary();
});

elements.directDownloadBtn?.addEventListener('click', async () => {
  try {
    await ensureLocalFolderIfPossible();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
    return;
  }

  await invokeAction(
    '/api/direct-download',
    {
      urls: getDirectUrls(),
      extractAudio: elements.directExtractAudio.checked,
    },
    elements.directDownloadBtn,
    'Download Pasted Links',
    'Starting...',
  );
});

elements.downloadLikedBtn?.addEventListener('click', async () => {
  try {
    await ensureLocalFolderIfPossible();
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
    return;
  }

  await invokeAction(
    '/api/youtube/download-liked',
    {
      extractAudio: elements.likedExtractAudio.checked,
    },
    elements.downloadLikedBtn,
    'Download My Liked Videos',
    'Starting...',
  );
});

await refreshStatus();
renderAll();
setInterval(refreshStatus, 2500);
