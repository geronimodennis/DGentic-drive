# Developer Setup

Date created: 2026-05-07

This guide explains how to run the current DGentic backend foundation and first web dashboard.

## Prerequisites

- Python 3.11 or newer, below Python 3.15.
- `uv` for dependency management.

## Install Dependencies

From the repository root:

```powershell
uv sync --dev
```

## Configure Environment

Copy `.env.example` to `.env` if local overrides are needed:

```powershell
Copy-Item .env.example .env
```

Default settings:

- `DGENTIC_APP_NAME=DGentic`
- `DGENTIC_ENVIRONMENT=development`
- `DGENTIC_ROOT_DIR=.`
- `DGENTIC_DATA_DIR=.dgentic`
- `DGENTIC_DATABASE_URL` unset, which means SQLAlchemy uses SQLite at `DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db`
- `DGENTIC_AUTOPILOT_ENABLED=false`
- `DGENTIC_MANAGED_SETTINGS_FILE` empty by default; set it to an organization-managed JSON file when deployment-owned settings should override `.env` and environment values
- `DGENTIC_AUTH_ENABLED` unset, which means auth is off in development and on in staging/production
- `DGENTIC_AUTH_TOKENS` empty by default
- `DGENTIC_OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `DGENTIC_LM_STUDIO_BASE_URL=http://127.0.0.1:1234`
- `DGENTIC_PROVIDER_ALLOWED_BASE_URLS` empty by default; add comma-separated exact provider base URLs only when an additional trusted provider endpoint is configured
- `DGENTIC_NETWORK_DOMAIN_POLICY` empty by default, which means provider and generated-tool Python socket network-domain checks allow by default
- Provider retry defaults: `DGENTIC_PROVIDER_RETRY_MAX_ATTEMPTS=3`, `DGENTIC_PROVIDER_RETRY_INITIAL_DELAY_SECONDS=0.2`, `DGENTIC_PROVIDER_RETRY_MAX_DELAY_SECONDS=2.0`, and `DGENTIC_PROVIDER_RETRY_BACKOFF_MULTIPLIER=2.0`
- `DGENTIC_PROVIDER_PRICING_CATALOG` empty by default; optionally set a bounded JSON map of exact provider/model advisory prices for routing and usage estimates
- OpenAI-compatible external adapter defaults: `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL`, `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV`, `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF`, and `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS` are empty, so the adapter is disabled
- `DGENTIC_CREDENTIAL_VAULT_KEY` is empty by default; set a Fernet key generated outside DGentic only when creating or resolving `local_vault` credential references
- `DGENTIC_CREDENTIAL_PROCESS_ADAPTERS` is empty by default; optional shell-free credential process adapters are disabled unless explicitly configured with absolute command paths
- `managed_credential_references` can be declared only inside `DGENTIC_MANAGED_SETTINGS_FILE`; ordinary environment variables with that name are ignored for managed record loading
- `DGENTIC_WEB_RETRIEVAL_TIMEOUT_SECONDS=10` and `DGENTIC_WEB_RETRIEVAL_MAX_RESPONSE_BYTES=262144` bound the guarded single-URL web retrieval fetch runtime

## Configure API Authentication

Local development is usable without authentication by default. In `staging` and `production`, DGentic enables bearer-token capability checks unless `DGENTIC_AUTH_ENABLED=false` is explicitly set.

When authentication is enabled, DGentic requires either at least one valid bootstrap `token=capabilities` entry in `DGENTIC_AUTH_TOKENS` or at least one active persisted generated token in `auth-tokens.json`. Startup fails closed if auth is enabled without a usable environment token or active persisted token. New persisted tokens are issued for active operator identities stored in `operators.json`; operators can also reference persisted operator groups in `operator-groups.json`, and requested token capabilities cannot exceed the operator's current direct plus active group-inherited effective capabilities. Operator display/role metadata, operator group display/description metadata, auth-token labels, and credential-reference labels are redacted for common secret-shaped values before API responses, audit metadata, and new or mutated JSON persistence.

Token configuration uses semicolon-separated token entries and comma-separated capabilities:

```powershell
$env:DGENTIC_ENVIRONMENT = "production"
$env:DGENTIC_AUTH_TOKENS = "admin-token=admin;task-token=tasks;cli-token=cli"
```

Use a bearer token when calling protected routes:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tasks/plan `
  -Headers @{ Authorization = "Bearer task-token" } `
  -ContentType "application/json" `
  -Body '{"objective":"Create a guarded plan for indexing project memory."}'
```

Persisted generated tokens can be issued and rotated with a bootstrap admin token or another principal that has auth-token management access. Create optional operator groups, create an operator profile, then issue a token within that operator's effective capabilities. The raw token is returned only from create or rotate responses; stored records keep salted PBKDF2 hashes and expose safe metadata when listed:

```powershell
$group = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/auth/operator-groups `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"group_id":"group-ops","display_name":"Operations","capabilities":["logs"]}'

