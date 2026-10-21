// Bouton « Télécharger cette vidéo » affiché au survol des lecteurs vidéo (comme IDM).
(() => {
  if (window.__pydmLoaded) return;
  window.__pydmLoaded = true;
  const api = globalThis.browser ?? chrome;
  let enabled = true;
  let host, button, label, current, hideTimer, resetTimer, lastScan = 0;

  api.storage.local.get("videoButton").then((s) => { enabled = s.videoButton !== false; });
  api.storage.onChanged.addListener((c) => {
    if (c.videoButton) { enabled = c.videoButton.newValue !== false; if (!enabled) hide(); }
  });

  const LABEL = "Télécharger avec PyDM";

  function build() {
    host = document.createElement("div");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;display:none;";
    const root = host.attachShadow({ mode: "closed" });
    // pastille au logo PyDM (anneau des connexions + flèche) qui s'allonge au survol
    root.innerHTML = `
      <style>
        button { all: unset; box-sizing: border-box; display: flex; align-items: center; gap: 0;
                 height: 34px; padding: 0 6px; border-radius: 17px; cursor: pointer;
                 font: 600 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif; color: #f8fafc;
                 background: rgba(15, 23, 42, .82); border: 1px solid rgba(148, 163, 184, .28);
                 -webkit-backdrop-filter: blur(10px) saturate(140%); backdrop-filter: blur(10px) saturate(140%);
                 box-shadow: 0 4px 16px rgba(0, 0, 0, .35);
                 transition: gap .2s ease, padding .2s ease, background .2s, border-color .2s; }
        .label { max-width: 0; opacity: 0; overflow: hidden; white-space: nowrap;
                 transition: max-width .25s ease, opacity .2s ease; }
        button:hover, button:focus-visible, button.busy, button.ok, button.err { gap: 8px; padding: 0 14px 0 6px; }
        button:hover .label, button:focus-visible .label, .busy .label, .ok .label, .err .label {
                 max-width: 220px; opacity: 1; }
        button:hover { background: rgba(15, 23, 42, .94); border-color: rgba(34, 211, 238, .55); }
        button:focus-visible { outline: 2px solid #22d3ee; outline-offset: 2px; }
        svg { width: 22px; height: 22px; flex: none; }
        .ring { stroke: #22d3ee; transform-origin: 12px 12px; }
        .check, .cross { display: none; }
        .busy .ring { animation: spin 1s linear infinite; }
        .ok { border-color: rgba(34, 211, 238, .7); } .ok .label { color: #67e8f9; }
        .ok .arrow, .err .arrow { display: none; } .ok .check, .err .cross { display: inline; }
        .err { border-color: rgba(248, 113, 113, .7); } .err .label { color: #fca5a5; } .err .ring { stroke: #f87171; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
      </style>
      <button type="button" title="${LABEL}" aria-label="${LABEL}">
        <svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle class="ring" cx="12" cy="12" r="9.5" stroke-width="2.2" stroke-dasharray="5.9 1.56"/>
          <path class="arrow" d="M12 7.5v8M8.8 12.6 12 15.8l3.2-3.2" stroke="#fff" stroke-width="2.2"/>
          <path class="check" d="M8 12.3l2.7 2.7L16 9.6" stroke="#fff" stroke-width="2.2"/>
          <path class="cross" d="M9 9l6 6M15 9l-6 6" stroke="#fff" stroke-width="2.2"/>
        </svg>
        <span class="label">${LABEL}</span>
      </button>`;
    button = root.querySelector("button");
    label = root.querySelector(".label");
    button.addEventListener("click", onClick);
    host.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  }

  function show(state, text) {
    button.className = state;
    label.textContent = text;
  }

  function place(video) {
    if (!host) build();
    const parent = document.fullscreenElement || document.documentElement;
    if (host.parentNode !== parent) parent.appendChild(host);
    const r = video.getBoundingClientRect();
    host.style.top = `${Math.max(4, r.top + 10)}px`;
    host.style.right = `${Math.max(4, document.documentElement.clientWidth - r.right + 10)}px`;
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
    clearTimeout(resetTimer);
    show("busy", "Envoi à PyDM…");
    let reply;
    try {
      reply = await api.runtime.sendMessage({ type: "video", pageUrl: location.href, src });
    } catch (err) {
      reply = { ok: false, error: String(err) };
    }
    show(reply?.ok ? "ok" : "err", reply?.ok ? "Envoyé à PyDM" : "PyDM injoignable");
    if (!reply?.ok) console.warn("PyDM :", reply?.error);
    resetTimer = setTimeout(() => show("", LABEL), 2500);
  }
})();
