/* Animated number counters for [data-count]. Exposes window.animateCount for reuse. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function animateCount(el, to, duration) {
    to = Number(to) || 0;
    var from = Number(String(el.textContent).replace(/[^0-9.-]/g, "")) || 0;
    if (el.dataset.counted !== "1") from = 0;
    el.dataset.counted = "1";
    if (reduce || from === to) { el.textContent = to.toLocaleString(); return; }
    duration = duration || 1400;
    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      el.textContent = Math.round(from + (to - from) * eased).toLocaleString();
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  window.animateCount = animateCount;

  var els = document.querySelectorAll("[data-count]");
  if (!els.length) return;

  function run(el) { animateCount(el, el.getAttribute("data-count")); }

  if (!("IntersectionObserver" in window)) { els.forEach(run); return; }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) { run(entry.target); io.unobserve(entry.target); }
    });
  }, { threshold: 0.4 });
  els.forEach(function (el) { io.observe(el); });
})();
