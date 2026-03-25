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

// ── Launch from Project Page (SSE streaming) ────────────────────

function launchFromProject(projectName, command) {
  var consoleEl = document.getElementById("console-output");
  var consoleHeader = document.getElementById("console-header-text");
  var headerEl = document.getElementById("console-header");

  if (!consoleEl) return;

  consoleEl.classList.add("visible");
  if (headerEl) headerEl.style.display = "";
  clearElement(consoleEl);
  consoleEl.appendChild(createTextSpan("Launching...", "console-loading"));

  if (consoleHeader) {
    consoleHeader.textContent = "> " + command;
  }

  // Disable launch button, show stop
  var activeBtn = document.querySelector('.run-cmd-btn[data-command="' + command + '"]');
  if (activeBtn) activeBtn.disabled = true;

  var stopBar = document.getElementById("launch-stop-bar");
  if (stopBar) stopBar.style.display = "";

  var body = { command: command };

  fetch("/api/launch/" + encodeURIComponent(projectName), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(function (resp) {
    if (!resp.ok) {
      return resp.json().then(function (data) {
        clearElement(consoleEl);
        consoleEl.appendChild(
          createTextSpan("Error: " + (data.error || "Launch failed"), "error")
        );
        if (activeBtn) activeBtn.disabled = false;
        showToast("Launch failed", "error");
      });
    }

    clearElement(consoleEl);
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";

    function read() {
      reader.read().then(function (result) {
        if (result.done) {
          if (activeBtn) activeBtn.disabled = false;
          if (stopBar) stopBar.style.display = "none";
          return;
        }

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split("\n");
        buffer = lines.pop();

        lines.forEach(function (line) {
          if (line.startsWith("data: ")) {
            try {
              var event = JSON.parse(line.substring(6));
              _handleProjectLaunchEvent(event, consoleEl, activeBtn, stopBar, projectName);
            } catch (e) {}
          }
        });

        read();
      }).catch(function () {
        if (activeBtn) activeBtn.disabled = false;
        if (stopBar) stopBar.style.display = "none";
      });
    }

    read();
  }).catch(function (err) {
    clearElement(consoleEl);
    consoleEl.appendChild(
      createTextSpan("Network error: " + err.message, "error")
    );
    if (activeBtn) activeBtn.disabled = false;
    showToast("Network error", "error");
  });
}

function _handleProjectLaunchEvent(event, consoleEl, activeBtn, stopBar, projectName) {
  var urlBar = document.getElementById("launch-url-bar");

  switch (event.type) {
    case "status":
      // Update status dots on run command buttons
      document.querySelectorAll('.run-cmd-btn[data-project="' + projectName + '"]').forEach(function (btn) {
        var dot = btn.querySelector(".status-dot");
        if (dot) {
          dot.className = "status-dot";
          if (event.status === "running") dot.classList.add("up");
          else if (event.status === "starting") dot.classList.add("timeout");
        }
      });
      break;

    case "output":
      var lineEl = document.createElement("div");
      lineEl.textContent = event.line;
      consoleEl.appendChild(lineEl);
      consoleEl.scrollTop = consoleEl.scrollHeight;
      break;

    case "port":
      if (urlBar) {
        var link = urlBar.querySelector("a");
        if (link) {
          link.textContent = event.url;
          link.href = event.url;
        }
        urlBar.classList.add("visible");
      }
      showToast("Available at " + event.url, "success");
      break;

    case "exit":
      if (activeBtn) activeBtn.disabled = false;
      if (stopBar) stopBar.style.display = "none";
      // Reset status dots
      document.querySelectorAll('.run-cmd-btn[data-project="' + projectName + '"]').forEach(function (btn) {
        var dot = btn.querySelector(".status-dot");
        if (dot) dot.className = "status-dot unknown";
      });
      if (event.exit_code !== 0 && event.exit_code !== null) {
        showToast("Process exited with code " + event.exit_code, "error");
      }
      break;
  }
}

function stopFromProject(projectName) {
  fetch("/api/launch/" + encodeURIComponent(projectName) + "/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast("Process stopped", "info");
      } else {
        showToast("No running process to stop", "error");
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });
}

