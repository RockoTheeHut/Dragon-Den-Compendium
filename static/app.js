(function () {
  const SWAP_ANIMATION_CLASS = "swap-region-pop";
  function animateSwapTarget(target) {
    if (!target) return;
    target.classList.remove(SWAP_ANIMATION_CLASS);
    // Force restart when repeated swaps hit the same region.
    target.getBoundingClientRect();
    target.classList.add(SWAP_ANIMATION_CLASS);
    if (target._swapAnimationTimer) {
      clearTimeout(target._swapAnimationTimer);
    }
    target._swapAnimationTimer = setTimeout(function () {
      target.classList.remove(SWAP_ANIMATION_CLASS);
      target._swapAnimationTimer = null;
    }, 260);
  }

  function isAnimatableSwapTarget(target) {
    if (!target || !target.id) return false;
    return [
      "main-content",
      "tracker-edit-modal-content",
      "tracker-status-modal-content",
      "tracker-monster-modal-content",
      "compendium-preview-modal-content",
      "notes-modal-content",
      "dice-roll-result",
      "random-item-result",
      "random-item-history-region",
    ].includes(target.id);
  }

  function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (!sidebar) return;
    sidebar.classList.toggle("collapsed");
    document.body.classList.toggle("sidebar-collapsed", sidebar.classList.contains("collapsed"));
  }

  function toggleMobileSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (!sidebar) return;
    sidebar.classList.toggle("mobile-open");
  }

  function wireButtons() {
    const sidebarToggle = document.getElementById("sidebar-toggle");
    if (sidebarToggle) {
      sidebarToggle.onclick = toggleSidebar;
    }

    const mobileBtn = document.getElementById("mobile-menu-btn");
    if (mobileBtn) {
      mobileBtn.onclick = toggleMobileSidebar;
    }

    const sidebar = document.getElementById("sidebar");
    if (sidebar) {
      document.body.classList.toggle("sidebar-collapsed", sidebar.classList.contains("collapsed"));
    }
  }

  function wireTurnSorting() {
    const tableBody = document.getElementById("turn-entry-table");
    if (!tableBody || tableBody.dataset.sortableBound === "1") {
      return;
    }

    const orderInput = document.getElementById(tableBody.dataset.orderInput);
    const reorderForm = document.getElementById(tableBody.dataset.reorderForm);
    if (!orderInput || !reorderForm) {
      return;
    }

    tableBody.dataset.sortableBound = "1";
    Sortable.create(tableBody, {
      animation: 150,
      handle: ".tracker-drag-handle",
      onEnd: function () {
        const ids = Array.from(tableBody.querySelectorAll("tr[data-entry-id]")).map((row) => row.dataset.entryId);
        orderInput.value = ids.join(",");
        if (window.htmx && reorderForm.getAttribute("hx-post")) {
          window.htmx.trigger(reorderForm, "submit");
        } else {
          reorderForm.submit();
        }
      },
    });
  }

  function wireGlobalSearch() {
    const wrap = document.querySelector(".search-wrap");
    const input = document.getElementById("global-search");
    const preview = document.getElementById("global-search-preview");
    const clearBtn = document.getElementById("global-search-clear");

    if (!wrap || !input || !preview || !clearBtn || wrap.dataset.searchBound === "1") {
      return;
    }

    wrap.dataset.searchBound = "1";

    function hidePreview() {
      preview.classList.remove("is-open");
    }

    function showPreview() {
      if (!input.value.trim()) {
        return;
      }
      preview.classList.add("is-open");
    }

    function syncClearButton() {
      const hasValue = input.value.length > 0;
      clearBtn.classList.toggle("is-visible", hasValue);
      if (!hasValue) {
        hidePreview();
        preview.innerHTML = "";
      }
    }

    input.addEventListener("input", syncClearButton);
    input.addEventListener("focus", showPreview);
    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        hidePreview();
      }
    });

    clearBtn.addEventListener("click", function () {
      input.value = "";
      preview.innerHTML = "";
      hidePreview();
      syncClearButton();
      input.focus();
    });

    preview.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        hidePreview();
      }
    });

    document.addEventListener("click", function (event) {
      if (!wrap.contains(event.target)) {
        hidePreview();
      }
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      if (event.target && event.target.id === "global-search-preview") {
        if (input.value.trim()) {
          preview.classList.add("is-open");
        } else {
          hidePreview();
        }
      }
    });

    syncClearButton();
  }

  function openTrackerModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    if (typeof window.openAppModal === "function") {
      window.openAppModal(modal);
      return;
    }
    modal.classList.remove("hidden");
  }

  function closeTrackerModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    if (typeof window.closeAppModal === "function") {
      window.closeAppModal(modal);
      return;
    }
    modal.classList.add("hidden");
  }

  function openTrackerEditModal(entryId) {
    const modal = document.getElementById("tracker-edit-modal");
    const target = document.getElementById("tracker-edit-modal-content");
    if (!modal || !target || !window.htmx) return;
    if (typeof window.openAppModal === "function") {
      window.openAppModal(modal);
    } else {
      modal.classList.remove("hidden");
    }
    window.htmx.ajax("GET", "/tracker/entries/" + entryId + "/edit-modal/", "#tracker-edit-modal-content");
  }

  function openTrackerStatusModal(entryId) {
    const modal = document.getElementById("tracker-status-modal");
    const target = document.getElementById("tracker-status-modal-content");
    if (!modal || !target || !window.htmx) return;
    if (typeof window.openAppModal === "function") {
      window.openAppModal(modal);
    } else {
      modal.classList.remove("hidden");
    }
    window.htmx.ajax("GET", "/tracker/entries/" + entryId + "/status/modal/", "#tracker-status-modal-content");
  }

  function openTrackerMonsterModal(entryId) {
    const modal = document.getElementById("tracker-monster-modal");
    const target = document.getElementById("tracker-monster-modal-content");
    if (!modal || !target || !window.htmx) return;
    if (typeof window.openAppModal === "function") {
      window.openAppModal(modal);
    } else {
      modal.classList.remove("hidden");
    }
    window.htmx.ajax("GET", "/tracker/entries/" + entryId + "/monster/modal/", "#tracker-monster-modal-content");
  }

  function openCompendiumPreviewModal(objectId) {
    const modal = document.getElementById("compendium-preview-modal");
    const target = document.getElementById("compendium-preview-modal-content");
    if (!modal || !target || !window.htmx) return;
    if (typeof window.openAppModal === "function") {
      window.openAppModal(modal);
    } else {
      modal.classList.remove("hidden");
    }
    window.htmx.ajax("GET", "/compendium/" + objectId + "/preview/modal/", "#compendium-preview-modal-content");
  }

  function closeCompendiumPreviewModal() {
    const modal = document.getElementById("compendium-preview-modal");
    if (!modal) return;
    if (typeof window.closeAppModal === "function") {
      window.closeAppModal(modal);
      return;
    }
    modal.classList.add("hidden");
  }

  function wireTrackerTabs() {
    const tabRoots = document.querySelectorAll("[data-tracker-tabs='1']");
    if (!tabRoots.length) return;

    tabRoots.forEach(function (root) {
      if (root.dataset.tabsBound === "1") return;
      root.dataset.tabsBound = "1";

      const buttons = Array.from(root.querySelectorAll("[data-tracker-tab-target]"));
      const panels = Array.from(root.querySelectorAll(".tracker-tab-panel"));
      if (!buttons.length || !panels.length) return;

      function activate(panelId) {
        buttons.forEach(function (button) {
          button.classList.toggle("is-active", button.dataset.trackerTabTarget === panelId);
        });
        panels.forEach(function (panel) {
          panel.classList.toggle("hidden", panel.id !== panelId);
        });
      }

      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          activate(button.dataset.trackerTabTarget);
        });
      });
    });
  }

  function wireTrackerEntryTypeForms() {
    const forms = document.querySelectorAll("[data-entry-type-toggle='1']");
    if (!forms.length) return;

    forms.forEach(function (form) {
      const select =
        form.querySelector("[data-entry-type-select]") ||
        form.querySelector("select[name='entry_type']");
      if (!select || select.dataset.entryTypeBound === "1") return;

      select.dataset.entryTypeBound = "1";
      const nonPlayerFields = form.querySelectorAll("[data-non-player-only='1']");

      function sync() {
        const isPlayer = select.value === "player";
        nonPlayerFields.forEach(function (fieldWrap) {
          fieldWrap.classList.toggle("hidden", isPlayer);
          const inputs = fieldWrap.querySelectorAll("input, textarea, select");
          inputs.forEach(function (input) {
            input.disabled = isPlayer;
          });
        });
      }

      select.addEventListener("change", sync);
      sync();
    });
  }

  function wireFilterSelectInputs() {
    const searchInputs = document.querySelectorAll("[data-filter-select]");
    if (!searchInputs.length) return;

    searchInputs.forEach(function (input) {
      if (input.dataset.filterBound === "1") return;
      input.dataset.filterBound = "1";

      const selectId = (input.dataset.filterSelect || "").replace(/^#/, "");
      const select = document.getElementById(selectId);
      if (!select) return;

      const options = Array.from(select.options);
      if (!options.length) return;
      const placeholderOption = options[0];

      function applyFilter() {
        const query = (input.value || "").trim().toLowerCase();
        let visibleCount = 0;

        options.forEach(function (option, index) {
          if (index === 0) {
            option.hidden = false;
            return;
          }
          const match = option.text.toLowerCase().includes(query);
          option.hidden = !match;
          if (match) {
            visibleCount += 1;
          }
        });

        if (query && visibleCount === 0) {
          select.value = placeholderOption.value;
        }
      }

      input.addEventListener("input", applyFilter);
      applyFilter();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireButtons();
    wireTurnSorting();
    wireGlobalSearch();
    wireTrackerTabs();
    wireTrackerEntryTypeForms();
    wireFilterSelectInputs();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event && isAnimatableSwapTarget(event.target)) {
      animateSwapTarget(event.target);
    }
    wireButtons();
    wireTurnSorting();
    wireGlobalSearch();
    wireTrackerTabs();
    wireTrackerEntryTypeForms();
    wireFilterSelectInputs();
  });

  window.openTrackerModal = openTrackerModal;
  window.closeTrackerModal = closeTrackerModal;
  window.openTrackerEditModal = openTrackerEditModal;
  window.openTrackerStatusModal = openTrackerStatusModal;
  window.openTrackerMonsterModal = openTrackerMonsterModal;
  window.openCompendiumPreviewModal = openCompendiumPreviewModal;
  window.closeCompendiumPreviewModal = closeCompendiumPreviewModal;
})();
