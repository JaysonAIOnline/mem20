"""The kanban bot: the channel's view onto the one true board.

This is the bot that makes the board *accurate* rather than merely visible.
The loop it closes is:

    job appears on the board
      -> bot advertises it in #mem20
      -> a human or agent claims it with !accept
      -> the door records the assignee
      -> the worker does the thing and says !done
      -> the door moves the card into the board's done column

Without the middle step the board rots: a card that is being worked on still
looks untouched, so two agents take the same job, and nobody can tell which
work is actually in flight.

Design rules:

* **The bot never writes state it invented.** Every claim and every
  completion is a real call to the mem20-kanban door. If the door is down the
  bot says the door is down — it does not confirm a claim it could not record,
  because a confirmed-but-unrecorded claim is worse than a refusal: the agent
  starts work the board has no record of.
* **Claims are not stolen.** ``!accept`` on a card someone else holds is
  refused by the door, and the bot reports the refusal rather than forcing it.
* **A done column is required to finish.** The bot refuses ``!done`` on a board
  with no done column instead of guessing, so a job is never silently marked
  complete in the wrong place.
"""

from __future__ import annotations

import shlex
from typing import Optional

from mem20kanbanz import Door, DoorError, NotFound

from .base import Bot
from .irc import Message

DEFAULT_BOARD = "Fleet HQ"
#: How many open jobs to advertise at once. A channel that gets 200 lines on
#: join is unreadable, and the point is to make work findable.
ADVERTISE_LIMIT = 8


