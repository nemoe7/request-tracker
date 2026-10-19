"use strict";

/* A page swap reruns this whole script, so each boot first aborts the
   listeners the last one added. Nothing binds twice, and a plain page load
   without a swap works the same. */
window.pwedepaBoot = function pwedepaBoot() {
  window.pwedepaLifecycle?.abort();
  const lifecycle = (window.pwedepaLifecycle = new AbortController());
  const listen = { signal: lifecycle.signal };

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

/* Notification switches save as they flip, so the
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
          status.textContent = "Could not save the switch. Check the connection.";
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
  }, listen);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  }, listen);
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

/* Prefetch linked pages on intent, so navigation answers at once. One
   listener reads each hover, because a page swap brings new links. */
const prefetched = new Set();
document.addEventListener(
  "pointerover",
  (event) => {
    const link = event.target.closest?.('a[href^="/"]');
    if (!link) return;
    const href = link.getAttribute("href");
    if (!href || prefetched.has(href)) return;
    prefetched.add(href);
    const hint = document.createElement("link");
    hint.rel = "prefetch";
    hint.href = href;
    document.head.appendChild(hint);
  },
  listen
, listen);

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
    const busy = (on) => {
      if (on) inspector.setAttribute("aria-busy", "true");
      else inspector.removeAttribute("aria-busy");
      inspector.classList.toggle("is-loading", on);
    };
    busy(true);
    try {
      const response = await fetch(href);
      if (!response.ok) throw new Error(`card ${response.status}`);
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const card = page.querySelector(".workspace-grid .inspector") ?? page.querySelector(".narrow");
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
      // A failed fetch keeps the reader on the page and offers the record as its own page.
      inspector.innerHTML = "";
      const failed = document.createElement("p");
      failed.className = "muted";
      const link = document.createElement("a");
      link.href = href;
      link.textContent = "Open it as a page";
      failed.append("This record did not load. ", link, ".");
      inspector.append(failed);
      inspector.classList.add("is-main");
      workspaceGrid.classList.add("is-open", "is-main");
    } finally {
      busy(false);
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

  // The bar offers a new request, and it opens in the pane like a record does.
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href$="/requests/new"]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    openCard(link.href, null, true);
  }, listen);

  // The rows are replaced when a filter swaps, so one listener reads each click.
  workspaceGrid.addEventListener("click", (event) => {
    const link = event.target.closest(".record-table tbody a[href]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    if (!link.matches("a[href*='selected='], a[href*='/record/']")) return;
    event.preventDefault();
    openCard(link.href, link.closest("tr"), true);
  });

  const basePath = new URL(baseHref).pathname;
  window.addEventListener("popstate", () => {
    const url = window.location.href;
    if (url === baseHref) {
      closeCard();
    } else if (cardHrefs.has(url)) {
      const row = rowLinks.find((link) => link.href === url)?.closest("tr");
      openCard(url, row, false);
    } else if (new URL(url).pathname === basePath) {
      // The filters own a change on this page, and they repaint the panels.
      return;
    } else {
      window.location.reload();
    }
  }, listen);
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
  if (!response.ok) throw new Error(data.error || "The action failed.");
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

/* An Admin row opens its page inside Settings, so the rail and the group stay.
   A form inside that pane posts the same way, then shows the answer in place. */
const drill = document.querySelector("[data-admin-drill]");
const adminList = document.querySelector("[data-admin-list]");

if (drill && adminList) {
  const paneFor = (doc) => {
    const page = doc.querySelector(".admin-page");
    if (!page) return null;
    page.querySelectorAll(".page-head").forEach((head) => head.remove());
    const back = document.createElement("button");
    back.type = "button";
    back.className = "set-row link-row set-back";
    back.textContent = "Back to Admin";
    back.addEventListener("click", () => {
      drill.hidden = true;
      drill.replaceChildren();
      adminList.hidden = false;
      document.querySelector("[data-admin-pane]")?.focus();
    });
    return [back, ...page.childNodes];
  };

  const show = async (url, options) => {
    const response = await fetch(url, options);
    if (!response.ok) return;
    const nodes = paneFor(new DOMParser().parseFromString(await response.text(), "text/html"));
    if (!nodes) return;
    drill.replaceChildren(...nodes);
    drill.hidden = false;
    adminList.hidden = true;
    drill.querySelector("button, a, input, select")?.focus();
  };

  document.querySelectorAll("[data-admin-pane]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      show(link.href);
    });
  });

  drill.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    show(form.action, { method: "POST", body: new FormData(form) });
  });
}

/* The time format saves the moment it is picked, so the page never reloads and
   the buttons stay under the cursor. */
const clockForm = document.querySelector("[data-clock-form]");

if (clockForm) {
  const note = document.querySelector("[data-clock-status]");
  const buttons = [...clockForm.querySelectorAll("button[name=clock]")];
  const mark = (value) => {
    buttons.forEach((button) => {
      button.classList.toggle("is-active", button.value === value);
    });
  };
  clockForm.addEventListener("click", async (event) => {
    const button = event.target.closest("button[name=clock]");
    if (!button) return;
    event.preventDefault();
    const previous = buttons.find((item) => item.classList.contains("is-active"));
    mark(button.value);
    try {
      const response = await fetch(clockForm.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new URLSearchParams({ clock: button.value }),
      });
      if (!response.ok) throw new Error("Could not save the time format.");
      if (note) note.textContent = "Time format saved.";
    } catch {
      if (previous) mark(previous.value);
      if (note) note.textContent = "Could not save the format. Check the connection.";
    }
  });
}

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
      if (!response.ok) throw new Error("Could not save the text size.");
      if (note) note.textContent = "";
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

