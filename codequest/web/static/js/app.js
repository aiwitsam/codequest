/* ====================================================================
   CodeQuest - Dashboard Interactivity
   ====================================================================
   Handles command execution, AI chat, project search, toast
   notifications, and typing animations.
   ==================================================================== */

"use strict";

// ── Toast Notifications ───────────────────────────────────────────

function showToast(message, type) {
  type = type || "info";
  var container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  var toast = document.createElement("div");
  toast.className = "toast " + type;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(function () {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 4000);
}

// ── Debounce Utility ──────────────────────────────────────────────

function debounce(fn, delay) {
  var timer = null;
  return function () {
    var args = arguments;
    var self = this;
    clearTimeout(timer);
    timer = setTimeout(function () {
      fn.apply(self, args);
    }, delay);
  };
}

// ── HTML Escaping ────────────────────────────────────────────────

function escapeHtml(text) {
  var div = document.createElement("div");
  div.textContent = text;
  return div.textContent;
}

// ── Safe DOM helpers ─────────────────────────────────────────────
// Build DOM elements safely without innerHTML to prevent XSS.

function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

function createTextSpan(text, className) {
  var span = document.createElement("span");
  if (className) span.className = className;
  span.textContent = text;
  return span;
}

// ── Typing Animation ─────────────────────────────────────────────

function typeText(element, text, speed) {
  speed = speed || 12;
  return new Promise(function (resolve) {
    var i = 0;
    element.textContent = "";
    function step() {
      if (i < text.length) {
        element.textContent += text.charAt(i);
        i++;
        var parent = element.closest(
          ".chat-messages, .console-output, .ask-response"
        );
        if (parent) {
          parent.scrollTop = parent.scrollHeight;
        }
        setTimeout(step, speed);
      } else {
        resolve();
      }
    }
    step();
  });
}

// ── Run Command ──────────────────────────────────────────────────

function runCommand(projectName, command) {
  var consoleEl = document.getElementById("console-output");
  var consoleHeader = document.getElementById("console-header-text");

  if (!consoleEl) return;

  consoleEl.classList.add("visible");
  clearElement(consoleEl);
  consoleEl.appendChild(createTextSpan("Executing...", "console-loading"));

  if (consoleHeader) {
    consoleHeader.textContent = "> " + command;
  }

  fetch("/api/run/" + encodeURIComponent(projectName), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: command }),
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      clearElement(consoleEl);
      if (result.ok) {
        var output = result.data.output || "(no output)";
        var rc = result.data.returncode;

        var statusSpan = document.createElement("span");
        if (rc === 0) {
          statusSpan.className = "info";
          statusSpan.textContent = "[OK] ";
          showToast("Command completed", "success");
        } else {
          statusSpan.className = "error";
          statusSpan.textContent = "[EXIT " + rc + "] ";
          showToast("Command exited with code " + rc, "error");
        }
        consoleEl.appendChild(statusSpan);
        consoleEl.appendChild(document.createTextNode(output));
      } else {
        consoleEl.appendChild(
          createTextSpan(
            "Error: " + (result.data.error || "Unknown error"),
            "error"
          )
        );
        showToast("Command failed", "error");
      }
      consoleEl.scrollTop = consoleEl.scrollHeight;
    })
    .catch(function (err) {
      clearElement(consoleEl);
      consoleEl.appendChild(
        createTextSpan("Network error: " + err.message, "error")
      );
      showToast("Network error", "error");
    });
}

// ── Ask AI (Project Page) ────────────────────────────────────────

function askAI(question, projectName) {
  var responseEl = document.getElementById("ask-response");
  if (!responseEl) return;

  responseEl.classList.add("visible");
  clearElement(responseEl);
  responseEl.appendChild(createTextSpan("Thinking...", "console-loading"));

  fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question, project: projectName || "" }),
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      clearElement(responseEl);
      if (result.ok) {
        var modelTag = document.createElement("span");
        modelTag.className = "ask-model-tag";
        modelTag.textContent = result.data.model || "AI";
        responseEl.appendChild(modelTag);

        var textEl = document.createElement("span");
        responseEl.appendChild(textEl);
        typeText(textEl, result.data.answer || "No answer received.");
      } else {
        responseEl.appendChild(
          createTextSpan(result.data.error || "Error", "error")
        );
      }
    })
    .catch(function (err) {
      clearElement(responseEl);
      responseEl.appendChild(
        createTextSpan("Network error: " + err.message, "error")
      );
    });
}

// ── Chat (Assistant Page) ────────────────────────────────────────

