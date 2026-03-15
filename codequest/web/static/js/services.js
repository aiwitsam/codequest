/* Services & Mesh - Health polling, restart */
"use strict";

function refreshServices() {
  showToast("Refreshing service status...", "info");
  location.reload();
}

function restartService(name) {
  if (!confirm('Restart service "' + name + '"?')) return;

  fetch("/api/ops/services/" + encodeURIComponent(name) + "/restart", {
    method: "POST",
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast(name + " restarted", "success");
        setTimeout(function () { location.reload(); }, 2000);
      } else {
        showToast(data.error || "Restart failed", "error");
      }
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}

function stopLaunchpadService(name) {
  if (!confirm('Stop launchpad process "' + name + '"?')) return;

  fetch("/api/launch/" + encodeURIComponent(name) + "/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast(name + " stopped", "success");
        setTimeout(function () { location.reload(); }, 1500);
      } else {
        showToast("Failed to stop " + name, "error");
      }
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}

// Auto-refresh every 30s
var _serviceInterval = null;

document.addEventListener("DOMContentLoaded", function () {
  _serviceInterval = setInterval(function () {
    fetch("/api/ops/services")
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var services = data.services || [];
        services.forEach(function (svc) {
          var card = document.getElementById("svc-" + svc.name);
          if (!card) return;
          var dot = card.querySelector(".status-dot");
          if (dot) {
            dot.className = "status-dot " + svc.health.status;
          }
        });
      })
      .catch(function () {});
  }, 30000);
});
