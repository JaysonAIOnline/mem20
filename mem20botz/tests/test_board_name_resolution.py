"""Guard board-name resolution against truncation at the first space.

The real defect: ``_board()`` did ``shlex.split(args)`` and returned
``parts[0]``. Every board on this box whose name contains a space therefore
resolved to its first word — ``"Fleet HQ"`` became ``"Fleet"``, which does not
exist. ``DEFAULT_BOARD`` is ``"Fleet HQ"``, so the bare ``!jobs`` worked and
looked healthy while ``!jobs Fleet HQ``, ``!board Fleet HQ`` and the shell path
``mem20botz jobs "Fleet HQ"`` all failed with ``no board 'Fleet'``. This is the
same class of bug the bot's own README warns about: a hardcoded assumption that
only a live run against the real board finds.

The property worth protecting: a board name is resolved against the board names
the door actually reports, longest match first, so a name containing a space is
never silently truncated into a different, non-existent board.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20kanbanz import NotFound  # noqa: E402
from mem20botz.kanban_bot import DEFAULT_BOARD, KanbanBot  # noqa: E402


class FakeBoard:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDoor:
    """Minimal stand-in for the door's board-name surface."""

    def __init__(self, names: list[str]) -> None:
        self._names = names
        self.base = "http://127.0.0.1:8221"

    def board_names(self) -> list[str]:
        return list(self._names)

    def board(self, name: str) -> FakeBoard:
        if name not in self._names:
            raise NotFound(f"no board {name!r}")
        return FakeBoard(name)


class TestBoardNameResolution(unittest.TestCase):
    def setUp(self) -> None:
        self.door = FakeDoor(["Fleet HQ", "dev", "pipelines"])
        self.bot = KanbanBot(door=self.door, board=DEFAULT_BOARD)  # type: ignore[arg-type]

    def test_a_board_name_with_a_space_is_not_truncated(self):
        """The defect: 'Fleet HQ' resolved to 'Fleet', which does not exist."""
        self.assertEqual(self.bot._board("Fleet HQ"), "Fleet HQ")

    def test_bare_call_still_falls_back_to_the_default_board(self):
        self.assertEqual(self.bot._board(""), DEFAULT_BOARD)

    def test_trailing_tokens_do_not_eat_the_board_name(self):
        self.assertEqual(self.bot._board("Fleet HQ extra"), "Fleet HQ")

    def test_quoted_name_resolves(self):
        self.assertEqual(self.bot._board('"Fleet HQ"'), "Fleet HQ")

    def test_single_word_board_is_unchanged(self):
        self.assertEqual(self.bot._board("dev"), "dev")

    def test_longest_known_name_wins_over_a_prefix(self):
        """'Fleet HQ' and 'Fleet' both known must not resolve to 'Fleet'."""
        door = FakeDoor(["Fleet", "Fleet HQ"])
        bot = KanbanBot(door=door, board=DEFAULT_BOARD)  # type: ignore[arg-type]
        self.assertEqual(bot._board("Fleet HQ"), "Fleet HQ")

    def test_unknown_name_is_passed_through_for_a_real_error(self):
        """An unknown board must still surface as an error, not silently default."""
        self.assertEqual(self.bot._board("nosuchboard"), "nosuchboard")

    def test_board_or_error_accepts_a_spaced_name(self):
        name, err = self.bot._board_or_error("Fleet HQ")
        self.assertIsNone(err)
        self.assertEqual(name, "Fleet HQ")

    def test_board_or_error_still_errors_on_a_genuinely_unknown_board(self):
        name, err = self.bot._board_or_error("nope")
        self.assertEqual(name, "")
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("no board", err)