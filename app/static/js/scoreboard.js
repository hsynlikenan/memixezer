/* Live scoreboard: polls the JSON endpoint and animates rank changes. */
(function () {
  "use strict";
  var table = document.getElementById("sb");
  if (!table) return;

  var endpoint = table.dataset.endpoint;
  var me = String(table.dataset.me || "");
  var tbody = table.tBodies[0];
  var dot = document.getElementById("sb-dot");
  var state = document.getElementById("sb-state");
  var youScore = document.getElementById("sb-you-score");
  var youRank = document.getElementById("sb-you-rank");
  var players = document.getElementById("sb-players");
  var empty = document.getElementById("sb-empty");
  var INTERVAL = 15000;
  var timer = null;
  var inflight = false;

  // previous rank per user, seeded from server-rendered rows
  var prev = {};
  Array.prototype.forEach.call(tbody.rows, function (tr) {
    prev[tr.dataset.user] = Number(tr.cells[0].textContent) || 0;
  });

  function cell(text, cls) {
    var td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    return td;
  }

  function setCount(el, value) {
    if (!el) return;
    if (window.animateCount) window.animateCount(el, value, 800);
    else el.textContent = Number(value).toLocaleString();
  }

  function render(data) {
    var entries = data.entries || [];
    var frag = document.createDocumentFragment();
    var next = {};
    var myRank = null;

    entries.forEach(function (e) {
      var id = String(e.user_id);
      var tr = document.createElement("tr");
      tr.dataset.user = id;
      if (e.rank <= 3) tr.classList.add("rank--" + e.rank);
      if (id === me) { tr.classList.add("is-you"); myRank = e.rank; }
      if (!(id in prev)) tr.classList.add("is-new");
      else if (e.rank < prev[id]) tr.classList.add("moved-up");
      else if (e.rank > prev[id]) tr.classList.add("moved-down");
      tr.appendChild(cell(e.rank, "num"));
      tr.appendChild(cell(e.name));
      tr.appendChild(cell(e.solves, "num"));
      tr.appendChild(cell(Number(e.score).toLocaleString(), "num score"));
      frag.appendChild(tr);
      next[id] = e.rank;
    });

    tbody.textContent = "";
    tbody.appendChild(frag);
    prev = next;

    if (empty) empty.classList.toggle("hidden", entries.length > 0);
    if (players) players.textContent = entries.length;
    if (youRank) youRank.textContent = myRank ? "#" + myRank : "—";
    if (youScore && typeof data.you === "number") setCount(youScore, data.you);

    var frozen = !!data.frozen_at;
    if (dot) dot.classList.toggle("is-frozen", frozen);
    if (state) {
      if (frozen) {
        var d = new Date(data.frozen_at);
        var label = isNaN(d) ? data.frozen_at : d.toISOString().slice(0, 16).replace("T", " ");
        state.textContent = "Frozen at " + label + " UTC";
      } else {
        state.textContent = "Live · updates every 15 seconds";
      }
    }
  }

  function poll() {
    if (inflight || document.hidden) return;
    inflight = true;
    fetch(endpoint, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(render)
      .catch(function () {
        if (state) state.textContent = "Connection lost · retrying…";
      })
      .then(function () { inflight = false; });
  }

  function start() { if (!timer) timer = setInterval(poll, INTERVAL); }
  function stop() { clearInterval(timer); timer = null; }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stop();
    else { poll(); start(); }
  });
  start();
})();
