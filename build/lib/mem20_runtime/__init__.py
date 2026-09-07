"""Packaging-only package.

Holds the bundled mem20 MCP server directory (``mcp/``) as package data so the
console-script launcher can locate and run it. This package must NOT reuse the
name ``mcp`` (that would shadow the ``mcp`` SDK).
"""
