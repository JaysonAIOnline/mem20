"""The hub against a real socket: does the noise actually stay out?

These tests point a real Connection at a real in-process IRC server. The claim
under test is not "the filter classifies things correctly" -- that is
test_filter's job -- it is "the connect burst never reaches a buffer, and a
delta read returns exactly what is new".
"""

from __future__ import annotations

import time

import pytest

from mem20ircz.hub import Connection, Hub, RingBuffer


def wait_until(predicate, timeout=6.0, interval=0.02):
    """Bounded wait. Returns whether it became true; never hangs the suite."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestRingBuffer:
    def test_sequence_numbers_are_monotonic(self):
        buf = RingBuffer(10)
        for i in range(3):
            buf.append(ts=0.0, nick="muse", target="#c", text=f"m{i}")
        assert [m["seq"] for m in buf.since(0)[0]] == [1, 2, 3]

    def test_since_returns_only_what_is_new(self):
        buf = RingBuffer(10)
        for i in range(3):
            buf.append(ts=0.0, nick="muse", target="#c", text=f"m{i}")
        msgs, truncated, latest = buf.since(2)
        assert [m["text"] for m in msgs] == ["m2"]
        assert not truncated
        assert latest == 3

    def test_cursor_at_head_returns_nothing(self):
        buf = RingBuffer(10)
        buf.append(ts=0.0, nick="muse", target="#c", text="only")
        msgs, _truncated, _latest = buf.since(1)
        assert msgs == []

    def test_truncation_is_reported_not_hidden(self):
        # A cursor older than the buffer means messages were lost. Returning a
        # partial set without saying so would read like the whole conversation.
        buf = RingBuffer(3)
        for i in range(10):
            buf.append(ts=0.0, nick="muse", target="#c", text=f"m{i}")
        msgs, truncated, _latest = buf.since(0)
        assert truncated is True
        assert len(msgs) == 3

    def test_fresh_cursor_is_not_flagged_truncated(self):
        buf = RingBuffer(3)
        for i in range(10):
            buf.append(ts=0.0, nick="muse", target="#c", text=f"m{i}")
        _msgs, truncated, _latest = buf.since(9)
        assert truncated is False

    def test_buffer_is_bounded(self):
        buf = RingBuffer(5)
        for i in range(50):
            buf.append(ts=0.0, nick="muse", target="#c", text=str(i))
        assert buf.latest_seq == 50
        assert len(buf.since(0)[0]) == 5


class TestConnectBurstIsSwallowed:
    def test_no_numerics_reach_the_buffer(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",), buffer_size=100)
        try:
            conn.start()
            assert wait_until(lambda: ircd.motd_sent.is_set())
            # Give the burst time to be read and judged.
            assert wait_until(lambda: conn.meter.swallowed >= 13)
            msgs, _t, _l = conn.buffer.since(0)
            assert msgs == [], f"MOTD leaked into the buffer: {msgs}"
        finally:
            conn.stop()

    def test_meter_shows_the_saving(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: conn.meter.swallowed >= 13)
            report = conn.meter.report()
            assert report["kept"] == 0
            assert report["swallowed"] >= 13
            assert report["waste_ratio"] == 1.0
            assert "numeric.motd" in report["by_reason"]
        finally:
            conn.stop()


class TestConversationReachesTheAgent:
    def test_real_message_is_buffered(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: ircd.motd_sent.is_set())
            ircd.say("muse", "#test", "step 18 is unblocked")
            assert wait_until(lambda: conn.buffer.latest_seq >= 1)
            msgs, _t, _l = conn.buffer.since(0)
            assert len(msgs) == 1
            assert msgs[0]["nick"] == "muse"
            assert msgs[0]["text"] == "step 18 is unblocked"
            assert msgs[0]["mine"] is False
        finally:
            conn.stop()

    def test_delta_read_returns_only_new_messages(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: ircd.motd_sent.is_set())
            ircd.say("muse", "#test", "first")
            assert wait_until(lambda: conn.buffer.latest_seq == 1)

            ircd.say("muse", "#test", "second")
            assert wait_until(lambda: conn.buffer.latest_seq == 2)

            first_pass, _t, _l = conn.buffer.since(0)
            assert [m["text"] for m in first_pass] == ["first", "second"]
            # The second read from the same cursor is the whole point: no
            # re-read of what the agent already saw.
            second_pass, _t, _l = conn.buffer.since(2)
            assert second_pass == []
        finally:
            conn.stop()

    def test_our_own_message_is_marked_as_mine(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: conn.ready.is_set())
            ircd.say("tester", "#test", "on it")
            assert wait_until(lambda: conn.buffer.latest_seq >= 1)
            msgs, _t, _l = conn.buffer.since(0)
            assert msgs[0]["mine"] is True
        finally:
            conn.stop()


class TestSending:
    def test_say_puts_a_privmsg_on_the_wire(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: conn.ready.is_set())
            conn.say("hello room")
            assert ircd.wait_for(
                lambda lines: any(l.startswith("PRIVMSG #test :hello room")
                                  for l in lines))
        finally:
            conn.stop()

    def test_say_without_a_connection_is_refused(self):
        from mem20botz.irc import IRCError
        conn = Connection(host="127.0.0.1", port=1, nick="tester",
                          channels=("#test",))
        # Never started, so there is no socket to write to. The point is that it
        # refuses loudly rather than pretending the message went out.
        with pytest.raises(IRCError):
            conn.say("nobody is listening")


class TestRoster:
    def test_who_reflects_the_names_reply(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            # Wait for the specific condition under test. Waiting merely for a
            # non-empty roster races the JOIN that arrives before the NAMES
            # reply, and fails intermittently under load.
            assert wait_until(lambda: "someone" in conn.who())
            nicks = conn.who()
            assert "someone" in nicks
            assert "fakeirc" in nicks
        finally:
            conn.stop()

    def test_who_tracks_a_newcomer(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",))
        try:
            conn.start()
            assert wait_until(lambda: conn.who())
            ircd.broadcast(":newcomer!u@h JOIN #test")
            assert wait_until(lambda: "newcomer" in conn.who())
        finally:
            conn.stop()


class TestHub:
    def test_join_is_idempotent(self, ircd):
        hub = Hub(host="127.0.0.1", port=ircd.port, channels=("#test",),
                  default_nick="tester")
        try:
            first = hub.join("tester")
            second = hub.join("tester")
            # Re-joining must not stack up duplicate connections, or an agent
            # that calls join every turn would receive every message twice.
            assert first is second
            assert len(hub.connections) == 1
        finally:
            hub.stop()

    def test_read_reports_connection_state(self, ircd):
        hub = Hub(host="127.0.0.1", port=ircd.port, channels=("#test",),
                  default_nick="tester")
        try:
            hub.join("tester")
            assert wait_until(lambda: hub.read(nick="tester")["connected"])
            result = hub.read(since=0)
            assert result["connected"] is True
            assert result["truncated"] is False
            assert result["latest_seq"] == 0
        finally:
            hub.stop()

    def test_each_nick_gets_its_own_buffer(self, ircd):
        hub = Hub(host="127.0.0.1", port=ircd.port, channels=("#test",),
                  default_nick="tester")
        try:
            hub.join("tester")
            hub.join("second")
            assert wait_until(lambda: all(c.ready.is_set()
                                          for c in hub.connections.values()))
            ircd.say("muse", "#test", "to both")
            assert wait_until(lambda: hub.read(nick="tester")["count"] == 1)
            assert wait_until(lambda: hub.read(nick="second")["count"] == 1)
            # One message, one copy per connection -- not double-counted into a
            # shared buffer.
            assert hub.read(nick="tester")["latest_seq"] == 1
        finally:
            hub.stop()


class TestResilience:
    def test_reconnects_after_the_server_drops_the_socket(self, ircd):
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",), reconnect_delay=0.1,
                          max_delay=0.3)
        try:
            conn.start()
            assert wait_until(lambda: conn.ready.is_set())
            before = ircd.accept_count
            # Drop every live socket the server holds, which is what "the
            # server dropped us" means. Closing one arbitrary entry is not:
            # clients[0] can be a long-dead socket from an earlier attempt.
            with ircd._clients_lock:
                live = list(ircd.clients)
            for sock in live:
                try:
                    sock.close()
                except OSError:
                    pass
            # The supervisor must notice and come back on its own, because an
            # agent is not going to be watching to reconnect for it.
            assert wait_until(
                lambda: ircd.accept_count > before and conn.ready.is_set(),
                timeout=15.0)
            assert conn.disconnects >= 1
        finally:
            conn.stop()

    def test_transient_nick_conflict_recovers(self, ircd):
        # After a restart the previous session's nick is often still held, so
        # the server answers the first attempt with 433. Treating that as fatal
        # wedged the daemon for good while looking perfectly healthy.
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",), reconnect_delay=0.1,
                          max_delay=0.2, nick_attempts=6)
        try:
            conn.start()
            assert wait_until(lambda: conn.ready.is_set())
            # Wait for server-side registration, not merely a live socket.
            # `connected` is set the moment NICK/USER are written, which can be
            # before the server's accept loop has the connection in its client
            # list -- and a broadcast to a client list that does not contain us
            # yet goes nowhere, which made this test fail intermittently.
            assert wait_until(lambda: ircd.motd_sent.is_set())
            before = ircd.accept_count
            ircd.broadcast(":fakeirc 433 * tester :Nickname is already in use")
            # The conflict is counted, not believed on the first answer.
            assert wait_until(lambda: conn.nick_conflicts >= 1)
            assert conn.fatal == ""
            # A genuinely new TCP connection, not the old session's flag still
            # being set -- that distinction is what makes this deterministic.
            assert wait_until(lambda: ircd.accept_count > before, timeout=12.0)
            assert wait_until(lambda: conn.connected.is_set(), timeout=12.0)
        finally:
            conn.stop()

    def test_persistent_nick_conflict_gives_up_eventually(self, ircd):
        # Bounded, not infinite: a genuinely taken nick must not be retried
        # forever, and the refusal has to say what happened. The server refuses
        # on *every* attempt here -- a one-off 433 is a transient conflict and is
        # covered by the test above.
        ircd.rejected_nicks.add("tester")
        conn = Connection(host="127.0.0.1", port=ircd.port, nick="tester",
                          channels=("#test",), reconnect_delay=0.05,
                          max_delay=0.1, nick_attempts=3)
        try:
            conn.start()
            assert wait_until(lambda: bool(conn.fatal), timeout=12.0)
            assert "tester" in conn.fatal
            assert conn.nick_conflicts >= 3
        finally:
            conn.stop()