$operator = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/auth/operators `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"operator_id":"operator-alpha","display_name":"Operator Alpha","role":"automation","capabilities":["tasks"],"group_ids":["group-ops"]}'

$created = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/auth/tokens `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"operator_id":"operator-alpha","label":"task automation","capabilities":["tasks","logs"]}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/auth/tokens/$($created.record.id)/rotate" `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"label":"rotated task automation","capabilities":["tasks","logs"]}'
```

Capability groups currently include `admin`, `auth`, `credentials`, `tasks`, `filesystem`, `cli`, `providers`, `approvals`, `network`, `hooks`, `agents`, `memory`, `tools`, `sessions`, and `logs`. The `admin` capability can access all protected route groups, and operator group management is protected by the `auth` capability. Public routes remain `GET /`, `GET /health`, `/docs`, `/redoc`, `/openapi.json`, and the static `/ui/` dashboard shell. The dashboard stores any entered bearer token only in the browser session and uses it for protected API calls. Plugin discovery and trust routes use the `tools` capability. Hook policy rule routes use the `hooks` capability. Filesystem approval creation and bound filesystem execution use the `filesystem` capability, while filesystem approval list, review, approve, and deny routes use the separate `approvals` capability. CLI approval creation and approved-command execution use the `cli` capability; CLI approval list, review, approve, and deny routes use the separate `approvals` capability.

## Configure Managed Settings

Set `DGENTIC_MANAGED_SETTINGS_FILE` when deployment-owned runtime settings should be enforced from a JSON file instead of local `.env` edits. The file is loaded at settings initialization, must be valid JSON, must contain a top-level `settings` object, and may only include supported runtime policy fields. Managed values override `.env` and process environment values. Malformed files, unknown fields, unsupported bootstrap fields such as `root_dir`, `data_dir`, `database_url`, raw auth tokens, vault keys, or secret-shaped text fail closed.

Example:

```json
{
  "settings": {
    "auth_enabled": true,
    "network_domain_policy": {
      "default_mode": "deny",
      "rules": [
        {
          "domain": "provider.example.test",
          "mode": "allow"
        }
      ]
    }
  }
}
```

Use `GET /settings/effective` with an admin-capable token to inspect effective values, source labels, managed field names, and the managed-file SHA-256 digest. Secret-bearing settings are redacted in that view.

The same managed file can publish deployment-owned plugin trust records with `managed_plugin_trust_records`. Each record pins one plugin id to an exact manifest digest and `trusted` or `blocked` status. Managed plugin trust is reported as `trust_source: "managed"`, overrides local `plugin-trust.json` for that plugin id, and rejects local trust mutation until the managed record is removed or changed.

Managed files can also publish deployment-owned command recipes with `managed_command_recipes`. These records use the normal command recipe schema, appear from `GET /cli/recipes` and `GET /cli/recipes/{recipe_id}` with `source: "managed"`, and execute, preview, request approvals, and start runs through the existing CLI runtime and approval contracts. They are only honored from `DGENTIC_MANAGED_SETTINGS_FILE`, are validated fail-closed for duplicate normalized fields, duplicate normalized ids, unsafe templates, and secret-shaped text, are never written to `command-recipes.json`, and cannot be created, patched, or shadowed by local or plugin recipe mutation routes.

Managed files can configure HashiCorp Vault KV v2 credential adapters with `credential_secret_manager_adapters`, `credential_secret_manager_allowed_base_urls`, and `managed_credential_references` records using `source_type: "secret_manager"`. Adapter settings are metadata only: the Vault token is read from the configured `token_env_var` at runtime, the exact normalized Vault base URL must be explicitly allowlisted, and `deny` or `approval_required` network policy decisions block Vault egress before token lookup or HTTP transport.

Managed files can also publish `managed_network_domain_policy_rules`. These records are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, sort ahead of local/environment `network_domain_policy.rules`, and support stable `id`, `domain`, `mode`, optional non-secret `reason`, `enabled`, and `priority` fields. Managed rules are fail-closed for malformed records, unknown fields, duplicate ids/domains, invalid domains or modes, and secret-shaped text. Network decisions expose safe `matched_rule_id` and `matched_rule_source` metadata, while generated-tool subprocess handoff receives only domains, modes, and approved endpoints.

Managed files can publish deployment-owned inert plugin component records with `managed_plugin_component_records`. Each record pins a plugin id, component type, relative component path, manifest digest, component digest, component size, and optional `installed` or `disabled` status. Managed component records are honored only from `DGENTIC_MANAGED_SETTINGS_FILE`, appear from `GET /plugins/{plugin_id}/components` with `source: "managed"`, shadow matching local `plugin-components.json` rows, reject local component install/disable mutation for that plugin, never write managed rows to `plugin-components.json`, and report `stale` when the manifest digest changes or `drifted` when the referenced component bytes no longer match.

Rotate persisted local vault ciphertext after changing the operator-managed Fernet key:

```powershell
$oldKey = "<old-fernet-key>"
$newKey = "<new-fernet-key>"

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/credentials/references/local-vault/rotate-key `
  -Headers @{ Authorization = "Bearer credential-token" } `
  -ContentType "application/json" `
  -Body (@{ current_vault_key = $oldKey; new_vault_key = $newKey } | ConvertTo-Json -Compress)
```

The rotation response returns only `rotated_count`, `skipped_count`, and `rotated_at`. Rotation skips environment and external-process references, fails without partial state changes when any local vault record cannot decrypt with the supplied current key, and does not return keys, plaintext, or ciphertext.

Deactivate an operator to fail closed for linked persisted tokens:

```powershell
Invoke-RestMethod `
  -Method Patch `
  -Uri http://127.0.0.1:8000/auth/operators/operator-alpha `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"status":"inactive"}'
```

## Configure Database Persistence

By default, SQLAlchemy-backed metadata and tool registry services use SQLite at:

```text
DGENTIC_ROOT_DIR/DGENTIC_DATA_DIR/dgentic.db
```

Override the database URL when needed:

```powershell
$env:DGENTIC_DATABASE_URL = "sqlite:///C:/workspace/dgentic-state/dgentic.db"
```

On first use, DGentic initializes the current SQLAlchemy metadata tables and records ordered migrations in `schema_migrations`, including `0001_metadata_tool_registry_baseline` and `0002_memory_lifecycle_metadata`. Production PostgreSQL remains the planned database target, but driver packaging, JSON-store migration, scheduled backup automation, and concurrency hardening remain follow-up work.

## Backup And Restore Local SQLite State

For local/operator smoke workflows using the default file-backed SQLite database, create a backup with:

```powershell
uv run python -c "from dgentic.database import backup_sqlite_database; backup_sqlite_database('backups/dgentic.db')"
```

Restore from a backup with:

```powershell
uv run python -c "from dgentic.database import restore_sqlite_database; restore_sqlite_database('backups/dgentic.db')"
```

These helpers are intended for file-backed SQLite state. PostgreSQL-native backup, retention, and scheduled remote backup automation remain production follow-up work.

## Run The Backend

```powershell
uv run uvicorn dgentic.main:app --reload --app-dir src
```

After installing the package, you can also run:

```powershell
dgentic-server --host 127.0.0.1 --port 8000
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ui/`
- `http://127.0.0.1:8000/docs`

