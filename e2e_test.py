"""
Seed / smoke-test script: exercises the full happy path plus the two
scariest probes (unapproved-schedule refusal, idempotent publish).
Run the server first (`uvicorn app.main:app --reload`), then:
    python3 e2e_test.py
"""
import json
import time
import datetime
import urllib.request
import urllib.error

BASE = "http://localhost:8000"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("== 1. Ingest ==")
status, post = call("POST", "/posts", {
    "source": "markdown",
    "content": "We shipped idempotent publishing for our capstone this week."
})
print(status, post)
post_id = post["id"]

print("\n== 2. Generate variants ==")
status, gen = call("POST", f"/posts/{post_id}/generate", {"platforms": ["x", "linkedin"]})
print(status, gen)
variant_id = gen["created"][0]["id"]

print("\n== 2b. Generate a rule-breaking variant (Probe 2) ==")
status, bad = call("POST", f"/posts/{post_id}/generate", {"platforms": ["nonexistent"]})
print(status, bad)

print("\n== 3. Schedule BEFORE approval — must be 400 (Probe 3) ==")
status, resp = call("POST", f"/variants/{variant_id}/schedule",
                     {"publish_at": "2026-08-27T06:00:00"})
print(status, resp)
assert status == 400, "unapproved schedule should be rejected"

print("\n== 4. Approve ==")
status, resp = call("POST", f"/variants/{variant_id}/approve")
print(status, resp)

print("\n== 5. Schedule 5s from now ==")
publish_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5)).isoformat()
status, sched = call("POST", f"/variants/{variant_id}/schedule", {"publish_at": publish_at})
print(status, sched)
slot_id = sched["slot_id"]

print("waiting for scheduler to fire...")
time.sleep(8)

print("\n== 6. Publish history after first fire ==")
status, hist = call("GET", "/publish-history")
print(status, hist)

print("\n== 7. Idempotency hammer: manually re-run the same publish job 3x ==")
import sys
sys.path.insert(0, ".")
from app.scheduler import publish_slot
for i in range(3):
    publish_slot(slot_id)

status, hist2 = call("GET", "/publish-history")
successes = [h for h in hist2 if h["slot_id"] == slot_id and h["result"] == "success"]
dup_skips = [h for h in hist2 if h["slot_id"] == slot_id and h["result"] == "duplicate_skipped"]
print(f"success rows for slot: {len(successes)} (must be 1)")
print(f"duplicate_skipped rows: {len(dup_skips)}")
assert len(successes) == 1, "IDEMPOTENCY VIOLATION: more than one success row!"
print("\nIDEMPOTENCY CHECK PASSED — exactly one post, despite 4 total publish calls.")
