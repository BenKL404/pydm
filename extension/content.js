// Bouton « Télécharger cette vidéo » affiché au survol des lecteurs vidéo (comme IDM).
(() => {
  if (window.__pydmLoaded) return;
  window.__pydmLoaded = true;
  const api = globalThis.browser ?? chrome;
  let enabled = true;
  let host, button, label, current, hideTimer, resetTimer, lastScan = 0, hovered = false, queued = false;
  let found = [], scanned = 0, taken = null;

  api.storage.local.get("videoButton").then((s) => { enabled = s.videoButton !== false; });
  api.storage.onChanged.addListener((c) => {
    if (c.videoButton) { enabled = c.videoButton.newValue !== false; if (!enabled) hide(); }
  });

  const LABEL = "Télécharger avec PyDM";
  const WIDTH = 240;
  const SIZE = 34;        // pastille repliée : carré de 34 px (cf. la feuille de style)
  const INSET = 10;
  const SCAN_MS = 1000;   // fréquence de recherche des vidéos (le survol, lui, est à 150 ms)
  const BUDGET = 20000;   // éléments inspectés au plus : une page énorme ne doit pas ramer
  // Le haut-gauche d'abord : les commandes des lecteurs et les boutons de Firefox (image dans
  // l'image) vivent à droite, et rien ne peut passer devant eux — ils sont dessinés par le
  // navigateur, hors de portée d'un z-index.
  const CORNERS = ["tl", "tr", "bl", "br"];

  // Position du conteneur et centre de la pastille pour un coin de la partie *visible* de la
  // vidéo. Se contenter du rectangle de la vidéo la rendait inatteignable : hors de l'écran sur
  // un lecteur plus large que la fenêtre, à cheval sur le bord d'une vidéo étroite. null quand
  // il ne reste rien d'assez grand pour cliquer.
  function anchor(rect, view, corner, width = WIDTH, size = SIZE, inset = INSET) {
    const left = Math.max(rect.left, 0), right = Math.min(rect.right, view.width);
    const top = Math.max(rect.top, 0), bottom = Math.min(rect.bottom, view.height);
    if (right - left < size + 2 * inset || bottom - top < size + 2 * inset) return null;
    const toLeft = corner[1] === "l", toTop = corner[0] === "t";
    const bx = toLeft ? left + inset : right - inset - size;    // bord gauche de la pastille
    const by = toTop ? top + inset : bottom - inset - size;
    return {
      corner,
      align: toLeft ? "flex-start" : "flex-end",   // le libellé s'allonge vers l'intérieur
      left: toLeft ? bx : bx + size - width,
      top: by,
      cx: bx + size / 2,
      cy: by + size / 2,
    };
  }

  // Premier coin où la pastille est réellement au-dessus de tout : `free` la pose et vérifie.
  function pickCorner(rect, view, free, first) {
    const order = first ? [first, ...CORNERS.filter((c) => c !== first)] : CORNERS;
    let fallback = null;
    for (const corner of order) {
      const spot = anchor(rect, view, corner);
      if (!spot) return null;
      if (!fallback && corner === CORNERS[0]) fallback = spot;
      if (free(spot)) return spot;
    }
    return fallback || anchor(rect, view, CORNERS[0]);          // tous pris : on affiche quand même
  }

  // Certains lecteurs encapsulent leur <video> dans un shadow root ouvert, que
  // document.querySelectorAll ne traverse pas : la pastille ne s'affichait jamais sur ces pages.
  function collect(root, out, budget) {
    for (const v of root.querySelectorAll("video")) out.push(v);
    for (const el of root.querySelectorAll("*")) {
      if (budget.left-- <= 0) return out;
      if (el.shadowRoot) collect(el.shadowRoot, out, budget);
    }
    return out;
  }

  function build() {
    host = document.createElement("div");
    host.style.cssText = `all:initial;position:fixed;z-index:2147483647;display:none;width:${WIDTH}px;`
      + "justify-content:flex-end;pointer-events:none;";
    const root = host.attachShadow({ mode: "closed" });
    // pastille au logo PyDM (anneau des connexions + flèche) qui s'allonge au survol
    root.innerHTML = `
      <style>
        button { all: unset; pointer-events: auto; box-sizing: border-box; display: flex; align-items: center; gap: 0;
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
    // le curseur est sur la pastille : ni effacement, ni déplacement sous le doigt
    host.addEventListener("pointerenter", () => { hovered = true; clearTimeout(hideTimer); });
    host.addEventListener("pointerleave", () => { hovered = false; });
  }

  function show(state, text) {
    button.className = state;
    label.textContent = text;
  }

  function apply(spot) {
    host.style.justifyContent = spot.align;
    host.style.left = `${spot.left}px`;
    host.style.top = `${spot.top}px`;
    host.style.display = "flex";
    // une page qui transforme <html> ou le conteneur plein écran décale « fixed » : on corrige
    const h = host.getBoundingClientRect();
    if (Math.abs(h.left - spot.left) > 1 || Math.abs(h.top - spot.top) > 1) {
      host.style.left = `${2 * spot.left - h.left}px`;
      host.style.top = `${2 * spot.top - h.top}px`;
    }
  }

  function place(video) {
    if (!host) build();
    if (hovered && current === video) return;       // ne pas déplacer la pastille sous le curseur
    const view = { width: innerWidth, height: innerHeight };
    const parent = document.fullscreenElement || document.documentElement;
    if (host.parentNode !== parent) parent.appendChild(host);
    const at = pickCorner(video.getBoundingClientRect(), view, (spot) => {
      apply(spot);        // posée pour de vrai : seul le test de survol dit qui est devant
      const front = document.elementFromPoint(spot.cx, spot.cy);
      return front === host || host.contains(front);
    }, taken);
    if (!at) {
      hide();
      return;
    }
    apply(at);
    taken = at.corner;    // réessayé en premier la prochaine fois : pas de saut d'un bord à l'autre
    current = video;
  }

  // la vidéo bouge (défilement, redimensionnement, plein écran) : la pastille la suit au lieu
  // d'attendre le prochain mouvement de souris, posée sur un emplacement devenu faux
  function follow() {
    if (queued || !current || !enabled) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (current && enabled) place(current);
    });
  }

  function hide() {
    if (host) host.style.display = "none";
    hovered = false;
    current = null;
  }

  function videos() {
    const now = performance.now();
    // liste gardée une seconde : la recherche en profondeur est trop coûteuse à chaque survol
    if (now - scanned < SCAN_MS && found.every((v) => v.isConnected)) return found;
    scanned = now;
    found = collect(document, [], { left: BUDGET });
    return found;
  }

  function videoUnder(x, y) {
    for (const v of videos()) {
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
    } else if (current && !hovered) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(hide, 1500);
    }
  }, { passive: true, capture: true });

  addEventListener("scroll", follow, { passive: true, capture: true });
  addEventListener("resize", follow, { passive: true });
  document.addEventListener("fullscreenchange", follow);

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
