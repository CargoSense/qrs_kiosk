const $ = (id) => document.getElementById(id);
let pin = sessionStorage.getItem("qrs-kiosk.pin") || "";
let entered = "";
let status = null;

async function api(method, path, data) {
  const res = await fetch(path, {
    method,
    headers: { "content-type": "application/json", "x-pin": pin },
    body: data ? JSON.stringify(data) : undefined,
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 403) {
    sessionStorage.removeItem("qrs-kiosk.pin");
    pin = "";
    gate();
    throw new Error("wrong PIN");
  }
  if (!res.ok) throw new Error(body.error || `${res.status}`);
  return body;
}

function say(id, text, kind = "ok") {
  const el = $(id);
  el.textContent = text;
  el.className = `msg ${kind}`;
}

function gate() {
  $("main").hidden = true;
  $("gate").hidden = false;
  entered = "";
  $("dots").textContent = "";
}

async function unlock() {
  pin = entered;
  try {
    await api("POST", "/api/settings", {});
  } catch (e) {
    $("gate-msg").textContent = "Wrong PIN";
    entered = "";
    $("dots").textContent = "";
    return;
  }
  sessionStorage.setItem("qrs-kiosk.pin", pin);
  open();
}

async function open() {
  $("gate").hidden = true;
  $("main").hidden = false;
  await refresh();
}

async function refresh() {
  status = await (await fetch("/api/status")).json();
  $("s-version").textContent = status.version;
  const n = status.network;
  $("s-network").textContent = n.connected === null ? "not managed here" : n.connected ? n.ssid || "connected" : "offline";
  $("s-ip").textContent = n.ip || "";
  $("s-scanner").textContent = status.scanner.connected ? status.scanner.name || "ready" : "none found";
  $("s-base").textContent = status.base;

  $("p-label").textContent = status.plate ? status.plate.label || "(no label)" : status.want_plate ? "waiting for a scan" : "none";
  $("p-url").textContent = status.plate?.url || "";

  if (document.activeElement?.tagName !== "INPUT") fill();

  paired();

  const u = status.update;
  $("u-current").textContent = u.current;
  $("u-available").textContent = u.available ? u.available.version : "none";
  $("u-state").textContent = u.state + (u.error ? ` (${u.error})` : "");
  $("u-apply").disabled = !u.available || u.state !== "idle";
}

document.querySelectorAll(".pad button").forEach((b) =>
  b.addEventListener("click", () => {
    const k = b.dataset.k;
    if (k === "clear") entered = entered.slice(0, -1);
    else if (k === "go") return unlock();
    else if (entered.length < 8) entered += k;
    $("dots").textContent = "•".repeat(entered.length);
    $("gate-msg").textContent = "";
  })
);

$("p-next").addEventListener("click", async () => {
  try {
    await api("POST", "/api/plate", { next: true });
    say("p-msg", "Scan the wall plate with the terminal's scanner.");
    await refresh();
  } catch (e) {
    say("p-msg", e.message, "error");
  }
});
$("p-clear").addEventListener("click", async () => {
  try {
    await api("POST", "/api/plate", { url: null });
    say("p-msg", "Cleared.");
    await refresh();
  } catch (e) {
    say("p-msg", e.message, "error");
  }
});

function fill() {
  $("f-name").value = status.name || "";
  $("f-base").value = status.base;
  $("f-idle").value = status.idle_seconds;
  $("f-pin").value = "";
}

$("f-cancel").addEventListener("click", () => {
  fill();
  say("f-msg", "");
});

$("f-save").addEventListener("click", async () => {
  const data = { name: $("f-name").value, base: $("f-base").value, idle_seconds: $("f-idle").value };
  if ($("f-pin").value) data.pin = $("f-pin").value;
  try {
    await api("POST", "/api/settings", data);
    if (data.pin) {
      pin = data.pin;
      sessionStorage.setItem("qrs-kiosk.pin", pin);
      $("f-pin").value = "";
    }
    say("f-msg", "Saved.");
    await refresh();
  } catch (e) {
    say("f-msg", e.message, "error");
  }
});

$("w-scan").addEventListener("click", async () => {
  $("w-nets").textContent = "Looking…";
  try {
    const { networks } = await api("GET", "/api/wifi");
    $("w-nets").replaceChildren();
    if (!networks.length) $("w-nets").textContent = "No networks listed.";
    for (const n of networks) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = `${n.ssid}  ${n.signal}%  ${n.security || "open"}`;
      b.addEventListener("click", () => {
        $("w-ssid").value = n.ssid;
        $("w-pass").focus();
      });
      $("w-nets").append(b);
    }
  } catch (e) {
    $("w-nets").textContent = e.message;
  }
});
$("w-join").addEventListener("click", async () => {
  say("w-msg", "Joining…", "");
  try {
    const r = await api("POST", "/api/wifi", { ssid: $("w-ssid").value, password: $("w-pass").value, hidden: $("w-hidden").checked });
    say("w-msg", r.message);
    await refresh();
  } catch (e) {
    say("w-msg", e.message, "error");
  }
});