function sendChatMessage() {
  var input = document.getElementById("chat-input");
  var messages = document.getElementById("chat-messages");
  var projectSelect = document.getElementById("project-select");

  if (!input || !messages) return;

  var question = input.value.trim();
  if (!question) return;

  input.value = "";

  // Remove welcome message if present
  var welcome = messages.querySelector(".chat-welcome");
  if (welcome) welcome.remove();

  // Add user message
  var userMsg = document.createElement("div");
  userMsg.className = "chat-message user";
  var userMeta = document.createElement("div");
  userMeta.className = "msg-meta";
  userMeta.textContent = "You";
  userMsg.appendChild(userMeta);
  userMsg.appendChild(document.createTextNode(question));
  messages.appendChild(userMsg);
  messages.scrollTop = messages.scrollHeight;

  // Add placeholder for assistant response
  var assistantMsg = document.createElement("div");
  assistantMsg.className = "chat-message assistant";
  var assistMeta = document.createElement("div");
  assistMeta.className = "msg-meta";
  assistMeta.textContent = "Assistant";
  assistantMsg.appendChild(assistMeta);
  assistantMsg.appendChild(createTextSpan("Thinking", "console-loading"));
  messages.appendChild(assistantMsg);
  messages.scrollTop = messages.scrollHeight;

  var projectName = projectSelect ? projectSelect.value : "";

  fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question, project: projectName }),
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      var answer = result.data.answer || "No response received.";
      var model = result.data.model || "AI";

      // Rebuild assistant message safely
      clearElement(assistantMsg);
      var meta = document.createElement("div");
      meta.className = "msg-meta";
      meta.textContent = model;
      assistantMsg.appendChild(meta);

      var textSpan = document.createElement("span");
      assistantMsg.appendChild(textSpan);
      typeText(textSpan, answer);

      messages.scrollTop = messages.scrollHeight;
    })
    .catch(function (err) {
      clearElement(assistantMsg);
      var meta = document.createElement("div");
      meta.className = "msg-meta";
      meta.textContent = "Error";
      assistantMsg.appendChild(meta);
      assistantMsg.appendChild(createTextSpan(err.message, "error"));
      messages.scrollTop = messages.scrollHeight;
    });
}

// ── Rescan Projects ──────────────────────────────────────────────

function rescanProjects() {
  showToast("Scanning projects...", "info");

  fetch("/api/rescan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      if (result.ok) {
        showToast("Found " + result.data.count + " projects", "success");
        setTimeout(function () {
          window.location.reload();
        }, 1200);
      } else {
        showToast(
          "Scan failed: " + (result.data.error || "Unknown error"),
          "error"
        );
      }
    })
    .catch(function (err) {
      showToast("Network error: " + err.message, "error");
    });
}

// ── Search Projects ──────────────────────────────────────────────

function searchProjects(query) {
  if (query && query.trim()) {
    window.location.href = "/search?q=" + encodeURIComponent(query.trim());
  } else {
    window.location.href = "/";
  }
}

// ── Filter Projects (client-side) ────────────────────────────────

function filterByType(type) {
  var cards = document.querySelectorAll(".project-card");
  var buttons = document.querySelectorAll(".filter-btn");

  buttons.forEach(function (btn) {
    if (btn.dataset.type === type) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  cards.forEach(function (card) {
    if (type === "all" || card.dataset.type === type) {
      card.style.display = "";
    } else {
      card.style.display = "none";
    }
  });
}

// ── Event Binding on DOM Ready ───────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  // Search input (debounced)
  var searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.focus();

    var debouncedSearch = debounce(function (e) {
      searchProjects(e.target.value);
    }, 600);

    searchInput.addEventListener("input", debouncedSearch);

    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        searchProjects(searchInput.value);
      }
    });
  }

  // Filter buttons
  document.querySelectorAll(".filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      filterByType(btn.dataset.type);
    });
  });

  // Rescan button
  var rescanBtn = document.getElementById("rescan-btn");
  if (rescanBtn) {
    rescanBtn.addEventListener("click", function (e) {
      e.preventDefault();
      rescanProjects();
    });
  }

  // Run command buttons (project detail page)
  document.querySelectorAll(".run-cmd-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var project = btn.dataset.project;
      var command = btn.dataset.command;
      if (project && command) {
        runCommand(project, command);
      }
    });
  });

  // Ask form (project detail page)
  var askForm = document.getElementById("ask-form");
  if (askForm) {
    askForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = document.getElementById("ask-input");
      var project = askForm.dataset.project || "";
      if (input && input.value.trim()) {
        askAI(input.value.trim(), project);
        input.value = "";
      }
    });
  }

  // Chat input (assistant page)
  var chatInput = document.getElementById("chat-input");
  if (chatInput) {
    chatInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  var chatSendBtn = document.getElementById("chat-send-btn");
  if (chatSendBtn) {
    chatSendBtn.addEventListener("click", function (e) {
      e.preventDefault();
      sendChatMessage();
    });
  }

  // Active nav link highlighting
  var currentPath = window.location.pathname;
  document.querySelectorAll(".nav-links a").forEach(function (link) {
    var href = link.getAttribute("href");
    if (href === currentPath || (href === "/" && currentPath === "/")) {
      link.classList.add("active");
    } else if (href !== "/" && currentPath.startsWith(href)) {
      link.classList.add("active");
    }
  });
});
