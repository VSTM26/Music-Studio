const state = {
  status: null,
  results: null,
  search: '',
  selectedKeys: new Set(),
};

const elements = {
  chooseFolderBtn: document.querySelector('#chooseFolderBtn'),
  launchBrowserBtn: document.querySelector('#launchBrowserBtn'),
  runExportBtn: document.querySelector('#runExportBtn'),
  resetSessionBtn: document.querySelector('#resetSessionBtn'),
  chromeStatus: document.querySelector('#chromeStatus'),
  chromeDetail: document.querySelector('#chromeDetail'),
  debugStatus: document.querySelector('#debugStatus'),
  debugDetail: document.querySelector('#debugDetail'),
  exportStatus: document.querySelector('#exportStatus'),
  exportDetail: document.querySelector('#exportDetail'),
  resultStatus: document.querySelector('#resultStatus'),
  resultDetail: document.querySelector('#resultDetail'),
  downloadStatus: document.querySelector('#downloadStatus'),
  downloadDetail: document.querySelector('#downloadDetail'),
  toolStatus: document.querySelector('#toolStatus'),
  toolDetail: document.querySelector('#toolDetail'),
  outputFolderStatus: document.querySelector('#outputFolderStatus'),
  outputFolderDetail: document.querySelector('#outputFolderDetail'),
  downloadSelectedBtn: document.querySelector('#downloadSelectedBtn'),
  downloadAllBtn: document.querySelector('#downloadAllBtn'),
  clearSelectionBtn: document.querySelector('#clearSelectionBtn'),
  extractAudio: document.querySelector('#extractAudio'),
  selectionSummary: document.querySelector('#selectionSummary'),
  fileLinks: document.querySelector('#fileLinks'),
  summaryBanner: document.querySelector('#summaryBanner'),
  logs: document.querySelector('#logs'),
  tracksTable: document.querySelector('#tracksTable'),
  trackSearch: document.querySelector('#trackSearch'),
  selectAllTracks: document.querySelector('#selectAllTracks'),
};

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
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
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

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function getTracks() {
  return state.results?.tracks || [];
}

function getFilteredTracks() {
  const tracks = getTracks();
  const search = state.search.trim().toLowerCase();
  if (!search) {
    return tracks;
  }

  return tracks.filter((track) =>
    [track.title, track.artists, track.meta, track.duration]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(search)),
  );
}

function trimSelection() {
  const validKeys = new Set(
    getTracks()
      .map((track) => track.trackKey)
      .filter(Boolean),
  );
  for (const key of [...state.selectedKeys]) {
    if (!validKeys.has(key)) {
      state.selectedKeys.delete(key);
    }
  }
}

function renderStatus() {
  const { status } = state;
  if (!status) {
    return;
  }

  elements.chromeStatus.textContent = status.chrome.found ? 'Ready' : 'Missing';
  elements.chromeDetail.textContent = status.chrome.found
    ? status.chrome.path
    : 'Install Chrome or set CHROME_PATH before launching the guided browser.';

  elements.debugStatus.textContent = status.debug.connected ? 'Connected' : 'Offline';
  elements.debugDetail.textContent = status.debug.connected
    ? status.debug.musicTabOpen
      ? `${status.debug.browser || 'Chrome'} | ${status.debug.musicTabTitle || 'YouTube Music tab open'}`
      : `${status.debug.browser || 'Chrome'} | Open the Guided Chrome window and sign in.`
    : 'No Chrome DevTools session is listening on port 9224 yet.';

  elements.exportStatus.textContent = status.export.running ? 'Running' : 'Idle';
  elements.exportDetail.textContent = status.export.running
    ? `Started ${formatTime(status.export.last_started_at)}`
    : status.export.last_finished_at
      ? `Last finished ${formatTime(status.export.last_finished_at)}`
      : 'No export has been run in this session.';
  if (status.export.last_error) {
    elements.exportDetail.textContent += ` | ${status.export.last_error}`;
  }

  if (status.latestExport) {
    elements.resultStatus.textContent = `${formatNumber(status.latestExport.exportedCount)} songs exported`;
    elements.resultDetail.textContent = `Saved ${formatTime(status.latestExport.exportedAt)} from ${status.latestExport.title || 'Liked Music'}`;
  } else {
    elements.resultStatus.textContent = 'No export yet';
    elements.resultDetail.textContent = 'Run the exporter after signing in to YouTube Music.';
  }

  elements.downloadStatus.textContent = status.download.running ? 'Running' : 'Idle';
  elements.downloadDetail.textContent = status.download.running
    ? `Working on ${formatNumber(status.download.requested_count)} tracks`
    : status.download.last_finished_at
      ? `Last finished ${formatTime(status.download.last_finished_at)}`
      : 'No media download has been started yet.';
  if (status.download.last_error) {
    elements.downloadDetail.textContent += ` | ${status.download.last_error}`;
  }

  const ytDlpAvailable = Boolean(status.tools?.ytDlp?.available);
  const ffmpegAvailable = Boolean(status.tools?.ffmpeg?.available);
  elements.toolStatus.textContent = ytDlpAvailable
    ? ffmpegAvailable
      ? 'Media and audio ready'
      : 'Media ready'
    : 'Downloads unavailable';
  elements.toolDetail.textContent = ytDlpAvailable
    ? ffmpegAvailable
      ? 'yt-dlp and ffmpeg are available for full downloads and MP3 extraction.'
      : 'yt-dlp is available. Install ffmpeg if you want MP3 extraction.'
    : 'Run pip install -r requirements.txt to enable yt-dlp downloads.';

  elements.outputFolderStatus.textContent = status.output?.directory || 'Using the project output folder';
  elements.outputFolderDetail.textContent = `Exports save here, and media downloads go into ${status.output?.downloadsDirectory || ''}`;

  syncActionButtons();
}

