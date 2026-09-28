"""The models proven to answer on this host, recorded so the roster cannot drift.

Generated from a live probe. Kept as data rather than re-probed in CI, because
the point of the roster test is to catch *edits to the roster* that introduce an
unverified model - not to re-bill eight providers on every test run.
"""

VERIFIED = {
    # groq
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "allam-2-7b",
    # cohere (OpenAI-compatible endpoint)
    "command-a-plus-05-2026",
    "command-a-03-2025",
    "command-a-reasoning-08-2025",
    "c4ai-aya-expanse-32b",
}
