/* Tech Pulse - Generate, chat, queue actions */
"use strict";

function generatePulse() {
  var btn = document.getElementById("generate-btn");
  var loading = document.getElementById("pulse-loading");

  if (btn) btn.disabled = true;
  if (loading) loading.style.display = "";

  fetch("/api/intel/pulse/generate", { method: "POST" })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.success) {
        showToast("Digest generated with " + (data.total_items || 0) + " items", "success");
        setTimeout(function () { location.reload(); }, 1000);
      } else {
        showToast(data.error || "Generation failed", "error");
        if (btn) btn.disabled = false;
        if (loading) loading.style.display = "none";
      }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
      if (btn) btn.disabled = false;
      if (loading) loading.style.display = "none";
    });
}

function sendPulseChat() {
  var input = document.getElementById("pulse-chat-input");
  var messages = document.getElementById("pulse-chat-messages");
  if (!input || !messages) return;

  var question = input.value.trim();
  if (!question) return;
  input.value = "";

  // Add user message
  var userDiv = document.createElement("div");
  userDiv.style.cssText = "color:var(--cyan);margin-bottom:4px";
  userDiv.textContent = "> " + question;
  messages.appendChild(userDiv);

  // Add placeholder
  var assistDiv = document.createElement("div");
  assistDiv.style.cssText = "color:var(--green);margin-bottom:8px";
  assistDiv.textContent = "Thinking...";
  messages.appendChild(assistDiv);
  messages.scrollTop = messages.scrollHeight;

  fetch("/api/intel/pulse/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      assistDiv.textContent = data.answer || "No response";
      messages.scrollTop = messages.scrollHeight;
    })
    .catch(function (err) {
      assistDiv.textContent = "Error: " + err.message;
      assistDiv.style.color = "var(--red)";
    });
}

function flagItem(index, section) {
  fetch("/api/intel/pulse/flag", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index: index, section: section }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast(data.message || "Flagged for Linear queue", "success");
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}

function saveNd(index, section) {
  fetch("/api/intel/pulse/save-nd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index: index, section: section }),
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      showToast(data.message || "Saved to ND queue", "success");
    })
    .catch(function (err) { showToast("Error: " + err.message, "error"); });
}

// Enter to send chat
document.addEventListener("DOMContentLoaded", function () {
  var chatInput = document.getElementById("pulse-chat-input");
  if (chatInput) {
    chatInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        sendPulseChat();
      }
    });
  }
});