function renderFiles() {
  const latest = state.status?.latestExport;
  if (!latest?.files?.length) {
    elements.fileLinks.className = 'file-links empty-state';
    elements.fileLinks.textContent = 'Run an export to generate downloadable files.';
    return;
  }

  elements.fileLinks.className = 'file-links';
  elements.fileLinks.innerHTML = latest.files
    .map(
      (file) => `
        <a class="file-pill" href="${file.url}">
          <strong>${escapeHtml(file.name)}</strong>
          <span>${formatBytes(file.sizeBytes)}</span>
        </a>
      `,
    )
    .join('');
}

function renderSummary() {
  const latest = state.status?.latestExport;
  if (!latest) {
    elements.summaryBanner.className = 'summary-banner empty-state';
    elements.summaryBanner.textContent = 'No results loaded yet.';
    return;
  }

  const mismatch =
    typeof latest.mismatchCount === 'number' && latest.mismatchCount > 0;
  elements.summaryBanner.className = `summary-banner${mismatch ? ' warning' : ''}`;
  elements.summaryBanner.innerHTML = mismatch
    ? `
      <strong>${formatNumber(latest.exportedCount)}</strong> songs were exported, while the
      playlist header reported <strong>${formatNumber(latest.reportedTrackCount)}</strong>.
      The app keeps both numbers so you can see the mismatch instead of hiding it.
    `
    : `
      Export completed with <strong>${formatNumber(latest.exportedCount)}</strong> songs from
      <strong>${escapeHtml(latest.title || 'Liked Music')}</strong>.
    `;
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

function renderSelectionSummary() {
  const tracks = getTracks();
  const filtered = getFilteredTracks();
  const selectedCount = state.selectedKeys.size;

  if (!tracks.length) {
    elements.selectionSummary.textContent =
      'Export tracks first, then select the songs you want from the table below.';
  } else if (!selectedCount) {
    elements.selectionSummary.textContent =
      `Showing ${formatNumber(filtered.length)} of ${formatNumber(tracks.length)} exported tracks. Download All uses every exported song.`;
  } else {
    elements.selectionSummary.textContent =
      `${formatNumber(selectedCount)} track(s) selected. Download Selected uses the checked rows only.`;
  }
}

function syncSelectAllCheckbox() {
  const visibleKeys = getFilteredTracks()
    .map((track) => track.trackKey)
    .filter(Boolean);
  const selectedVisible = visibleKeys.filter((key) => state.selectedKeys.has(key));

  elements.selectAllTracks.disabled = visibleKeys.length === 0;
  elements.selectAllTracks.checked =
    visibleKeys.length > 0 && selectedVisible.length === visibleKeys.length;
  elements.selectAllTracks.indeterminate =
    selectedVisible.length > 0 && selectedVisible.length < visibleKeys.length;
}

function renderTracks() {
  const tracks = getTracks();
  if (!tracks.length) {
    elements.tracksTable.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">No tracks loaded yet.</td>
      </tr>
    `;
    renderSelectionSummary();
    syncSelectAllCheckbox();
    return;
  }

  const filtered = getFilteredTracks();
  if (!filtered.length) {
    elements.tracksTable.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">No tracks matched that search.</td>
      </tr>
    `;
    renderSelectionSummary();
    syncSelectAllCheckbox();
    return;
  }

  elements.tracksTable.innerHTML = filtered
    .slice(0, 500)
    .map(
      (track) => `
        <tr>
          <td>
            <input
              class="track-select"
              type="checkbox"
              data-track-key="${escapeHtml(track.trackKey || '')}"
              ${state.selectedKeys.has(track.trackKey) ? 'checked' : ''}
            >
          </td>
          <td>${track.index}</td>
          <td>
            <strong class="track-title">
              ${
                track.url
                  ? `<a class="track-link" href="${track.url}" target="_blank" rel="noreferrer">${escapeHtml(track.title || '')}</a>`
                  : escapeHtml(track.title || '')
              }
            </strong>
            <span class="track-meta">${escapeHtml(track.videoType || '')}</span>
          </td>
          <td>${escapeHtml(track.artists || '')}</td>
          <td>${escapeHtml(track.meta || '')}</td>
          <td>${escapeHtml(track.duration || '')}</td>
        </tr>
      `,
    )
    .join('');

  renderSelectionSummary();
  syncSelectAllCheckbox();
}

function syncActionButtons() {
  const exportRunning = Boolean(state.status?.export?.running);
  const downloadRunning = Boolean(state.status?.download?.running);
  const ytDlpAvailable = Boolean(state.status?.tools?.ytDlp?.available);
  const tracks = getTracks();
  const hasSelection = state.selectedKeys.size > 0;

  elements.chooseFolderBtn.disabled = exportRunning || downloadRunning;
  elements.launchBrowserBtn.disabled = exportRunning;
  elements.runExportBtn.disabled = exportRunning;
  elements.resetSessionBtn.disabled = exportRunning;
  elements.downloadSelectedBtn.disabled =
    exportRunning || downloadRunning || !ytDlpAvailable || !hasSelection;
  elements.downloadAllBtn.disabled =
    exportRunning || downloadRunning || !ytDlpAvailable || tracks.length === 0;
  elements.clearSelectionBtn.disabled = !hasSelection;
}

async function loadResults() {
  try {
    state.results = await fetchJson('/api/results');
    trimSelection();
  } catch {
    state.results = null;
    state.selectedKeys.clear();
  }
  renderTracks();
  syncActionButtons();
}

async function refreshStatus() {
  try {
    const previousExportedAt = state.status?.latestExport?.exportedAt || null;
    state.status = await fetchJson('/api/status');
    renderStatus();
    renderFiles();
    renderSummary();
    renderLogs();

    const nextExportedAt = state.status?.latestExport?.exportedAt || null;
    if (nextExportedAt && nextExportedAt !== previousExportedAt) {
      await loadResults();
    }

    if (!state.results && nextExportedAt) {
      await loadResults();
    }
  } catch (error) {
    elements.debugStatus.textContent = 'Unavailable';
    elements.debugDetail.textContent = error instanceof Error ? error.message : String(error);
  }
}

async function invokeAction(url, button, idleLabel, busyLabel, body) {
  button.disabled = true;
  button.textContent = busyLabel;

  try {
    await fetchJson(url, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
    await refreshStatus();
    if (url === '/api/select-output-folder') {
      await loadResults();
    }
  } catch (error) {
    alert(error instanceof Error ? error.message : String(error));
  } finally {
    button.disabled = false;
    button.textContent = idleLabel;
    syncActionButtons();
  }
}

elements.chooseFolderBtn.addEventListener('click', () => {
  invokeAction(
    '/api/select-output-folder',
    elements.chooseFolderBtn,
    'Choose Save Folder',
    'Choosing...',
  );
});

elements.launchBrowserBtn.addEventListener('click', () => {
  invokeAction(
    '/api/launch-browser',
    elements.launchBrowserBtn,
    'Open Guided Chrome',
    'Opening...',
  );
});

elements.runExportBtn.addEventListener('click', () => {
  invokeAction('/api/export', elements.runExportBtn, 'Run Export', 'Starting...');
});

elements.resetSessionBtn.addEventListener('click', () => {
  invokeAction(
    '/api/reset-session',
    elements.resetSessionBtn,
    'Reset Guided Session',
    'Resetting...',
  );
});

elements.downloadSelectedBtn.addEventListener('click', () => {
  invokeAction(
    '/api/download',
    elements.downloadSelectedBtn,
    'Download Selected',
    'Starting...',
    {
      trackKeys: [...state.selectedKeys],
      extractAudio: elements.extractAudio.checked,
    },
  );
});

elements.downloadAllBtn.addEventListener('click', () => {
  invokeAction(
    '/api/download',
    elements.downloadAllBtn,
    'Download All Exported',
    'Starting...',
    {
      extractAudio: elements.extractAudio.checked,
    },
  );
});

elements.clearSelectionBtn.addEventListener('click', () => {
  state.selectedKeys.clear();
  renderTracks();
  syncActionButtons();
});

elements.trackSearch.addEventListener('input', (event) => {
  state.search = event.currentTarget.value;
  renderTracks();
  syncActionButtons();
});

elements.tracksTable.addEventListener('change', (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !input.classList.contains('track-select')) {
    return;
  }

  const key = input.dataset.trackKey;
  if (!key) {
    return;
  }

  if (input.checked) {
    state.selectedKeys.add(key);
  } else {
    state.selectedKeys.delete(key);
  }
  renderSelectionSummary();
  syncSelectAllCheckbox();
  syncActionButtons();
});

elements.selectAllTracks.addEventListener('change', (event) => {
  const input = event.currentTarget;
  const visibleKeys = getFilteredTracks()
    .map((track) => track.trackKey)
    .filter(Boolean);

  if (input.checked) {
    for (const key of visibleKeys) {
      state.selectedKeys.add(key);
    }
  } else {
    for (const key of visibleKeys) {
      state.selectedKeys.delete(key);
    }
  }

  renderTracks();
  syncActionButtons();
});

await refreshStatus();
await loadResults();
setInterval(refreshStatus, 2500);
