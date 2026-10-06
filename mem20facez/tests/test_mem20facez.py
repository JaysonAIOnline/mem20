"""Hermetic tests for the mem20facez skeleton slice."""

from __future__ import annotations

import unittest


class TestBranding(unittest.TestCase):
    def test_version_present(self):
        import mem20facez as pkg
        self.assertTrue(pkg.__version__)
        self.assertIsInstance(pkg.__version__, str)

    def test_members_registry(self):
        import mem20facez as pkg
        self.assertTrue(pkg.MEMBERS)
        self.assertEqual(len(pkg.MEMBERS), 8)
        self.assertIn("mem20adaptiveinterfacecomposerz", pkg.MEMBERS)


class TestCli(unittest.TestCase):
    def test_version_flag(self):
        from mem20facez import cli
        self.assertEqual(cli.main(["--version"]), 0)

    def test_members_flag(self):
        from mem20facez import cli
        self.assertEqual(cli.main(["--members"]), 0)


if __name__ == "__main__":
    unittest.main()
