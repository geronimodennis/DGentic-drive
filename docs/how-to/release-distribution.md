# Release Distribution

Date created: 2026-05-07

This guide describes how to build and verify a DGentic release distribution.

## Build Artifacts

From the repository root:

```powershell
uv build
```

This creates:

- `dist/dgentic-0.2.6.tar.gz`
- `dist/dgentic-0.2.6-py3-none-any.whl`

The current release bundle is:

- `releases/dgentic-0.2.6.zip`

## Verify The Wheel

Create a clean virtual environment and install the wheel:

```powershell
python -m venv .release-test
.\.release-test\Scripts\python -m pip install dist\dgentic-0.2.6-py3-none-any.whl
```

Run a smoke test:

```powershell
.\.release-test\Scripts\dgentic-server --host 127.0.0.1 --port 8016
```

Then open:

- `http://127.0.0.1:8016/health`
- `http://127.0.0.1:8016/docs`

## Release Checklist

- Tests pass.
- Lint passes.
- Format check passes.
- Wheel builds.
- Source distribution builds.
- Wheel installs in a clean virtual environment.
- `dgentic-server` starts successfully.
- `/health` returns `status: ok`.
- Release notes are updated.
- Project progress log is updated.

## Current Release

Current release notes: `docs/releases/0.2.6.md`.

The release bundle checksum is recorded in `docs/progress/project-progress-log.md`. Publishing it with a GitHub Release asset requires GitHub CLI or a GitHub token in the execution environment.
