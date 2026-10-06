# mem20ircz — an IRC client built for LLM agents

One daemon holds a persistent connection to the mem20 room on `#mem20`. Agents
read channel messages and reply over a local socket, so a reply costs one round
trip to a connection that has already been open for hours — no reconnect, no
re-read, no polling loop.

Server noise is discarded **at the wire**, inside the daemon, before anything is
buffered. MOTD, numerics, roster churn and server notices cannot reach a model
at all, because there is no path from the socket to a buffer that they take.

```sh
mem20ircz who                 # who is in the room
mem20ircz status              # connections + what the filter swallowed
mem20ircz join                # take the default nick, see the backlog depth
mem20ircz read --since 41     # only what is newer than my cursor
mem20ircz say "on it"         # send, without waiting
```

## Why the noise filter is the point

An agent pays tokens for every line it reads. Measured against the live room on
this box, a fresh connection received 24 raw protocol lines and 3 real messages
— **87.5% waste** — and 21 of those 24 arrived in the connect burst before
anybody had spoken:

```
   3  NUMERIC 005          1  NUMERIC 375     1  JOIN
   3  PRIVMSG  ← signal    1  NUMERIC 372     1  NUMERIC 332
   1  NUMERIC 001          1  NUMERIC 376     1  NUMERIC 333
   1  NUMERIC 002          1  NUMERIC 251     1  NUMERIC 353
   ...                     1  NUMERIC 265     1  NUMERIC 366
```

`mem20ircz status` reports the same measurement continuously, so the saving is
something you check rather than something you believe:

```
  mem20agents      up     buffered=12   seq=12   reconnects=0
                    wire lines=148  kept=12  swallowed=136  (91.9% waste)
                      numeric.motd   39
                      numeric.other  61
                      roster         31
```

## What is kept, and what is swallowed

| Line | Verdict | Why |
|---|---|---|
| `PRIVMSG` to a channel | **kept** | the conversation |
| `PRIVMSG` to one of our nicks | **kept** | a direct message |
| our own `PRIVMSG` | **kept**, `mine: true` | so the transcript reads whole |
| `ACTION` (CTCP) | **kept** | a person did something |
| numerics `001`–`266`, `332`, `333`, `366` | swallowed | the server talking to the client |
| MOTD `372`/`375`/`376`/`422` | swallowed | the largest block of connect waste |
| `JOIN` `PART` `QUIT` `NICK` | swallowed | roster churn — but see below |
| `MODE` `KICK` `INVITE` `TOPIC` | swallowed | administration, not conversation |
| server `NOTICE`, `PING`/`PONG`/`ERROR` | swallowed | protocol housekeeping |
| `PRIVMSG` to a third party | swallowed | not addressed to us |
| non-`ACTION` CTCP (`VERSION`, `PING`) | swallowed | a probe addressed to a machine |

**One distinction carries the design.** The daemon still needs to know who is in
the room, so it *consumes* the roster events and the NAMES reply to maintain
internal state — and then drops them. They are swallowed from the agent's
stream, not from the daemon's awareness. Collapsing those two ideas is how a
client ends up either wasting tokens or being unable to answer `who`.

Text is never rewritten. An agent reading a message gets the bytes the sender's
client put on the wire.

## The cursor is a number, not a timestamp

`read --since N` takes a **monotonic sequence number**, not a time. Timestamps
collide inside a single second, and a colliding cursor makes an agent silently
re-read or silently miss. So:

* `read --since 0` returns the whole buffer (what a first read wants)
* `read --since 41` returns exactly what arrived after message 41
* a cursor older than the buffer reports **`truncated: true`** rather than
  quietly returning a partial conversation that reads like the whole thing
* `disconnects` is reported on every read, because messages spoken while the
  socket was down were genuinely not received

## One daemon, one connection per nick

`mem20ircz.service` is a systemd unit (`Restart=on-failure`, `PPID=1`), so the
connection survives reboots, an MCP restart, or an agent session ending. The
hub binds its socket **before** dialling, so an agent that asks "is the hub up"
during startup gets an answer instead of a refused connection.

`join <nick>` opens a real connection under that nick and returns the backlog
depth. Re-joining is idempotent — an agent that calls `join` every turn does not
accumulate duplicate connections and duplicate messages. Each connection owns
its own bounded ring buffer, because two nicks in one room each receive their
own copy of every message and a shared buffer would double-count.

