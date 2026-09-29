"""llm must not publish the estate's secrets into the process environment.

Regression test for a real leak. ``llm._load_dotenv`` used to copy *every* key
from ``/opt/mem20/secrets/.env`` into ``os.environ`` at import time, so any
process importing it - the dream engine, the control plane, the cognitive engine,
the game build harness - held the control-plane admin password, the sudo
password, database credentials and cloud keys that have nothing to do with
calling a model. It was also sticky: the snapshot happened once, at import, so a
rotated secret in the file was ignored for the life of the process. That is how
the control plane served a stale admin password until someone restarted it.

These tests import in a subprocess, because the property is about what *importing*
does to a process - asserting it in the current interpreter would be asserting
something about the test session rather than about the module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run_in_subprocess(body: str) -> dict:
    """Import llm in a clean interpreter and return what it reports as JSON."""
    script = textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_importing_llm_adds_nothing_to_the_process_environment():
    report = _run_in_subprocess(
        """
        import json, os
        before = set(os.environ)
        import llm
        added = sorted(set(os.environ) - before)
        print(json.dumps({
            "added": added,
            # Spot-check the credentials that must never be published.
            "control_password_present": "MEM20_CONTROL_PASSWORD" in os.environ,
            "control_secret_present": "MEM20_CONTROL_SECRET" in os.environ,
            "sudo_present": "SUDO_PASSWORD" in os.environ,
            "github_present": "GITHUB_TOKEN" in os.environ,
        }))
        """
    )
    assert report["added"] == [], f"llm published {len(report['added'])} keys into os.environ: {report['added'][:12]}"
    for key in ("control_password_present", "control_secret_present", "sudo_present", "github_present"):
        assert report[key] is False, f"llm leaked a non-LLM credential ({key})"


def test_llm_still_finds_its_provider_key_in_the_file():
    """The point of the fix is *not* to stop llm reading the file.

    It reads the file, it just keeps the values to itself.
    """
    report = _run_in_subprocess(
        """
        import json, llm
        base, key, model = llm._config()
        print(json.dumps({
            "has_key": bool(key),
            "base_is_configured": bool(base),
            "model": model,
        }))
        """
    )
    assert report["has_key"] is True, "llm must still resolve its provider key from the secrets file"
    assert report["base_is_configured"] is True
    assert report["model"], "a model must still resolve"


def test_a_real_environment_value_wins_over_the_file():
    """Injecting a secret through the environment must keep working."""
    report = _run_in_subprocess(
        """
        import json, os
        os.environ["GROQ_API_KEY"] = "value-from-the-environment"
        import llm
        print(json.dumps({"resolved": llm._get("GROQ_API_KEY")}))
        """
    )
    assert report["resolved"] == "value-from-the-environment"


def test_the_file_is_still_consulted_for_values_absent_from_the_environment():
    report = _run_in_subprocess(
        """
        import json, os
        os.environ.pop("GROQ_API_KEY", None)
        import llm
        print(json.dumps({
            "resolved_nonempty": bool(llm._get("GROQ_API_KEY")),
            # And the value is genuinely not in the environment.
            "in_environment": "GROQ_API_KEY" in os.environ,
        }))
        """
    )
    assert report["resolved_nonempty"] is True
    assert report["in_environment"] is False, "the value must be read, not published"


def test_file_values_are_consulted_at_call_time_and_the_environment_wins():
    """`_get` reads the map per call, so precedence is decided every time.

    Note what this does *not* claim: llm still reads the file once, at import.
    Rotating a provider key therefore still needs the consumer restarted, exactly
    as before this change. What is fixed is that the values live in one private
    map instead of being copied into every process that imports the module.
    """
    import llm

    saved = llm._FILE_VALUES.get("GROQ_API_KEY")
    saved_env = os.environ.pop("GROQ_API_KEY", None)
    try:
        llm._FILE_VALUES["GROQ_API_KEY"] = "from-the-file"
        assert llm._get("GROQ_API_KEY") == "from-the-file"

        llm._FILE_VALUES["GROQ_API_KEY"] = "rotated"
        assert llm._get("GROQ_API_KEY") == "rotated", "the map is read per call, not snapshotted"

        os.environ["GROQ_API_KEY"] = "from-the-environment"
        assert llm._get("GROQ_API_KEY") == "from-the-environment", "the environment takes precedence"
    finally:
        os.environ.pop("GROQ_API_KEY", None)
        if saved_env is not None:
            os.environ["GROQ_API_KEY"] = saved_env
        if saved is None:
            llm._FILE_VALUES.pop("GROQ_API_KEY", None)
        else:
            llm._FILE_VALUES["GROQ_API_KEY"] = saved