The `/ui/` dashboard is served by the same FastAPI process. In local development it can call the API without a token unless auth is explicitly enabled. In staging or production, open the dashboard, enter a bearer token with the needed capabilities, and use the UI surfaces for task planning, active root context visibility, project root preflight, registration, and guarded Open controls, active-root workspace file browsing/editing, orchestration summary/detail with task graph, expandable per-task sub-agent briefs, task update/recovery/blocker resolution/closeout controls, and execution controls, approval source/status filtering and review/decisions, approved CLI execution, CLI run output inspection, structured Git checkpoint review, provider/tool summaries, read-only CLI policy, command recipe, hook policy, and plugin trust visibility, effective settings, and logs. Project Open switches the active runtime `DGENTIC_ROOT_DIR` inside the current FastAPI process only after blocking active CLI/orchestration work and unexecuted approvals; relative `DGENTIC_DATA_DIR` is pinned to its current absolute location during the switch. Agent brief detail uses the existing `/agents` capability; without it, orchestration tasks still render and the agent detail area fails softly. Blocker resolution remains admin-gated by the backend.

## Create A Task Plan

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tasks/plan `
  -ContentType "application/json" `
  -Body '{"objective":"Create a guarded plan for indexing project memory.","constraints":["Only operate inside rootDir."],"acceptance_criteria":["Plan includes validation step."]}'
```

Task plans and execution runs are persisted in local JSON state:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/tasks/plans
Invoke-RestMethod -Uri http://127.0.0.1:8000/tasks/runs
```

By default, local state files are written under `.dgentic/`, which is ignored by Git.

## Use Guarded Text File Operations

Write a UTF-8 text file inside `DGENTIC_ROOT_DIR`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/write `
  -ContentType "application/json" `
  -Body '{"path":"notes/sprint.txt","content":"Sprint note."}'
```

Read and write binary payloads as base64, inspect metadata, or list a directory:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/write-binary `
  -ContentType "application/json" `
  -Body '{"path":"artifacts/blob.bin","content_base64":"AAEC/w=="}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/metadata `
  -ContentType "application/json" `
  -Body '{"path":"artifacts/blob.bin"}'
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/list `
  -ContentType "application/json" `
  -Body '{"path":"artifacts"}'
```

Destructive filesystem operations are approval-gated at the backend contract level. In `development` and `test`, local smoke checks may still use `approved: true`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/copy `
  -ContentType "application/json" `
  -Body '{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","approved":true}'
```

In `staging` and `production`, approval-required filesystem operations need a single-use bound `approval_id`. Approval records are persisted in `filesystem-approvals.json` and bind the action, path/target digests, write payload digest when present, source/target state digests, options, requester, agent/task context, orchestration decision, and hook-policy decision:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/approvals `
  -Headers @{ Authorization = "Bearer filesystem-token" } `
  -ContentType "application/json" `
  -Body '{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","action":"copy","requested_by":"operator"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/filesystem/approvals/$($approval.id)/approve" `
  -Headers @{ Authorization = "Bearer approval-token" } `
  -ContentType "application/json" `
  -Body '{"reason":"Reviewed copy target."}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/copy `
  -Headers @{ Authorization = "Bearer filesystem-token" } `
  -ContentType "application/json" `
  -Body ('{"path":"artifacts/blob.bin","target_path":"artifacts/blob-copy.bin","approval_id":"' + $approval.id + '"}')
```

## Use Guarded CLI Execution

Safe commands can run inside `DGENTIC_ROOT_DIR`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"cmd /c echo hello","timeout_seconds":5}'
```

Command policy blocks explicit executable paths that resolve outside `DGENTIC_ROOT_DIR`, including direct commands such as `../outside-tool`, absolute host paths, shell-wrapped commands, and PowerShell launcher payloads. Configured-safe rules for common project tools also cannot downgrade path/directory flags such as `git -C`, `npm --prefix`, `pnpm --dir`/`-C`, `yarn --cwd`, and `uv --directory`/`--project` when they point outside `DGENTIC_ROOT_DIR`. Nested shell payloads must keep startup hardening visible in the reviewed command: nested `cmd` needs `/d`, and nested PowerShell/pwsh needs `-NoProfile -NonInteractive`. Bare command names still flow through the configured command policy, but launch preflight rejects bare executables that would resolve from the workspace current directory, from a `cmd /c` inner command, or from any `PATH` entry under `DGENTIC_ROOT_DIR`. If you intentionally need a workspace-local tool, use an explicit reviewed path so approval and audit records show the executable location.

At launch time, DGentic also hardens top-level Windows shell wrappers without changing the reviewed command string or approval digest. `cmd` and `cmd.exe` are executed with `/d` so Command Processor AutoRun hooks do not run first, and `powershell`, `powershell.exe`, `pwsh`, and `pwsh.exe` are executed with `-NoProfile -NonInteractive` unless equivalent switches are already present. Commands that need profile aliases, profile-set environment, AutoRun behavior, or interactive prompts should make that setup explicit in the reviewed command instead.

Command requests can include agent/task context and explicit environment overrides. DGentic builds a controlled process environment, blocks sensitive runtime overrides such as `PATH`, `PYTHONPATH`, `SYSTEMROOT`, and `COMSPEC`, and also rejects shell startup hooks, dynamic-loader preloads/library paths, and interpreter injection variables such as `BASH_ENV`, `ENV`, `LD_PRELOAD`, `DYLD_*`, `NODE_OPTIONS`, `RUBYOPT`, and `PERL5LIB`. Command run history stores only the applied environment variable names:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"cmd /c echo context","requested_by":"pm","agent_id":"agent-dev-1","agent_role":"developer","task_id":"story-5.3","environment":{"DGENTIC_TEST_FLAG":"enabled"}}'
```

In `development` and `test`, approval-required commands can still use the explicit `approved: true` bypass for local smoke checks:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/execute `
  -ContentType "application/json" `
  -Body '{"command":"git status","approved":true,"timeout_seconds":5}'
```

In `staging` and `production`, approval-required commands need a single-use approved `approval_id`. Approval records are bound to command, cwd, timeout, requester, agent/task context, environment keys, policy decision metadata, and expiry. When auth is enabled, queueing an approval and executing approved CLI work require `cli`, while listing/reviewing/approving/denying CLI approvals requires `approvals`:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"command":"python --version","timeout_seconds":10,"requested_by":"operator"}'

Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($approval.id)/review"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($approval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer","reason":"Version check is acceptable."}'

