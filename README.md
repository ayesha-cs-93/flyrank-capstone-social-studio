# Social Media Studio

Turns one blog post into approved, scheduled, idempotently-published
posts across multiple platforms — built for the FlyRank Backend AI
Engineering capstone (current "Social Media Studio" brief).

## Architecture

```
POST -> ingest & store (Post, single source of truth)
      -> variant generator (per platform)
      -> constraint validation (length / hashtags / tone rules)
      -> review workflow: draft -> approved | rejected
      -> scheduler (durable — jobs live in the same SQLite DB)
      -> SocialPublisher interface
           +-- TelegramPublisher   (real, free target)
           +-- MockXPublisher      (records what it would post)
           +-- MockLinkedInPublisher
      -> publish history (every attempt, success or not)
```

The app only ever talks to the `SocialPublisher` interface
(`app/adapters.py`). Which concrete class handles which platform is a
one-line registry entry (`ADAPTER_REGISTRY`), not a code change.

**Idempotency** — the part the brief calls the heart of the grade — is
enforced two ways: a unique `idempotency_key` per (variant, slot), and a
check for an existing `success` `PublishAttempt` row before the adapter
is ever called again. See `app/scheduler.py::publish_slot`.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

### Seed / try it end to end

```bash
python3 e2e_test.py
```

This ingests a post, generates X + LinkedIn variants, proves an
unapproved variant can't be scheduled, approves + schedules one, waits
for it to fire, then manually re-calls the publish job 3 more times to
prove idempotency (see `EVIDENCE.md` for the full transcript).

## Endpoints

| Method | Path | What it does |
|---|---|---|
| POST | `/posts` | Ingest a post (`source`: `url`\|`markdown`) |
| POST | `/posts/{id}/generate` | Generate variants for given `platforms` |
| POST | `/variants/{id}/approve` | Approve a draft variant |
| POST | `/variants/{id}/reject` | Reject a draft variant |
| POST | `/variants/{id}/schedule` | Schedule an **approved** variant (`publish_at`) |
| GET | `/publish-history` | Every publish attempt, newest first |
| GET | `/constraint-profiles` | Current per-platform rules |

## Known limitations

- `POST /posts` with `source: "url"` does not fetch the URL yet — it
  stores a placeholder. Swap in a `requests.get()` + extraction step if
  full URL ingestion is needed.
- Variant generation is template-based, not AI-generated (the brief
  allows either — enforcement is what's graded). Swapping in Gemini/
  Ollama is a change to `app/constraints.py::generate_variant` only.
- Real Telegram publishing is implemented (`app/adapters.py::TelegramPublisher`)
  but only exercised against the mock adapters so far — see
  `BUILDLOG.md` for the remaining live-test step.
- Only two platforms (`x`, `linkedin`) have constraint profiles + real
  templates wired up; Telegram itself is treated as the real publish
  *target*, not a third content variant, per the brief's "one real
  free platform" requirement.

## Repo naming (per brief)

Push this as a new **public** repo named `flyrank-capstone-social-studio`,
separate from your assignments repo, first commit = this README +
`.gitignore`.
