"""The noise filter: what an agent pays for, and what it does not.

Fed literal wire lines, because the point of this module is that a specific set
of protocol lines never reaches a model. A test that builds Message objects by
hand would pass even if the real parser produced something else.
"""

from __future__ import annotations

from mem20botz.irc import parse_line

from mem20ircz.filter import NoiseMeter, apply_roster, classify


def v(line: str, my_nicks=("mem20agents",)):
    return classify(parse_line(line), my_nicks=my_nicks)


class TestKeepRealConversation:
    def test_channel_message_is_kept(self):
        verdict = v(":muse!u@h PRIVMSG #mem20 :step 18 is unblocked")
        assert verdict.keep
        assert verdict.reason == "channel"

    def test_direct_message_to_us_is_kept(self):
        verdict = v(":jayson!u@h PRIVMSG mem20agents :your turn")
        assert verdict.keep
        assert verdict.reason == "direct"

    def test_our_own_echo_is_kept(self):
        # Losing our own messages makes a conversation read as though the agent
        # never spoke, which is worse for an agent than a duplicated line.
        verdict = v(":mem20agents!u@h PRIVMSG #mem20 :on it")
        assert verdict.keep

    def test_ctcp_action_is_kept(self):
        verdict = v(":muse!u@h PRIVMSG #mem20 :\x01ACTION waves\x01")
        assert verdict.keep


class TestSwallowServerNoise:
    def test_motd_numerics_are_swallowed(self):
        for code in ("375", "372", "376", "422"):
            verdict = v(f":mem20.irc {code} mem20agents :motd text")
            assert not verdict.keep, f"numeric {code} must not reach an agent"
            assert verdict.reason == "numeric.motd"

    def test_registration_numerics_are_swallowed(self):
        for code in ("001", "002", "003", "004", "005", "251", "254", "255",
                     "265", "266"):
            verdict = v(f":mem20.irc {code} mem20agents :server info")
            assert not verdict.keep, f"numeric {code} must not reach an agent"

    def test_channel_metadata_numerics_are_swallowed(self):
        for code in ("332", "333", "366"):
            verdict = v(f":mem20.irc {code} mem20agents #mem20 :metadata")
            assert not verdict.keep

    def test_roster_events_are_swallowed(self):
        for line in (
            ":muse!u@h JOIN #mem20",
            ":muse!u@h PART #mem20 :bye",
            ":muse!u@h QUIT :ping timeout",
            ":muse!u@h NICK muser",
        ):
            verdict = v(line)
            assert not verdict.keep, f"{line} must not reach an agent"
            assert verdict.reason == "roster"

    def test_admin_and_protocol_are_swallowed(self):
        for line, reason in (
            (":mem20.irc MODE #mem20 +m", "admin"),
            (":op!u@h KICK #mem20 rude :out", "admin"),
            (":op!u@h TOPIC #mem20 :new topic", "admin"),
            (":mem20.irc NOTICE AUTH :*** Looking up your hostname", "notice"),
            ("PING :12345", "protocol"),
            (":mem20.irc ERROR :Closing link", "protocol"),
        ):
            verdict = v(line)
            assert not verdict.keep, f"{line} must not reach an agent"
            assert verdict.reason == reason

    def test_empty_message_is_swallowed(self):
        assert not v(":muse!u@h PRIVMSG #mem20 :   ").keep

    def test_ctcp_query_is_swallowed(self):
        # A client capability probe is addressed to a machine, not a person.
        assert not v(":muse!u@h PRIVMSG mem20agents :\x01VERSION\x01").keep

    def test_privmsg_to_someone_else_is_swallowed(self):
        verdict = v(":muse!u@h PRIVMSG kanban :not for you")
        assert not verdict.keep
        assert verdict.reason == "not-for-us"


class TestMeter:
    def test_meter_reports_the_saving_as_evidence(self):
        meter = NoiseMeter()
        lines = [
            ":mem20.irc 001 n :welcome",
            ":mem20.irc 375 n :- motd",
            ":mem20.irc 376 n :End of MOTD",
            ":muse!u@h JOIN #mem20",
            ":muse!u@h PRIVMSG #mem20 :real content",
        ]
        for line in lines:
            meter.record(v(line))
        report = meter.report()
        assert report["lines_seen"] == 5
        assert report["kept"] == 1
        assert report["swallowed"] == 4
        assert report["waste_ratio"] == 0.8
        assert report["by_reason"]["numeric.motd"] == 2

    def test_meter_starts_empty(self):
        assert NoiseMeter().report()["lines_seen"] == 0


class TestRosterIsTrackedWithoutBeingForwarded:
    def test_names_reply_seeds_the_roster(self):
        rosters: dict = {}
        apply_roster(rosters, parse_line(
            ":mem20.irc 353 tester = #mem20 :muse @jayson +crewbot sdk"))
        assert rosters["#mem20"] == {"muse", "jayson", "crewbot", "sdk"}

    def test_join_adds_quit_removes(self):
        rosters: dict = {}
        apply_roster(rosters, parse_line(":muse!u@h JOIN #mem20"))
        assert "muse" in rosters["#mem20"]
        apply_roster(rosters, parse_line(":muse!u@h QUIT :bye"))
        assert "muse" not in rosters["#mem20"]

    def test_part_leaves_only_that_channel(self):
        rosters: dict = {"#a": {"muse"}, "#b": {"muse"}}
        apply_roster(rosters, parse_line(":muse!u@h PART #a"))
        assert rosters["#a"] == set()
        assert rosters["#b"] == {"muse"}

    def test_quit_clears_every_channel(self):
        rosters: dict = {"#a": {"muse"}, "#b": {"muse"}}
        apply_roster(rosters, parse_line(":muse!u@h QUIT :bye"))
        assert rosters["#a"] == set()
        assert rosters["#b"] == set()

    def test_nick_change_renames_in_every_channel(self):
        rosters: dict = {"#a": {"muse"}, "#b": {"muse"}}
        apply_roster(rosters, parse_line(":muse!u@h NICK muser"))
        assert rosters["#a"] == {"muser"}
        assert rosters["#b"] == {"muser"}

    def test_conversation_does_not_touch_the_roster(self):
        rosters: dict = {"#mem20": {"muse"}}
        apply_roster(rosters, parse_line(":muse!u@h PRIVMSG #mem20 :hi"))
        assert rosters["#mem20"] == {"muse"}