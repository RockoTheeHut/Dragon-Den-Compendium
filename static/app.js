(function () {
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

  document.addEventListener("DOMContentLoaded", function () {
    wireButtons();
    wireTurnSorting();
    wireGlobalSearch();
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    wireButtons();
    wireTurnSorting();
    wireGlobalSearch();
  });
})();
