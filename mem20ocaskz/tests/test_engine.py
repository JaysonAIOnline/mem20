"""Bounded tests for mem20ocaskz.

Every test builds its own tiny SQLite database in tmp_path, so the suite is
fast, deterministic and never touches the real 3.47 GB opencode database.
The one integration test against the real database skips cleanly when absent.
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from mem20ocaskz import engine as A
from mem20ocaskz import cli as C

SCHEMA = """
CREATE TABLE session (
  id text PRIMARY KEY,
  project_id text NOT NULL,
  title text NOT NULL,
  directory text NOT NULL,
  version text NOT NULL,
  time_created integer NOT NULL
);
CREATE TABLE message (
  id text PRIMARY KEY,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE TABLE part (
  id text PRIMARY KEY,
  message_id text NOT NULL,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
"""


def build_db(path, sessions=(), prompts=(), extra_messages=()):
    """Create a synthetic opencode-shaped database.

    prompts: (session_id, message_id, text, role)
    """
    parent = os.path.dirname(str(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for sid, title, directory in sessions:
        con.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?)",
            (sid, "p1", title, directory, "1.18.34", 1700000000000),
        )
    for sid, mid, text, role in list(prompts) + list(extra_messages):
        ts = 1700000000000
        con.execute(
            "INSERT INTO message VALUES (?,?,?,?,?)",
            (mid, sid, ts, ts, json.dumps({"role": role, "agent": "build"})),
        )
        con.execute(
            "INSERT INTO part VALUES (?,?,?,?,?,?)",
            ("pt_" + mid, mid, sid, ts, ts,
             json.dumps({"type": "text", "text": text})),
        )
    con.commit()
    con.close()
    return str(path)


# ---------------------------------------------------------------- classify

def test_classify_explicit_names_opencode():
    themes, kinds, noise = A.classify("does opencode have tts and stt")
    assert not noise
    assert "explicit" in kinds
    assert "capability-question" in kinds
    assert "voice-tts-stt" in themes


def test_classify_feature_request():
    themes, kinds, noise = A.classify("add a button for rollback please")
    assert not noise
    assert "feature-request" in kinds
    assert "rollback-undo" in themes


def test_classify_capability_question_without_product_name():
    themes, kinds, noise = A.classify("can the tui support subagents")
    assert not noise
    assert "capability-question" in kinds
    assert "subagents" in themes
    assert "explicit" not in kinds, "prompt never names opencode"


def test_classify_noise_is_detected():
    for text in (
        "I overheard you say something interesting: hello. Keep your reply to 1-3 sentences.",
        "You are packaging an existing Python project, **mem20**",
    ):
        _, _, noise = A.classify(text)
        assert noise is True, text


def test_classify_plain_prompt_is_not_an_ask():
    themes, kinds, noise = A.classify("run the tests please")
    assert themes == ()
    assert kinds == ()
    assert noise is False


def test_classify_multiple_themes():
    themes, _, _ = A.classify(
        "the desktop client needs a dropdown for models and a webfrontend for tabs"
    )
    assert "gui-command-center" in themes
    assert "model-picker" in themes


def test_classify_gui_command_center_phrase():
    themes, _, _ = A.classify(
        "the hermes dashboard is a fully functional framework, lots of pages and tabs"
    )
    assert "gui-command-center" in themes


def test_classify_output_pacing():
    themes, _, _ = A.classify("answer the question then wait for instructions")
    assert "output-pacing" in themes


def test_every_theme_pattern_compiles():
    for name, pats in A.THEMES.items():
        assert pats, f"theme {name} has no patterns"
        for p in pats:
            re_compiled = A.re.compile(p, A.re.I)
            assert re_compiled is not None


# ------------------------------------------------------------------- audit

def test_audit_counts_and_classifies(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "Accessing kanban board", "/root")],
        prompts=[
            ("ses_a", "msg_1", "does opencode have tts and stt", "user"),
            ("ses_a", "msg_2", "run the tests", "user"),
            ("ses_a", "msg_3", "can opencode use subagents", "user"),
        ],
        extra_messages=[("ses_a", "msg_4", "does opencode have tts", "assistant")],
    )
    result = A.audit(db)
    assert result.session_count == 1
    assert result.prompts_total == 3, "assistant turns must not be counted"
    assert len(result.asks) == 2
    assert result.prompts_noise == 0
    assert result.sessions_with_asks == 1
    assert result.theme_counts["voice-tts-stt"] == 1
    assert result.theme_counts["subagents"] == 1


def test_audit_noise_counted_not_hidden(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[
            ("ses_a", "msg_1", "You are packaging an existing Python project", "user"),
            ("ses_a", "msg_2", "does opencode have tts", "user"),
            ("ses_a", "msg_3", "run the tests", "user"),
        ],
    )
    result = A.audit(db)
    assert result.prompts_total == 3
    assert result.prompts_noise == 1
    assert len(result.asks) == 1
    # Nothing silently disappears: every prompt is an ask, noise, or neither.
    unclassified = (
        result.prompts_total - len(result.asks) - result.prompts_noise
    )
    assert unclassified == 1


def test_audit_leaves_database_untouched(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    before = A.fingerprint(db)
    A.audit(db)
    assert A.fingerprint(db) == before


def test_audit_limit_is_bounded(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", f"msg_{i}", "does opencode have tts", "user")
                 for i in range(10)],
    )
    assert A.audit(db, limit=3).prompts_total == 3


def test_audit_asks_sorted_by_time(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    result = A.audit(db)
    times = [a.prompt.time_created for a in result.asks]
    assert times == sorted(times)


def test_missing_database_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        A.connect(str(tmp_path / "nope.db"))


def test_quote_collapses_whitespace(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode\n   have\ttts", "user")],
    )
    result = A.audit(db)
    assert result.asks[0].quote == "does opencode have tts"


# ------------------------------------------------------------- index render

def test_render_index_is_traceable(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_abc123", "Accessing kanban board", "/root")],
        prompts=[("ses_abc123", "msg_1", "does opencode have tts and stt", "user")],
    )
    text = A.render_index(A.audit(db))
    assert "ses_abc123" in text
    assert "does opencode have tts and stt" in text
    assert "voice-tts-stt" in text
    assert "Accessing kanban board" in text
    assert "Database unchanged by this audit: **True**" in text


def test_render_index_truncates_long_quotes(tmp_path):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts " + "x" * 5000, "user")],
    )
    text = A.render_index(A.audit(db), max_quote=100)
    assert "…" in text
    assert "x" * 5000 not in text


# --------------------------------------------------------------------- CLI

def test_cli_scan_json(tmp_path, capsys):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    assert C.main(["--db", db, "scan", "--json"]) == C.EXIT_CLEAN
    payload = json.loads(capsys.readouterr().out)
    assert payload["prompts_total"] == 1
    assert len(payload["asks"]) == 1


def test_cli_search_hit_and_miss(tmp_path, capsys):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    assert C.main(["--db", db, "search", "tts"]) == C.EXIT_CLEAN
    assert "1 match" in capsys.readouterr().out
    assert C.main(["--db", db, "search", "zzzznotpresent"]) == C.EXIT_FINDINGS


def test_cli_index_writes_file(tmp_path, capsys):
    db = build_db(
        tmp_path / "data" / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    out = tmp_path / "docs" / "index.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    assert C.main(["--db", db, "index", "--out", str(out)]) == C.EXIT_CLEAN
    assert out.exists()
    assert "does opencode have tts" in out.read_text()


def test_cli_index_refuses_data_dir(tmp_path):
    db = build_db(
        tmp_path / "data" / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    bad = os.path.join(os.path.dirname(db), "index.md")
    assert C.main(["--db", db, "index", "--out", bad]) == C.EXIT_ERROR
    assert not os.path.exists(bad)


def test_cli_verify_passes_on_stable_db(tmp_path, capsys):
    db = build_db(
        tmp_path / "opencode.db",
        sessions=[("ses_a", "t", "/root")],
        prompts=[("ses_a", "msg_1", "does opencode have tts", "user")],
    )
    assert C.main(["--db", db, "verify", "--repeat", "2"]) == C.EXIT_CLEAN
    assert "PASS" in capsys.readouterr().out


def test_cli_themes_lists_taxonomy(capsys):
    assert C.main(["themes"]) == C.EXIT_CLEAN
    out = capsys.readouterr().out
    assert "voice-tts-stt" in out
    assert "gui-command-center" in out


def test_cli_scan_missing_db_errors(tmp_path, capsys):
    assert C.main(["--db", str(tmp_path / "gone.db"), "scan"]) == C.EXIT_ERROR


# ------------------------------------------------------- integration (opt-in)

@pytest.mark.skipif(
    not os.path.exists(A.default_db_path()), reason="real opencode db not present"
)
def test_real_database_is_readable_and_stable():
    """Proves the tool works on the real 3.47 GB database, not just fixtures."""
    result = A.audit()
    assert result.prompts_total > 0
    assert result.db_unchanged is True
    assert result.asks, "expected feature asks in real session history"