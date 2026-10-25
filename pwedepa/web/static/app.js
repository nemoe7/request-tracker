"use strict";

/* Each page swap reruns this boot function and aborts prior listeners first.
   Nothing binds twice, and a full page load without JS swap behaves the same. */

/* Recipe: nuu relative timestamps */
window.relativeTime = function relativeTime(
  value,
  { compact = false, includeSeconds = false, now = Date.now() } = {},
) {
  const stamp = value instanceof Date ? value.getTime() : new Date(value).getTime();
  const seconds = Math.max(0, Math.floor((now - stamp) / 1000));
  if (includeSeconds) {
    if (seconds < 1) return compact ? "now" : "just now";
    if (seconds < 60) {
      return compact
        ? `${seconds}s ago`
        : seconds === 1
          ? "a second ago"
          : `${seconds} seconds ago`;
    }
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return compact ? "now" : "just now";
  if (minutes < 60) {
    return compact
      ? `${minutes}min ago`
      : minutes === 1
        ? "a minute ago"
        : `${minutes} minutes ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return compact ? `${hours}h ago` : hours === 1 ? "an hour ago" : `${hours} hours ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) return compact ? `${days}d ago` : days === 1 ? "yesterday" : `${days} days ago`;
  if (days < 30) {
    const weeks = Math.floor(days / 7);
    return compact ? `${weeks}wk ago` : weeks === 1 ? "last week" : `${weeks} weeks ago`;
  }
  if (days < 365) {
    const months = Math.max(1, Math.floor(days / 30));
    return compact ? `${months}mo ago` : months === 1 ? "last month" : `${months} months ago`;
  }
  const years = Math.max(1, Math.floor(days / 365));
  return compact ? `${years}yr ago` : years === 1 ? "last year" : `${years} years ago`;
};

const RELATIVE_WINDOW_MS = 72 * 3600 * 1000;

window.refreshRelativeTimes = function refreshRelativeTimes(root = document, now = Date.now()) {
  root.querySelectorAll("time[datetime][data-relative-time]").forEach((node) => {
    const stamp = new Date(node.dateTime).getTime();
    if (!Number.isFinite(stamp)) return;
    const age = now - stamp;
    if (age >= RELATIVE_WINDOW_MS) return;
    if (age < 60_000) {
      node.textContent = "just now";
      return;
    }
    const compact = node.dataset.relativeTime === "compact";
    node.textContent = window.relativeTime(stamp, { compact, now });
  });
};

/* Recipe: nuu live dot */
window.liveDot = function liveDot() {
  const wrap = document.createElement("span");
  wrap.className = "ico-svg";
  wrap.setAttribute("aria-hidden", "true");
  const dot = document.createElement("i");
  dot.className = "dot";
  wrap.appendChild(dot);
  return wrap;
};

/* Recipe: nuu loading bar and inline button loading */
async function loadPanel(panel, task) {
  if (!panel) return task();
  panel.dataset.loading = "true";
  panel.setAttribute("aria-busy", "true");
  try {
    return await task();
  } finally {
    delete panel.dataset.loading;
    panel.setAttribute("aria-busy", "false");
  }
}

async function runButtonFetch(button, task) {
  if (!button) return task();
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await task();
  } finally {
    button.setAttribute("aria-busy", "false");
    button.disabled = false;
  }
}

window.loadPanel = loadPanel;
window.runButtonFetch = runButtonFetch;