$executeBody = @{
  command = "python --version"
  timeout_seconds = 10
  approval_id = $approval.id
  requested_by = "operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/execute" `
  -ContentType "application/json" `
  -Body $executeBody
```

Approvals can also be listed through `GET /cli/approvals`, reviewed through `GET /cli/approvals/{approval_id}/review`, and executed through `POST /cli/approvals/{approval_id}/execute` when no environment override is required. Review responses expose redacted command text, environment key names, policy context, HMAC digest identifiers, warnings, and direct-execute availability without persisting environment values. Approval requests may include environment overrides for review, but only the environment variable names are persisted; the execution request must include the same environment keys when using `approval_id` directly.

For git workflow automation, start with a read-only checkpoint. Direct local commits use `POST /cli/git/commit-runs`; the request re-runs the checkpoint, requires the supplied digest to match the fresh ready checkpoint, validates a single-line non-secret commit message, runs `git commit -m ...` by argv, isolates repository hooks with an empty temporary hooks path, disables GPG signing, and returns head-before/head-after plus digest metadata without creating a CLI approval or echoing raw stdout/stderr:

```powershell
$checkpoint = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/checkpoints `
  -ContentType "application/json" `
  -Body '{"action":"commit","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'

$commitRunBody = @{
  checkpoint_digest = $checkpoint.checkpoint_digest
  commit_message = "Add safe local milestone"
  test_evidence = @("python -m pytest -q")
  requested_by = "operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/commit-runs `
  -ContentType "application/json" `
  -Body $commitRunBody
```

Use `POST /cli/git/commit-approvals` when the commit should remain a pending CLI approval. A direct push run is available through `POST /cli/git/push-runs` after a fresh ready push checkpoint. It derives the configured upstream remote and branch from repository config, runs shell-free `git push --porcelain [remote] HEAD:refs/heads/[upstream-branch]`, disables repository hooks and push GPG signing, rejects caller-supplied remote/refspec/flag fields, and returns ahead/behind plus remote URL digest metadata without raw remote URLs or command output:

```powershell
$pushCheckpoint = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/checkpoints `
  -ContentType "application/json" `
  -Body '{"action":"push","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'

$pushRunBody = @{
  checkpoint_digest = $pushCheckpoint.checkpoint_digest
  test_evidence = @("python -m pytest -q")
  requested_by = "operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/push-runs `
  -ContentType "application/json" `
  -Body $pushRunBody
```

Push approvals remain available through `POST /cli/git/push-approvals` when the push should stay in the normal approval queue. PR approvals remain available through `POST /cli/git/pr-approvals`; PR approval creation does not run `gh` or create network PRs. A direct PR run is available through `POST /cli/git/pr-runs` after a fresh ready PR checkpoint on a branch that is already pushed and current with upstream. It requires an explicit `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, or `GHE_TOKEN`, runs shell-free `gh pr create` with checkpoint-derived `--head`, isolates `gh` config through a temporary `GH_CONFIG_DIR`, rejects caller-supplied remote/head/flag/template/reviewer fields, and returns safe digest metadata plus a strict sanitized PR URL when `gh` emits one:

```powershell
$prCheckpoint = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/checkpoints `
  -ContentType "application/json" `
  -Body '{"action":"pr","test_evidence":["python -m pytest -q"],"requested_by":"operator"}'

$prRunBody = @{
  checkpoint_digest = $prCheckpoint.checkpoint_digest
  title = "Open guarded PR"
  body = "Validation passed."
  base_branch = "main"
  draft = $true
  test_evidence = @("python -m pytest -q")
  requested_by = "operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/git/pr-runs `
  -ContentType "application/json" `
  -Body $prRunBody
```

`GET /logs` responses redact common secret assignments, secret-like flags, shell-substitution values, and structured sensitive metadata keys such as token, password, secret, credential, and API key fields.

If a local JSON state file is malformed or contains records that no longer validate, DGentic quarantines the original file beside the active collection with a `*.corrupt-*.json` name and repairs the active file to `[]`. Collection owners can inspect quarantined files and restore a valid quarantined file with the storage helper methods `list_quarantined_files()` and `restore_quarantine()`.

Long-running commands can be started asynchronously, polled for status and output chunks, and cancelled. Policy checks and `rootDir` working-directory checks still run before the process starts:

```powershell
$runApproval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"command":"python -c \"import time; time.sleep(30)\"","timeout_seconds":60,"requested_by":"operator"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/approvals/$($runApproval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer"}'

$runBody = @{
  command = "python -c `"import time; time.sleep(30)`""
  timeout_seconds = 60
  approval_id = $runApproval.id
  requested_by = "operator"
} | ConvertTo-Json

$run = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/runs `
  -ContentType "application/json" `
  -Body $runBody

Invoke-RestMethod -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)"

Invoke-RestMethod -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)/output?after_sequence=0"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/cli/runs/$($run.id)/cancel"
```

Output chunks include sequence numbers and redacted stdout/stderr text. Persisted runs that are still marked `running` without a process in the current backend process are reconciled to `stale` on runtime service initialization.

Configure persisted command policy rules when the built-in defaults are too broad or too narrow. Rules are evaluated by ascending priority and can match by executable, exact command, command substring, or argument substring. Rules can also be scoped to agent roles:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/cli/policy/rules `
  -ContentType "application/json" `
  -Body '{"name":"Developers may inspect git","match_type":"executable","pattern":"git","permission_mode":"autopilot_safe","reason":"Developer git inspection is allowed.","agent_roles":["developer"],"priority":5}'
```

Check that the role-scoped rule applies:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/guardrails/commands `
  -ContentType "application/json" `
  -Body '{"command":"git status","agent_role":"developer","agent_id":"agent-dev-1","task_id":"story-5.3"}'
```

List or disable configured policy rules:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/cli/policy/rules

Invoke-RestMethod `
  -Method Patch `
  -Uri http://127.0.0.1:8000/cli/policy/rules/[rule_id] `
  -ContentType "application/json" `
  -Body '{"enabled":false}'
```

