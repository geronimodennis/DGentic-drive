const TOKEN_KEY = "dgentic.ui.token";

const approvalSources = [
  { key: "cli", label: "CLI", base: "/cli/approvals" },
  { key: "filesystem", label: "Filesystem", base: "/filesystem/approvals" },
  { key: "network", label: "Network", base: "/network/approvals" },
  { key: "provider", label: "Provider", base: "/providers/approvals" },
  { key: "tool", label: "Tool", base: "/tools/approvals" },
];

let approvalStatus = "pending";
let selectedApproval = null;
let workspacePath = ".";
let openFilePath = "";
let toastTimer = null;
let activeRootDir = "";
let activeRootSource = "";

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
    throw new Error(detail || `Request failed with ${response.status}`);
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

function appendKeyValue(target, label, value, chipValue = "") {
  const item = make("div", "info-pair");
  item.append(make("span", "", label));
  item.append(make("strong", "", value));
  if (chipValue) {
    item.append(statusChip(chipValue));
  }
  target.append(item);
}

async function refreshDashboard() {
  await Promise.all([
    loadHealth(),
    loadTasks(),
    loadWorkspace(),
    loadApprovals(),
    loadProviders(),
    loadCliRuns(),
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
  const [plans, runs, summary, orchestrations] = await Promise.all([
    safeLoad("plans", () => api("/tasks/plans")),
    safeLoad("runs", () => api("/tasks/runs")),
    safeLoad("orchestration summary", () => api("/tasks/orchestrations/operations/summary")),
    safeLoad("orchestrations", () => api("/tasks/orchestrations")),
  ]);

  const planCount = plans.ok ? plans.data.length : "-";
  const runCount = runs.ok ? runs.data.length : "-";
  setMetric("#plansMetric", String(planCount));
  setMetric("#runsMetric", `Runs: ${runCount}`);

  renderTaskOutput(plans, runs);
  renderOrchestrationSummary(summary, orchestrations);
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
  for (const plan of latestPlans) {
    const item = make("div", "list-item");
    item.append(make("div", "item-title", plan.objective || plan.id));
    item.append(make("div", "item-meta", `${plan.id} - ${plan.status} - ${plan.steps?.length || 0} steps`));
    item.append(statusChip(plan.status));
    target.append(item);
  }
}

function renderOrchestrationSummary(summary, orchestrations) {
  const target = qs("#orchestrationSummary");
  clear(target);
  if (!summary.ok) {
    target.append(statusBox("Summary unavailable", summary.error, "blocked"));
  } else {
    const counts = summary.data.run_status_counts || {};
    const item = make("div", "list-item");
    item.append(make("div", "item-title", `${summary.data.total_runs || 0} orchestration runs`));
    item.append(make("div", "item-meta", Object.entries(counts).map(([key, value]) => `${key}: ${value}`).join(" | ") || "No status counts"));
    target.append(item);
  }

  if (!orchestrations.ok) {
    target.append(statusBox("Runs unavailable", orchestrations.error, "blocked"));
    return;
  }
  for (const run of orchestrations.data.slice(-5).reverse()) {
    const item = make("div", "list-item");
    item.append(make("div", "item-title", run.objective || run.id));
    item.append(make("div", "item-meta", `${run.id} - tasks: ${run.tasks?.length || 0}`));
    item.append(statusChip(run.status));
    target.append(item);
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

async function loadApprovals() {
  const loads = approvalSources.map(async (source) => {
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
  target.append(header, jsonBlock(item.review));

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
  if (item.source.key === "cli" && item.approval.status === "approved") {
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
  }
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
    selectedApproval = { source, approval: result };
    renderApprovalReview({ source, approval: result, review: result });
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

async function createGitCheckpoint(event) {
  event.preventDefault();
  const payload = {
    action: qs("#gitActionInput").value,
    test_evidence: splitLines(qs("#gitEvidenceInput").value),
  };
  const cwd = qs("#gitCwdInput").value.trim();
  if (cwd) {
    payload.cwd = cwd;
  }
  const target = qs("#gitOutput");
  clear(target);
  target.append(statusBox("Checking repository", payload.action, "running"));
  try {
    const checkpoint = await api("/cli/git/checkpoints", { method: "POST", body: payload });
    renderGitCheckpoint(checkpoint);
  } catch (error) {
    clear(target);
    target.append(statusBox("Checkpoint failed", error.message, "failed"));
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

  renderFindings(target, "Blockers", checkpoint.blockers || [], "blocked");
  renderFindings(target, "Warnings", checkpoint.warnings || [], "pending");
  renderChangedPaths(target, checkpoint);

  const details = make("details", "json-details");
  details.append(make("summary", "", "Raw checkpoint"));
  details.append(jsonBlock(checkpoint));
  target.append(details);
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

async function loadSettings() {
  const result = await safeLoad("settings", () => api("/settings/effective"));
  const target = qs("#settingsOutput");
  clear(target);
  if (!result.ok) {
    target.append(statusBox("Settings unavailable", result.error, "blocked"));
    renderProjectContext(null, result.error);
    return;
  }
  renderProjectContext(result.data);
  const settings = result.data.settings || [];
  for (const setting of settings.slice(0, 24)) {
    const item = make("div", "setting-item");
    item.append(make("strong", "", setting.name || "setting"));
    const value =
      setting.value && typeof setting.value === "object"
        ? JSON.stringify(setting.value)
        : String(setting.value);
    item.append(make("code", "", `${setting.source || "runtime"}: ${value}`));
    if (setting.redacted) {
      item.append(statusChip("redacted"));
    }
    target.append(item);
  }
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
  renderPolicyList(qs("#cliPolicyList"), cliRules, (rule) => ({
    title: rule.name || rule.id,
    meta: `${rule.source || "local"} - ${rule.permission_mode || rule.risk || "policy"} - ${
      rule.match_type || "-"
    }`,
    status: rule.enabled === false ? "blocked" : "ok",
  }));
  renderPolicyList(qs("#recipeList"), recipes, (recipe) => ({
    title: recipe.name || recipe.id,
    meta: `${recipe.source || "local"} - ${(recipe.tags || []).join(", ") || "recipe"}`,
    status: "ok",
  }));
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
  qs("#taskForm").addEventListener("submit", createTaskPlan);
  qs("#workspaceForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loadWorkspace(qs("#workspacePathInput").value.trim() || ".");
  });
  qs("#projectOpenRootButton").addEventListener("click", () => {
    loadWorkspace(".");
    window.location.hash = "workspace";
  });
  qs("#workspaceRootButton").addEventListener("click", () => loadWorkspace("."));
  qs("#workspaceParentButton").addEventListener("click", () => loadWorkspace(parentPath(workspacePath)));
  qs("#workspaceSaveButton").addEventListener("click", saveWorkspaceFile);
  qs("#loadCliRunsButton").addEventListener("click", loadCliRuns);
  qs("#loadPolicyButton").addEventListener("click", loadPolicySurfaces);
  qs("#gitForm").addEventListener("submit", createGitCheckpoint);
  qs("#logFilter").addEventListener("change", loadLogs);
  for (const button of qsa(".segmented-control button")) {
    button.addEventListener("click", () => {
      approvalStatus = button.dataset.status;
      qsa(".segmented-control button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      loadApprovals();
    });
  }
}

bindEvents();
refreshDashboard();