/* Recipe: nuu shared modal manager */
window.createModalManager = function createModalManager(
  shell = document.getElementById("modal-shell"),
) {
  if (!shell) return null;
  const titleEl = shell.querySelector("#modal-title");
  const bodyEl = shell.querySelector("#modal-body");
  const actionsEl = shell.querySelector("#modal-actions");
  const registry = new Map();
  let activeTrigger = null;

  for (const tpl of document.querySelectorAll("template[data-modal-template]")) {
    registry.set(tpl.dataset.modalTemplate, tpl);
  }

  return {
    register(name, templateEl) {
      registry.set(name, templateEl);
    },
    open(name, { title = "", slots = {}, trigger = document.activeElement } = {}) {
      const tpl = registry.get(name);
      if (!tpl) throw new Error(`Unknown modal template: ${name}`);
      if (shell.open) shell.close("replaced");
      activeTrigger = trigger;
      if (titleEl) titleEl.textContent = title;
      const frag = tpl.content.cloneNode(true);
      for (const [slot, text] of Object.entries(slots)) {
        const node = frag.querySelector(`[data-slot="${slot}"]`);
        if (node) node.textContent = text;
      }
      const actionSlot = frag.querySelector('[data-slot="actions"]');
      actionsEl?.replaceChildren(...(actionSlot ? actionSlot.childNodes : []));
      if (actionSlot) actionSlot.remove();
      bodyEl?.replaceChildren(frag);
      shell.dataset.suppressRing = "true";
      shell.returnValue = "cancel";
      shell.showModal();
      const target =
        shell.querySelector("[autofocus]") ||
        shell.querySelector('button:not(.modal-close), input, select, textarea');
      target?.focus();
      return new Promise((resolve) => {
        shell.addEventListener(
          "close",
          () => {
            delete shell.dataset.suppressRing;
            const triggerEl = activeTrigger;
            activeTrigger = null;
            if (triggerEl && typeof triggerEl.focus === "function") triggerEl.focus();
            resolve(shell.returnValue || "cancel");
          },
          { once: true },
        );
      });
    },
  };
};

/* Recipe: nuu page memory cache */
const PAGE_MEMORY_CAP = 60;
const pageMemory = new Map();
let pageMemoryRev = 0;

function pageMemoryKey(href) {
  const build = document.querySelector(".brand-version")?.textContent?.trim() || "v0";
  const scope = document.documentElement.dataset.themeScope || "browser";
  const seat = document.body?.className || "default";
  let path = String(href || "");
  try {
    const parsed = new URL(path, window.location.href);
    path = `${parsed.pathname}${parsed.search}`;
  } catch {
    // Keep non-URL custom keys unchanged for callers and tests.
  }
  return `${build}|${scope}|${seat}|r${pageMemoryRev}|${path}`;
}

function invalidatePageMemory() {
  pageMemoryRev += 1;
  pageMemory.clear();
}

window.pageMemory = {
  key: pageMemoryKey,
  invalidate: invalidatePageMemory,
  clear: () => pageMemory.clear(),
  get: (key) => {
    if (pageMemory.has(key)) return pageMemory.get(key);
    return pageMemory.get(pageMemoryKey(key));
  },
  set: (key, value) => {
    const k = String(key).includes("|r") ? key : pageMemoryKey(key);
    if (pageMemory.size >= PAGE_MEMORY_CAP) pageMemory.delete(pageMemory.keys().next().value);
    pageMemory.set(k, value);
  },
  has: (key) => pageMemory.has(key) || pageMemory.has(pageMemoryKey(key)),
};

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

const prefetched = new Set();

