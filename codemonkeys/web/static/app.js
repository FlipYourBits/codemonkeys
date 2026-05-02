/* codemonkeys web UI */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const state = {
  mode: "run",
  cwd: null,
  agents: [],
  selectedAgent: null,
  savedOutputs: [],
  selectedOutputs: new Set(),
  session: null,
  ws: null,
  lastPrompt: null,
};

// ── Mode switching ──

function setMode(mode) {
  state.mode = mode;
  $("#btn-mode-run").classList.toggle("active", mode === "run");
  $("#btn-mode-chat").classList.toggle("active", mode === "chat");
  $("#panel-run").classList.toggle("hidden", mode !== "run");
  $("#panel-chat").classList.toggle("hidden", mode !== "chat");
  updateButtons();
}

// ── Working directory ──

async function loadCwd() {
  const res = await fetch("/cwd");
  const data = await res.json();
  state.cwd = data.path;
  renderCwd();
}

async function setCwd() {
  const input = $("#cwd-input");
  const path = input.value.trim();
  if (!path) return;

  const res = await fetch("/cwd", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

  if (!res.ok) {
    const err = await res.json();
    alert(err.detail || "Invalid directory");
    return;
  }

  const data = await res.json();
  state.cwd = data.path;
  input.value = "";
  renderCwd();
  updateButtons();
  loadSavedOutputs();
}

function renderCwd() {
  const display = $("#cwd-display");
  if (state.cwd) {
    display.textContent = state.cwd;
    $("#cwd-input").placeholder = state.cwd;
  } else {
    display.textContent = "";
    $("#cwd-input").placeholder = "/path/to/project";
  }
}

// ── Agents ──

async function loadAgents() {
  const res = await fetch("/agents");
  state.agents = await res.json();
  renderAgents();
}

function renderAgents() {
  const list = $("#agent-list");
  const sorted = [...state.agents].sort((a, b) => a.key.localeCompare(b.key));
  list.innerHTML = sorted.map((a) => `
    <div class="agent-item${state.selectedAgent === a.key ? " selected" : ""}" data-key="${a.key}">
      <div class="agent-info">
        <div class="agent-name">${esc(a.key)}</div>
        <div class="agent-desc">${esc(truncate(a.description, 60))}</div>
      </div>
      <div class="agent-actions">
        ${a.model ? `<span class="agent-model">${esc(a.model)}</span>` : ""}
        ${!a.needs_prompt ? `<button class="btn-run-agent" data-key="${a.key}" title="Run with default prompt">Run</button>` : ""}
      </div>
    </div>
  `).join("");

  for (const item of $$(".agent-item")) {
    item.addEventListener("click", (e) => {
      if (e.target.classList.contains("btn-run-agent")) return;
      state.selectedAgent = item.dataset.key;
      renderAgents();
      updatePromptArea();
      updateButtons();
    });
  }

  for (const btn of $$(".btn-run-agent")) {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      state.selectedAgent = btn.dataset.key;
      renderAgents();
      await startRun();
    });
  }
}

function updatePromptArea() {
  const agent = state.agents.find((a) => a.key === state.selectedAgent);
  const promptArea = $("#run-prompt");
  if (agent && agent.needs_prompt) {
    promptArea.classList.remove("hidden");
    promptArea.placeholder = "Describe what to fix/implement/test...";
    promptArea.required = true;
  } else {
    promptArea.classList.add("hidden");
    promptArea.value = "";
    promptArea.required = false;
  }
}

// ── Saved outputs ──

async function loadSavedOutputs() {
  const res = await fetch("/saved-outputs");
  state.savedOutputs = await res.json();
  renderSavedOutputs();
}