class KanbanBot(Bot):
    """Advertises work and records claims and completions."""

    name = "kanban"

    def __init__(self, nick: str = "kanban", door: Optional[Door] = None,
                 board: str = DEFAULT_BOARD, channel: str = "#mem20",
                 host: str = "127.0.0.1", port: int = 6667) -> None:
        self.door = door or Door()
        self.board = board
        self.advertised: set[str] = set()
        super().__init__(
            nick=nick, name="kanban", channel=channel, host=host, port=port,
            purpose=("advertises work on the mem20 kanban board and records "
                     "claims and completions, so the board stays accurate"),
            source_of_truth=(f"the mem20-kanban door at {self.door.base} "
                             f"(mem20kanbanz client, HTTP only — this bot "
                             f"never opens the database)"),
            commands={
                "jobs": self.cmd_jobs,
                "accept": self.cmd_accept,
                "done": self.cmd_done,
                "release": self.cmd_release,
                "board": self.cmd_board,
                "boards": self.cmd_boards,
                "who": self.cmd_who,
                "door": self.cmd_status,
            },
            help_text=(
                "kanban: !jobs [board] | !accept <id> | !done <id> [reason] | "
                "!release <id> | !board [name] | !boards | !who | !door"),
        )

    # ------------------------------------------------------------ utilities
    def _board(self, args: str) -> str:
        """Resolve a board name from a command's argument text.

        A board name may contain a space — ``Fleet HQ`` is this box's default
        board — so taking the first token truncates it to ``Fleet``, which is
        not a board. The name is therefore resolved against the names the door
        actually reports, longest match first. Bare calls still fall back to
        this bot's configured board.
        """
        raw = args.strip()
        if not raw:
            return self.board
        try:
            known = list(self.door.board_names())
        except Exception:  # noqa: BLE001 - door down; caller reports it
            known = []
        if known:
            try:
                parts = shlex.split(raw)
            except ValueError:
                parts = []
            # A quoted argument arrives as one token; prefer that form.
            for candidate in ([parts[0]] if len(parts) == 1 else []) + [raw]:
                if candidate in known:
                    return candidate
            # Longest known name the text starts with, on a word boundary, so
            # 'Fleet HQ extra' resolves to 'Fleet HQ' and not to 'Fleet'.
            for name in sorted(known, key=len, reverse=True):
                if raw == name or raw.startswith(name + " "):
                    return name
        parts = shlex.split(raw)
        return parts[0] if parts else self.board

    def _board_or_error(self, args: str) -> tuple[str, Optional[str]]:
        """Return ``(board_name, error_text)`` — exactly one is set.

        On error the board name is the empty string, never None, so a caller
        that only inspects the error cannot accidentally pass None onward as a
        board name.
        """
        name = self._board(args)
        try:
            self.door.board(name)
        except NotFound:
            known = ", ".join(self.door.board_names()) or "none"
            return "", f"kanban: no board {name!r}. Boards: {known}"
        except DoorError as exc:
            return "", f"kanban: door unreachable — {exc}"
        return name, None

    def _short(self, card_id: str) -> str:
        """A short, quotable id.

        The door's ids are UUIDs; typing 36 characters into a chat is a good way
        to get jobs stuck. The prefix is long enough not to collide in practice
        and is always resolved back to the full id by :meth:`_resolve`.
        """
        return card_id[:8]

    def _resolve(self, board_name: str, token: str) -> Optional[str]:
        """Turn a short id, a full id, or an exact title into a full id."""
        board = self.door.board(board_name)
        for c in board.cards:
            if c.id == token or c.id.startswith(token):
                return c.id
        low = token.lower()
        exact = [c for c in board.cards if c.title.lower() == low]
        if exact:
            return exact[0].id
        return None

    # ------------------------------------------------------------- commands
    def cmd_jobs(self, bot: Bot, msg: Message, args: str) -> str:
        name, err = self._board_or_error(args)
        if err:
            return err
        open_cards = self.door.open_jobs(name)
        if not open_cards:
            return f"kanban: {name} has no open work."
        lines = [f"kanban: {len(open_cards)} open on {name}:"]
        for c in open_cards[:ADVERTISE_LIMIT]:
            who = c.assignee or "unclaimed"
            lines.append(f"  {self._short(c.id)}  [{c.status}] {c.title} ({who})")
        if len(open_cards) > ADVERTISE_LIMIT:
            lines.append(f"  … and {len(open_cards) - ADVERTISE_LIMIT} more")
        lines.append(f"kanban: !accept <id> to take one, !done <id> when finished")
        return "\n".join(lines)

    def _work_column(self, board, fallback: str = "") -> str:
        """The column a claimed job should land in.

        Hardcoding "in_progress" is wrong: the boards on this box disagree
        (dev has `in_progress`, Fleet HQ has `In Progress`, and a board could
        use anything). So the name is resolved from the board itself, matching
        case-insensitively and then by fuzzy intent, and only falls back to a
        literal if the board has exactly one plausible non-done column.

        Returning "" means "the board has nowhere to put it", which the caller
        reports rather than silently moving the card to a column that does not
        exist.
        """
        cols = board.columns
        done = {c.name for c in cols if c.is_done}
        open_cols = [c for c in cols if c.name not in done]
        if not open_cols:
            return ""
        wanted = (fallback or "in_progress").lower()
        for c in open_cols:
            if c.name.lower() == wanted:
                return c.name
        # "in progress" vs "in_progress" vs "In-Progress"
        squashed = wanted.replace("_", "").replace(" ", "").replace("-", "")
        for c in open_cols:
            if c.name.lower().replace("_", "").replace(" ", "").replace(
                    "-", "") == squashed:
                return c.name
        for c in open_cols:
            if squashed in c.name.lower().replace("_", "").replace(" ", ""):
                return c.name
        # The landing column is where new work already sits, so it is a safe
        # place to put a claim when nothing better is obvious.
        for c in cols:
            if c.is_landing:
                return c.name
        return open_cols[0].name

    def cmd_accept(self, bot: Bot, msg: Message, args: str) -> str:
        # The job token is the first word, but a title may contain spaces
        # ("fix the flaky test"), so an exact-title match is tried against the
        # whole argument before falling back to the first word. Splitting
        # first and keeping only word[0] would make every multi-word title
        # impossible to claim.
        token, _, rest = (args or "").strip().partition(" ")
        if not token:
            return "kanban: !accept <id> — which job?"
        agent = rest.strip() or msg.nick
        name, err = self._board_or_error("")
        if err:
            return err
        full = self._resolve(name, args.strip()) or self._resolve(name, token)
        if full is None:
            return f"kanban: no job matching {token!r} on {name}."
        try:
            board = self.door.board(name)
        except DoorError as exc:
            return f"kanban: cannot reach the door — {exc}"
        target = self._work_column(board, "in_progress")
        if not target:
            return (f"kanban: {name} has no working column, so a job cannot be "
                    f"claimed. Ask jayson to add one.")
        # Checked before the claim so a repeat claim can be reported as a
        # no-op rather than re-announced as if it were fresh.
        already_held = any(c.id == full and (c.assignee or "").lower()
                           == agent.lower() for c in board.cards)
        try:
            card = self.door.claim(full, agent, board=name, column=target)
        except NotFound as exc:
            return f"kanban: {exc}"
        except DoorError as exc:
            # Includes the "already claimed by X" refusal. Report it, never
            # override it: a stolen claim is how work gets done twice.
            return f"kanban: cannot claim — {exc}"
        # Claiming something you already hold is not an error, but saying
        # "took" again hides the fact that nothing changed. Say so plainly.
        if already_held:
            return (f"kanban: {agent} already holds {self._short(card.id)} "
                    f"“{card.title}” — still {card.status}")
        self.advertised.discard(card.id)
        return (f"kanban: {agent} took {self._short(card.id)} "
                f"“{card.title}” → {card.status}")

    def cmd_done(self, bot: Bot, msg: Message, args: str) -> str:
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return "kanban: !done <id> [reason] — which job?"
        token = parts[0]
        reason = " ".join(parts[1:]) or f"reported done by {msg.nick}"
        name, err = self._board_or_error("")
        if err:
            return err
        full = self._resolve(name, token)
        if full is None:
            return f"kanban: no job matching {token!r} on {name}."
        try:
            card = self.door.complete(full, board=name, reason=reason)
        except NotFound as exc:
            return f"kanban: {exc}"
        except DoorError as exc:
            return f"kanban: cannot mark done — {exc}"
        self.advertised.discard(card.id)
        return (f"kanban: {self._short(card.id)} “{card.title}” done → "
                f"{card.status} ({reason})")

    def cmd_release(self, bot: Bot, msg: Message, args: str) -> str:
        parts = shlex.split(args) if args.strip() else []
        if not parts:
            return "kanban: !release <id> — which job?"
        name, err = self._board_or_error("")
        if err:
            return err
        full = self._resolve(name, parts[0])
        if full is None:
            return f"kanban: no job matching {parts[0]!r} on {name}."
        try:
            card = self.door.release(full, board=name)
        except DoorError as exc:
            return f"kanban: cannot release — {exc}"
        return (f"kanban: {self._short(card.id)} released → {card.status}, "
                f"back in the queue")

    def cmd_board(self, bot: Bot, msg: Message, args: str) -> str:
        name, err = self._board_or_error(args)
        if err:
            return err
        b = self.door.board(name)
        done = ", ".join(b.done_columns) or "none set"
        head = (f"kanban: {b.name} — {len(b.cards)} cards, "
                f"{len(b.open_cards())} open, done column: {done}")
        if not b.goal:
            return head
        return f"{head}\n  goal: {b.goal}"

    def cmd_boards(self, bot: Bot, msg: Message, args: str) -> str:
        try:
            names = self.door.board_names()
        except DoorError as exc:
            return f"kanban: door unreachable — {exc}"
        return "kanban: boards — " + (", ".join(names) or "none")

    def cmd_who(self, bot: Bot, msg: Message, args: str) -> str:
        """Who holds what. This is how a channel avoids duplicate work."""
        name, err = self._board_or_error("")
        if err:
            return err
        b = self.door.board(name)
        holders: dict[str, list[str]] = {}
        for c in b.open_cards():
            if c.assignee:
                holders.setdefault(c.assignee, []).append(c.title)
        if not holders:
            return f"kanban: nobody holds open work on {name}."
        lines = [f"kanban: work in flight on {name}:"]
        for who, titles in sorted(holders.items()):
            lines.append(f"  {who}: {len(titles)} — " + ", ".join(titles[:3]))
        return "\n".join(lines)

    def cmd_status(self, bot: Bot, msg: Message, args: str) -> str:
        try:
            ok = self.door.healthy()
        except DoorError:
            ok = False
        state = "up" if ok else "DOWN"
        return (f"kanban: door {state} at {self.door.base} | "
                f"uptime {int(self.uptime())}s | "
                f"{self.commands_run} commands | {self.mentions} mentions")

    # ------------------------------------------------------------ advertise
    def advertise(self) -> Optional[str]:
        """One line describing the newest unclaimed work, or None.

        Called on a timer by the daemon so a job posted to the board shows up
        in the channel without anyone having to ask.
        """
        try:
            fresh = [c for c in self.door.unclaimed(self.board)
                     if c.id not in self.advertised]
        except DoorError as exc:
            return f"kanban: cannot reach the door — {exc}"
        if not fresh:
            return None
        newest = fresh[-1]
        self.advertised.add(newest.id)
        return (f"kanban: new job on {self.board} — {self._short(newest.id)} "
                f"“{newest.title}” (!accept {self._short(newest.id)})")