window.pwedepaBoot = function pwedepaBoot(bootOptions = {}) {
  window.pwedepaLifecycle?.abort();
  const lifecycle = (window.pwedepaLifecycle = new AbortController());
  const listen = { signal: lifecycle.signal };

  const bootMain = document.querySelector("main.wrap");
  if (bootMain && !bootOptions.skipSeed && !window.pageMemory.has(window.location.href)) {
    window.pageMemory.set(window.location.href, {
      className: bootMain.className,
      html: bootMain.innerHTML,
      title: document.title,
    });
  }

  /* Keep <72h relative timestamps fresh once per minute and on tab return. */
  const tickTimer = window.setInterval(() => {
    if (!document.hidden) window.refreshRelativeTimes();
  }, 60_000);
  lifecycle.signal.addEventListener("abort", () => window.clearInterval(tickTimer), {
    once: true,
  });
  document.addEventListener(
    "visibilitychange",
    () => {
      if (!document.hidden) window.refreshRelativeTimes();
    },
    listen,
  );

  /* Theme: System (default), Light, Dark. Signed-in accounts sync to the server. */
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
    invalidatePageMemory();
    if (root.dataset.themeScope === "account") {
      fetch(root.dataset.themeEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ theme }),
      }).catch(() => {});
    }
    markThemeButtons();
  }

  /* Notification switches save immediately and roll back on failure. */
  document.querySelectorAll("form[data-autosave]").forEach((form) => {
    form.classList.add("is-auto");
    const status = document.querySelector("[data-autosave-status]");
    let saved = new FormData(form);
    let queue = Promise.resolve();
    form.addEventListener(
      "change",
      () => {
        const body = new URLSearchParams(new FormData(form));
        invalidatePageMemory();
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
      },
      listen,
    );
  });

  themeButtons.forEach((button) => {
    button.addEventListener("click", () => setTheme(button.dataset.themeSet), listen);
  });
  markThemeButtons();

  /* Load the 1.2 MB animated brand WebP only on pointer, focus, or touch intent. */
  const appIcon = document.querySelector(".app-icon");
  const animatedIcon = appIcon?.querySelector(".icon-animated[data-src]");
  if (appIcon && animatedIcon) {
    const loadAnimatedIcon = () => {
      animatedIcon.addEventListener("load", () => appIcon.classList.add("is-ready"));
      animatedIcon.src = animatedIcon.dataset.src;
      delete animatedIcon.dataset.src;
    };
    ["pointerenter", "focusin", "touchstart"].forEach((type) => {
      appIcon.addEventListener(type, loadAnimatedIcon, { once: true, signal: lifecycle.signal });
    });
  }

  const userMenuButton = document.querySelector("#user-menu-button");
  const userMenu = document.querySelector("#user-menu");
  if (userMenuButton && userMenu) {
    const closeMenu = () => {
      userMenu.hidden = true;
      userMenuButton.setAttribute("aria-expanded", "false");
    };
    userMenuButton.addEventListener(
      "click",
      () => {
        const opening = userMenu.hidden;
        userMenu.hidden = !opening;
        userMenuButton.setAttribute("aria-expanded", String(opening));
      },
      listen,
    );
    document.addEventListener(
      "click",
      (event) => {
        if (!userMenu.hidden && !event.target.closest(".user-menu-wrap")) closeMenu();
      },
      listen,
    );
    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key === "Escape") closeMenu();
      },
      listen,
    );
  }

  /* Prefetch internal links on pointer intent so navigation answers promptly. */
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
    listen,
  );

  /* Invalidate page memory before any non-GET form submission navigates. */
  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (form instanceof HTMLFormElement && (form.method || "get").toLowerCase() !== "get") {
        invalidatePageMemory();
      }
    },
    listen,
  );

  /* Workspace: a row opens the reading pane in place while keeping a real URL. */
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
        { once: true },
      );
    };

    const hideCard = () => {
      inspector.innerHTML = baseCard;
      inspector.classList.remove("is-main");
      workspaceGrid.classList.remove("is-open", "is-main", "is-picked");
      workspaceGrid.querySelector("tr.is-selected")?.classList.remove("is-selected");
    };

    const paintCard = (html, row) => {
      closeToken += 1;
      inspector.innerHTML = html;
      inspector.classList.add("is-main");
      workspaceGrid.classList.add("is-open", "is-main", "is-picked");
      workspaceGrid.querySelector("tr.is-selected")?.classList.remove("is-selected");
      row?.classList.add("is-selected");
    };

    const openCard = async (href, row, remember) => {
      const memKey = `card:${pageMemoryKey(href)}`;
      const cached = pageMemory.get(memKey);
      if (cached) {
        paintCard(cached, row);
        if (remember) history.pushState(null, "", href);
      }
      const fetchCard = async () => {
        const response = await fetch(href);
        if (!response.ok) throw new Error(`card ${response.status}`);
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        const card =
          page.querySelector(".workspace-grid .inspector") ?? page.querySelector(".narrow");
        if (!card || !inspector) throw new Error("no card");
        const html = card.innerHTML;
        window.pageMemory.set(memKey, html);
        if (!cached || html !== cached) {
          paintCard(html, row);
          revealCard();
        }
        if (remember && !cached) history.pushState(null, "", href);
        if (window.innerWidth < 900) {
          inspector.scrollIntoView({
            behavior: calm.matches ? "auto" : "smooth",
            block: "start",
          });
        }
      };

      if (!cached) inspector.setAttribute("aria-busy", "true");
      inspector.classList.toggle("is-loading", !cached);
      try {
        if (cached) {
          await fetchCard();
        } else {
          await loadPanel(inspector, fetchCard);
        }
      } catch {
        if (!cached) {
          inspector.innerHTML = "";
          const failed = document.createElement("p");
          failed.className = "muted";
          const link = document.createElement("a");
          link.href = href;
          link.textContent = "Open it as a page";
          failed.append("This record did not load. ", link, ".");
          inspector.append(failed);
          inspector.classList.add("is-main");
          workspaceGrid.classList.add("is-open", "is-main", "is-picked");
        }
      } finally {
        inspector.classList.remove("is-loading");
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

    document.addEventListener(
      "click",
      (event) => {
        const link = event.target.closest('a[href$="/requests/new"]');
        if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
          return;
        }
        event.preventDefault();
        openCard(link.href, null, true);
      },
      listen,
    );

    workspaceGrid.addEventListener(
      "click",
      (event) => {
        const link = event.target.closest(".record-table tbody a[href]");
        if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
          return;
        }
        if (!link.matches("a[href*='selected='], a[href*='/record/']")) return;
        event.preventDefault();
        openCard(link.href, link.closest("tr"), true);
      },
      listen,
    );

    const basePath = new URL(baseHref).pathname;
    window.addEventListener(
      "popstate",
      () => {
        const url = window.location.href;
        if (url === baseHref) {
          closeCard();
        } else if (cardHrefs.has(url)) {
          const row = rowLinks.find((link) => link.href === url)?.closest("tr");
          openCard(url, row, false);
        } else if (new URL(url).pathname === basePath) {
          return;
        } else {
          window.location.reload();
        }
      },
      listen,
    );
  }

  /* WebAuthn helpers convert between server base64url JSON and ArrayBuffers. */
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
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function postJson(url, body) {
    invalidatePageMemory();
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
        ...item,
        id: toBuffer(item.id),
      }));
    }
    return { publicKey };
  }

  function requestOptions(options) {
    const publicKey = { ...options, challenge: toBuffer(options.challenge) };
    if (options.allowCredentials) {
      publicKey.allowCredentials = options.allowCredentials.map((item) => ({
        ...item,
        id: toBuffer(item.id),
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

  function ceremonyError(error) {
    const blocked =
      error.name === "NotAllowedError" ||
      error.name === "SecurityError" ||
      String(error.message).includes("publickey-credentials");
    if (blocked) {
      return "Passkeys need a direct browser tab. Open this page outside the preview, or open the demo site.";
    }
    return error.message;
  }

  async function runCeremony(startUrl, finishUrl, extra, create) {
    const start = await postJson(startUrl, extra);
    const options = create ? creationOptions(start.options) : requestOptions(start.options);
    const credential = create
      ? await navigator.credentials.create(options)
      : await navigator.credentials.get(options);
    return postJson(finishUrl, {
      ...extra,
      flow_id: start.flow_id,
      credential: credentialJson(credential),
    });
  }

  const loginButton = document.querySelector("#login-button");
  loginButton?.addEventListener(
    "click",
    () =>
      runButtonFetch(loginButton, async () => {
        setStatus("Waiting for your passkey…");
        try {
          const done = await runCeremony("/login/options", "/login/finish", {}, false);
          window.location.assign(done.redirect || "/");
        } catch (error) {
          setStatus(ceremonyError(error));
        }
      }),
    listen,
  );

  const enrollForm = document.querySelector("#enroll-form");
  enrollForm?.addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      const submitBtn = enrollForm.querySelector('button[type="submit"]');
      runButtonFetch(submitBtn, async () => {
        const token = document.querySelector("#token").value.trim();
        const username = document.querySelector("#username").value.trim();
        const display_name = document.querySelector("#display-name").value.trim();
        setStatus("Waiting for your passkey…");
        try {
          const done = await runCeremony(
            "/enroll/options",
            "/enroll/finish",
            { token, username, display_name },
            true,
          );
          window.location.assign(done.redirect || "/");
        } catch (error) {
          setStatus(ceremonyError(error));
        }
      });
    },
    listen,
  );

  const tokenField = document.querySelector("#token");
  if (tokenField) {
    tokenField.value = new URLSearchParams(window.location.search).get("token") || "";
  }

  const addPasskeyButton = document.querySelector("#add-passkey");
  addPasskeyButton?.addEventListener(
    "click",
    () =>
      runButtonFetch(addPasskeyButton, async () => {
        setStatus("Waiting for your passkey…");
        try {
          await runCeremony("/auth/register/options", "/auth/register/finish", {}, true);
          window.location.reload();
        } catch (error) {
          setStatus(ceremonyError(error));
        }
      }),
    listen,
  );

  /* Admin subpages open inside Settings so the rail and group stay in place. */
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
      if (options?.method && options.method.toUpperCase() !== "GET") {
        invalidatePageMemory();
      }
      await loadPanel(drill, async () => {
        const response = await fetch(url, options);
        if (!response.ok) return;
        const nodes = paneFor(
          new DOMParser().parseFromString(await response.text(), "text/html"),
        );
        if (!nodes) return;
        drill.replaceChildren(...nodes);
        drill.hidden = false;
        adminList.hidden = true;
        drill.querySelector("button, a, input, select")?.focus();
      });
    };

    document.querySelectorAll("[data-admin-pane]").forEach((link) => {
      link.addEventListener(
        "click",
        (event) => {
          event.preventDefault();
          show(link.href);
        },
        listen,
      );
    });

    drill.addEventListener(
      "submit",
      (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        event.preventDefault();
        show(form.action, { method: "POST", body: new FormData(form) });
      },
      listen,
    );
  }

  /* Time format saves immediately and rolls back on failure. */
  const clockForm = document.querySelector("[data-clock-form]");

  if (clockForm) {
    const note = document.querySelector("[data-clock-status]");
    const buttons = [...clockForm.querySelectorAll("button[name=clock]")];
    const mark = (value) => {
      buttons.forEach((button) => {
        button.classList.toggle("is-active", button.value === value);
      });
    };
    clockForm.addEventListener(
      "click",
      async (event) => {
        const button = event.target.closest("button[name=clock]");
        if (!button) return;
        event.preventDefault();
        const previous = buttons.find((item) => item.classList.contains("is-active"));
        mark(button.value);
        invalidatePageMemory();
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
      },
      listen,
    );
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
    range.addEventListener(
      "input",
      () => {
        number.value = range.value;
        apply(Number(range.value));
      },
      listen,
    );
    number.addEventListener(
      "input",
      () => {
        const value = Number(number.value);
        if (valid(value)) apply(value);
      },
      listen,
    );
    const settle = async () => {
      const value = Math.min(130, Math.max(85, Number(number.value) || 100));
      number.value = value;
      range.value = value;
      apply(value);
      invalidatePageMemory();
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

  const logoutButton = document.querySelector("#logout-button");
  logoutButton?.addEventListener(
    "click",
    () =>
      runButtonFetch(logoutButton, async () => {
        const done = await postJson("/logout", {}).catch(() => ({ redirect: "/" }));
        window.location.assign(done.redirect || "/");
      }),
    listen,
  );

  document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
    form.classList.add("is-auto");
  });
  document.addEventListener(
    "change",
    (event) => {
      const form = event.target.closest?.("form[data-auto-submit]");
      if (form) form.requestSubmit();
    },
    listen,
  );

  /* Modal: shared manager and native dialog openers with focus restoration. */
  (() => {
    const shared = window.createModalManager();
    let active = null;
    let returnFocus = null;

    function focusable(modal) {
      return [
        ...modal.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((node) => !node.disabled && node.offsetParent !== null);
    }

    function finishClose(modal) {
      delete modal.dataset.suppressRing;
      document.body.classList.remove("has-modal");
      const prev = returnFocus;
      returnFocus = null;
      if (prev && prev.isConnected) prev.focus();
    }

    function open(id) {
      const modal = document.getElementById(id);
      if (!modal) return;
      if (active && active !== modal) close();
      active = modal;
      returnFocus = document.activeElement;
      modal.dataset.suppressRing = "true";
      if (modal instanceof HTMLDialogElement && typeof modal.showModal === "function") {
        if (!modal.open) modal.showModal();
        modal.addEventListener(
          "close",
          () => {
            if (active === modal) active = null;
            finishClose(modal);
          },
          { once: true, signal: lifecycle.signal },
        );
      } else {
        modal.hidden = false;
      }
      document.body.classList.add("has-modal");
      const items = focusable(modal);
      const explicit = modal.querySelector("[autofocus]:not(.modal-close)");
      const target =
        explicit || items.find((node) => !node.classList.contains("modal-close")) || items[0];
      if (target) target.focus();
    }

    function close() {
      if (!active) return;
      const modal = active;
      active = null;
      if (modal instanceof HTMLDialogElement && modal.open) {
        modal.close("cancel");
        return;
      }
      modal.hidden = true;
      finishClose(modal);
    }

    document.addEventListener(
      "click",
      (event) => {
        const opener = event.target.closest("[data-modal-open]");
        if (opener) {
          event.preventDefault();
          open(opener.dataset.modalOpen);
          return;
        }
        if (event.target.closest("[data-modal-close]")) {
          event.preventDefault();
          close();
          return;
        }
        if (active instanceof HTMLDialogElement && event.target === active) {
          close();
        }
      },
      listen,
    );

    document.addEventListener(
      "cancel",
      (event) => {
        if (active && event.target === active) {
          event.preventDefault();
          close();
        }
      },
      { ...listen, capture: true },
    );

    document.addEventListener(
      "keydown",
      (event) => {
        const dialog = active || document.querySelector("dialog.modal-shell[open]");
        if (!dialog) return;
        if (event.key === "Tab" || event.key.startsWith("Arrow")) {
          delete dialog.dataset.suppressRing;
        }
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
      },
      listen,
    );

    const openOnLoad = document.querySelector(
      "dialog.modal[data-modal-open-init], .modal:not(dialog):not([hidden])",
    );
    if (openOnLoad) open(openOnLoad.id);

    window.PwedePaModal = {
      open,
      close,
      manager: shared,
      confirm: (options) => shared?.open("confirm", options),
    };
  })();

  /* Textareas grow with wrapped text after final font metrics load. */
  (() => {
    const fit = (element) => {
      if (!(element instanceof HTMLTextAreaElement) || !element.offsetParent) return;
      element.style.height = "auto";
      const border = element.offsetHeight - element.clientHeight;
      element.style.height = `${element.scrollHeight + border}px`;
    };
    const fitAll = () => document.querySelectorAll("textarea").forEach(fit);

    document.addEventListener(
      "input",
      (event) => {
        if (event.target instanceof HTMLTextAreaElement) fit(event.target);
      },
      listen,
    );
    document.addEventListener(
      "focusin",
      (event) => {
        if (event.target instanceof HTMLTextAreaElement) fit(event.target);
      },
      listen,
    );
    window.addEventListener("resize", fitAll, listen);
    const runWhenReady = () => {
      fitAll();
      document.fonts?.ready?.then(() => {
        if (!lifecycle.signal.aborted) fitAll();
      });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", runWhenReady, listen);
    } else {
      runWhenReady();
    }
  })();

  /* Settings rail swaps panes on wide screens by replacing the hash in place. */
  (() => {
    const rail = document.querySelector(".settings-nav");
    if (!rail) return;
    const wide = window.matchMedia("(min-width: 640px)");
    rail.addEventListener(
      "click",
      (event) => {
        if (!wide.matches) return;
        const link = event.target.closest('a[href^="#"]');
        if (
          !link ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }
        event.preventDefault();
        const y = window.scrollY;
        location.replace(link.getAttribute("href"));
        window.scrollTo(0, y);
      },
      listen,
    );
  })();

  /* Workspace filters swap the filter and record panels in place. */
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
        await loadPanel(records, async () => {
          const response = await fetch(url, { headers: { Accept: "text/html" } });
          if (!response.ok) throw new Error(`filters ${response.status}`);
          const page = new DOMParser().parseFromString(await response.text(), "text/html");
          if (token !== run || !repaint(page)) return;
          if (remember) history.pushState(null, "", url);
        });
      } catch {
        window.location.assign(url);
      }
    };

    filters.addEventListener(
      "click",
      (event) => {
        const link = event.target.closest("a[href]");
        if (!link || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const url = new URL(link.href, window.location.href);
        if (url.pathname !== window.location.pathname || url.hash) return;
        event.preventDefault();
        load(url, true);
      },
      listen,
    );

    grid.addEventListener(
      "submit",
      (event) => {
        const form = event.target.closest("form[data-auto-submit]");
        if (!form || (form.method || "get").toLowerCase() !== "get") return;
        event.preventDefault();
        load(new URL(form.action + "?" + new URLSearchParams(new FormData(form))), true);
      },
      listen,
    );

    const path = window.location.pathname;
    window.addEventListener(
      "popstate",
      () => {
        if (window.location.pathname !== path) return;
        load(window.location.href, false);
      },
      listen,
    );
  })();

  /* Top-level pages swap into main.wrap with versioned page memory and edge loading. */
  (() => {
    const main = document.querySelector("main.wrap");
    if (!main || !window.fetch || !window.DOMParser) return;
    let run = 0;

    const finishSwap = (mainEl, remember, href) => {
      if (remember) history.pushState(null, "", href);
      window.scrollTo(0, 0);
      mainEl.setAttribute("tabindex", "-1");
      mainEl.focus({ preventScroll: true });
      window.pwedepaBoot({ skipSeed: true });
    };

    const swap = async (href, remember, { fresh = false } = {}) => {
      const token = ++run;
      const cached = !fresh ? window.pageMemory.get(href) : undefined;
      try {
        if (cached) {
          main.className = cached.className;
          main.innerHTML = cached.html;
          document.title = cached.title;
          finishSwap(main, remember, href);
        }
        const fetchFresh = async () => {
          const response = await fetch(href, { headers: { Accept: "text/html" } });
          if (!response.ok) throw new Error(`page ${response.status}`);
          const page = new DOMParser().parseFromString(await response.text(), "text/html");
          const nextMain = page.querySelector("main.wrap");
          if (!nextMain || token !== run) throw new Error("no page");
          const nextHtml = nextMain.innerHTML;
          const unchanged =
            cached &&
            nextHtml === cached.html &&
            nextMain.className === cached.className &&
            page.body.className === document.body.className;
          const bar = document.querySelector("header.topbar");
          const nextBar = page.querySelector("header.topbar");
          if (bar && nextBar) bar.replaceWith(nextBar);
          document.title = page.title;
          document.body.className = page.body.className;
          window.pageMemory.set(href, {
            className: nextMain.className,
            html: nextHtml,
            title: page.title,
          });
          if (unchanged) return;
          main.className = nextMain.className;
          main.replaceChildren(...nextMain.childNodes);
          finishSwap(main, !cached && remember, href);
        };
        if (cached) {
          await fetchFresh();
        } else {
          await loadPanel(main, fetchFresh);
        }
      } catch {
        if (!cached) window.location.assign(href);
      }
    };

    document.addEventListener(
      "click",
      (event) => {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const reload = event.target.closest("[data-page-reload]");
        if (reload) {
          event.preventDefault();
          swap(window.location.href, false, { fresh: true });
          return;
        }
        const link = event.target.closest("a[href]");
        if (!link || link.target || link.hasAttribute("download")) return;
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || url.hash) return;
        if (
          url.pathname === window.location.pathname &&
          url.search === window.location.search
        ) {
          return;
        }
        if (link.dataset.fullLoad !== undefined) return;
        event.preventDefault();
        swap(url.href, true);
      },
      listen,
    );

    window.addEventListener("popstate", () => swap(window.location.href, false), listen);
  })();
};

window.pwedepaBoot();