// ── Footer Process Count (global) ────────────────────────────────

function updateFooterProcessCount(count) {
  var countEl = document.getElementById("footer-proc-count");
  var dotEl = document.getElementById("footer-proc-dot");
  if (countEl) countEl.textContent = count;
  if (dotEl) {
    if (count > 0) {
      dotEl.classList.add("active");
    } else {
      dotEl.classList.remove("active");
    }
  }
}

// ── Dashboard Quick Actions ──────────────────────────────────────

function dashboardLaunch(name, event) {
  if (event) event.stopPropagation();
  fetch("/api/launch/" + encodeURIComponent(name), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  }).then(function (resp) {
    if (resp.ok) {
      showToast(name + " launched", "success");
      // Consume the SSE stream silently
      var reader = resp.body.getReader();
      function drain() {
        reader.read().then(function (result) {
          if (!result.done) drain();
        });
      }
      drain();
    } else {
      resp.json().then(function (data) {
        showToast("Failed: " + (data.error || "Unknown"), "error");
      });
    }
  }).catch(function (err) {
    showToast("Error: " + err.message, "error");
  });
}

function dashboardOpenBrowser(url, event) {
  if (event) event.stopPropagation();
  if (url) window.open(url, "_blank");
}

// ── Dashboard Service Controls ───────────────────────────────────

function dashboardStartService(name, event) {
  if (event) event.stopPropagation();
  var btn = event && event.currentTarget;
  if (btn) btn.disabled = true;
  showToast("Starting " + name + "...", "info");

  fetch("/api/ops/services/" + encodeURIComponent(name) + "/start", {
    method: "POST",
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast(name + " started", "success");
        setTimeout(function () { location.reload(); }, 1500);
      } else {
        showToast(data.error || "Start failed", "error");
        if (btn) btn.disabled = false;
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
      if (btn) btn.disabled = false;
    });
}

function dashboardStopService(name, event) {
  if (event) event.stopPropagation();
  if (!confirm('Stop service "' + name + '"?\n\nThis will shut down the running service.')) return;
  var btn = event && event.currentTarget;
  if (btn) btn.disabled = true;
  showToast("Stopping " + name + "...", "info");

  fetch("/api/ops/services/" + encodeURIComponent(name) + "/stop", {
    method: "POST",
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast(name + " stopped", "success");
        setTimeout(function () { location.reload(); }, 1500);
      } else {
        showToast(data.error || "Stop failed", "error");
        if (btn) btn.disabled = false;
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
      if (btn) btn.disabled = false;
    });
}

// ── Ask AI (Project Page) ────────────────────────────────────────

