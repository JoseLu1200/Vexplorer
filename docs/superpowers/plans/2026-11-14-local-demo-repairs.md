# Local demo repairs

**Goal:** Restore a reproducible local demo with honest provenance and real embeddings.

**Architecture:** Keep validators closed. Announce accepted reference syntax to the proposer, restore revision-bound table costs from their own repository, and align replay requests with the existing API. Preserve current workspace changes.

**Tech Stack:** FastAPI/Python, native JavaScript, pytest and node:test.

- [x] Add failing tests for vector reference authority, table cost reload, and replay request mode.
- [x] Implement narrow corrections in live.py, main.py and core/table.js.
- [x] Run focused Python and frontend regressions.
- [x] Restart the owned localhost process and verify persisted data, costs, replay and a real general-furniture job.
- [x] Deliver exact URLs, fixture paths, UI steps and known limitations.
