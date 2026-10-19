"use strict";

/* Theme: System (default), Light, Dark. A signed-in account holds the choice;
   a signed-out page or a frozen demo keeps it in the browser. */
const themeButtons = document.querySelectorAll("[data-theme-set]");

function markThemeButtons() {
  const theme = document.documentElement.dataset.theme || "system";
  themeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.themeSet === theme);
  });
}

function setTheme(theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  localStorage.setItem("pwedepa-theme", theme);
  if (root.dataset.themeScope === "account") {
    fetch(root.dataset.themeEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ theme }),
    }).catch(() => {});
  }
  markThemeButtons();
}

/* Notification switches save as they flip, the way iOS Settings does, so the
   page never reloads and the button only exists for a browser without JS. */
document.querySelectorAll("form[data-autosave]").forEach((form) => {
  form.classList.add("is-auto");
  const status = document.querySelector("[data-autosave-status]");
  let saved = new FormData(form);
  let queue = Promise.resolve();
  form.addEventListener("change", () => {
    const body = new URLSearchParams(new FormData(form));
    queue = queue
      .then(() =>
        fetch(form.action, {
          method: "POST",
          headers: { "X-Autosave": "1" },
          body,
        }),
      )
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        saved = new FormData(form);
        if (status) status.textContent = "";
      })
      .catch(() => {
        form.querySelectorAll("input[type=checkbox]").forEach((box) => {
          box.checked = saved.has(box.name);
        });
        if (status) {
          status.textContent = "That switch did not save. Check the connection.";
          status.scrollIntoView({ block: "nearest" });
        }
      });
  });
});

themeButtons.forEach((button) => {
  button.addEventListener("click", () => setTheme(button.dataset.themeSet));
});
markThemeButtons();

/* The animated icon is 1.2 MB. Fetch it on the first sign of intent, never
   while a page is still loading, and only swap it in once it can paint. */
const appIcon = document.querySelector(".app-icon");
const animatedIcon = appIcon?.querySelector(".icon-animated[data-src]");
if (appIcon && animatedIcon) {
  const loadAnimatedIcon = () => {
    animatedIcon.addEventListener("load", () => appIcon.classList.add("is-ready"));
    animatedIcon.src = animatedIcon.dataset.src;
    delete animatedIcon.dataset.src;
  };
  ["pointerenter", "focusin", "touchstart"].forEach((type) => {
    appIcon.addEventListener(type, loadAnimatedIcon, { once: true });
  });
}

const userMenuButton = document.querySelector("#user-menu-button");
const userMenu = document.querySelector("#user-menu");
if (userMenuButton && userMenu) {
  const closeMenu = () => {
    userMenu.hidden = true;
    userMenuButton.setAttribute("aria-expanded", "false");
  };
  userMenuButton.addEventListener("click", () => {
    const opening = userMenu.hidden;
    userMenu.hidden = !opening;
    userMenuButton.setAttribute("aria-expanded", String(opening));
  });
  document.addEventListener("click", (event) => {
    if (!userMenu.hidden && !event.target.closest(".user-menu-wrap")) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

/* Prefetch linked pages on intent, so navigation answers at once. */
const prefetched = new Set();
document.querySelectorAll('a[href^="/"]').forEach((link) => {
  link.addEventListener("pointerenter", () => {
    const href = link.getAttribute("href");
    if (!href || prefetched.has(href)) return;
    prefetched.add(href);
    const hint = document.createElement("link");
    hint.rel = "prefetch";
    hint.href = href;
    document.head.appendChild(hint);
  }, { once: true });
});

/* Workspace: a row opens the centre card in place, and its link stays real. */
const workspaceGrid = document.querySelector(".workspace-grid");
if (workspaceGrid) {
  const inspector = workspaceGrid.querySelector(".inspector");
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  const baseHref = window.location.href;
  const baseCard = inspector.innerHTML;
  const rowLinks = [
    ...workspaceGrid.querySelectorAll(".record-table tbody a[href*='selected=']"),
    ...workspaceGrid.querySelectorAll(".record-table tbody a[href*='/record/']"),
  ];
  const cardHrefs = new Set(rowLinks.map((link) => link.href));
  let closeToken = 0;

  const revealCard = () => {
    inspector.classList.remove("is-leaving");
    if (calm.matches) return;
    inspector.classList.add("is-entering");
    inspector.addEventListener(
      "animationend",
      () => inspector.classList.remove("is-entering"),
      { once: true }
    );
  };

  const hideCard = () => {
    inspector.innerHTML = baseCard;
    inspector.classList.remove("is-main");
    workspaceGrid.classList.remove("is-open", "is-main");
    workspaceGrid.querySelector("tr.is-selected")?.classList.remove("is-selected");
  };

  const openCard = async (href, row, remember) => {
    try {
      const response = await fetch(href);
      if (!response.ok) throw new Error(`card ${response.status}`);
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const card = page.querySelector(".workspace-grid .inspector");
      if (!card || !inspector) throw new Error("no card");
      closeToken += 1;
      inspector.innerHTML = card.innerHTML;
      inspector.classList.add("is-main");
      workspaceGrid.classList.add("is-open", "is-main");
      workspaceGrid.querySelector("tr.is-selected")?.classList.remove("is-selected");
      row?.classList.add("is-selected");
      revealCard();
      if (remember) history.pushState(null, "", href);
      if (window.innerWidth < 900) {
        inspector.scrollIntoView({ behavior: calm.matches ? "auto" : "smooth", block: "start" });
      }
    } catch {
      window.location.assign(href);
    }
  };

  const closeCard = () => {
    const token = ++closeToken;
    const finish = () => {
      if (token !== closeToken) return;
      inspector.classList.remove("is-leaving");
      hideCard();
    };
    if (calm.matches || !workspaceGrid.classList.contains("is-open")) {
      finish();
      return;
    }
    inspector.classList.add("is-leaving");
    inspector.addEventListener("animationend", finish, { once: true });
  };

  rowLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      openCard(link.href, link.closest("tr"), true);
    });
  });

  window.addEventListener("popstate", () => {
    if (window.location.href === baseHref) {
      closeCard();
    } else if (cardHrefs.has(window.location.href)) {
      const row = rowLinks.find((link) => link.href === window.location.href)?.closest("tr");
      openCard(window.location.href, row, false);
    } else {
      window.location.reload();
    }
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
    return "Passkeys need a direct browser tab. Open this page outside the preview, or open the demo site.";
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
    window.location.assign(done.redirect || "/");
  } catch (error) {
    setStatus(ceremonyError(error));
  }
});

