import re

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
    assert "workspacePreviewButton" in response.text
    assert "workspaceApplyButton" in response.text
    assert "workspaceRevertButton" in response.text
    assert "workspaceChangeReview" in response.text
    assert "Preview Change" in response.text
    assert "Apply Change" in response.text
    assert "Revert Last" in response.text
    assert "Project" in response.text
    assert "Context" in response.text
    assert "Active root" in response.text
    assert "CLI Runs" in response.text
    assert "taskChatForm" in response.text
    assert "taskChatInput" in response.text
    assert "taskChatTranscript" in response.text
    assert "taskChatContextStream" in response.text
    assert "taskChatHistoryStatus" in response.text
    assert "taskChatSubmitButton" in response.text
    assert "taskChatRunInput" in response.text
    assert "taskChatProviderPanel" in response.text
    assert "taskChatProviderInput" in response.text
    assert "taskChatProviderModelInput" in response.text
    assert "taskChatProviderRoleInput" in response.text
    assert "taskChatRoutingRoleInput" in response.text
    assert "taskChatRoutingCapabilitiesInput" in response.text
    assert "taskChatRoutingPrivacyInput" in response.text
    assert "taskChatProviderStreamInput" in response.text
    assert "taskChatProviderApprovalInput" in response.text
    assert "taskChatProviderNetworkApprovalInput" in response.text
    assert "taskChatContextReviewPanel" in response.text
    assert "taskChatContextReviewStatus" in response.text
    assert "taskChatContextPreviewButton" in response.text
    assert "taskChatContextRedactButton" in response.text
    assert "taskChatContextClearButton" in response.text
    assert "taskChatContextReviewOutput" in response.text
    assert "Context Review" in response.text
    assert "Preview Context" in response.text
    assert "Redact Context" in response.text
    assert "Clear Context" in response.text
    assert "taskChatProviderButton" in response.text
    assert "taskChatProviderPromptPreviewButton" in response.text
    assert "taskChatRouteButton" in response.text
    assert "taskChatProviderApprovalRequestButton" in response.text
    assert "taskChatHandoffPanel" in response.text
    assert "taskChatHandoffPreviewButton" in response.text
    assert "taskChatHandoffCopyMarkdownButton" in response.text
    assert "taskChatHandoffCopyJsonButton" in response.text
    assert "taskChatHandoffOutput" in response.text
    assert "Handoff Packet" in response.text
    assert "Preview Prompt" in response.text
    assert "Preview Route" in response.text
    assert "Request Approval" in response.text
    assert "refreshActivityButton" in response.text
    assert "sessionSummaryForm" in response.text
    assert "sessionSummaryIdInput" in response.text
    assert "sessionSummaryActionsInput" in response.text
    assert "sessionSummaryDecisionsInput" in response.text
    assert "sessionSummaryKnowledgeInput" in response.text
    assert "sessionSummaryToolsInput" in response.text
    assert "sessionSummaryNextStepsInput" in response.text
    assert "sessionSummaryList" in response.text
    assert "sessionSummaryOutput" in response.text
    assert 'value="session"' in response.text
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
    assert "providerHealthOutput" in response.text
    assert "routingPreviewPanel" in response.text
    assert "routingPreviewForm" in response.text
    assert "routingRoleInput" in response.text
    assert "routingPrivacyInput" in response.text
    assert "routingCapabilitiesInput" in response.text
    assert "routingLatencyInput" in response.text
    assert "routingCostInput" in response.text
    assert "routingOutput" in response.text
    assert "providerGenerationPanel" in response.text
    assert "providerGenerationForm" in response.text
    assert "providerGenerationProviderInput" in response.text
    assert "providerGenerationModelInput" in response.text
    assert "providerGenerationMessageInput" in response.text
    assert "providerGenerationStreamInput" in response.text
    assert "providerGenerationApprovalInput" in response.text
    assert "providerGenerationNetworkApprovalInput" in response.text
    assert "providerGenerationOutput" in response.text
    assert "toolGovernancePanel" in response.text
    assert "toolGovernanceReasonInput" in response.text
    assert "toolGovernanceList" in response.text
    assert "toolGovernanceOutput" in response.text
    assert "memoryRetrievalPanel" in response.text
    assert "memoryRetrievalForm" in response.text
    assert "memoryRetrievalQueryInput" in response.text
    assert "memoryRetrievalEntityTypesInput" in response.text
    assert "memoryRetrievalTagsInput" in response.text
    assert "memoryRetrievalCategoryInput" in response.text
    assert "memoryRetrievalLifecycleInput" in response.text
    assert "memoryRetrievalLimitInput" in response.text
    assert "memoryRetrievalThresholdInput" in response.text
    assert "memoryRetrievalInactiveInput" in response.text
    assert "memoryRetrievalOutput" in response.text
    assert "memoryLifecyclePreviewPanel" in response.text
    assert "memoryLifecyclePreviewForm" in response.text
    assert "memoryLifecycleEntityTypesInput" in response.text
    assert "memoryLifecycleTagsInput" in response.text
    assert "memoryLifecycleCategoryInput" in response.text
    assert "memoryLifecycleRetentionInput" in response.text
    assert "memoryLifecycleStateInput" in response.text
    assert "memoryLifecycleLimitInput" in response.text
    assert "memoryLifecycleInactiveInput" in response.text
    assert "memoryLifecycleApplyButton" in response.text
    assert "Apply Lifecycle" in response.text
    assert "memoryLifecyclePreviewOutput" in response.text
    assert "memoryCompressionPreviewPanel" in response.text
    assert "memoryCompressionPreviewForm" in response.text
    assert "memoryCompressionEntityTypesInput" in response.text
    assert "memoryCompressionTagsInput" in response.text
    assert "memoryCompressionCategoryInput" in response.text
    assert "memoryCompressionRetentionInput" in response.text
    assert "memoryCompressionLimitInput" in response.text
    assert "memoryCompressionSummaryInput" in response.text
    assert "memoryCompressionAgeInput" in response.text
    assert "memoryCompressionAccessInput" in response.text
    assert "memoryCompressionInactiveInput" in response.text
    assert "memoryCompressionApplyButton" in response.text
    assert "Apply Compression" in response.text
    assert "memoryCompressionPreviewOutput" in response.text
    assert "memoryReliabilityList" in response.text
    assert "memoryReliabilityDetail" in response.text
    assert "toolReliabilityList" in response.text
    assert "toolReliabilityDetail" in response.text
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
    assert "networkPolicyCheckPanel" in response.text
    assert "networkPolicyCheckForm" in response.text
    assert "networkPolicyUrlInput" in response.text
    assert "networkPolicySurfaceInput" in response.text
    assert "networkPolicyApprovalButton" in response.text
    assert "networkPolicyCheckOutput" in response.text
    assert "networkDomainPolicyEditor" in response.text
    assert "networkDomainPolicyForm" in response.text
    assert "networkDomainPolicyDomainInput" in response.text
    assert "networkDomainPolicyModeInput" in response.text
    assert "networkDomainPolicyReasonInput" in response.text
    assert "networkDomainPolicyPriorityInput" in response.text
    assert "networkDomainPolicyEnabledInput" in response.text
    assert "networkDomainPolicyCancelEditButton" in response.text
    assert "networkDomainPolicySubmitLabel" in response.text
    assert "networkDomainPolicyEditorOutput" in response.text
    assert "networkDomainPolicyList" in response.text
    assert "filesystemPolicyCheckPanel" in response.text
    assert "filesystemPolicyCheckForm" in response.text
    assert "filesystemPolicyActionInput" in response.text
    assert "filesystemPolicyPathInput" in response.text
    assert "filesystemPolicyTargetInput" in response.text
    assert "filesystemPolicyRecursiveInput" in response.text
    assert "filesystemPolicyOverwriteInput" in response.text
    assert "filesystemPolicyCreateParentsInput" in response.text
    assert "filesystemPolicyContentInput" in response.text
    assert "filesystemPolicyContentBase64Input" in response.text
    assert "filesystemPolicyRoleInput" in response.text
    assert "filesystemPolicyAgentInput" in response.text
    assert "filesystemPolicyTaskInput" in response.text
    assert "filesystemPolicyCheckButton" in response.text
    assert "filesystemPolicyApprovalButton" in response.text
    assert "filesystemPolicyCheckOutput" in response.text
    assert "Check Filesystem" in response.text
    assert "cliPolicyForm" in response.text
    assert "cliPolicyEditor" in response.text
    assert "cliPolicyEditorOutput" in response.text
    assert "cliPolicyCancelEditButton" in response.text
    assert "cliPolicySubmitLabel" in response.text
    assert "cliPolicyMatchInput" in response.text
    assert "cliPolicyModeInput" in response.text
    assert "cliPolicyRolesInput" in response.text
    assert "hookPolicyForm" in response.text
    assert "hookPolicyEditor" in response.text
    assert "hookPolicyEditorOutput" in response.text
    assert "hookPolicyCancelEditButton" in response.text
    assert "hookPolicySubmitLabel" in response.text
    assert "hookPolicySurfaceInput" in response.text
    assert "hookPolicyEffectInput" in response.text
    assert "hookPolicyActionInput" in response.text
    assert "hookPolicyMatchInput" in response.text
    assert "hookPolicyPatternInput" in response.text
    assert '<input id="hookPolicyPatternInput" type="text" maxlength="300" required>' in (
        response.text
    )
    assert "hookPolicyReasonInput" in response.text
    assert "hookPolicyRolesInput" in response.text
    assert "hookPolicyPriorityInput" in response.text
    assert "recipeEditor" in response.text
    assert "recipeForm" in response.text
    assert "recipeEditorOutput" in response.text
    assert "recipeCancelEditButton" in response.text
    assert "recipeSubmitLabel" in response.text
    assert "recipeIdInput" in response.text
    assert "recipeNameInput" in response.text
    assert "recipeTemplateInput" in response.text
    assert "recipeDescriptionInput" in response.text
    assert "recipeCwdInput" in response.text
    assert "recipeTimeoutInput" in response.text
    assert "recipeTagsInput" in response.text
    assert "recipeParameterBuilder" in response.text
    assert "recipeAddParameterButton" in response.text
    assert "recipeEnabledInput" in response.text
    assert "recipeActionPanel" in response.text
    assert "pluginTrustReasonInput" in response.text
    assert "pluginTrustOutput" in response.text
    assert "settingsOutput" in response.text
    assert 'rel="icon" href="data:,"' in response.text
    assert "./app.js" in response.text
    assert "./app.css" in response.text


