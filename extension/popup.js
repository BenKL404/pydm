const api = globalThis.browser ?? chrome;
const $ = (id) => document.getElementById(id);

function human(n) {
  if (!n) return "";
  const units = ["o", "Ko", "Mo", "Go"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function feedback(btn, reply) {
  const old = btn.textContent;
  btn.textContent = reply?.ok ? "✓ Envoyé" : "✗ Échec";
  setTimeout(() => { btn.textContent = old; }, 2000);
}

(async () => {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });

  const ping = await api.runtime.sendMessage({ type: "ping" });
  $("status").textContent = ping?.ok ? (ping.ytdlp ? "Connecté ✓" : "Connecté (sans yt-dlp)") : "Non connecté";
  $("status").className = ping?.ok ? "ok" : "err";
  $("help").style.display = ping?.ok ? "none" : "block";

  const s = await api.storage.local.get(["intercept", "videoButton"]);
  for (const key of ["intercept", "videoButton"]) {
    $(key).checked = s[key] !== false;
    $(key).addEventListener("change", (e) => api.storage.local.set({ [key]: e.target.checked }));
  }

  $("page").addEventListener("click", async (e) => {
    feedback(e.target, await api.runtime.sendMessage({ type: "pageVideo", tabId: tab.id, pageUrl: tab.url }));
  });
  $("open").addEventListener("click", () => api.runtime.sendMessage({ type: "show" }));

  const { media = [] } = await api.runtime.sendMessage({ type: "media", tabId: tab.id });
  if (media.length) {
    const ul = $("media");
    ul.textContent = "";
    for (const m of media) {
      const li = document.createElement("li");
      const info = document.createElement("div");
      info.className = "info";
      const name = document.createElement("div");
      name.className = "name";
      name.textContent = decodeURIComponent(new URL(m.url).pathname.split("/").pop() || m.url);
      name.title = m.url;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = [m.type, human(m.size)].filter(Boolean).join(" · ");
      info.append(name, meta);
      const btn = document.createElement("button");
      btn.textContent = "⬇";
      btn.title = "Télécharger avec PyDM";
      btn.addEventListener("click", async () => {
        const kind = m.type === "HLS" || m.type === "DASH" ? "video" : "file";
        feedback(btn, await api.runtime.sendMessage({
          type: "download", job: { url: m.url, referer: tab.url, kind },
        }));
      });
      li.append(info, btn);
      ul.append(li);
    }
  }
})();
