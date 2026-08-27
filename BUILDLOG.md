# BUILDLOG.md

Built with Claude as pair-programmer given the FlyRank "Social Media
Studio" brief. Logging honestly per the brief's requirement.

## Where AI helped
- Scaffolding the SQLAlchemy models, FastAPI routes, and the
  APScheduler + SQLAlchemyJobStore wiring — boilerplate I know how to
  write but that AI wrote faster.
- Suggesting the two-layer idempotency guard (unique idempotency_key at
  the DB level + a pre-publish check against `PublishAttempt` rows)
  instead of relying on APScheduler's `replace_existing` alone.

## Where AI was wrong / had to be corrected
- First pass of the e2e test used raw `curl` + bash string extraction on
  JSON responses containing embedded newlines — this broke bash's
  variable handling (not actually invalid JSON, just fragile shell
  parsing). Rewrote the test in plain Python (`e2e_test.py`) using
  `urllib` instead of shelling out, which is what the transcript in
  EVIDENCE.md is from.
- Initial background-server start with plain `&` died between tool
  calls because each call runs in a fresh shell — had to use `setsid`
  to detach it properly.

## What I changed / still need to do
- [ ] Get a real Telegram bot token + chat ID and re-run Probe 4/6
      against the real `TelegramPublisher` (currently only tested
      against the mock adapters — the real HTTP call path in
      `adapters.py::TelegramPublisher.publish` is untested live).
- [ ] Decide whether to keep template-based variant generation
      (current, zero API keys needed) or wire up the optional
      Gemini/Ollama AI path.
- [ ] Add the durable-scheduler crash-and-resume manual test (kill the
      uvicorn process mid-batch, restart, confirm the job store still
      has the pending job and it fires without a duplicate).
- [ ] Push to a public repo named `flyrank-capstone-social-studio` per
      the brief's naming convention, first commit = README skeleton +
      .gitignore.
