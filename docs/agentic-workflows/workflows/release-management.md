# Release Management Workflow

## Major Milestone Release Process

When a milestone is completed, the Release Manager Agent must complete the following steps.

## 1. Validate Release Readiness

Ensure:

- All sprint stories are completed.
- QA approvals exist.
- Security validation passed.
- Deployment validation passed.
- Documentation updated.
- Version updated.

## 2. Generate Release Artifacts

Create:

- Release notes.
- Changelog.
- Deployment instructions.
- Upgrade guides.
- Migration notes.

## 3. Tag Release

Use semantic versioning:

- Major release: `v2.0.0`
- Minor release: `v2.1.0`
- Patch release: `v2.1.1`

## 4. Coordinate Deployment

Coordinate with DevOps:

- Staging deployment.
- Production deployment.
- Rollback readiness.
- Runtime monitoring.

## 5. Post-Release Validation

Validate:

- Production stability.
- Runtime metrics.
- Error monitoring.
- Deployment success.