function askAI(question, projectName) {
  var responseEl = document.getElementById("ask-response");
  if (!responseEl) return;

  responseEl.classList.add("visible");
  clearElement(responseEl);
  responseEl.appendChild(createTextSpan("Thinking...", "console-loading"));

  var payload = { question: question, project: projectName || "" };
  var projectModelSelect = document.getElementById("project-model-select");
  if (projectModelSelect && projectModelSelect.value) {
    payload.model = projectModelSelect.value;
  }

  fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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
  var chatPayload = { question: question, project: projectName };
  var chatModelSelect = document.getElementById("project-model-select");
  if (chatModelSelect && chatModelSelect.value) {
    chatPayload.model = chatModelSelect.value;
  }

  fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(chatPayload),
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

// ── Project Manager Integration ──────────────────────────────

function pmAdd(service) {
  /* pmConfig is set in the project.html template */
  if (typeof pmConfig === "undefined") return;

  var name = pmConfig.projectName;
  var desc = pmConfig.description || "";
  var path = pmConfig.projectPath;
  var ptype = pmConfig.projectType;
  var body = name + " (" + ptype + ")\n\nPath: " + path;
  if (desc) body += "\n\n" + desc;

  var url = null;

  switch (service) {
    case "trello":
      url = "https://trello.com/add-card"
        + "?mode=popup"
        + "&name=" + encodeURIComponent(name)
        + "&desc=" + encodeURIComponent(body);
      break;

    case "linear":
      if (!pmConfig.linearTeam) {
        showToast("Set your Linear team in Settings first", "info");
        return;
      }
      url = "https://linear.app/" + encodeURIComponent(pmConfig.linearTeam)
        + "/new"
        + "?title=" + encodeURIComponent(name)
        + "&description=" + encodeURIComponent(body);
      break;

    case "github":
      if (!pmConfig.gitRemote) {
        showToast("No GitHub remote on this project", "error");
        return;
      }
      var repo = pmConfig.gitRemote
        .replace(/\.git$/, "")
        .replace(/^git@github\.com:/, "https://github.com/");
      if (repo.indexOf("github.com") === -1) {
        showToast("Remote is not a GitHub URL", "error");
        return;
      }
      url = repo + "/issues/new"
        + "?title=" + encodeURIComponent(name + " - Task")
        + "&body=" + encodeURIComponent(body);
      break;

    case "jira":
      if (!pmConfig.jiraInstance) {
        showToast("Set your Jira instance in Settings first", "info");
        return;
      }
      var jiraBase = pmConfig.jiraInstance;
      if (jiraBase.indexOf("http") !== 0) jiraBase = "https://" + jiraBase;
      url = jiraBase + "/secure/CreateIssue!default.jspa";
      if (pmConfig.jiraProject) {
        url += "?pid=&summary=" + encodeURIComponent(name);
      }
      break;

    case "asana":
      if (!pmConfig.asanaWorkspace) {
        showToast("Set your Asana workspace in Settings first", "info");
        return;
      }
      url = "https://app.asana.com/0/"
        + encodeURIComponent(pmConfig.asanaWorkspace)
        + "/list";
      break;

    case "notion":
    case "copy":
      var text = "# " + name + "\n"
        + "**Type:** " + ptype + "\n"
        + "**Path:** `" + path + "`\n";
      if (desc) text += "\n" + desc + "\n";
      if (pmConfig.gitRemote) text += "\n**Remote:** " + pmConfig.gitRemote + "\n";
      navigator.clipboard.writeText(text).then(function () {
        showToast(
          service === "notion"
            ? "Project info copied \u2014 paste into Notion"
            : "Project info copied to clipboard",
          "success"
        );
      }).catch(function () {
        showToast("Clipboard not available", "error");
      });
      return;
  }

  if (url) {
    window.open(url, "_blank", "noopener");
    showToast("Opening " + service + "...", "success");
  }
}

// ── Editor Launcher ──────────────────────────────────────────

function checkEditors() {
  fetch("/api/editors")
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      var editors = ["code", "cursor"];
      editors.forEach(function (ed) {
        var btn = document.getElementById("btn-" + (ed === "code" ? "vscode" : ed));
        var status = document.getElementById("status-" + ed);
        if (!btn || !status) return;

        if (data[ed]) {
          btn.disabled = false;
          status.textContent = "available";
          status.className = "editor-status available";
        } else {
          btn.disabled = true;
          status.textContent = "not found";
          status.className = "editor-status unavailable";
        }
      });
    })
    .catch(function () {
      // Silently fail — buttons stay disabled
    });
}

function openInEditor(projectName, editor) {
  var btn = document.getElementById("btn-" + (editor === "code" ? "vscode" : editor));
  if (btn) btn.disabled = true;

  fetch("/api/open-editor/" + encodeURIComponent(projectName), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ editor: editor }),
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      if (result.ok) {
        showToast("Opening in " + (editor === "code" ? "VS Code" : "Cursor"), "success");
      } else {
        showToast(result.data.error || "Failed to open editor", "error");
      }
      if (btn) btn.disabled = false;
    })
    .catch(function (err) {
      showToast("Network error: " + err.message, "error");
      if (btn) btn.disabled = false;
    });
}