Configure backend hook policy rules when you need an audited pre-action layer across command, filesystem, or network guardrail decisions. Hook rules are persisted in `hook-policy-rules.json`, evaluated by priority, can match `any`, `exact`, `contains`, or `prefix`, and support `audit`, `approval_required`, or `blocked` effects. Command, filesystem, and network approval-required hook decisions are bound into approval digests and rechecked before execution or approval claim. Filesystem hook `blocked` decisions enforce immediately.

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/guardrails/hooks/rules `
  -ContentType "application/json" `
  -Body '{"name":"Block private network path","surface":"network","action":"request","match_type":"contains","pattern":"https://api.example.test/private","effect":"blocked","reason":"Private endpoint requires a managed workflow.","priority":5}'
```

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/guardrails/hooks/rules
```

## Check Local Providers

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/providers/ollama/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/providers/lm-studio/health
```

Run a local provider generation request:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/providers/generate `
  -ContentType "application/json" `
  -Body '{"provider_id":"ollama","model":"llama3.1","messages":[{"role":"user","content":"Say hello."}]}'
```

Provider generation and health probes only use exact allowlisted base URLs. The default allowlist is the configured Ollama and LM Studio base URLs, plus any trusted URLs in `DGENTIC_PROVIDER_ALLOWED_BASE_URLS`. Provider redirects are blocked, malformed upstream JSON or provider-specific success payloads are returned to API callers as generic provider failures, and provider logs store safe metadata rather than raw completion content. Generation retries only bounded transient failures such as `429` and upstream `5xx`; repeated retry-exhausted generation failures open an in-process per-provider circuit breaker that returns a fast `503` until its cooldown expires. Tune this with `DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD` and `DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS`. Health probes do not retry.

Optionally layer a domain policy on top of exact provider base URL allowlists and generated-tool Python socket egress. `allow` and `audit` permit matching outbound provider requests and common generated-tool socket attempts, `deny` fails closed before provider transport or during tool execution, and `approval_required` requires a single-use bound `network_approval_id` before provider generation or streaming can reach transport. Generated tools can also consume one bound network approval per execution when the approval uses surface `generated_tool`, action `socket_connect`, and an explicit host plus port URL such as `https://api.review.example.test:443`.

```powershell
$env:DGENTIC_NETWORK_DOMAIN_POLICY = '{"default_mode":"deny","rules":[{"domain":"provider.example.test","mode":"allow"},{"domain":"*.review.example.test","mode":"approval_required","reason":"Network review required."}]}'
```

Check a URL against the configured policy:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/guardrails/network `
  -ContentType "application/json" `
  -Body '{"url":"https://provider.example.test/v1/chat/completions"}'
```

Create, review, approve, and use a bound network approval for an approval-required provider base URL:

```powershell
$networkApproval = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/network/approvals `
  -ContentType "application/json" `
  -Body '{"url":"https://provider.example.test/v1","surface":"provider","action":"generate","requested_by":"operator"}'

Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/network/approvals/$($networkApproval.id)/review"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/network/approvals/$($networkApproval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer","reason":"Approved for this provider endpoint."}'
```

To enable the OpenAI-compatible external adapter, set an API-versioned HTTPS base URL, a comma-separated model allowlist, and either the name of an environment variable that already contains the API key or a persisted credential reference id. The API key value itself is not stored in DGentic settings:

```powershell
$env:OPENAI_API_KEY = "<set outside DGentic config>"
$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV = "OPENAI_API_KEY"
$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS = "gpt-4.1-mini,gpt-4.1"
```

For a persisted external credential reference, first create the reference with an authenticated principal that has the `credentials` capability, then set `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF` to the returned id. Environment-backed references store only an environment variable name; the raw secret value remains outside DGentic and is read only when a provider request reaches the transport step:

```powershell
$credential = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/credentials/references `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"env_var":"OPENAI_API_KEY","label":"OpenAI-compatible provider"}'

$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF = $credential.id
```

For a local encrypted credential reference, provide a Fernet key through `DGENTIC_CREDENTIAL_VAULT_KEY`. DGentic does not generate, rotate, escrow, or recover this key; store it outside DGentic state. The create request is the only API call that accepts `secret_value`; persisted state stores ciphertext, and API views plus credential audit events omit both plaintext and ciphertext. Missing, malformed, or wrong keys fail closed before provider transport and before provider approval claims:

```powershell
$env:DGENTIC_CREDENTIAL_VAULT_KEY = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$credential = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/credentials/references `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"source_type":"local_vault","secret_value":"<provider-api-key>","label":"OpenAI-compatible provider"}'
$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF = $credential.id
```

For an external secret-manager CLI or mounted sidecar helper, configure a shell-free process adapter. `argv[0]` must be an absolute executable path, DGentic appends the credential reference `secret_name` as the final argument, closes stdin, uses a minimal inherited environment, enforces timeout/output limits, and treats any stderr, non-zero exit, empty output, multi-line output, or oversized output as a credential failure. The returned secret is used only to build the outbound Authorization header after pricing, configuration, circuit, and approval gates pass:

```powershell
$env:DGENTIC_CREDENTIAL_PROCESS_ADAPTERS = '{"process-vault":{"argv":["C:\\tools\\secret-fetch.exe","--name"]}}'
$credential = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/credentials/references `
  -Headers @{ Authorization = "Bearer admin-token" } `
  -ContentType "application/json" `
  -Body '{"source_type":"external_process","adapter_id":"process-vault","secret_name":"providers/openai","label":"OpenAI-compatible provider"}'
$env:DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF = $credential.id
```

For deployment-owned references, publish read-only `managed_credential_references` from `DGENTIC_MANAGED_SETTINGS_FILE`. Managed credential records support `env` and `external_process` sources only, are returned by `GET /credentials/references` with `source: "managed"`, can be used by `DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF`, never write to `credential-references.json`, and cannot be revoked or shadowed by local records:

```json
{
  "settings": {
    "managed_credential_references": [
      {
        "id": "managed.provider-key",
        "source_type": "env",
        "env_var": "OPENAI_API_KEY",
        "label": "Managed OpenAI-compatible provider",
        "purpose": "provider",
        "status": "active"
      }
    ]
  }
}
```