function renderSavedOutputs() {
  const list = $("#output-list");
  if (state.savedOutputs.length === 0) {
    list.innerHTML = `<div class="empty">No saved outputs yet.</div>`;
    return;
  }
  list.innerHTML = state.savedOutputs.map((o) => `
    <div class="output-item">
      <label class="output-check">
        <input type="checkbox" data-file="${esc(o.filename)}"
          ${state.selectedOutputs.has(o.filename) ? "checked" : ""}>
        <span class="output-name" title="${esc(o.filename)}">${esc(o.agent_key)}</span>
      </label>
      <span class="output-date">${fmtDate(o.created_at)}</span>
      <button class="btn-icon-sm btn-view" data-file="${esc(o.filename)}" title="View">v</button>
    </div>
  `).join("");

  for (const cb of $$(".output-check input")) {
    cb.addEventListener("change", () => {
      if (cb.checked) state.selectedOutputs.add(cb.dataset.file);
      else state.selectedOutputs.delete(cb.dataset.file);
    });
  }

  for (const btn of $$(".btn-view")) {
    btn.addEventListener("click", async () => {
      const res = await fetch(`/saved-outputs/${encodeURIComponent(btn.dataset.file)}`);
      if (!res.ok) return;
      const text = await res.text();
      showOutputModal(btn.dataset.file, text);
    });
  }
}

function fmtObject(obj, indent) {
  indent = indent || 0;
  const pad = "  ".repeat(indent);
  if (obj === null || obj === undefined) return `${pad}null`;
  if (typeof obj === "boolean" || typeof obj === "number") return `${pad}${obj}`;
  if (typeof obj === "string") {
    const trimmed = obj.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try { return fmtObject(JSON.parse(trimmed), indent); } catch { /* not JSON */ }
    }
    if (obj.includes("\n")) {
      return obj.split("\n").map((line) => `${pad}${line}`).join("\n");
    }
    return `${pad}${obj}`;
  }
  if (Array.isArray(obj)) {
    return obj.map((item, i) => `${pad}[${i}]:\n${fmtObject(item, indent + 1)}`).join("\n");
  }
  const lines = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === "object") {
      lines.push(`${pad}${k}:`);
      lines.push(fmtObject(v, indent + 1));
    } else if (typeof v === "string" && v.includes("\n")) {
      lines.push(`${pad}${k}:`);
      lines.push(fmtObject(v, indent + 1));
    } else {
      lines.push(`${pad}${k}: ${v === null ? "null" : v === undefined ? "" : v}`);
    }
  }
  return lines.join("\n");
}

function showOutputModal(title, content) {
  let modal = $("#output-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "output-modal";
    modal.className = "modal-overlay";
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <span class="modal-title"></span>
          <div class="modal-header-actions">
            <button class="btn btn-sm modal-copy">Copy</button>
            <button class="btn-icon-sm modal-close">&times;</button>
          </div>
        </div>
        <pre class="modal-body"></pre>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector(".modal-close").addEventListener("click", () => {
      modal.classList.add("hidden");
    });
    modal.querySelector(".modal-copy").addEventListener("click", async () => {
      const text = modal.querySelector(".modal-body").textContent;
      await navigator.clipboard.writeText(text);
      const btn = modal.querySelector(".modal-copy");
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
    });
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  }
  modal.querySelector(".modal-title").textContent = title;

  let display = content;
  try {
    const parsed = JSON.parse(content);
    display = fmtObject(parsed);
  } catch { /* plain text, use as-is */ }
  modal.querySelector(".modal-body").textContent = display;
  modal.classList.remove("hidden");
}

// ── Confirm modal ──

