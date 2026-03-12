/* Ollama Hub - Pull with SSE, delete, GPU refresh */
"use strict";

function pullModel() {
  var nameInput = document.getElementById("pull-model-name");
  var name = nameInput ? nameInput.value.trim() : "";
  if (!name) {
    showToast("Enter a model name", "error");
    return;
  }

  var btn = document.getElementById("pull-btn");
  var progress = document.getElementById("pull-progress");
  var bar = document.getElementById("pull-progress-bar");
  var status = document.getElementById("pull-status");

  if (btn) btn.disabled = true;
  if (progress) progress.style.display = "";
  if (bar) bar.style.width = "0%";
  if (status) status.textContent = "Starting pull...";

  fetch("/api/ai/ollama/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name }),
  })
    .then(function (resp) {
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      function read() {
        return reader.read().then(function (result) {
          if (result.done) {
            if (btn) btn.disabled = false;
            if (bar) bar.style.width = "100%";
            if (status) status.textContent = "Pull complete!";
            showToast("Model " + name + " pulled", "success");
            setTimeout(function () { location.reload(); }, 1500);
            return;
          }

          buffer += decoder.decode(result.value, { stream: true });
          var lines = buffer.split("\n");
          buffer = lines.pop();

          lines.forEach(function (line) {
            if (line.startsWith("data: ")) {
              try {
                var data = JSON.parse(line.substring(6));
                if (data.error) {
                  if (status) status.textContent = "Error: " + data.error;
                  showToast("Pull error: " + data.error, "error");
                  if (btn) btn.disabled = false;
                  return;
                }
                if (data.total && data.completed) {
                  var pct = Math.round((data.completed / data.total) * 100);
                  if (bar) bar.style.width = pct + "%";
                }
                if (data.status) {
                  if (status) status.textContent = data.status;
                }
              } catch (e) {}
            }
          });

          return read();
        });
      }

      return read();
    })
    .catch(function (err) {
      if (btn) btn.disabled = false;
      if (status) status.textContent = "Network error: " + err.message;
      showToast("Pull failed: " + err.message, "error");
    });
}

function deleteModel(name) {
  if (!confirm('Delete model "' + name + '"?')) return;

  fetch("/api/ai/ollama/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast("Deleted " + name, "success");
        setTimeout(function () { location.reload(); }, 1000);
      } else {
        showToast(data.error || "Delete failed", "error");
      }
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}

function refreshGpu() {
  fetch("/api/ai/ollama/gpu")
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast("GPU info refreshed", "success");
      location.reload();
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}
