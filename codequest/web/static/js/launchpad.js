/* ====================================================================
   CodeQuest Launchpad - Process Management UI
   ====================================================================
   Handles project launching, stopping, SSE streaming, port detection,
   and status polling for the Launchpad page.
   ==================================================================== */

"use strict";

// ── Launch a project from the Launchpad page ─────────────────────

function launchProject(name, selectEl) {
  var command = "";
  if (selectEl && selectEl.value) {
    command = selectEl.value;
  }

  var card = document.getElementById("launch-card-" + name);
  if (!card) return;

  var consoleEl = card.querySelector(".launch-console");
  var urlBar = card.querySelector(".launch-url-bar");
  var launchBtn = card.querySelector(".launch-btn");
  var stopBtn = card.querySelector(".stop-cmd-btn");

  if (consoleEl) {
    clearElement(consoleEl);
    consoleEl.classList.add("visible");
  }
  if (launchBtn) launchBtn.disabled = true;
  if (stopBtn) stopBtn.style.display = "";

  card.className = card.className.replace(/\b(running|failed|starting)\b/g, "").trim();
  card.classList.add("starting");

  var body = {};
  if (command) body.command = command;

  fetch("/api/launch/" + encodeURIComponent(name), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(function (resp) {
    if (!resp.ok) {
      return resp.json().then(function (data) {
        if (consoleEl) {
          consoleEl.appendChild(
            createTextSpan("Error: " + (data.error || "Launch failed"), "error")
          );
        }
        card.classList.remove("starting");
        card.classList.add("failed");
        if (launchBtn) launchBtn.disabled = false;
        showToast("Launch failed: " + (data.error || "Unknown error"), "error");
      });
    }

    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";

    function read() {
      reader.read().then(function (result) {
        if (result.done) {
          if (launchBtn) launchBtn.disabled = false;
          return;
        }

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split("\n");
        buffer = lines.pop();

        lines.forEach(function (line) {
          if (line.startsWith("data: ")) {
            try {
              var event = JSON.parse(line.substring(6));
              handleLaunchEvent(card, event);
            } catch (e) {
              // skip malformed
            }
          }
        });

        read();
      }).catch(function () {
        if (launchBtn) launchBtn.disabled = false;
      });
    }

    read();
  }).catch(function (err) {
    if (consoleEl) {
      consoleEl.appendChild(
        createTextSpan("Network error: " + err.message, "error")
      );
    }
    card.classList.remove("starting");
    card.classList.add("failed");
    if (launchBtn) launchBtn.disabled = false;
    showToast("Network error", "error");
  });
}

// ── Handle SSE events on a launch card ───────────────────────────

function handleLaunchEvent(card, event) {
  var consoleEl = card.querySelector(".launch-console");
  var urlBar = card.querySelector(".launch-url-bar");
  var urlLink = card.querySelector(".launch-url-link");
  var launchBtn = card.querySelector(".launch-btn");
  var stopBtn = card.querySelector(".stop-cmd-btn");
  var name = card.dataset.name;

  switch (event.type) {
    case "status":
      card.className = card.className.replace(/\b(running|failed|starting)\b/g, "").trim();
      if (event.status === "running") {
        card.classList.add("running");
      } else if (event.status === "starting") {
        card.classList.add("starting");
      }
      if (event.pid) {
        card.dataset.pid = event.pid;
      }
      break;

    case "output":
      if (consoleEl) {
        var lineEl = document.createElement("div");
        lineEl.textContent = event.line;
        consoleEl.appendChild(lineEl);
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
      break;

    case "port":
      if (urlBar && urlLink) {
        urlLink.textContent = event.url;
        urlLink.href = event.url;
        urlBar.classList.add("visible");
      }
      card.dataset.port = event.port;
      card.dataset.url = event.url;
      var browserBtn = card.querySelector(".open-browser-btn");
      if (browserBtn) browserBtn.style.display = "";
      showToast(name + " available at " + event.url, "success");
      break;

    case "exit":
      card.className = card.className.replace(/\b(running|failed|starting)\b/g, "").trim();
      if (event.status === "failed") {
        card.classList.add("failed");
        showToast(name + " exited with code " + event.exit_code, "error");
      } else {
        showToast(name + " stopped", "info");
      }
      if (launchBtn) launchBtn.disabled = false;
      if (stopBtn) stopBtn.style.display = "none";
      break;
  }
}

// ── Stop a project ───────────────────────────────────────────────

function stopProject(name, processId) {
  var body = {};
  if (processId) body.process_id = processId;

  fetch("/api/launch/" + encodeURIComponent(name) + "/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast(name + " stopped", "info");
        var card = document.getElementById("launch-card-" + name);
        if (card) {
          card.className = card.className.replace(/\b(running|failed|starting)\b/g, "").trim();
          var launchBtn = card.querySelector(".launch-btn");
          var stopBtn = card.querySelector(".stop-cmd-btn");
          if (launchBtn) launchBtn.disabled = false;
          if (stopBtn) stopBtn.style.display = "none";
        }
      } else {
        showToast("Failed to stop " + name, "error");
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });
}

// ── Open URL in browser ──────────────────────────────────────────

function openInBrowser(url) {
  if (url) window.open(url, "_blank");
}

// ── Toggle console expand ────────────────────────────────────────

function toggleConsole(el) {
  el.classList.toggle("expanded");
}

// ── Poll launch status (every 10s) ──────────────────────────────

var _launchPollTimer = null;

function pollLaunchStatus() {
  fetch("/api/launch/status")
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      var processes = data.processes || [];
      var runningCount = data.running || 0;

      // Update footer process count (global)
      updateFooterProcessCount(runningCount);

      // Update launchpad cards if on launchpad page
      processes.forEach(function (proc) {
        var card = document.getElementById("launch-card-" + proc.project_name);
        if (!card) return;

        var dot = card.querySelector(".status-dot");
        if (dot) {
          dot.className = "status-dot";
          if (proc.status === "running") dot.classList.add("up");
          else if (proc.status === "failed") dot.classList.add("down");
          else if (proc.status === "starting") dot.classList.add("timeout");
          else dot.classList.add("unknown");
        }

        // Update port/URL if detected
        if (proc.port && proc.url) {
          card.dataset.port = proc.port;
          card.dataset.url = proc.url;
          var urlBar = card.querySelector(".launch-url-bar");
          var urlLink = card.querySelector(".launch-url-link");
          if (urlBar && urlLink) {
            urlLink.textContent = proc.url;
            urlLink.href = proc.url;
            urlBar.classList.add("visible");
          }
          var browserBtn = card.querySelector(".open-browser-btn");
          if (browserBtn) browserBtn.style.display = "";
        }
      });

      // Update dashboard process dots
      var dashDots = document.querySelectorAll(".card-process-dot");
      dashDots.forEach(function (dot) {
        var projName = dot.dataset.project;
        var proc = processes.find(function (p) {
          return p.project_name === projName && (p.status === "running" || p.status === "starting");
        });
        dot.className = "card-process-dot";
        if (proc) {
          dot.classList.add(proc.status);
        }
      });
    })
    .catch(function () {
      // silently fail
    });
}

function startLaunchPolling() {
  if (_launchPollTimer) return;
  pollLaunchStatus();
  _launchPollTimer = setInterval(pollLaunchStatus, 10000);
}

// Start polling on page load
document.addEventListener("DOMContentLoaded", function () {
  startLaunchPolling();
});