function showConfirmModal(title, message) {
  return new Promise((resolve) => {
    let modal = $("#confirm-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "confirm-modal";
      modal.className = "modal-overlay";
      modal.innerHTML = `
        <div class="modal modal-confirm">
          <div class="modal-header">
            <span class="modal-title confirm-title"></span>
          </div>
          <div class="modal-body confirm-message"></div>
          <div class="modal-footer">
            <button class="btn confirm-cancel">Cancel</button>
            <button class="btn btn-danger confirm-ok">Continue</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }

    modal.querySelector(".confirm-title").textContent = title;
    modal.querySelector(".confirm-message").textContent = message;
    modal.classList.remove("hidden");

    function cleanup(result) {
      modal.classList.add("hidden");
      modal.querySelector(".confirm-cancel").removeEventListener("click", onCancel);
      modal.querySelector(".confirm-ok").removeEventListener("click", onOk);
      modal.removeEventListener("click", onBackdrop);
      resolve(result);
    }

    function onCancel() { cleanup(false); }
    function onOk() { cleanup(true); }
    function onBackdrop(e) { if (e.target === modal) cleanup(false); }

    modal.querySelector(".confirm-cancel").addEventListener("click", onCancel);
    modal.querySelector(".confirm-ok").addEventListener("click", onOk);
    modal.addEventListener("click", onBackdrop);
  });
}

// ── Button state ──

function updateButtons() {
  const hasCwd = !!state.cwd;
  const hasAgent = !!state.selectedAgent;
  const isRunning = state.session && (state.session.status === "running" || state.session.status === "idle");

  if (state.mode === "run") {
    const agent = state.agents.find((a) => a.key === state.selectedAgent);
    const needsPrompt = agent?.needs_prompt;
    const hasPrompt = !!$("#run-prompt").value.trim();
    $("#btn-run").disabled = !hasCwd || !hasAgent || (needsPrompt && !hasPrompt);
    $("#btn-cancel-run").classList.toggle("hidden", !isRunning);
  } else {
    const isChatActive = isRunning && state.session?.mode === "chat";
    const isChatIdle = state.session?.status === "idle" && state.session?.mode === "chat";
    $("#btn-send").disabled = !hasCwd || (!hasAgent && !isChatActive);
    if (isChatIdle) $("#btn-send").disabled = false;
    $("#btn-cancel-chat").classList.toggle("hidden", !isChatActive && !isChatIdle);
    $("#btn-end-chat").classList.toggle("hidden", !isChatIdle);
  }

  // Disable inline Run buttons if no cwd
  for (const btn of $$(".btn-run-agent")) {
    btn.disabled = !hasCwd;
  }
}

// ── Run mode ──

async function startRun() {
  if (!state.selectedAgent) return;
  const agent = state.agents.find((a) => a.key === state.selectedAgent);
  const prompt = $("#run-prompt").value.trim();

  if (agent?.needs_prompt && !prompt) {
    $("#run-prompt").focus();
    return;
  }

  const isRunning = state.session && (state.session.status === "running" || state.session.status === "idle");
  if (isRunning) {
    const confirmed = await showConfirmModal(
      "Cancel current run?",
      "A job is currently running. Starting a new run will cancel it.",
    );
    if (!confirmed) return;
    await cancelSession();
  }

  const body = {
    agent_key: state.selectedAgent,
    prompt: prompt || "",
    context_files: [...state.selectedOutputs],
  };

  $("#btn-run").disabled = true;
  clearLog("run-log");

  const res = await fetch("/sessions/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json();
    appendLog("run-log", "error", err.detail || "Failed to start");
    updateButtons();
    return;
  }

  const session = await res.json();
  state.session = session;
  updateButtons();
  updateStatusBar();
  connectWS(session.session_id);
  appendLog("run-log", "system", `Running ${session.agent_key}...`);
}

// ── Chat mode ──

async function startOrSendChat() {
  const input = $("#chat-input");
  const message = input.value.trim();
  if (!message) return;

  if (state.session?.mode === "chat" && state.session?.status === "idle") {
    input.value = "";
    appendLog("chat-log", "user", message);
    const res = await fetch(`/sessions/${state.session.session_id}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      const err = await res.json();
      appendLog("chat-log", "error", err.detail || "Failed to send");
    }
    state.session.status = "running";
    updateButtons();
    return;
  }

  if (!state.selectedAgent) return;

  const body = {
    agent_key: state.selectedAgent,
    message,
    context_files: [...state.selectedOutputs],
  };

  input.value = "";
  clearLog("chat-log");
  appendLog("chat-log", "user", message);

  const res = await fetch("/sessions/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json();
    appendLog("chat-log", "error", err.detail || "Failed to start chat");
    return;
  }

  const session = await res.json();
  state.session = session;
  updateButtons();
  updateStatusBar();
  connectWS(session.session_id);
}

async function endChat() {
  if (!state.session) return;
  const res = await fetch(`/sessions/${state.session.session_id}/end`, {
    method: "POST",
  });
  if (res.ok) {
    const data = await res.json();
    appendLog("chat-log", "system", `Chat saved to ${data.output_file}`);
    state.session.status = "completed";
    updateButtons();
    loadSavedOutputs();
  }
}

// ── Cancel ──

async function cancelSession() {
  if (!state.session) return;
  await fetch(`/sessions/${state.session.session_id}/cancel`, {
    method: "POST",
  });
  appendLog(
    state.mode === "run" ? "run-log" : "chat-log",
    "system", "Session cancelled",
  );
  state.session.status = "cancelled";
  updateButtons();
  updateStatusBar();
}

// ── WebSocket ──

function connectWS(sessionId) {
  if (state.ws) { state.ws.close(); state.ws = null; }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/sessions/${sessionId}/ws`);
  state.ws = ws;

  ws.addEventListener("message", (evt) => {
    const event = JSON.parse(evt.data);
    handleWSEvent(event);
  });

  ws.addEventListener("close", () => {
    if (state.ws === ws) state.ws = null;
  });
}

function handleWSEvent(event) {
  const logId = state.mode === "run" ? "run-log" : "chat-log";

  switch (event.type) {
    case "session_started": {
      appendLog(logId, "system", `Session started: ${event.data.agent_key} [${event.data.mode}]`);
      const ctx = event.data.context_files || [];
      if (ctx.length > 0) {
        appendLog(logId, "system", `Context: ${ctx.join(", ")}`);
      }
      if (event.data.prompt) {
        state.lastPrompt = event.data.prompt;
        appendLogLink(logId, "system", "View full prompt", () => {
          showOutputModal("Prompt sent to agent", state.lastPrompt);
        });
      }
      break;
    }

    case "text":
      appendLog(logId, "text", event.data.text);
      break;

    case "thinking":
      appendLog(logId, "thinking", event.data.thinking);
      break;

    case "tool_use": {
      const inp = fmtToolInput(event.data.name, event.data.input);
      appendLog(logId, "tool", `${event.data.name} ${inp}`);
      break;
    }

    case "tool_result": {
      const content = event.data.content || "";
      const label = event.data.is_error ? "error" : "result";
      if (content.length > 300) {
        appendLog(logId, "tool-result", `[${label}] ${content.slice(0, 200)}...`);
        appendLogLink(logId, "tool-result", "View full output", () => {
          showOutputModal("Tool Result", content);
        });
      } else {
        appendLog(logId, "tool-result", `[${label}] ${content}`);
      }
      break;
    }

    case "server_tool_use": {
      const inp = fmtToolInput(event.data.name, event.data.input);
      appendLog(logId, "tool", `${event.data.name} ${inp}`);
      break;
    }

    case "server_tool_result": {
      const content = JSON.stringify(event.data.content);
      if (content.length > 300) {
        appendLog(logId, "tool-result", `[result] ${content.slice(0, 200)}...`);
        appendLogLink(logId, "tool-result", "View full output", () => {
          showOutputModal("Server Tool Result", JSON.stringify(event.data.content, null, 2));
        });
      } else {
        appendLog(logId, "tool-result", `[result] ${content}`);
      }
      break;
    }

    case "token_update":
      if (state.session) state.session.total_tokens = event.data.tokens;
      updateStatusBar();
      break;

    case "result":
      if (state.session) {
        state.session.total_tokens = event.data.total_tokens || state.session.total_tokens;
        state.session.cost_usd = event.data.cost_usd;
      }
      appendLog(logId, "system", `Result: ${fmtTokens(event.data.total_tokens)} tokens, $${(event.data.cost_usd || 0).toFixed(4)}, ${((event.data.duration_ms || 0) / 1000).toFixed(1)}s (${event.data.num_turns} turns)${event.data.is_error ? " [ERROR]" : ""}`);
      updateStatusBar();
      break;

    case "task_started":
      appendLog(logId, "system", `[task_started] ${event.data.description} (${event.data.task_id})`);
      break;

    case "task_progress": {
      const parts = [`[task_progress] ${event.data.description}`];
      if (event.data.tokens) parts.push(`${fmtTokens(event.data.tokens)} tokens`);
      if (event.data.tool_uses) parts.push(`${event.data.tool_uses} tool uses`);
      if (event.data.last_tool_name) parts.push(`last: ${event.data.last_tool_name}`);
      appendLog(logId, "system", parts.join(" | "));
      break;
    }

    case "task_notification":
      appendLog(logId, "system", `[task_${event.data.status}] ${event.data.task_id}: ${event.data.summary}`);
      break;

    case "rate_limit": {
      const rl = event.data;
      const pct = rl.utilization != null ? ` (${(rl.utilization * 100).toFixed(0)}%)` : "";
      appendLog(logId, rl.status === "rejected" ? "error" : "system", `[rate_limit] ${rl.status}${pct} ${rl.rate_limit_type || ""}`);
      break;
    }

    case "user_message":
      appendLog(logId, "user", event.data.content);
      break;

    case "mirror_error":
      appendLog(logId, "error", `[mirror_error] ${event.data.error}`);
      break;

    case "stream_event":
      appendLog(logId, "system", `[stream] ${JSON.stringify(event.data.event)}`);
      break;

    case "system_message": {
      const summary = fmtSystemData(event.data.data);
      appendLog(logId, "system", `[${event.data.subtype}] ${summary}`);
      if (summary.includes("...")) {
        const raw = JSON.stringify(event.data.data, null, 2);
        appendLogLink(logId, "system", "View full event", () => {
          showOutputModal(`[${event.data.subtype}]`, raw);
        });
      }
      break;
    }

    case "chat_turn_done":
      if (state.session) {
        state.session.status = "idle";
        state.session.total_tokens = event.data.total_tokens || state.session.total_tokens;
      }
      appendLog(logId, "system", "--- ready for input ---");
      updateButtons();
      updateStatusBar();
      break;

    case "session_completed":
      if (state.session) {
        state.session.status = "completed";
        state.session.total_tokens = event.data.total_tokens || state.session.total_tokens;
        state.session.cost_usd = event.data.cost_usd;
      }
      appendLog(logId, "system", `Completed. ${fmtTokens(event.data.total_tokens)} tokens, $${(event.data.cost_usd || 0).toFixed(4)}. Output: ${event.data.output_file || "n/a"}`);
      updateButtons();
      updateStatusBar();
      loadSavedOutputs();
      if (state.ws) { state.ws.close(); state.ws = null; }
      break;

    case "session_cancelled":
      if (state.session) state.session.status = "cancelled";
      appendLog(logId, "system", "Cancelled");
      updateButtons();
      updateStatusBar();
      if (state.ws) { state.ws.close(); state.ws = null; }
      break;

    case "error":
      appendLog(logId, "error", event.data.message);
      break;

    default:
      appendLog(logId, "system", `[${event.type}] ${JSON.stringify(event.data)}`);
      break;
  }
}

// ── Status bar ──

function updateStatusBar() {
  const s = state.session;
  if (!s) {
    $("#status-tokens").textContent = "";
    $("#status-cost").textContent = "";
    $("#status-state").textContent = "";
    return;
  }
  $("#status-tokens").textContent = s.total_tokens ? `${fmtTokens(s.total_tokens)} tokens` : "";
  $("#status-cost").textContent = s.cost_usd ? `$${s.cost_usd.toFixed(3)}` : "";
  $("#status-state").textContent = s.status;
}

// ── Log rendering ──

function clearLog(logId) {
  $(`#${logId}`).innerHTML = "";
}

function isNearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}