// ── Load Changelog ───────────────────────────────────────────

function loadChangelog(projectName) {
  var container = document.getElementById("changelog-container");
  if (!container) return;

  fetch("/api/changelog/" + encodeURIComponent(projectName))
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      clearElement(container);

      if (!data.is_git) {
        container.appendChild(
          createTextSpan("Not a git repository.", "changelog-empty")
        );
        return;
      }

      var entries = data.entries || [];
      if (entries.length === 0) {
        container.appendChild(
          createTextSpan("No commits found.", "changelog-empty")
        );
        return;
      }

      var list = document.createElement("ul");
      list.className = "changelog-list";

      entries.forEach(function (entry) {
        var li = document.createElement("li");
        li.className = "changelog-entry";

        var hashSpan = document.createElement("span");
        hashSpan.className = "changelog-hash";
        hashSpan.textContent = entry.short_hash;
        hashSpan.title = entry.hash;
        li.appendChild(hashSpan);

        var bodyDiv = document.createElement("div");
        var msgDiv = document.createElement("div");
        msgDiv.className = "changelog-message";
        msgDiv.textContent = entry.message;
        bodyDiv.appendChild(msgDiv);

        var metaDiv = document.createElement("div");
        metaDiv.className = "changelog-meta";

        var authorSpan = document.createElement("span");
        authorSpan.className = "author";
        authorSpan.textContent = entry.author;
        metaDiv.appendChild(authorSpan);

        metaDiv.appendChild(
          document.createTextNode(" \u00B7 " + entry.date)
        );
        bodyDiv.appendChild(metaDiv);

        li.appendChild(bodyDiv);
        list.appendChild(li);
      });

      container.appendChild(list);
    })
    .catch(function (err) {
      clearElement(container);
      container.appendChild(
        createTextSpan("Failed to load changelog.", "changelog-empty")
      );
    });
}

// ── Load Repo Visibility ────────────────────────────────────

function loadVisibility(projectName) {
  var badge = document.getElementById("visibility-badge");
  if (!badge) return;

  fetch("/api/repo-visibility/" + encodeURIComponent(projectName))
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      var vis = data.visibility || "unknown";
      badge.className = "visibility-badge " + vis;
      badge.textContent = vis;
    })
    .catch(function () {
      // Silently fail — no badge shown
    });
}

// ── Save Project Notes ───────────────────────────────────────

