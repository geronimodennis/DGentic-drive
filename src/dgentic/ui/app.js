const TOKEN_KEY = "dgentic.ui.token";

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
let latestGitCheckpoint = null;
let latestGitCheckpointRequest = null;
let latestGitDiffReview = null;
let editingCliPolicyRuleId = "";
let taskChatMessages = [];

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

function appendTaskChatMessage(message) {
  taskChatMessages.push({
    createdAt: new Date().toISOString(),
    ...message,
  });
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
  if (message.plan) {
    renderTaskChatPlan(item, message.plan);
  }
  if (message.run) {
    renderTaskRunResult(item, message.run);
  }
  target.append(item);
}

function renderTaskChatPlan(target, plan) {
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
  const runButton = make("button", "primary-button", "Run Plan");
  runButton.type = "button";
  runButton.disabled = !(plan.steps || []).length;
  runButton.addEventListener("click", () => runTaskChatPlan(plan));
  actions.append(statusChip(plan.status), runButton);
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
    await loadTasks();
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
      await loadTasks();
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
  item.append(copy, statusChip(run.status));

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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
    await loadTasks();
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
  const buttons = make("div", "recipe-action-buttons");
  const copyButton = make("button", "link-button", "Copy Payload");
  copyButton.type = "button";
  copyButton.addEventListener("click", () => copyBoundExecutionPayload(scaffold));
  buttons.append(copyButton);
  panel.append(details, buttons);
  target.append(panel);
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
    payload,
    notes,
  };
}

function networkBoundExecutionScaffold(review, basePayload) {
  const webRetrieval = review.surface === "web_retrieval" || review.action === "fetch";
  return {
    method: "POST",
    endpoint: webRetrieval ? "/web-retrieval/fetch" : "/web-retrieval/network/authorize",
    payload: {
      ...basePayload,
      url: review.url || "<approved URL>",
      timeout_seconds: 30,
      max_response_bytes: 65536,
    },
    notes: webRetrieval
      ? ["Web retrieval approvals are consumed by the fetch request."]
      : ["Provider and tool network approvals are consumed through provider/tool execution as network_approval_id."],
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
    payload: {
      ...basePayload,
      provider_id: review.provider_id || "<provider id>",
      model: review.model || "<model>",
      messages,
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
    payload: {
      ...basePayload,
      payload: review.review_payload || {},
      timeout_seconds: review.timeout_seconds || 30,
    },
    notes: ["Tool approvals require the exact approved payload; redacted review payloads may need original values restored."],
  };
}

async function copyBoundExecutionPayload(scaffold) {
  const text = JSON.stringify({ method: scaffold.method, endpoint: scaffold.endpoint, payload: scaffold.payload }, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    showToast("Bound payload copied.");
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
    await loadApprovals();
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
    await Promise.all([loadApprovals(), loadCliRuns()]);
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
    latestGitDiffReview = await api("/cli/git/diff-reviews", {
      method: "POST",
      body: gitDiffReviewPayload(checkpoint),
    });
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
  for (const section of review.sections || []) {
    renderGitDiffSection(target, section);
  }
}

function renderGitDiffSection(target, section) {
  const box = make("details", "git-diff-section");
  box.open = true;
  box.append(make("summary", "", `${section.scope} diff`));
  const meta = make("div", "chip-row");
  meta.append(statusChip(section.redacted ? "redacted" : "ok"));
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
  box.append(info);
  if (section.omitted_protected_paths?.length) {
    const omitted = make("div", "changed-paths");
    omitted.append(make("div", "item-title", "Omitted paths"));
    for (const path of section.omitted_protected_paths) {
      omitted.append(make("code", "", path));
    }
    box.append(omitted);
  }
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
    await loadApprovals();
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
    await loadProjects();
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
    await loadProjects();
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
      const item = make("div", "list-item");
      item.append(make("div", "item-title", provider.name || provider.id));
      item.append(make("div", "item-meta", `${provider.kind} - ${provider.permission_mode}`));
      item.append(statusChip(provider.enabled ? "ok" : "blocked"));
      target.append(item);
    }
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
  clear(target);
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
    target.append(row);
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
  clear(target);
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
    target.append(row);
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
  renderPolicyList(qs("#hookPolicyList"), hooks, (hook) => ({
    title: hook.name || hook.id,
    meta: `${hook.source || "local"} - ${hook.surface || "-"} - ${hook.effect || "-"}`,
    status: hook.enabled === false ? "blocked" : "ok",
  }));
  const pluginItems = plugins.ok ? plugins.data.plugins || [] : [];
  renderPolicyList(qs("#pluginList"), { ...plugins, data: pluginItems }, (plugin) => ({
    title: plugin.plugin_id || plugin.id || plugin.name,
    meta: `${plugin.trust_status || plugin.status || "unknown"} - ${
      plugin.trust_source || "local"
    }`,
    status: plugin.trust_status === "trusted" ? "ok" : "pending",
  }));
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

function renderRecipeList(result) {
  const target = qs("#recipeList");
  const actionPanel = qs("#recipeActionPanel");
  clear(target);
  clear(actionPanel);
  if (!result.ok) {
    target.append(statusBox("Unavailable", result.error, "blocked"));
    return;
  }
  const recipes = result.data || [];
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
    const button = make("button", "link-button", "Use");
    button.type = "button";
    button.disabled = recipe.enabled === false;
    button.addEventListener("click", () => renderRecipeActionPanel(recipe));
    item.append(detail, button);
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
      await loadApprovals();
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
  qs("#loadTasksButton").addEventListener("click", loadTasks);
  qs("#taskChatForm").addEventListener("submit", submitTaskChatMessage);
  qs("#taskChatClearButton").addEventListener("click", clearTaskChatThread);
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
  qs("#loadCliRunsButton").addEventListener("click", loadCliRuns);
  qs("#loadPolicyButton").addEventListener("click", loadPolicySurfaces);
  qs("#cliPolicyForm").addEventListener("submit", createCliPolicyRule);
  qs("#cliPolicyCancelEditButton").addEventListener("click", () => {
    resetCliPolicyForm();
    clear(qs("#cliPolicyEditorOutput"));
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