function renderMarkdown(text) {
  let html = esc(text);
  // code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="log-code-block">$2</pre>');
  // inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // headers
  html = html.replace(/^#### (.+)$/gm, '<strong class="log-h4">$1</strong>');
  html = html.replace(/^### (.+)$/gm, '<strong class="log-h3">$1</strong>');
  html = html.replace(/^## (.+)$/gm, '<strong class="log-h2">$1</strong>');
  html = html.replace(/^# (.+)$/gm, '<strong class="log-h1">$1</strong>');
  // bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // list items
  html = html.replace(/^(\s*)[-*] (.+)$/gm, '$1<span class="log-list-item">$2</span>');
  // line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

function appendLog(logId, type, text) {
  const area = $(`#${logId}`);
  const shouldScroll = isNearBottom(area);
  const entry = document.createElement("div");
  entry.className = `log-entry log-${type}`;

  if (type === "tool-detail") {
    const pre = document.createElement("pre");
    pre.className = "log-tool-json";
    pre.textContent = text;
    entry.appendChild(pre);
  } else if (type === "text") {
    entry.innerHTML = renderMarkdown(text);
  } else {
    entry.textContent = text;
  }

  area.appendChild(entry);
  if (shouldScroll) area.scrollTop = area.scrollHeight;
}

function appendLogLink(logId, type, label, onClick) {
  const area = $(`#${logId}`);
  const shouldScroll = isNearBottom(area);
  const entry = document.createElement("div");
  entry.className = `log-entry log-${type}`;
  const link = document.createElement("a");
  link.textContent = label;
  link.href = "#";
  link.className = "log-link";
  link.addEventListener("click", (e) => { e.preventDefault(); onClick(); });
  entry.appendChild(link);
  area.appendChild(entry);
  if (shouldScroll) area.scrollTop = area.scrollHeight;
}

// ── Helpers ──

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 3) + "..." : s;
}

function fmtSystemData(d) {
  if (!d || typeof d !== "object") return String(d || "");
  const skip = new Set(["type", "subtype", "uuid", "session_id", "hook_id"]);
  const parts = [];
  for (const [k, v] of Object.entries(d)) {
    if (skip.has(k)) continue;
    let s = typeof v === "string" ? v : JSON.stringify(v);
    if (s.length > 120) s = s.slice(0, 117) + "...";
    parts.push(`${k}=${s}`);
  }
  return parts.join(", ") || JSON.stringify(d);
}

function fmtToolInput(name, input) {
  if (!input) return "";
  if (name === "Read") return input.file_path || "";
  if (name === "Write") return input.file_path || "";
  if (name === "Edit") return input.file_path || "";
  if (name === "Bash") return input.command ? `$ ${truncate(input.command, 80)}` : "";
  if (name === "Glob") return input.pattern || "";
  if (name === "Grep") return `${input.pattern || ""} ${input.path || ""}`.trim();
  if (name === "Agent") return truncate(input.prompt || input.description || "", 80);
  const s = JSON.stringify(input);
  return s.length > 100 ? s.slice(0, 97) + "..." : s;
}

function fmtTokens(n) {
  if (!n) return "0";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return Math.round(n / 1000) + "k";
  return String(n);
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return Math.floor(diff / 60000) + "m ago";
  if (diff < 86400000) return Math.floor(diff / 3600000) + "h ago";
  return d.toLocaleDateString();
}

// ── Init ──

document.addEventListener("DOMContentLoaded", () => {
  // Mode buttons
  $("#btn-mode-run").addEventListener("click", () => setMode("run"));
  $("#btn-mode-chat").addEventListener("click", () => setMode("chat"));

  // Run mode
  $("#btn-run").addEventListener("click", startRun);
  $("#btn-cancel-run").addEventListener("click", cancelSession);
  $("#run-prompt").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); startRun(); }
  });
  $("#run-prompt").addEventListener("input", updateButtons);

  // Chat mode
  $("#btn-send").addEventListener("click", startOrSendChat);
  $("#btn-end-chat").addEventListener("click", endChat);
  $("#btn-cancel-chat").addEventListener("click", cancelSession);
  $("#chat-input").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); startOrSendChat(); }
  });

  // Sidebar
  $("#btn-set-cwd").addEventListener("click", setCwd);
  $("#cwd-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); setCwd(); }
  });
  $("#btn-refresh-outputs").addEventListener("click", loadSavedOutputs);

  // Header click to reset
  $("#header-title").addEventListener("click", () => {
    state.session = null;
    updateButtons();
    updateStatusBar();
  });

  loadCwd();
  loadAgents();
  loadSavedOutputs();
  updatePromptArea();
  setMode("run");
});
