/* Shell-level behavior: theme, modal manager, toasts, scratchpad autosave,
 * dice/random-item tools, settings + XML import wiring.
 * URLs are provided by data-url-* attributes on <body>. */
(function () {
  "use strict";

  var FOCUSABLE_SELECTOR =
    "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type='hidden']), select:not([disabled]), [tabindex]:not([tabindex='-1'])";

  function bodyUrl(name) {
    return (document.body && document.body.dataset[name]) || "";
  }

  /* ---------- Theme ---------- */

  function getStoredThemeMode() {
    try {
      return localStorage.getItem("ddc_theme_mode") || "dark";
    } catch (error) {
      return "dark";
    }
  }

  function applyThemeMode(mode) {
    var root = document.documentElement;
    var body = document.body;
    if (!root) return;
    var isLight = mode === "light";
    root.classList.toggle("theme-light", isLight);
    if (body) {
      body.classList.toggle("theme-light", isLight);
    }
  }

  function saveThemeMode(mode) {
    try {
      localStorage.setItem("ddc_theme_mode", mode);
    } catch (error) {
    }
  }

  function wireThemeSettings() {
    var toggle = document.getElementById("theme-light-toggle");
    if (!toggle || toggle.dataset.bound === "1") return;
    var modeLabel = document.getElementById("theme-mode-label");
    var isLight = getStoredThemeMode() === "light";

    toggle.checked = isLight;
    toggle.dataset.bound = "1";
    if (modeLabel) {
      modeLabel.textContent = isLight
        ? "Light mode is on (warm light palette)."
        : "Dark mode is on.";
    }

    toggle.addEventListener("change", function () {
      var nextMode = toggle.checked ? "light" : "dark";
      applyThemeMode(nextMode);
      saveThemeMode(nextMode);
      if (modeLabel) {
        modeLabel.textContent = toggle.checked
          ? "Light mode is on (warm light palette)."
          : "Dark mode is on.";
      }
    });
  }

  /* ---------- Toasts ---------- */

  function showToast(text, tag) {
    var container = document.querySelector(".messages");
    if (!container) {
      container = document.createElement("div");
      container.className = "messages";
      var host = document.querySelector(".layout-right") || document.body;
      host.insertBefore(container, host.querySelector("main, #main-content"));
    }
    var message = document.createElement("div");
    message.className = "message " + (tag || "error");
    message.setAttribute("role", "status");

    var label = document.createElement("span");
    label.textContent = text;
    message.appendChild(label);

    var close = document.createElement("button");
    close.className = "message-close";
    close.type = "button";
    close.setAttribute("aria-label", "Close notification");
    close.textContent = "X";
    close.addEventListener("click", function () {
      message.remove();
    });
    message.appendChild(close);

    container.appendChild(message);
    setTimeout(function () {
      message.remove();
    }, 6000);
  }

  window.ddcShowToast = showToast;

  /* ---------- Modal manager (animation + keyboard accessibility) ---------- */

  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function focusFirstElement(modal) {
    var content = modal.querySelector(".modal-content") || modal;
    var target = content.querySelector(FOCUSABLE_SELECTOR);
    if (target) {
      target.focus();
    }
  }

  function syncBodyScrollLock() {
    var anyOpen = !!document.querySelector(".modal.is-open");
    document.body.classList.toggle("modal-open", anyOpen);
  }

  function openAppModal(modal) {
    if (!modal) return;
    if (modal._hideTimer) {
      clearTimeout(modal._hideTimer);
      modal._hideTimer = null;
    }
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    var heading = modal.querySelector("h1, h2, h3");
    if (heading) {
      if (!heading.id) {
        heading.id = modal.id + "-heading";
      }
      modal.setAttribute("aria-labelledby", heading.id);
    }
    modal._opener = document.activeElement;
    modal.classList.remove("hidden");
    modal.classList.remove("is-open");
    modal.getBoundingClientRect();
    if (prefersReducedMotion()) {
      modal.classList.add("is-open");
    } else {
      requestAnimationFrame(function () {
        modal.classList.add("is-open");
      });
    }
    syncBodyScrollLock();
    requestAnimationFrame(function () {
      focusFirstElement(modal);
    });
  }

  function closeAppModal(modal, beforeClose) {
    if (!modal) return;
    if (typeof beforeClose === "function") {
      beforeClose();
    }
    var opener = modal._opener;
    modal._opener = null;
    modal.classList.remove("is-open");
    if (prefersReducedMotion()) {
      modal.classList.add("hidden");
    } else {
      if (modal._hideTimer) {
        clearTimeout(modal._hideTimer);
      }
      modal._hideTimer = setTimeout(function () {
        modal.classList.add("hidden");
        modal._hideTimer = null;
      }, 260);
    }
    syncBodyScrollLock();
    if (opener && typeof opener.focus === "function" && document.contains(opener)) {
      opener.focus();
    }
  }

  window.openAppModal = openAppModal;
  window.closeAppModal = closeAppModal;

  function topmostOpenModal() {
    var open = document.querySelectorAll(".modal.is-open");
    return open.length ? open[open.length - 1] : null;
  }

  // Per-modal cleanup used when closing through Escape/backdrop.
  var MODAL_CLOSE_HOOKS = {
    "notes-modal": function () { autosaveScratchpad(); },
    "dice-modal": function () { hideDiceRolling(); },
    "random-item-modal": function () { hideRandomItemPicking(); }
  };

  function closeModalWithHooks(modal) {
    if (!modal) return;
    closeAppModal(modal, MODAL_CLOSE_HOOKS[modal.id]);
  }

  window.ddcCloseModalWithHooks = closeModalWithHooks;

  document.addEventListener("keydown", function (event) {
    var modal = topmostOpenModal();
    if (!modal) return;

    if (event.key === "Escape") {
      event.preventDefault();
      closeModalWithHooks(modal);
      return;
    }

    if (event.key === "Tab") {
      var content = modal.querySelector(".modal-content") || modal;
      var focusable = Array.prototype.filter.call(
        content.querySelectorAll(FOCUSABLE_SELECTOR),
        function (element) {
          return element.offsetParent !== null;
        }
      );
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !content.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  /* ---------- Scratchpad ---------- */

  function updateScratchpadCounter() {
    var textarea = document.getElementById("scratchpad-content");
    var counter = document.getElementById("scratchpad-counter");
    if (!textarea || !counter) return;

    var maxLength = parseInt(counter.dataset.maxLength || "0", 10);
    if (!maxLength) return;
    var remaining = Math.max(maxLength - textarea.value.length, 0);
    counter.textContent = remaining + " characters remaining";
  }

  function markScratchpadLoaded() {
    var form = document.getElementById("scratchpad-form");
    var textarea = document.getElementById("scratchpad-content");
    if (!form || !textarea) return;
    form.dataset.lastSaved = textarea.value;
    if (textarea.dataset.counterBound !== "1") {
      textarea.addEventListener("input", updateScratchpadCounter);
      textarea.dataset.counterBound = "1";
    }
    updateScratchpadCounter();
  }

  function autosaveScratchpad() {
    var form = document.getElementById("scratchpad-form");
    var textarea = document.getElementById("scratchpad-content");
    if (!form || !textarea) return;

    var currentValue = textarea.value;
    var lastSaved = form.dataset.lastSaved || "";
    if (currentValue === lastSaved) return;

    var csrfInput = form.querySelector("input[name='csrfmiddlewaretoken']");
    var payload = new URLSearchParams();
    payload.set("content", currentValue);
    if (csrfInput) {
      payload.set("csrfmiddlewaretoken", csrfInput.value);
    }

    fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "HX-Request": "true"
      },
      body: payload.toString()
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("Save failed with status " + response.status);
      }
      form.dataset.lastSaved = currentValue;
    }).catch(function () {
      showToast("Could not save your scratchpad — your latest changes are not stored.");
    });
  }

  function openNotesModal() {
    var modal = document.getElementById("notes-modal");
    if (!modal) return;
    openAppModal(modal);
    htmx.ajax("GET", bodyUrl("urlNotesModal"), "#notes-modal-content");
  }

  function closeNotesModal() {
    var modal = document.getElementById("notes-modal");
    if (!modal) return;
    closeAppModal(modal, autosaveScratchpad);
  }

  /* ---------- Dice tool ---------- */

  function showDiceRolling() {
    var animation = document.getElementById("dice-roll-animation");
    if (!animation) return;
    animation.classList.remove("hidden");
    animation.classList.add("is-rolling");
  }

  function hideDiceRolling() {
    var animation = document.getElementById("dice-roll-animation");
    if (!animation) return;
    animation.classList.add("hidden");
    animation.classList.remove("is-rolling");
  }

  function wireDiceTool() {
    var form = document.getElementById("dice-tool-form");
    if (!form || form.dataset.bound === "1") return;
    form.dataset.bound = "1";

    var addQuantity = document.getElementById("dice-add-quantity");
    var addSides = document.getElementById("dice-add-sides");
    var addButton = document.getElementById("dice-add-button");
    var planList = document.getElementById("dice-plan-list");
    var rollPlanInput = document.getElementById("dice-roll-plan");
    var rollAllButton = document.getElementById("dice-roll-all-button");

    var rollPlan = [];

    function syncPlanUi() {
      rollPlanInput.value = JSON.stringify(rollPlan);
      if (!rollPlan.length) {
        planList.textContent = "No dice added yet.";
        planList.classList.add("muted");
        rollAllButton.disabled = true;
        return;
      }

      planList.classList.remove("muted");
      planList.innerHTML = rollPlan
        .map(function (entry, index) {
          return "<button type='button' class='die-chip roll-plan-chip' data-plan-index='" + index + "' title='Remove from roll list'>" + entry.quantity + "d" + entry.sides + " ×</button>";
        })
        .join("");
      rollAllButton.disabled = false;
    }

    addButton.addEventListener("click", function () {
      var quantity = parseInt(addQuantity.value || "0", 10);
      var sides = parseInt(addSides.value || "0", 10);
      if (!quantity || quantity < 1 || !sides) {
        return;
      }

      rollPlan.push({ quantity: quantity, sides: sides });
      addQuantity.value = "1";
      syncPlanUi();
    });

    planList.addEventListener("click", function (event) {
      var target = event.target.closest(".roll-plan-chip");
      if (!target) return;
      var index = parseInt(target.dataset.planIndex || "-1", 10);
      if (index < 0 || index >= rollPlan.length) return;
      rollPlan.splice(index, 1);
      syncPlanUi();
    });

    syncPlanUi();

    form.addEventListener("htmx:beforeRequest", function () {
      showDiceRolling();
    });
    form.addEventListener("htmx:afterRequest", function (event) {
      hideDiceRolling();
      var status = event.detail && event.detail.xhr ? event.detail.xhr.status : 0;
      if (status >= 200 && status < 300) {
        rollPlan = [];
        syncPlanUi();
      }
    });
  }

  /* ---------- Random item tool ---------- */

  function showRandomItemPicking() {
    var result = document.getElementById("random-item-result");
    if (!result) return;
    result.classList.add("is-picking");
  }

  function hideRandomItemPicking() {
    var result = document.getElementById("random-item-result");
    if (!result) return;
    result.classList.remove("is-picking");
  }

  function wireRandomItemTool() {
    var form = document.getElementById("random-item-form");
    if (!form || form.dataset.bound === "1") return;
    form.dataset.bound = "1";

    form.addEventListener("htmx:beforeRequest", function () {
      showRandomItemPicking();
    });

    form.addEventListener("htmx:afterRequest", function () {
      hideRandomItemPicking();
    });
  }

  /* ---------- Shell modals ---------- */

  function openDiceModal() {
    var modal = document.getElementById("dice-modal");
    if (!modal) return;
    openAppModal(modal);
    htmx.ajax("GET", bodyUrl("urlDiceModal"), "#dice-modal-content");
  }

  function closeDiceModal() {
    var modal = document.getElementById("dice-modal");
    if (!modal) return;
    closeAppModal(modal, hideDiceRolling);
  }

  function openRandomItemModal() {
    var modal = document.getElementById("random-item-modal");
    if (!modal) return;
    openAppModal(modal);
    htmx.ajax("GET", bodyUrl("urlRandomItemModal"), "#random-item-modal-content");
  }

  function closeRandomItemModal() {
    var modal = document.getElementById("random-item-modal");
    if (!modal) return;
    closeAppModal(modal, hideRandomItemPicking);
  }

  function openSettingsModal() {
    var modal = document.getElementById("settings-modal");
    if (!modal) return;
    openAppModal(modal);
    htmx.ajax("GET", bodyUrl("urlSettingsModal"), "#settings-modal-content");
  }

  function closeSettingsModal() {
    var modal = document.getElementById("settings-modal");
    if (!modal) return;
    closeAppModal(modal);
  }

  window.openNotesModal = openNotesModal;
  window.closeNotesModal = closeNotesModal;
  window.openDiceModal = openDiceModal;
  window.closeDiceModal = closeDiceModal;
  window.openRandomItemModal = openRandomItemModal;
  window.closeRandomItemModal = closeRandomItemModal;
  window.openSettingsModal = openSettingsModal;
  window.closeSettingsModal = closeSettingsModal;

  /* ---------- XML import progress ---------- */

  function showXmlImportLoading() {
    openAppModal(document.getElementById("xml-import-loading-modal"));
  }

  function hideXmlImportLoading() {
    closeAppModal(document.getElementById("xml-import-loading-modal"));
  }

  function isXmlImportRequestElement(requestElement) {
    if (!requestElement || !requestElement.closest) return false;
    return !!requestElement.closest("#settings-import-xml-form");
  }

  /* ---------- Global wiring ---------- */

  applyThemeMode(getStoredThemeMode());

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (!event.target) return;
    switch (event.target.id) {
      case "notes-modal-content":
        markScratchpadLoaded();
        break;
      case "dice-modal-content":
        wireDiceTool();
        break;
      case "dice-roll-result":
        hideDiceRolling();
        break;
      case "random-item-modal-content":
        wireRandomItemTool();
        break;
      case "random-item-result":
        hideRandomItemPicking();
        break;
      case "settings-modal-content":
        wireThemeSettings();
        hideXmlImportLoading();
        break;
    }
  });

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var requestElement = event && event.detail ? event.detail.elt : null;
    if (isXmlImportRequestElement(requestElement)) {
      showXmlImportLoading();
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var requestElement = event && event.detail ? event.detail.elt : null;
    if (isXmlImportRequestElement(requestElement)) {
      hideXmlImportLoading();
    }
  });

  document.body.addEventListener("htmx:responseError", function (event) {
    var requestElement = event && event.detail ? event.detail.elt : null;
    if (isXmlImportRequestElement(requestElement)) {
      hideXmlImportLoading();
    }
    showToast("That action failed on the server. Please try again.");
  });

  document.body.addEventListener("htmx:sendError", function (event) {
    var requestElement = event && event.detail ? event.detail.elt : null;
    if (isXmlImportRequestElement(requestElement)) {
      hideXmlImportLoading();
    }
    showToast("Could not reach the server. Check your connection and try again.");
  });

  wireRandomItemTool();
  wireThemeSettings();
})();
