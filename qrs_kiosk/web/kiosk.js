// The kiosk page: a sidebar that stays, and a frame that shows the QRS
// shell. The daemon decides what a scan means and tells this page what to
// do: navigate the frame, or hand the scan to the shell's open overlay. The
// shell tells this page where it is (the kiosk bridge in qrs), which the
// sidebar shows and which the daemon needs to route the next scan.

const frame = document.getElementById("frame");
const $ = (id) => document.getElementById(id);

let status = null;
let shell = {};
let ws = null;
let idleTimer = null;
let toastTimer = null;

function shellOrigin() {
  try {
    return new URL(status.base).origin;
  } catch {
    return null;
  }
}

function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  ws = new WebSocket(url);
  ws.addEventListener("open", () => {
    $("offline").hidden = true;
    send({ type: "hello" });
  });
  ws.addEventListener("message", (e) => {
    let msg;
    try {
      msg = JSON.parse(e.data);
    } catch {
      return;
    }
    handle(msg);
  });
  ws.addEventListener("close", () => {
    $("offline").hidden = false;
    setTimeout(connect, 1500);
  });
}

function send(msg) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

function handle(msg) {
  switch (msg.type) {
    case "status":
      status = msg;
      renderStatus();
      break;
    case "navigate":
      navigate(msg.url);
      break;
    case "scan":
      activity();
      frame.contentWindow?.postMessage({ type: "qrs:scan", payload: msg.payload, symbology: msg.symbology ?? null }, shellOrigin() ?? "/");
      break;
    case "toast":
      toast(msg.text, msg.kind);
      break;
  }
}

function navigate(url) {
  activity();
  shell = {};
  renderContext();
  frame.src = url;
}

function renderStatus() {
  const s = status;
  $("brand-name").textContent = s.name || "QR Sensor";
  const start = $("start");
  if (s.plate) {
    start.disabled = false;
    start.classList.remove("scan");
    start.textContent = "Start";
    $("hint").textContent = s.want_plate ? "Scan the wall plate" : s.plate.label || "";
  } else {
    start.disabled = true;
    start.classList.add("scan");
    start.textContent = "Scan the wall plate to start";
    $("hint").textContent = "";
  }

  const net = $("net");
  if (s.network.connected === null) {
    net.textContent = "n/a";
    net.className = "";
  } else if (s.network.connected) {
    net.textContent = s.network.ssid || "connected";
    net.title = s.network.ip || "";
    net.className = "";
  } else {
    net.textContent = "offline";
    net.className = "bad";
  }

  const scanner = $("scanner");
  scanner.textContent = s.scanner.connected ? "ready" : "none";
  scanner.title = s.scanner.name || "";
  scanner.className = s.scanner.connected ? "" : "bad";

  const version = $("version");
  const available = s.update?.available;
  version.textContent = available ? `${s.version} → ${available.version}` : s.version;
  version.className = available ? "update" : "";
  resetIdle();
}

function renderContext() {
  const c = $("context");
  c.replaceChildren();
  const add = (cls, text) => {
    if (!text) return;
    const el = document.createElement("span");
    el.className = cls;
    el.textContent = text;
    c.append(el);
  };
  add("where", [shell.brand, shell.sensor].filter(Boolean).join(" · "));
  add("applet", shell.applet);
  add("screen", shell.screen);
  if (shell.scanning) add("scanning", "Scanning…");
}

function toast(text, kind = "info") {
  const el = $("toast");
  el.textContent = text;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 5000);
}

// Idle: with nothing scanned and the shell not moving for a while, go back
// to the wall plate's menu, or the home page when there is none.
function resetIdle() {
  clearTimeout(idleTimer);
  const seconds = status?.idle_seconds ?? 0;
  if (seconds > 0) idleTimer = setTimeout(goHome, seconds * 1000);
}

function activity() {
  resetIdle();
}

function goHome() {
  const url = status?.plate?.url ?? "/home";
  if (frame.src !== url && !frame.src.endsWith(url)) navigate(url);
  else resetIdle();
}

addEventListener("message", (e) => {
  if (e.source !== frame.contentWindow) return;
  const origin = shellOrigin();
  if (!origin || e.origin !== origin) return;
  const m = e.data;
  if (m?.type !== "qrs:state") return;
  shell = m;
  renderContext();
  send({ type: "state", scanning: Boolean(m.scanning), url: m.url ?? null, applet: m.applet ?? null, screen: m.screen ?? null });
  activity();
});

function tick() {
  const now = new Date();
  $("time").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  $("date").textContent = now.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}
tick();
setInterval(tick, 1000);

$("start").addEventListener("click", () => send({ type: "start" }));
$("home").addEventListener("click", () => send({ type: "home" }));
$("gear").addEventListener("click", () => navigate("/settings"));
document.addEventListener("pointerdown", activity, { capture: true });

connect();