For HashiCorp Vault KV v2 over HTTP, configure a first-class secret-manager adapter instead of a helper process:

```powershell
$env:DGENTIC_CREDENTIAL_SECRET_MANAGER_ALLOWED_BASE_URLS = "https://vault.example.test/v1"
$env:DGENTIC_CREDENTIAL_SECRET_MANAGER_ADAPTERS = '{"vault-main":{"type":"hashicorp_vault_kv2","base_url":"https://vault.example.test/v1","mount":"secret","field":"api_key","token_env_var":"DGENTIC_VAULT_TOKEN"}}'
$env:DGENTIC_VAULT_TOKEN = "<vault-token>"
```

Then create or publish a credential reference with `source_type: "secret_manager"`, `adapter_id: "vault-main"`, and a safe Vault `secret_name` such as `providers/openai`. DGentic calls `/v1/secret/data/providers/openai`, sends `X-Vault-Token` from the configured environment variable only after provider approval/configuration gates pass, disables redirects and proxies, and rejects missing/malformed KV v2 responses, multiline secrets, oversized responses, and non-allowlisted or policy-denied Vault hosts.

Optionally configure advisory provider/model pricing. Entries are exact provider/model matches; token rates are USD per 1,000 prompt/completion tokens, and `request_estimate_usd` is the routing-time estimate used before provider usage is known:

```powershell
$env:DGENTIC_PROVIDER_PRICING_CATALOG = '{"external-openai-compatible":{"gpt-4.1-mini":{"prompt_usd_per_1k_tokens":0.0004,"completion_usd_per_1k_tokens":0.0016,"request_estimate_usd":0.01}}}'
```

Pricing estimates are not billing records. DGentic does not contact provider billing APIs, and malformed pricing catalogs fail closed before outbound provider transport.

Optionally configure role-specific provider/model routes. Role routes are exact preferences and still must pass the normal enabled-provider, privacy, capability, max-cost, and model-availability gates; if a configured role route is blocked, routing fails instead of silently falling back:

```powershell
$env:DGENTIC_PROVIDER_ROLE_ROUTING = '{"planner":{"provider_id":"lm-studio","model":"local-model"},"reviewer":{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini"}}'
```

Invalid role-routing JSON or unsupported provider ids fail closed before provider health probes.

Direct external generation is approval-required. In development/test mode, local smoke checks may include `"approved": true`; staging/production requests need a single-use bound provider `approval_id`. If the network domain policy for the configured provider base URL is `approval_required`, the same generation request also needs a bound `network_approval_id`. External API-key lookup and Authorization header construction are deferred until pricing, configuration, circuit-breaker, provider approval, and network approval gates allow outbound transport.

