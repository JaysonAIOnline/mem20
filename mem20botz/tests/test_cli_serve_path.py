"""Guard the serve path in main().

A function-local ``from .crew import Crew`` inside the ``bots`` branch made
``Crew`` local to all of ``main()``, so ``serve`` died with UnboundLocalError
and the unit crash-looped. No existing test called ``main()``, so 128 green
tests sat alongside a service that could not start.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20botz import cli


class TestServePathIsCallable(unittest.TestCase):
    def test_crew_is_not_shadowed_by_a_function_local_import(self):
        """The real defect: a local import binding the name for all of main()."""
        import ast

        tree = ast.parse(Path(cli.__file__).read_text())
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        locals_bound = set()
        for node in ast.walk(main):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    locals_bound.add(alias.asname or alias.name.split(".")[0])
        self.assertNotIn("Crew", locals_bound,
                         "a local `from .crew import Crew` shadows the "
                         "module-level import for the whole of main()")

    def test_bots_listing_reports_nine(self):
        """The crew grew; a hand-maintained list drifted and reported four."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        argv = ["mem20botz", "bots"]
        old = sys.argv
        sys.argv = argv
        try:
            with redirect_stdout(buf):
                cli.main()
        finally:
            sys.argv = old
        out = buf.getvalue()
        for nick in ("kanban", "agentz", "crewbot", "orca", "graph",
                     "swarm", "adk", "sdk", "relay"):
            self.assertIn(f"{nick} ({nick})", out, nick)


if __name__ == "__main__":
    unittest.main()