function saveNotes(projectName, content) {
  var statusEl = document.getElementById("notes-status");

  if (statusEl) {
    statusEl.textContent = "Saving...";
    statusEl.className = "notes-status";
  }

  fetch("/api/notes/" + encodeURIComponent(projectName), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: content }),
  })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data };
      });
    })
    .then(function (result) {
      if (result.ok) {
        if (statusEl) {
          statusEl.textContent = "Saved!";
          statusEl.className = "notes-status saved";
          setTimeout(function () {
            statusEl.textContent = "Saves to .codequest-notes.md";
            statusEl.className = "notes-status";
          }, 2000);
        }
        showToast("Notes saved", "success");
      } else {
        if (statusEl) {
          statusEl.textContent = "Save failed";
          statusEl.className = "notes-status error";
        }
        showToast("Failed to save notes", "error");
      }
    })
    .catch(function (err) {
      if (statusEl) {
        statusEl.textContent = "Network error";
        statusEl.className = "notes-status error";
      }
      showToast("Network error: " + err.message, "error");
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

var _activeTypeFilter = "all";
var _activeTagFilter = "all";

function _applyFilters() {
  var cards = document.querySelectorAll(".project-card");
  cards.forEach(function (card) {
    var typeMatch = _activeTypeFilter === "all" || card.dataset.type === _activeTypeFilter;
    var tagMatch = _activeTagFilter === "all" ||
      (card.dataset.tags && card.dataset.tags.split(",").indexOf(_activeTagFilter) !== -1);
    card.style.display = (typeMatch && tagMatch) ? "" : "none";
  });
}

function filterByType(type) {
  _activeTypeFilter = type;
  var buttons = document.querySelectorAll(".filter-btn");
  buttons.forEach(function (btn) {
    btn.classList.toggle("active", btn.dataset.type === type);
  });
  _applyFilters();
}

function filterByTag(tag) {
  _activeTagFilter = tag;
  var buttons = document.querySelectorAll(".tag-filter-btn");
  buttons.forEach(function (btn) {
    btn.classList.toggle("active", btn.dataset.tag === tag);
  });
  _applyFilters();
}

// ── Git Status Loading ──────────────────────────────────────────

function loadGitStatus(projectName, cardEl) {
  fetch("/api/git-status/" + encodeURIComponent(projectName))
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      var dot = document.getElementById("git-dot-" + projectName);
      var branch = document.getElementById("git-branch-" + projectName);
      if (dot) {
        if (data.behind > 0) {
          dot.className = "git-status-dot behind";
          dot.title = "Behind upstream by " + data.behind;
        } else if (data.dirty) {
          dot.className = "git-status-dot dirty";
          dot.title = "Uncommitted changes";
        } else {
          dot.className = "git-status-dot clean";
          dot.title = "Clean";
        }
        if (data.ahead > 0) {
          dot.title += " (ahead by " + data.ahead + ")";
        }
      }
      if (branch && data.branch) {
        branch.textContent = data.branch;
      }
    })
    .catch(function () {
      // Silently fail
    });
}

// ── Favorites ───────────────────────────────────────────────────

function toggleFavorite(name, btnEl) {
  fetch("/api/favorite/" + encodeURIComponent(name), { method: "POST" })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.favorite) {
        btnEl.classList.add("active");
        btnEl.closest(".project-card").dataset.favorite = "true";
        showToast(name + " added to favorites", "success");
      } else {
        btnEl.classList.remove("active");
        btnEl.closest(".project-card").dataset.favorite = "false";
        showToast(name + " removed from favorites", "info");
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });
}

// ── Tags ────────────────────────────────────────────────────────

function addTagToProject(name) {
  var tag = prompt("Enter tag name:");
  if (!tag || !tag.trim()) return;
  tag = tag.trim();

  // Get current tags
  var card = document.querySelector('.project-card[data-name="' + name + '"]');
  var currentTags = card && card.dataset.tags ? card.dataset.tags.split(",").filter(Boolean) : [];
  if (currentTags.indexOf(tag) === -1) {
    currentTags.push(tag);
  }

  fetch("/api/tags/" + encodeURIComponent(name), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tags: currentTags }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast("Tag added: " + tag, "success");
      if (card) card.dataset.tags = (data.tags || []).join(",");
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });
}

// ── Sort Cards ──────────────────────────────────────────────────

function sortCards(criterion) {
  var grid = document.getElementById("project-grid");
  if (!grid) return;
  var cards = Array.from(grid.querySelectorAll(".project-card"));

  cards.sort(function (a, b) {
    switch (criterion) {
      case "favorites":
        var fa = a.dataset.favorite === "true" ? 0 : 1;
        var fb = b.dataset.favorite === "true" ? 0 : 1;
        if (fa !== fb) return fa - fb;
        return (a.dataset.name || "").localeCompare(b.dataset.name || "");
      case "name-az":
        return (a.dataset.name || "").localeCompare(b.dataset.name || "");
      case "name-za":
        return (b.dataset.name || "").localeCompare(a.dataset.name || "");
      case "modified":
        return (parseFloat(b.dataset.modified) || 0) - (parseFloat(a.dataset.modified) || 0);
      case "type":
        return (a.dataset.type || "").localeCompare(b.dataset.type || "");
      default:
        return 0;
    }
  });

  cards.forEach(function (card) { grid.appendChild(card); });
  localStorage.setItem("cq-sort", criterion);
}

