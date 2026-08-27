"""
Constraint profiles: the rules each platform's variant must satisfy.
Enforcement is code, not hope — a variant that breaks a rule is blocked
before it ever reaches review (Probe 2 in the brief).
"""

PROFILES = {
    "x": {
        "max_len": 280,
        "max_hashtags": 3,
        "tone": "punchy",
    },
    "linkedin": {
        "max_len": 3000,
        "max_hashtags": 5,
        "tone": "professional",
    },
}


class ConstraintViolation(Exception):
    def __init__(self, platform: str, rule: str, detail: str):
        self.platform = platform
        self.rule = rule
        self.detail = detail
        super().__init__(f"[{platform}] broke rule '{rule}': {detail}")


def count_hashtags(text: str) -> int:
    return sum(1 for tok in text.split() if tok.startswith("#"))


def validate(platform: str, text: str) -> None:
    """Raises ConstraintViolation naming the exact broken rule, or returns silently."""
    if platform not in PROFILES:
        raise ConstraintViolation(platform, "unknown_platform", f"no constraint profile for '{platform}'")

    profile = PROFILES[platform]

    if len(text) > profile["max_len"]:
        raise ConstraintViolation(
            platform, "max_len",
            f"{len(text)} chars exceeds limit of {profile['max_len']}"
        )

    tags = count_hashtags(text)
    if tags > profile["max_hashtags"]:
        raise ConstraintViolation(
            platform, "max_hashtags",
            f"{tags} hashtags exceeds limit of {profile['max_hashtags']}"
        )


def generate_variant(platform: str, post_body: str) -> str:
    """
    Template-based variant generation (AI is optional per the brief —
    this keeps the capstone runnable with zero API keys).
    Swap this for a Gemini/Ollama call later if you want the AI stretch.
    """
    summary = post_body.strip().replace("\n", " ")

    if platform == "x":
        # Punchy, short, capped hashtags.
        text = summary[:250].rstrip()
        return f"{text}\n\n#buildinpublic #backend"

    if platform == "linkedin":
        text = summary[:2800].rstrip()
        return (
            f"{text}\n\n"
            f"Full write-up linked below. Would love your thoughts.\n"
            f"#SoftwareEngineering #BackendDevelopment"
        )

    raise ConstraintViolation(platform, "unknown_platform", f"no generator for '{platform}'")
