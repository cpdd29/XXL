---
name: security-gateway-guardian
description: Use this skill when implementing or modifying WorkBot's local security gateway, including rate limiting, auth scope validation, prompt injection detection, desensitization/redaction, audit tracing, and penalty state handling. This skill is only for the brain's local trusted zone and must not externalize final security decisions.
---

# Security Gateway Guardian

This skill is for developing the WorkBot brain's local security gateway.

Use it when the task touches:

- `backend/app/services/security_gateway_service.py`
- `backend/app/services/security_service.py`
- `backend/app/api/routes/security.py`
- `backend/app/schemas/security.py`
- `backend/tests/test_security.py`

## Scope

This skill covers the five local security layers:

1. Rate limit
2. Auth scope validation
3. Prompt injection detection
4. Redaction / rewrite
5. Audit / trace / penalty persistence

## Hard Rules

- Final allow / block decisions must stay local to the brain.
- Penalty state truth must stay local.
- Audit log truth must stay local.
- Trace context must stay local.
- Do not move security judgment into MCP, external skills, or external agents.
- Every security change must add or update tests.

## Workflow

1. Identify which security layer is changing.
2. Confirm the change belongs in the local trusted zone.
3. Modify implementation in the local security service or route layer.
4. Update tests in `backend/tests/test_security.py`.
5. Run security tests and architecture boundary checks.
6. Verify audit, trace, and penalty paths still exist.

## Required Validation

Run:

```bash
cd /Users/xiaoyuge/Documents/XXL/backend && pytest -q tests/test_security.py tests/test_architecture_boundaries.py
python3 scripts/check_architecture_boundaries.py --root /Users/xiaoyuge/Documents/XXL/backend
```

If the change also touches message ingestion or brain-core routing, also run:

```bash
cd /Users/xiaoyuge/Documents/XXL/backend && pytest -q tests/test_messages.py tests/test_brain_core.py
```

## What Not To Do

- Do not write security truth into `tentacle_adapters`.
- Do not let `execution_gateway` persist security truth.
- Do not bypass audit append.
- Do not bypass `trace_id`.
- Do not suppress rewrite diffs for sensitive content.

## References

- For the current gateway structure and file map, read `references/current-gateway.md`.
