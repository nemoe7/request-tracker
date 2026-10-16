"use strict";

/* Theme: System (default), Light, Dark, persisted per device. */
const THEMES = ["system", "light", "dark"];
const themeLabel = document.querySelector("#theme-label");

function applyThemeLabel() {
  if (!themeLabel) return;
  const theme = document.documentElement.dataset.theme || "system";
  themeLabel.textContent = theme[0].toUpperCase() + theme.slice(1);
}

document.querySelector("#theme-toggle")?.addEventListener("click", () => {
  const theme = document.documentElement.dataset.theme || "system";
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  document.documentElement.dataset.theme = next;
  localStorage.setItem("pwedepa-theme", next);
  applyThemeLabel();
});
applyThemeLabel();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

/* Tagline: asks "pwede pa...?" while loading, answers "pwede na!" when done. */
const taglineMarks = document.querySelector("#tagline-marks");
if (taglineMarks) {
  const frames = [".", "..", "...", "...?"];
  let frame = 0;
  const timer = setInterval(() => {
    frame = (frame + 1) % frames.length;
    taglineMarks.textContent = frames[frame];
  }, 450);
  window.addEventListener("load", () => {
    setTimeout(() => {
      clearInterval(timer);
      document.querySelector("#tagline").textContent = "pwede na!";
    }, 1200);
  });
}

/* WebAuthn helpers: the server speaks base64url JSON, the browser wants buffers. */
function toBuffer(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function fromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function creationOptions(options) {
  const publicKey = { ...options };
  publicKey.challenge = toBuffer(options.challenge);
  publicKey.user = { ...options.user, id: toBuffer(options.user.id) };
  if (options.excludeCredentials) {
    publicKey.excludeCredentials = options.excludeCredentials.map((item) => ({
      ...item, id: toBuffer(item.id),
    }));
  }
  return { publicKey };
}

function requestOptions(options) {
  const publicKey = { ...options, challenge: toBuffer(options.challenge) };
  if (options.allowCredentials) {
    publicKey.allowCredentials = options.allowCredentials.map((item) => ({
      ...item, id: toBuffer(item.id),
    }));
  }
  return { publicKey };
}

function credentialJson(credential) {
  const response = { clientDataJSON: fromBuffer(credential.response.clientDataJSON) };
  if (credential.response.attestationObject) {
    response.attestationObject = fromBuffer(credential.response.attestationObject);
  }
  if (credential.response.authenticatorData) {
    response.authenticatorData = fromBuffer(credential.response.authenticatorData);
    response.signature = fromBuffer(credential.response.signature);
    response.userHandle = credential.response.userHandle
      ? fromBuffer(credential.response.userHandle)
      : null;
  }
  return {
    id: credential.id,
    rawId: fromBuffer(credential.rawId),
    type: credential.type,
    response,
  };
}

function setStatus(message) {
  const status = document.querySelector("#status");
  if (status) status.textContent = message;
}

/* Frames without a WebAuthn delegation get a plain note, not a console error. */
function ceremonyError(error) {
  const blocked = error.name === "NotAllowedError" || error.name === "SecurityError"
    || String(error.message).includes("publickey-credentials");
  if (blocked) {
    return "Passkeys need a direct browser tab. Open this page outside the preview, or use the demo entry.";
  }
  return error.message;
}

async function runCeremony(startUrl, finishUrl, extra, create) {
  const start = await postJson(startUrl, extra);
  const options = create
    ? creationOptions(start.options)
    : requestOptions(start.options);
  const credential = create
    ? await navigator.credentials.create(options)
    : await navigator.credentials.get(options);
  return postJson(finishUrl, {
    ...extra,
    flow_id: start.flow_id,
    credential: credentialJson(credential),
  });
}

document.querySelector("#login-button")?.addEventListener("click", async () => {
  setStatus("Waiting for your passkey…");
  try {
    const done = await runCeremony("/login/options", "/login/finish", {}, false);
    window.location.assign(done.redirect || "/home");
  } catch (error) {
    setStatus(ceremonyError(error));
  }
});

document.querySelector("#enroll-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = document.querySelector("#token").value.trim();
  setStatus("Waiting for your passkey…");
  try {
    const done = await runCeremony(
      "/enroll/options", "/enroll/finish", { token }, true,
    );
    window.location.assign(done.redirect || "/home");
  } catch (error) {
    setStatus(ceremonyError(error));
  }
});

const tokenField = document.querySelector("#token");
if (tokenField) {
  tokenField.value = new URLSearchParams(window.location.search).get("token") || "";
}

document.querySelector("#add-passkey")?.addEventListener("click", async () => {
  setStatus("Waiting for your passkey…");
  try {
    await runCeremony("/auth/register/options", "/auth/register/finish", {}, true);
    window.location.reload();
  } catch (error) {
    setStatus(ceremonyError(error));
  }
});

document.querySelectorAll("[data-revoke-passkey]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await postJson(`/auth/passkeys/${button.dataset.revokePasskey}/revoke`, {});
      window.location.reload();
    } catch (error) {
      setStatus(error.message);
    }
  });
});

document.querySelector("#logout-button")?.addEventListener("click", async () => {
  const done = await postJson("/logout", {}).catch(() => ({ redirect: "/" }));
  window.location.assign(done.redirect || "/");
});
