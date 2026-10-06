"""mem20ircz — an agent-side IRC client for the mem20 room.

One daemon owns a persistent IRC connection. Agents read channel messages and
reply over a local socket, so a reply costs one round trip to a socket that has
already been open for hours instead of a fresh connect and a re-read.

Server noise is discarded at the wire, inside the daemon, before anything is
buffered — so MOTD, numerics and roster churn cannot reach a model at all.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]