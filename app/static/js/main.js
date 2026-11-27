/* Global UI: mobile nav, flash messages, confirm prompts. */
(function () {
  "use strict";

  // Mobile burger menu
  var burger = document.getElementById("burger");
  var links = document.getElementById("nav-links");
  if (burger && links) {
    burger.addEventListener("click", function () {
      var open = links.classList.toggle("is-open");
      burger.classList.toggle("is-open", open);
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        links.classList.remove("is-open");
        burger.classList.remove("is-open");
        burger.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Flash messages: dismiss button + auto-hide after 6s
  function dismiss(flash) {
    if (!flash || flash.dataset.leaving) return;
    flash.dataset.leaving = "1";
    flash.classList.add("is-leaving");
    setTimeout(function () { flash.remove(); }, 300);
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-dismiss]");
    if (btn) dismiss(btn.closest(".flash"));
  });
  document.querySelectorAll(".flash").forEach(function (f) {
    setTimeout(function () { dismiss(f); }, 6000);
  });

  // Forms with data-confirm ask before submitting
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });
})();