// A filter swap replaces the form, so one listener reads each change.
document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
  form.classList.add("is-auto");
});
document.addEventListener("change", (event) => {
  const form = event.target.closest?.("form[data-auto-submit]");
  if (form) form.requestSubmit();
}, listen);

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
  }, listen);

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
  }, listen);

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
  }, listen);
  document.addEventListener("focusin", (event) => {
    if (event.target instanceof HTMLTextAreaElement) fit(event.target);
  }, listen);
  window.addEventListener("resize", fitAll, listen);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fitAll, listen);
  } else {
    fitAll();
  }
})();

// The settings rail swaps panes in place on a wide screen. A plain hash link
// would scroll the page and add a history entry, so the rail replaces the hash.
(() => {
  const rail = document.querySelector(".settings-nav");
  if (!rail) return;
  const wide = window.matchMedia("(min-width: 640px)");
  rail.addEventListener("click", (event) => {
    if (!wide.matches) return;
    const link = event.target.closest('a[href^="#"]');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const y = window.scrollY;
    location.replace(link.getAttribute("href"));
    window.scrollTo(0, y);
  });
})();

// The workspace filters narrow one list. A full load would blink and reset the
// scroll, so the two panels swap in place and the rail keeps its place.
(() => {
  const grid = document.querySelector(".workspace-grid");
  if (!grid) return;
  const filters = grid.querySelector(":scope > .panel.filters");
  const records = grid.querySelector(":scope > .panel.records");
  if (!filters || !records) return;
  let run = 0;

  const keepSeg = (oldSeg, freshSeg) => {
    if (!oldSeg || !freshSeg) return;
    oldSeg.dataset.active = freshSeg.dataset.active;
    const links = oldSeg.querySelectorAll("a");
    freshSeg.querySelectorAll("a").forEach((fresh, index) => {
      if (links[index]) links[index].className = fresh.className;
    });
    freshSeg.replaceWith(oldSeg);
  };

  const repaint = (page) => {
    const nextFilters = page.querySelector(".workspace-grid > .panel.filters");
    const nextRecords = page.querySelector(".workspace-grid > .panel.records");
    if (!nextFilters || !nextRecords) return false;
    const seg = filters.querySelector(".seg");
    const open = filters.querySelector("#filters-toggle")?.checked;
    filters.innerHTML = nextFilters.innerHTML;
    records.innerHTML = nextRecords.innerHTML;
    keepSeg(seg, filters.querySelector(".seg"));
    const toggle = filters.querySelector("#filters-toggle");
    if (toggle && open) toggle.checked = true;
    for (const panel of [filters, records]) {
      panel.classList.remove("is-swapping");
      void panel.offsetWidth;
      panel.classList.add("is-swapping");
    }
    const status = grid.querySelector("[data-filter-status]");
    if (status) {
      const shown = records.querySelectorAll("tbody tr").length;
      status.textContent = shown ? `${shown} rows shown.` : "No rows match these filters.";
    }
    return true;
  };

  const load = async (url, remember) => {
    const token = ++run;
    try {
      const response = await fetch(url, { headers: { Accept: "text/html" } });
      if (!response.ok) throw new Error(`filters ${response.status}`);
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      if (token !== run || !repaint(page)) return;
      if (remember) history.pushState(null, "", url);
    } catch {
      window.location.assign(url);
    }
  };

  filters.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, window.location.href);
    if (url.pathname !== window.location.pathname || url.hash) return;
    event.preventDefault();
    load(url, true);
  });

  // The status picker sends a GET, and it narrows the same list.
  grid.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-auto-submit]");
    if (!form || (form.method || "get").toLowerCase() !== "get") return;
    event.preventDefault();
    load(new URL(form.action + "?" + new URLSearchParams(new FormData(form))), true);
  });

  const path = window.location.pathname;
  window.addEventListener("popstate", () => {
    if (window.location.pathname !== path) return;
    load(window.location.href, false);
  }, listen);
})();
  /* Top-level pages swap into the same shell, so the top bar never redraws,
     the page never blanks, and the scroll stays put. A plain link still
     loads a whole page when this script is absent. */
  (() => {
    const main = document.querySelector("main.wrap");
    if (!main || !window.fetch || !window.DOMParser) return;
    let run = 0;

    const swap = async (href, remember) => {
      const token = ++run;
      try {
        const response = await fetch(href, { headers: { Accept: "text/html" } });
        if (!response.ok) throw new Error(`page ${response.status}`);
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        const nextMain = page.querySelector("main.wrap");
        if (!nextMain || token !== run) throw new Error("no page");
        main.className = nextMain.className;
        main.replaceChildren(...nextMain.childNodes);
        // The bar carries its own state and controls, so the fresh one replaces
        // it whole. A leftover copy would bind the same button twice.
        const bar = document.querySelector("header.topbar");
        const nextBar = page.querySelector("header.topbar");
        if (bar && nextBar) bar.replaceWith(nextBar);
        document.title = page.title;
        document.body.className = page.body.className;
        if (remember) history.pushState(null, "", href);
        window.scrollTo(0, 0);
        // A reader who lands on a new page keeps a starting point for the
        // keyboard, and the screen reader reads from there.
        main.setAttribute("tabindex", "-1");
        main.focus({ preventScroll: true });
        window.pwedepaBoot();
      } catch {
        window.location.assign(href);
      }
    };

    document.addEventListener(
      "click",
      (event) => {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest("a[href]");
        if (!link || link.target || link.hasAttribute("download")) return;
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || url.hash) return;
        if (url.pathname === window.location.pathname && url.search === window.location.search) return;
        if (link.dataset.fullLoad !== undefined) return;
        event.preventDefault();
        swap(url.href, true);
      },
      listen
    );

    window.addEventListener("popstate", () => swap(window.location.href, false), listen);
  })();

};

window.pwedepaBoot();
