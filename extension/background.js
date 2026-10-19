// PyDM – extension : intercepte les téléchargements, détecte les vidéos et
// envoie tout à PyDM par la messagerie native (hôte « com.pydm.host »).
const api = globalThis.browser ?? chrome;
const HOST = "com.pydm.host";
const DEFAULTS = { intercept: true, videoButton: true, minSizeKB: 100 };
const VIDEO_HOSTS = /(^|\.)(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|dai\.ly|twitch\.tv|tiktok\.com|instagram\.com|facebook\.com|fb\.watch|x\.com|twitter\.com|reddit\.com|soundcloud\.com|bilibili\.com|rumble\.com|odysee\.com|bandcamp\.com|arte\.tv|france\.tv|streamable\.com)$/i;
const IGNORED_MEDIA_HOSTS = /(^|\.)(googlevideo\.com|fbcdn\.net|cdninstagram\.com)$/i;
const passThrough = new Set();   // URLs relancées dans le navigateur (PyDM indisponible)

async function settings() {
  return { ...DEFAULTS, ...(await api.storage.local.get(Object.keys(DEFAULTS))) };
}

function hostOf(url) {
  try { return new URL(url).hostname; } catch { return ""; }
}

async function cookieHeader(url) {
  try {
    const cookies = await api.cookies.getAll({ url });
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    return "";
  }
}

async function sendToPyDM({ url, referer, filename, kind = "auto" }) {
  const headers = { "User-Agent": navigator.userAgent };
  if (referer && /^https?:/.test(referer)) headers.Referer = referer;
  const cookie = await cookieHeader(url);
  if (cookie) headers.Cookie = cookie;
  const reply = await api.runtime.sendNativeMessage(HOST, { action: "add", url, headers, filename, kind });
  if (!reply?.ok) throw new Error(reply?.error || "PyDM n'a pas répondu");
  return reply;
}

function flashBadge(text, color) {
  api.action.setBadgeBackgroundColor({ color });
  api.action.setBadgeText({ text });
  setTimeout(() => api.action.setBadgeText({ text: "" }), 2500);
}

// --- 1. Interception des téléchargements du navigateur ---------------------
api.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/.test(url)) return;                 // blob:, data:… restent au navigateur
  if (passThrough.delete(url)) return;
  const s = await settings();
  if (!s.intercept) return;
  if (item.totalBytes > 0 && item.totalBytes < s.minSizeKB * 1024) return;

  try { await api.downloads.cancel(item.id); } catch {}
  try { await api.downloads.erase({ id: item.id }); } catch {}
  const filename = (item.filename || "").split(/[\\/]/).pop() || undefined;
  try {
    await sendToPyDM({ url, referer: item.referrer, filename, kind: "file" });
    flashBadge("✓", "#188038");
  } catch (e) {
    console.warn("PyDM indisponible, téléchargement rendu au navigateur :", e);
    passThrough.add(url);
    api.downloads.download({ url });
    flashBadge("!", "#d93025");
  }
});

// --- 2. Détection des flux vidéo / audio de chaque onglet ------------------
async function getMedia(tabId) {
  const key = `m_${tabId}`;
  return (await api.storage.session.get(key))[key] || [];
}

async function setMedia(tabId, list) {
  await api.storage.session.set({ [`m_${tabId}`]: list });
  api.action.setBadgeBackgroundColor({ color: "#1a73e8", tabId });
  api.action.setBadgeText({ text: list.length ? String(list.length) : "", tabId });
}

