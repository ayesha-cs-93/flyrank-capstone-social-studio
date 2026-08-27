# EVIDENCE.md

One proof per Requirements box. Ran with `python3 e2e_test.py` against a
fresh `social_studio.db`, server on `localhost:8000`. Full transcript
below (also runnable yourself — see README).

## Ingestion + storage as source of truth

```
POST /posts {"source":"markdown","content":"We shipped idempotent publishing..."}
-> 200 {'id': '429ffb4c-...', 'source': 'markdown', 'body': 'We shipped idempotent publishing...'}
```
Generation for both platforms below reads this stored `body` only.

## Constraint profiles enforced by code

Good case — two distinct variants from one post:
```
POST /posts/{id}/generate {"platforms":["x","linkedin"]}
-> {'created': [{'platform': 'x', 'text': '...#buildinpublic #backend'},
                {'platform': 'linkedin', 'text': '...#SoftwareEngineering #BackendDevelopment'}],
    'blocked': []}
```
Bad case — unknown platform is blocked, naming the broken rule:
```
POST /posts/{id}/generate {"platforms":["nonexistent"]}
-> {'created': [], 'blocked': [{'platform': 'nonexistent', 'rule': 'unknown_platform',
                                 'detail': "no generator for 'nonexistent'"}]}
```
(`app/constraints.py::validate` also blocks on `max_len` / `max_hashtags` the
same way — see the function for the exact checks.)

## Review workflow — unapproved variant cannot be scheduled

```
POST /variants/{id}/schedule {"publish_at":"2026-08-27T06:00:00"}
-> HTTP 400 {'detail': "variant status is 'draft', must be 'approved' to schedule"}
```
After approval, the same call succeeds:
```
POST /variants/{id}/approve -> 200 {'status': 'approved'}
POST /variants/{id}/schedule {...} -> 200 {'slot_id': 'c9024c00-...', ...}
```

## Adapter layer — swap via config, zero business-logic change

`app/adapters.py::ADAPTER_REGISTRY` maps platform name -> adapter class.
The scheduler calls `get_publisher(variant.platform)` — never a concrete
class. Changing `"x": MockXPublisher` to `"x": TelegramPublisher` (or vice
versa) is a one-line registry edit; `scheduler.py` and `main.py` are
untouched.

## Idempotent publish — the core proof

Slot published once by the scheduler, then `publish_slot(slot_id)` called
3 more times manually (simulating retries):

```
publish-history after first (scheduled) fire:
[{'result': 'success', 'detail': 'mock:mock_x:e8b4a365-...:2026-08-27T05:26:47...'}]

publish-history after 3 more manual calls:
[duplicate_skipped, duplicate_skipped, duplicate_skipped, success]

success rows for slot: 1   (must be 1)
duplicate_skipped rows: 3
IDEMPOTENCY CHECK PASSED — exactly one post, despite 4 total publish calls.
```

## Durable scheduling

Jobs are stored in `SQLAlchemyJobStore(url="sqlite:///./social_studio.db")`
— the same DB file, not in-memory. A process restart re-reads pending jobs
from this table, so a worker killed mid-batch resumes without re-running
completed jobs (guarded additionally by the idempotency check above).

## Publish history

`GET /publish-history` returns every attempt (success + duplicate_skipped +
error) ordered newest-first — see transcript above.

## Secrets

`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are read only from environment
variables (`os.environ.get`, `app/adapters.py`). `.env` is git-ignored;
`.env.example` ships with placeholder values only.