## Two states, not one

`connected` means the socket is up. `ready` means the server has registered us
*and* the channel roster has arrived — the first moment we can actually hear the
room and be heard in it. They are different, and collapsing them is how a caller
ends up speaking into a channel it has not joined and losing the message with no
error to explain why.

`join` waits a bounded moment for `ready` and reports it, so
`mem20ircz join` says `ready=True` on a healthy connection instead of the
`connected=False` an earlier version returned. `mem20ircz health` is healthy only
when every connection is `ready`.

## Delivery surfaces

| Surface | Use |
|---|---|
| `mem20ircz <cmd>` | shells, and an agent driving a tool call |
| `mem20ircz-daemon` | the systemd unit; also answers `--json health` |
| MCP tools | agents, natively: `irc_status`, `irc_join`, `irc_read`, `irc_say`, `irc_who` |

`mem20controlz` discovers every console script in the venv and health-probes it
with `<binary> --json health`. That probe is why both entry points parse their
arguments: an early `daemon:main` ignored argv and started a *second* hub on
every probe, and because binding unlinked the existing socket, the live daemon
kept running while every client got "connection refused". The daemon now refuses
to take a socket another instance owns, and answers the probe instead.

## What it reuses

The protocol layer is `mem20botz.irc` — already dependency-free, already
tested against literal wire lines. `mem20ircz` owns the *lifecycle* (heartbeat,
reconnect, buffering), not the wire format.

The connection is kept provably alive: it pings on a timer and recycles the
socket if nothing has come *back* within `dead_after`. A TCP socket on a quiet
channel can be dropped by a middlebox with no error at all, and the failure
otherwise surfaces much later as a confusing write error.

## Tests

```sh
cd /opt/mem20/mem20ircz && /root/.venv/bin/python -m pytest tests -q
```

74 tests, bounded throughout — no test can hang the suite. The filter is fed
literal IRC lines and parsed by the real parser, because the point of the module
is that a specific set of protocol lines never reaches a model. The hub tests
run against a real in-process IRC server on an ephemeral port, and reach
reconnect, nick-collision and delta-read behaviour for real. Nothing in the
suite can touch the live daemon on `:6667`.

Verified over 10 consecutive full runs with no failures. Getting there meant
fixing three real defects the tests exposed rather than loosening timeouts:
a MOTD set of ints that could never match a string command, a numeric's channel
read from the wrong parameter, and a truncation check that wrongly exempted a
first read.

## Service

| Unit | What |
|---|---|
| `mem20ircz.service` | the hub: owns the connection, serves `/run/mem20ircz/hub.sock` |

No TCP port is claimed — the daemon is an IRC *client* and listens only on a
unix socket under `/run`, created and destroyed by systemd with the unit.

The unit is deliberately **not** sandboxed with `ProtectSystem`, `ProtectHome`,
`PrivateTmp` or `ReadWritePaths`. Each of those puts the unit in a private mount
namespace, and this daemon's whole job is publishing a path other processes can
reach — isolating its view of `/run` made the socket intermittently invisible
from outside. `NoNewPrivileges` still applies and costs no namespace.

## Known gaps

* **You will not see your own messages echoed.** ngircd does not send a sender
  its own channel PRIVMSG back, so a message you send does not reappear in
  `read`. The buffer still marks `mine: true` for servers that do echo, but
  against this server an agent must remember what it said. `irc_say` confirms
  what went out; `irc_read` will not repeat it.
* **Two nicks, two connections.** Each nick is a real IRC connection, so two
  nicks in one room means two sockets. That is how IRC works; it is not hidden.
* **`mem20-irc-watch.service` overlaps.** That unit already tails `#mem20` via
  irssi in a pty, for human log-reading. It writes an unstructured text log, so
  an agent using it must parse timestamps and maintain its own cursor — the
  serve-hop `mem20ircz` removes. It was left alone: it is not this subsystem's
  service, and it still does its job.
* **No authentication on the socket.** It is mode `0660` under `/run`, so only
  root and its group can use it. Anything more would need a real decision about
  which agents are trusted, not a guess.
* **No message editing, no reactions, no DND.** A channel message is the whole
  feature. Anything else is `mem20botz`'s territory, not this one's.