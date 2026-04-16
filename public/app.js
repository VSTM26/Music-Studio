const elements = {
  platformNote: document.querySelector("#platformNote"),
  platformTargets: [...document.querySelectorAll("[data-platform]")],
};

function detectPlatform() {
  const source = [
    navigator.userAgentData && navigator.userAgentData.platform,
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

function highlightPlatform(platform) {
  for (const element of elements.platformTargets) {
    element.classList.toggle("is-recommended", element.getAttribute("data-platform") === platform);
  }
}

function renderPlatformNote(platform) {
  if (!elements.platformNote) {
    return;
  }

  if (platform === "unknown") {
    elements.platformNote.textContent =
      "Each button downloads an actual packaged desktop app, so users can pick Windows, macOS, or Linux without hitting an empty Releases page.";
    return;
  }

  elements.platformNote.textContent =
    `This browser looks like ${platformLabel(platform)}. That option is highlighted below, and all three buttons now download actual packaged desktop apps.`;
}

const platform = detectPlatform();
highlightPlatform(platform);
renderPlatformNote(platform);