api.webRequest.onHeadersReceived.addListener(
  (det) => {
    if (det.tabId < 0 || IGNORED_MEDIA_HOSTS.test(hostOf(det.url))) return;
    const header = (n) => det.responseHeaders?.find((h) => h.name.toLowerCase() === n)?.value || "";
    const ctype = header("content-type").toLowerCase();
    // les lecteurs chargent par plages (206) : la taille totale est dans Content-Range
    const total = header("content-range").match(/\/(\d+)\s*$/);
    const size = total ? parseInt(total[1], 10) : parseInt(header("content-length"), 10) || 0;
    const path = new URL(det.url).pathname.toLowerCase();
    let type = null;
    if (path.endsWith(".m3u8") || ctype.includes("mpegurl")) type = "HLS";
    else if (path.endsWith(".mpd") || ctype.includes("dash+xml")) type = "DASH";
    else if (/^(video|audio)\//.test(ctype) && !ctype.includes("mp2t") && size > 1_000_000 && (det.statusCode === 200 || det.statusCode === 206))
      type = ctype.startsWith("video") ? "Vidéo" : "Audio";
    if (!type) return;
    (async () => {
      const list = await getMedia(det.tabId);
      if (list.some((m) => m.url === det.url) || list.length >= 30) return;
      list.push({ url: det.url, type, size, referer: det.documentUrl || det.initiator || "" });
      await setMedia(det.tabId, list);
    })();
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"]
);

api.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url) setMedia(tabId, []);
});
api.tabs.onRemoved.addListener((tabId) => api.storage.session.remove(`m_${tabId}`));

// Choisit quoi télécharger pour « la vidéo de cette page ».
async function resolveVideo(tabId, pageUrl, src) {
  if (VIDEO_HOSTS.test(hostOf(pageUrl))) return { url: pageUrl, kind: "video" };
  if (src && /^https?:/.test(src)) return { url: src, referer: pageUrl, kind: "auto" };
  const media = tabId >= 0 ? await getMedia(tabId) : [];
  const stream = media.find((m) => m.type === "HLS" || m.type === "DASH") || media[0];
  if (stream) return { url: stream.url, referer: pageUrl, kind: stream.type === "Vidéo" || stream.type === "Audio" ? "file" : "video" };
  return { url: pageUrl, kind: "video" };   // yt-dlp tente son extracteur générique
}

// --- 3. Menu du clic droit -------------------------------------------------
api.runtime.onInstalled.addListener(async () => {
  await api.contextMenus.removeAll();
  api.contextMenus.create({ id: "pydm-link", title: "Télécharger avec PyDM", contexts: ["link"] });
  api.contextMenus.create({ id: "pydm-media", title: "Télécharger ce média avec PyDM", contexts: ["video", "audio", "image"] });
  api.contextMenus.create({ id: "pydm-page", title: "Télécharger la vidéo de cette page avec PyDM", contexts: ["page", "frame"] });
});

api.contextMenus.onClicked.addListener(async (info, tab) => {
  const pageUrl = info.frameUrl || info.pageUrl || tab?.url;
  let job;
  if (info.menuItemId === "pydm-link") job = { url: info.linkUrl, referer: pageUrl, kind: "auto" };
  else if (info.menuItemId === "pydm-media" && info.mediaType === "image") job = { url: info.srcUrl, referer: pageUrl, kind: "file" };
  else job = await resolveVideo(tab?.id ?? -1, pageUrl, info.srcUrl);
  try {
    await sendToPyDM(job);
    flashBadge("✓", "#188038");
  } catch (e) {
    console.warn(e);
    flashBadge("!", "#d93025");
  }
});

// --- 4. Messages du bouton flottant et de la fenêtre de l'extension -------
api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "video") {
        const job = await resolveVideo(sender.tab?.id ?? -1, msg.pageUrl, msg.src);
        await sendToPyDM(job);
        return { ok: true };
      }
      if (msg.type === "download") {
        await sendToPyDM(msg.job);
        return { ok: true };
      }
      if (msg.type === "pageVideo") {
        await sendToPyDM(await resolveVideo(msg.tabId, msg.pageUrl, null));
        return { ok: true };
      }
      if (msg.type === "media") return { ok: true, media: await getMedia(msg.tabId) };
      if (msg.type === "ping") return await api.runtime.sendNativeMessage(HOST, { action: "ping" });
      if (msg.type === "show") return await api.runtime.sendNativeMessage(HOST, { action: "show" });
      return { ok: false, error: "message inconnu" };
    } catch (e) {
      return { ok: false, error: String(e?.message || e) };
    }
  })().then(sendResponse);
  return true;   // réponse asynchrone
});
