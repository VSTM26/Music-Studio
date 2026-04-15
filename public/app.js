const DOWNLOADS_URL = "https://github.com/VSTM26/Music-Studio/releases/latest";

const elements = {
  primaryDownload: document.querySelector("#primaryDownload"),
  platformNote: document.querySelector("#platformNote"),
  downloadCards: [...document.querySelectorAll(".download-card[data-platform]")],
};

function detectPlatform() {
  const source = [
    navigator.userAgentData && Array.isArray(navigator.userAgentData.platform)
      ? navigator.userAgentData.platform.join(" ")
      : navigator.userAgentData && navigator.userAgentData.platform,
    navigator.platform,
    navigator.userAgent,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (source.includes("win")) {
    return "windows";
  }
  if (source.includes("mac")) {
    return "macos";
  }
  if (source.includes("linux") || source.includes("x11")) {
    return "linux";
  }
  return "unknown";
}

function platformLabel(platform) {
  if (platform === "windows") {
    return "Windows";
  }
  if (platform === "macos") {
    return "macOS";
  }
  if (platform === "linux") {
    return "Linux";
  }
  return "your platform";
}

function highlightPlatformCards(platform) {
  for (const card of elements.downloadCards) {
    const matches = card.getAttribute("data-platform") === platform;
    card.classList.toggle("is-recommended", matches);
  }
}

function hydrateDownloads() {
  const platform = detectPlatform();
  const label = platformLabel(platform);

  if (elements.primaryDownload) {
    elements.primaryDownload.href = DOWNLOADS_URL;
    elements.primaryDownload.textContent =
      platform === "unknown" ? "Download Latest Release" : `Download for ${label}`;
  }

  if (elements.platformNote) {
    elements.platformNote.textContent =
      platform === "unknown"
        ? "Desktop installers and release files are published on GitHub Releases."
        : `This browser looks like ${label}. The matching download is highlighted below, and all builds live on GitHub Releases.`;
  }

  highlightPlatformCards(platform);
}

hydrateDownloads();