// ── Bulk Actions ────────────────────────────────────────────────

var _bulkSelected = new Set();

function updateBulkBar() {
  var bar = document.getElementById("bulk-bar");
  var countEl = document.getElementById("bulk-count");
  if (!bar) return;
  if (_bulkSelected.size > 0) {
    bar.style.display = "";
    countEl.textContent = _bulkSelected.size + " selected";
  } else {
    bar.style.display = "none";
  }
}

function bulkOpenEditor(editor) {
  if (_bulkSelected.size === 0) return;
  fetch("/api/bulk/open-editor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names: Array.from(_bulkSelected), editor: editor }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast("Opened " + (data.opened || []).length + " projects", "success");
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });
}

function bulkClear() {
  _bulkSelected.clear();
  document.querySelectorAll(".bulk-check").forEach(function (cb) {
    cb.checked = false;
    cb.closest(".project-card").classList.remove("card-selected");
  });
  updateBulkBar();
}

// ── Keyboard Navigation ─────────────────────────────────────────

function _getVisibleCards() {
  return Array.from(document.querySelectorAll(".project-card")).filter(function (c) {
    return c.style.display !== "none";
  });
}

function _getGridColumns() {
  var grid = document.getElementById("project-grid");
  if (!grid) return 1;
  var style = window.getComputedStyle(grid);
  var cols = style.getPropertyValue("grid-template-columns");
  return cols ? cols.split(" ").length : 1;
}

// ── Model Switcher (Global Nav Dropdown) ─────────────────────────

function loadModelList(callback) {
  fetch("/api/models")
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (callback) callback(data.models || []);
    })
    .catch(function () {
      if (callback) callback([]);
    });
}

function renderModelDropdown(models) {
  var dropdown = document.getElementById("model-dropdown");
  if (!dropdown) return;
  clearElement(dropdown);

  models.forEach(function (m) {
    var item = document.createElement("button");
    item.className = "model-dropdown-item";
    if (m.active) item.classList.add("active");

    var dot = document.createElement("span");
    dot.className = "model-dot";
    if (m.active) dot.classList.add("active");
    else if (m.available) dot.classList.add("available");
    else dot.classList.add("unavailable");
    item.appendChild(dot);

    var nameSpan = document.createElement("span");
    nameSpan.className = "model-item-name";
    nameSpan.textContent = m.name;
    item.appendChild(nameSpan);

    var badge = document.createElement("span");
    badge.className = "model-item-badge";
    if (m.active) {
      badge.textContent = "active";
    } else if (!m.available) {
      badge.textContent = "offline";
    }
    if (badge.textContent) item.appendChild(badge);

    if (!m.active) {
      item.addEventListener("click", function (e) {
        e.stopPropagation();
        switchModel(m.name);
      });
    }

    dropdown.appendChild(item);
  });
}

function switchModel(name) {
  fetch("/api/model/switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.active) {
        var nameEl = document.getElementById("model-switcher-name");
        if (nameEl) nameEl.textContent = data.active;
        showToast("Switched to " + data.active, "success");
        // Refresh dropdown
        loadModelList(renderModelDropdown);
        // Update project picker if present
        var projectSelect = document.getElementById("project-model-select");
        if (projectSelect) {
          projectSelect.value = data.active;
        }
      } else {
        showToast(data.error || "Failed to switch model", "error");
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    });

  // Close dropdown
  var dropdown = document.getElementById("model-dropdown");
  if (dropdown) dropdown.classList.remove("open");
}