function paired() {
  const b = status.bluetooth;
  const box = $("b-paired");
  box.replaceChildren();
  $("b-find").disabled = !b.available;
  if (!b.available) {
    box.textContent = "Bluetooth is not managed here.";
    return;
  }
  if (!b.paired.length) {
    box.textContent = "No scanner is paired.";
    return;
  }
  for (const d of b.paired) {
    const row = document.createElement("div");
    row.className = "row";
    const label = document.createElement("span");
    label.textContent = `${d.name}  ${d.connected ? "connected" : "not connected"}`;
    label.style.flex = "1";
    const forget = document.createElement("button");
    forget.type = "button";
    forget.className = "light";
    forget.textContent = "Forget";
    forget.addEventListener("click", async () => {
      say("b-msg", "Forgetting…", "");
      try {
        const r = await api("POST", "/api/bluetooth/forget", { mac: d.mac });
        say("b-msg", r.message);
        await refresh();
      } catch (e) {
        say("b-msg", e.message, "error");
      }
    });
    row.append(label, forget);
    box.append(row);
  }
}

$("b-find").addEventListener("click", async () => {
  $("b-devs").textContent = "Looking… this takes a few seconds.";
  $("b-find").disabled = true;
  say("b-msg", "");
  try {
    const { devices } = await api("POST", "/api/bluetooth/scan");
    $("b-devs").replaceChildren();
    if (!devices.length) $("b-devs").textContent = "Nothing found. Is the scanner in pairing mode?";
    for (const d of devices) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = `${d.name}${d.scanner ? "  (scanner)" : ""}${d.paired ? "  paired" : ""}`;
      b.addEventListener("click", async () => {
        say("b-msg", `Pairing ${d.name}…`, "");
        try {
          const r = await api("POST", "/api/bluetooth/pair", { mac: d.mac });
          say("b-msg", r.message);
          $("b-devs").replaceChildren();
          await refresh();
        } catch (e) {
          say("b-msg", e.message, "error");
        }
      });
      $("b-devs").append(b);
    }
  } catch (e) {
    $("b-devs").textContent = e.message;
  } finally {
    $("b-find").disabled = false;
  }
});

$("u-check").addEventListener("click", async () => {
  say("u-msg", "Checking…", "");
  try {
    const u = await api("POST", "/api/update/check");
    say("u-msg", u.available ? `Version ${u.available.version} is available.` : "Up to date.");
    await refresh();
  } catch (e) {
    say("u-msg", e.message, "error");
  }
});
$("u-apply").addEventListener("click", async () => {
  say("u-msg", "Installing. The terminal restarts when it is done.", "");
  try {
    await api("POST", "/api/update/apply");
    const poll = setInterval(async () => {
      await refresh().catch(() => clearInterval(poll));
      if (status.update.state === "idle") {
        clearInterval(poll);
        say("u-msg", status.update.error || "Done.", status.update.error ? "error" : "ok");
      }
    }, 3000);
  } catch (e) {
    say("u-msg", e.message, "error");
  }
});

$("d-reboot").addEventListener("click", async () => {
  try {
    await api("POST", "/api/reboot");
  } catch (e) {
    say("u-msg", e.message, "error");
  }
});

addEventListener("resize", () => document.activeElement?.scrollIntoView?.({ block: "center" }));
addEventListener("keydown", (e) => {
  if (e.target.tagName !== "INPUT") return;
  if (e.key === "Enter") e.target.blur();
  if (e.key === "Escape") {
    fill();
    e.target.blur();
  }
});

(async () => {
  const s = await (await fetch("/api/status")).json();
  if (s.pin_set && !pin) gate();
  else open();
})();
