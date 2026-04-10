# TASK-014 Crawl4AI Install And Env Verification

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-013

## Goal

Provision a local prototype environment that can import and run Crawl4AI on Windows so the collection spike can proceed with a real browser-backed fetch probe.

## Scope

- Use a dedicated Python 3.12 virtual environment for the prototype if `.venv-dev` remains blocked by Python 3.14 and binary-wheel availability.
- Install and verify `crawl4ai` and `playwright` in the prototype environment.
- Install Chromium for the prototype browser runtime.
- Capture exact install commands, runtime caveats, and failure modes in `docs/CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md`.
- Keep `src/` and `tests/` unchanged in this task.

## Done When

- The prototype environment can import `crawl4ai` and `playwright`.
- Chromium is installed and a minimal Crawl4AI smoke succeeds.
- The install path and blocker/fallback notes are documented.

## Notes

- The current `.venv-dev` environment is blocked by Python 3.14 / wheel availability for Crawl4AI dependencies.
- The fallback prototype environment should use `C:\Users\NHN\.local\bin\python3.12.exe` if needed.
- This task is install and verification only, not a runtime migration.
- Prototype environment landed as `.venv-crawl4ai`.
- `crawl4ai==0.8.0` and `playwright==1.58.0` are installed there, Chromium is installed, and a minimal `AsyncWebCrawler` smoke succeeded.
- `crawl4ai-doctor` also succeeds when `PYTHONIOENCODING=utf-8` is set under the current Windows console.
