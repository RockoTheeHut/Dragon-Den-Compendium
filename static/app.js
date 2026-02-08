(function () {
  function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (!sidebar) return;
    sidebar.classList.toggle("collapsed");
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
        reorderForm.submit();
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireButtons();
    wireTurnSorting();
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    wireButtons();
    wireTurnSorting();
  });
})();