document.querySelector("#enroll-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = document.querySelector("#token").value.trim();
  const username = document.querySelector("#username").value.trim();
  const display_name = document.querySelector("#display-name").value.trim();
  setStatus("Waiting for your passkey…");
  try {
    const done = await runCeremony(
      "/enroll/options", "/enroll/finish", { token, username, display_name }, true,
    );
    window.location.assign(done.redirect || "/");
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

const fontForm = document.querySelector("[data-font-size-form]");

if (fontForm) {
  fontForm.classList.add("is-auto");
  const range = fontForm.querySelector("[data-font-size-range]");
  const number = fontForm.querySelector("[data-font-size-number]");
  const note = document.querySelector("[data-font-size-status]");
  const apply = (value) => {
    document.documentElement.style.setProperty("--font-scale", String(value / 100));
  };
  const valid = (value) => Number.isInteger(value) && value >= 85 && value <= 130;
  range.addEventListener("input", () => {
    number.value = range.value;
    apply(Number(range.value));
  });
  number.addEventListener("input", () => {
    const value = Number(number.value);
    if (valid(value)) apply(value);
  });
  const settle = async () => {
    const value = Math.min(130, Math.max(85, Number(number.value) || 100));
    number.value = value;
    range.value = value;
    apply(value);
    try {
      const body = new FormData(fontForm);
      body.set("font_size", String(value));
      const response = await fetch(fontForm.action, {
        method: "POST",
        body,
        headers: { "X-Requested-With": "fetch" },
      });
      if (!response.ok) throw new Error("The text size did not save.");
      if (note) note.textContent = `Text size ${value}%.`;
    } catch (error) {
      if (note) note.textContent = error.message;
    }
  };
  range.addEventListener("change", settle);
  number.addEventListener("change", settle);
}

document.querySelector("#logout-button")?.addEventListener("click", async () => {
  const done = await postJson("/logout", {}).catch(() => ({ redirect: "/" }));
  window.location.assign(done.redirect || "/");
});

document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
  form.classList.add("is-auto");
  form.addEventListener("change", () => form.requestSubmit());
});

/* Modal: one manager for every custom dialog. An opener carries
   data-modal-open="<id>", and a close control carries data-modal-close. */
(() => {
  let active = null;
  let returnFocus = null;

  function focusable(modal) {
    return [
      ...modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ].filter((node) => !node.disabled && node.offsetParent !== null);
  }

  function open(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    active = modal;
    returnFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("has-modal");
    const first = focusable(modal)[0];
    if (first) first.focus();
  }

  function close() {
    if (!active) return;
    active.hidden = true;
    document.body.classList.remove("has-modal");
    active = null;
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
    returnFocus = null;
  }

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-modal-open]");
    if (opener) {
      event.preventDefault();
      open(opener.dataset.modalOpen);
      return;
    }
    if (event.target.closest("[data-modal-close]")) {
      event.preventDefault();
      close();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!active) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusable(active);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  const openOnLoad = document.querySelector(".modal:not([hidden])");
  if (openOnLoad) open(openOnLoad.id);

  window.PwedePaModal = { open, close };
})();

// Textareas grow with their wrapped text, so a drag handle never shows.
(() => {
  const fit = (element) => {
    if (!(element instanceof HTMLTextAreaElement) || !element.offsetParent) return;
    element.style.height = "auto";
    const border = element.offsetHeight - element.clientHeight;
    element.style.height = `${element.scrollHeight + border}px`;
  };
  const fitAll = () => document.querySelectorAll("textarea").forEach(fit);

  document.addEventListener("input", (event) => {
    if (event.target instanceof HTMLTextAreaElement) fit(event.target);
  });
  document.addEventListener("focusin", (event) => {
    if (event.target instanceof HTMLTextAreaElement) fit(event.target);
  });
  window.addEventListener("resize", fitAll);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fitAll);
  } else {
    fitAll();
  }
})();
