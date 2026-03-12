/* Reddit Intel - Search, filter, scrape */
"use strict";

function searchReddit() {
  var query = document.getElementById("reddit-search");
  var subFilter = document.getElementById("reddit-sub-filter");
  var q = query ? query.value.trim() : "";
  var sub = subFilter ? subFilter.value : "";

  var params = new URLSearchParams();
  if (q) params.set("q", q);
  if (sub) params.set("sub", sub);

  window.location.href = "/intel/reddit?" + params.toString();
}

function triggerScrape() {
  var btn = document.getElementById("scrape-btn");
  if (btn) btn.disabled = true;

  fetch("/api/intel/reddit/scrape", { method: "POST" })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast("Scrape started in background", "success");
      if (btn) {
        btn.textContent = "Scraping...";
        setTimeout(function () {
          btn.disabled = false;
          btn.textContent = "Scrape Now";
          showToast("Scrape likely complete - refresh to see results", "info");
        }, 30000);
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
      if (btn) btn.disabled = false;
    });
}

// Enter to search
document.addEventListener("DOMContentLoaded", function () {
  var searchInput = document.getElementById("reddit-search");
  if (searchInput) {
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        searchReddit();
      }
    });
  }
});
