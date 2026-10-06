"""Hermetic tests for mem20greenz (no network, no live substrate)."""

from __future__ import annotations

import http.server
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


class TestRegistry(unittest.TestCase):
    def _reg(self):
        from mem20greenz.store import Registry
        tmp = tempfile.mkdtemp(prefix="greenz-reg-")
        return Registry(Path(tmp) / "r.sqlite"), tmp

    def test_add_get_list(self):
        reg, _ = self._reg()
        created = reg.add("demo", "website", "http://127.0.0.1:1/")
        self.assertEqual(created["status"], "staged")
        self.assertEqual(reg.get("demo")["source"], "http://127.0.0.1:1/")
        self.assertEqual(len(reg.list()), 1)

    def test_bad_kind_rejected(self):
        from mem20greenz.store import RegistryError
        reg, _ = self._reg()
        with self.assertRaises(RegistryError):
            reg.add("x", "music", "http://127.0.0.1:1/")

    def test_duplicate_rejected(self):
        from mem20greenz.store import RegistryError
        reg, _ = self._reg()
        reg.add("demo", "website", "http://127.0.0.1:1/")
        with self.assertRaises(RegistryError):
            reg.add("demo", "website", "http://127.0.0.1:1/")

    def test_advance_is_sequential(self):
        from mem20greenz.store import RegistryError
        reg, _ = self._reg()
        reg.add("demo", "website", "http://127.0.0.1:1/")
        with self.assertRaises(RegistryError):
            reg.advance("demo", "verified")
        self.assertEqual(reg.advance("demo", "captured")["status"],
                         "captured")
        self.assertEqual(reg.drop("demo")["status"], "dropped")
        with self.assertRaises(RegistryError):
            reg.advance("demo", "promoted")


class TestMirror(unittest.TestCase):
    @staticmethod
    def _server(root):
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=str(root), **k)

            def log_message(self, *a):
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd

    def test_mirror_stays_on_origin(self):
        from mem20greenz.mirror import mirror
        with tempfile.TemporaryDirectory(prefix="greenz-www-") as www:
            (Path(www) / "index.html").write_text(
                '<a href="/page2.html">two</a>'
                '<a href="https://example.invalid/x">off</a>',
                encoding="utf-8")
            (Path(www) / "page2.html").write_text("second", encoding="utf-8")
            httpd = self._server(www)
            try:
                base = f"http://127.0.0.1:{httpd.server_address[1]}"
                with tempfile.TemporaryDirectory(prefix="greenz-out-") as out:
                    manifest = mirror(base + "/", out, max_pages=10)
            finally:
                httpd.shutdown()
                httpd.server_close()
        self.assertEqual(manifest["pages"], 2)
        urls = [f["url"] for f in manifest["files"]]
        self.assertTrue(all("example.invalid" not in u for u in urls))
        self.assertTrue(any(u.endswith("/page2.html") for u in urls))


class TestRepo(unittest.TestCase):
    def test_clone_local_repo(self):
        from mem20greenz.repo import clone_repo
        with tempfile.TemporaryDirectory(prefix="greenz-src-") as src:
            env = dict(os.environ, GIT_AUTHOR_NAME="t",
                       GIT_AUTHOR_EMAIL="t@t",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
            subprocess.run(["git", "init", "-q", src], check=True, env=env,
                           timeout=30)
            (Path(src) / "hello.txt").write_text("hi", encoding="utf-8")
            subprocess.run(["git", "-C", src, "add", "."],
                           check=True, env=env, timeout=30)
            subprocess.run(["git", "-C", src, "commit", "-qm", "seed"],
                           check=True, env=env, timeout=30)
            with tempfile.TemporaryDirectory(prefix="greenz-dst-") as dst:
                report = clone_repo(f"file://{src}", Path(dst) / "clone")
        self.assertGreaterEqual(report["files"], 1)
        self.assertIn("file://", report["source"])

    def test_clone_refuses_nonempty(self):
        from mem20greenz.repo import CloneError
        from mem20greenz.repo import clone_repo
        with tempfile.TemporaryDirectory(prefix="greenz-dst-") as dst:
            (Path(dst) / "taken.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(CloneError):
                clone_repo("file:///nonexistent", dst)


class TestBaseline(unittest.TestCase):
    def test_writes_split_doc(self):
        from mem20greenz.baseline import write_baseline
        with tempfile.TemporaryDirectory(prefix="greenz-base-") as out:
            path = write_baseline(out, name="demo",
                                  source="http://127.0.0.1:1/",
                                  keeps="chat rooms", changes="our theme",
                                  run_steps="run it")
            text = Path(path).read_text(encoding="utf-8")
        self.assertIn("What we keep", text)
        self.assertIn("chat rooms", text)
        self.assertIn("our theme", text)

    def test_empty_sections_rejected(self):
        from mem20greenz.baseline import write_baseline
        with tempfile.TemporaryDirectory(prefix="greenz-base-") as out:
            with self.assertRaises(ValueError):
                write_baseline(out, name="demo", source="s", keeps=" ",
                               changes="c", run_steps="r")


class TestCli(unittest.TestCase):
    def _env(self):
        tmp = tempfile.mkdtemp(prefix="greenz-home-")
        return {"MEM20GREENZ_HOME": tmp}, tmp

    def test_version(self):
        from mem20greenz import cli
        self.assertEqual(cli.main(["--version"]), 0)

    def test_full_lifecycle_offline(self):
        from mem20greenz import cli
        env, home = self._env()
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(cli.main(
                ["add", "t1", "--kind", "software",
                 "--source", "file:///nonexistent"]), 0)
            self.assertEqual(cli.main(["status", "t1"]), 0)
            self.assertEqual(cli.main(["list"]), 0)
            # capture fails honestly (bad source), status stays staged
            self.assertEqual(cli.main(["capture", "t1"]), 1)
            # illegal jump is refused, not faked
            self.assertEqual(cli.main(["promote", "t1"]), 2)
            self.assertEqual(cli.main(["drop", "t1"]), 0)
            self.assertEqual(cli.main(["promote", "t1"]), 2)


if __name__ == "__main__":
    unittest.main()