def test_web_ui_static_assets_are_served() -> None:
    client = TestClient(create_app())

    html_response = client.get("/ui/")
    script_response = client.get("/ui/app.js")
    style_response = client.get("/ui/app.css")

    assert html_response.status_code == 200
    assert script_response.status_code == 200
    assert "const TOKEN_KEY" in script_response.text
    assert "approvalSources" in script_response.text
    assert "approvalSource" in script_response.text
    assert "approvalStatusLabel" in script_response.text
    assert "approvalSourceLabel" in script_response.text
    assert "renderApprovalSummary" in script_response.text
    assert "renderApprovalReviewSummary" in script_response.text
    assert "approvalReviewPairs" in script_response.text
    assert "approvalReviewReferenceLabel" in script_response.text
    assert "approvalReviewContextTitle" in script_response.text
    assert "approvalReviewContextLines" in script_response.text
    assert "insertApprovalReviewContext" in script_response.text
    assert "useApprovalReviewContextAndAsk" in script_response.text
    assert "approval-review-use-context" in script_response.text
    assert "approval-review-use-and-ask" in script_response.text
    assert "Use Review Context" in script_response.text
    assert "Use Review & Ask" in script_response.text
    assert "renderApprovalExecutionControls" in script_response.text
    assert "renderBoundExecutionRequestPanel" in script_response.text
    assert "boundExecutionRequestScaffold" in script_response.text
    assert "filesystemBoundExecutionScaffold" in script_response.text
    assert "networkBoundExecutionScaffold" in script_response.text
    assert "networkPolicyCheckEndpoint" in script_response.text
    assert "networkPolicyApprovalRequest" in script_response.text
    assert "networkPolicyDecisionState" in script_response.text
    assert "renderNetworkPolicyDecision" in script_response.text
    assert "checkNetworkPolicy" in script_response.text
    assert "requestNetworkPolicyApproval" in script_response.text
    assert "editingNetworkDomainPolicyRuleId" in script_response.text
    assert "networkDomainPolicyLocked" in script_response.text
    assert "networkDomainPolicyRulePayload" in script_response.text
    assert "createNetworkDomainPolicyRule" in script_response.text
    assert "resetNetworkDomainPolicyForm" in script_response.text
    assert "editNetworkDomainPolicyRule" in script_response.text
    assert "patchNetworkDomainPolicyRule" in script_response.text
    assert "renderNetworkDomainPolicyList" in script_response.text
    assert "latestPolicyReviewResults?.networkRules" in script_response.text
    assert "latestFilesystemPolicyPreflight" in script_response.text
    assert "filesystemPolicyAccessPayload" in script_response.text
    assert "filesystemPolicyPayload" in script_response.text
    assert "filesystemPolicyPayloadKey" in script_response.text
    assert "filesystemPolicyApprovalRequest" in script_response.text
    assert "updateFilesystemPolicyFieldVisibility" in script_response.text
    assert "filesystemDecisionState" in script_response.text
    assert "renderFilesystemPolicyDecision" in script_response.text
    assert "checkFilesystemPolicy" in script_response.text
    assert "requestFilesystemPolicyApproval" in script_response.text
    assert "resetFilesystemPolicyApprovalState" in script_response.text
    assert '"/guardrails/network"' in script_response.text
    assert 'api("/network/policy/rules")' in script_response.text
    assert 'api("/network/policy/rules", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "/network/policy/rules/${encodeURIComponent(editingNetworkDomainPolicyRuleId)}" in (
        script_response.text
    )
    assert "/network/policy/rules/${encodeURIComponent(ruleId)}" in script_response.text
    assert 'managedPolicyLocks().includes("network_policy")' in script_response.text
    assert "network-domain-policy-edit" in script_response.text
    assert "network-domain-policy-toggle" in script_response.text
    assert "Network rules" in script_response.text
    assert "Network policy locked" in script_response.text
    assert "Network rule created" in script_response.text
    assert "Network rule updated" in script_response.text
    assert 'api("/guardrails/filesystem", {' in script_response.text
    assert "body: accessPayload" in script_response.text
    assert '"/web-retrieval/network/check"' in script_response.text
    assert 'endpoint: "/network/approvals"' in script_response.text
    assert 'endpoint: "/web-retrieval/network/approvals"' in script_response.text
    assert 'endpoint: "/filesystem/approvals"' in script_response.text
    assert 'body: { url, surface: "provider", action: "request" }' in script_response.text
    assert 'decision.mode !== "approval_required"' in script_response.text
    assert 'decision.permission_mode !== "approval_required"' in script_response.text
    assert "Approval requires a fresh check" in script_response.text
    assert "Approval requires a fresh filesystem check" in script_response.text
    assert "Network approval created" in script_response.text
    assert "Filesystem approval created" in script_response.text
    assert "Filesystem approval failed" in script_response.text
    assert "approvalPayloadKey" in script_response.text
    assert "filesystemBoundExecutionExpectedFields" in script_response.text
    assert "validateFilesystemBoundExecutionPayload" in script_response.text
    assert "must match the approved filesystem request." in script_response.text
    assert "Path digest" in script_response.text
    assert "Target digest" in script_response.text
    assert "Payload digest" in script_response.text
    assert "Options digest" in script_response.text
    assert "Policy digest" in script_response.text
    assert 'qs("#networkPolicyCheckForm").addEventListener("submit", checkNetworkPolicy)' in (
        script_response.text
    )
    assert (
        'qs("#filesystemPolicyCheckForm").addEventListener("submit", checkFilesystemPolicy)'
        in script_response.text
    )
    assert 'qs("#filesystemPolicyApprovalButton").addEventListener(' in script_response.text
    assert '"click",\n    requestFilesystemPolicyApproval,' in script_response.text
    assert (
        'qs("#networkPolicyApprovalButton").addEventListener("click", requestNetworkPolicyApproval)'
        in script_response.text
    )
    assert (
        'qs("#networkDomainPolicyForm").addEventListener("submit", createNetworkDomainPolicyRule)'
        in script_response.text
    )
    assert 'qs("#networkDomainPolicyCancelEditButton").addEventListener("click"' in (
        script_response.text
    )
    assert "Network policy decision" in script_response.text
    assert "Network policy checked" in script_response.text
    assert "Filesystem guardrail decision" in script_response.text
    assert "Filesystem guardrail checked" in script_response.text
    assert "Filesystem guardrail check failed" in script_response.text
    assert "Checking filesystem guardrail" in script_response.text
    assert "resolved_target_path" in script_response.text
    assert 'decision.permission_mode === "approval_required"' in script_response.text
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
    assert "renderBoundExecutionGuidedGroup" in script_response.text
    assert "isGuidedNestedValue" in script_response.text
    assert "isBoundExecutionLockedPath" in script_response.text
    assert "boundExecutionPayloadPathLabel" in script_response.text
    assert "boundExecutionGuidedFieldControl" in script_response.text
    assert "syncBoundExecutionGuidedField" in script_response.text
    assert "setBoundExecutionPayloadPathValue" in script_response.text
    assert "boundExecutionGuidedFieldValue" in script_response.text
    assert "boundExecutionPayloadFromText" in script_response.text
    assert "control.dataset.boundPayloadPath = pathText" in script_response.text
    assert "renderBoundExecutionGuidedField(body, scaffold, [...path, field]" in (
        script_response.text
    )
    assert 'make("details", "bound-execution-guided-group")' in script_response.text
    assert "Empty nested value" in script_response.text
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
    assert ".checkbox-row" in style_response.text
    assert "Dashboard execute" in script_response.text
    assert "network_approval_id" in script_response.text
    assert "await Promise.all([loadApprovals(), loadTaskChatContext()])" in (script_response.text)
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
    assert "renderProviderHealth" in script_response.text
    assert "checkProviderHealth" in script_response.text
    assert "/providers/${encodeURIComponent(providerId)}/health" in script_response.text
    assert "provider-health-check" in script_response.text
    assert "Provider health checked" in script_response.text
    assert "Provider health unavailable" in script_response.text
    assert "routingPreviewPayload" in script_response.text
    assert "previewProviderRoute" in script_response.text
    assert "renderRoutingDecision" in script_response.text
    assert 'api("/routing/decide", { method: "POST", body: payload })' in script_response.text
    assert "candidate_scores" in script_response.text
    assert "provider_id" in script_response.text
    assert "model_name" in script_response.text
    assert "max_cost_usd" in script_response.text
    assert "providerGenerationPayload" in script_response.text
    assert "runProviderGeneration" in script_response.text
    assert "renderProviderGenerationResult" in script_response.text
    assert "providerGenerationContextLines" in script_response.text
    assert "providerGenerationStreamInput" in script_response.text
    assert "TextDecoder" in script_response.text
    assert re.search(r"\.body\s*\.\s*getReader\(\)", script_response.text)
    assert re.search(
        r'["`]/providers/generate/stream["`][\s\S]{0,240}method:\s*"POST"',
        script_response.text,
    )
    assert re.search(
        r"updateProviderModelOptions\(\s*"
        r'"#providerGenerationProviderInput",\s*'
        r'"#providerGenerationModelInput",\s*'
        r'"#providerGenerationModelOptions",\s*'
        r'"#providerGenerationStreamInput"',
        script_response.text,
    )
    assert "provider-generation-use-response" in script_response.text
    assert 'api("/providers/generate", { method: "POST", body: payload })' in (script_response.text)
    assert "Provider generation completed" in script_response.text
    assert "Provider generation failed" in script_response.text
    assert (
        'qs("#providerGenerationForm").addEventListener("submit", runProviderGeneration)'
        in script_response.text
    )
    assert (
        'qs("#providerGenerationProviderInput").addEventListener("change", '
        "updateProviderGenerationModelOptions)" in script_response.text
    )
    assert 'qs("#routingPreviewForm").addEventListener("submit", previewProviderRoute)' in (
        script_response.text
    )
    assert "Provider route previewed" in script_response.text
    assert "Routing preview failed" in script_response.text
    assert "renderToolGovernanceList" in script_response.text
    assert "updateToolGovernance" in script_response.text
    assert "toolGovernancePayload" in script_response.text
    assert "/tools/${encodeURIComponent(toolName)}/governance" in script_response.text
    assert 'method: "PATCH"' in script_response.text
    assert "tool-governance-active" in script_response.text
    assert "tool-governance-deprecated" in script_response.text
    assert "tool-governance-disabled" in script_response.text
    assert "Governance reason required" in script_response.text
    assert "Tool governance updated" in script_response.text
    assert "Tool governance update failed" in script_response.text
    assert "memoryRetrievalPayload" in script_response.text
    assert "runMemoryRetrieval" in script_response.text
    assert "renderMemoryRetrievalResults" in script_response.text
    assert 'api("/api/v1/memory/retrieve/hybrid", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "combined_score" in script_response.text
    assert "matched_fields" in script_response.text
    assert "score_reasons" in script_response.text
    assert "query_time_ms" in script_response.text
    assert 'qs("#memoryRetrievalForm").addEventListener("submit", runMemoryRetrieval)' in (
        script_response.text
    )
    assert "Memory retrieval complete" in script_response.text
    assert "Memory retrieval failed" in script_response.text
    assert "memoryLifecyclePreviewPayload" in script_response.text
    assert "runMemoryLifecyclePreview" in script_response.text
    assert "runMemoryLifecycleApply" in script_response.text
    assert "renderMemoryLifecyclePreview" in script_response.text
    assert 'api("/api/v1/memory/lifecycle/preview", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert 'api("/api/v1/memory/lifecycle/apply", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "recommended_action" in script_response.text
    assert "const applied = result.applied === true" in script_response.text
    assert 'applied ? "Lifecycle applied" : "Lifecycle preview"' in script_response.text
    assert 'applied ? "true" : "false"' in script_response.text
    assert "compress_candidate" in script_response.text
    assert (
        'qs("#memoryLifecyclePreviewForm").addEventListener("submit", runMemoryLifecyclePreview)'
        in (script_response.text)
    )
    assert (
        'qs("#memoryLifecycleApplyButton").addEventListener("click", runMemoryLifecycleApply)'
        in script_response.text
    )
    assert 'window.confirm("Apply memory lifecycle changes for the current filters?")' in (
        script_response.text
    )
    assert "Memory lifecycle preview complete" in script_response.text
    assert "Memory lifecycle preview failed" in script_response.text
    assert "Applying memory lifecycle" in script_response.text
    assert "Memory lifecycle apply complete" in script_response.text
    assert "Memory lifecycle apply failed" in script_response.text
    assert "memoryCompressionPreviewPayload" in script_response.text
    assert "runMemoryCompressionPreview" in script_response.text
    assert "runMemoryCompressionApply" in script_response.text
    assert "renderMemoryCompressionPreview" in script_response.text
    assert "compressionSavings" in script_response.text
    assert 'api("/api/v1/memory/compression/preview", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert 'api("/api/v1/memory/compression/apply", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "compressed_description" in script_response.text
    assert "original_length" in script_response.text
    assert "compressed_length" in script_response.text
    assert "embedding_reindexed" in script_response.text
    assert 'applied ? "Compression applied" : "Compression preview"' in script_response.text
    assert 'qs("#memoryCompressionPreviewForm").addEventListener("submit"' in script_response.text
    assert "runMemoryCompressionPreview" in script_response.text
    assert (
        'qs("#memoryCompressionApplyButton").addEventListener("click", runMemoryCompressionApply)'
        in script_response.text
    )
    assert 'window.confirm("Apply memory compression changes for the current filters?")' in (
        script_response.text
    )
    assert "Memory compression preview complete" in script_response.text
    assert "Memory compression preview failed" in script_response.text
    assert "Applying memory compression" in script_response.text
    assert "Memory compression apply complete" in script_response.text
    assert "Memory compression apply failed" in script_response.text
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
    assert "TASK_CHAT_HANDOFF_RECENT_LIMIT" in script_response.text
    assert "latestTaskChatHandoffPacket" in script_response.text
    assert "safeHandoffString" in script_response.text
    assert "handoffReference" in script_response.text
    assert "handoffReferenceLabel" in script_response.text
    assert "taskChatHandoffPacket" in script_response.text
    assert "taskChatHandoffMarkdown" in script_response.text
    assert "renderTaskChatHandoffPreview" in script_response.text
    assert "copyTaskChatHandoff" in script_response.text
    assert "dgentic.task-chat-handoff.v1" in script_response.text
    assert "Task Chat handoff Markdown copied." in script_response.text
    assert "Task Chat handoff JSON copied." in script_response.text
    assert "taskPlanContextLines" in script_response.text
    assert "taskRunContextLines" in script_response.text
    assert "orchestrationContextLines" in script_response.text
    assert "taskChatProviderApprovalRequest" in script_response.text
    assert "createTaskChatProviderApprovalRequest" in script_response.text
    assert "renderTaskChatProviderApproval" in script_response.text
    assert "compactTaskChatProviderApproval" in script_response.text
    assert "renderTaskChatApprovalOutcome" in script_response.text
    assert "compactTaskChatApprovalOutcome" in script_response.text
    assert "appendTaskChatApprovalOutcomeMessage" in script_response.text
    assert "approvalOutcomeReferenceLabel" in script_response.text
    assert "approvalOutcomeContextTitle" in script_response.text
    assert "approvalOutcomeContextLines" in script_response.text
    assert "canUseApprovalOutcomeAndAsk" in script_response.text
    assert "useTaskChatApprovalOutcomeAndAsk" in script_response.text
    assert "task-chat-approval-outcome-use-context" in script_response.text
    assert "task-chat-approval-outcome-use-and-ask" in script_response.text
    assert "task-chat-approval-outcome-review" in script_response.text
    assert "Use Outcome & Ask" in script_response.text
    assert "Provider Approval Request" in script_response.text
    assert "Approval Outcome" in script_response.text
    assert "task-chat-provider-approval-use-id" in script_response.text
    assert "task-chat-provider-approval-review" in script_response.text
    assert "delete body.approval_id" in script_response.text
    assert "delete body.network_approval_id" in script_response.text
    assert 'qs("#taskChatProviderApprovalRequestButton").addEventListener(' in script_response.text
    assert (
        'qs("#taskChatHandoffPreviewButton").addEventListener("click", '
        "renderTaskChatHandoffPreview)" in script_response.text
    )
    assert 'copyTaskChatHandoff("markdown")' in script_response.text
    assert 'copyTaskChatHandoff("json")' in script_response.text
    assert "task-plan-use-context" in script_response.text
    assert "task-run-use-evidence" in script_response.text
    assert "task-chat-orchestration-use-context" in script_response.text
    assert "Use Context" in script_response.text
    assert "Use Evidence" in script_response.text
    assert "insertTaskChatContext(`Plan ${plan.id}`" in script_response.text
    assert "insertTaskChatContext(`Run ${run.id}`" in script_response.text
    assert "insertTaskChatContext(`Orchestration ${run.id}`" in script_response.text
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
    assert "loadTaskChatContext" in script_response.text
    assert "renderTaskChatContextStream" in script_response.text
    assert "renderTaskChatContextCard" in script_response.text
    assert "insertTaskChatContext" in script_response.text
    assert "TASK_CHAT_CONTEXT_REVIEW_PREVIEW_LIMIT" in script_response.text
    assert "TASK_CHAT_CONTEXT_REDACT_LIMIT" in script_response.text
    assert "redactHandoffSecrets" in script_response.text
    assert "taskChatContextBlocks" in script_response.text
    assert "writeTaskChatContextBlocks" in script_response.text
    assert "taskChatContextReviewStats" in script_response.text
    assert "updateTaskChatContextReviewStatus" in script_response.text
    assert "renderTaskChatContextReview" in script_response.text
    assert "renderTaskChatContextBlockList" in script_response.text
    assert "removeTaskChatContextBlock" in script_response.text
    assert "redactTaskChatContext" in script_response.text
    assert "clearTaskChatContext" in script_response.text
    assert "task-chat-context-review-preview" in script_response.text
    assert "task-chat-context-block-list" in script_response.text
    assert "task-chat-context-block" in script_response.text
    assert "task-chat-context-block-remove" in script_response.text
    assert "Context block changed; review refreshed." in script_response.text
    assert "Preview redaction is display-only" in script_response.text
    assert "Task chat context block removed." in script_response.text
    assert "Task chat context redacted." in script_response.text
    assert "Task chat context cleared." in script_response.text
    assert "useTaskChatContextAndAsk" in script_response.text
    assert "Use Context & Ask" in script_response.text
    assert "task-chat-plan-use-and-ask" in script_response.text
    assert "task-chat-run-use-and-ask" in script_response.text
    assert "task-chat-orchestration-context-use-and-ask" in script_response.text
    assert "task-chat-session-use-and-ask" in script_response.text
    assert "task-chat-memory-use-and-ask" in script_response.text
    assert "task-chat-log-use-and-ask" in script_response.text
    assert "safeHandoffString(String(line), 280)" in script_response.text
    assert "memoryContextLabel" in script_response.text
    assert "memoryMetadataContextLines" in script_response.text
    assert "memoryRetrievalContextLines" in script_response.text
    assert "task-chat-memory-use-context" in script_response.text
    assert "memory-retrieval-use-context" in script_response.text
    assert "memory-detail-use-context" in script_response.text
    assert (
        'safeLoad("task chat memory", () => '
        'api("/api/v1/memory/metadata?limit=6&lifecycle_state=active"))' in script_response.text
    )
    assert 'appendKeyValue(summary, "Memory"' in script_response.text
    assert 'appendKeyValue(summary, "Sessions"' in script_response.text
    assert "sessionSummaryPayload" in script_response.text
    assert "createSessionSummary" in script_response.text
    assert "loadSessionSummaries" in script_response.text
    assert "renderSessionSummaryList" in script_response.text
    assert "sessionSummaryContextLines" in script_response.text
    assert "logEventContextLines" in script_response.text
    assert "renderLogEvent" in script_response.text
    assert "task-chat-session-use-context" in script_response.text
    assert "session-summary-use-context" in script_response.text
    assert "log-event-use-context" in script_response.text
    assert "log-event-copy-evidence" in script_response.text
    assert 'api("/sessions/summary", { method: "POST", body: payload })' in script_response.text
    assert 'safeLoad("session summaries", () => api("/sessions/summary"))' in script_response.text
    assert "Promise.all([loadSessionSummaries(), loadLogs(), loadTaskChatContext()])" in (
        script_response.text
    )
    assert (
        "Plans, runs, orchestration runs, session summaries, memory, approvals, and logs"
        in script_response.text
    )
    assert "openTaskChatApprovalReview" in script_response.text
    assert "task-chat-approval-review" in script_response.text
    assert "appendTaskChatApprovalOutcomeMessage(selectedApproval)" in script_response.text
    assert "approval: { ...item.approval, status: review.status || item.approval.status }" in (
        script_response.text
    )
    assert "taskChatLatestActivity" in script_response.text
    assert "taskChatContextLines" in script_response.text
    assert "openTaskChatContextSection" in script_response.text
    assert "task chat orchestrations" in script_response.text
    assert 'api("/tasks/orchestrations")' in script_response.text
    assert 'appendKeyValue(summary, "Orchestrations"' in script_response.text
    assert 'safeLoad("task chat sessions", () => api("/sessions/summary"))' in script_response.text
    assert "isAuthorizationError" in script_response.text
    assert "unavailable_count" in script_response.text
    assert "Limited sources" in script_response.text
    assert "Context added to task chat." in script_response.text
    assert "Use Context" in script_response.text
    assert 'api("/projects/active")' in script_response.text
    assert 'api("/logs")' in script_response.text
    assert "api(`${source.base}?status=pending`)" in script_response.text
    assert "Promise.all([loadTasks(), loadTaskChatContext()])" in script_response.text
    assert "Promise.all([loadProjects(), loadTaskChatContext()])" in script_response.text
    assert "submitTaskChatMessage" in script_response.text
    assert "appendTaskChatMessage" in script_response.text
    assert "renderTaskChatThread" in script_response.text
    assert "renderTaskChatMessage" in script_response.text
    assert "renderTaskChatPlan" in script_response.text
    assert "renderTaskChatExecution" in script_response.text
    assert "renderTaskChatOrchestration" in script_response.text
    assert "taskChatProviderPrompt" in script_response.text
    assert "taskChatProviderPromptPreviewRecord" in script_response.text
    assert "renderTaskChatProviderPromptPreview" in script_response.text
    assert "previewTaskChatProviderPrompt" in script_response.text
    assert "compactTaskChatProviderPromptPreview" in script_response.text
    assert "task-chat-provider-prompt-preview" in script_response.text
    assert "Provider Prompt Preview" in script_response.text
    assert "taskChatProviderPayload" in script_response.text
    assert "taskChatProviderRoleInput" in script_response.text
    assert 'role: qs("#taskChatProviderRoleInput").value' in script_response.text
    assert "taskChatRoutePreviewPayload" in script_response.text
    assert "taskChatRouteCapabilities" in script_response.text
    assert "previewTaskChatProviderRoute" in script_response.text
    assert "compactTaskChatRouteDecision" in script_response.text
    assert "renderTaskChatRouteDecision" in script_response.text
    assert "taskChatRouteContextLines" in script_response.text
    assert "applyTaskChatRoute" in script_response.text
    assert "applyTaskChatRouteAndAsk" in script_response.text
    assert "task-chat-route-use-provider" in script_response.text
    assert "task-chat-route-use-and-ask" in script_response.text
    assert "task-chat-route-use-context" in script_response.text
    assert "Use Route & Ask" in script_response.text
    assert "Provider Route" in script_response.text
    assert 'api("/routing/decide", { method: "POST", body: payload })' in script_response.text
    assert 'qs("#taskChatRouteButton").addEventListener("click", previewTaskChatProviderRoute)' in (
        script_response.text
    )
    assert "askTaskChatProvider" in script_response.text
    assert 'qs("#taskChatProviderPromptPreviewButton").addEventListener(' in script_response.text
    assert "renderTaskChatProviderGeneration" in script_response.text
    assert "compactTaskChatProviderGeneration" in script_response.text
    assert "task-chat-provider-use-response" in script_response.text
    assert "task-chat-provider-use-and-ask" in script_response.text
    assert "Use Response & Ask" in script_response.text
    assert "useTaskChatProviderResponseAndAsk" in script_response.text
    assert 'safeHandoffString(result.content || "", 900)' in script_response.text
    assert "Provider Reply" in script_response.text
    assert "Provider Stream" in script_response.text
    assert 'requested_by: "dashboard-task-chat"' in script_response.text
    assert 'api("/providers/generate", { method: "POST", body: providerPayload })' in (
        script_response.text
    )
    assert "await readProviderGenerationStream(providerPayload)" in script_response.text
    assert re.search(
        r"updateProviderModelOptions\(\s*"
        r'"#taskChatProviderInput",\s*'
        r'"#taskChatProviderModelInput",\s*'
        r'"#taskChatProviderModelOptions",\s*'
        r'"#taskChatProviderStreamInput"',
        script_response.text,
    )
    assert "taskChatExecutionRecord" in script_response.text
    assert "taskPlanOrchestrationPayload" in script_response.text
    assert "taskRunSummaryLine" in script_response.text
    assert "taskRunDurationLine" in script_response.text
    assert "compactTaskChatExecution" in script_response.text
    assert "compactTaskChatOrchestrationRun" in script_response.text
    assert "compactTaskChatStepResult" in script_response.text
    assert "updateTaskChatMessage" in script_response.text
    assert "task-chat-execution-use-evidence" in script_response.text
    assert "task-plan-create-orchestration" in script_response.text
    assert "providerRoutingEntries" in script_response.text
    assert "renderProviderRoutingSettings" in script_response.text
    assert "applyProviderRoutingSettingToTaskChat" in script_response.text
    assert "applyProviderRoutingSettingToPreview" in script_response.text
    assert "provider-routing-use-task-chat" in script_response.text
    assert "provider-routing-preview-role" in script_response.text
    assert 'settingMap.get("provider_role_routing")' in script_response.text
    assert "Create Orchestration" in script_response.text
    assert 'api("/tasks/orchestrations", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "runTaskChatPlan" in script_response.text
    assert "runTaskPlan" in script_response.text
    assert 'qs("#taskChatForm").addEventListener("submit", submitTaskChatMessage)' in (
        script_response.text
    )
    assert 'qs("#taskChatProviderButton").addEventListener("click", askTaskChatProvider)' in (
        script_response.text
    )
    assert (
        'qs("#taskChatProviderInput").addEventListener("change", '
        "updateTaskChatProviderModelOptions)" in script_response.text
    )
    assert 'api("/tasks/plan", { method: "POST", body: payload })' in script_response.text
    assert 'api("/filesystem/list"' in script_response.text
    assert 'api("/filesystem/read"' in script_response.text
    assert 'api("/filesystem/write"' in script_response.text
    assert "openFileBaselineContent" in script_response.text
    assert "lastWorkspaceAppliedChange" in script_response.text
    assert "workspaceChangeStats" in script_response.text
    assert "renderWorkspaceChangeReview" in script_response.text
    assert "previewWorkspaceFileChange" in script_response.text
    assert "applyWorkspaceFileChange" in script_response.text
    assert "revertWorkspaceFileChange" in script_response.text
    assert 'qs("#workspacePreviewButton").addEventListener("click"' in script_response.text
    assert 'qs("#workspaceApplyButton").addEventListener("click"' in script_response.text
    assert 'qs("#workspaceRevertButton").addEventListener("click"' in script_response.text
    assert 'qs("#workspaceEditor").addEventListener("input", renderWorkspaceChangeReview)' in (
        script_response.text
    )
    assert "Pending file change" in script_response.text
    assert "File change applied" in script_response.text
    assert "File change reverted" in script_response.text
    assert "Discard unsaved editor changes" in script_response.text
    assert "body: { path: change.path, content: change.previousContent }" in script_response.text
    assert 'api("/cli/runs"' in script_response.text
    assert "api(`/cli/runs/${encodeURIComponent(runId)}/output`)" in script_response.text
    assert "api(`/cli/approvals/${encodeURIComponent(approvalId)}/execute`" in script_response.text
    assert 'api("/cli/policy/rules")' in script_response.text
    assert 'api("/cli/recipes")' in script_response.text
    assert "renderRecipeList" in script_response.text
    assert "renderRecipeActionPanel" in script_response.text
    assert "commandRecipeEditorPayload" in script_response.text
    assert "commandRecipeEditorParameters" in script_response.text
    assert "appendCommandRecipeParameterRow" in script_response.text
    assert "createCommandRecipe" in script_response.text
    assert "editCommandRecipe" in script_response.text
    assert "patchCommandRecipe" in script_response.text
    assert "resetCommandRecipeForm" in script_response.text
    assert 'api("/cli/recipes", { method: "POST", body: payload })' in script_response.text
    assert "/cli/recipes/${encodeURIComponent(editingCommandRecipeId)}" in script_response.text
    assert "/cli/recipes/${encodeURIComponent(recipeId)}" in script_response.text
    assert "{ enabled: recipe.enabled === false }" in script_response.text
    assert "command-recipe-edit" in script_response.text
    assert "command-recipe-toggle" in script_response.text
    assert 'managedPolicyLocks().includes("command_recipes")' in script_response.text
    assert (
        'qs("#recipeForm").addEventListener("submit", createCommandRecipe)' in script_response.text
    )
    assert 'qs("#recipeCancelEditButton").addEventListener("click"' in script_response.text
    assert "commandRecipePayload" in script_response.text
    assert "postCommandRecipeAction" in script_response.text
    assert "data-recipe-parameter" in script_response.text
    assert "/cli/recipes/${encodeURIComponent(recipeId)}/${action}" in script_response.text
    assert 'api("/guardrails/hooks/rules")' in script_response.text
    assert 'api("/plugins")' in script_response.text
    assert "renderPluginList" in script_response.text
    assert "patchPluginTrust" in script_response.text
    assert "pluginRecordsFromResult" in script_response.text
    assert "pluginTrustLocked" in script_response.text
    assert 'managedPolicyLocks().includes("plugin_trust")' in script_response.text
    assert "/plugins/${encodeURIComponent(pluginId)}/trust" in script_response.text
    assert "body: { status, reason }" in script_response.text
    assert "plugin-trust-trust" in script_response.text
    assert "plugin-trust-block" in script_response.text
    assert "Plugin trust locked" in script_response.text
    assert "Plugin trust updated" in script_response.text
    assert "pluginActivationLocked" in script_response.text
    assert "pluginReferenceComponentCount" in script_response.text
    assert "pluginActivationEndpoint" in script_response.text
    assert "renderPluginActivationResult" in script_response.text
    assert "runPluginActivation" in script_response.text
    assert "appendPluginActivationControls" in script_response.text
    assert "pluginActivationOutput" in html_response.text
    assert "/plugins/${encoded}/components" in script_response.text
    assert "/plugins/${encoded}/components/${action}" in script_response.text
    assert "/plugins/${encoded}/${route}/${action}" in script_response.text
    assert 'locks.includes("plugin_components")' in script_response.text
    assert 'locks.includes("plugin_command_recipes")' in script_response.text
    assert 'locks.includes("plugin_hook_policies")' in script_response.text
    assert "button.dataset.testid = `plugin-${family}-${action}`" in script_response.text
    assert '"Preview Components"' in script_response.text
    assert '"Install Components"' in script_response.text
    assert '"Disable Components"' in script_response.text
    assert '"Preview Recipes"' in script_response.text
    assert '"Install Recipes"' in script_response.text
    assert '"Preview Hooks"' in script_response.text
    assert '"Install Hooks"' in script_response.text
    assert "Plugin activation locked" in script_response.text
    assert "Plugin activation failed" in script_response.text
    assert 'api("/settings/effective")' in script_response.text
    assert "renderProjectContext" in script_response.text
    assert "activeRootDir" in script_response.text
    assert "projectOpenRootButton" in script_response.text
    assert "projectPreflightButton" in script_response.text
    assert "projectForm" in script_response.text
    assert "projectEditPanel" in html_response.text
    assert "projectEditForm" in html_response.text
    assert "projectEditStatusInput" in html_response.text
    assert 'api("/projects/preflight"' in script_response.text
    assert 'api("/projects"' in script_response.text
    assert 'api("/projects/active")' in script_response.text
    assert "activateProject" in script_response.text
    assert "api(`/projects/${encodeURIComponent(projectId)}/activate`" in script_response.text
    assert "editProject" in script_response.text
    assert "projectEditPayload" in script_response.text
    assert "patchProject" in script_response.text
    assert "toggleProjectStatus" in script_response.text
    assert "project-status-toggle" in script_response.text
    assert "api(`/projects/${encodeURIComponent(projectId)}`" in script_response.text
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
    assert "renderMemoryReliabilityDetail" in script_response.text
    assert "renderMemoryMetadataEditor" in script_response.text
    assert "memoryMetadataIsEditable" in script_response.text
    assert "memoryMetadataEditorPayload" in script_response.text
    assert "saveMemoryMetadataEdit" in script_response.text
    assert "memoryMetadataTagsInput" in script_response.text
    assert "memoryMetadataCategoryInput" in script_response.text
    assert "memoryMetadataDescriptionInput" in script_response.text
    assert "memoryMetadataRelevanceInput" in script_response.text
    assert "memoryMetadataRetentionInput" in script_response.text
    assert "memory-metadata-save" in script_response.text
    assert "Memory metadata read-only" in script_response.text
    assert "Memory metadata updated." in script_response.text
    assert "Memory metadata update failed" in script_response.text
    assert "/api/v1/memory/metadata/${encodeURIComponent(metadataId)}" in script_response.text
    assert 'method: "PATCH"' in script_response.text
    assert "loadMemoryReliabilityDetail" in script_response.text
    assert "memory-reliability-detail" in script_response.text
    assert "/api/v1/memory/metadata/${encodeURIComponent(metadataId)}" in script_response.text
    assert "Memory detail loaded" in script_response.text
    assert "Memory detail failed" in script_response.text
    assert "renderToolReliability" in script_response.text
    assert "renderToolReliabilityDetail" in script_response.text
    assert "loadToolReliabilityDetail" in script_response.text
    assert "tool-reliability-detail" in script_response.text
    assert "/api/v1/tools/registry/${encodeURIComponent(toolId)}" in script_response.text
    assert "Tool detail loaded" in script_response.text
    assert "Tool detail failed" in script_response.text
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
    assert "latestGitChangeReviewArtifacts" in script_response.text
    assert "gitDiffReviewDecisions" in script_response.text
    assert "gitDiffReviewDecisionFilter" in script_response.text
    assert "renderGitDiffReviewPanel" in script_response.text
    assert "loadGitDiffReview" in script_response.text
    assert "renderGitDiffSection" in script_response.text
    assert "gitDiffReviewPayload" in script_response.text
    assert "renderGitChangeReview" in script_response.text
    assert "gitDiffReviewVisibleSections" in script_response.text
    assert "setGitDiffReviewDecisionFilter" in script_response.text
    assert "setVisibleGitDiffReviewDecisions" in script_response.text
    assert "gitDiffSectionReviewState" in script_response.text
    assert "gitDiffSectionDecisionReason" in script_response.text
    assert "setGitDiffSectionDecisionReason" in script_response.text
    assert "gitChangeReviewEvidence" in script_response.text
    assert "copyGitChangeReviewEvidence" in script_response.text
    assert "gitChangeReviewArtifactPayload" in script_response.text
    assert "loadGitChangeReviewArtifacts" in script_response.text
    assert "saveGitChangeReviewArtifact" in script_response.text
    assert "applyGitChangeReviewArtifact" in script_response.text
    assert "renderGitChangeReviewArtifacts" in script_response.text
    assert "gitChangeReviewArtifactCounts" in script_response.text
    assert 'api("/cli/git/change-review-artifacts", {' in script_response.text
    assert "/cli/git/change-review-artifacts?" in script_response.text
    assert "Save Artifact" in script_response.text
    assert "Saved artifacts" in script_response.text
    assert "Review note" in script_response.text
    assert "Reason, risk, or follow-up for this decision" in script_response.text
    assert "reason: gitDiffSectionDecisionReason(section)" in script_response.text
    assert "reason: decision.reason" in script_response.text
    assert "reason: decision.reason ||" in script_response.text
    assert "Stale artifacts cannot unblock Git closeout." in script_response.text
    assert "setGitDiffSectionDecision" in script_response.text
    assert "gitDiffReviewDecisionCounts" in script_response.text
    assert "gitDiffReviewHasRejectedSections" in script_response.text
    assert "updateGitReviewDecisionGate" in script_response.text
    assert "Git closeout paused" in script_response.text
    assert 'make("button", "success-button", "Accept")' in script_response.text
    assert 'make("button", "danger-button", "Reject")' in script_response.text
    assert 'make("button", "link-button", "Clear")' in script_response.text
    assert 'make("button", "success-button", "Accept Visible")' in script_response.text
    assert 'make("button", "danger-button", "Reject Visible")' in script_response.text
    assert 'make("button", "link-button", "Clear Visible")' in script_response.text
    assert 'make("button", "link-button", "Copy Patch")' in script_response.text
    assert "filterButton.dataset.testid = `git-diff-filter-${value}`" in script_response.text
    assert '["All", "all"]' in script_response.text
    assert '["Accepted", "accepted"]' in script_response.text
    assert '["Rejected", "rejected"]' in script_response.text
    assert '["Pending", "pending"]' in script_response.text
    assert "No visible diff sections" in script_response.text
    assert "Diff patch copied." in script_response.text
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
    assert "hookPolicyRulePayload" in script_response.text
    assert "createHookPolicyRule" in script_response.text
    assert "editHookPolicyRule" in script_response.text
    assert "patchHookPolicyRule" in script_response.text
    assert "resetHookPolicyForm" in script_response.text
    assert "renderHookPolicyList" in script_response.text
    assert "validateHookPolicyRulePayload" in script_response.text
    assert "updateHookPolicyPatternRequirement" in script_response.text
    assert "Pattern is required unless match is Any." in script_response.text
    assert "renderHookPolicyList(latestPolicyReviewResults.hooks)" in script_response.text
    assert 'api("/guardrails/hooks/rules")' in script_response.text
    assert 'api("/guardrails/hooks/rules", { method: "POST", body: payload })' in (
        script_response.text
    )
    assert "/guardrails/hooks/rules/${encodeURIComponent(ruleId)}" in script_response.text
    assert 'managedPolicyLocks().includes("hook_policy")' in script_response.text
    assert "hook-policy-edit" in script_response.text
    assert "hook-policy-toggle" in script_response.text
    assert (
        'qs("#hookPolicyForm").addEventListener("submit", createHookPolicyRule)'
        in script_response.text
    )
    assert (
        'qs("#hookPolicyMatchInput").addEventListener("change", '
        "updateHookPolicyPatternRequirement)" in script_response.text
    )
    assert 'qs("#hookPolicyCancelEditButton").addEventListener("click"' in script_response.text
    assert style_response.status_code == 200
    assert ".app-shell" in style_response.text
    assert ".panel > *" in style_response.text
    assert "grid-template-columns: minmax(0, 1fr);" in style_response.text
    assert ".task-chat" in style_response.text
    assert ".task-chat-header-actions" in style_response.text
    assert ".task-chat-history-status" in style_response.text
    assert ".task-chat-transcript" in style_response.text
    assert ".task-chat-context-stream" in style_response.text
    assert ".task-chat-context-summary" in style_response.text
    assert ".task-chat-context-cards" in style_response.text
    assert ".task-chat-context-card" in style_response.text
    assert ".task-chat-context-actions" in style_response.text
    assert ".task-chat-handoff-panel" in style_response.text
    assert ".task-chat-handoff-actions" in style_response.text
    assert ".task-chat-handoff-preview" in style_response.text
    assert ".task-chat-message" in style_response.text
    assert ".task-chat-message-user" in style_response.text
    assert ".task-chat-message-agent" in style_response.text
    assert ".task-chat-composer" in style_response.text
    assert ".task-chat-plan-card" in style_response.text
    assert ".task-chat-execution-card" in style_response.text
    assert ".task-chat-orchestration-card" in style_response.text
    assert ".task-chat-execution-header" in style_response.text
    assert ".task-chat-execution-grid" in style_response.text
    assert ".task-chat-execution-results" in style_response.text
    assert ".task-run-actions" in style_response.text
    assert "grid-column: 1 / -1;" in style_response.text
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
    assert ".workspace-change-actions" in style_response.text
    assert ".workspace-change-review" in style_response.text
    assert ".workspace-change-review:empty" in style_response.text
    assert ".approval-filter-row" in style_response.text
    assert ".segmented-control button" in style_response.text
    assert "flex: 1 1 96px;" in style_response.text
    assert ".approval-summary-grid" in style_response.text
    assert ".approval-review-summary" in style_response.text
    assert ".bound-execution-panel" in style_response.text
    assert ".bound-execution-editor" in style_response.text
    assert ".bound-execution-guided-fields" in style_response.text
    assert ".bound-execution-guided-field" in style_response.text
    assert ".bound-execution-guided-group" in style_response.text
    assert ".bound-execution-guided-group-body" in style_response.text
    assert ".review-warning-list" in style_response.text
    assert ".context-grid" in style_response.text
    assert ".checkpoint-grid" in style_response.text
    assert ".reliability-grid" in style_response.text
    assert ".policy-grid" in style_response.text
    assert ".activity-layout" in style_response.text
    assert ".session-summary-card" in style_response.text
    assert ".session-summary-actions" in style_response.text
    assert ".log-actions" in style_response.text
    assert ".recipe-action-panel" in style_response.text
    assert ".recipe-parameter-editor" in style_response.text
    assert ".recipe-parameter-builder" in style_response.text
    assert ".recipe-parameter-row" in style_response.text
    assert ".plugin-trust-editor" in style_response.text
    assert ".recipe-parameter-grid" in style_response.text
    assert ".recipe-action-buttons" in style_response.text
    assert ".approval-list" in style_response.text
    assert ".settings-review-summary" in style_response.text
    assert ".settings-routing-review" in style_response.text
    assert ".settings-routing-card" in style_response.text
    assert ".settings-routing-actions" in style_response.text
    assert ".task-chat-context-review-panel" in style_response.text
    assert ".task-chat-context-review-status" in style_response.text
    assert ".task-chat-context-review-actions" in style_response.text
    assert ".task-chat-context-review-preview" in style_response.text
    assert ".task-chat-context-block-list" in style_response.text
    assert ".task-chat-context-block" in style_response.text
    assert ".task-chat-context-block-excerpt" in style_response.text
    assert ".task-chat-context-block-remove" in style_response.text
    assert ".settings-group-list" in style_response.text
    assert ".setting-source-row" in style_response.text
    assert ".policy-review-section" in style_response.text
    assert ".policy-editor" in style_response.text
    assert ".git-approval-actions" in style_response.text
    assert ".direct-run-button" in style_response.text
    assert ".git-run-summary" in style_response.text
    assert ".git-change-review" in style_response.text
    assert ".git-change-review-artifacts" in style_response.text
    assert ".git-change-review-artifact" in style_response.text
    assert ".git-diff-review" in style_response.text
    assert ".git-diff-section" in style_response.text
    assert ".git-diff-decision-controls" in style_response.text
    assert ".git-diff-review-note" in style_response.text
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


def test_memory_lifecycle_threshold_controls_match_backend_request_contract() -> None:
    client = TestClient(create_app())

    html_response = client.get("/ui/")
    script_response = client.get("/ui/app.js")

    assert html_response.status_code == 200
    assert script_response.status_code == 200
    for control_id in [
        "memoryLifecycleArchiveDaysInput",
        "memoryLifecycleSoftPruneDaysInput",
        "memoryLifecycleArchiveRelevanceInput",
        "memoryLifecycleSoftPruneRelevanceInput",
        "memoryLifecyclePromoteRelevanceInput",
        "memoryLifecyclePromoteAccessInput",
        "memoryLifecycleCompressDaysInput",
        "memoryLifecycleCompressAccessInput",
    ]:
        assert f'id="{control_id}"' in html_response.text

    integer_thresholds = [
        ("archive_after_days", "memoryLifecycleArchiveDaysInput", "90", "1", "3650"),
        ("soft_prune_after_days", "memoryLifecycleSoftPruneDaysInput", "365", "1", "3650"),
        (
            "promote_access_count_threshold",
            "memoryLifecyclePromoteAccessInput",
            "20",
            "1",
            "1000000",
        ),
        ("compress_after_days", "memoryLifecycleCompressDaysInput", "30", "1", "3650"),
        (
            "compress_access_count_threshold",
            "memoryLifecycleCompressAccessInput",
            "10",
            "1",
            "1000000",
        ),
    ]
    for field, control_id, fallback, minimum, maximum in integer_thresholds:
        assert re.search(
            rf"{field}:\s*Math\.trunc\(\s*"
            rf'boundedNumber\("#{control_id}", {fallback}, {minimum}, {maximum}\),?\s*\)',
            script_response.text,
        )

    decimal_thresholds = [
        ("archive_relevance_threshold", "memoryLifecycleArchiveRelevanceInput", "0.4"),
        ("soft_prune_relevance_threshold", "memoryLifecycleSoftPruneRelevanceInput", "0.2"),
        ("promote_relevance_threshold", "memoryLifecyclePromoteRelevanceInput", "0.9"),
    ]
    for field, control_id, fallback in decimal_thresholds:
        assert re.search(
            rf'{field}:\s*boundedNumber\("#{control_id}", {fallback}, 0, 1\)',
            script_response.text,
        )


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


def test_web_ui_can_create_provider_and_tool_approval_requests_from_runtime_panel() -> None:
    client = TestClient(create_app())

    index_response = client.get("/ui/")
    script_response = client.get("/ui/app.js")

    assert index_response.status_code == 200
    assert script_response.status_code == 200
    for expected in [
        'article id="providers"',
        "providerApprovalRequestForm",
        "providerApprovalProviderInput",
        "providerApprovalModelOptions",
        "providerApprovalOptionsInput",
        "toolApprovalRequestForm",
        "toolApprovalPayloadInput",
        "toolApprovalNameOptions",
    ]:
        assert expected in index_response.text
    for expected in [
        "populateProviderApprovalControls",
        "updateProviderApprovalModelOptions",
        "providerApprovalPayload",
        "providerApprovalRequest",
        "createProviderApprovalRequest",
        "toolApprovalPayload",
        "toolApprovalRequest",
        "createToolApprovalRequest",
        "`/providers/${encodeURIComponent(body.provider_id)}/approvals${requesterQuery(body.requested_by)}`",
        "`/tools/${encodeURIComponent(request.toolName)}/approvals${requesterQuery(request.payload.requested_by)}`",
        'setApprovalFilterState("provider", "pending")',
        'setApprovalFilterState("tool", "pending")',
        "loadTaskChatContext()",
    ]:
        assert expected in script_response.text


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