function populateProjectModelPicker(models) {
  var select = document.getElementById("project-model-select");
  if (!select) return;

  // Remember current value
  var currentVal = select.value;
  clearElement(select);

  models.forEach(function (m) {
    var opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.name;
    if (!m.available) {
      opt.textContent += " (offline)";
    }
    if (m.active && !currentVal) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });

  // Restore selection if it was set
  if (currentVal) select.value = currentVal;
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

  // Tag filter buttons
  document.querySelectorAll(".tag-filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      filterByTag(btn.dataset.tag);
    });
  });

  // Sort select
  var sortSelect = document.getElementById("sort-select");
  if (sortSelect) {
    var savedSort = localStorage.getItem("cq-sort") || "favorites";
    sortSelect.value = savedSort;
    sortSelect.addEventListener("change", function () {
      sortCards(sortSelect.value);
    });
    // Apply saved sort on load
    if (savedSort !== "favorites") {
      sortCards(savedSort);
    }
  }

  // Rescan button
  var rescanBtn = document.getElementById("rescan-btn");
  if (rescanBtn) {
    rescanBtn.addEventListener("click", function (e) {
      e.preventDefault();
      rescanProjects();
    });
  }

  // Load git status for all git project cards
  document.querySelectorAll(".project-card[data-is-git='true']").forEach(function (card) {
    var name = card.dataset.name;
    if (name) loadGitStatus(name, card);
  });

  // Bulk checkboxes
  document.querySelectorAll(".bulk-check").forEach(function (cb) {
    cb.addEventListener("change", function () {
      var name = cb.dataset.name;
      if (cb.checked) {
        _bulkSelected.add(name);
        cb.closest(".project-card").classList.add("card-selected");
      } else {
        _bulkSelected.delete(name);
        cb.closest(".project-card").classList.remove("card-selected");
      }
      updateBulkBar();
    });
  });

  // Bulk action buttons
  var bulkOpenBtn = document.getElementById("bulk-open-vscode");
  if (bulkOpenBtn) {
    bulkOpenBtn.addEventListener("click", function () { bulkOpenEditor("code"); });
  }
  var bulkTagBtn = document.getElementById("bulk-tag-btn");
  if (bulkTagBtn) {
    bulkTagBtn.addEventListener("click", function () {
      var tag = prompt("Enter tag for selected projects:");
      if (!tag || !tag.trim()) return;
      tag = tag.trim();
      _bulkSelected.forEach(function (name) {
        var card = document.querySelector('.project-card[data-name="' + name + '"]');
        var currentTags = card && card.dataset.tags ? card.dataset.tags.split(",").filter(Boolean) : [];
        if (currentTags.indexOf(tag) === -1) currentTags.push(tag);
        fetch("/api/tags/" + encodeURIComponent(name), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tags: currentTags }),
        }).then(function () {
          if (card) card.dataset.tags = currentTags.join(",");
        });
      });
      showToast("Tagged " + _bulkSelected.size + " projects with: " + tag, "success");
    });
  }
  var bulkClearBtn = document.getElementById("bulk-clear");
  if (bulkClearBtn) {
    bulkClearBtn.addEventListener("click", bulkClear);
  }

  // Keyboard navigation on dashboard
  var projectGrid = document.getElementById("project-grid");
  if (projectGrid) {
    document.addEventListener("keydown", function (e) {
      var target = e.target;
      var tagName = target.tagName.toLowerCase();

      // Don't hijack input fields
      if (tagName === "input" || tagName === "textarea" || tagName === "select") {
        if (e.key === "Escape") {
          target.blur();
          e.preventDefault();
        }
        return;
      }

      var cards = _getVisibleCards();
      if (cards.length === 0) return;

      var focusedCard = document.activeElement;
      var focusedIndex = cards.indexOf(focusedCard);
      var cols = _getGridColumns();

      switch (e.key) {
        case "/":
          e.preventDefault();
          if (searchInput) searchInput.focus();
          break;
        case "Escape":
          // Clear search and filters
          if (searchInput && searchInput.value) {
            searchInput.value = "";
            window.location.href = "/";
          }
          break;
        case "f":
          if (focusedIndex >= 0) {
            var favBtn = cards[focusedIndex].querySelector(".favorite-btn");
            if (favBtn) favBtn.click();
          }
          break;
        case "ArrowRight":
          e.preventDefault();
          if (focusedIndex < 0) {
            cards[0].focus();
          } else if (focusedIndex < cards.length - 1) {
            cards[focusedIndex + 1].focus();
          }
          break;
        case "ArrowLeft":
          e.preventDefault();
          if (focusedIndex < 0) {
            cards[0].focus();
          } else if (focusedIndex > 0) {
            cards[focusedIndex - 1].focus();
          }
          break;
        case "ArrowDown":
          e.preventDefault();
          if (focusedIndex < 0) {
            cards[0].focus();
          } else {
            var nextIdx = Math.min(focusedIndex + cols, cards.length - 1);
            cards[nextIdx].focus();
          }
          break;
        case "ArrowUp":
          e.preventDefault();
          if (focusedIndex < 0) {
            cards[0].focus();
          } else {
            var prevIdx = Math.max(focusedIndex - cols, 0);
            cards[prevIdx].focus();
          }
          break;
        case "Enter":
          if (focusedIndex >= 0) {
            var link = cards[focusedIndex].querySelector(".card-link");
            if (link) link.click();
          }
          break;
      }
    });
  }

  // Run command buttons (project detail page) — use streaming launch
  document.querySelectorAll(".run-cmd-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var project = btn.dataset.project;
      var command = btn.dataset.command;
      if (project && command) {
        launchFromProject(project, command);
      }
    });
  });

  // Notes save button (project detail page)
  var notesSaveBtn = document.getElementById("notes-save-btn");
  if (notesSaveBtn) {
    notesSaveBtn.addEventListener("click", function (e) {
      e.preventDefault();
      var textarea = document.getElementById("notes-textarea");
      if (textarea) {
        saveNotes(textarea.dataset.project, textarea.value);
      }
    });
  }

  // Ctrl+S to save notes when textarea is focused
  var notesTextarea = document.getElementById("notes-textarea");
  if (notesTextarea) {
    notesTextarea.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        saveNotes(notesTextarea.dataset.project, notesTextarea.value);
      }
    });
  }

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
  document.querySelectorAll(".nav-links > a").forEach(function (link) {
    var href = link.getAttribute("href");
    if (href === currentPath || (href === "/" && currentPath === "/")) {
      link.classList.add("active");
    } else if (href !== "/" && currentPath.startsWith(href)) {
      link.classList.add("active");
    }
  });

  // Nav dropdown toggle
  document.querySelectorAll(".nav-dropdown-btn").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var menu = btn.nextElementSibling;
      var wasOpen = menu.classList.contains("open");
      // Close all dropdowns
      document.querySelectorAll(".nav-dropdown-menu").forEach(function (m) {
        m.classList.remove("open");
      });
      if (!wasOpen) {
        menu.classList.add("open");
      }
    });
  });

  // Close nav dropdowns on outside click
  document.addEventListener("click", function (e) {
    if (!e.target.closest(".nav-dropdown")) {
      document.querySelectorAll(".nav-dropdown-menu").forEach(function (m) {
        m.classList.remove("open");
      });
    }
  });

  // Highlight active dropdown menu items
  document.querySelectorAll(".nav-dropdown-menu a").forEach(function (link) {
    if (link.getAttribute("href") === currentPath) {
      link.classList.add("active");
    }
  });

  // Model switcher dropdown toggle
  var modelBtn = document.getElementById("model-switcher-btn");
  var modelDropdown = document.getElementById("model-dropdown");
  if (modelBtn && modelDropdown) {
    modelBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var isOpen = modelDropdown.classList.contains("open");
      if (!isOpen) {
        loadModelList(function (models) {
          renderModelDropdown(models);
          modelDropdown.classList.add("open");
        });
      } else {
        modelDropdown.classList.remove("open");
      }
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", function () {
      modelDropdown.classList.remove("open");
    });

    modelDropdown.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  // Populate project-level model picker if present
  var projectModelSelect = document.getElementById("project-model-select");
  if (projectModelSelect) {
    loadModelList(populateProjectModelPicker);
  }
});
