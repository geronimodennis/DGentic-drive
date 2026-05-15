const TOKEN_KEY = "dgentic.ui.token";
const TASK_CHAT_HISTORY_KEY = "dgentic.ui.taskChatMessages";
const TASK_CHAT_HISTORY_MAX_MESSAGES = 40;
const TASK_CHAT_HISTORY_MAX_BYTES = 120000;

const approvalSources = [
  { key: "cli", label: "CLI", base: "/cli/approvals" },
  { key: "filesystem", label: "Filesystem", base: "/filesystem/approvals" },
  { key: "network", label: "Network", base: "/network/approvals" },
  { key: "provider", label: "Provider", base: "/providers/approvals" },
  { key: "tool", label: "Tool", base: "/tools/approvals" },
];

const recoverableTaskBlockerSeverities = new Set(["role_boundary", "retry_exhausted"]);
const resolvableTaskBlockerSeverities = new Set(["blocked", "security"]);

let approvalStatus = "pending";
let approvalSource = "";
let selectedApproval = null;
let workspacePath = ".";
let openFilePath = "";
let toastTimer = null;
let activeRootDir = "";
let activeRootSource = "";
let activeProjectId = "";
let selectedOrchestrationId = "";
let taskGraphBuilderTasks = [];
let latestSettingsView = null;
let latestPolicyReviewResults = null;
let latestNetworkPolicyPreflight = null;
let latestFilesystemPolicyPreflight = null;
let latestGitCheckpoint = null;
let latestGitCheckpointRequest = null;
let latestGitDiffReview = null;
let latestGitChangeReviewArtifacts = [];
let editingCliPolicyRuleId = "";
let editingCommandRecipeId = "";
let editingHookPolicyRuleId = "";
let taskChatMessages = [];
let latestTaskChatContext = {
  plans: [],
  runs: [],
  approvals: [],
  logs: [],
  active: null,
  errors: [],
};
let gitDiffReviewDecisions = {};

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function clear(node) {
  node.replaceChildren();
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function requestHeaders(hasBody) {
  const headers = {
    Accept: "application/json",
  };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (hasBody) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

async function api(path, options = {}) {
  const hasBody = Object.prototype.hasOwnProperty.call(options, "body");
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: requestHeaders(hasBody),
    body: hasBody ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (_error) {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    let message = detail || `Request failed with ${response.status}`;
    if (Array.isArray(detail)) {
      message = detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    } else if (detail && typeof detail === "object") {
      message = detail.detail || `Request failed with ${response.status}`;
    }
    const error = new Error(message);
    error.detail = detail;
    throw error;
  }
  return payload;
}

async function safeLoad(label, loader) {
  try {
    return { ok: true, data: await loader() };
  } catch (error) {
    return { ok: false, label, error: error.message };
  }
}

function splitLines(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function jsonBlock(value) {
  const pre = make("pre");
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function statusChip(value, extraClass = "") {
  const normalized = String(value || "unknown").toLowerCase();
  return make("span", `status-chip ${normalized} ${extraClass}`.trim(), normalized);
}

function showToast(message) {
  const toast = qs("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}

function statusBox(title, detail, state = "") {
  const box = make("div", "status-box");
  const heading = make("div", "item-title", title);
  const body = make("div", "item-meta", detail);
  box.append(heading, body);
  if (state) {
    box.append(statusChip(state));
  }
  return box;
}

function setMetric(selector, value) {
  qs(selector).textContent = value;
}

function compactPath(value) {
  const text = String(value || "-");
  if (text.length <= 76) {
    return text;
  }
  return `${text.slice(0, 34)}...${text.slice(-34)}`;
}

function settingByName(view, name) {
  return (view?.settings || []).find((setting) => setting.name === name) || null;
}

function settingText(setting, fallback = "-") {
  if (!setting) {
    return fallback;
  }
  if (setting.value && typeof setting.value === "object") {
    return JSON.stringify(setting.value);
  }
  return String(setting.value ?? fallback);
}

function settingValueText(value, fallback = "-") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function reviewValue(value, fallback = "-") {
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => reviewValue(item)).join(", ") : fallback;
  }
  return settingValueText(value, fallback);
}

function parseSettingList(setting) {
  if (!setting) {
    return [];
  }
  const value = setting.value;
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value !== "string") {
    return [];
  }
  const text = value.trim();
  if (!text) {
    return [];
  }
  if (text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item).trim()).filter(Boolean);
      }
    } catch (_error) {
      return [text];
    }
  }
  return text
    .split(/[,\n;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceCounts(settings) {
  const counts = {};
  for (const setting of settings || []) {
    const source = setting.source || "unknown";
    counts[source] = (counts[source] || 0) + 1;
  }
  return counts;
}

function compactCounts(counts) {
  const entries = Object.entries(counts || {});
  return entries.length ? entries.map(([key, value]) => `${key}: ${value}`).join(" | ") : "-";
}

function appendKeyValue(target, label, value, chipValue = "") {
  const item = make("div", "info-pair");
  item.append(make("span", "", label));
  item.append(make("strong", "", value));
  if (chipValue) {
    item.append(statusChip(chipValue));
  }
  target.append(item);
}

function formatTimestamp(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function countsText(counts) {
  const parts = Object.entries(counts || {}).map(([key, value]) => `${key}: ${value}`);
  return parts.length ? parts.join(" | ") : "No status counts";
}

function taskStatusCounts(tasks) {
  const counts = {};
  for (const task of tasks || []) {
    const status = task.status || "unknown";
    counts[status] = (counts[status] || 0) + 1;
  }
  return counts;
}

function activeExecution(executions) {
  return (executions || []).find((execution) =>
    ["starting", "running", "cancelling"].includes(execution.status),
  );
}

function approvalStatusLabel() {
  return approvalStatus ? approvalStatus : "all";
}

function approvalSourceLabel() {
  const source = approvalSources.find((candidate) => candidate.key === approvalSource);
  return source ? source.label : "All sources";
}

function setApprovalFilterState(sourceKey, statusKey) {
  approvalSource = sourceKey;
  approvalStatus = statusKey;
  qs("#approvalSourceInput").value = sourceKey;
  for (const button of qsa(".segmented-control button")) {
    button.classList.toggle("active", button.dataset.status === statusKey);
  }
  selectedApproval = null;
  clear(qs("#approvalReview"));
}

async function refreshDashboard() {
  await Promise.all([
    loadHealth(),
    loadTasks(),
    loadWorkspace(),
    loadApprovals(),
    loadProviders(),
    loadReliability(),
    loadCliRuns(),
    loadProjects(),
    loadPolicySurfaces(),
    loadSettings(),
    loadTaskChatContext(),
    loadLogs(),
  ]);
}

function parentPath(path) {
  const parts = String(path || ".")
    .replaceAll("\\", "/")
    .split("/")
    .filter((part) => part && part !== ".");
  parts.pop();
  return parts.join("/") || ".";
}

function entryPath(entry) {
  return String(entry.path || entry.name || ".");
}

function fileMeta(entry) {
  const size = entry.size_bytes === null || entry.size_bytes === undefined ? "-" : entry.size_bytes;
  const modified = entry.modified_at ? new Date(entry.modified_at).toLocaleString() : "-";
  return `${entry.type} - ${size} bytes - ${modified}`;
}

async function loadWorkspace(path = workspacePath) {
  workspacePath = path || ".";
  qs("#workspacePathInput").value = workspacePath;
  const target = qs("#workspaceList");
  clear(target);
  target.append(statusBox("Loading workspace", workspacePath, "running"));
  const result = await safeLoad("workspace", () =>
    api("/filesystem/list", { method: "POST", body: { path: workspacePath } }),
  );
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Workspace unavailable", result.error, "blocked"));
    return;
  }
  const entries = [...(result.data.entries || [])].sort((left, right) => {
    if (left.type !== right.type) {
      return left.type === "directory" ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });
  if (!entries.length) {
    target.append(statusBox("Empty folder", result.data.path || workspacePath, "pending"));
    return;
  }
  for (const entry of entries) {
    const row = make("button", "file-row");
    row.type = "button";
    const copy = make("div");
    copy.append(make("strong", "", entry.name));
    copy.append(make("div", "item-meta", fileMeta(entry)));
    row.append(copy, statusChip(entry.type));
    if (entry.type === "directory") {
      row.addEventListener("click", () => loadWorkspace(entryPath(entry)));
    } else if (entry.type === "file") {
      row.addEventListener("click", () => openWorkspaceFile(entryPath(entry)));
    } else {
      row.disabled = true;
    }
    target.append(row);
  }
}

async function openWorkspaceFile(path) {
  const target = qs("#workspaceStatus");
  clear(target);
  target.append(statusBox("Opening file", path, "running"));
  try {
    const response = await api("/filesystem/read", { method: "POST", body: { path } });
    openFilePath = String(response.path || path);
    qs("#workspaceEditorTitle").textContent = openFilePath;
    qs("#workspaceEditor").value = response.content || "";
    clear(target);
    target.append(statusBox("File loaded", `${response.bytes_read} bytes`, "ok"));
  } catch (error) {
    clear(target);
    target.append(statusBox("Open failed", error.message, "failed"));
  }
}

async function saveWorkspaceFile() {
  const target = qs("#workspaceStatus");
  clear(target);
  if (!openFilePath) {
    target.append(statusBox("No file open", "Open a file before saving.", "blocked"));
    return;
  }
  target.append(statusBox("Saving file", openFilePath, "running"));
  try {
    const response = await api("/filesystem/write", {
      method: "POST",
      body: { path: openFilePath, content: qs("#workspaceEditor").value },
    });
    clear(target);
    target.append(statusBox("File saved", `${response.bytes_written} bytes`, "ok"));
    await loadWorkspace(workspacePath);
  } catch (error) {
    clear(target);
    target.append(statusBox("Save failed", error.message, "failed"));
  }
}

async function loadHealth() {
  const result = await safeLoad("health", () => api("/health"));
  if (!result.ok) {
    setMetric("#serviceMetric", "-");
    setMetric("#healthMetric", result.error);
    return;
  }
  setMetric("#serviceMetric", result.data.service || "DGentic");
  setMetric("#healthMetric", result.data.status || "ok");
  qs("#environmentLabel").textContent = result.data.environment || "Control";
}

async function loadTasks() {
  const [plans, runs, summary, orchestrations, agents] = await Promise.all([
    safeLoad("plans", () => api("/tasks/plans")),
    safeLoad("runs", () => api("/tasks/runs")),
    safeLoad("orchestration summary", () => api("/tasks/orchestrations/operations/summary")),
    safeLoad("orchestrations", () => api("/tasks/orchestrations")),
    safeLoad("agents", () => api("/agents")),
  ]);

  const planCount = plans.ok ? plans.data.length : "-";
  const runCount = runs.ok ? runs.data.length : "-";
  setMetric("#plansMetric", String(planCount));
  setMetric("#runsMetric", `Runs: ${runCount}`);

  renderTaskOutput(plans, runs);
  renderOrchestrationSummary(summary, orchestrations, agents);
}

function renderTaskOutput(plans, runs) {
  const target = qs("#taskOutput");
  clear(target);
  if (!plans.ok && !runs.ok) {
    target.append(statusBox("Tasks unavailable", `${plans.error}; ${runs.error}`, "blocked"));
    return;
  }

  const latestPlans = plans.ok ? plans.data.slice(-4).reverse() : [];
  if (!latestPlans.length) {
    target.append(statusBox("No task plans", "Create a plan to start the queue.", "pending"));
  }
  if (!runs.ok) {
    target.append(statusBox("Task runs unavailable", runs.error, "blocked"));
  }
  for (const plan of latestPlans) {
    renderTaskPlanCard(target, plan, runsForPlan(plan, runs.ok ? runs.data : []));
  }
}

function taskChatPayload() {
  return {
    objective: qs("#taskChatInput").value.trim(),
    constraints: splitLines(qs("#taskChatContextInput").value),
    acceptance_criteria: splitLines(qs("#taskChatAcceptanceInput").value),
    priority: qs("#taskChatPriorityInput").value,
  };
}

function isAuthorizationError(result) {
  return /^(401|403)\b/.test(String(result?.error || ""));
}

async function loadTaskChatContext() {
  const approvalLoads = approvalSources.map(async (source) => {
    const result = await safeLoad(`${source.label} pending approvals`, () => api(`${source.base}?status=pending`));
    return { source, ...result };
  });
  const [plans, runs, active, logs, ...approvalResults] = await Promise.all([
    safeLoad("task chat plans", () => api("/tasks/plans")),
    safeLoad("task chat runs", () => api("/tasks/runs")),
    safeLoad("task chat active project", () => api("/projects/active")),
    safeLoad("task chat logs", () => api("/logs")),
    ...approvalLoads,
  ]);
  const approvals = [];
  for (const result of approvalResults) {
    if (result.ok) {
      for (const approval of result.data || []) {
        approvals.push({ source: result.source, approval });
      }
    }
  }
  const loadResults = [plans, runs, active, logs, ...approvalResults];
  latestTaskChatContext = {
    plans: plans.ok ? plans.data || [] : [],
    runs: runs.ok ? runs.data || [] : [],
    approvals,
    logs: logs.ok ? (logs.data || []).slice(-8).reverse() : [],
    active: active.ok ? active.data : null,
    errors: loadResults.filter((result) => !result.ok && !isAuthorizationError(result)),
    unavailable_count: loadResults.filter((result) => !result.ok && isAuthorizationError(result)).length,
  };
  renderTaskChatContextStream();
}

function taskChatLatestActivity(context) {
  const timestamps = [
    ...context.logs.map((event) => event.created_at),
    ...context.runs.map((run) => run.completed_at || run.started_at),
    ...context.plans.map((plan) => plan.created_at),
    ...context.approvals.map((item) => item.approval.created_at),
  ]
    .filter(Boolean)
    .map((value) => new Date(value).getTime())
    .filter((value) => Number.isFinite(value));
  if (!timestamps.length) {
    return "-";
  }
  return formatTimestamp(new Date(Math.max(...timestamps)).toISOString());
}

function taskChatContextLines(title, lines) {
  return [title, ...lines].filter(Boolean).map((line) => boundedString(String(line), 280));
}

function taskPlanContextLines(plan) {
  return [
    `Plan ID: ${plan.id}`,
    `Objective: ${plan.objective || "-"}`,
    `Steps: ${(plan.steps || []).map((step) => step.title || step.id).slice(0, 6).join("; ") || "-"}`,
  ];
}

function taskRunContextLines(run) {
  const results = (run.results || [])
    .map((result) => `${result.step_id}:${result.status}`)
    .slice(0, 8)
    .join("; ");
  return [
    `Run ID: ${run.id}`,
    `Plan ID: ${run.plan_id || "-"}`,
    `Status: ${run.status || "-"}`,
    `Results: ${results || "-"}`,
  ];
}

function insertTaskChatContext(title, lines) {
  const input = qs("#taskChatContextInput");
  const block = taskChatContextLines(title, lines).join("\n");
  input.value = input.value.trim() ? `${input.value.trim()}\n\n${block}` : block;
  input.focus();
  showToast("Context added to task chat.");
}

function openTaskChatContextSection(sectionId) {
  const target = document.getElementById(sectionId);
  if (!target) {
    return;
  }
  window.location.hash = sectionId;
  target.scrollIntoView({ block: "start" });
}

function renderTaskChatContextCard(target, card) {
  const item = make("div", "task-chat-context-card");
  const copy = make("div");
  copy.append(make("div", "item-title", card.title));
  copy.append(make("div", "item-meta", card.meta));
  if (card.state) {
    copy.append(statusChip(card.state));
  }
  const actions = make("div", "task-chat-context-actions");
  const useButton = make("button", "link-button", "Use Context");
  useButton.type = "button";
  useButton.addEventListener("click", () => insertTaskChatContext(card.title, card.lines || []));
  actions.append(useButton);
  if (card.sectionId) {
    const openButton = make("button", "link-button", "Open");
    openButton.type = "button";
    openButton.addEventListener("click", () => openTaskChatContextSection(card.sectionId));
    actions.append(openButton);
  }
  item.append(copy, actions);
  target.append(item);
}

function renderTaskChatContextStream() {
  const target = qs("#taskChatContextStream");
  if (!target) {
    return;
  }
  clear(target);
  const context = latestTaskChatContext;
  const activeRoot = context.active?.active_root_dir || activeRootDir || "-";
  const summary = make("div", "task-chat-context-summary");
  appendKeyValue(summary, "Root", compactPath(activeRoot));
  appendKeyValue(summary, "Tasks", `${context.plans.length} plans / ${context.runs.length} runs`);
  appendKeyValue(summary, "Pending approvals", String(context.approvals.length), context.approvals.length ? "pending" : "ok");
  appendKeyValue(summary, "Latest activity", taskChatLatestActivity(context));
  if (context.unavailable_count) {
    appendKeyValue(summary, "Limited sources", String(context.unavailable_count), "pending");
  }
  target.append(summary);
  if (context.errors.length) {
    target.append(
      statusBox(
        "Context partially loaded",
        context.errors
          .slice(0, 3)
          .map((error) => `${error.label}: ${error.error}`)
          .join("; "),
        "pending",
      ),
    );
  }
  const cards = make("div", "task-chat-context-cards");
  for (const plan of context.plans.slice(-2).reverse()) {
    renderTaskChatContextCard(cards, {
      title: `Plan ${plan.id}`,
      meta: `${formatTimestamp(plan.created_at)} - ${plan.steps?.length || 0} steps`,
      state: plan.status || "ready",
      sectionId: "tasks",
      lines: taskPlanContextLines(plan),
    });
  }
  for (const run of context.runs.slice(-2).reverse()) {
    renderTaskChatContextCard(cards, {
      title: `Run ${run.id}`,
      meta: `${run.plan_id || "plan"} - ${formatTimestamp(run.completed_at || run.started_at)}`,
      state: run.status,
      sectionId: "tasks",
      lines: taskRunContextLines(run),
    });
  }
  for (const item of context.approvals.slice(0, 3)) {
    renderTaskChatContextCard(cards, {
      title: `${item.source.label} approval ${item.approval.id}`,
      meta: approvalTitle(item),
      state: item.approval.status,
      sectionId: "approvals",
      lines: [
        `Approval: ${item.source.label} ${item.approval.id}`,
        `Status: ${item.approval.status || "-"}`,
        `Subject: ${approvalTitle(item)}`,
      ],
    });
  }
  for (const event of context.logs.slice(0, 2)) {
    renderTaskChatContextCard(cards, {
      title: `Event ${event.event_type || "log"}`,
      meta: formatTimestamp(event.created_at),
      state: "event",
      sectionId: "logs",
      lines: [
        `Event: ${event.event_type || "-"}`,
        `Actor: ${event.actor || "-"}`,
        `Message: ${event.message || "-"}`,
      ],
    });
  }
  if (!cards.childElementCount) {
    cards.append(statusBox("No context cards", "Plans, runs, approvals, and logs will appear here as work starts.", "pending"));
  }
  target.append(cards);
}

function boundedString(value, limit = 600) {
  if (typeof value !== "string") {
    return "";
  }
  return value.length > limit ? value.slice(0, limit) : value;
}

function boundedStringList(values, limit = 8, itemLimit = 280) {
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .slice(0, limit)
    .map((value) => boundedString(value, itemLimit))
    .filter(Boolean);
}

function compactTaskChatPlan(plan) {
  if (!plan || typeof plan !== "object") {
    return null;
  }
  return {
    id: boundedString(plan.id, 120),
    objective: boundedString(plan.objective, 800),
    created_at: boundedString(plan.created_at, 80),
    status: boundedString(plan.status, 80),
    constraints: boundedStringList(plan.constraints),
    acceptance_criteria: boundedStringList(plan.acceptance_criteria),
    clarification_questions: boundedStringList(plan.clarification_questions),
    steps: (Array.isArray(plan.steps) ? plan.steps : []).slice(0, 12).map((step) => {
      const safeStep = step && typeof step === "object" ? step : {};
      return {
        id: boundedString(safeStep.id, 120),
        title: boundedString(safeStep.title, 240),
        description: boundedString(safeStep.description, 500),
        agent_role: boundedString(safeStep.agent_role, 120),
        status: boundedString(safeStep.status, 80),
        validation: boundedString(safeStep.validation, 360),
        dependencies: boundedStringList(safeStep.dependencies, 8, 120),
        tools: boundedStringList(safeStep.tools, 8, 120),
      };
    }),
  };
}

function compactTaskChatRun(run) {
  if (!run || typeof run !== "object") {
    return null;
  }
  return {
    id: boundedString(run.id, 120),
    status: boundedString(run.status, 80),
    completed_at: boundedString(run.completed_at, 80),
    results: (Array.isArray(run.results) ? run.results : []).slice(0, 12).map((result) => {
      const safeResult = result && typeof result === "object" ? result : {};
      return {
        step_id: boundedString(safeResult.step_id, 120),
        status: boundedString(safeResult.status, 80),
        error: boundedString(safeResult.error, 360),
      };
    }),
  };
}

function compactTaskChatMessage(message, { restored = false } = {}) {
  if (!message || typeof message !== "object") {
    return null;
  }
  const compact = {
    role: message.role === "user" ? "user" : "agent",
    title: boundedString(message.title, 160),
    detail: boundedString(message.detail, 1200),
    state: boundedString(message.state, 80),
    createdAt: boundedString(message.createdAt, 80) || new Date().toISOString(),
  };
  if (message.plan) {
    compact.plan = compactTaskChatPlan(message.plan);
  }
  if (message.run) {
    compact.run = compactTaskChatRun(message.run);
  }
  if (restored) {
    compact.restored = true;
  }
  return compact;
}

function taskChatHistoryMessagesForStorage() {
  const messages = taskChatMessages
    .slice(-TASK_CHAT_HISTORY_MAX_MESSAGES)
    .map((message) => compactTaskChatMessage(message))
    .filter(Boolean);
  while (messages.length && JSON.stringify(messages).length > TASK_CHAT_HISTORY_MAX_BYTES) {
    messages.shift();
  }
  return messages;
}

function updateTaskChatHistoryStatus(message) {
  const target = qs("#taskChatHistoryStatus");
  if (!target) {
    return;
  }
  if (message) {
    target.textContent = message;
    return;
  }
  target.textContent = taskChatMessages.length ? `${taskChatMessages.length} saved` : "No saved history";
}

function saveTaskChatHistory() {
  try {
    if (!taskChatMessages.length) {
      clearTaskChatHistory();
      return;
    }
    const historyMessages = taskChatHistoryMessagesForStorage();
    localStorage.setItem(TASK_CHAT_HISTORY_KEY, JSON.stringify(historyMessages));
    updateTaskChatHistoryStatus();
  } catch (_error) {
    updateTaskChatHistoryStatus("History not saved");
  }
}

function loadTaskChatHistory() {
  try {
    const rawHistory = localStorage.getItem(TASK_CHAT_HISTORY_KEY);
    if (!rawHistory) {
      updateTaskChatHistoryStatus();
      return;
    }
    const parsed = JSON.parse(rawHistory);
    if (!Array.isArray(parsed)) {
      throw new Error("Task chat history must be an array.");
    }
    taskChatMessages = parsed
      .slice(-TASK_CHAT_HISTORY_MAX_MESSAGES)
      .map((message) => compactTaskChatMessage(message, { restored: true }))
      .filter(Boolean);
    updateTaskChatHistoryStatus(taskChatMessages.length ? `${taskChatMessages.length} restored` : undefined);
  } catch (_error) {
    taskChatMessages = [];
    clearTaskChatHistory();
    updateTaskChatHistoryStatus("History reset");
  }
}

function clearTaskChatHistory() {
  try {
    localStorage.removeItem(TASK_CHAT_HISTORY_KEY);
  } catch (_error) {
    // Local storage can be unavailable in private or locked-down browser sessions.
  }
  updateTaskChatHistoryStatus();
}

function appendTaskChatMessage(message) {
  taskChatMessages.push({
    createdAt: new Date().toISOString(),
    ...message,
  });
  saveTaskChatHistory();
  renderTaskChatThread();
}

function renderTaskChatThread() {
  const target = qs("#taskChatTranscript");
  clear(target);
  if (!taskChatMessages.length) {
    target.append(statusBox("No task messages", "Ready.", "pending"));
    return;
  }
  for (const message of taskChatMessages) {
    renderTaskChatMessage(target, message);
  }
  target.scrollTop = target.scrollHeight;
}

function renderTaskChatMessage(target, message) {
  const item = make("div", `task-chat-message task-chat-message-${message.role || "agent"}`);
  const header = make("div", "task-chat-message-header");
  header.append(make("strong", "", message.title || (message.role === "user" ? "You" : "DGentic")));
  header.append(make("span", "item-meta", formatTimestamp(message.createdAt)));
  item.append(header);
  if (message.detail) {
    item.append(make("div", "item-meta", message.detail));
  }
  if (message.state) {
    item.append(statusChip(message.state));
  }
  if (message.restored) {
    item.append(statusChip("saved"));
  }
  if (message.plan) {
    renderTaskChatPlan(item, message.plan, { historical: message.restored });
  }
  if (message.run) {
    renderTaskRunResult(item, message.run);
  }
  target.append(item);
}

function renderTaskChatPlan(target, plan, options = {}) {
  const card = make("div", "task-chat-plan-card");
  const header = make("div", "task-plan-header");
  const copy = make("div");
  copy.append(make("div", "item-title", plan.objective || plan.id));
  copy.append(
    make(
      "div",
      "item-meta",
      `${plan.id} - ${formatTimestamp(plan.created_at)} - ${plan.steps?.length || 0} steps`,
    ),
  );
  const actions = make("div", "task-plan-actions");
  const contextButton = make("button", "link-button", "Use Context");
  contextButton.type = "button";
  contextButton.dataset.testid = "task-plan-use-context";
  contextButton.addEventListener("click", () =>
    insertTaskChatContext(`Plan ${plan.id}`, taskPlanContextLines(plan)),
  );
  const runButton = make("button", "primary-button", "Run Plan");
  runButton.type = "button";
  runButton.disabled = options.historical || !(plan.steps || []).length;
  if (options.historical) {
    runButton.title = "Saved history is display only.";
  }
  runButton.addEventListener("click", () => runTaskChatPlan(plan));
  actions.append(statusChip(plan.status), contextButton, runButton);
  header.append(copy, actions);
  card.append(header);
  renderTaskPlanContext(card, plan);
  renderTaskPlanSteps(card, plan);
  target.append(card);
}

async function runTaskPlan(plan) {
  return api("/tasks/execute", { method: "POST", body: plan });
}

async function runTaskChatPlan(plan) {
  appendTaskChatMessage({
    role: "agent",
    title: "Running plan",
    detail: plan.id,
    state: "running",
  });
  try {
    const run = await runTaskPlan(plan);
    appendTaskChatMessage({
      role: "agent",
      title: "Task plan executed",
      detail: `${run.id} - ${run.results?.length || 0} step results`,
      state: run.status,
      run,
    });
    await Promise.all([loadTasks(), loadTaskChatContext()]);
    showToast("Task plan executed.");
  } catch (error) {
    appendTaskChatMessage({
      role: "agent",
      title: "Task execution failed",
      detail: error.message,
      state: "failed",
    });
    showToast(error.message);
  }
}

function clearTaskChatThread() {
  taskChatMessages = [];
  clearTaskChatHistory();
  renderTaskChatThread();
}

async function submitTaskChatMessage(event) {
  event.preventDefault();
  const payload = taskChatPayload();
  if (!payload.objective) {
    showToast("Message is required.");
    return;
  }
  appendTaskChatMessage({
    role: "user",
    title: "You",
    detail: payload.objective,
    state: payload.priority,
  });
  appendTaskChatMessage({
    role: "agent",
    title: "Creating plan",
    detail: "Submitting task objective.",
    state: "running",
  });
  try {
    const plan = await api("/tasks/plan", { method: "POST", body: payload });
    appendTaskChatMessage({
      role: "agent",
      title: "Plan created",
      detail: `${plan.id} - ${plan.steps?.length || 0} steps`,
      state: "ready",
      plan,
    });
    qs("#taskChatInput").value = "";
    if (qs("#taskChatRunInput").checked) {
      await runTaskChatPlan(plan);
    } else {
      await Promise.all([loadTasks(), loadTaskChatContext()]);
      showToast("Task plan created.");
    }
  } catch (error) {
    appendTaskChatMessage({
      role: "agent",
      title: "Plan failed",
      detail: error.message,
      state: "failed",
    });
    showToast(error.message);
  }
}

function runsForPlan(plan, runs) {
  return (runs || [])
    .filter((run) => run.plan_id === plan.id)
    .sort((left, right) => new Date(right.started_at || 0) - new Date(left.started_at || 0));
}

function renderTaskPlanCard(target, plan, relatedRuns) {
  const card = make("div", "task-plan-card");
  const header = make("div", "task-plan-header");
  const copy = make("div");
  copy.append(make("div", "item-title", plan.objective || plan.id));
  copy.append(
    make(
      "div",
      "item-meta",
      `${plan.id} - ${formatTimestamp(plan.created_at)} - ${plan.steps?.length || 0} steps`,
    ),
  );
  const actions = make("div", "task-plan-actions");
  const runButton = make("button", "primary-button", "Run Plan");
  runButton.type = "button";
  runButton.disabled = !(plan.steps || []).length;
  runButton.addEventListener("click", () => executeTaskPlan(plan));
  actions.append(statusChip(plan.status), runButton);
  header.append(copy, actions);
  card.append(header);

  renderTaskPlanContext(card, plan);
  renderTaskPlanSteps(card, plan);
  renderTaskRunSummary(card, relatedRuns);
  target.append(card);
}

function renderTaskPlanContext(target, plan) {
  const constraints = plan.constraints || [];
  const acceptance = plan.acceptance_criteria || [];
  const questions = plan.clarification_questions || [];
  if (!constraints.length && !acceptance.length && !questions.length) {
    return;
  }
  const context = make("div", "task-plan-context");
  renderChipList(context, "Constraints", constraints, "pending");
  renderChipList(context, "Acceptance", acceptance, "ok");
  renderChipList(context, "Questions", questions, "running");
  target.append(context);
}

function renderTaskPlanSteps(target, plan) {
  const steps = plan.steps || [];
  const list = make("div", "task-step-list");
  if (!steps.length) {
    list.append(statusBox("No plan steps", "This draft has no executable steps.", "pending"));
    target.append(list);
    return;
  }
  for (const step of steps) {
    const item = make("div", "task-step-card");
    const titleRow = make("div", "task-step-title-row");
    const title = make("div");
    title.append(make("div", "item-title", step.title || step.id));
    title.append(make("div", "item-meta", `${step.id} - ${step.agent_role || "orchestrator"}`));
    titleRow.append(title, statusChip(step.status));
    item.append(titleRow);
    if (step.description) {
      item.append(make("div", "item-meta", step.description));
    }
    const details = make("div", "task-step-detail-grid");
    appendKeyValue(details, "Validation", step.validation || "-");
    appendKeyValue(details, "Dependencies", (step.dependencies || []).join(", ") || "-");
    appendKeyValue(details, "Tools", (step.tools || []).join(", ") || "-");
    item.append(details);
    list.append(item);
  }
  target.append(list);
}

function renderTaskRunSummary(target, relatedRuns) {
  const panel = make("div", "task-run-summary");
  if (!relatedRuns.length) {
    panel.append(statusBox("No runs yet", "Run this plan to create deterministic execution evidence.", "pending"));
    target.append(panel);
    return;
  }
  for (const run of relatedRuns.slice(0, 3)) {
    renderTaskRunResult(panel, run);
  }
  target.append(panel);
}

function renderTaskRunResult(target, run) {
  const item = make("div", "task-run-row");
  const copy = make("div");
  const completed = run.completed_at ? ` - completed ${formatTimestamp(run.completed_at)}` : "";
  copy.append(make("div", "item-title", run.id));
  copy.append(make("div", "item-meta", `${run.results?.length || 0} step results${completed}`));
  const actions = make("div", "task-run-actions");
  const contextButton = make("button", "link-button", "Use Evidence");
  contextButton.type = "button";
  contextButton.dataset.testid = "task-run-use-evidence";
  contextButton.dataset.runId = run.id || "";
  contextButton.addEventListener("click", () =>
    insertTaskChatContext(`Run ${run.id}`, taskRunContextLines(run)),
  );
  actions.append(statusChip(run.status), contextButton);
  item.append(copy, actions);

  const resultList = make("div", "task-run-result-list");
  for (const result of (run.results || []).slice(0, 4)) {
    const resultItem = make("div", "finding-row");
    resultItem.append(statusChip(result.status));
    resultItem.append(make("span", "", `${result.step_id}${result.error ? ` - ${result.error}` : ""}`));
    resultList.append(resultItem);
  }
  target.append(item, resultList);
}

async function executeTaskPlan(plan) {
  const target = qs("#taskOutput");
  clear(target);
  target.append(statusBox("Running plan", plan.id, "running"));
  try {
    const run = await runTaskPlan(plan);
    clear(target);
    target.append(statusBox("Task plan executed", `${run.id} - ${run.results?.length || 0} step results`, run.status));
    renderTaskRunResult(target, run);
    target.append(jsonBlock(run));
    await Promise.all([loadTasks(), loadTaskChatContext()]);
    showToast("Task plan executed.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Task execution failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderOrchestrationSummary(summary, orchestrations, agents) {
  const target = qs("#orchestrationSummary");
  const detailTarget = qs("#orchestrationDetail");
  clear(target);
  clear(detailTarget);
  if (!summary.ok) {
    target.append(statusBox("Summary unavailable", summary.error, "blocked"));
  } else {
    const item = make("div", "list-item");
    item.append(make("div", "item-title", `${summary.data.total_runs || 0} orchestration runs`));
    item.append(make("div", "item-meta", countsText(summary.data.run_status_counts)));
    target.append(item);

    const operations = make("div", "checkpoint-grid");
    appendKeyValue(operations, "Tasks", countsText(summary.data.task_status_counts));
    appendKeyValue(operations, "Executions", countsText(summary.data.execution_status_counts));
    appendKeyValue(operations, "Active", String(summary.data.active_execution_count || 0));
    appendKeyValue(operations, "Blockers", String(summary.data.unresolved_blocker_count || 0));
    target.append(operations);
  }

  if (!orchestrations.ok) {
    target.append(statusBox("Runs unavailable", orchestrations.error, "blocked"));
    return;
  }
  const runs = orchestrations.data.slice(-6).reverse();
  if (!runs.length) {
    detailTarget.append(statusBox("No orchestration runs", "No task graph records are available.", "pending"));
    return;
  }
  const selectedStillVisible = runs.some((run) => run.id === selectedOrchestrationId);
  if (!selectedOrchestrationId || !selectedStillVisible) {
    selectedOrchestrationId = runs[0].id;
  }
  for (const run of runs) {
    const row = make("div", "run-row");
    const copy = make("div");
    copy.append(make("div", "item-title", run.objective || run.id));
    copy.append(
      make(
        "div",
        "item-meta",
        `${run.id} - tasks: ${run.tasks?.length || 0} - updated: ${formatTimestamp(run.updated_at)}`,
      ),
    );
    const inspectButton = make("button", "link-button", run.id === selectedOrchestrationId ? "Selected" : "Inspect");
    inspectButton.type = "button";
    inspectButton.disabled = run.id === selectedOrchestrationId;
    inspectButton.addEventListener("click", () => selectOrchestration(run.id, run));
    row.append(copy, statusChip(run.status), inspectButton);
    target.append(row);
    if (run.id === selectedOrchestrationId) {
      renderOrchestrationDetail(run, { ok: true, data: [] }, true, agents);
      void loadOrchestrationDetail(run.id, run, agents);
    }
  }
}

function selectOrchestration(runId, run = null) {
  selectedOrchestrationId = runId;
  loadOrchestrationDetail(runId, run);
}

async function loadOrchestrationDetail(runId, knownRun = null, knownAgents = null) {
  const target = qs("#orchestrationDetail");
  clear(target);
  target.append(statusBox("Loading orchestration", runId, "running"));
  const [runResult, executions, agents] = await Promise.all([
    knownRun ? Promise.resolve({ ok: true, data: knownRun }) : safeLoad("orchestration", () => api(`/tasks/orchestrations/${encodeURIComponent(runId)}`)),
    safeLoad("executions", () => api(`/tasks/orchestrations/${encodeURIComponent(runId)}/executions`)),
    knownAgents ? Promise.resolve(knownAgents) : safeLoad("agents", () => api("/agents")),
  ]);
  if (selectedOrchestrationId !== runId) {
    return;
  }
  clear(target);
  if (!runResult.ok) {
    target.append(statusBox("Orchestration unavailable", runResult.error, "blocked"));
    return;
  }
  renderOrchestrationDetail(runResult.data, executions, false, agents);
}

function renderOrchestrationDetail(run, executionsResult, loadingExecutions = false, agentsResult = null) {
  const target = qs("#orchestrationDetail");
  clear(target);
  const executions = executionsResult.ok ? executionsResult.data : [];
  const active = loadingExecutions ? null : activeExecution(executions);
  const runOpen = run.status === "running";
  target.append(statusBox(run.objective || run.id, `${run.id} - ${run.status}`, run.status));

  const controls = make("div", "orchestration-controls");
  const cycleButton = make("button", "link-button", "Cycle");
  cycleButton.type = "button";
  cycleButton.disabled = !runOpen;
  cycleButton.addEventListener("click", () => postOrchestrationRunAction(run.id, "cycle"));
  const loopButton = make("button", "primary-button", "Loop");
  loopButton.type = "button";
  loopButton.disabled = !runOpen;
  loopButton.addEventListener("click", () => postOrchestrationLoop(run.id));
  const startButton = make("button", "link-button", "Start");
  startButton.type = "button";
  startButton.disabled = !runOpen || loadingExecutions || Boolean(active);
  startButton.addEventListener("click", () => postOrchestrationExecution(run.id));
  controls.append(cycleButton, loopButton, startButton);
  if (active) {
    const cancelButton = make("button", "danger-button", "Cancel");
    cancelButton.type = "button";
    cancelButton.addEventListener("click", () => cancelOrchestrationExecution(run.id, active.id));
    controls.append(cancelButton);
  }
  target.append(controls);

  const options = make("div", "orchestration-options");
  const iterationLabel = make("label");
  iterationLabel.textContent = "Max Iterations";
  const iterationInput = make("input");
  iterationInput.id = "orchestrationLoopIterations";
  iterationInput.type = "number";
  iterationInput.min = "1";
  iterationInput.max = "50";
  iterationInput.value = "10";
  iterationLabel.append(iterationInput);
  const blockerLabel = make("label", "checkbox-label");
  const blockerInput = make("input");
  blockerInput.id = "orchestrationStopOnBlocked";
  blockerInput.type = "checkbox";
  blockerInput.checked = true;
  blockerLabel.append(blockerInput, make("span", "", "Stop on blockers"));
  options.append(iterationLabel, blockerLabel);
  target.append(options);

  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Tasks", countsText(taskStatusCounts(run.tasks)));
  appendKeyValue(grid, "Scheduled", (run.scheduled_task_ids || []).join(", ") || "-");
  appendKeyValue(grid, "Evidence", (run.required_dod_evidence || []).join(", ") || "-");
  appendKeyValue(grid, "Updated", formatTimestamp(run.updated_at));
  target.append(grid);

  renderOrchestrationTasks(target, run, run.tasks || [], agentsResult);
  renderAgentHierarchy(target, run, agentsResult);
  renderOrchestrationBlockers(target, run, run.blockers || []);
  renderOrchestrationFollowUps(target, run.follow_ups || []);
  renderOrchestrationCloseout(target, run);
  renderOrchestrationExecutions(target, executionsResult, loadingExecutions);
}

function renderOrchestrationTasks(target, run, tasks, agentsResult = null) {
  const box = make("div", "orchestration-task-list");
  box.append(make("div", "item-title", "Task Graph"));
  if (!tasks.length) {
    box.append(make("div", "item-meta", "No tasks recorded."));
    target.append(box);
    return;
  }
  for (const task of tasks) {
    const item = make("div", "task-card");
    const title = make("div", "task-title-row");
    title.append(make("strong", "", `${task.id}: ${task.title}`), statusChip(task.status));
    item.append(title);
    item.append(make("div", "item-meta", `${task.role} - agent: ${task.agent_id || "-"} - retries: ${task.retry_count || 0}/${task.retry_limit || 0}`));
    if (task.dependencies?.length) {
      item.append(make("div", "item-meta", `Depends on: ${task.dependencies.join(", ")}`));
    }
    if (task.declared_write_paths?.length) {
      item.append(make("div", "item-meta", `Writes: ${task.declared_write_paths.join(", ")}`));
    }
    if (task.error) {
      item.append(statusBox("Task error", task.error, "failed"));
    }
    renderTaskAgentBrief(item, task, agentsResult);
    renderTaskActionForms(item, run, task);
    box.append(item);
  }
  target.append(box);
}

function renderTaskActionForms(target, run, task) {
  if (run.status !== "running") {
    return;
  }
  if (task.status === "running") {
    renderTaskUpdateForm(target, run.id, task);
  }
  if (canRecoverTask(run, task)) {
    renderTaskRecoveryForm(target, run.id, task);
  }
}

function unresolvedTaskBlockers(run, taskId) {
  return (run.blockers || []).filter((blocker) => blocker.task_id === taskId && blocker.status !== "resolved");
}

function canRecoverTask(run, task) {
  if (task.status !== "blocked") {
    return false;
  }
  const blockers = unresolvedTaskBlockers(run, task.id);
  return blockers.length > 0 && blockers.every((blocker) => recoverableTaskBlockerSeverities.has(blocker.severity));
}

function renderTaskUpdateForm(target, runId, task) {
  const detail = make("details", "orchestration-form");
  detail.append(make("summary", "", "Update task"));
  const form = make("form", "stacked-form");

  const statusLabel = make("label");
  statusLabel.textContent = "Status";
  const statusInput = make("select");
  statusInput.name = "status";
  for (const status of ["completed", "failed", "blocked"]) {
    const option = make("option", "", status);
    option.value = status;
    statusInput.append(option);
  }
  statusLabel.append(statusInput);

  const outputLabel = make("label");
  outputLabel.textContent = "Output Note";
  const outputInput = make("textarea");
  outputInput.name = "output_note";
  outputInput.rows = 3;
  outputLabel.append(outputInput);

  const errorLabel = make("label");
  errorLabel.textContent = "Failure Or Blocker Reason";
  const errorInput = make("textarea");
  errorInput.name = "error";
  errorInput.rows = 3;
  errorLabel.append(errorInput);

  const footer = make("div", "form-footer");
  footer.append(make("span", "item-meta", task.id));
  const button = make("button", "primary-button", "Save Task");
  button.type = "submit";
  footer.append(button);

  form.append(statusLabel, outputLabel, errorLabel, footer);
  form.addEventListener("submit", (event) => submitOrchestrationTaskUpdate(event, runId, task.id, form));
  detail.append(form);
  target.append(detail);
}

function renderTaskRecoveryForm(target, runId, task) {
  const detail = make("details", "orchestration-form");
  detail.append(make("summary", "", "Recover task"));
  const form = make("form", "stacked-form");

  const resolutionLabel = make("label");
  resolutionLabel.textContent = "Resolution";
  const resolutionInput = make("textarea");
  resolutionInput.name = "resolution";
  resolutionInput.rows = 3;
  resolutionInput.required = true;
  resolutionLabel.append(resolutionInput);

  const roleLabel = make("label");
  roleLabel.textContent = "Role";
  const roleInput = make("input");
  roleInput.name = "role";
  roleInput.type = "text";
  roleInput.value = task.role || "";
  roleLabel.append(roleInput);

  const pathsLabel = make("label");
  pathsLabel.textContent = "Declared Write Paths";
  const pathsInput = make("textarea");
  pathsInput.name = "declared_write_paths";
  pathsInput.rows = 3;
  pathsInput.value = (task.declared_write_paths || []).join("\n");
  pathsLabel.append(pathsInput);

  const resetLabel = make("label", "checkbox-label");
  const resetInput = make("input");
  resetInput.name = "reset_retry_count";
  resetInput.type = "checkbox";
  resetLabel.append(resetInput, make("span", "", "Reset retry count"));

  const footer = make("div", "form-footer");
  footer.append(resetLabel);
  const button = make("button", "primary-button", "Recover");
  button.type = "submit";
  footer.append(button);

  form.append(resolutionLabel, roleLabel, pathsLabel, footer);
  form.addEventListener("submit", (event) => submitOrchestrationTaskRecovery(event, runId, task.id, form));
  detail.append(form);
  target.append(detail);
}

function renderTaskAgentBrief(target, task, agentsResult) {
  if (!task.agent_id) {
    return;
  }
  if (!agentsResult) {
    target.append(make("div", "item-meta", "Agent detail loading."));
    return;
  }
  if (!agentsResult.ok) {
    target.append(statusBox("Agent detail unavailable", agentsResult.error, "blocked"));
    return;
  }
  const agents = Array.isArray(agentsResult.data) ? agentsResult.data : [];
  const agent = agents.find((candidate) => candidate.id === task.agent_id);
  if (!agent) {
    target.append(statusBox("Agent detail unavailable", task.agent_id, "pending"));
    return;
  }
  const detail = make("details", "agent-brief");
  detail.append(make("summary", "", `Agent ${agent.id}`));
  const grid = make("div", "agent-brief-grid");
  appendKeyValue(grid, "Role", agent.role || task.role || "-");
  appendKeyValue(grid, "Status", agent.status || "-", agent.status || "");
  appendKeyValue(grid, "Parent", agent.parent_agent_id || "-");
  appendKeyValue(grid, "Task", agent.task_id || task.id || "-");
  appendKeyValue(grid, "Created", formatTimestamp(agent.created_at));
  appendKeyValue(grid, "Completed", formatTimestamp(agent.completed_at));
  detail.append(grid);
  if (agent.task) {
    detail.append(make("div", "item-meta", agent.task));
  }
  if (agent.expected_output) {
    detail.append(make("div", "item-meta", `Expected: ${agent.expected_output}`));
  }
  if (agent.required_data?.length) {
    detail.append(make("div", "item-meta", `Needs: ${agent.required_data.join(", ")}`));
  }
  if (agent.context?.length) {
    const context = make("div", "changed-paths");
    context.append(make("div", "item-title", "Context"));
    for (const item of agent.context.slice(0, 4)) {
      context.append(make("code", "", item));
    }
    detail.append(context);
  }
  target.append(detail);
}

function renderAgentHierarchy(target, run, agentsResult) {
  const taskAgentIds = new Set((run.tasks || []).map((task) => task.agent_id).filter(Boolean));
  if (!taskAgentIds.size) {
    return;
  }
  const box = make("div", "agent-tree");
  box.append(make("div", "item-title", "Agent Graph"));
  if (!agentsResult) {
    box.append(make("div", "item-meta", "Agent graph loading."));
    target.append(box);
    return;
  }
  if (!agentsResult.ok) {
    box.append(statusBox("Agent graph unavailable", agentsResult.error, "blocked"));
    target.append(box);
    return;
  }
  const agents = Array.isArray(agentsResult.data) ? agentsResult.data : [];
  const agentsById = new Map(agents.map((agent) => [agent.id, agent]));
  const included = new Set(Array.from(taskAgentIds).filter((agentId) => agentsById.has(agentId)));
  let changed = true;
  while (changed) {
    changed = false;
    for (const agent of agents) {
      if (agent.parent_agent_id && included.has(agent.parent_agent_id) && !included.has(agent.id)) {
        included.add(agent.id);
        changed = true;
      }
    }
  }
  if (!included.size) {
    box.append(statusBox("Agent graph unavailable", "No visible agents match this run.", "pending"));
    target.append(box);
    return;
  }
  const tasksByAgentId = new Map((run.tasks || []).filter((task) => task.agent_id).map((task) => [task.agent_id, task]));
  const childrenByParentId = new Map();
  for (const agentId of included) {
    const agent = agentsById.get(agentId);
    const parentId = agent.parent_agent_id && included.has(agent.parent_agent_id) ? agent.parent_agent_id : "";
    if (!childrenByParentId.has(parentId)) {
      childrenByParentId.set(parentId, []);
    }
    childrenByParentId.get(parentId).push(agent);
  }
  const appendAgentNode = (container, agent, depth = 0) => {
    const node = make("div", "agent-node");
    node.style.setProperty("--depth", String(depth));
    const row = make("div", "task-title-row");
    row.append(make("strong", "", agent.id), statusChip(agent.status));
    node.append(row);
    const task = tasksByAgentId.get(agent.id);
    node.append(make("div", "item-meta", `${agent.role || task?.role || "-"} - task: ${task?.id || agent.task_id || "-"}`));
    if (agent.task) {
      node.append(make("div", "item-meta", agent.task));
    }
    container.append(node);
    for (const child of childrenByParentId.get(agent.id) || []) {
      appendAgentNode(container, child, depth + 1);
    }
  };
  for (const root of childrenByParentId.get("") || []) {
    appendAgentNode(box, root);
  }
  target.append(box);
}

function renderOrchestrationBlockers(target, run, blockers) {
  const openBlockers = blockers.filter((blocker) => blocker.status !== "resolved");
  if (!openBlockers.length) {
    return;
  }
  const box = make("div", "finding-list");
  box.append(make("div", "item-title", "Open Blockers"));
  for (const blocker of openBlockers) {
    const row = make("div", "finding-row");
    row.append(statusChip(blocker.severity || "blocked"), make("span", "", `${blocker.task_id}: ${blocker.reason}`));
    box.append(row);
    if (run.status === "running" && resolvableTaskBlockerSeverities.has(blocker.severity)) {
      renderBlockerResolutionForm(box, run.id, blocker);
    }
  }
  target.append(box);
}

function renderBlockerResolutionForm(target, runId, blocker) {
  const detail = make("details", "orchestration-form");
  detail.append(make("summary", "", `Resolve ${blocker.id}`));
  const form = make("form", "stacked-form");

  const resolutionLabel = make("label");
  resolutionLabel.textContent = "Resolution";
  const resolutionInput = make("textarea");
  resolutionInput.name = "resolution";
  resolutionInput.rows = 3;
  resolutionInput.required = true;
  resolutionLabel.append(resolutionInput);

  const rescheduleLabel = make("label", "checkbox-label");
  const rescheduleInput = make("input");
  rescheduleInput.name = "reschedule";
  rescheduleInput.type = "checkbox";
  rescheduleLabel.append(rescheduleInput, make("span", "", "Reschedule after resolve"));

  const footer = make("div", "form-footer");
  footer.append(rescheduleLabel);
  const button = make("button", "primary-button", "Resolve");
  button.type = "submit";
  footer.append(button);

  form.append(resolutionLabel, footer);
  form.addEventListener("submit", (event) =>
    submitOrchestrationBlockerResolution(event, runId, blocker.id, form),
  );
  detail.append(form);
  target.append(detail);
}

function renderOrchestrationFollowUps(target, followUps) {
  if (!followUps.length) {
    return;
  }
  const box = make("div", "changed-paths");
  box.append(make("div", "item-title", "Follow-ups"));
  for (const followUp of followUps.slice(0, 8)) {
    box.append(make("code", "", `${followUp.assigned_role} - ${followUp.task_id}: ${followUp.description}`));
  }
  target.append(box);
}

function renderOrchestrationCloseout(target, run) {
  if (run.status !== "running") {
    return;
  }
  const detail = make("details", "orchestration-form");
  detail.append(make("summary", "", "Close orchestration"));
  const form = make("form", "stacked-form");
  const incompleteTasks = (run.tasks || []).filter((task) => task.status !== "completed");
  const openBlockers = (run.blockers || []).filter((blocker) => blocker.status !== "resolved");
  if (incompleteTasks.length || openBlockers.length) {
    form.append(
      statusBox(
        "Close blocked",
        `${incompleteTasks.length} incomplete tasks, ${openBlockers.length} open blockers`,
        "blocked",
      ),
    );
  }

  const evidenceKeys = run.required_dod_evidence || [];
  if (!evidenceKeys.length) {
    form.append(make("div", "item-meta", "No required Definition of Done evidence keys are configured."));
  }
  for (const key of evidenceKeys) {
    const label = make("label");
    label.textContent = key;
    const input = make("textarea");
    input.name = "evidence";
    input.dataset.evidenceKey = key;
    input.rows = 3;
    input.required = true;
    input.value = run.dod_evidence?.[key] || "";
    label.append(input);
    form.append(label);
  }

  const footer = make("div", "form-footer");
  footer.append(make("span", "item-meta", run.id));
  const button = make("button", "primary-button", "Close Run");
  button.type = "submit";
  button.disabled = Boolean(incompleteTasks.length || openBlockers.length);
  footer.append(button);
  form.append(footer);
  form.addEventListener("submit", (event) => submitOrchestrationCloseout(event, run.id, form));
  detail.append(form);
  target.append(detail);
}

function renderOrchestrationExecutions(target, executionsResult, loadingExecutions) {
  const box = make("div", "changed-paths");
  box.append(make("div", "item-title", "Executions"));
  if (loadingExecutions) {
    box.append(make("div", "item-meta", "Loading execution records."));
  } else if (!executionsResult.ok) {
    box.append(statusBox("Executions unavailable", executionsResult.error, "blocked"));
  } else if (!executionsResult.data.length) {
    box.append(make("div", "item-meta", "No background executions recorded."));
  } else {
    for (const execution of executionsResult.data.slice(-5).reverse()) {
      const row = make("div", "execution-row");
      row.append(
        make(
          "span",
          "",
          `${execution.id} - ${execution.status} - started: ${formatTimestamp(execution.started_at)}`,
        ),
        statusChip(execution.status),
      );
      if (execution.status_reason || execution.error) {
        row.append(make("span", "item-meta", execution.status_reason || execution.error));
      }
      box.append(row);
    }
  }
  target.append(box);
}

async function postOrchestrationRunAction(runId, action) {
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Updating orchestration", action, "running"));
  try {
    const run = await api(`/tasks/orchestrations/${encodeURIComponent(runId)}/${action}`, {
      method: "POST",
    });
    showToast(`Orchestration ${action} completed.`);
    await loadOrchestrationDetail(run.id, run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Orchestration action failed", error.message, "failed"));
  }
}

async function postOrchestrationLoop(runId) {
  const iterations = Number(qs("#orchestrationLoopIterations")?.value || 10);
  const payload = {
    max_iterations: Math.min(Math.max(iterations || 10, 1), 50),
    stop_on_blocked: Boolean(qs("#orchestrationStopOnBlocked")?.checked),
  };
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Looping orchestration", `${payload.max_iterations} iterations`, "running"));
  try {
    const result = await api(`/tasks/orchestrations/${encodeURIComponent(runId)}/loop`, {
      method: "POST",
      body: payload,
    });
    showToast(`Loop stopped: ${result.stopped_reason}.`);
    await loadOrchestrationDetail(result.run.id, result.run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Orchestration loop failed", error.message, "failed"));
  }
}

async function postOrchestrationExecution(runId) {
  const iterations = Number(qs("#orchestrationLoopIterations")?.value || 10);
  const payload = {
    max_iterations: Math.min(Math.max(iterations || 10, 1), 50),
    stop_on_blocked: Boolean(qs("#orchestrationStopOnBlocked")?.checked),
  };
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Starting execution", `${payload.max_iterations} iterations`, "running"));
  try {
    const execution = await api(`/tasks/orchestrations/${encodeURIComponent(runId)}/executions`, {
      method: "POST",
      body: payload,
    });
    showToast("Background execution started.");
    target.append(jsonBlock(execution));
    await loadOrchestrationDetail(runId);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Execution start failed", error.message, "failed"));
  }
}

async function cancelOrchestrationExecution(runId, executionId) {
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Cancelling execution", executionId, "running"));
  try {
    const execution = await api(
      `/tasks/orchestrations/${encodeURIComponent(runId)}/executions/${encodeURIComponent(executionId)}/cancel`,
      { method: "POST" },
    );
    showToast("Background execution cancel requested.");
    target.append(jsonBlock(execution));
    await loadOrchestrationDetail(runId);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Execution cancel failed", error.message, "failed"));
  }
}

async function submitOrchestrationTaskUpdate(event, runId, taskId, form) {
  event.preventDefault();
  const status = form.querySelector('[name="status"]').value;
  const outputNote = form.querySelector('[name="output_note"]').value.trim();
  const errorText = form.querySelector('[name="error"]').value.trim();
  if ((status === "failed" || status === "blocked") && !errorText) {
    showToast("Failure or blocker reason is required.");
    return;
  }
  const payload = {
    status,
    output: outputNote ? { summary: outputNote } : {},
    error: errorText || null,
  };
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Updating task", taskId, "running"));
  try {
    const run = await api(
      `/tasks/orchestrations/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(taskId)}`,
      {
        method: "PATCH",
        body: payload,
      },
    );
    showToast("Task updated.");
    await loadOrchestrationDetail(run.id, run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Task update failed", error.message, "failed"));
  }
}

async function submitOrchestrationTaskRecovery(event, runId, taskId, form) {
  event.preventDefault();
  const resolution = form.querySelector('[name="resolution"]').value.trim();
  if (!resolution) {
    showToast("Resolution is required.");
    return;
  }
  const role = form.querySelector('[name="role"]').value.trim();
  const declaredWritePaths = splitLines(form.querySelector('[name="declared_write_paths"]').value);
  const payload = {
    resolution,
    reset_retry_count: Boolean(form.querySelector('[name="reset_retry_count"]').checked),
    declared_write_paths: declaredWritePaths,
  };
  if (role) {
    payload.role = role;
  }
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Recovering task", taskId, "running"));
  try {
    const run = await api(
      `/tasks/orchestrations/${encodeURIComponent(runId)}/tasks/${encodeURIComponent(taskId)}/recover`,
      {
        method: "POST",
        body: payload,
      },
    );
    showToast("Task recovery submitted.");
    await loadOrchestrationDetail(run.id, run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Task recovery failed", error.message, "failed"));
  }
}

async function submitOrchestrationBlockerResolution(event, runId, blockerId, form) {
  event.preventDefault();
  const resolution = form.querySelector('[name="resolution"]').value.trim();
  if (!resolution) {
    showToast("Resolution is required.");
    return;
  }
  const payload = {
    resolution,
    reschedule: Boolean(form.querySelector('[name="reschedule"]').checked),
  };
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Resolving blocker", blockerId, "running"));
  try {
    const run = await api(
      `/tasks/orchestrations/${encodeURIComponent(runId)}/blockers/${encodeURIComponent(blockerId)}/resolve`,
      {
        method: "POST",
        body: payload,
      },
    );
    showToast("Blocker resolved.");
    await loadOrchestrationDetail(run.id, run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Blocker resolution failed", error.message, "failed"));
  }
}

async function submitOrchestrationCloseout(event, runId, form) {
  event.preventDefault();
  const evidence = {};
  for (const input of Array.from(form.querySelectorAll('[name="evidence"]'))) {
    const key = input.dataset.evidenceKey;
    const value = input.value.trim();
    if (key && value) {
      evidence[key] = value;
    }
  }
  const target = qs("#orchestrationDetail");
  target.append(statusBox("Closing orchestration", runId, "running"));
  try {
    const run = await api(`/tasks/orchestrations/${encodeURIComponent(runId)}/close`, {
      method: "POST",
      body: { evidence },
    });
    showToast("Orchestration closed.");
    await loadOrchestrationDetail(run.id, run);
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Closeout failed", error.message, "failed"));
  }
}

async function createTaskPlan(event) {
  event.preventDefault();
  const objective = qs("#objectiveInput").value.trim();
  if (!objective) {
    showToast("Objective is required.");
    return;
  }
  const payload = {
    objective,
    constraints: splitLines(qs("#constraintsInput").value),
    acceptance_criteria: splitLines(qs("#acceptanceInput").value),
    priority: qs("#priorityInput").value,
  };
  const target = qs("#taskOutput");
  clear(target);
  target.append(statusBox("Creating plan", "Submitting task objective.", "running"));
  try {
    const plan = await api("/tasks/plan", { method: "POST", body: payload });
    clear(target);
    target.append(statusBox("Plan created", `${plan.id} - ${plan.steps?.length || 0} steps`, "ready"));
    target.append(jsonBlock(plan));
    qs("#taskForm").reset();
    await Promise.all([loadTasks(), loadTaskChatContext()]);
  } catch (error) {
    clear(target);
    target.append(statusBox("Plan failed", error.message, "failed"));
  }
}

function parseOrchestrationTasksInput() {
  const value = qs("#orchestrationTasksInput").value.trim();
  if (!value) {
    return [];
  }
  const tasks = JSON.parse(value);
  if (!Array.isArray(tasks)) {
    throw new Error("Tasks must be a JSON array.");
  }
  return tasks;
}

function writeOrchestrationTasksInput(tasks) {
  taskGraphBuilderTasks = tasks;
  qs("#orchestrationTasksInput").value = JSON.stringify(tasks, null, 2);
  renderOrchestrationTaskBuilderPreview();
}

function buildOrchestrationTaskDraft() {
  return {
    id: qs("#orchestrationTaskIdInput").value.trim(),
    title: qs("#orchestrationTaskTitleInput").value.trim(),
    description: qs("#orchestrationTaskDescriptionInput").value.trim(),
    role: qs("#orchestrationTaskRoleInput").value,
    dependencies: Array.from(qs("#orchestrationTaskDependencyList").selectedOptions).map((option) => option.value),
    declared_write_paths: splitLines(qs("#orchestrationTaskPathsInput").value),
    shared_memory_tags: splitLines(qs("#orchestrationTaskTagsInput").value),
    expected_output: qs("#orchestrationTaskOutputInput").value.trim(),
    validation: qs("#orchestrationTaskValidationInput").value.trim(),
    retry_limit: Number(qs("#orchestrationTaskRetryInput").value || 0),
  };
}

function validateOrchestrationTaskDraft(task, tasks) {
  if (!task.id || !task.title || !task.description) {
    throw new Error("Task ID, title, and description are required.");
  }
  if (tasks.some((item) => item.id === task.id)) {
    throw new Error("Task ID already exists in the graph.");
  }
  if (task.retry_limit < 0 || task.retry_limit > 10) {
    throw new Error("Retry limit must be between 0 and 10.");
  }
  const existingIds = new Set(tasks.map((item) => item.id));
  const unknownDependencies = task.dependencies.filter((dependency) => !existingIds.has(dependency));
  if (unknownDependencies.length) {
    throw new Error(`Unknown dependencies: ${unknownDependencies.join(", ")}`);
  }
}

function resetOrchestrationTaskDraft() {
  qs("#orchestrationTaskIdInput").value = "";
  qs("#orchestrationTaskTitleInput").value = "";
  qs("#orchestrationTaskDescriptionInput").value = "";
  qs("#orchestrationTaskRoleInput").value = "Developer";
  qs("#orchestrationTaskPathsInput").value = "";
  qs("#orchestrationTaskOutputInput").value = "";
  qs("#orchestrationTaskValidationInput").value = "";
  qs("#orchestrationTaskTagsInput").value = "";
  qs("#orchestrationTaskRetryInput").value = "0";
  for (const option of qs("#orchestrationTaskDependencyList").options) {
    option.selected = false;
  }
}

function showOrchestrationBuilderError(message) {
  const target = qs("#orchestrationCreateOutput");
  clear(target);
  target.append(statusBox("Task graph invalid", message, "failed"));
  showToast(message);
}

function addOrchestrationTaskDraft() {
  let tasks = [];
  try {
    tasks = parseOrchestrationTasksInput();
    const task = buildOrchestrationTaskDraft();
    validateOrchestrationTaskDraft(task, tasks);
    writeOrchestrationTasksInput([...tasks, task]);
    resetOrchestrationTaskDraft();
    showToast("Task added to graph.");
  } catch (error) {
    showOrchestrationBuilderError(error.message);
  }
}

function removeOrchestrationTaskDraft(taskId) {
  let tasks = [];
  try {
    tasks = parseOrchestrationTasksInput()
      .filter((task) => task.id !== taskId)
      .map((task) => ({
        ...task,
        dependencies: (task.dependencies || []).filter((dependency) => dependency !== taskId),
      }));
    writeOrchestrationTasksInput(tasks);
    showToast("Task removed from graph.");
  } catch (error) {
    showOrchestrationBuilderError(error.message);
  }
}

function renderOrchestrationTaskDependencyOptions(tasks) {
  const target = qs("#orchestrationTaskDependencyList");
  const selected = new Set(Array.from(target.selectedOptions).map((option) => option.value));
  clear(target);
  for (const task of tasks) {
    const option = document.createElement("option");
    option.value = task.id;
    option.textContent = `${task.id} - ${task.title || task.role}`;
    option.selected = selected.has(task.id);
    target.append(option);
  }
}

function renderOrchestrationTaskBuilderPreview() {
  const target = qs("#orchestrationTaskBuilderPreview");
  clear(target);
  let tasks = [];
  try {
    tasks = parseOrchestrationTasksInput();
  } catch (error) {
    renderOrchestrationTaskDependencyOptions([]);
    target.append(statusBox("Task graph invalid", error.message, "failed"));
    return;
  }
  taskGraphBuilderTasks = tasks;
  renderOrchestrationTaskDependencyOptions(tasks);
  if (!tasks.length) {
    target.append(statusBox("No builder tasks", "Add tasks here or paste JSON below.", "pending"));
    return;
  }
  for (const task of tasks) {
    const row = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", `${task.id} - ${task.title || "Untitled task"}`));
    detail.append(
      make(
        "div",
        "item-meta",
        `${task.role || "Unassigned"} - depends on ${(task.dependencies || []).join(", ") || "none"} - paths ${(task.declared_write_paths || []).join(", ") || "read-only"}`,
      ),
    );
    const removeButton = make("button", "link-button", "Remove");
    removeButton.type = "button";
    removeButton.addEventListener("click", () => removeOrchestrationTaskDraft(task.id));
    row.append(detail, removeButton);
    target.append(row);
  }
}

function loadOrchestrationTaskBuilderJson() {
  try {
    taskGraphBuilderTasks = parseOrchestrationTasksInput();
    renderOrchestrationTaskBuilderPreview();
    showToast("Task graph loaded into builder.");
  } catch (error) {
    showOrchestrationBuilderError(error.message);
  }
}

function setupOrchestrationTaskBuilder() {
  qs("#orchestrationTaskAddButton").addEventListener("click", addOrchestrationTaskDraft);
  qs("#orchestrationTaskClearButton").addEventListener("click", () => {
    resetOrchestrationTaskDraft();
    showToast("Task draft cleared.");
  });
  qs("#orchestrationTaskLoadJsonButton").addEventListener("click", loadOrchestrationTaskBuilderJson);
  qs("#orchestrationTasksInput").addEventListener("input", renderOrchestrationTaskBuilderPreview);
  renderOrchestrationTaskBuilderPreview();
}

async function createOrchestrationRun(event) {
  event.preventDefault();
  const objective = qs("#orchestrationObjectiveInput").value.trim();
  const target = qs("#orchestrationCreateOutput");
  if (!objective) {
    showToast("Objective is required.");
    return;
  }
  let tasks = [];
  try {
    tasks = parseOrchestrationTasksInput();
  } catch (error) {
    clear(target);
    target.append(statusBox("Task graph invalid", error.message, "failed"));
    return;
  }
  if (!Array.isArray(tasks) || !tasks.length) {
    clear(target);
    target.append(statusBox("Task graph invalid", "Tasks must be a non-empty JSON array.", "failed"));
    return;
  }
  const payload = {
    objective,
    tasks,
    required_dod_evidence: splitLines(qs("#orchestrationEvidenceInput").value),
    shared_memory_tags: splitLines(qs("#orchestrationSharedTagsInput").value),
    shared_memory_policy: qs("#orchestrationMemoryPolicyInput").value,
  };
  clear(target);
  target.append(statusBox("Creating orchestration", objective, "running"));
  try {
    const run = await api("/tasks/orchestrations", { method: "POST", body: payload });
    selectedOrchestrationId = run.id;
    clear(target);
    target.append(statusBox("Orchestration created", run.id, run.status));
    qs("#orchestrationCreateForm").reset();
    writeOrchestrationTasksInput([]);
    resetOrchestrationTaskDraft();
    await Promise.all([loadTasks(), loadTaskChatContext()]);
    await loadOrchestrationDetail(run.id, run);
  } catch (error) {
    clear(target);
    target.append(statusBox("Orchestration create failed", error.message, "failed"));
  }
}

async function loadApprovals() {
  const selectedSources = approvalSource
    ? approvalSources.filter((source) => source.key === approvalSource)
    : approvalSources;
  const loads = selectedSources.map(async (source) => {
    const suffix = approvalStatus ? `?status=${encodeURIComponent(approvalStatus)}` : "";
    const result = await safeLoad(source.label, () => api(`${source.base}${suffix}`));
    return { source, ...result };
  });
  const results = await Promise.all(loads);
  const approvals = [];
  const errors = [];
  for (const result of results) {
    if (result.ok) {
      for (const approval of result.data) {
        approvals.push({ source: result.source, approval });
      }
    } else {
      errors.push(result);
    }
  }
  setMetric("#approvalsMetric", String(approvals.length));
  setMetric("#approvalScopeMetric", `${approvalStatusLabel()} - ${approvalSourceLabel()}`);
  renderApprovalList(approvals, errors);
}

function approvalTitle(item) {
  const approval = item.approval;
  return (
    approval.command ||
    approval.path ||
    approval.url ||
    approval.provider_id ||
    approval.tool_name ||
    approval.name ||
    approval.id
  );
}

function approvalMeta(item) {
  const approval = item.approval;
  const bits = [item.source.label, approval.requested_by, approval.created_at].filter(Boolean);
  return bits.join(" - ");
}

function renderApprovalList(items, errors) {
  const target = qs("#approvalList");
  clear(target);
  renderApprovalSummary(target, items, errors);
  for (const error of errors) {
    target.append(statusBox(`${error.source.label} unavailable`, error.error, "blocked"));
  }
  if (!items.length && !errors.length) {
    target.append(statusBox("Inbox clear", "No approvals match the current filter.", "ok"));
    return;
  }
  for (const item of items) {
    const row = make("div", "approval-item");
    const copy = make("div");
    copy.append(make("div", "item-title", approvalTitle(item)));
    copy.append(make("div", "item-meta", approvalMeta(item)));
    copy.append(statusChip(item.approval.status));
    const button = make("button", "link-button", "Review");
    button.type = "button";
    button.addEventListener("click", () => reviewApproval(item));
    row.append(copy, button);
    target.append(row);
  }
}

function renderApprovalSummary(target, items, errors) {
  const grid = make("div", "approval-summary-grid");
  const counts = {};
  for (const item of items) {
    const status = item.approval.status || "unknown";
    counts[status] = (counts[status] || 0) + 1;
  }
  appendKeyValue(grid, "Status", approvalStatusLabel());
  appendKeyValue(grid, "Source", approvalSourceLabel());
  appendKeyValue(grid, "Loaded", String(items.length));
  appendKeyValue(grid, "Errors", String(errors.length), errors.length ? "blocked" : "ok");
  if (items.length) {
    appendKeyValue(grid, "Breakdown", countsText(counts));
  }
  target.append(grid);
}

async function reviewApproval(item) {
  selectedApproval = item;
  const target = qs("#approvalReview");
  clear(target);
  target.append(statusBox("Loading review", `${item.source.label} ${item.approval.id}`, "running"));
  try {
    const review = await api(`${item.source.base}/${encodeURIComponent(item.approval.id)}/review`);
    selectedApproval = { ...item, review };
    renderApprovalReview(selectedApproval);
  } catch (error) {
    clear(target);
    target.append(statusBox("Review unavailable", error.message, "blocked"));
  }
}

function renderApprovalReview(item) {
  const target = qs("#approvalReview");
  clear(target);
  const header = statusBox(`${item.source.label} review`, item.approval.id, item.approval.status);
  target.append(header);
  renderApprovalReviewSummary(target, item);

  const details = make("details", "json-details");
  details.append(make("summary", "", "Raw review"));
  details.append(jsonBlock(item.review));
  target.append(details);

  const form = make("form", "decision-form");
  const reason = make("input");
  reason.type = "text";
  reason.placeholder = "Reason";
  const approve = make("button", "success-button", "Approve");
  approve.type = "submit";
  approve.dataset.decision = "approve";
  const deny = make("button", "danger-button", "Deny");
  deny.type = "submit";
  deny.dataset.decision = "deny";
  form.append(reason, approve, deny);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    decideApproval(submitter.dataset.decision, reason.value.trim());
  });
  target.append(form);
  renderApprovalExecutionControls(target, item);
}

function renderApprovalExecutionControls(target, item) {
  if (item.approval.status !== "approved") {
    return;
  }
  if (item.source.key === "cli") {
    const canExecute = item.review.direct_execute_available !== false;
    const executeButton = make("button", "primary-button", "Execute approved command");
    executeButton.type = "button";
    executeButton.disabled = !canExecute;
    executeButton.addEventListener("click", () => executeCliApproval(item.approval.id));
    target.append(executeButton);
    if (!canExecute) {
      target.append(
        statusBox(
          "Bound execution required",
          "This approval needs an execution request with matching bound fields.",
          "blocked",
        ),
      );
    }
    return;
  }
  renderBoundExecutionRequestPanel(target, item);
}

function renderBoundExecutionRequestPanel(target, item) {
  const scaffold = boundExecutionRequestScaffold(item);
  if (!scaffold) {
    return;
  }
  const panel = make("div", "bound-execution-panel");
  panel.append(statusBox("Bound execution request", `${scaffold.method} ${scaffold.endpoint}`, "pending"));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Source", item.source.label);
  appendKeyValue(grid, "Approval", item.approval.id);
  appendKeyValue(grid, "Direct execution", item.review.direct_execute_available ? "Available" : "Not available");
  appendKeyValue(grid, "Requires bound request", item.review.requires_bound_execution_request ? "Yes" : "No");
  appendKeyValue(grid, "Dashboard execute", scaffold.executable === false ? "Not available" : "Available");
  panel.append(grid);

  if (scaffold.notes.length) {
    const notes = make("div", "review-warning-list");
    notes.append(make("div", "item-title", "Execution notes"));
    for (const note of scaffold.notes) {
      const row = make("div", "finding-row");
      row.append(statusChip("pending"), make("span", "", note));
      notes.append(row);
    }
    panel.append(notes);
  }

  const details = make("details", "json-details");
  details.open = true;
  details.append(make("summary", "", "Payload scaffold"));
  details.append(jsonBlock(scaffold.payload));
  const editor = make("label", "bound-execution-editor");
  editor.append(make("span", "", "Editable Payload"));
  const textarea = make("textarea");
  textarea.id = "boundExecutionPayloadInput";
  textarea.rows = 10;
  textarea.spellcheck = false;
  textarea.value = JSON.stringify(scaffold.payload, null, 2);
  editor.append(textarea);
  const guidedFields = renderBoundExecutionGuidedFields(scaffold, textarea);
  const buttons = make("div", "recipe-action-buttons");
  const copyButton = make("button", "link-button", "Copy Payload");
  copyButton.type = "button";
  copyButton.addEventListener("click", () => copyBoundExecutionPayload(scaffold));
  const executeButton = make("button", "primary-button", "Execute Request");
  executeButton.id = "boundExecutionExecuteButton";
  executeButton.type = "button";
  executeButton.disabled = scaffold.executable === false;
  executeButton.addEventListener("click", () => executeBoundExecutionRequest(scaffold));
  buttons.append(copyButton, executeButton);
  const output = make("div", "output-region");
  output.id = "boundExecutionOutput";
  output.setAttribute("aria-live", "polite");
  panel.append(details, guidedFields, editor, buttons, output);
  target.append(panel);
}

function renderBoundExecutionGuidedFields(scaffold, textarea) {
  const payload = scaffold.payload || {};
  const fields = Object.entries(payload);
  const box = make("div", "bound-execution-guided-fields");
  box.append(make("div", "item-title", "Guided Fields"));
  if (!fields.length) {
    box.append(statusBox("No guided fields", "Edit the JSON payload directly.", "pending"));
    return box;
  }
  for (const [field, value] of fields) {
    renderBoundExecutionGuidedField(box, scaffold, [field], value, textarea);
  }
  return box;
}

function renderBoundExecutionGuidedField(target, scaffold, path, value, textarea) {
  if (isGuidedNestedValue(value)) {
    renderBoundExecutionGuidedGroup(target, scaffold, path, value, textarea);
    return;
  }
  const field = path[path.length - 1];
  const pathText = boundExecutionPayloadPathLabel(path);
  const row = make("label", "bound-execution-guided-field");
  const header = make("span", "", pathText);
  row.append(header);
  const control = boundExecutionGuidedFieldControl(field, value);
  control.dataset.boundPayloadField = field;
  control.dataset.boundPayloadPath = pathText;
  if (isBoundExecutionLockedPath(scaffold, path)) {
    control.disabled = true;
    control.title = "Bound approval fields are locked in guided editing.";
    row.append(control, make("small", "", "Bound field"));
    target.append(row);
    return;
  }
  const eventName = control.type === "checkbox" ? "change" : "input";
  control.addEventListener(eventName, () => {
    syncBoundExecutionGuidedField(path, control, value, textarea);
  });
  row.append(control);
  target.append(row);
}

function renderBoundExecutionGuidedGroup(target, scaffold, path, value, textarea) {
  const group = make("details", "bound-execution-guided-group");
  group.open = path.length <= 2;
  const entries = Array.isArray(value)
    ? value.map((item, index) => [index, item])
    : Object.entries(value || {});
  group.append(make("summary", "", boundExecutionPayloadPathLabel(path)));
  const body = make("div", "bound-execution-guided-group-body");
  if (!entries.length) {
    body.append(statusBox("Empty nested value", "Edit the JSON payload directly.", "pending"));
  }
  for (const [field, nestedValue] of entries) {
    renderBoundExecutionGuidedField(body, scaffold, [...path, field], nestedValue, textarea);
  }
  group.append(body);
  target.append(group);
}

function isGuidedNestedValue(value) {
  return Boolean(value && typeof value === "object");
}

function isBoundExecutionLockedPath(scaffold, path) {
  return path.length === 1 && scaffold.binding?.field === path[0];
}

function boundExecutionPayloadPathLabel(path) {
  return path.map((part) => String(part).replaceAll("_", " ")).join(".");
}

function boundExecutionGuidedFieldControl(field, value) {
  const fieldName = String(field);
  if (typeof value === "boolean") {
    const input = make("input");
    input.type = "checkbox";
    input.checked = value;
    return input;
  }
  if (typeof value === "number") {
    const input = make("input");
    input.type = "number";
    input.value = String(value);
    return input;
  }
  if (value && typeof value === "object") {
    const input = make("textarea");
    input.rows = Array.isArray(value) ? 5 : 4;
    input.spellcheck = false;
    input.value = JSON.stringify(value, null, 2);
    return input;
  }
  const stringValue = value === undefined || value === null ? "" : String(value);
  if (stringValue.length > 80 || fieldName.includes("content") || fieldName.includes("body")) {
    const input = make("textarea");
    input.rows = 3;
    input.value = stringValue;
    return input;
  }
  const input = make("input");
  input.type = "text";
  input.value = stringValue;
  return input;
}

function syncBoundExecutionGuidedField(path, control, sampleValue, textarea) {
  let payload = {};
  try {
    payload = boundExecutionPayloadFromText(textarea.value);
  } catch (_error) {
    showToast("Fix payload JSON before syncing guided fields.");
    return;
  }
  let value;
  try {
    value = boundExecutionGuidedFieldValue(control, sampleValue);
  } catch (error) {
    showToast(error.message);
    return;
  }
  setBoundExecutionPayloadPathValue(payload, path, value);
  textarea.value = JSON.stringify(payload, null, 2);
}

function setBoundExecutionPayloadPathValue(payload, path, value) {
  let current = payload;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    const nextKey = path[index + 1];
    if (!current[key] || typeof current[key] !== "object") {
      current[key] = typeof nextKey === "number" ? [] : {};
    }
    current = current[key];
  }
  current[path[path.length - 1]] = value;
}

function boundExecutionGuidedFieldValue(control, sampleValue) {
  if (control.type === "checkbox") {
    return control.checked;
  }
  if (control.type === "number") {
    const value = Number(control.value);
    if (!Number.isFinite(value)) {
      throw new Error("Guided numeric field is invalid.");
    }
    return value;
  }
  if (sampleValue && typeof sampleValue === "object") {
    try {
      return JSON.parse(control.value || (Array.isArray(sampleValue) ? "[]" : "{}"));
    } catch (error) {
      throw new Error(`Guided field JSON invalid: ${error.message}`);
    }
  }
  return control.value;
}

function addApprovalContextFields(payload, review) {
  for (const key of ["requested_by", "agent_id", "agent_role", "task_id"]) {
    if (review[key]) {
      payload[key] = review[key];
    }
  }
  return payload;
}

function boundExecutionRequestScaffold(item) {
  const review = item.review || {};
  const basePayload = addApprovalContextFields({ approval_id: item.approval.id }, review);
  if (item.source.key === "filesystem") {
    return filesystemBoundExecutionScaffold(review, basePayload);
  }
  if (item.source.key === "network") {
    return networkBoundExecutionScaffold(review, basePayload);
  }
  if (item.source.key === "provider") {
    return providerBoundExecutionScaffold(review, basePayload);
  }
  if (item.source.key === "tool") {
    return toolBoundExecutionScaffold(review, basePayload);
  }
  return null;
}

function filesystemBoundExecutionScaffold(review, basePayload) {
  const endpoints = {
    read: "/filesystem/read",
    write: "/filesystem/write",
    binary_read: "/filesystem/read-binary",
    binary_write: "/filesystem/write-binary",
    delete: "/filesystem/delete",
    move: "/filesystem/move",
    copy: "/filesystem/copy",
    rename: "/filesystem/rename",
    metadata: "/filesystem/metadata",
    list: "/filesystem/list",
  };
  const action = review.action || "read";
  const payload = { ...basePayload, path: review.path || "." };
  const notes = [];
  if (action === "write") {
    payload.content = "<original approved content>";
    payload.create_parent_dirs = review.create_parent_dirs !== false;
    notes.push("Write approvals require the original approved content; it is not stored in the review.");
  } else if (action === "binary_write") {
    payload.content_base64 = "<original approved base64 content>";
    payload.create_parent_dirs = review.create_parent_dirs !== false;
    notes.push("Binary write approvals require the original approved base64 content; it is not stored in the review.");
  } else if (action === "delete") {
    payload.recursive = Boolean(review.recursive);
  } else if (action === "move") {
    payload.target_path = review.target_path || "<approved target path>";
    payload.overwrite = Boolean(review.overwrite);
  } else if (action === "copy") {
    payload.target_path = review.target_path || "<approved target path>";
    payload.overwrite = Boolean(review.overwrite);
    payload.recursive = Boolean(review.recursive);
  } else if (action === "rename") {
    payload.new_name = review.target_path ? String(review.target_path).split(/[\\/]/).pop() : "<approved new name>";
    payload.overwrite = Boolean(review.overwrite);
  }
  return {
    method: "POST",
    endpoint: endpoints[action] || "/filesystem/read",
    executable: true,
    binding: { field: "approval_id", value: basePayload.approval_id },
    payload,
    notes,
  };
}

function networkBoundExecutionScaffold(review, basePayload) {
  const webRetrieval = review.surface === "web_retrieval" || review.action === "fetch";
  if (!webRetrieval) {
    const { approval_id, ...context } = basePayload;
    return {
      method: "POST",
      endpoint: "<provider/tool execution endpoint>",
      executable: false,
      binding: { field: "network_approval_id", value: approval_id },
      payload: {
        ...context,
        network_approval_id: approval_id,
        url: review.url || "<approved URL>",
      },
      notes: ["Provider and tool network approvals are consumed as network_approval_id in the matching provider/tool execution request."],
    };
  }
  return {
    method: "POST",
    endpoint: "/web-retrieval/fetch",
    executable: true,
    binding: { field: "approval_id", value: basePayload.approval_id },
    payload: {
      ...basePayload,
      url: review.url || "<approved URL>",
      timeout_seconds: 30,
      max_response_bytes: 65536,
    },
    notes: ["Web retrieval approvals are consumed by the fetch request."],
  };
}

function providerBoundExecutionScaffold(review, basePayload) {
  const messages = review.review_messages?.length
    ? review.review_messages.map((message) => ({
        role: message.role || "user",
        content: "<original approved message content>",
      }))
    : [{ role: "user", content: "<original approved message content>" }];
  const options = {};
  for (const key of review.option_keys || []) {
    options[key] = "<original approved option value>";
  }
  return {
    method: "POST",
    endpoint: review.stream ? "/providers/generate/stream" : "/providers/generate",
    executable: true,
    binding: { field: "approval_id", value: basePayload.approval_id },
    payload: {
      ...basePayload,
      provider_id: review.provider_id || "<provider id>",
      model: review.model || "<model>",
      messages,
      network_approval_id: null,
      stream: Boolean(review.stream),
      temperature: review.temperature ?? undefined,
      max_tokens: review.max_tokens ?? undefined,
      options,
      timeout_seconds: review.timeout_seconds || 30,
    },
    notes: ["Provider approvals require the original approved message and option values; reviews expose safe metadata only."],
  };
}

function toolBoundExecutionScaffold(review, basePayload) {
  return {
    method: "POST",
    endpoint: `/tools/${encodeURIComponent(review.tool_name || "<tool>")}/execute`,
    executable: true,
    binding: { field: "approval_id", value: basePayload.approval_id },
    payload: {
      ...basePayload,
      payload: review.review_payload || {},
      network_approval_id: null,
      timeout_seconds: review.timeout_seconds || 30,
    },
    notes: ["Tool approvals require the exact approved payload; redacted review payloads may need original values restored."],
  };
}

async function copyBoundExecutionPayload(scaffold) {
  const text = JSON.stringify({ method: scaffold.method, endpoint: scaffold.endpoint, payload: scaffold.payload }, null, 2);
  await copyTextToClipboard(text, "Bound payload copied.");
}

function boundExecutionPayloadFromEditor() {
  return boundExecutionPayloadFromText(qs("#boundExecutionPayloadInput").value);
}

function boundExecutionPayloadFromText(rawValue) {
  const value = rawValue.trim();
  if (!value) {
    throw new Error("Payload JSON is required.");
  }
  const payload = JSON.parse(value);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Payload JSON must be an object.");
  }
  return payload;
}

function validateBoundExecutionPayload(scaffold, payload) {
  const binding = scaffold.binding || {};
  if (!binding.field || !binding.value) {
    return;
  }
  if (payload[binding.field] !== binding.value) {
    throw new Error(`${binding.field} must match the approved request.`);
  }
}

async function executeBoundExecutionRequest(scaffold) {
  const output = qs("#boundExecutionOutput");
  const button = qs("#boundExecutionExecuteButton");
  clear(output);
  if (scaffold.executable === false) {
    output.append(statusBox("Bound execution handoff only", "Use the copied payload in the matching provider or tool request.", "blocked"));
    return;
  }
  let payload = {};
  try {
    payload = boundExecutionPayloadFromEditor();
    validateBoundExecutionPayload(scaffold, payload);
  } catch (error) {
    output.append(statusBox("Payload JSON invalid", error.message, "failed"));
    showToast(error.message);
    return;
  }
  button.disabled = true;
  output.append(statusBox("Executing bound request", `${scaffold.method} ${scaffold.endpoint}`, "running"));
  try {
    const result = await api(scaffold.endpoint, { method: scaffold.method, body: payload });
    clear(output);
    output.append(statusBox("Bound request executed", scaffold.endpoint, "ready"));
    output.append(jsonBlock(result));
    await Promise.all([loadApprovals(), loadTaskChatContext()]);
    showToast("Bound request executed.");
  } catch (error) {
    button.disabled = false;
    clear(output);
    output.append(statusBox("Bound execution failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function copyTextToClipboard(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage);
  } catch (_error) {
    showToast("Copy unavailable in this browser context.");
  }
}

function renderApprovalReviewSummary(target, item) {
  const review = item.review || item.approval || {};
  const box = make("div", "approval-review-summary");
  box.append(make("div", "item-title", "Review Summary"));
  const grid = make("div", "checkpoint-grid");
  for (const pair of approvalReviewPairs(item)) {
    appendKeyValue(grid, pair.label, reviewValue(pair.value), pair.chip || "");
  }
  box.append(grid);
  renderReviewWarnings(box, review.review_warnings || []);
  target.append(box);
}

function approvalReviewPairs(item) {
  const review = item.review || item.approval || {};
  const pairs = [
    { label: "Status", value: review.status || item.approval.status, chip: review.status || item.approval.status },
    { label: "Permission", value: review.permission_mode },
    { label: "Policy reason", value: review.policy_reason },
    { label: "Requested by", value: review.requested_by },
    { label: "Agent role", value: review.agent_role },
    { label: "Task", value: review.task_id },
    {
      label: "Bound execution",
      value: review.requires_bound_execution_request ? "Required" : "Not required",
      chip: review.requires_bound_execution_request ? "pending" : "ok",
    },
    {
      label: "Direct execution",
      value: review.direct_execute_available ? "Available" : "Not available",
      chip: review.direct_execute_available ? "ok" : "blocked",
    },
    { label: "Expires", value: formatTimestamp(review.expires_at) },
  ];

  if (review.decided_by || review.decision_reason || review.denial_reason) {
    pairs.push(
      { label: "Decided by", value: review.decided_by },
      { label: "Decision reason", value: review.decision_reason || review.denial_reason },
    );
  }
  if (review.executed_at) {
    pairs.push({ label: "Executed", value: formatTimestamp(review.executed_at), chip: "ok" });
  }

  if (item.source.key === "cli") {
    pairs.splice(
      1,
      0,
      { label: "Command", value: review.review_command },
      { label: "Working directory", value: review.cwd },
      { label: "Timeout", value: `${review.timeout_seconds || "-"} seconds` },
      { label: "Matched rule", value: review.matched_rule_name || review.matched_rule_id },
      { label: "Environment keys", value: review.environment_keys },
      { label: "Workflow binding", value: workflowBindingSummary(review.workflow_binding) },
      { label: "Command digest", value: review.command_digest },
      { label: "Run", value: review.run_id },
    );
  } else if (item.source.key === "filesystem") {
    pairs.splice(
      1,
      0,
      { label: "Action", value: review.action },
      { label: "Path", value: review.path },
      { label: "Target path", value: review.target_path },
      { label: "Options", value: filesystemApprovalOptions(review) },
      { label: "Approval digest", value: review.approval_digest },
    );
  } else if (item.source.key === "network") {
    pairs.splice(
      1,
      0,
      { label: "URL", value: review.url },
      { label: "Surface", value: review.surface },
      { label: "Action", value: review.action },
      { label: "Host", value: review.port ? `${review.host}:${review.port}` : review.host },
      { label: "Matched domain", value: review.matched_domain },
      { label: "Approval digest", value: review.approval_digest },
    );
  } else if (item.source.key === "provider") {
    pairs.splice(
      1,
      0,
      { label: "Provider", value: review.provider_id },
      { label: "Model", value: review.model },
      { label: "Messages", value: providerMessageSummary(review) },
      { label: "Options", value: review.option_keys },
      { label: "Stream", value: review.stream ? "Yes" : "No" },
      { label: "Approval digest", value: review.approval_digest },
    );
  } else if (item.source.key === "tool") {
    pairs.splice(
      1,
      0,
      { label: "Tool", value: review.tool_name },
      { label: "Version", value: review.tool_version },
      { label: "Tool status", value: review.tool_status, chip: review.tool_status },
      { label: "Entrypoint", value: review.entrypoint },
      { label: "Payload digest", value: review.payload_digest },
      { label: "Approval digest", value: review.approval_digest },
    );
  }
  return pairs.filter((pair) => pair.value !== undefined && pair.value !== null && pair.value !== "");
}

function filesystemApprovalOptions(review) {
  return [
    review.recursive ? "recursive" : "",
    review.overwrite ? "overwrite" : "",
    review.create_parent_dirs === false ? "no parent creation" : "",
  ]
    .filter(Boolean)
    .join(", ");
}

function providerMessageSummary(review) {
  const messages = review.review_messages || [];
  if (!messages.length) {
    return `${review.message_count || 0} messages`;
  }
  return messages.map((message) => `${message.role || "message"}:${message.content_length || 0}`).join(", ");
}

function workflowBindingSummary(binding) {
  if (!binding || !Object.keys(binding).length) {
    return "";
  }
  const type = binding.type || "bound";
  const digest = binding.checkpoint_digest || binding.approval_digest || binding.digest || "";
  return digest ? `${type} ${String(digest).slice(0, 16)}` : type;
}

function renderReviewWarnings(target, warnings) {
  if (!warnings.length) {
    return;
  }
  const box = make("div", "review-warning-list");
  box.append(make("div", "item-title", "Review warnings"));
  for (const warning of warnings) {
    const row = make("div", "finding-row");
    row.append(statusChip("pending"), make("span", "", warning));
    box.append(row);
  }
  target.append(box);
}

async function decideApproval(decision, reason) {
  if (!selectedApproval) {
    return;
  }
  const { source, approval } = selectedApproval;
  try {
    const result = await api(`${source.base}/${encodeURIComponent(approval.id)}/${decision}`, {
      method: "POST",
      body: reason ? { reason } : {},
    });
    const verb = decision === "approve" ? "approved" : "denied";
    showToast(`${source.label} approval ${verb}.`);
    const review = await api(`${source.base}/${encodeURIComponent(result.id || approval.id)}/review`);
    selectedApproval = { source, approval: result, review };
    renderApprovalReview(selectedApproval);
    await Promise.all([loadApprovals(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
  }
}

async function executeCliApproval(approvalId) {
  const target = qs("#approvalReview");
  target.append(statusBox("Executing approved command", approvalId, "running"));
  try {
    const result = await api(`/cli/approvals/${encodeURIComponent(approvalId)}/execute`, {
      method: "POST",
    });
    showToast("CLI approval executed.");
    target.append(jsonBlock(result));
    await Promise.all([loadApprovals(), loadCliRuns(), loadTaskChatContext()]);
  } catch (error) {
    showToast(error.message);
    target.append(statusBox("Execution failed", error.message, "failed"));
  }
}

function gitCheckpointPayload() {
  const payload = {
    action: qs("#gitActionInput").value,
    test_evidence: splitLines(qs("#gitEvidenceInput").value),
  };
  const cwd = qs("#gitCwdInput").value.trim();
  if (cwd) {
    payload.cwd = cwd;
  }
  return payload;
}

async function createGitCheckpoint(event) {
  event.preventDefault();
  const payload = gitCheckpointPayload();
  const target = qs("#gitOutput");
  latestGitCheckpoint = null;
  latestGitCheckpointRequest = payload;
  latestGitDiffReview = null;
  latestGitChangeReviewArtifacts = [];
  gitDiffReviewDecisions = {};
  renderGitApprovalActions(null);
  clear(target);
  target.append(statusBox("Checking repository", payload.action, "running"));
  try {
    const checkpoint = await api("/cli/git/checkpoints", { method: "POST", body: payload });
    checkpoint.review_evidence_count = payload.test_evidence.length;
    latestGitCheckpoint = checkpoint;
    latestGitCheckpointRequest = payload;
    renderGitCheckpoint(checkpoint);
  } catch (error) {
    latestGitCheckpoint = null;
    clear(target);
    target.append(statusBox("Checkpoint failed", error.message, "failed"));
    latestGitChangeReviewArtifacts = [];
    gitDiffReviewDecisions = {};
    renderGitApprovalActions(null);
  }
}

function renderGitCheckpoint(checkpoint) {
  const target = qs("#gitOutput");
  clear(target);
  target.append(
    statusBox(
      checkpoint.ready ? "Checkpoint ready" : "Checkpoint blocked",
      `${checkpoint.action} on ${checkpoint.branch}`,
      checkpoint.ready ? "ready" : "blocked",
    ),
  );

  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Branch", checkpoint.branch || "-");
  appendKeyValue(grid, "Head", checkpoint.head_sha ? checkpoint.head_sha.slice(0, 12) : "-");
  appendKeyValue(grid, "Upstream", checkpoint.upstream || "-");
  appendKeyValue(grid, "Ahead / behind", `${checkpoint.ahead || 0} / ${checkpoint.behind || 0}`);
  appendKeyValue(grid, "Staged", String(checkpoint.staged_count || 0));
  appendKeyValue(grid, "Unstaged", String(checkpoint.unstaged_count || 0));
  appendKeyValue(grid, "Untracked", String(checkpoint.untracked_count || 0));
  appendKeyValue(grid, "Diff", checkpoint.diff_stat?.summary || "No tracked diff changes.");
  target.append(grid);

  renderGitReviewSummary(target, checkpoint);
  renderFindings(target, "Blockers", checkpoint.blockers || [], "blocked");
  renderFindings(target, "Warnings", checkpoint.warnings || [], "pending");
  renderChangedPaths(target, checkpoint);
  renderGitDiffReviewPanel(target, checkpoint);

  const details = make("details", "json-details");
  details.append(make("summary", "", "Raw checkpoint"));
  details.append(jsonBlock(checkpoint));
  target.append(details);
  renderGitApprovalActions(checkpoint);
}

function renderGitReviewSummary(target, checkpoint) {
  const box = make("div", "git-review-summary");
  box.append(make("div", "item-title", "AI change review"));
  const grid = make("div", "checkpoint-grid");
  const diffStat = checkpoint.diff_stat || {};
  const pathCount = (checkpoint.changed_paths || []).length;
  const pathSuffix = checkpoint.changed_paths_truncated ? "+" : "";
  const evidenceCount =
    checkpoint.review_evidence_count === undefined ? "-" : String(checkpoint.review_evidence_count);
  appendKeyValue(grid, "Readiness", checkpoint.ready ? "Ready" : "Blocked", checkpoint.ready ? "ready" : "blocked");
  appendKeyValue(
    grid,
    "Diff stat",
    `${diffStat.files_changed || 0} files | +${diffStat.insertions || 0} / -${diffStat.deletions || 0}`,
  );
  appendKeyValue(grid, "Review paths", `${pathCount}${pathSuffix}`);
  appendKeyValue(grid, "Evidence lines", evidenceCount);
  appendKeyValue(
    grid,
    "Checkpoint digest",
    checkpoint.checkpoint_digest ? checkpoint.checkpoint_digest.slice(0, 16) : "-",
  );
  appendKeyValue(grid, "Action", checkpoint.action || "-");
  box.append(grid);
  target.append(box);
}

function renderFindings(target, title, findings, state) {
  if (!findings.length) {
    return;
  }
  const box = make("div", "finding-list");
  box.append(make("div", "item-title", title));
  for (const finding of findings) {
    const row = make("div", "finding-row");
    row.append(statusChip(state), make("span", "", finding));
    box.append(row);
  }
  target.append(box);
}

function renderChangedPaths(target, checkpoint) {
  const paths = checkpoint.changed_paths || [];
  if (!paths.length) {
    return;
  }
  const box = make("div", "changed-paths");
  const title = checkpoint.changed_paths_truncated ? "Changed paths (truncated)" : "Changed paths";
  box.append(make("div", "item-title", title));
  for (const path of paths.slice(0, 12)) {
    box.append(make("code", "", path));
  }
  target.append(box);
}

function renderGitDiffReviewPanel(target, checkpoint) {
  const panel = make("div", "git-diff-review");
  const header = make("div", "builder-row");
  const copy = make("div");
  copy.append(make("div", "item-title", "Raw diff review"));
  copy.append(make("div", "item-meta", "Checkpoint-bound staged and unstaged patch preview."));
  const button = make("button", "link-button", "Load Diff");
  button.id = "gitDiffReviewButton";
  button.type = "button";
  button.addEventListener("click", () => loadGitDiffReview(checkpoint));
  header.append(copy, button);
  panel.append(header);
  const output = make("div", "git-diff-review-output");
  output.id = "gitDiffReviewOutput";
  panel.append(output);
  target.append(panel);
}

function gitDiffReviewPayload(checkpoint) {
  const payload = {
    checkpoint_digest: checkpoint.checkpoint_digest,
    action: checkpoint.action,
    test_evidence: latestGitCheckpointRequest?.test_evidence || [],
    include_staged: true,
    include_unstaged: true,
    context_lines: 3,
  };
  if (latestGitCheckpointRequest?.cwd) {
    payload.cwd = latestGitCheckpointRequest.cwd;
  }
  return payload;
}

async function loadGitDiffReview(checkpoint) {
  const target = qs("#gitDiffReviewOutput");
  clear(target);
  target.append(statusBox("Loading raw diff", checkpoint.checkpoint_digest.slice(0, 16), "running"));
  try {
    gitDiffReviewDecisions = {};
    latestGitDiffReview = await api("/cli/git/diff-reviews", {
      method: "POST",
      body: gitDiffReviewPayload(checkpoint),
    });
    latestGitChangeReviewArtifacts = await loadGitChangeReviewArtifacts(latestGitDiffReview);
    renderGitDiffReview(target, latestGitDiffReview);
  } catch (error) {
    clear(target);
    target.append(statusBox("Raw diff unavailable", error.message, "failed"));
    showToast(error.message);
  }
}

function renderGitDiffReview(target, review) {
  clear(target);
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Branch", review.branch || "-");
  appendKeyValue(grid, "Head", review.head_sha ? review.head_sha.slice(0, 12) : "-");
  appendKeyValue(grid, "Digest", review.checkpoint_digest ? review.checkpoint_digest.slice(0, 16) : "-");
  appendKeyValue(grid, "Warnings", String((review.warnings || []).length), review.warnings?.length ? "pending" : "ok");
  target.append(grid);
  renderFindings(target, "Diff review warnings", review.warnings || [], "pending");
  renderGitChangeReview(target, review);
  for (const section of review.sections || []) {
    renderGitDiffSection(target, section);
  }
}

function gitDiffSectionDecisionKey(section) {
  return `${section.scope || "diff"}:${section.patch_digest || section.byte_count || section.returned_byte_count || "empty"}`;
}

function gitDiffSectionDecision(section) {
  return gitDiffReviewDecisions[gitDiffSectionDecisionKey(section)]?.decision || "pending";
}

function setGitDiffSectionDecision(section, decision) {
  const key = gitDiffSectionDecisionKey(section);
  if (decision === "pending") {
    delete gitDiffReviewDecisions[key];
  } else {
    gitDiffReviewDecisions[key] = {
      decision,
      scope: section.scope || "diff",
      patch_digest: section.patch_digest || "",
      decided_at: new Date().toISOString(),
    };
  }
  if (latestGitDiffReview) {
    renderGitDiffReview(qs("#gitDiffReviewOutput"), latestGitDiffReview);
  }
}

function gitDiffReviewDecisionCounts(review) {
  const counts = { accepted: 0, rejected: 0, pending: 0 };
  for (const section of review.sections || []) {
    const decision = gitDiffSectionDecision(section);
    if (decision === "accepted" || decision === "rejected") {
      counts[decision] += 1;
    } else {
      counts.pending += 1;
    }
  }
  return counts;
}

function gitDiffReviewHasRejectedSections() {
  return Boolean(latestGitDiffReview && gitDiffReviewDecisionCounts(latestGitDiffReview).rejected);
}

function updateGitReviewDecisionGate() {
  if (!latestGitCheckpoint) {
    return;
  }
  const blocked = gitDiffReviewHasRejectedSections();
  const enabled = latestGitCheckpoint.ready && !blocked;
  qs("#gitApprovalSubmitButton").disabled = !enabled;
  qs("#gitRunSubmitButton").disabled = !enabled;
}

function gitDiffSectionPaths(section) {
  const paths = [];
  const seen = new Set();
  const pattern = /^diff --git a\/(.+?) b\/(.+)$/gm;
  let match = pattern.exec(section.patch || "");
  while (match) {
    const path = match[2] || match[1];
    if (path && !seen.has(path)) {
      seen.add(path);
      paths.push(path);
    }
    match = pattern.exec(section.patch || "");
  }
  return paths;
}

function gitChangeReviewEvidence(review) {
  return {
    checkpoint_digest: review.checkpoint_digest || "",
    branch: review.branch || "",
    head_sha: review.head_sha || "",
    decisions: (review.sections || []).map((section) => ({
      scope: section.scope || "diff",
      decision: gitDiffSectionDecision(section),
      patch_digest: section.patch_digest || "",
      paths: gitDiffSectionPaths(section),
      redacted: Boolean(section.redacted),
      truncated: Boolean(section.truncated),
      omitted_protected_paths: section.omitted_protected_paths || [],
    })),
  };
}

function gitChangeReviewArtifactPayload(review) {
  const evidence = gitChangeReviewEvidence(review);
  const payload = {
    checkpoint_digest: review.checkpoint_digest || "",
    action: review.action || latestGitCheckpoint?.action || "commit",
    test_evidence: latestGitCheckpointRequest?.test_evidence || [],
    context_lines: 3,
    decisions: evidence.decisions.map((decision) => ({
      scope: decision.scope,
      decision: decision.decision,
      patch_digest: decision.patch_digest,
      paths: decision.paths,
      redacted: decision.redacted,
      truncated: decision.truncated,
      omitted_protected_paths: decision.omitted_protected_paths,
    })),
  };
  if (latestGitCheckpointRequest?.cwd) {
    payload.cwd = latestGitCheckpointRequest.cwd;
  }
  return payload;
}

async function copyGitChangeReviewEvidence(review) {
  await copyTextToClipboard(JSON.stringify(gitChangeReviewEvidence(review), null, 2), "Change review evidence copied.");
}

async function loadGitChangeReviewArtifacts(review) {
  const params = new URLSearchParams({
    action: review.action || latestGitCheckpoint?.action || "commit",
    limit: "12",
  });
  try {
    return await api(`/cli/git/change-review-artifacts?${params.toString()}`);
  } catch (error) {
    showToast(`Saved review artifacts unavailable: ${error.message}`);
    return [];
  }
}

async function saveGitChangeReviewArtifact(review) {
  const button = qs("#gitChangeReviewSaveButton");
  if (button) {
    button.disabled = true;
  }
  try {
    const artifact = await api("/cli/git/change-review-artifacts", {
      method: "POST",
      body: gitChangeReviewArtifactPayload(review),
    });
    latestGitChangeReviewArtifacts = await loadGitChangeReviewArtifacts(review);
    if (!latestGitChangeReviewArtifacts.find((item) => item.id === artifact.id)) {
      latestGitChangeReviewArtifacts.unshift(artifact);
    }
    renderGitDiffReview(qs("#gitDiffReviewOutput"), review);
    showToast("Change review artifact saved.");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

function gitChangeReviewArtifactCounts(artifact) {
  const counts = { accepted: 0, rejected: 0, pending: 0 };
  for (const decision of artifact.decisions || []) {
    if (decision.decision === "accepted" || decision.decision === "rejected") {
      counts[decision.decision] += 1;
    } else {
      counts.pending += 1;
    }
  }
  return counts;
}

function applyGitChangeReviewArtifact(artifact, review) {
  if (artifact.checkpoint_digest !== review.checkpoint_digest) {
    showToast("Saved review artifact is stale for this checkpoint.");
    return;
  }
  const sectionKeys = new Set((review.sections || []).map((section) => gitDiffSectionDecisionKey(section)));
  gitDiffReviewDecisions = {};
  for (const decision of artifact.decisions || []) {
    const key = `${decision.scope || "diff"}:${decision.patch_digest || "empty"}`;
    if (!sectionKeys.has(key) || decision.decision === "pending") {
      continue;
    }
    gitDiffReviewDecisions[key] = {
      decision: decision.decision,
      scope: decision.scope || "diff",
      patch_digest: decision.patch_digest || "",
      decided_at: artifact.created_at || new Date().toISOString(),
      artifact_id: artifact.id,
    };
  }
  renderGitDiffReview(qs("#gitDiffReviewOutput"), review);
  showToast("Change review artifact applied.");
}

function renderGitChangeReviewArtifacts(target, review) {
  const box = make("div", "git-change-review-artifacts");
  box.append(make("div", "item-title", "Saved artifacts"));
  if (!latestGitChangeReviewArtifacts.length) {
    box.append(statusBox("No saved review artifacts", "Save decisions to restore them after reload.", "pending"));
    target.append(box);
    return;
  }
  for (const artifact of latestGitChangeReviewArtifacts) {
    const current = artifact.checkpoint_digest === review.checkpoint_digest;
    const counts = gitChangeReviewArtifactCounts(artifact);
    const row = make("div", "git-change-review-artifact");
    const copy = make("div");
    copy.append(make("div", "item-title", artifact.id || "saved-review"));
    copy.append(
      make(
        "div",
        "item-meta",
        `${artifact.branch || "-"} at ${artifact.head_sha ? artifact.head_sha.slice(0, 12) : "-"} | ${formatTimestamp(artifact.created_at)}`,
      ),
    );
    const chips = make("div", "chip-row");
    chips.append(statusChip(current ? "current" : "stale", current ? "ok" : "pending"));
    chips.append(statusChip(`accepted ${counts.accepted}`, counts.accepted ? "accepted" : ""));
    chips.append(statusChip(`rejected ${counts.rejected}`, counts.rejected ? "rejected" : ""));
    chips.append(statusChip(`pending ${counts.pending}`, counts.pending ? "pending" : "ok"));
    copy.append(chips);
    const apply = make("button", "link-button", "Apply");
    apply.type = "button";
    apply.disabled = !current;
    apply.title = current
      ? "Apply saved decisions to this loaded checkpoint."
      : "Stale artifacts cannot unblock Git closeout.";
    apply.addEventListener("click", () => applyGitChangeReviewArtifact(artifact, review));
    row.append(copy, apply);
    box.append(row);
  }
  target.append(box);
}

function renderGitChangeReview(target, review) {
  const box = make("div", "git-change-review");
  const header = make("div", "builder-row");
  const copy = make("div");
  copy.append(make("div", "item-title", "Change decisions"));
  copy.append(make("div", "item-meta", "Persistable review for loaded checkpoint diff sections."));
  const actions = make("div", "button-row");
  const save = make("button", "primary-button", "Save Artifact");
  save.id = "gitChangeReviewSaveButton";
  save.type = "button";
  save.disabled = !(review.sections || []).length;
  save.addEventListener("click", () => saveGitChangeReviewArtifact(review));
  const button = make("button", "link-button", "Copy Evidence");
  button.type = "button";
  button.disabled = !(review.sections || []).length;
  button.addEventListener("click", () => copyGitChangeReviewEvidence(review));
  actions.append(save, button);
  header.append(copy, actions);
  box.append(header);
  const counts = gitDiffReviewDecisionCounts(review);
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Accepted", String(counts.accepted), counts.accepted ? "accepted" : "");
  appendKeyValue(grid, "Rejected", String(counts.rejected), counts.rejected ? "rejected" : "");
  appendKeyValue(grid, "Pending", String(counts.pending), counts.pending ? "pending" : "ok");
  appendKeyValue(grid, "Sections", String((review.sections || []).length));
  box.append(grid);
  if (counts.rejected) {
    box.append(statusBox("Git closeout paused", "Rejected diff sections block dashboard Git approval and direct run controls.", "blocked"));
  }
  target.append(box);
  renderGitChangeReviewArtifacts(target, review);
  updateGitReviewDecisionGate();
}

function renderGitDiffSection(target, section) {
  const box = make("details", "git-diff-section");
  box.open = true;
  box.append(make("summary", "", `${section.scope} diff`));
  const meta = make("div", "chip-row");
  meta.append(statusChip(section.redacted ? "redacted" : "ok"));
  meta.append(statusChip(gitDiffSectionDecision(section)));
  if (section.truncated) {
    meta.append(statusChip("truncated", "pending"));
  }
  if (section.omitted_protected_paths?.length) {
    meta.append(statusChip("protected paths omitted", "blocked"));
  }
  box.append(meta);
  const info = make("div", "checkpoint-grid");
  appendKeyValue(info, "Patch digest", section.patch_digest ? section.patch_digest.slice(0, 16) : "-");
  appendKeyValue(info, "Returned bytes", `${section.returned_byte_count || 0} / ${section.byte_count || 0}`);
  appendKeyValue(info, "Decision", gitDiffSectionDecision(section), gitDiffSectionDecision(section));
  box.append(info);
  const paths = gitDiffSectionPaths(section);
  if (paths.length) {
    renderChipList(box, "Diff paths", paths, "pending");
  }
  if (section.omitted_protected_paths?.length) {
    const omitted = make("div", "changed-paths");
    omitted.append(make("div", "item-title", "Omitted paths"));
    for (const path of section.omitted_protected_paths) {
      omitted.append(make("code", "", path));
    }
    box.append(omitted);
  }
  const controls = make("div", "git-diff-decision-controls");
  const accept = make("button", "success-button", "Accept");
  accept.type = "button";
  accept.setAttribute("aria-pressed", String(gitDiffSectionDecision(section) === "accepted"));
  accept.addEventListener("click", () => setGitDiffSectionDecision(section, "accepted"));
  const reject = make("button", "danger-button", "Reject");
  reject.type = "button";
  reject.setAttribute("aria-pressed", String(gitDiffSectionDecision(section) === "rejected"));
  reject.addEventListener("click", () => setGitDiffSectionDecision(section, "rejected"));
  const clearDecision = make("button", "link-button", "Clear");
  clearDecision.type = "button";
  clearDecision.addEventListener("click", () => setGitDiffSectionDecision(section, "pending"));
  controls.append(accept, reject, clearDecision);
  box.append(controls);
  const patch = make("pre", "diff-patch", section.patch || "No tracked patch content.");
  box.append(patch);
  target.append(box);
}

function gitApprovalEndpoint(action) {
  return `/cli/git/${action}-approvals`;
}

function gitRunEndpoint(action) {
  return `/cli/git/${action}-runs`;
}

function gitApprovalTimeout() {
  const timeout = Number(qs("#gitApprovalTimeoutInput").value || 30);
  return Number.isFinite(timeout) ? timeout : 30;
}

function gitApprovalPayload(checkpoint) {
  const payload = {
    checkpoint_digest: checkpoint.checkpoint_digest,
    test_evidence: latestGitCheckpointRequest?.test_evidence || [],
    timeout_seconds: gitApprovalTimeout(),
  };
  if (latestGitCheckpointRequest?.cwd) {
    payload.cwd = latestGitCheckpointRequest.cwd;
  }
  if (checkpoint.action === "commit") {
    payload.commit_message = qs("#gitCommitMessageInput").value.trim();
  } else if (checkpoint.action === "pr") {
    payload.title = qs("#gitPrTitleInput").value.trim();
    payload.body = qs("#gitPrBodyInput").value.trim();
    payload.draft = qs("#gitPrDraftInput").checked;
    const baseBranch = qs("#gitPrBaseInput").value.trim();
    if (baseBranch) {
      payload.base_branch = baseBranch;
    }
  }
  return payload;
}

function gitRunPayload(checkpoint) {
  return gitApprovalPayload(checkpoint);
}

function validateGitCloseoutFields(checkpoint) {
  if (checkpoint.action === "commit" && !qs("#gitCommitMessageInput").value.trim()) {
    throw new Error("Commit message is required.");
  }
  if (checkpoint.action === "pr" && !qs("#gitPrTitleInput").value.trim()) {
    throw new Error("PR title is required.");
  }
}

function renderGitApprovalActions(checkpoint) {
  const panel = qs("#gitApprovalActions");
  const approvalOutput = qs("#gitApprovalOutput");
  const runOutput = qs("#gitRunOutput");
  clear(approvalOutput);
  clear(runOutput);
  if (!checkpoint) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.open = true;

  const actionLabels = {
    commit: "Commit Approval",
    push: "Push Approval",
    pr: "PR Approval",
  };
  const runLabels = {
    commit: "Run Commit Now",
    push: "Run Push Now",
    pr: "Run PR Now",
  };
  qs("#gitApprovalSummary").textContent = actionLabels[checkpoint.action] || "Checkpoint Approval Actions";
  qs("#gitCommitMessageField").hidden = checkpoint.action !== "commit";
  qs("#gitCommitMessageInput").required = checkpoint.action === "commit";
  qs("#gitPrTitleField").hidden = checkpoint.action !== "pr";
  qs("#gitPrTitleInput").required = checkpoint.action === "pr";
  qs("#gitPrBodyField").hidden = checkpoint.action !== "pr";
  qs("#gitPrOptionsField").hidden = checkpoint.action !== "pr";
  qs("#gitApprovalSubmitLabel").textContent = `Create ${actionLabels[checkpoint.action] || "Git"} Approval`;
  qs("#gitApprovalSubmitButton").disabled = !checkpoint.ready;
  qs("#gitRunSubmitLabel").textContent = runLabels[checkpoint.action] || "Run Git Now";
  qs("#gitRunSubmitButton").disabled = !checkpoint.ready;
  updateGitReviewDecisionGate();
  if (!checkpoint.ready) {
    approvalOutput.append(
      statusBox("Approval unavailable", "Resolve checkpoint blockers before creating a Git approval.", "blocked"),
    );
    runOutput.append(statusBox("Direct run unavailable", "Resolve checkpoint blockers before running Git.", "blocked"));
  }
}

async function createGitApproval(event) {
  event.preventDefault();
  if (!latestGitCheckpoint) {
    return;
  }
  const target = qs("#gitApprovalOutput");
  if (!latestGitCheckpoint.ready) {
    clear(target);
    target.append(statusBox("Approval unavailable", "Resolve checkpoint blockers before creating a Git approval.", "blocked"));
    return;
  }
  const payload = gitApprovalPayload(latestGitCheckpoint);
  const endpoint = gitApprovalEndpoint(latestGitCheckpoint.action);
  clear(target);
  target.append(statusBox("Creating Git approval", latestGitCheckpoint.checkpoint_digest.slice(0, 16), "running"));
  try {
    const approval = await api(endpoint, { method: "POST", body: payload });
    clear(target);
    target.append(statusBox("Git approval created", approval.id, approval.status || "pending"));
    target.append(jsonBlock(approval));
    setApprovalFilterState("cli", "pending");
    await Promise.all([loadApprovals(), loadTaskChatContext()]);
    showToast("Git approval created.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Git approval failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function runGitWorkflow() {
  if (!latestGitCheckpoint) {
    return;
  }
  const target = qs("#gitRunOutput");
  if (!latestGitCheckpoint.ready) {
    clear(target);
    target.append(statusBox("Direct run unavailable", "Resolve checkpoint blockers before running Git.", "blocked"));
    return;
  }
  let payload = {};
  try {
    validateGitCloseoutFields(latestGitCheckpoint);
    payload = gitRunPayload(latestGitCheckpoint);
  } catch (error) {
    clear(target);
    target.append(statusBox("Git run invalid", error.message, "failed"));
    showToast(error.message);
    return;
  }
  const endpoint = gitRunEndpoint(latestGitCheckpoint.action);
  clear(target);
  target.append(statusBox("Running checkpoint-bound Git action", latestGitCheckpoint.checkpoint_digest.slice(0, 16), "running"));
  try {
    const result = await api(endpoint, { method: "POST", body: payload });
    clear(target);
    renderGitRunResult(target, result);
    latestGitCheckpoint = null;
    latestGitDiffReview = null;
    latestGitChangeReviewArtifacts = [];
    gitDiffReviewDecisions = {};
    qs("#gitApprovalSubmitButton").disabled = true;
    qs("#gitRunSubmitButton").disabled = true;
    await Promise.all([loadTasks(), loadCliRuns()]);
    showToast("Git workflow run completed.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Git run failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderGitRunResult(target, result) {
  const box = make("div", "git-run-summary");
  box.append(statusBox("Git run completed", result.action || "git", "ready"));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Action", result.action || "-");
  appendKeyValue(grid, "Branch", result.branch || "-");
  appendKeyValue(grid, "Digest", result.checkpoint_digest ? result.checkpoint_digest.slice(0, 16) : "-");
  appendKeyValue(grid, "Exit code", String(result.exit_code ?? "-"));
  appendKeyValue(grid, "Duration", `${result.duration_ms ?? 0} ms`);
  if (result.action === "commit") {
    appendKeyValue(grid, "Head before", result.head_before ? result.head_before.slice(0, 12) : "-");
    appendKeyValue(grid, "Head after", result.head_after ? result.head_after.slice(0, 12) : "-");
    appendKeyValue(grid, "Message digest", result.commit_message_digest ? result.commit_message_digest.slice(0, 16) : "-");
  } else if (result.action === "push") {
    appendKeyValue(grid, "Upstream", result.upstream || "-");
    appendKeyValue(grid, "Remote digest", result.remote_url_digest ? result.remote_url_digest.slice(0, 16) : "-");
    appendKeyValue(grid, "Ahead before / after", `${result.ahead_before ?? "-"} / ${result.ahead_after ?? "-"}`);
    appendKeyValue(grid, "Behind before / after", `${result.behind_before ?? "-"} / ${result.behind_after ?? "-"}`);
  } else if (result.action === "pr") {
    appendKeyValue(grid, "Head branch", result.head_branch || "-");
    appendKeyValue(grid, "Base branch", result.base_branch || "-");
    appendKeyValue(grid, "Draft", result.draft ? "Yes" : "No");
    appendKeyValue(grid, "Title digest", result.title_digest ? result.title_digest.slice(0, 16) : "-");
    appendKeyValue(grid, "Body digest", result.body_digest ? result.body_digest.slice(0, 16) : "-");
    appendKeyValue(grid, "PR URL", result.pr_url || "-");
  }
  box.append(grid);
  const details = make("details", "json-details");
  details.append(make("summary", "", "Raw run metadata"));
  details.append(jsonBlock(result));
  box.append(details);
  target.append(box);
}

function projectPayload() {
  const payload = {
    root_dir: qs("#projectRootInput").value.trim(),
  };
  const name = qs("#projectNameInput").value.trim();
  if (name) {
    payload.name = name;
  }
  return payload;
}

function renderProjectMarkers(target, markers, warnings) {
  if (markers?.length) {
    const box = make("div", "changed-paths");
    box.append(make("div", "item-title", "Markers"));
    for (const marker of markers) {
      box.append(make("code", "", marker));
    }
    target.append(box);
  }
  renderFindings(target, "Warnings", warnings || [], "pending");
}

function renderActivationChecks(target, activation) {
  const checks = activation?.checks || [];
  if (!checks.length) {
    return;
  }
  const box = make("div", "finding-list");
  box.append(make("div", "item-title", "Activation checks"));
  for (const check of checks) {
    const row = make("div", "finding-row");
    row.append(statusChip(check.status), make("span", "", `${check.label}: ${check.detail}`));
    box.append(row);
  }
  target.append(box);
}

async function preflightProjectRoot(event) {
  event?.preventDefault();
  const payload = projectPayload();
  if (!payload.root_dir) {
    showToast("Project root is required.");
    return;
  }
  const target = qs("#projectRegistryOutput");
  clear(target);
  target.append(statusBox("Checking project root", payload.root_dir, "running"));
  try {
    const result = await api("/projects/preflight", { method: "POST", body: payload });
    clear(target);
    target.append(statusBox("Project root ready", result.root_dir, "ok"));
    renderProjectMarkers(target, result.markers, result.warnings);
  } catch (error) {
    clear(target);
    target.append(statusBox("Project check failed", error.message, "failed"));
  }
}

async function registerProject(event) {
  event.preventDefault();
  const payload = projectPayload();
  if (!payload.root_dir) {
    showToast("Project root is required.");
    return;
  }
  if (!payload.name) {
    payload.name = payload.root_dir.split(/[\\/]/).filter(Boolean).pop() || "Project";
  }
  const target = qs("#projectRegistryOutput");
  clear(target);
  target.append(statusBox("Registering project", payload.root_dir, "running"));
  try {
    const project = await api("/projects", { method: "POST", body: payload });
    clear(target);
    target.append(statusBox("Project registered", project.name, "ok"));
    qs("#projectForm").reset();
    await Promise.all([loadProjects(), loadTaskChatContext()]);
  } catch (error) {
    clear(target);
    target.append(statusBox("Registration failed", error.message, "failed"));
  }
}

async function activateProject(projectId) {
  const target = qs("#projectRegistryOutput");
  clear(target);
  target.append(statusBox("Opening project", projectId, "running"));
  try {
    const result = await api(`/projects/${encodeURIComponent(projectId)}/activate`, {
      method: "POST",
    });
    workspacePath = ".";
    openFilePath = "";
    qs("#workspaceEditorTitle").textContent = "No file open";
    qs("#workspaceEditor").value = "";
    await Promise.all([loadSettings(), loadWorkspace("."), loadLogs()]);
    await Promise.all([loadProjects(), loadTaskChatContext()]);
    showToast(result.switched ? "Project opened." : "Project is already active.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Project activation blocked", error.message, "blocked"));
    if (error.detail && typeof error.detail === "object") {
      renderFindings(target, "Blockers", error.detail.blockers || [], "blocked");
      renderFindings(target, "Warnings", error.detail.warnings || [], "pending");
      renderActivationChecks(target, error.detail);
    }
  }
}

async function loadProjects() {
  const [projects, active] = await Promise.all([
    safeLoad("projects", () => api("/projects")),
    safeLoad("active project", () => api("/projects/active")),
  ]);
  const target = qs("#projectRegistryOutput");
  if (!projects.ok && !active.ok) {
    clear(target);
    target.append(statusBox("Projects unavailable", `${projects.error}; ${active.error}`, "blocked"));
    return;
  }
  if (active.ok) {
    activeProjectId = active.data.project?.id || "";
  }
  renderProjectList(projects, active);
}

function renderProjectList(projects, active) {
  const target = qs("#projectRegistryOutput");
  clear(target);
  if (!projects.ok) {
    target.append(statusBox("Projects unavailable", projects.error, "blocked"));
    return;
  }
  const records = projects.data || [];
  if (!records.length) {
    target.append(statusBox("No registered projects", active.ok ? active.data.active_root_dir : "-", "pending"));
  }
  for (const project of records.slice(0, 8)) {
    const item = make("div", "list-item");
    const isActive = activeProjectId && project.id === activeProjectId;
    item.append(make("div", "item-title", project.name || project.id));
    item.append(make("div", "item-meta", compactPath(project.root_dir)));
    item.append(statusChip(isActive ? "active" : project.status || "available"));
    const actions = make("div", "button-row");
    const openButton = make("button", "link-button", isActive ? "Active" : "Open");
    openButton.type = "button";
    openButton.disabled =
      isActive || project.status !== "available" || !active.ok || !active.data.switching_available;
    openButton.addEventListener("click", () => activateProject(project.id));
    actions.append(openButton);
    item.append(actions);
    target.append(item);
  }
  if (active.ok) {
    target.append(statusBox("Runtime root", compactPath(active.data.active_root_dir), "ok"));
    if (active.data.reason) {
      renderFindings(target, "Notes", [active.data.reason], "pending");
    }
  }
}

async function loadSettings() {
  const result = await safeLoad("settings", () => api("/settings/effective"));
  const target = qs("#settingsOutput");
  clear(target);
  if (!result.ok) {
    latestSettingsView = null;
    target.append(statusBox("Settings unavailable", result.error, "blocked"));
    renderProjectContext(null, result.error);
    renderPolicyReviewSummary();
    return;
  }
  latestSettingsView = result.data;
  renderProjectContext(result.data);
  renderSettingsReview(result.data, target);
  renderPolicyReviewSummary();
  if (latestPolicyReviewResults?.cliRules) {
    renderCliPolicyList(latestPolicyReviewResults.cliRules);
  }
  if (latestPolicyReviewResults?.recipes) {
    renderRecipeList(latestPolicyReviewResults.recipes);
  }
  if (latestPolicyReviewResults?.hooks) {
    renderHookPolicyList(latestPolicyReviewResults.hooks);
  }
  if (latestPolicyReviewResults?.plugins) {
    renderPluginList(latestPolicyReviewResults.plugins);
  }
}

function renderSettingsReview(settingsView, target) {
  const settings = settingsView.settings || [];
  const settingMap = new Map(settings.map((setting) => [setting.name, setting]));
  const managedLocks = parseSettingList(settingMap.get("managed_policy_locks"));
  const redactedCount = settings.filter((setting) => setting.redacted).length;
  const summary = make("div", "settings-review-summary");
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(
    grid,
    "Managed settings",
    settingsView.managed_settings_enabled ? "Enabled" : "Disabled",
    settingsView.managed_settings_enabled ? "managed" : "default",
  );
  appendKeyValue(grid, "Managed fields", String(settingsView.managed_fields?.length || 0));
  appendKeyValue(grid, "Policy locks", managedLocks.length ? String(managedLocks.length) : "None");
  appendKeyValue(grid, "Redacted values", String(redactedCount));
  appendKeyValue(grid, "Sources", compactCounts(sourceCounts(settings)));
  appendKeyValue(
    grid,
    "Managed digest",
    settingsView.managed_settings_digest ? settingsView.managed_settings_digest.slice(0, 16) : "-",
  );
  summary.append(grid);
  if (settingsView.managed_settings_file) {
    summary.append(statusBox("Managed file", compactPath(settingsView.managed_settings_file), "managed"));
  }
  renderChipList(summary, "Managed fields", settingsView.managed_fields || [], "managed");
  renderChipList(summary, "Policy locks", managedLocks, "locked");
  target.append(summary);
  renderSettingsGroups(target, settings);
}

function renderChipList(target, title, values, chipClass) {
  if (!values.length) {
    return;
  }
  const box = make("div", "chip-list");
  box.append(make("div", "item-title", title));
  const row = make("div", "chip-row");
  for (const value of values.slice(0, 24)) {
    row.append(statusChip(value, chipClass));
  }
  if (values.length > 24) {
    row.append(statusChip(`+${values.length - 24} more`, chipClass));
  }
  box.append(row);
  target.append(box);
}

function settingsGroupName(name) {
  const value = String(name || "").toLowerCase();
  if (["app_name", "environment", "root_dir", "data_dir", "database_url"].includes(value)) {
    return "Runtime";
  }
  if (
    value.includes("auth") ||
    value.includes("token") ||
    value.includes("credential") ||
    value.includes("secret") ||
    value.includes("vault") ||
    value.includes("approval_digest")
  ) {
    return "Security";
  }
  if (
    value.includes("managed") ||
    value.includes("policy") ||
    value.includes("hook") ||
    value.includes("plugin") ||
    value.includes("network_domain") ||
    value.includes("command_recipe")
  ) {
    return "Policy Sources";
  }
  if (
    value.includes("provider") ||
    value.includes("ollama") ||
    value.includes("lm_studio") ||
    value.includes("openai") ||
    value.includes("model") ||
    value.includes("routing") ||
    value.includes("cost") ||
    value.includes("price")
  ) {
    return "Providers";
  }
  if (
    value.includes("memory") ||
    value.includes("retrieval") ||
    value.includes("embedding") ||
    value.includes("tool") ||
    value.includes("localmcp")
  ) {
    return "Memory And Tools";
  }
  if (
    value.includes("cli") ||
    value.includes("command") ||
    value.includes("filesystem") ||
    value.includes("timeout") ||
    value.includes("process") ||
    value.includes("output") ||
    value.includes("web_retrieval")
  ) {
    return "Execution Limits";
  }
  return "Other";
}

function renderSettingsGroups(target, settings) {
  const groupOrder = [
    "Runtime",
    "Security",
    "Policy Sources",
    "Providers",
    "Memory And Tools",
    "Execution Limits",
    "Other",
  ];
  const groups = new Map(groupOrder.map((group) => [group, []]));
  for (const setting of settings) {
    groups.get(settingsGroupName(setting.name)).push(setting);
  }
  const wrapper = make("div", "settings-groups");
  for (const group of groupOrder) {
    const records = groups.get(group);
    if (!records.length) {
      continue;
    }
    const details = make("details", "settings-group");
    if (["Runtime", "Security", "Policy Sources"].includes(group)) {
      details.open = true;
    }
    details.append(make("summary", "", `${group} (${records.length})`));
    const list = make("div", "settings-group-list");
    for (const setting of records) {
      list.append(renderSettingItem(setting));
    }
    details.append(list);
    wrapper.append(details);
  }
  target.append(wrapper);
}

function renderSettingItem(setting) {
  const item = make("div", "setting-item");
  item.append(make("strong", "", setting.name || "setting"));
  const meta = make("div", "setting-source-row");
  meta.append(statusChip(setting.source || "runtime"));
  if (setting.redacted) {
    meta.append(statusChip("redacted"));
  }
  item.append(meta);
  item.append(make("code", "", settingValueText(setting.value)));
  return item;
}

function renderProjectContext(settingsView, error = "") {
  const target = qs("#projectContextOutput");
  clear(target);
  if (!settingsView) {
    activeRootDir = "";
    activeRootSource = "";
    qs("#rootContextSummary").textContent = "Active root: -";
    target.append(statusBox("Project context unavailable", error || "Settings are unavailable.", "blocked"));
    return;
  }

  const rootSetting = settingByName(settingsView, "root_dir");
  const dataSetting = settingByName(settingsView, "data_dir");
  const environmentSetting = settingByName(settingsView, "environment");
  const authSetting = settingByName(settingsView, "effective_auth_enabled");
  activeRootDir = settingText(rootSetting, ".");
  activeRootSource = rootSetting?.source || "default";

  qs("#rootContextSummary").textContent = `Active root: ${compactPath(activeRootDir)}`;
  target.append(statusBox("Active workspace root", compactPath(activeRootDir), "ok"));
  const grid = make("div", "context-grid");
  appendKeyValue(grid, "Root source", activeRootSource, activeRootSource);
  appendKeyValue(grid, "State directory", compactPath(settingText(dataSetting, "-")));
  appendKeyValue(grid, "Environment", settingText(environmentSetting, "-"));
  appendKeyValue(grid, "Auth", settingText(authSetting, "-"));
  target.append(grid);

  if (settingsView.managed_settings_enabled) {
    target.append(
      statusBox(
        "Managed settings",
        compactPath(settingsView.managed_settings_file || settingsView.managed_settings_digest || "-"),
        "ok",
      ),
    );
  }
}

async function loadProviders() {
  const [providers, tools] = await Promise.all([
    safeLoad("providers", () => api("/providers")),
    safeLoad("tools", () => api("/tools")),
  ]);
  setMetric("#providersMetric", providers.ok ? String(providers.data.length) : "-");
  setMetric("#toolsMetric", `Tools: ${tools.ok ? tools.data.length : "-"}`);

  const target = qs("#providerList");
  clear(target);
  if (!providers.ok) {
    target.append(statusBox("Providers unavailable", providers.error, "blocked"));
  } else if (!providers.data.length) {
    target.append(statusBox("No providers", "Provider catalog is empty.", "pending"));
  } else {
    for (const provider of providers.data) {
      const item = make("div", "list-item builder-row");
      const detail = make("div");
      detail.append(make("div", "item-title", provider.name || provider.id));
      detail.append(make("div", "item-meta", `${provider.kind} - ${provider.permission_mode}`));
      const actions = make("div", "recipe-action-buttons");
      const healthButton = make("button", "link-button", "Health");
      healthButton.type = "button";
      healthButton.dataset.testid = "provider-health-check";
      healthButton.dataset.providerId = provider.id || "";
      healthButton.addEventListener("click", () => checkProviderHealth(provider.id));
      actions.append(statusChip(provider.enabled ? "ok" : "blocked"), healthButton);
      item.append(detail, actions);
      target.append(item);
    }
  }
  renderToolGovernanceList(tools);
}

function renderProviderHealth(target, health) {
  const state = health.available ? "ok" : "blocked";
  target.append(statusBox("Provider health", health.message || health.provider_id, state));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Provider", health.provider_id || "-");
  appendKeyValue(grid, "Available", health.available ? "Yes" : "No", state);
  appendKeyValue(grid, "Models", health.model_names?.length ? health.model_names.join(", ") : "-");
  appendKeyValue(grid, "Checked", health.checked_at || "-");
  target.append(grid);
  target.append(jsonBlock(health));
}

async function checkProviderHealth(providerId) {
  const target = qs("#providerHealthOutput");
  clear(target);
  target.append(statusBox("Checking provider health", providerId, "running"));
  try {
    const health = await api(`/providers/${encodeURIComponent(providerId)}/health`);
    clear(target);
    renderProviderHealth(target, health);
    showToast("Provider health checked.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Provider health unavailable", error.message, "failed"));
    showToast(error.message);
  }
}

function toolGovernanceState(tool) {
  if (tool.status === "disabled") {
    return "blocked";
  }
  if (tool.status === "deprecated") {
    return "pending";
  }
  return "ok";
}

function toolGovernancePayload(status) {
  const reason = qs("#toolGovernanceReasonInput").value.trim();
  const payload = { status };
  if (reason) {
    payload.reason = reason;
  }
  return payload;
}

async function updateToolGovernance(toolName, status) {
  const target = qs("#toolGovernanceOutput");
  clear(target);
  const payload = toolGovernancePayload(status);
  if (status !== "active" && !payload.reason) {
    target.append(statusBox("Governance reason required", "Add a reason before changing tool status.", "blocked"));
    return;
  }
  target.append(statusBox("Updating tool governance", `${toolName} -> ${status}`, "running"));
  try {
    const tool = await api(`/tools/${encodeURIComponent(toolName)}/governance`, {
      method: "PATCH",
      body: payload,
    });
    clear(target);
    target.append(statusBox("Tool governance updated", tool.name || toolName, toolGovernanceState(tool)));
    target.append(jsonBlock(tool));
    showToast("Tool governance updated.");
    await loadProviders();
  } catch (error) {
    clear(target);
    target.append(statusBox("Tool governance update failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderToolGovernanceList(result) {
  const target = qs("#toolGovernanceList");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Tools unavailable", result.error, "blocked"));
    return;
  }
  const tools = result.data || [];
  if (!tools.length) {
    target.append(statusBox("No generated tools", "Tool registry is empty.", "pending"));
    return;
  }
  for (const tool of tools.slice(0, 10)) {
    const toolName = tool.name || "";
    const item = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", toolName || "-"));
    detail.append(
      make(
        "div",
        "item-meta",
        `${tool.status || "active"} - ${tool.permission_mode || "policy"} - v${tool.version || "-"}`,
      ),
    );
    if (tool.deprecated_reason) {
      detail.append(make("div", "item-meta", tool.deprecated_reason));
    }
    const actions = make("div", "recipe-action-buttons");
    const activeButton = make("button", "success-button", "Active");
    activeButton.type = "button";
    activeButton.dataset.testid = "tool-governance-active";
    activeButton.dataset.toolName = toolName;
    activeButton.disabled = !toolName || tool.status === "active";
    activeButton.addEventListener("click", () => updateToolGovernance(toolName, "active"));
    const deprecatedButton = make("button", "link-button", "Deprecate");
    deprecatedButton.type = "button";
    deprecatedButton.dataset.testid = "tool-governance-deprecated";
    deprecatedButton.dataset.toolName = toolName;
    deprecatedButton.disabled = !toolName || tool.status === "deprecated";
    deprecatedButton.addEventListener("click", () => updateToolGovernance(toolName, "deprecated"));
    const disabledButton = make("button", "danger-button", "Disable");
    disabledButton.type = "button";
    disabledButton.dataset.testid = "tool-governance-disabled";
    disabledButton.dataset.toolName = toolName;
    disabledButton.disabled = !toolName || tool.status === "disabled";
    disabledButton.addEventListener("click", () => updateToolGovernance(toolName, "disabled"));
    actions.append(statusChip(toolGovernanceState(tool)), activeButton, deprecatedButton, disabledButton);
    item.append(detail, actions);
    target.append(item);
  }
}

function optionalNumber(selector) {
  const value = qs(selector).value.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function routingPreviewPayload() {
  return {
    role: qs("#routingRoleInput").value.trim() || "planner",
    privacy_required: qs("#routingPrivacyInput").checked,
    max_latency_ms: optionalNumber("#routingLatencyInput"),
    max_cost_usd: optionalNumber("#routingCostInput"),
    required_capabilities: splitCsv(qs("#routingCapabilitiesInput").value),
  };
}

function renderRoutingDecision(target, decision) {
  target.append(statusBox("Routing preview", decision.reason || decision.provider_id, "ok"));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Provider", decision.provider_id || "-");
  appendKeyValue(grid, "Model", decision.model_name || "-");
  appendKeyValue(grid, "Score", Number(decision.score ?? 0).toFixed(3));
  appendKeyValue(grid, "Role", decision.policy?.role || "-");
  appendKeyValue(grid, "Max latency", decision.policy?.max_latency_ms ?? "-");
  appendKeyValue(grid, "Max cost", decision.policy?.max_cost_usd ?? "-");
  target.append(grid);
  const candidateScores = Object.entries(decision.candidate_scores || {})
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .map(([providerId, score]) => `${providerId}: ${Number(score).toFixed(3)}`);
  renderChipList(target, "Candidate scores", candidateScores, "pending");
  target.append(jsonBlock(decision));
}

async function previewProviderRoute(event) {
  event.preventDefault();
  const target = qs("#routingOutput");
  const payload = routingPreviewPayload();
  clear(target);
  target.append(statusBox("Previewing provider route", payload.role, "running"));
  try {
    const decision = await api("/routing/decide", { method: "POST", body: payload });
    clear(target);
    renderRoutingDecision(target, decision);
    showToast("Provider route previewed.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Routing preview failed", error.message, "failed"));
    showToast(error.message);
  }
}

function boundedNumber(selector, fallback, minimum, maximum) {
  const value = optionalNumber(selector);
  if (value === null) {
    return fallback;
  }
  return Math.min(maximum, Math.max(minimum, value));
}

function memoryRetrievalPayload() {
  const metadataFilters = {};
  const category = qs("#memoryRetrievalCategoryInput").value.trim();
  const lifecycleState = qs("#memoryRetrievalLifecycleInput").value.trim();
  if (category) {
    metadataFilters.category = category;
  }
  if (lifecycleState) {
    metadataFilters.lifecycle_state = lifecycleState;
  }
  const payload = {
    query: qs("#memoryRetrievalQueryInput").value.trim(),
    limit: Math.trunc(boundedNumber("#memoryRetrievalLimitInput", 10, 1, 100)),
    similarity_threshold: boundedNumber("#memoryRetrievalThresholdInput", 0.2, 0, 1),
    include_inactive: qs("#memoryRetrievalInactiveInput").checked,
  };
  const entityTypes = splitCsv(qs("#memoryRetrievalEntityTypesInput").value);
  const tags = splitCsv(qs("#memoryRetrievalTagsInput").value);
  if (entityTypes.length) {
    payload.entity_types = entityTypes;
  }
  if (tags.length) {
    payload.tags = tags;
  }
  if (Object.keys(metadataFilters).length) {
    payload.metadata_filters = metadataFilters;
  }
  return payload;
}

function retrievalScore(value) {
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(3) : "-";
}

function renderMemoryRetrievalResults(target, result) {
  const results = result.results || [];
  target.append(
    statusBox(
      "Memory retrieval",
      `${result.total ?? results.length} result(s) in ${Number(result.query_time_ms ?? 0).toFixed(1)} ms`,
      "ok",
    ),
  );
  if (!results.length) {
    target.append(statusBox("No memory matches", "Try a broader query or lower threshold.", "pending"));
    target.append(jsonBlock(result));
    return;
  }
  const list = make("div", "compact-list");
  for (const item of results.slice(0, 10)) {
    const row = make("div", "list-item");
    row.append(make("div", "item-title", `${item.entity_type || "memory"}: ${item.entity_id || item.metadata_id || "-"}`));
    row.append(
      make(
        "div",
        "item-meta",
        `combined ${retrievalScore(item.combined_score)} - similarity ${retrievalScore(
          item.similarity_score,
        )} - metadata ${retrievalScore(item.metadata_relevance)} - ${item.source_type || item.source || "retrieval"}`,
      ),
    );
    if (item.description) {
      row.append(make("div", "item-meta", item.description));
    }
    renderChipList(row, "Matched fields", item.matched_fields || [], "ok");
    renderChipList(row, "Score reasons", item.score_reasons || [], "pending");
    list.append(row);
  }
  target.append(list);
  target.append(jsonBlock(result));
}

async function runMemoryRetrieval(event) {
  event.preventDefault();
  const target = qs("#memoryRetrievalOutput");
  const payload = memoryRetrievalPayload();
  clear(target);
  if (!payload.query) {
    target.append(statusBox("Memory query required", "Enter a query before searching memory.", "blocked"));
    return;
  }
  target.append(statusBox("Searching memory", payload.query, "running"));
  try {
    const result = await api("/api/v1/memory/retrieve/hybrid", { method: "POST", body: payload });
    clear(target);
    renderMemoryRetrievalResults(target, result);
    showToast("Memory retrieval complete.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory retrieval failed", error.message, "failed"));
    showToast(error.message);
  }
}

function memoryLifecyclePreviewPayload() {
  const payload = {
    limit: Math.trunc(boundedNumber("#memoryLifecycleLimitInput", 100, 1, 500)),
    include_inactive: qs("#memoryLifecycleInactiveInput").checked,
  };
  const entityTypes = splitCsv(qs("#memoryLifecycleEntityTypesInput").value);
  const tags = splitCsv(qs("#memoryLifecycleTagsInput").value);
  const category = qs("#memoryLifecycleCategoryInput").value.trim();
  const retentionPolicy = qs("#memoryLifecycleRetentionInput").value.trim();
  const lifecycleState = qs("#memoryLifecycleStateInput").value.trim();
  if (entityTypes.length) {
    payload.entity_types = entityTypes;
  }
  if (tags.length) {
    payload.tags = tags;
  }
  if (category) {
    payload.category = category;
  }
  if (retentionPolicy) {
    payload.retention_policy = retentionPolicy;
  }
  if (lifecycleState) {
    payload.lifecycle_state = lifecycleState;
  }
  return payload;
}

function lifecycleActionState(action) {
  if (["archive", "soft_prune"].includes(action)) {
    return "blocked";
  }
  if (action === "compress_candidate") {
    return "pending";
  }
  return "ok";
}

function renderMemoryLifecyclePreview(target, result) {
  const decisions = result.decisions || [];
  const applied = result.applied === true;
  target.append(
    statusBox(
      applied ? "Lifecycle applied" : "Lifecycle preview",
      `${result.total ?? decisions.length} decision(s), applied=${applied ? "true" : "false"}`,
      "ok",
    ),
  );
  if (!decisions.length) {
    target.append(statusBox("No lifecycle decisions", "No memory matched the lifecycle filters.", "pending"));
    target.append(jsonBlock(result));
    return;
  }
  const list = make("div", "compact-list");
  for (const decision of decisions.slice(0, 10)) {
    const row = make("div", "list-item");
    row.append(make("div", "item-title", `${decision.entity_type || "memory"}: ${decision.entity_id || "-"}`));
    row.append(
      make(
        "div",
        "item-meta",
        `${decision.current_state || "active"} -> ${decision.recommended_action || "keep"} - freshness ${retrievalScore(
          decision.freshness_score,
        )}`,
      ),
    );
    row.append(make("div", "item-meta", decision.reason || "No reason returned."));
    row.append(statusChip(lifecycleActionState(decision.recommended_action || "keep")));
    list.append(row);
  }
  target.append(list);
  target.append(jsonBlock(result));
}

async function runMemoryLifecyclePreview(event) {
  event.preventDefault();
  const target = qs("#memoryLifecyclePreviewOutput");
  const payload = memoryLifecyclePreviewPayload();
  clear(target);
  target.append(statusBox("Previewing memory lifecycle", `limit ${payload.limit}`, "running"));
  try {
    const result = await api("/api/v1/memory/lifecycle/preview", { method: "POST", body: payload });
    clear(target);
    renderMemoryLifecyclePreview(target, result);
    showToast("Memory lifecycle preview complete.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory lifecycle preview failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function runMemoryLifecycleApply() {
  if (!window.confirm("Apply memory lifecycle changes for the current filters?")) {
    return;
  }
  const target = qs("#memoryLifecyclePreviewOutput");
  const payload = memoryLifecyclePreviewPayload();
  clear(target);
  target.append(statusBox("Applying memory lifecycle", `limit ${payload.limit}`, "running"));
  try {
    const result = await api("/api/v1/memory/lifecycle/apply", { method: "POST", body: payload });
    clear(target);
    renderMemoryLifecyclePreview(target, result);
    await loadReliability();
    showToast("Memory lifecycle apply complete.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory lifecycle apply failed", error.message, "failed"));
    showToast(error.message);
  }
}

function memoryCompressionPreviewPayload() {
  const payload = {
    limit: Math.trunc(boundedNumber("#memoryCompressionLimitInput", 100, 1, 500)),
    compress_after_days: Math.trunc(boundedNumber("#memoryCompressionAgeInput", 30, 1, 3650)),
    compress_access_count_threshold: Math.trunc(boundedNumber("#memoryCompressionAccessInput", 10, 1, 1000000)),
    max_summary_chars: Math.trunc(boundedNumber("#memoryCompressionSummaryInput", 240, 80, 4000)),
    include_inactive: qs("#memoryCompressionInactiveInput").checked,
  };
  const entityTypes = splitCsv(qs("#memoryCompressionEntityTypesInput").value);
  const tags = splitCsv(qs("#memoryCompressionTagsInput").value);
  const category = qs("#memoryCompressionCategoryInput").value.trim();
  const retentionPolicy = qs("#memoryCompressionRetentionInput").value.trim();
  if (entityTypes.length) {
    payload.entity_types = entityTypes;
  }
  if (tags.length) {
    payload.tags = tags;
  }
  if (category) {
    payload.category = category;
  }
  if (retentionPolicy) {
    payload.retention_policy = retentionPolicy;
  }
  return payload;
}

function compressionSavings(candidate) {
  const originalLength = Number(candidate.original_length || 0);
  const compressedLength = Number(candidate.compressed_length || 0);
  const saved = Math.max(0, originalLength - compressedLength);
  return `${saved} chars saved (${originalLength} -> ${compressedLength})`;
}

function renderMemoryCompressionPreview(target, result) {
  const candidates = result.candidates || [];
  const applied = result.applied === true;
  target.append(
    statusBox(
      applied ? "Compression applied" : "Compression preview",
      `${result.total ?? candidates.length} candidate(s), applied=${applied ? "true" : "false"}`,
      "ok",
    ),
  );
  if (!candidates.length) {
    target.append(statusBox("No compression candidates", "No memory matched the compression policy.", "pending"));
    target.append(jsonBlock(result));
    return;
  }
  const list = make("div", "compact-list");
  for (const candidate of candidates.slice(0, 10)) {
    const row = make("div", "list-item");
    row.append(make("div", "item-title", `${candidate.entity_type || "memory"}: ${candidate.entity_id || "-"}`));
    row.append(make("div", "item-meta", compressionSavings(candidate)));
    row.append(make("div", "item-meta", candidate.reason || "No reason returned."));
    if (candidate.compressed_description) {
      row.append(make("div", "item-meta", candidate.compressed_description));
    }
    row.append(statusChip(candidate.embedding_reindexed ? "ok" : "pending"));
    list.append(row);
  }
  target.append(list);
  target.append(jsonBlock(result));
}

async function runMemoryCompressionPreview(event) {
  event.preventDefault();
  const target = qs("#memoryCompressionPreviewOutput");
  const payload = memoryCompressionPreviewPayload();
  clear(target);
  target.append(statusBox("Previewing memory compression", `limit ${payload.limit}`, "running"));
  try {
    const result = await api("/api/v1/memory/compression/preview", { method: "POST", body: payload });
    clear(target);
    renderMemoryCompressionPreview(target, result);
    showToast("Memory compression preview complete.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory compression preview failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function runMemoryCompressionApply() {
  if (!window.confirm("Apply memory compression changes for the current filters?")) {
    return;
  }
  const target = qs("#memoryCompressionPreviewOutput");
  const payload = memoryCompressionPreviewPayload();
  clear(target);
  target.append(statusBox("Applying memory compression", `limit ${payload.limit}`, "running"));
  try {
    const result = await api("/api/v1/memory/compression/apply", { method: "POST", body: payload });
    clear(target);
    renderMemoryCompressionPreview(target, result);
    await loadReliability();
    showToast("Memory compression apply complete.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory compression apply failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function loadReliability() {
  const [memory, registry] = await Promise.all([
    safeLoad("memory metadata", () => api("/api/v1/memory/metadata?limit=50")),
    safeLoad("tool registry", () => api("/api/v1/tools/registry?limit=50")),
  ]);
  renderReliabilitySummary(memory, registry);
  renderMemoryReliability(memory);
  renderToolReliability(registry);
}

function renderReliabilitySummary(memory, registry) {
  const target = qs("#reliabilitySummary");
  clear(target);
  const memoryItems = memory.ok ? memory.data.items || [] : [];
  const registryItems = registry.ok ? registry.data.items || [] : [];
  const memoryTotal = memory.ok ? memory.data.total ?? memoryItems.length : "-";
  const toolTotal = registry.ok ? registry.data.total ?? registryItems.length : "-";
  const activeMemory = memoryItems.filter((item) => item.lifecycle_state === "active").length;
  const lowReliabilityTools = registryItems.filter((tool) => Number(tool.reliability_score ?? 1) < 0.8).length;
  appendKeyValue(target, "Memory", String(memoryTotal));
  appendKeyValue(target, "Active memory", memory.ok ? String(activeMemory) : "-");
  appendKeyValue(target, "Registered tools", String(toolTotal));
  appendKeyValue(target, "Tools needing review", registry.ok ? String(lowReliabilityTools) : "-");
}

function memoryStatusChip(item) {
  const lifecycleState = String(item.lifecycle_state || "active").toLowerCase();
  const freshnessScore = Number(item.freshness_score ?? 1);
  if (["archived", "soft_pruned", "pruned"].includes(lifecycleState)) {
    return "blocked";
  }
  if (freshnessScore < 0.35) {
    return "pending";
  }
  if (["active", "promoted"].includes(lifecycleState)) {
    return "ok";
  }
  return lifecycleState || "pending";
}

function renderMemoryReliability(result) {
  const target = qs("#memoryReliabilityList");
  const detail = qs("#memoryReliabilityDetail");
  clear(target);
  clear(detail);
  if (!result.ok) {
    target.append(statusBox("Memory unavailable", result.error, "blocked"));
    return;
  }
  const items = result.data.items || [];
  if (!items.length) {
    target.append(statusBox("No memory metadata", "Indexed memory records will appear here.", "pending"));
    return;
  }
  const sorted = [...items].sort((left, right) => {
    const leftFreshness = Number(left.freshness_score ?? 1);
    const rightFreshness = Number(right.freshness_score ?? 1);
    return leftFreshness - rightFreshness || Number(right.access_count || 0) - Number(left.access_count || 0);
  });
  for (const item of sorted.slice(0, 8)) {
    const row = make("div", "list-item");
    row.append(make("div", "item-title", `${item.entity_type}: ${item.entity_id}`));
    row.append(
      make(
        "div",
        "item-meta",
        `${item.category || "uncategorized"} - ${item.lifecycle_state || "active"} - freshness ${Number(item.freshness_score ?? 0).toFixed(2)} - accesses ${item.access_count || 0}`,
      ),
    );
    row.append(statusChip(memoryStatusChip(item)));
    const button = make("button", "link-button", "Details");
    button.type = "button";
    button.dataset.testid = "memory-reliability-detail";
    button.dataset.metadataId = item.id || "";
    button.addEventListener("click", () => loadMemoryReliabilityDetail(item.id));
    row.append(button);
    target.append(row);
  }
}

function renderMemoryReliabilityDetail(target, item) {
  target.append(
    statusBox("Memory detail", `${item.entity_type || "memory"}: ${item.entity_id || "-"}`, memoryStatusChip(item)),
  );
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Category", item.category || "-");
  appendKeyValue(grid, "Lifecycle", item.lifecycle_state || "active", memoryStatusChip(item));
  appendKeyValue(grid, "Retention", item.retention_policy || "-");
  appendKeyValue(grid, "Indexed", item.indexed ? "true" : "false", item.indexed ? "ok" : "pending");
  appendKeyValue(grid, "Freshness", retrievalScore(item.freshness_score));
  appendKeyValue(grid, "Relevance", retrievalScore(item.relevance_score));
  appendKeyValue(grid, "Accesses", String(item.access_count || 0));
  appendKeyValue(grid, "Owner", item.owner_agent || "-");
  appendKeyValue(grid, "Updated", formatTimestamp(item.updated_at));
  appendKeyValue(grid, "Last accessed", formatTimestamp(item.last_accessed_at));
  appendKeyValue(grid, "Lifecycle updated", formatTimestamp(item.lifecycle_updated_at));
  appendKeyValue(grid, "Compacted", formatTimestamp(item.last_compacted_at));
  target.append(grid);
  renderChipList(target, "Tags", item.tags || [], "pending");
  if (item.lifecycle_reason) {
    target.append(statusBox("Lifecycle reason", item.lifecycle_reason, "pending"));
  }
  if (item.description) {
    target.append(statusBox("Description", item.description, "ok"));
  }
  target.append(jsonBlock(item));
}

async function loadMemoryReliabilityDetail(metadataId) {
  const target = qs("#memoryReliabilityDetail");
  clear(target);
  if (!metadataId) {
    target.append(
      statusBox("Memory detail unavailable", "The selected row did not include a metadata id.", "blocked"),
    );
    return;
  }
  target.append(statusBox("Loading memory detail", metadataId, "running"));
  try {
    const item = await api(`/api/v1/memory/metadata/${encodeURIComponent(metadataId)}`);
    clear(target);
    renderMemoryReliabilityDetail(target, item);
    showToast("Memory detail loaded.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Memory detail failed", error.message, "failed"));
    showToast(error.message);
  }
}

function toolReliabilityStatus(tool) {
  if (tool.deprecated) {
    return "blocked";
  }
  const score = Number(tool.reliability_score ?? 1);
  if (score < 0.5) {
    return "failed";
  }
  if (score < 0.8 || Number(tool.failure_count || 0) > 0) {
    return "pending";
  }
  return "ok";
}

function renderToolReliability(result) {
  const target = qs("#toolReliabilityList");
  const detail = qs("#toolReliabilityDetail");
  clear(target);
  clear(detail);
  if (!result.ok) {
    target.append(statusBox("Tool registry unavailable", result.error, "blocked"));
    return;
  }
  const tools = result.data.items || [];
  if (!tools.length) {
    target.append(statusBox("No registered tools", "Generated-tool registry rows will appear here.", "pending"));
    return;
  }
  const sorted = [...tools].sort((left, right) => {
    const leftStatus = left.deprecated ? -1 : Number(left.reliability_score ?? 1);
    const rightStatus = right.deprecated ? -1 : Number(right.reliability_score ?? 1);
    return leftStatus - rightStatus || Number(right.failure_count || 0) - Number(left.failure_count || 0);
  });
  for (const tool of sorted.slice(0, 8)) {
    const row = make("div", "list-item");
    row.append(make("div", "item-title", `${tool.tool_name} ${tool.version}`));
    row.append(
      make(
        "div",
        "item-meta",
        `${tool.permission_level} - reliability ${Number(tool.reliability_score ?? 0).toFixed(2)} - usage ${tool.usage_count || 0} - failures ${tool.failure_count || 0}`,
      ),
    );
    row.append(statusChip(toolReliabilityStatus(tool)));
    const button = make("button", "link-button", "Details");
    button.type = "button";
    button.dataset.testid = "tool-reliability-detail";
    button.dataset.toolId = tool.id || "";
    button.addEventListener("click", () => loadToolReliabilityDetail(tool.id));
    row.append(button);
    target.append(row);
  }
}

function renderToolReliabilityDetail(target, tool) {
  target.append(
    statusBox("Tool detail", `${tool.tool_name || "tool"} ${tool.version || ""}`.trim(), toolReliabilityStatus(tool)),
  );
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Permission", tool.permission_level || "-");
  appendKeyValue(grid, "Reliability", retrievalScore(tool.reliability_score));
  appendKeyValue(grid, "Usage", String(tool.usage_count || 0));
  appendKeyValue(grid, "Successes", String(tool.success_count || 0));
  appendKeyValue(grid, "Failures", String(tool.failure_count || 0), Number(tool.failure_count || 0) ? "pending" : "ok");
  appendKeyValue(grid, "Deprecated", tool.deprecated ? "true" : "false", tool.deprecated ? "blocked" : "ok");
  appendKeyValue(grid, "Source", compactPath(tool.source_path || "-"));
  appendKeyValue(grid, "Created by", tool.created_by_agent || "-");
  appendKeyValue(grid, "Updated", formatTimestamp(tool.updated_at));
  appendKeyValue(grid, "Last used", formatTimestamp(tool.last_used_at));
  target.append(grid);
  renderChipList(target, "Tags", tool.tags || [], "pending");
  if (tool.description) {
    target.append(statusBox("Description", tool.description, "ok"));
  }
  target.append(jsonBlock(tool));
}

async function loadToolReliabilityDetail(toolId) {
  const target = qs("#toolReliabilityDetail");
  clear(target);
  if (!toolId) {
    target.append(statusBox("Tool detail unavailable", "The selected row did not include a tool id.", "blocked"));
    return;
  }
  target.append(statusBox("Loading tool detail", toolId, "running"));
  try {
    const tool = await api(`/api/v1/tools/registry/${encodeURIComponent(toolId)}`);
    clear(target);
    renderToolReliabilityDetail(target, tool);
    showToast("Tool detail loaded.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Tool detail failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function loadCliRuns() {
  const result = await safeLoad("cli runs", () => api("/cli/runs"));
  const target = qs("#cliRunList");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("CLI runs unavailable", result.error, "blocked"));
    return;
  }
  const runs = result.data.slice(-10).reverse();
  if (!runs.length) {
    target.append(statusBox("No CLI runs", "Executed commands will appear here.", "pending"));
    clear(qs("#cliRunOutput"));
    return;
  }
  for (const run of runs) {
    const item = make("div", "list-item");
    item.append(make("div", "item-title", run.command || run.id));
    item.append(make("div", "item-meta", `${run.id} - exit ${run.exit_code ?? "-"} - ${run.cwd}`));
    item.append(statusChip(run.status));
    const button = make("button", "link-button", "Output");
    button.type = "button";
    button.addEventListener("click", () => loadCliRunOutput(run.id));
    item.append(button);
    target.append(item);
  }
}

async function loadCliRunOutput(runId) {
  const target = qs("#cliRunOutput");
  clear(target);
  target.append(statusBox("Loading CLI output", runId, "running"));
  try {
    const output = await api(`/cli/runs/${encodeURIComponent(runId)}/output`);
    clear(target);
    target.append(statusBox("CLI output", `${runId} - next sequence ${output.next_sequence}`, output.status));
    const lines = (output.chunks || []).map((chunk) => {
      const marker = chunk.truncated ? " truncated" : "";
      return `[${chunk.sequence}] ${chunk.stream}${marker}\n${chunk.text}`;
    });
    const pre = make("pre");
    pre.textContent = lines.join("\n\n") || "No output chunks recorded.";
    target.append(pre);
  } catch (error) {
    clear(target);
    target.append(statusBox("Output unavailable", error.message, "failed"));
  }
}

async function loadPolicySurfaces() {
  const [cliRules, recipes, hooks, plugins] = await Promise.all([
    safeLoad("CLI rules", () => api("/cli/policy/rules")),
    safeLoad("recipes", () => api("/cli/recipes")),
    safeLoad("hooks", () => api("/guardrails/hooks/rules")),
    safeLoad("plugins", () => api("/plugins")),
  ]);
  renderPolicyReviewSummary(cliRules, recipes, hooks, plugins);
  renderCliPolicyList(cliRules);
  renderRecipeList(recipes);
  renderHookPolicyList(hooks);
  renderPluginList(plugins);
}

function resultList(result, nestedKey = "") {
  if (!result?.ok) {
    return [];
  }
  if (Array.isArray(result.data)) {
    return result.data;
  }
  if (nestedKey && Array.isArray(result.data?.[nestedKey])) {
    return result.data[nestedKey];
  }
  return [];
}

function countBy(records, getter) {
  const counts = {};
  for (const record of records || []) {
    const key = getter(record) || "unknown";
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function disabledCount(records) {
  return (records || []).filter((record) => record.enabled === false || record.status === "disabled").length;
}

function managedPolicyLocks() {
  return parseSettingList(settingByName(latestSettingsView, "managed_policy_locks"));
}

function splitCsv(value) {
  return String(value || "")
    .split(/[\n,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderPolicyReviewSummary(cliRules, recipes, hooks, plugins) {
  if (arguments.length) {
    latestPolicyReviewResults = { cliRules, recipes, hooks, plugins };
  } else if (latestPolicyReviewResults) {
    ({ cliRules, recipes, hooks, plugins } = latestPolicyReviewResults);
  }
  const target = qs("#policyReviewSummary");
  if (!target) {
    return;
  }
  clear(target);
  if (!latestPolicyReviewResults) {
    target.append(statusBox("Policy review", "Waiting for policy surfaces.", "pending"));
    return;
  }

  const cliRecords = resultList(cliRules);
  const recipeRecords = resultList(recipes);
  const hookRecords = resultList(hooks);
  const pluginRecords = resultList(plugins, "plugins");
  const locks = parseSettingList(settingByName(latestSettingsView, "managed_policy_locks"));
  appendPolicyReviewCard(target, "CLI rules", cliRules, cliRecords, "source");
  appendPolicyReviewCard(target, "Recipes", recipes, recipeRecords, "source");
  appendPolicyReviewCard(target, "Hook policies", hooks, hookRecords, "source");
  appendPolicyReviewCard(target, "Plugins", plugins, pluginRecords, "trust_source");
  appendKeyValue(target, "Managed locks", locks.length ? String(locks.length) : "None", locks.length ? "locked" : "");
  appendKeyValue(
    target,
    "Disabled records",
    String(disabledCount(cliRecords) + disabledCount(recipeRecords) + disabledCount(hookRecords)),
  );
  renderChipList(target, "Locked surfaces", locks, "locked");
}

function appendPolicyReviewCard(target, label, result, records, sourceField) {
  if (!result?.ok) {
    target.append(statusBox(label, result?.error || "Unavailable", "blocked"));
    return;
  }
  const detailParts = [`total: ${records.length}`];
  const counts = countBy(records, (record) => record[sourceField] || record.source || "local");
  const sourceText = compactCounts(counts);
  if (sourceText !== "-") {
    detailParts.push(sourceText);
  }
  const disabled = disabledCount(records);
  if (disabled) {
    detailParts.push(`disabled: ${disabled}`);
  }
  appendKeyValue(target, label, detailParts.join(" | "), records.length ? "ok" : "pending");
}

function networkPolicyCheckEndpoint() {
  return qs("#networkPolicySurfaceInput").value === "web_retrieval"
    ? "/web-retrieval/network/check"
    : "/guardrails/network";
}

function networkPolicyApprovalRequest() {
  const url = qs("#networkPolicyUrlInput").value.trim();
  if (qs("#networkPolicySurfaceInput").value === "web_retrieval") {
    return {
      endpoint: "/web-retrieval/network/approvals",
      body: { url },
    };
  }
  return {
    endpoint: "/network/approvals",
    body: { url, surface: "provider", action: "request" },
  };
}

function networkPolicyDecisionState(decision) {
  if (decision.mode === "approval_required") {
    return "pending";
  }
  return decision.allowed ? "ok" : "blocked";
}

function renderNetworkPolicyDecision(target, decision) {
  const modeState = networkPolicyDecisionState(decision);
  target.append(statusBox("Network policy decision", decision.reason || decision.url, modeState));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Mode", decision.mode || "unknown", decision.mode || "");
  appendKeyValue(grid, "Host", decision.host || "-", modeState);
  appendKeyValue(grid, "Review URL", decision.url || "-");
  appendKeyValue(grid, "Matched domain", decision.matched_domain || "-");
  appendKeyValue(grid, "Matched rule", decision.matched_rule_id || "-");
  appendKeyValue(grid, "Rule source", decision.matched_rule_source || "-");
  if (decision.hook_policy) {
    appendKeyValue(grid, "Hook policy", decision.hook_policy.effect || "matched", decision.hook_policy.effect || "");
  }
  target.append(grid);
  target.append(jsonBlock(decision));
}

function filesystemPolicyPayload() {
  const payload = {
    action: qs("#filesystemPolicyActionInput").value,
    path: qs("#filesystemPolicyPathInput").value.trim() || ".",
  };
  const targetPath = qs("#filesystemPolicyTargetInput").value.trim();
  const agentRole = qs("#filesystemPolicyRoleInput").value.trim();
  const agentId = qs("#filesystemPolicyAgentInput").value.trim();
  const taskId = qs("#filesystemPolicyTaskInput").value.trim();
  if (targetPath) {
    payload.target_path = targetPath;
  }
  if (agentRole) {
    payload.agent_role = agentRole;
  }
  if (agentId) {
    payload.agent_id = agentId;
  }
  if (taskId) {
    payload.task_id = taskId;
  }
  return payload;
}

function filesystemPolicyPayloadKey(payload) {
  return JSON.stringify(payload);
}

function filesystemPolicyApprovalRequest(payload) {
  return {
    endpoint: "/filesystem/approvals",
    body: { ...payload },
  };
}

function filesystemDecisionState(decision) {
  if (decision.permission_mode === "approval_required") {
    return "pending";
  }
  return decision.allowed ? "ok" : "blocked";
}

function renderFilesystemPolicyDecision(target, decision) {
  const state = filesystemDecisionState(decision);
  target.append(statusBox("Filesystem guardrail decision", decision.reason || "Policy evaluated.", state));
  const grid = make("div", "checkpoint-grid");
  appendKeyValue(grid, "Allowed", decision.allowed ? "true" : "false", state);
  appendKeyValue(grid, "Mode", decision.permission_mode || "unknown", decision.permission_mode || "");
  appendKeyValue(grid, "Path", compactPath(decision.path || "-"));
  appendKeyValue(grid, "Resolved", compactPath(decision.resolved_path || "-"));
  appendKeyValue(grid, "Target", compactPath(decision.target_path || "-"));
  appendKeyValue(grid, "Resolved target", compactPath(decision.resolved_target_path || "-"));
  if (decision.orchestration) {
    appendKeyValue(
      grid,
      "Orchestration",
      decision.orchestration.allowed ? "allowed" : "blocked",
      decision.orchestration.allowed ? "ok" : "blocked",
    );
  }
  if (decision.hook_policy) {
    appendKeyValue(
      grid,
      "Hook policy",
      decision.hook_policy.effect || "matched",
      decision.hook_policy.effect || "",
    );
  }
  target.append(grid);
  target.append(jsonBlock(decision));
}

async function checkFilesystemPolicy(event) {
  event.preventDefault();
  const target = qs("#filesystemPolicyCheckOutput");
  const approvalButton = qs("#filesystemPolicyApprovalButton");
  const payload = filesystemPolicyPayload();
  latestFilesystemPolicyPreflight = null;
  approvalButton.disabled = true;
  clear(target);
  target.append(statusBox("Checking filesystem guardrail", `${payload.action} ${payload.path}`, "running"));
  try {
    const decision = await api("/guardrails/filesystem", { method: "POST", body: payload });
    clear(target);
    latestFilesystemPolicyPreflight = {
      payload,
      payloadKey: filesystemPolicyPayloadKey(payload),
      decision,
    };
    approvalButton.disabled = decision.permission_mode !== "approval_required";
    renderFilesystemPolicyDecision(target, decision);
    showToast("Filesystem guardrail checked.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Filesystem guardrail check failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function requestFilesystemPolicyApproval() {
  const target = qs("#filesystemPolicyCheckOutput");
  const approvalButton = qs("#filesystemPolicyApprovalButton");
  const payload = filesystemPolicyPayload();
  if (
    !latestFilesystemPolicyPreflight ||
    latestFilesystemPolicyPreflight.payloadKey !== filesystemPolicyPayloadKey(payload) ||
    latestFilesystemPolicyPreflight.decision.permission_mode !== "approval_required"
  ) {
    clear(target);
    target.append(
      statusBox(
        "Approval requires a fresh filesystem check",
        `${payload.action} ${payload.path}`,
        "blocked",
      ),
    );
    approvalButton.disabled = true;
    return;
  }
  const request = filesystemPolicyApprovalRequest(payload);
  clear(target);
  target.append(
    statusBox("Creating filesystem approval", `${payload.action} ${payload.path}`, "running"),
  );
  try {
    const approval = await api(request.endpoint, {
      method: "POST",
      body: request.body,
    });
    latestFilesystemPolicyPreflight = null;
    approvalButton.disabled = true;
    clear(target);
    target.append(statusBox("Filesystem approval created", approval.id, "pending"));
    target.append(jsonBlock(approval));
    await Promise.all([loadApprovals(), loadTaskChatContext()]);
    showToast("Filesystem approval created.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Filesystem approval failed", error.message, "failed"));
    showToast(error.message);
  }
}

function resetFilesystemPolicyApprovalState() {
  latestFilesystemPolicyPreflight = null;
  qs("#filesystemPolicyApprovalButton").disabled = true;
}

async function checkNetworkPolicy(event) {
  event.preventDefault();
  const target = qs("#networkPolicyCheckOutput");
  const approvalButton = qs("#networkPolicyApprovalButton");
  const url = qs("#networkPolicyUrlInput").value.trim();
  const surface = qs("#networkPolicySurfaceInput").value;
  latestNetworkPolicyPreflight = null;
  approvalButton.disabled = true;
  clear(target);
  target.append(statusBox("Checking network policy", url, "running"));
  try {
    const decision = await api(networkPolicyCheckEndpoint(), {
      method: "POST",
      body: { url },
    });
    clear(target);
    latestNetworkPolicyPreflight = { url, surface, decision };
    approvalButton.disabled = decision.mode !== "approval_required";
    renderNetworkPolicyDecision(target, decision);
    showToast("Network policy checked.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Network policy check failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function requestNetworkPolicyApproval() {
  const target = qs("#networkPolicyCheckOutput");
  const approvalButton = qs("#networkPolicyApprovalButton");
  const url = qs("#networkPolicyUrlInput").value.trim();
  const surface = qs("#networkPolicySurfaceInput").value;
  if (
    !latestNetworkPolicyPreflight ||
    latestNetworkPolicyPreflight.url !== url ||
    latestNetworkPolicyPreflight.surface !== surface ||
    latestNetworkPolicyPreflight.decision.mode !== "approval_required"
  ) {
    clear(target);
    target.append(statusBox("Approval requires a fresh check", url || "URL is missing.", "blocked"));
    approvalButton.disabled = true;
    return;
  }
  const request = networkPolicyApprovalRequest();
  clear(target);
  target.append(statusBox("Creating network approval", url, "running"));
  try {
    const approval = await api(request.endpoint, {
      method: "POST",
      body: request.body,
    });
    approvalButton.disabled = true;
    clear(target);
    target.append(statusBox("Network approval created", approval.id, "pending"));
    target.append(jsonBlock(approval));
    await loadApprovals();
    showToast("Network approval created.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Network approval failed", error.message, "failed"));
    showToast(error.message);
  }
}

function cliPolicyRulePayload() {
  const priority = Number(qs("#cliPolicyPriorityInput").value || 100);
  return {
    name: qs("#cliPolicyNameInput").value.trim(),
    match_type: qs("#cliPolicyMatchInput").value,
    pattern: qs("#cliPolicyPatternInput").value.trim(),
    permission_mode: qs("#cliPolicyModeInput").value,
    reason: qs("#cliPolicyReasonInput").value.trim(),
    agent_roles: splitCsv(qs("#cliPolicyRolesInput").value),
    enabled: qs("#cliPolicyEnabledInput").checked,
    priority: Number.isFinite(priority) ? priority : 100,
  };
}

async function createCliPolicyRule(event) {
  event.preventDefault();
  const target = qs("#cliPolicyEditorOutput");
  const payload = cliPolicyRulePayload();
  clear(target);
  const isEditing = Boolean(editingCliPolicyRuleId);
  target.append(statusBox(isEditing ? "Updating CLI rule" : "Creating CLI rule", payload.name || "policy", "running"));
  try {
    const rule = isEditing
      ? await api(`/cli/policy/rules/${encodeURIComponent(editingCliPolicyRuleId)}`, {
          method: "PATCH",
          body: payload,
        })
      : await api("/cli/policy/rules", { method: "POST", body: payload });
    resetCliPolicyForm();
    clear(target);
    target.append(
      statusBox(isEditing ? "CLI rule updated" : "CLI rule created", rule.name || rule.id, rule.enabled === false ? "blocked" : "ok"),
    );
    target.append(jsonBlock(rule));
    await loadPolicySurfaces();
    showToast(isEditing ? "CLI policy rule updated." : "CLI policy rule created.");
  } catch (error) {
    clear(target);
    target.append(statusBox(isEditing ? "CLI rule update failed" : "CLI rule create failed", error.message, "failed"));
    showToast(error.message);
  }
}

function resetCliPolicyForm() {
  editingCliPolicyRuleId = "";
  qs("#cliPolicyForm").reset();
  qs("#cliPolicyPriorityInput").value = "100";
  qs("#cliPolicyEnabledInput").checked = true;
  qs("#cliPolicyEditorSummary").textContent = "New CLI Rule";
  qs("#cliPolicySubmitLabel").textContent = "Add Rule";
  qs("#cliPolicyCancelEditButton").hidden = true;
}

function editCliPolicyRule(rule) {
  editingCliPolicyRuleId = rule.id || "";
  qs("#cliPolicyEditor").open = true;
  qs("#cliPolicyEditorSummary").textContent = `Edit CLI Rule: ${rule.name || rule.id}`;
  qs("#cliPolicyNameInput").value = rule.name || "";
  qs("#cliPolicyMatchInput").value = rule.match_type || "executable";
  qs("#cliPolicyModeInput").value = rule.permission_mode || "approval_required";
  qs("#cliPolicyPatternInput").value = rule.pattern || "";
  qs("#cliPolicyReasonInput").value = rule.reason || "";
  qs("#cliPolicyRolesInput").value = (rule.agent_roles || []).join(", ");
  qs("#cliPolicyPriorityInput").value = String(rule.priority ?? 100);
  qs("#cliPolicyEnabledInput").checked = rule.enabled !== false;
  qs("#cliPolicySubmitLabel").textContent = "Update Rule";
  qs("#cliPolicyCancelEditButton").hidden = false;
  clear(qs("#cliPolicyEditorOutput"));
  qs("#cliPolicyEditorOutput").append(statusBox("Editing CLI rule", rule.id || rule.name, "pending"));
}

async function patchCliPolicyRule(ruleId, update) {
  const target = qs("#cliPolicyEditorOutput");
  clear(target);
  target.append(statusBox("Updating CLI rule", ruleId, "running"));
  try {
    const rule = await api(`/cli/policy/rules/${encodeURIComponent(ruleId)}`, {
      method: "PATCH",
      body: update,
    });
    clear(target);
    target.append(statusBox("CLI rule updated", rule.name || rule.id, rule.enabled === false ? "blocked" : "ok"));
    target.append(jsonBlock(rule));
    await loadPolicySurfaces();
    showToast("CLI policy rule updated.");
  } catch (error) {
    clear(target);
    target.append(statusBox("CLI rule update failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderCliPolicyList(result) {
  const target = qs("#cliPolicyList");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  if (!result.data.length) {
    target.append(statusBox("No records", "Nothing configured for this surface.", "pending"));
    return;
  }
  const cliPolicyLocked = managedPolicyLocks().includes("cli_policy");
  for (const rule of result.data.slice(0, 8)) {
    const item = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", rule.name || rule.id));
    detail.append(
      make(
        "div",
        "item-meta",
        `${rule.source || "local"} - ${rule.permission_mode || "policy"} - ${rule.match_type || "-"} - priority ${
          rule.priority ?? 100
        }`,
      ),
    );
    const actions = make("div", "recipe-action-buttons");
    const editButton = make("button", "link-button", "Edit");
    editButton.type = "button";
    editButton.dataset.testid = "cli-policy-edit";
    editButton.dataset.ruleId = rule.id || "";
    editButton.disabled = rule.source === "managed" || cliPolicyLocked;
    editButton.addEventListener("click", () => editCliPolicyRule(rule));
    const toggleButton = make("button", rule.enabled === false ? "success-button" : "danger-button", rule.enabled === false ? "Enable" : "Disable");
    toggleButton.type = "button";
    toggleButton.dataset.testid = "cli-policy-toggle";
    toggleButton.dataset.ruleId = rule.id || "";
    toggleButton.disabled = rule.source === "managed" || cliPolicyLocked;
    toggleButton.addEventListener("click", () => patchCliPolicyRule(rule.id, { enabled: rule.enabled === false }));
    actions.append(statusChip(rule.enabled === false ? "blocked" : "ok"), editButton, toggleButton);
    item.append(detail, actions);
    target.append(item);
  }
}

function hookPolicyRulePayload() {
  const priority = Number(qs("#hookPolicyPriorityInput").value || 100);
  return {
    name: qs("#hookPolicyNameInput").value.trim(),
    surface: qs("#hookPolicySurfaceInput").value,
    action: qs("#hookPolicyActionInput").value.trim() || "*",
    match_type: qs("#hookPolicyMatchInput").value,
    pattern: qs("#hookPolicyPatternInput").value.trim(),
    effect: qs("#hookPolicyEffectInput").value,
    reason: qs("#hookPolicyReasonInput").value.trim(),
    agent_roles: splitCsv(qs("#hookPolicyRolesInput").value),
    enabled: qs("#hookPolicyEnabledInput").checked,
    priority: Number.isFinite(priority) ? priority : 100,
  };
}

function validateHookPolicyRulePayload(payload) {
  if (payload.match_type !== "any" && !payload.pattern) {
    return "Pattern is required unless match is Any.";
  }
  return "";
}

function updateHookPolicyPatternRequirement() {
  const patternInput = qs("#hookPolicyPatternInput");
  const requiresPattern = qs("#hookPolicyMatchInput").value !== "any";
  patternInput.required = requiresPattern;
  patternInput.placeholder = requiresPattern ? "Text to match" : "Optional for any match";
  if (!requiresPattern) {
    patternInput.setCustomValidity("");
  }
}

async function createHookPolicyRule(event) {
  event.preventDefault();
  const target = qs("#hookPolicyEditorOutput");
  const hookPolicyLocked = managedPolicyLocks().includes("hook_policy");
  clear(target);
  if (hookPolicyLocked) {
    target.append(statusBox("Hook policy locked", "Managed settings make hook policy read-only.", "blocked"));
    return;
  }
  const payload = hookPolicyRulePayload();
  const validationError = validateHookPolicyRulePayload(payload);
  if (validationError) {
    target.append(statusBox("Hook rule validation failed", validationError, "failed"));
    return;
  }
  const isEditing = Boolean(editingHookPolicyRuleId);
  target.append(statusBox(isEditing ? "Updating hook rule" : "Creating hook rule", payload.name || "policy", "running"));
  try {
    const rule = isEditing
      ? await api(`/guardrails/hooks/rules/${encodeURIComponent(editingHookPolicyRuleId)}`, {
          method: "PATCH",
          body: payload,
        })
      : await api("/guardrails/hooks/rules", { method: "POST", body: payload });
    resetHookPolicyForm();
    clear(target);
    target.append(
      statusBox(isEditing ? "Hook rule updated" : "Hook rule created", rule.name || rule.id, rule.enabled === false ? "blocked" : "ok"),
    );
    target.append(jsonBlock(rule));
    await loadPolicySurfaces();
    showToast(isEditing ? "Hook policy rule updated." : "Hook policy rule created.");
  } catch (error) {
    clear(target);
    target.append(statusBox(isEditing ? "Hook rule update failed" : "Hook rule create failed", error.message, "failed"));
    showToast(error.message);
  }
}

function resetHookPolicyForm() {
  editingHookPolicyRuleId = "";
  qs("#hookPolicyForm").reset();
  qs("#hookPolicyActionInput").value = "*";
  qs("#hookPolicyPriorityInput").value = "100";
  qs("#hookPolicyEnabledInput").checked = true;
  qs("#hookPolicyEditorSummary").textContent = "New Hook Rule";
  qs("#hookPolicySubmitLabel").textContent = "Add Rule";
  qs("#hookPolicyCancelEditButton").hidden = true;
  updateHookPolicyPatternRequirement();
}

function editHookPolicyRule(rule) {
  editingHookPolicyRuleId = rule.id || "";
  qs("#hookPolicyEditor").open = true;
  qs("#hookPolicyEditorSummary").textContent = `Edit Hook Rule: ${rule.name || rule.id}`;
  qs("#hookPolicyNameInput").value = rule.name || "";
  qs("#hookPolicySurfaceInput").value = rule.surface || "command";
  qs("#hookPolicyActionInput").value = rule.action || "*";
  qs("#hookPolicyMatchInput").value = rule.match_type || "contains";
  qs("#hookPolicyPatternInput").value = rule.pattern || "";
  qs("#hookPolicyEffectInput").value = rule.effect || "audit";
  qs("#hookPolicyReasonInput").value = rule.reason || "";
  qs("#hookPolicyRolesInput").value = (rule.agent_roles || []).join(", ");
  qs("#hookPolicyPriorityInput").value = String(rule.priority ?? 100);
  qs("#hookPolicyEnabledInput").checked = rule.enabled !== false;
  qs("#hookPolicySubmitLabel").textContent = "Update Rule";
  qs("#hookPolicyCancelEditButton").hidden = false;
  updateHookPolicyPatternRequirement();
  clear(qs("#hookPolicyEditorOutput"));
  qs("#hookPolicyEditorOutput").append(statusBox("Editing hook rule", rule.id || rule.name, "pending"));
}

async function patchHookPolicyRule(ruleId, update) {
  const target = qs("#hookPolicyEditorOutput");
  const hookPolicyLocked = managedPolicyLocks().includes("hook_policy");
  clear(target);
  if (hookPolicyLocked) {
    target.append(statusBox("Hook policy locked", "Managed settings make hook policy read-only.", "blocked"));
    return;
  }
  target.append(statusBox("Updating hook rule", ruleId, "running"));
  try {
    const rule = await api(`/guardrails/hooks/rules/${encodeURIComponent(ruleId)}`, {
      method: "PATCH",
      body: update,
    });
    clear(target);
    target.append(statusBox("Hook rule updated", rule.name || rule.id, rule.enabled === false ? "blocked" : "ok"));
    target.append(jsonBlock(rule));
    await loadPolicySurfaces();
    showToast("Hook policy rule updated.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Hook rule update failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderHookPolicyList(result) {
  const target = qs("#hookPolicyList");
  clear(target);
  const hookPolicyLocked = managedPolicyLocks().includes("hook_policy");
  qs("#hookPolicySubmitButton").disabled = hookPolicyLocked;
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  if (hookPolicyLocked) {
    target.append(statusBox("Hook policy locked", "Managed settings make hook policy read-only.", "blocked"));
  }
  if (!result.data.length) {
    target.append(statusBox("No records", "Nothing configured for this surface.", "pending"));
    return;
  }
  for (const rule of result.data.slice(0, 8)) {
    const item = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", rule.name || rule.id));
    detail.append(
      make(
        "div",
        "item-meta",
        `${rule.source || "local"} - ${rule.surface || "-"} - ${rule.effect || "-"} - ${rule.match_type || "-"} - priority ${
          rule.priority ?? 100
        }`,
      ),
    );
    const actions = make("div", "recipe-action-buttons");
    const editButton = make("button", "link-button", "Edit");
    editButton.type = "button";
    editButton.dataset.testid = "hook-policy-edit";
    editButton.dataset.ruleId = rule.id || "";
    editButton.disabled = rule.source !== "local" || hookPolicyLocked;
    editButton.addEventListener("click", () => editHookPolicyRule(rule));
    const toggleButton = make("button", rule.enabled === false ? "success-button" : "danger-button", rule.enabled === false ? "Enable" : "Disable");
    toggleButton.type = "button";
    toggleButton.dataset.testid = "hook-policy-toggle";
    toggleButton.dataset.ruleId = rule.id || "";
    toggleButton.disabled = rule.source !== "local" || hookPolicyLocked;
    toggleButton.addEventListener("click", () => patchHookPolicyRule(rule.id, { enabled: rule.enabled === false }));
    actions.append(statusChip(rule.enabled === false ? "blocked" : "ok"), editButton, toggleButton);
    item.append(detail, actions);
    target.append(item);
  }
}

function renderPolicyList(target, result, mapper) {
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  if (!result.data.length) {
    target.append(statusBox("No records", "Nothing configured for this surface.", "pending"));
    return;
  }
  for (const record of result.data.slice(0, 8)) {
    const mapped = mapper(record);
    const item = make("div", "list-item");
    item.append(make("div", "item-title", mapped.title || "record"));
    item.append(make("div", "item-meta", mapped.meta || ""));
    item.append(statusChip(mapped.status || "ok"));
    target.append(item);
  }
}

function pluginRecordsFromResult(result) {
  return result.ok ? result.data.plugins || [] : [];
}

function pluginTrustLocked() {
  return managedPolicyLocks().includes("plugin_trust");
}

async function patchPluginTrust(pluginId, status) {
  const target = qs("#pluginTrustOutput");
  const locked = pluginTrustLocked();
  clear(target);
  if (locked) {
    target.append(statusBox("Plugin trust locked", "Managed settings make plugin trust read-only.", "blocked"));
    return;
  }
  const reason = qs("#pluginTrustReasonInput").value.trim() || "Reviewed from dashboard.";
  target.append(statusBox(status === "trusted" ? "Trusting plugin" : "Blocking plugin", pluginId, "running"));
  try {
    const plugin = await api(`/plugins/${encodeURIComponent(pluginId)}/trust`, {
      method: "PATCH",
      body: { status, reason },
    });
    clear(target);
    target.append(statusBox("Plugin trust updated", plugin.plugin_id || pluginId, plugin.trust_status === "trusted" ? "ok" : "blocked"));
    target.append(jsonBlock(plugin));
    await loadPolicySurfaces();
    showToast("Plugin trust updated.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Plugin trust update failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderPluginList(result) {
  const target = qs("#pluginList");
  const output = qs("#pluginTrustOutput");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  const locked = pluginTrustLocked();
  const plugins = pluginRecordsFromResult(result);
  const errors = result.data?.errors || [];
  if (locked) {
    target.append(statusBox("Plugin trust locked", "Managed settings make plugin trust read-only.", "blocked"));
  }
  if (!plugins.length && !errors.length) {
    target.append(statusBox("No plugins", "Nothing configured for this surface.", "pending"));
    return;
  }
  for (const plugin of plugins.slice(0, 8)) {
    const item = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", plugin.name || plugin.plugin_id));
    detail.append(
      make(
        "div",
        "item-meta",
        `${plugin.plugin_id} - ${plugin.trust_status || "untrusted"} - ${
          plugin.trust_source || "none"
        } - ${plugin.version || "-"}`,
      ),
    );
    const actions = make("div", "recipe-action-buttons");
    const trustButton = make("button", "success-button", "Trust");
    trustButton.type = "button";
    trustButton.dataset.testid = "plugin-trust-trust";
    trustButton.dataset.pluginId = plugin.plugin_id || "";
    trustButton.disabled = locked || plugin.trust_source === "managed" || plugin.trust_status === "trusted";
    trustButton.addEventListener("click", () => patchPluginTrust(plugin.plugin_id, "trusted"));
    const blockButton = make("button", "danger-button", "Block");
    blockButton.type = "button";
    blockButton.dataset.testid = "plugin-trust-block";
    blockButton.dataset.pluginId = plugin.plugin_id || "";
    blockButton.disabled = locked || plugin.trust_source === "managed" || plugin.trust_status === "blocked";
    blockButton.addEventListener("click", () => patchPluginTrust(plugin.plugin_id, "blocked"));
    actions.append(statusChip(plugin.trust_status === "trusted" ? "ok" : plugin.trust_status || "pending"), trustButton, blockButton);
    item.append(detail, actions);
    target.append(item);
  }
  for (const error of errors.slice(0, 4)) {
    target.append(statusBox(error.plugin_id || "Plugin error", error.reason || error.manifest_path, "blocked"));
  }
  if (!output.childNodes.length && locked) {
    output.append(statusBox("Plugin trust locked", "Managed settings make plugin trust read-only.", "blocked"));
  }
}

function appendCommandRecipeParameterRow(parameter = {}) {
  const target = qs("#recipeParameterBuilder");
  const row = make("div", "recipe-parameter-row");

  const nameLabel = make("label");
  nameLabel.append(document.createTextNode("Name"));
  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.maxLength = 64;
  nameInput.value = parameter.name || "";
  nameInput.dataset.recipeParameterField = "name";
  nameLabel.append(nameInput);

  const descriptionLabel = make("label");
  descriptionLabel.append(document.createTextNode("Description"));
  const descriptionInput = document.createElement("input");
  descriptionInput.type = "text";
  descriptionInput.maxLength = 300;
  descriptionInput.value = parameter.description || "";
  descriptionInput.dataset.recipeParameterField = "description";
  descriptionLabel.append(descriptionInput);

  const defaultLabel = make("label");
  defaultLabel.append(document.createTextNode("Default"));
  const defaultInput = document.createElement("input");
  defaultInput.type = "text";
  defaultInput.maxLength = 256;
  defaultInput.value = parameter.default || "";
  defaultInput.dataset.recipeParameterField = "default";
  defaultLabel.append(defaultInput);

  const requiredLabel = make("label", "checkbox-label");
  const requiredInput = document.createElement("input");
  requiredInput.type = "checkbox";
  requiredInput.checked = parameter.required !== false;
  requiredInput.dataset.recipeParameterField = "required";
  requiredLabel.append(requiredInput, document.createTextNode("Required"));

  const removeButton = make("button", "link-button", "Remove");
  removeButton.type = "button";
  removeButton.addEventListener("click", () => row.remove());

  row.append(nameLabel, descriptionLabel, defaultLabel, requiredLabel, removeButton);
  target.append(row);
}

function commandRecipeEditorParameters() {
  const parameters = [];
  for (const row of qsa("#recipeParameterBuilder .recipe-parameter-row")) {
    const name = row.querySelector('[data-recipe-parameter-field="name"]').value.trim();
    if (!name) {
      continue;
    }
    const description = row.querySelector('[data-recipe-parameter-field="description"]').value.trim();
    const defaultValue = row.querySelector('[data-recipe-parameter-field="default"]').value.trim();
    const parameter = {
      name,
      description,
      required: row.querySelector('[data-recipe-parameter-field="required"]').checked,
    };
    if (defaultValue) {
      parameter.default = defaultValue;
    }
    parameters.push(parameter);
  }
  return parameters;
}

function commandRecipeEditorPayload({ includeId = true } = {}) {
  const timeout = Number(qs("#recipeTimeoutInput").value || 30);
  const payload = {
    name: qs("#recipeNameInput").value.trim(),
    description: qs("#recipeDescriptionInput").value.trim(),
    command_template: qs("#recipeTemplateInput").value.trim(),
    timeout_seconds: Number.isFinite(timeout) ? timeout : 30,
    parameters: commandRecipeEditorParameters(),
    tags: splitCsv(qs("#recipeTagsInput").value),
    enabled: qs("#recipeEnabledInput").checked,
  };
  const cwd = qs("#recipeCwdInput").value.trim();
  if (cwd) {
    payload.cwd = cwd;
  } else if (!includeId) {
    payload.cwd = null;
  }
  const recipeId = qs("#recipeIdInput").value.trim();
  if (includeId && recipeId) {
    payload.id = recipeId;
  }
  return payload;
}

async function createCommandRecipe(event) {
  event.preventDefault();
  const target = qs("#recipeEditorOutput");
  const recipeLocked = managedPolicyLocks().includes("command_recipes");
  clear(target);
  if (recipeLocked) {
    target.append(statusBox("Recipes locked", "Managed settings make command recipes read-only.", "blocked"));
    return;
  }
  const isEditing = Boolean(editingCommandRecipeId);
  const payload = commandRecipeEditorPayload({ includeId: !isEditing });
  target.append(statusBox(isEditing ? "Updating recipe" : "Creating recipe", payload.name || "recipe", "running"));
  try {
    const recipe = isEditing
      ? await api(`/cli/recipes/${encodeURIComponent(editingCommandRecipeId)}`, {
          method: "PATCH",
          body: payload,
        })
      : await api("/cli/recipes", { method: "POST", body: payload });
    resetCommandRecipeForm();
    clear(target);
    target.append(
      statusBox(isEditing ? "Recipe updated" : "Recipe created", recipe.name || recipe.id, recipe.enabled === false ? "blocked" : "ok"),
    );
    target.append(jsonBlock(recipe));
    await loadPolicySurfaces();
    showToast(isEditing ? "Command recipe updated." : "Command recipe created.");
  } catch (error) {
    clear(target);
    target.append(statusBox(isEditing ? "Recipe update failed" : "Recipe create failed", error.message, "failed"));
    showToast(error.message);
  }
}

function resetCommandRecipeForm() {
  editingCommandRecipeId = "";
  qs("#recipeForm").reset();
  qs("#recipeIdInput").disabled = false;
  qs("#recipeTimeoutInput").value = "30";
  qs("#recipeEnabledInput").checked = true;
  clear(qs("#recipeParameterBuilder"));
  qs("#recipeEditorSummary").textContent = "New Recipe";
  qs("#recipeSubmitLabel").textContent = "Add Recipe";
  qs("#recipeCancelEditButton").hidden = true;
}

function editCommandRecipe(recipe) {
  editingCommandRecipeId = recipe.id || "";
  qs("#recipeEditor").open = true;
  qs("#recipeEditorSummary").textContent = `Edit Recipe: ${recipe.name || recipe.id}`;
  qs("#recipeIdInput").value = recipe.id || "";
  qs("#recipeIdInput").disabled = true;
  qs("#recipeNameInput").value = recipe.name || "";
  qs("#recipeTemplateInput").value = recipe.command_template || "";
  qs("#recipeDescriptionInput").value = recipe.description || "";
  qs("#recipeCwdInput").value = recipe.cwd || "";
  qs("#recipeTimeoutInput").value = String(recipe.timeout_seconds ?? 30);
  qs("#recipeTagsInput").value = (recipe.tags || []).join(", ");
  qs("#recipeEnabledInput").checked = recipe.enabled !== false;
  clear(qs("#recipeParameterBuilder"));
  for (const parameter of recipe.parameters || []) {
    appendCommandRecipeParameterRow(parameter);
  }
  qs("#recipeSubmitLabel").textContent = "Update Recipe";
  qs("#recipeCancelEditButton").hidden = false;
  clear(qs("#recipeEditorOutput"));
  qs("#recipeEditorOutput").append(statusBox("Editing recipe", recipe.id || recipe.name, "pending"));
}

async function patchCommandRecipe(recipeId, update) {
  const target = qs("#recipeEditorOutput");
  const recipeLocked = managedPolicyLocks().includes("command_recipes");
  clear(target);
  if (recipeLocked) {
    target.append(statusBox("Recipes locked", "Managed settings make command recipes read-only.", "blocked"));
    return;
  }
  target.append(statusBox("Updating recipe", recipeId, "running"));
  try {
    const recipe = await api(`/cli/recipes/${encodeURIComponent(recipeId)}`, {
      method: "PATCH",
      body: update,
    });
    clear(target);
    target.append(statusBox("Recipe updated", recipe.name || recipe.id, recipe.enabled === false ? "blocked" : "ok"));
    target.append(jsonBlock(recipe));
    await loadPolicySurfaces();
    showToast("Command recipe updated.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Recipe update failed", error.message, "failed"));
    showToast(error.message);
  }
}

function renderRecipeList(result) {
  const target = qs("#recipeList");
  const actionPanel = qs("#recipeActionPanel");
  clear(target);
  clear(actionPanel);
  const recipeLocked = managedPolicyLocks().includes("command_recipes");
  qs("#recipeSubmitButton").disabled = recipeLocked;
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  const recipes = result.data || [];
  if (recipeLocked) {
    target.append(statusBox("Recipes locked", "Managed settings make command recipes read-only.", "blocked"));
  }
  if (!recipes.length) {
    target.append(statusBox("No records", "Nothing configured for this surface.", "pending"));
    return;
  }
  for (const recipe of recipes.slice(0, 8)) {
    const item = make("div", "list-item builder-row");
    const detail = make("div");
    detail.append(make("div", "item-title", recipe.name || recipe.id));
    detail.append(
      make(
        "div",
        "item-meta",
        `${recipe.source || "local"} - ${(recipe.tags || []).join(", ") || "recipe"} - ${
          recipe.parameters?.length || 0
        } params`,
      ),
    );
    const actions = make("div", "recipe-action-buttons");
    const useButton = make("button", "link-button", "Use");
    useButton.type = "button";
    useButton.disabled = recipe.enabled === false;
    useButton.addEventListener("click", () => renderRecipeActionPanel(recipe));
    const editButton = make("button", "link-button", "Edit");
    editButton.type = "button";
    editButton.dataset.testid = "command-recipe-edit";
    editButton.dataset.recipeId = recipe.id || "";
    editButton.disabled = recipe.source !== "local" || recipeLocked;
    editButton.addEventListener("click", () => editCommandRecipe(recipe));
    const toggleButton = make("button", recipe.enabled === false ? "success-button" : "danger-button", recipe.enabled === false ? "Enable" : "Disable");
    toggleButton.type = "button";
    toggleButton.dataset.testid = "command-recipe-toggle";
    toggleButton.dataset.recipeId = recipe.id || "";
    toggleButton.disabled = recipe.source !== "local" || recipeLocked;
    toggleButton.addEventListener("click", () => patchCommandRecipe(recipe.id, { enabled: recipe.enabled === false }));
    actions.append(statusChip(recipe.enabled === false ? "blocked" : "ok"), useButton, editButton, toggleButton);
    item.append(detail, actions);
    target.append(item);
  }
}

function renderRecipeActionPanel(recipe) {
  const target = qs("#recipeActionPanel");
  clear(target);
  target.append(
    statusBox(
      recipe.name || recipe.id,
      `${recipe.id} - ${recipe.source || "local"} - timeout ${recipe.timeout_seconds || 30}s`,
      recipe.enabled === false ? "blocked" : "ok",
    ),
  );
  const parameters = recipe.parameters || [];
  if (parameters.length) {
    const grid = make("div", "recipe-parameter-grid");
    for (const parameter of parameters) {
      const label = make("label");
      label.append(document.createTextNode(parameter.required === false ? parameter.name : `${parameter.name} *`));
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.recipeParameter = parameter.name;
      input.value = parameter.default || "";
      input.placeholder = parameter.description || parameter.name;
      label.append(input);
      grid.append(label);
    }
    target.append(grid);
  }
  const buttons = make("div", "recipe-action-buttons");
  for (const [label, action] of [
    ["Preview", "preview"],
    ["Create Approval", "approvals"],
    ["Start Run", "runs"],
    ["Execute", "execute"],
  ]) {
    const button = make("button", action === "execute" ? "primary-button" : "link-button", label);
    button.type = "button";
    button.disabled = recipe.enabled === false;
    button.addEventListener("click", () => postCommandRecipeAction(recipe.id, action));
    buttons.append(button);
  }
  const output = make("div", "output-region");
  output.id = "recipeActionOutput";
  target.append(buttons, output);
}

function commandRecipePayload() {
  const parameters = {};
  for (const input of qsa("#recipeActionPanel [data-recipe-parameter]")) {
    const value = input.value.trim();
    if (value) {
      parameters[input.dataset.recipeParameter] = value;
    }
  }
  return { parameters };
}

async function postCommandRecipeAction(recipeId, action) {
  const target = qs("#recipeActionOutput");
  const actionLabels = {
    preview: "Previewing recipe",
    approvals: "Creating recipe approval",
    runs: "Starting recipe run",
    execute: "Executing recipe",
  };
  clear(target);
  target.append(statusBox(actionLabels[action] || "Using recipe", recipeId, "running"));
  try {
    const result = await api(`/cli/recipes/${encodeURIComponent(recipeId)}/${action}`, {
      method: "POST",
      body: commandRecipePayload(),
    });
    clear(target);
    target.append(statusBox(actionLabels[action] || "Recipe action", recipeId, result.status || "ok"));
    target.append(jsonBlock(result));
    if (action === "approvals") {
      await Promise.all([loadApprovals(), loadTaskChatContext()]);
    }
    if (action === "runs" || action === "execute") {
      await loadCliRuns();
    }
    showToast("Recipe action completed.");
  } catch (error) {
    clear(target);
    target.append(statusBox("Recipe action failed", error.message, "failed"));
    showToast(error.message);
  }
}

async function loadLogs() {
  const eventType = qs("#logFilter").value;
  const suffix = eventType ? `?event_type=${encodeURIComponent(eventType)}` : "";
  const result = await safeLoad("logs", () => api(`/logs${suffix}`));
  const target = qs("#logList");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Logs unavailable", result.error, "blocked"));
    return;
  }
  const events = result.data.slice(-30).reverse();
  if (!events.length) {
    target.append(statusBox("No events", "The log stream is empty.", "pending"));
    return;
  }
  for (const event of events) {
    const item = make("div", "log-item");
    item.append(make("div", "log-message", event.message || event.event_type));
    item.append(make("div", "log-meta", `${event.event_type} - ${event.actor} - ${event.created_at}`));
    target.append(item);
  }
}

function bindEvents() {
  qs("#tokenInput").value = getToken();
  qs("#saveTokenButton").addEventListener("click", () => {
    sessionStorage.setItem(TOKEN_KEY, qs("#tokenInput").value.trim());
    showToast("Token saved for this browser session.");
    refreshDashboard();
  });
  qs("#clearTokenButton").addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    qs("#tokenInput").value = "";
    showToast("Token cleared.");
    refreshDashboard();
  });
  qs("#refreshButton").addEventListener("click", refreshDashboard);
  qs("#loadTasksButton").addEventListener("click", () => Promise.all([loadTasks(), loadTaskChatContext()]));
  qs("#taskChatForm").addEventListener("submit", submitTaskChatMessage);
  qs("#taskChatClearButton").addEventListener("click", clearTaskChatThread);
  loadTaskChatHistory();
  renderTaskChatContextStream();
  renderTaskChatThread();
  qs("#taskForm").addEventListener("submit", createTaskPlan);
  qs("#orchestrationCreateForm").addEventListener("submit", createOrchestrationRun);
  setupOrchestrationTaskBuilder();
  qs("#workspaceForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loadWorkspace(qs("#workspacePathInput").value.trim() || ".");
  });
  qs("#projectOpenRootButton").addEventListener("click", () => {
    loadWorkspace(".");
    window.location.hash = "workspace";
  });
  qs("#projectPreflightButton").addEventListener("click", preflightProjectRoot);
  qs("#projectForm").addEventListener("submit", registerProject);
  qs("#workspaceRootButton").addEventListener("click", () => loadWorkspace("."));
  qs("#workspaceParentButton").addEventListener("click", () => loadWorkspace(parentPath(workspacePath)));
  qs("#workspaceSaveButton").addEventListener("click", saveWorkspaceFile);
  qs("#loadReliabilityButton").addEventListener("click", loadReliability);
  qs("#memoryRetrievalForm").addEventListener("submit", runMemoryRetrieval);
  qs("#memoryLifecyclePreviewForm").addEventListener("submit", runMemoryLifecyclePreview);
  qs("#memoryLifecycleApplyButton").addEventListener("click", runMemoryLifecycleApply);
  qs("#memoryCompressionPreviewForm").addEventListener("submit", runMemoryCompressionPreview);
  qs("#memoryCompressionApplyButton").addEventListener("click", runMemoryCompressionApply);
  qs("#loadCliRunsButton").addEventListener("click", loadCliRuns);
  qs("#loadPolicyButton").addEventListener("click", loadPolicySurfaces);
  qs("#routingPreviewForm").addEventListener("submit", previewProviderRoute);
  qs("#networkPolicyCheckForm").addEventListener("submit", checkNetworkPolicy);
  qs("#networkPolicyApprovalButton").addEventListener("click", requestNetworkPolicyApproval);
  qs("#filesystemPolicyCheckForm").addEventListener("submit", checkFilesystemPolicy);
  qs("#filesystemPolicyApprovalButton").addEventListener(
    "click",
    requestFilesystemPolicyApproval,
  );
  qs("#networkPolicyUrlInput").addEventListener("input", () => {
    latestNetworkPolicyPreflight = null;
    qs("#networkPolicyApprovalButton").disabled = true;
  });
  qs("#networkPolicySurfaceInput").addEventListener("change", () => {
    latestNetworkPolicyPreflight = null;
    qs("#networkPolicyApprovalButton").disabled = true;
  });
  [
    "#filesystemPolicyActionInput",
    "#filesystemPolicyPathInput",
    "#filesystemPolicyTargetInput",
    "#filesystemPolicyRoleInput",
    "#filesystemPolicyAgentInput",
    "#filesystemPolicyTaskInput",
  ].forEach((selector) => {
    qs(selector).addEventListener("input", resetFilesystemPolicyApprovalState);
    qs(selector).addEventListener("change", resetFilesystemPolicyApprovalState);
  });
  qs("#cliPolicyForm").addEventListener("submit", createCliPolicyRule);
  qs("#cliPolicyCancelEditButton").addEventListener("click", () => {
    resetCliPolicyForm();
    clear(qs("#cliPolicyEditorOutput"));
  });
  qs("#recipeForm").addEventListener("submit", createCommandRecipe);
  qs("#recipeAddParameterButton").addEventListener("click", () => appendCommandRecipeParameterRow());
  qs("#recipeCancelEditButton").addEventListener("click", () => {
    resetCommandRecipeForm();
    clear(qs("#recipeEditorOutput"));
  });
  qs("#hookPolicyForm").addEventListener("submit", createHookPolicyRule);
  qs("#hookPolicyMatchInput").addEventListener("change", updateHookPolicyPatternRequirement);
  qs("#hookPolicyCancelEditButton").addEventListener("click", () => {
    resetHookPolicyForm();
    clear(qs("#hookPolicyEditorOutput"));
  });
  qs("#gitForm").addEventListener("submit", createGitCheckpoint);
  qs("#gitApprovalForm").addEventListener("submit", createGitApproval);
  qs("#gitRunSubmitButton").addEventListener("click", runGitWorkflow);
  qs("#logFilter").addEventListener("change", loadLogs);
  qs("#approvalSourceInput").addEventListener("change", () => {
    approvalSource = qs("#approvalSourceInput").value;
    selectedApproval = null;
    clear(qs("#approvalReview"));
    loadApprovals();
  });
  for (const button of qsa(".segmented-control button")) {
    button.addEventListener("click", () => {
      approvalStatus = button.dataset.status;
      selectedApproval = null;
      qsa(".segmented-control button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      clear(qs("#approvalReview"));
      loadApprovals();
    });
  }
}

bindEvents();
refreshDashboard();
