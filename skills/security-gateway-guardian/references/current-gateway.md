# Current Gateway

## Current Core File

- `backend/app/services/security_gateway_service.py`

## Current Responsibilities

- per-user rate limiting
- incident counting
- active penalty tracking
- persisted security subject state loading/updating
- auth scope whitelist validation
- prompt injection assessment
- content policy rewrite and redaction
- audit log append
- trace metadata generation/export

## Current Related Files

- `backend/app/services/security_service.py`
- `backend/app/api/routes/security.py`
- `backend/app/schemas/security.py`
- `backend/tests/test_security.py`

## Current Safety Constraint

The security gateway is part of the local brain trusted zone.

It may use:

- persistence
- runtime cache
- redis
- audit store
- trace exporter

It must not be externalized as a final decision maker.
