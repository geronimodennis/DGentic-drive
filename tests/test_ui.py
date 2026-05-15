from fastapi.testclient import TestClient

from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.settings import get_settings


def test_web_ui_entrypoint_is_served() -> None:
    client = TestClient(create_app())

    response = client.get("/ui/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DGentic Control" in response.text
    assert "Workspace" in response.text
    assert "Project" in response.text
    assert "Context" in response.text
    assert "Active root" in response.text
    assert "CLI Runs" in response.text
    assert "taskChatForm" in response.text
    assert "taskChatInput" in response.text
    assert "taskChatTranscript" in response.text
    assert "taskChatHistoryStatus" in response.text
    assert "taskChatSubmitButton" in response.text
    assert "taskChatRunInput" in response.text
    assert "orchestrationCreateForm" in response.text
    assert "orchestrationTaskBuilder" in response.text
    assert "orchestrationTaskIdInput" in response.text
    assert "orchestrationTaskRoleInput" in response.text
    assert "orchestrationTaskDependencyList" in response.text
    assert "orchestrationTaskBuilderPreview" in response.text
    assert "orchestrationTasksInput" in response.text
    assert "orchestrationMemoryPolicyInput" in response.text
    assert "orchestrationDetail" in response.text
    assert "loadReliabilityButton" in response.text
    assert "memoryReliabilityList" in response.text
    assert "toolReliabilityList" in response.text
    assert "approvalSourceInput" in response.text
    assert "Executed" in response.text
    assert "gitApprovalActions" in response.text
    assert "gitApprovalForm" in response.text
    assert "gitCommitMessageInput" in response.text
    assert "gitPrTitleInput" in response.text
    assert "gitApprovalSubmitLabel" in response.text
    assert "gitRunSubmitButton" in response.text
    assert "gitRunSubmitLabel" in response.text
    assert "gitRunOutput" in response.text
    assert "Rules And Plugins" in response.text
    assert "policyReviewSummary" in response.text
    assert "Review Summary" in response.text
    assert "cliPolicyForm" in response.text
    assert "cliPolicyEditor" in response.text
    assert "cliPolicyEditorOutput" in response.text
    assert "cliPolicyCancelEditButton" in response.text
    assert "cliPolicySubmitLabel" in response.text
    assert "cliPolicyMatchInput" in response.text
    assert "cliPolicyModeInput" in response.text
    assert "cliPolicyRolesInput" in response.text
    assert "recipeActionPanel" in response.text
    assert "settingsOutput" in response.text
    assert 'rel="icon" href="data:,"' in response.text
    assert "./app.js" in response.text
    assert "./app.css" in response.text


def test_web_ui_static_assets_are_served() -> None:
    client = TestClient(create_app())

    script_response = client.get("/ui/app.js")
    style_response = client.get("/ui/app.css")

    assert script_response.status_code == 200
    assert "const TOKEN_KEY" in script_response.text
    assert "approvalSources" in script_response.text
    assert "approvalSource" in script_response.text
    assert "approvalStatusLabel" in script_response.text
    assert "approvalSourceLabel" in script_response.text
    assert "renderApprovalSummary" in script_response.text
    assert "renderApprovalReviewSummary" in script_response.text
    assert "approvalReviewPairs" in script_response.text
    assert "renderApprovalExecutionControls" in script_response.text
    assert "renderBoundExecutionRequestPanel" in script_response.text
    assert "boundExecutionRequestScaffold" in script_response.text
    assert "filesystemBoundExecutionScaffold" in script_response.text
    assert "networkBoundExecutionScaffold" in script_response.text
    assert "providerBoundExecutionScaffold" in script_response.text
    assert "toolBoundExecutionScaffold" in script_response.text
    assert "copyBoundExecutionPayload" in script_response.text
    assert "Bound execution request" in script_response.text
    assert "Payload scaffold" in script_response.text
    assert "Copy Payload" in script_response.text
    assert "Guided Fields" in script_response.text
    assert "Editable Payload" in script_response.text
    assert "bound-execution-editor" in script_response.text
    assert "bound-execution-guided-fields" in script_response.text
    assert "bound-execution-guided-field" in script_response.text
    assert "boundExecutionPayloadInput" in script_response.text
    assert "boundExecutionPayloadFromEditor" in script_response.text
    assert "renderBoundExecutionGuidedFields" in script_response.text
    assert "renderBoundExecutionGuidedField" in script_response.text
    assert "boundExecutionGuidedFieldControl" in script_response.text
    assert "syncBoundExecutionGuidedField" in script_response.text
    assert "boundExecutionGuidedFieldValue" in script_response.text
    assert "boundExecutionPayloadFromText" in script_response.text
    assert "control.dataset.boundPayloadPath = field" in script_response.text
    assert "Bound approval fields are locked in guided editing." in script_response.text
    assert "Fix payload JSON before syncing guided fields." in script_response.text
    assert "Guided numeric field is invalid." in script_response.text
    assert "Guided field JSON invalid" in script_response.text
    assert "validateBoundExecutionPayload" in script_response.text
    assert "Payload JSON is required." in script_response.text
    assert "Payload JSON must be an object." in script_response.text
    assert "must match the approved request." in script_response.text
    assert "Payload JSON invalid" in script_response.text
    assert "executeBoundExecutionRequest" in script_response.text
    assert "boundExecutionExecuteButton" in script_response.text
    assert "Execute Request" in script_response.text
    assert "boundExecutionOutput" in script_response.text
    assert "api(scaffold.endpoint, { method: scaffold.method, body: payload })" in (
        script_response.text
    )
    assert "Bound request executed" in script_response.text
    assert "Bound execution failed" in script_response.text
    assert "Bound execution handoff only" in script_response.text
    assert "Dashboard execute" in script_response.text
    assert "network_approval_id" in script_response.text
    assert "await loadApprovals()" in script_response.text
    assert "renderReviewWarnings" in script_response.text
    assert "reviewValue" in script_response.text
    assert "Raw review" in script_response.text
    assert "requires_bound_execution_request" in script_response.text
    assert "direct_execute_available" in script_response.text
    assert "review_warnings" in script_response.text
    assert "workflow_binding" in script_response.text
    assert '"/filesystem/delete"' in script_response.text
    assert '"/filesystem/move"' in script_response.text
    assert '"/filesystem/copy"' in script_response.text
    assert '"/filesystem/rename"' in script_response.text
    assert '"<original approved content>"' in script_response.text
    assert '"<original approved base64 content>"' in script_response.text
    assert "target_path" in script_response.text
    assert "new_name" in script_response.text
    assert "content_base64" in script_response.text
    assert '"/web-retrieval/fetch"' in script_response.text
    assert "max_response_bytes" in script_response.text
    assert '"<provider/tool execution endpoint>"' in script_response.text
    assert '"/providers/generate"' in script_response.text
    assert '"/providers/generate/stream"' in script_response.text
    assert "messages" in script_response.text
    assert "options" in script_response.text
    assert "/tools/${encodeURIComponent" in script_response.text
    assert "api(`${source.base}/${encodeURIComponent(result.id || approval.id)}/review`)" in (
        script_response.text
    )
    assert "approvalScopeMetric" in script_response.text
    assert "latestSettingsView" in script_response.text
    assert "renderSettingsReview" in script_response.text
    assert "renderSettingsGroups" in script_response.text
    assert "settingsGroupName" in script_response.text
    assert "parseSettingList" in script_response.text
    assert "headers.Authorization" in script_response.text
    assert "TASK_CHAT_HISTORY_KEY" in script_response.text
    assert 'const TASK_CHAT_HISTORY_KEY = "dgentic.ui.taskChatMessages"' in script_response.text
    assert "TASK_CHAT_HISTORY_MAX_MESSAGES" in script_response.text
    assert "TASK_CHAT_HISTORY_MAX_BYTES" in script_response.text
    assert "loadTaskChatHistory" in script_response.text
    assert "saveTaskChatHistory" in script_response.text
    assert "clearTaskChatHistory" in script_response.text
    assert "updateTaskChatHistoryStatus" in script_response.text
    assert "compactTaskChatMessage" in script_response.text
    assert "taskChatHistoryMessagesForStorage" in script_response.text
    assert "localStorage.getItem(TASK_CHAT_HISTORY_KEY)" in script_response.text
    assert "localStorage.setItem(TASK_CHAT_HISTORY_KEY, JSON.stringify(historyMessages))" in (
        script_response.text
    )
    assert "localStorage.removeItem(TASK_CHAT_HISTORY_KEY)" in script_response.text
    assert 'qs("#taskChatHistoryStatus")' in script_response.text
    assert "History not saved" in script_response.text
    assert "History reset" in script_response.text
    assert "Saved history is display only." in script_response.text
    assert "localStorage.setItem(TOKEN_KEY" not in script_response.text
    assert "taskChatPayload" in script_response.text
    assert "submitTaskChatMessage" in script_response.text
    assert "appendTaskChatMessage" in script_response.text
    assert "renderTaskChatThread" in script_response.text
    assert "renderTaskChatMessage" in script_response.text
    assert "renderTaskChatPlan" in script_response.text
    assert "runTaskChatPlan" in script_response.text
    assert "runTaskPlan" in script_response.text
    assert 'qs("#taskChatForm").addEventListener("submit", submitTaskChatMessage)' in (
        script_response.text
    )
    assert 'api("/tasks/plan", { method: "POST", body: payload })' in script_response.text
    assert 'api("/filesystem/list"' in script_response.text
    assert 'api("/filesystem/read"' in script_response.text
    assert 'api("/filesystem/write"' in script_response.text
    assert 'api("/cli/runs"' in script_response.text
    assert "api(`/cli/runs/${encodeURIComponent(runId)}/output`)" in script_response.text
    assert "api(`/cli/approvals/${encodeURIComponent(approvalId)}/execute`" in script_response.text
    assert 'api("/cli/policy/rules")' in script_response.text
    assert 'api("/cli/recipes")' in script_response.text
    assert "renderRecipeList" in script_response.text
    assert "renderRecipeActionPanel" in script_response.text
    assert "commandRecipePayload" in script_response.text
    assert "postCommandRecipeAction" in script_response.text
    assert "data-recipe-parameter" in script_response.text
    assert "/cli/recipes/${encodeURIComponent(recipeId)}/${action}" in script_response.text
    assert 'api("/guardrails/hooks/rules")' in script_response.text
    assert 'api("/plugins")' in script_response.text
    assert 'api("/settings/effective")' in script_response.text
    assert "renderProjectContext" in script_response.text
    assert "activeRootDir" in script_response.text
    assert "projectOpenRootButton" in script_response.text
    assert "projectPreflightButton" in script_response.text
    assert "projectForm" in script_response.text
    assert 'api("/projects/preflight"' in script_response.text
    assert 'api("/projects"' in script_response.text
    assert 'api("/projects/active")' in script_response.text
    assert "activateProject" in script_response.text
    assert "api(`/projects/${encodeURIComponent(projectId)}/activate`" in script_response.text
    assert "renderActivationChecks" in script_response.text
    assert "workspaceRootButton" in script_response.text
    assert "selectedOrchestrationId" in script_response.text
    assert "createOrchestrationRun" in script_response.text
    assert 'api("/tasks/orchestrations", { method: "POST", body: payload })' in script_response.text
    assert "setupOrchestrationTaskBuilder" in script_response.text
    assert "parseOrchestrationTasksInput" in script_response.text
    assert "writeOrchestrationTasksInput" in script_response.text
    assert "buildOrchestrationTaskDraft" in script_response.text
    assert "renderOrchestrationTaskBuilderPreview" in script_response.text
    assert "JSON.stringify(tasks, null, 2)" in script_response.text
    assert 'qs("#orchestrationTasksInput").value' in script_response.text
    assert "runsForPlan" in script_response.text
    assert "renderTaskPlanCard" in script_response.text
    assert "renderTaskPlanSteps" in script_response.text
    assert "renderTaskRunSummary" in script_response.text
    assert "executeTaskPlan" in script_response.text
    assert 'api("/tasks/execute", { method: "POST", body: plan })' in script_response.text
    assert "Run Plan" in script_response.text
    assert "No task messages" in script_response.text
    assert "task-chat-plan-card" in script_response.text
    assert "innerHTML" not in script_response.text
    assert "outerHTML" not in script_response.text
    assert "insertAdjacentHTML" not in script_response.text
    assert "task-plan-card" in script_response.text
    assert "task-run-summary" in script_response.text
    assert "required_dod_evidence" in script_response.text
    assert "shared_memory_tags" in script_response.text
    assert "shared_memory_policy" in script_response.text
    assert "loadReliability" in script_response.text
    assert 'api("/api/v1/memory/metadata?limit=50")' in script_response.text
    assert 'api("/api/v1/tools/registry?limit=50")' in script_response.text
    assert "renderMemoryReliability" in script_response.text
    assert "renderToolReliability" in script_response.text
    assert "reliability_score" in script_response.text
    assert "freshness_score" in script_response.text
    assert 'safeLoad("agents", () => api("/agents"))' in script_response.text
    assert "Array.isArray(agentsResult.data)" in script_response.text
    assert "renderOrchestrationDetail" in script_response.text
    assert "renderAgentHierarchy" in script_response.text
    assert "agent.parent_agent_id" in script_response.text
    assert "agent-tree" in script_response.text
    assert "agent-node" in script_response.text
    assert "renderTaskAgentBrief" in script_response.text
    assert "agent-brief-grid" in script_response.text
    assert "renderTaskUpdateForm" in script_response.text
    assert "submitOrchestrationTaskUpdate" in script_response.text
    assert 'method: "PATCH"' in script_response.text
    assert "recoverableTaskBlockerSeverities" in script_response.text
    assert "canRecoverTask" in script_response.text
    assert "submitOrchestrationTaskRecovery" in script_response.text
    assert "declared_write_paths: declaredWritePaths" in script_response.text
    assert "/recover`" in script_response.text
    assert "resolvableTaskBlockerSeverities" in script_response.text
    assert "submitOrchestrationBlockerResolution" in script_response.text
    assert "/blockers/${encodeURIComponent(blockerId)}/resolve`" in script_response.text
    assert "renderOrchestrationCloseout" in script_response.text
    assert "submitOrchestrationCloseout" in script_response.text
    assert "required_dod_evidence" in script_response.text
    assert "postOrchestrationLoop" in script_response.text
    assert "postOrchestrationExecution" in script_response.text
    assert "cancelOrchestrationExecution" in script_response.text
    assert "api(`/tasks/orchestrations/${encodeURIComponent(runId)}`" in script_response.text
    assert (
        "api(`/tasks/orchestrations/${encodeURIComponent(runId)}/executions`"
        in script_response.text
    )
    assert "api(`/tasks/orchestrations/${encodeURIComponent(runId)}/loop`" in script_response.text
    assert (
        "api(`/tasks/orchestrations/${encodeURIComponent(runId)}/executions`, {"
        in script_response.text
    )
    assert "executions/${encodeURIComponent(executionId)}/cancel`" in script_response.text
    assert "renderGitCheckpoint" in script_response.text
    assert "renderGitReviewSummary" in script_response.text
    assert "latestGitCheckpoint" in script_response.text
    assert "latestGitCheckpointRequest" in script_response.text
    assert "gitCheckpointPayload" in script_response.text
    assert "renderGitApprovalActions" in script_response.text
    assert "createGitApproval" in script_response.text
    assert "gitApprovalPayload" in script_response.text
    assert "gitApprovalEndpoint" in script_response.text
    assert "gitRunEndpoint" in script_response.text
    assert "gitRunPayload" in script_response.text
    assert "validateGitCloseoutFields" in script_response.text
    assert "runGitWorkflow" in script_response.text
    assert "renderGitRunResult" in script_response.text
    assert "latestGitDiffReview" in script_response.text
    assert "gitDiffReviewDecisions" in script_response.text
    assert "renderGitDiffReviewPanel" in script_response.text
    assert "loadGitDiffReview" in script_response.text
    assert "renderGitDiffSection" in script_response.text
    assert "gitDiffReviewPayload" in script_response.text
    assert "renderGitChangeReview" in script_response.text
    assert "gitChangeReviewEvidence" in script_response.text
    assert "copyGitChangeReviewEvidence" in script_response.text
    assert "setGitDiffSectionDecision" in script_response.text
    assert "gitDiffReviewDecisionCounts" in script_response.text
    assert "gitDiffReviewHasRejectedSections" in script_response.text
    assert "updateGitReviewDecisionGate" in script_response.text
    assert "Git closeout paused" in script_response.text
    assert 'make("button", "success-button", "Accept")' in script_response.text
    assert 'make("button", "danger-button", "Reject")' in script_response.text
    assert 'make("button", "link-button", "Clear")' in script_response.text
    assert "checkpoint_digest: review.checkpoint_digest" in script_response.text
    assert 'qs("#gitApprovalSubmitButton").disabled = !enabled' in script_response.text
    assert 'api("/cli/git/diff-reviews"' in script_response.text
    assert 'make("pre", "diff-patch"' in script_response.text
    assert "/cli/git/${action}-approvals" in script_response.text
    assert "/cli/git/${action}-runs" in script_response.text
    assert 'api(endpoint, { method: "POST", body: payload })' in script_response.text
    assert "commit_message" in script_response.text
    assert "base_branch" in script_response.text
    assert "setApprovalFilterState" in script_response.text
    assert 'setApprovalFilterState("cli", "pending")' in script_response.text
    assert 'qs("#gitApprovalForm").addEventListener("submit", createGitApproval)' in (
        script_response.text
    )
    assert 'qs("#gitRunSubmitButton").addEventListener("click", runGitWorkflow)' in (
        script_response.text
    )
    assert "AI change review" in script_response.text
    assert "review_evidence_count" in script_response.text
    assert "checkpoint-grid" in script_response.text
    assert "policyReviewSummary" in script_response.text
    assert "renderPolicyReviewSummary" in script_response.text
    assert "appendPolicyReviewCard" in script_response.text
    assert "managed_policy_locks" in script_response.text
    assert "cliPolicyRulePayload" in script_response.text
    assert "createCliPolicyRule" in script_response.text
    assert "renderCliPolicyList" in script_response.text
    assert "editCliPolicyRule" in script_response.text
    assert "patchCliPolicyRule" in script_response.text
    assert "resetCliPolicyForm" in script_response.text
    assert "managedPolicyLocks" in script_response.text
    assert "splitCsv" in script_response.text
    assert 'api("/cli/policy/rules", { method: "POST", body: payload })' in script_response.text
    assert 'method: "PATCH"' in script_response.text
    assert "/cli/policy/rules/${encodeURIComponent(ruleId)}" in script_response.text
    assert "{ enabled: rule.enabled === false }" in script_response.text
    assert "cli-policy-toggle" in script_response.text
    assert (
        'qs("#cliPolicyForm").addEventListener("submit", createCliPolicyRule)'
        in script_response.text
    )
    assert 'qs("#cliPolicyCancelEditButton").addEventListener("click"' in script_response.text
    assert style_response.status_code == 200
    assert ".app-shell" in style_response.text
    assert ".panel > *" in style_response.text
    assert "grid-template-columns: minmax(0, 1fr);" in style_response.text
    assert ".task-chat" in style_response.text
    assert ".task-chat-header-actions" in style_response.text
    assert ".task-chat-history-status" in style_response.text
    assert ".task-chat-transcript" in style_response.text
    assert ".task-chat-message" in style_response.text
    assert ".task-chat-message-user" in style_response.text
    assert ".task-chat-message-agent" in style_response.text
    assert ".task-chat-composer" in style_response.text
    assert ".task-chat-plan-card" in style_response.text
    assert ".workspace-layout" in style_response.text
    assert ".orchestration-detail" in style_response.text
    assert ".orchestration-controls" in style_response.text
    assert ".task-card" in style_response.text
    assert ".agent-brief" in style_response.text
    assert ".agent-brief-grid" in style_response.text
    assert ".agent-tree" in style_response.text
    assert ".agent-node" in style_response.text
    assert ".orchestration-form" in style_response.text
    assert ".orchestration-builder" in style_response.text
    assert ".task-builder-grid" in style_response.text
    assert ".dependency-list" in style_response.text
    assert ".builder-task-actions" in style_response.text
    assert ".approval-filter-row" in style_response.text
    assert ".segmented-control button" in style_response.text
    assert "flex: 1 1 96px;" in style_response.text
    assert ".approval-summary-grid" in style_response.text
    assert ".approval-review-summary" in style_response.text
    assert ".bound-execution-panel" in style_response.text
    assert ".bound-execution-editor" in style_response.text
    assert ".bound-execution-guided-fields" in style_response.text
    assert ".bound-execution-guided-field" in style_response.text
    assert ".review-warning-list" in style_response.text
    assert ".context-grid" in style_response.text
    assert ".checkpoint-grid" in style_response.text
    assert ".reliability-grid" in style_response.text
    assert ".policy-grid" in style_response.text
    assert ".recipe-action-panel" in style_response.text
    assert ".recipe-parameter-grid" in style_response.text
    assert ".recipe-action-buttons" in style_response.text
    assert ".approval-list" in style_response.text
    assert ".settings-review-summary" in style_response.text
    assert ".settings-group-list" in style_response.text
    assert ".setting-source-row" in style_response.text
    assert ".policy-review-section" in style_response.text
    assert ".policy-editor" in style_response.text
    assert ".git-approval-actions" in style_response.text
    assert ".direct-run-button" in style_response.text
    assert ".git-run-summary" in style_response.text
    assert ".git-change-review" in style_response.text
    assert ".git-diff-review" in style_response.text
    assert ".git-diff-section" in style_response.text
    assert ".git-diff-decision-controls" in style_response.text
    assert ".status-chip.accepted" in style_response.text
    assert ".status-chip.rejected" in style_response.text
    assert ".diff-patch" in style_response.text
    assert ".git-review-summary" in style_response.text
    assert ".task-plan-card" in style_response.text
    assert ".task-plan-header" in style_response.text
    assert ".task-plan-actions" in style_response.text
    assert ".task-step-list" in style_response.text
    assert ".task-step-card" in style_response.text
    assert ".task-run-summary" in style_response.text


def test_web_ui_approval_sources_match_backend_contracts() -> None:
    client = TestClient(create_app())

    script_response = client.get("/ui/app.js")

    assert script_response.status_code == 200
    for source in [
        '{ key: "cli", label: "CLI", base: "/cli/approvals" }',
        '{ key: "filesystem", label: "Filesystem", base: "/filesystem/approvals" }',
        '{ key: "network", label: "Network", base: "/network/approvals" }',
        '{ key: "provider", label: "Provider", base: "/providers/approvals" }',
        '{ key: "tool", label: "Tool", base: "/tools/approvals" }',
    ]:
        assert source in script_response.text


def test_web_ui_is_public_while_api_routes_remain_protected(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "admin-token=admin")
    get_settings.cache_clear()
    reset_database_state()

    client = TestClient(create_app())

    ui_response = client.get("/ui/")
    api_response = client.get("/tasks/plans")

    assert ui_response.status_code == 200
    assert "DGentic Control" in ui_response.text
    assert api_response.status_code == 401

    reset_database_state()
    get_settings.cache_clear()
