// Bouton « Télécharger cette vidéo » affiché au survol des lecteurs vidéo (comme IDM).
(() => {
  if (window.__pydmLoaded) return;
  window.__pydmLoaded = true;
  const api = globalThis.browser ?? chrome;
  let enabled = true;
  let host, button, current, hideTimer, lastScan = 0;

  api.storage.local.get("videoButton").then((s) => { enabled = s.videoButton !== false; });
  api.storage.onChanged.addListener((c) => {
    if (c.videoButton) { enabled = c.videoButton.newValue !== false; if (!enabled) hide(); }
  });

  function build() {
    host = document.createElement("div");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;display:none;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        button { font: 600 13px/1 system-ui, sans-serif; color: #fff; background: #1a73e8;
                 border: 0; border-radius: 6px; padding: 8px 12px; cursor: pointer;
                 box-shadow: 0 2px 8px rgba(0,0,0,.35); display: flex; gap: 6px; align-items: center; }
        button:hover { background: #1557b0; }
        button.ok { background: #188038; } button.err { background: #d93025; }
      </style>
      <button type="button">⬇ Télécharger cette vidéo</button>`;
    button = root.querySelector("button");
    button.addEventListener("click", onClick);
    host.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  }

  function place(video) {
    if (!host) build();
    const parent = document.fullscreenElement || document.documentElement;
    if (host.parentNode !== parent) parent.appendChild(host);
    const r = video.getBoundingClientRect();
    host.style.top = `${Math.max(4, r.top + 8)}px`;
    host.style.left = `${Math.max(4, r.right - 210)}px`;
    host.style.display = "block";
    current = video;
  }

  function hide() {
    if (host) host.style.display = "none";
    current = null;
  }

  function videoUnder(x, y) {
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      if (r.width >= 200 && r.height >= 120 && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return v;
    }
    return null;
  }

  document.addEventListener("mousemove", (e) => {
    if (!enabled || e.timeStamp - lastScan < 150) return;
    lastScan = e.timeStamp;
    const v = videoUnder(e.clientX, e.clientY);
    if (v) {
      clearTimeout(hideTimer);
      place(v);
    } else if (current && !host.matches(":hover")) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(hide, 1500);
    }
  }, { passive: true, capture: true });

  async function onClick(e) {
    e.preventDefault();
    e.stopPropagation();
    const src = current?.currentSrc || current?.src || "";
    button.textContent = "Envoi à PyDM…";
    let reply;
    try {
      reply = await api.runtime.sendMessage({ type: "video", pageUrl: location.href, src });
    } catch (err) {
      reply = { ok: false, error: String(err) };
    }
    button.className = reply?.ok ? "ok" : "err";
    button.textContent = reply?.ok ? "✓ Envoyé à PyDM" : "✗ PyDM injoignable";
    if (!reply?.ok) console.warn("PyDM :", reply?.error);
    setTimeout(() => { button.className = ""; button.textContent = "⬇ Télécharger cette vidéo"; }, 2500);
  }
})();
