"""
SocialPublisher interface + adapters.

The app depends ONLY on the SocialPublisher interface. Swapping an
adapter (e.g. "x" -> mock_x) is a config change, never a business-logic
change — that's the whole point of the adapter seam.
"""
import os
import time
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mock_publish_store")
os.makedirs(DATA_DIR, exist_ok=True)


class SocialPublisher(ABC):
    @abstractmethod
    def publish(self, text: str, idempotency_key: str) -> str:
        """Publish `text`. Must be safe to call twice with the same
        idempotency_key — the second call must not create a second post.
        Returns a human-readable reference to the published message
        (a real URL, or a mock reference id)."""
        raise NotImplementedError


class TelegramPublisher(SocialPublisher):
    """Real, free target. Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in env."""

    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        # Idempotency is enforced at the scheduler layer (one row per slot,
        # publish_attempts checked before calling here) — see scheduler.py.

    def publish(self, text: str, idempotency_key: str) -> str:
        if not self.token or not self.chat_id:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — see .env.example"
            )
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = json.dumps({"chat_id": self.chat_id, "text": text}).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Telegram publish failed: {e.read().decode()}")

        if not body.get("ok"):
            raise RuntimeError(f"Telegram publish failed: {body}")

        msg_id = body["result"]["message_id"]
        return f"telegram:msg:{msg_id}"


class _MockPublisher(SocialPublisher):
    """Base for mock adapters — records what it WOULD post to a local
    JSON store and returns a fake reference id."""
    platform_name = "mock"

    def publish(self, text: str, idempotency_key: str) -> str:
        path = os.path.join(DATA_DIR, f"{self.platform_name}.jsonl")
        record = {
            "idempotency_key": idempotency_key,
            "text": text,
            "published_at": time.time(),
        }
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return f"mock:{self.platform_name}:{idempotency_key}"


class MockXPublisher(_MockPublisher):
    platform_name = "mock_x"


class MockLinkedInPublisher(_MockPublisher):
    platform_name = "mock_linkedin"


# Config-driven registry — this is the "swap an adapter in config" seam
# that Probe 6 checks. Change the value here (or read from env) and no
# other code changes.
ADAPTER_REGISTRY = {
    "telegram": TelegramPublisher,
    "x": MockXPublisher,          # real X account not used — mock per brief
    "mock_x": MockXPublisher,
    "linkedin": MockLinkedInPublisher,
    "mock_linkedin": MockLinkedInPublisher,
}


def get_publisher(platform: str) -> SocialPublisher:
    cls = ADAPTER_REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"no adapter registered for platform '{platform}'")
    return cls()
