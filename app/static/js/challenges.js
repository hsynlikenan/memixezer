/* Challenge board: client-side filtering, detail modal, AJAX flag submission. */
(function () {
  "use strict";

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var csrf = csrfMeta ? csrfMeta.getAttribute("content") : "";

  // ---------------------------------------------------------------- filtering
  var filters = document.getElementById("filters");
  var selCat = document.getElementById("f-category");
  var selDiff = document.getElementById("f-difficulty");
  var reset = document.getElementById("f-reset");
  var count = document.getElementById("f-count");
  var empty = document.getElementById("cards-empty");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".ch-card"));

  function applyFilters(updateUrl) {
    var cat = selCat ? selCat.value : "";
    var diff = selDiff ? selDiff.value : "";
    var shown = 0;
    cards.forEach(function (card) {
      var ok = (!cat || card.dataset.category === cat) && (!diff || card.dataset.difficulty === diff);
      card.classList.toggle("hidden", !ok);
      if (ok) shown++;
    });
    if (count) count.textContent = shown + " of " + cards.length + " challenge" + (cards.length === 1 ? "" : "s");
    if (empty) empty.classList.toggle("hidden", shown !== 0);
    if (reset) reset.classList.toggle("is-active", !!(cat || diff));
    if (updateUrl && window.history && history.replaceState) {
      var params = new URLSearchParams();
      if (cat) params.set("category", cat);
      if (diff) params.set("difficulty", diff);
      var qs = params.toString();
      history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : ""));
    }
  }

  if (filters) {
    filters.addEventListener("submit", function (e) { e.preventDefault(); applyFilters(true); });
    filters.querySelectorAll('button[type="submit"]').forEach(function (b) { b.hidden = true; });
  }
  if (selCat) selCat.addEventListener("change", function () { applyFilters(true); });
  if (selDiff) selDiff.addEventListener("change", function () { applyFilters(true); });
  if (reset) reset.addEventListener("click", function (e) {
    e.preventDefault();
    if (selCat) selCat.value = "";
    if (selDiff) selDiff.value = "";
    applyFilters(true);
  });
  applyFilters(false);

  // -------------------------------------------------------------------- modal
  var modal = document.getElementById("ch-modal");
  if (!modal) return;
  var dialog = modal.querySelector(".modal__dialog");
  var mMeta = document.getElementById("m-meta");
  var mTitle = document.getElementById("m-title");
  var mDesc = document.getElementById("m-desc");
  var mFile = document.getElementById("m-file");
  var mForm = document.getElementById("m-form");
  var mFlag = document.getElementById("m-flag");
  var mResult = document.getElementById("m-result");
  var mSubmit = mForm ? mForm.querySelector('button[type="submit"]') : null;

  var current = null;      // card element currently open
  var lastFocus = null;
  var requestSeq = 0;

  function setResult(text, state) {
    mResult.textContent = text || "";
    mResult.classList.remove("is-ok", "is-bad");
    if (state) mResult.classList.add(state);
  }

  function setSolved(solved) {
    mFlag.disabled = solved;
    if (mSubmit) mSubmit.disabled = solved;
    mForm.classList.toggle("is-solved", solved);
    if (solved) {
      mFlag.value = "";
      mFlag.placeholder = "Solved";
    } else {
      mFlag.placeholder = "flag{…}";
    }
  }

  function renderDescription(text) {
    // Plain text with paragraph breaks; never inject HTML.
    mDesc.textContent = "";
    String(text || "").split(/\n{2,}/).forEach(function (para) {
      var p = document.createElement("p");
      var lines = para.split("\n");
      lines.forEach(function (line, i) {
        if (i) p.appendChild(document.createElement("br"));
        p.appendChild(document.createTextNode(line));
      });
      mDesc.appendChild(p);
    });
  }

  function openModal(card) {
    current = card;
    lastFocus = document.activeElement;
    var seq = ++requestSeq;

    mMeta.textContent = card.dataset.category + " · " + card.dataset.difficulty;
    mTitle.textContent = "Loading…";
    mDesc.textContent = "";
    mFile.hidden = true;
    setResult("");
    setSolved(card.classList.contains("is-solved"));
    if (card.classList.contains("is-solved")) setResult("You already solved this one.", "is-ok");

    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("has-modal");
    setTimeout(function () { (mFlag.disabled ? dialog : mFlag).focus(); }, 60);

    fetch(card.dataset.detailUrl, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        if (seq !== requestSeq) return;
        mMeta.textContent = d.category + " · " + d.difficulty + " · " + d.points + " pts";
        mTitle.textContent = d.title;
        renderDescription(d.description);
        if (d.has_file) {
          mFile.href = card.dataset.fileUrl;
          mFile.textContent = "Download " + (d.file_name || "file");
          mFile.hidden = false;
        }
        if (d.solved) {
          card.classList.add("is-solved");
          setSolved(true);
          setResult("You already solved this one.", "is-ok");
        }
      })
      .catch(function () {
        if (seq !== requestSeq) return;
        mTitle.textContent = "Could not load challenge";
        setResult("Please refresh the page and try again.", "is-bad");
      });
  }

  function closeModal() {
    if (!modal.classList.contains("is-open")) return;
    requestSeq++;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("has-modal");
    current = null;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  cards.forEach(function (card) {
    card.addEventListener("click", function () { openModal(card); });
  });
  modal.addEventListener("click", function (e) {
    if (e.target === modal || e.target.closest("[data-close]")) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeModal();
  });

  // -------------------------------------------------------------- submission
  function shake() {
    dialog.classList.remove("shake");
    void dialog.offsetWidth; // restart animation
    dialog.classList.add("shake");
  }
  dialog.addEventListener("animationend", function () { dialog.classList.remove("shake"); });

  mForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!current) return;
    var flag = mFlag.value.trim();
    if (!flag) { setResult("Enter a flag first.", "is-bad"); shake(); mFlag.focus(); return; }

    var card = current;
    var body = new FormData();
    body.append("flag", flag);
    if (mSubmit) mSubmit.disabled = true;
    setResult("Checking…");

    fetch(card.dataset.submitUrl, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Accept": "application/json" }
    })
      .then(function (r) {
        if (r.status === 429) throw { message: "Too many attempts. Wait a minute and try again." };
        if (r.status === 400) throw { message: "Your session expired. Refresh the page and try again." };
        if (!r.ok) throw { message: "Something went wrong (HTTP " + r.status + ")." };
        return r.json();
      })
      .then(function (d) {
        if (card !== current) return;
        if (d.correct) {
          setResult(d.message || "Correct!", "is-ok");
          card.classList.add("is-solved");
          setSolved(true);
        } else {
          setResult(d.message || "Incorrect flag.", "is-bad");
          shake();
          if (mSubmit) mSubmit.disabled = false;
          mFlag.select();
        }
      })
      .catch(function (err) {
        if (card !== current) return;
        setResult((err && err.message) || "Network error. Try again.", "is-bad");
        shake();
        if (mSubmit) mSubmit.disabled = false;
      });
  });
})();
