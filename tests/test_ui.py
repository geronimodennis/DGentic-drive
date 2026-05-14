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
    assert "Rules And Plugins" in response.text
    assert "policyReviewSummary" in response.text
    assert "Review Summary" in response.text
    assert "cliPolicyForm" in response.text
    assert "cliPolicyEditorOutput" in response.text
    assert "cliPolicyMatchInput" in response.text
    assert "cliPolicyModeInput" in response.text
    assert "cliPolicyRolesInput" in response.text
    assert "recipeActionPanel" in response.text
    assert "settingsOutput" in response.text
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
    assert "approvalScopeMetric" in script_response.text
    assert "latestSettingsView" in script_response.text
    assert "renderSettingsReview" in script_response.text
    assert "renderSettingsGroups" in script_response.text
    assert "settingsGroupName" in script_response.text
    assert "parseSettingList" in script_response.text
    assert "headers.Authorization" in script_response.text
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
    assert "AI change review" in script_response.text
    assert "review_evidence_count" in script_response.text
    assert "checkpoint-grid" in script_response.text
    assert "policyReviewSummary" in script_response.text
    assert "renderPolicyReviewSummary" in script_response.text
    assert "appendPolicyReviewCard" in script_response.text
    assert "managed_policy_locks" in script_response.text
    assert "cliPolicyRulePayload" in script_response.text
    assert "createCliPolicyRule" in script_response.text
    assert "splitCsv" in script_response.text
    assert 'api("/cli/policy/rules", { method: "POST", body: payload })' in script_response.text
    assert (
        'qs("#cliPolicyForm").addEventListener("submit", createCliPolicyRule)'
        in script_response.text
    )
    assert style_response.status_code == 200
    assert ".app-shell" in style_response.text
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
    assert ".approval-summary-grid" in style_response.text
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
    assert ".git-review-summary" in style_response.text


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
