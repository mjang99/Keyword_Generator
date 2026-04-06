# Project Checklist Reference

## Always Verify

- Which InsightChat module owns the new endpoints
- Which job/status store already exists
- Which queue/worker runtime already exists
- Which storage location should hold JSON and CSV results
- Which notification path is standard in the host application

## Do Not Assume Yet

- Final API path names
- Actual DB or object storage choice
- Existing auth/permission model details
- Bedrock model version allowed in production
- Whether scraper and OCR must remain separate workers

## Minimum Validation Set

- Single URL generates 100+ keywords
- All 10 categories are present
- Platform-specific match types are present
- One URL failure does not block others
- Repeated request for same URL uses cache
