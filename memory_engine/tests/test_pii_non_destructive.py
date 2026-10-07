"""Regression tests for secret detection and non-destructive storage.

The store path must never rewrite the caller's text. Redaction is an explicit
output operation only.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import memory  # noqa: E402
from memory import _detect_only, _scrub_secrets, detect_secrets, redact_secrets  # noqa: E402

GIT_SHA1 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BRAID_CID = "br25166abf9a68c78abb8545dacb65dbcedbcb1f69ec0b02be4c1e4a4f48fec32c"
SHA256 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
AWS_SECRET_40 = ("aB3xY9Zq7WpL2mN8kRS4tVU6wXyZ1aB3xY9Zq7WpL"[:40])


class TestNoFalsePositives:
    def test_git_sha1_not_flagged(self):
        assert detect_secrets(f"deployed commit {GIT_SHA1} today") == []

    def test_braid_cid_not_flagged(self):
        assert detect_secrets(f"node {BRAID_CID} committed") == []

    def test_sha256_not_flagged(self):
        assert detect_secrets(f"digest {SHA256} end") == []

    def test_uuid_not_flagged(self):
        assert detect_secrets("id 550e8400-e29b-41d4-a716-446655440000") == []

    def test_plain_prose_not_flagged(self):
        text = "the secret sauce is the secret sauce and the api key is the api key"
        assert detect_secrets(text) == []

    def test_pure_alpha_40_not_flagged(self):
        assert detect_secrets("a" * 40) == []

    def test_long_technical_prose_untouched(self):
        text = f"replay buffer uses priorities; commit {GIT_SHA1} landed today"
        cleaned, detected = _scrub_secrets(text)
        assert cleaned == text
        assert detected == []

    def test_filesystem_path_not_flagged_as_aws_secret(self):
        text = "changed files:\n  - mem20zeroinstallmicroappruntimez/HANDOFF.md\n  - SITEMAP.md\n"
        assert detect_secrets(text) == []
        cleaned, detected = _scrub_secrets(text)
        assert cleaned == text
        assert detected == []

    def test_path_heavy_file_list_not_flagged(self):
        names = [
            "mem20adaptiveinterfacecomposerz/web/src/App.jsx",
            "mem20controlz/mem20controlz/static/index.html",
            "mem20zerotouchnodeswarmz/ROADMAP.md",
        ]
        text = "observed file-change record:\n" + "".join(f"  - {n}\n" for n in names)
        assert detect_secrets(text) == []

    def test_password_instruction_in_prose_not_flagged(self):
        text = "while resetting the control-plane admin password: rotating MEM20_CONTROL_PASSWORD in /opt/mem20"
        assert detect_secrets(text) == []


class TestTruePositives:
    def test_openai_style_key(self):
        found = detect_secrets("sk-" + "A" * 48)
        assert found and found[0].label == "OpenAI-style API key"
        assert found[0].confidence == "high"

    def test_anthropic_key(self):
        found = detect_secrets("sk-ant-" + "B" * 95)
        assert found and found[0].label == "Anthropic API key"

    def test_github_tokens(self):
        for prefix, label in (
            ("ghp_", "GitHub Personal Access Token"),
            ("ghs_", "GitHub Secret"),
            ("gho_", "GitHub OAuth Token"),
        ):
            found = detect_secrets(prefix + "C" * 36)
            assert found, prefix
            assert found[0].label == label

    def test_slack_token(self):
        found = detect_secrets("xoxb-12345678901-23456789012-" + "E" * 24)
        assert found and found[0].label == "Slack Bot Token"

    def test_aws_access_key_id(self):
        found = detect_secrets("AKIA" + "F" * 16)
        assert found and found[0].label == "AWS Access Key ID"

    def test_google_api_key(self):
        found = detect_secrets("AIza" + "G" * 35)
        assert found and found[0].label == "Google API Key"

    def test_bearer_token(self):
        found = detect_secrets("Authorization: Bearer " + "H" * 40)
        assert found and found[0].label == "Bearer token"

    def test_aws_secret_mixed_charset(self):
        found = detect_secrets(AWS_SECRET_40)
        assert found and found[0].label.startswith("AWS Secret Access Key")

    def test_password_assignment(self):
        found = detect_secrets("password = hunter2000")
        assert found and found[0].label == "Password assignment"

    def test_api_key_assignment(self):
        found = detect_secrets("api_key: 9f83bd2kQ1")
        assert found and found[0].label == "API key assignment"


class TestConfidenceFloor:
    def test_high_floor_filters_low_confidence(self):
        assert detect_secrets("password = hunter2000", min_confidence="high") == []
        assert detect_secrets("sk-" + "A" * 48, min_confidence="high")

    def test_medium_floor_keeps_bearer_drops_password(self):
        text = "Authorization: Bearer " + "H" * 40 + " password = hunter2000"
        labels = [f.label for f in detect_secrets(text, min_confidence="medium")]
        assert "Bearer token" in labels
        assert "Password assignment" not in labels


class TestRedactionIsOutputOnly:
    def test_redaction_removes_secret(self):
        key = "sk-" + "A" * 48
        redacted, findings = redact_secrets(f"token {key} leaked")
        assert key not in redacted
        assert "[REDACTED OpenAI-style API key]" in redacted
        assert findings

    def test_redaction_preserves_surrounding_text(self):
        key = "sk-" + "A" * 48
        redacted, _ = redact_secrets(f"before {key} after")
        assert redacted.startswith("before ")
        assert redacted.endswith(" after")

    def test_redaction_of_clean_text_is_identity(self):
        text = f"nothing to see, commit {GIT_SHA1}"
        redacted, findings = redact_secrets(text)
        assert redacted == text
        assert findings == []

    def test_redaction_handles_multiple_secrets(self):
        text = f"a ghp_{'C'*36} b sk-{'A'*48} c"
        redacted, findings = redact_secrets(text)
        assert len(findings) == 2
        assert "ghp_" not in redacted
        assert "REDACTED" in redacted
        assert redacted.startswith("a ")
        assert redacted.endswith(" c")

    def test_detect_only_never_mutates(self):
        text = f"commit {GIT_SHA1} and node {BRAID_CID}"
        assert _detect_only(text) == []


class TestStorePathIsNonDestructive:
    @contextmanager
    def _isolate_store(self, tmp):
        """Point EVERY store-derived path at `tmp`, and restore after.

        Rebinding only LEDGER and ENTRIES is not enough. `remember()` writes the
        ledger row to memory.LEDGER but then indexes through memory.VECTOR_INDEX,
        memory.VECTOR_META, memory.BM25_INDEX, memory.BM25_CORPUS, and
        memory.GRAPH_INDEX. With those left alone the test writes its ledger into
        tmp and its index rows into the LIVE store -- creating an orphaned index
        entry per run and permanently drifting the production indexes against the
        real ledger.

        That is not hypothetical: two such orphans (`pii-regression`,
        `pii-meta`) were found in the live store's vector metadata with no
        matching ledger record, having been created by this test.
        """
        keys = ("LEDGER", "ENTRIES", "INDEX", "BACKUP_DIR", "VECTOR_INDEX",
                "VECTOR_META", "BM25_INDEX", "BM25_CORPUS", "GRAPH_INDEX",
                "SIMULATED_LEDGER", "PINNED_FILE", "WORLD_MODEL_FILE",
                "PREDICTIONS_LEDGER", "AFFECTIVE_FILE", "PROCEDURAL_FILE")
        saved = {k: getattr(memory, k) for k in keys}
        for k in keys:
            if k in ("ENTRIES", "BACKUP_DIR"):
                setattr(memory, k, os.path.join(tmp, k.lower()))
            else:
                setattr(memory, k, os.path.join(tmp, k.lower()))
        try:
            yield
        finally:
            for k, v in saved.items():
                setattr(memory, k, v)

    def test_remember_stores_original_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolate_store(tmp):
                text = f"commit {GIT_SHA1} node {BRAID_CID} uuid 550e8400-e29b-41d4-a716-446655440000"
                rec = memory.remember(topic="pii-regression", content=text)
                assert rec["id"]
                results = memory.recall("pii-regression", k=5)
                joined = " ".join(r.get("content", "") for r in results)
                assert GIT_SHA1 in joined, "git SHA must survive storage verbatim"
                assert BRAID_CID in joined, "braid CID must survive storage verbatim"

                # The index must have followed the ledger into tmp, not stayed
                # behind pointing at whatever store was live.
                assert memory.VECTOR_INDEX.startswith(tmp)
                assert memory.GRAPH_INDEX.startswith(tmp)

    def test_remember_records_detection_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolate_store(tmp):
                memory.remember(topic="pii-meta", content="password = hunter2000")
                import json

                with open(memory.LEDGER, encoding="utf-8") as handle:
                    rows = [json.loads(line) for line in handle if line.strip()]
                meta = [r for r in rows if r.get("topic") == "pii-meta"]
                assert meta, "ledger row missing"
                assert meta[0]["secrets_detected"], "detection metadata should be recorded"