Create, review, approve, and execute a bound external provider request:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/providers/external-openai-compatible/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}]}'

Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/providers/approvals/$($approval.id)/review"

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/providers/approvals/$($approval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer","reason":"Approved for this request."}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/providers/generate" `
  -ContentType "application/json" `
  -Body ('{"provider_id":"external-openai-compatible","model":"gpt-4.1-mini","messages":[{"role":"user","content":"Say hello."}],"approval_id":"' + $approval.id + '","network_approval_id":"' + $networkApproval.id + '","requested_by":"operator"}')
```

Provider approval records bind provider id, model, stream mode, messages, generation options, timeout, configured base URL, credential reference identity, model allowlist, requester, and agent/task context through HMAC digests. Network approval records bind sanitized URL metadata, full URL digest, policy decision digest, surface/action, requester, and agent/task context, and are single-use when claimed for provider transport. Review responses expose safe metadata without raw prompt content, URL query secrets, or credential values. When auth is enabled, provider and network approval create/list/review/approve/deny routes require the `approvals` capability; generation requires the `providers` capability. Approved records are claimed only after external request/config/circuit/credential gates pass and immediately before outbound provider transport, so actual transport failures consume the approval while earlier fail-fast paths preserve it.

OpenAI-compatible streaming is available through `POST /providers/generate/stream` for LM Studio and the configured external adapter. The endpoint reads upstream `data:` server-sent event chunks and returns newline-delimited JSON (`application/x-ndjson`) events; non-streaming `/providers/generate` continues to reject `stream: true`.

## Discover And Trust Local Plugin Manifests

DGentic discovers plugin manifests without loading or executing plugin code. Place a manifest at `DGENTIC_ROOT_DIR/plugins/[plugin_id]/dgentic-plugin.json`:

```powershell
New-Item -ItemType Directory -Force plugins\example-plugin | Out-Null
@'
{
  "plugin_id": "example-plugin",
  "name": "Example plugin",
  "version": "1.0.0",
  "description": "Reusable local package metadata.",
  "components": {
    "command_recipes": ["status-check"],
    "agent_blueprints": ["reviewer"],
    "tools": ["scanner"]
  },
  "agent_blueprints": [{"path": "agents/reviewer.json", "name": "Reviewer"}],
  "skills": [{"path": "skills/triage.json", "name": "Triage"}],
  "tools": [{"path": "tools/scanner.json", "name": "Scanner"}],
  "docs": [{"path": "docs/runbook.md", "name": "Runbook"}]
}
'@ | Set-Content -Encoding utf8 plugins\example-plugin\dgentic-plugin.json
New-Item -ItemType Directory -Force plugins\example-plugin\agents,plugins\example-plugin\skills,plugins\example-plugin\tools,plugins\example-plugin\docs | Out-Null
'{"name":"Reviewer"}' | Set-Content -Encoding utf8 plugins\example-plugin\agents\reviewer.json
'{"name":"Triage"}' | Set-Content -Encoding utf8 plugins\example-plugin\skills\triage.json
'{"name":"Scanner"}' | Set-Content -Encoding utf8 plugins\example-plugin\tools\scanner.json
'{"name":"Runbook"}' | Set-Content -Encoding utf8 plugins\example-plugin\docs\runbook.md
```

List manifests, inspect one plugin, and record an explicit trust decision:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/plugins

Invoke-RestMethod -Uri http://127.0.0.1:8000/plugins/example-plugin

Invoke-RestMethod `
  -Method Patch `
  -Uri http://127.0.0.1:8000/plugins/example-plugin/trust `
  -ContentType "application/json" `
  -Body '{"status":"trusted","reason":"Reviewed manifest metadata only."}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/plugins/example-plugin/components/preview

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/plugins/example-plugin/components/install

Invoke-RestMethod -Uri http://127.0.0.1:8000/plugins/example-plugin/components

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/plugins/example-plugin/components/disable
```

Discovery reads only the exact manifest bytes, computes a SHA-256 digest, returns redacted safe metadata, and stores trust records in `plugin-trust.json`. Trust becomes `stale` when the manifest bytes change. Trusted current manifests can preview inert agent blueprint, skill, tool, and docs component references with root-bound bounded reads, component SHA-256 digests, and component sizes; install persists only the same inert metadata in `plugin-components.json`, and disable marks those records inactive. These routes do not parse, import, index, load, or execute referenced content. Symlinked plugin directories, symlinked manifests, out-of-root manifests, manifests over 64 KiB, malformed JSON, or manifests whose `plugin_id` does not match the containing directory are rejected with safe errors. In staging or production, these routes require a bearer token with the `tools` capability.

## Generate A Local Tool

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tools/generate `
  -ContentType "application/json" `
  -Body '{"name":"pdf-generator","description":"Generate a PDF from structured input.","trigger_source":"main_agent","permission_mode":"approval_required","tags":["pdf","document"]}'
```

This creates:

- `localmcp/pdf-generator/tool.py`
- `localmcp/pdf-generator/wrapper.py`
- `localmcp/pdf-generator/manifest.json`
- `localmcp/pdf-generator/README.md`

Generated tools are registered in local JSON state, auto-registered in the SQLAlchemy-backed tool registry with an interface signature, and indexed as memory artifacts. A duplicate SQL registry row or duplicate interface signature blocks generation before files are written.

Create, approve, and execute an approval-required generated tool in production-style mode:

```powershell
$approval = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/tools/pdf-generator/approvals?requested_by=operator" `
  -ContentType "application/json" `
  -Body '{"payload":{"title":"Example"},"timeout_seconds":30}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/tools/approvals/$($approval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer","reason":"Safe local generated tool run."}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tools/pdf-generator/execute `
  -ContentType "application/json" `
  -Body ('{"payload":{"title":"Example"},"approval_id":"' + $approval.id + '","timeout_seconds":30,"requested_by":"operator"}')
```

In `development` and `test`, approval-required tools can still use `approved: true` for local smoke checks. In `staging` and `production`, approval-required tools need a single-use approved `approval_id` bound to the tool name, version, status, generated artifact tree, payload digest, timeout, requester, agent/task context, and expiry. When auth is enabled, creating/executing tools uses the `tools` capability while approving or denying tool approvals uses the separate `approvals` capability. Tool execution also consults the SQL registry when a row exists. Deprecated registry rows, invalid permission levels, or permission conflicts between the SQL registry and local JSON manifest fail closed before the subprocess starts. Completed executions sync SQL registry usage counters, warn on low reliability after enough evidence, disable repeatedly weak tools, and deprecate very low-reliability tools. The subprocess launches with isolated Python import semantics, stripped host Python/virtualenv/library path environment variables, and only the generated tool directory plus validated tool-local dependency directories on the import path. If `DGENTIC_NETWORK_DOMAIN_POLICY` is configured, the runner validates it before launch, passes only sanitized domain/mode rules plus any claimed generated-tool network approval host and port to the child process, installs common Python socket guards before generated-tool imports run, treats `deny` socket attempts as failed tool executions, and permits an `approval_required` socket target only when the execution supplied a matching single-use `network_approval_id`. Generated-tool network approval consumption is a Python runtime socket guardrail, not OS-level or non-Python egress isolation. Tool execution starts with process-group isolation where supported and uses process-tree cleanup on timeout. Tool stdout, stderr, parsed JSON output, and execution audit metadata are redacted for common secret-shaped values.

Create a generated-tool socket approval with the generic network approval API, then pass the approved id on execution:

```powershell
$toolNetworkApproval = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/network/approvals `
  -ContentType "application/json" `
  -Body '{"url":"https://api.review.example.test:443","surface":"generated_tool","action":"socket_connect","requested_by":"operator"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/network/approvals/$($toolNetworkApproval.id)/approve" `
  -ContentType "application/json" `
  -Body '{"decided_by":"reviewer","reason":"Allow this generated tool socket target once."}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/tools/networked-tool/execute `
  -ContentType "application/json" `
  -Body ('{"payload":{},"network_approval_id":"' + $toolNetworkApproval.id + '","timeout_seconds":30,"requested_by":"operator"}')
```

Regenerating an existing tool name is treated as a deliberate version migration. Use `overwrite: true` and a strictly newer `version`; same or older versions, or newer versions without explicit overwrite, are rejected before files are rewritten. Accepted migrations update the local manifest and the existing SQL registry row in place, reset SQL usage/reliability counters, and clear SQL deprecation for the new generated artifact version.

Read it back:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/filesystem/read `
  -ContentType "application/json" `
  -Body '{"path":"notes/sprint.txt"}'
```

## Use Metadata And Tool Registry Services

Create and query a SQLAlchemy-backed metadata index record:

```powershell
$metadata = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/metadata `
  -ContentType "application/json" `
  -Body '{"entity_type":"memory","entity_id":"memory-1","tags":["sprint","metadata"],"category":"planning","description":"Sprint metadata record.","relevance_score":0.8}'

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/memory/metadata/$($metadata.id)"
```

Run dependency-light hybrid retrieval over metadata text. The default embedding model is deterministic and does not require `sentence-transformers`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/retrieve/hybrid `
  -ContentType "application/json" `
  -Body '{"query":"sprint metadata retrieval","tags":["sprint"],"similarity_threshold":0.1}'
```

Preview and apply the SQL-backed memory lifecycle policy. Preview is read-only; apply can promote, archive, or soft-prune matching metadata. Compression candidates are executed through the separate compression endpoints:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/lifecycle/preview `
  -ContentType "application/json" `
  -Body '{"category":"planning","reference_time":"2027-01-01T00:00:00+00:00"}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/lifecycle/apply `
  -ContentType "application/json" `
  -Body '{"category":"planning","reference_time":"2027-01-01T00:00:00+00:00"}'
```

Hybrid, vector, and metadata retrieval exclude archived and soft-pruned metadata by default. Add `"include_inactive": true` to hybrid retrieval requests, or `include_inactive=true` to vector/metadata retrieval query strings, when reviewing archived memory.

Retrieval results include additive attribution fields: `source_type`, `source_id`, `matched_fields`, and `score_reasons`. These explain whether a result came from a stored vector, metadata-text fallback, or metadata filter and which deterministic score components were used.

Preview and apply deterministic metadata-description compression for records that meet age/access thresholds:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/compression/preview `
  -ContentType "application/json" `
  -Body '{"category":"planning","compress_after_days":30,"compress_access_count_threshold":10,"max_summary_chars":240}'

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/memory/compression/apply `
  -ContentType "application/json" `
  -Body '{"category":"planning","compress_after_days":30,"compress_access_count_threshold":10,"max_summary_chars":240}'
```

Register a tool in the SQLAlchemy-backed registry and record usage:

```powershell
$tool = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/tools/registry `
  -ContentType "application/json" `
  -Body '{"tool_name":"example-tool","version":"1.0.0","source_path":"localmcp/example-tool","interface_signature":"sha256:example","permission_level":"approval_required","tags":["example"]}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/tools/registry/$($tool.id)/usage" `
  -ContentType "application/json" `
  -Body '{"status":"success","execution_time_ms":25}'
```

Semantic and hybrid retrieval work with the default deterministic hash embedding. Configure an optional sentence-transformers model only when stronger production embeddings are required and the dependency is installed.

## Run Tests

```powershell
uv run pytest
```

## Run Lint And Format Checks

```powershell
uv run ruff check .
uv run ruff format --check .
```

To format files:

```powershell
uv run ruff format .
```

## Current Limitations

- The planner is deterministic and does not call local or external models yet.
- Production/staging auth supports route capability gates, startup fail-closed validation, persisted operator profiles with direct and group-inherited effective capabilities, persisted operator groups, persisted generated token create/list/rotate/revoke/expire APIs with hashed storage, authenticated audit actors across the main API-triggered execution/mutation surfaces, persisted external credential references, managed credential reference records, encrypted local credential-vault references with supplied-key rotation, shell-free external-process credential resolver adapters, first-class HashiCorp Vault KV v2 credential adapters, provider-call network/domain guardrails with bound approval records, guarded web retrieval fetch runtime, bound filesystem approval records, generated-tool Python socket network policy guardrails with bound network approval consumption, plugin manifest trust controls, inert plugin reference component records, active-task verification for caller-supplied orchestration agent context across CLI, generated-tool, provider, and network approval surfaces, method-aware CLI/filesystem approval reviewer capability separation, and secret-shaped metadata redaction for operator/group/token/credential/plugin trust labels, but richer production identity workflows beyond operator groups, managed KMS integration, and OS-level egress isolation remain follow-up work.
- Filesystem runtime supports guarded text and binary read/write, directory listing, metadata, approval-gated delete/move/copy/rename, and single-use bound approval records inside `DGENTIC_ROOT_DIR`, but interactive filesystem approval UI, persisted configurable filesystem policy rules, deeper platform-specific locked-file handling, and OS-level filesystem isolation remain follow-up work.
- CLI execution is policy-enforced and root-bound with configurable and agent-role scoped policy rules, explicit executable path boundary checks, configured-safe command path-argument checks, nested shell startup-hardening checks, bare executable workspace/PATH trust checks, single-use bound approval IDs, reviewer operations behind the separate `approvals` capability, top-level `cmd` AutoRun and PowerShell profile/prompt suppression, direct checkpoint-bound local git commit, configured-upstream push, and GitHub PR creation execution with safe audit metadata, failed launch run records for claimed synchronous approvals, asynchronous status/output polling, stale-running reconciliation, process-local cancellation, conservative post-restart orphan termination for matching prior-supervisor processes, controlled environment overrides with startup/preload injection blocking, and context audit metadata, but richer approval filtering/non-CLI execution UX, full process adoption/resumable output after restart, and production multi-worker lease supervision remain follow-up work.
- Ollama and LM Studio can be probed and called for chat generation through exact allowlisted endpoints with redirect blocking, bounded request/payload validation, bounded retry/backoff, in-process per-provider circuit breakers for retry-exhausted generation failures, normalized usage/cost metadata, safe telemetry, NDJSON streaming, and optional role-to-provider/model routing preferences. The OpenAI-compatible external adapter can call and stream a configured model allowlist using an HTTPS-only local or managed external credential reference, local encrypted vault reference, shell-free external-process credential adapter, HashiCorp Vault KV v2 credential adapter, or env-var fallback and an explicit development/test approval flag or staging/production bound provider approval ID, with optional exact provider/model pricing for advisory usage and routing estimates; it defers API-key/header resolution on fail-fast approval, configuration, pricing, and circuit paths, but durable multi-worker circuit state, provider billing reconciliation, additional secret-manager adapters, and provider-specific external adapters are not implemented yet.
- Local JSON persistence and SQLite-compatible semantic memory prototypes exist with local SQLite backup/restore helpers, additive lifecycle metadata migrations, lifecycle preview/apply APIs, deterministic metadata compression APIs, a SQLite JSON-vector backend abstraction, retrieval attribution/score explanations, and baseline retrieval performance smoke coverage, but no pgvector production backend, scheduled memory lifecycle/compression job, frontend, or VS Code extension exists yet.
- Local tools can be generated, SQL-registered, duplicate-checked, migrated to strictly newer same-name versions with explicit overwrite, and executed under `localmcp/` with registry permission/deprecation checks, bound approval IDs for approval-required tools outside development/test mode, runtime reliability policy automation, redacted outputs/audit metadata, a reduced inherited environment, local-only dependency import isolation, common Python socket network policy guardrails, and process-group timeout cleanup hardening. Local plugin manifests can be discovered, explicitly trusted or blocked, and used to persist inert agent/skill/tool/docs reference metadata without execution, but plugin loading, full OS/filesystem/network sandbox isolation, parallel multi-version SQL registry rows, and production package/dependency lifecycle management are still needed.
