import asyncio
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP = os.path.join(REPO, "mcp")
if MCP not in sys.path:
    sys.path.insert(0, MCP)

import server


def call(handler, args):
    s = server.Mem20MCPServer()
    return asyncio.new_event_loop().run_until_complete(getattr(s, handler)(args))


def test_unlisted_actor_cannot_read_namespace():
    assert "✅" in call("_memory_namespace_create", {
        "namespace": "acl-read", "owner": "owner-a", "acl": {"reader": "read"},
    })
    assert "✅" in call("_memory_shared_store", {
        "namespace": "acl-read", "content": "quarterly numbers", "actor": "owner-a",
    })

    denied = call("_memory_shared_recall", {
        "namespace": "acl-read", "query": "quarterly", "actor": "random-unknown-agent",
    })
    assert denied.startswith("Access denied"), denied
    assert "quarterly numbers" not in denied


def test_unlisted_actor_cannot_write_namespace():
    call("_memory_namespace_create", {"namespace": "acl-write", "owner": "owner-b", "acl": {}})

    denied = call("_memory_shared_store", {
        "namespace": "acl-write", "content": "injected", "actor": "attacker",
    })
    assert denied.startswith("Access denied"), denied

    owner_view = call("_memory_shared_recall", {
        "namespace": "acl-write", "query": "injected", "actor": "owner-b",
    })
    assert "No memories found" in owner_view, owner_view


def test_acl_reader_can_read_but_not_write():
    call("_memory_namespace_create", {
        "namespace": "acl-roles", "owner": "owner-c", "acl": {"reader": "read", "writer": "write"},
    })
    call("_memory_shared_store", {
        "namespace": "acl-roles", "content": "launch plan", "actor": "writer",
    })

    read_ok = call("_memory_shared_recall", {
        "namespace": "acl-roles", "query": "launch", "actor": "reader",
    })
    assert "launch plan" in read_ok, read_ok

    write_denied = call("_memory_shared_store", {
        "namespace": "acl-roles", "content": "reader should not write", "actor": "reader",
    })
    assert write_denied.startswith("Access denied"), write_denied


def test_unknown_namespace_is_denied_fail_closed():
    missing = call("_memory_shared_recall", {
        "namespace": "never-created", "query": "anything", "actor": "owner-a",
    })
    assert missing.startswith("Access denied"), missing
    assert "does not exist" in missing, missing

    store_missing = call("_memory_shared_store", {
        "namespace": "never-created", "content": "sneaky", "actor": "owner-a",
    })
    assert store_missing.startswith("Access denied"), store_missing


def test_prefix_namespace_does_not_leak():
    call("_memory_namespace_create", {
        "namespace": "team-1", "owner": "owner-d", "acl": {},
    })
    call("_memory_shared_store", {
        "namespace": "team-1", "content": "team one secret", "actor": "owner-d",
    })

    leaked = call("_memory_shared_recall", {
        "namespace": "team-10", "query": "secret", "actor": "owner-d",
    })
    assert "team one secret" not in leaked, leaked

    other_actor = call("_memory_shared_recall", {
        "namespace": "team-1", "query": "secret", "actor": "owner-e",
    })
    assert other_actor.startswith("Access denied"), other_actor


def test_namespace_recreation_requires_admin():
    call("_memory_namespace_create", {
        "namespace": "acl-admin", "owner": "owner-f", "acl": {},
    })

    hijack = call("_memory_namespace_create", {
        "namespace": "acl-admin", "owner": "attacker", "acl": {"attacker": "admin"}, "actor": "attacker",
    })
    assert hijack.startswith("Access denied"), hijack

    by_owner = call("_memory_namespace_create", {
        "namespace": "acl-admin", "owner": "owner-f", "acl": {"helper": "write"}, "actor": "owner-f",
    })
    assert "✅" in by_owner, by_owner

    helper_write = call("_memory_shared_store", {
        "namespace": "acl-admin", "content": "helper wrote", "actor": "helper",
    })
    assert "✅" in helper_write, helper_write


def test_acl_must_be_object():
    bad = call("_memory_namespace_create", {
        "namespace": "acl-bad", "owner": "owner-g", "acl": "not-a-dict",
    })
    assert bad.startswith("Error:"), bad


def test_wildcard_acl_grants_everyone_read():
    call("_memory_namespace_create", {
        "namespace": "acl-open", "owner": "owner-h", "acl": {"*": "read"},
    })
    call("_memory_shared_store", {
        "namespace": "acl-open", "content": "public note", "actor": "owner-h",
    })
    anyone = call("_memory_shared_recall", {
        "namespace": "acl-open", "query": "public", "actor": "literally-anyone",
    })
    assert "public note" in anyone, anyone


def test_legacy_metadata_still_enforced():
    from memory import remember

    remember(
        topic="namespace_meta",
        content="Namespace: legacy-ns, Owner: legacy-owner, ACL: {'legacy-reader': 'read'}",
        tags=["namespace", "metadata", "legacy-ns"],
        priority="high",
    )
    call("_memory_shared_store", {
        "namespace": "legacy-ns", "content": "legacy content", "actor": "legacy-owner",
    })

    allowed = call("_memory_shared_recall", {
        "namespace": "legacy-ns", "query": "legacy", "actor": "legacy-reader",
    })
    assert "legacy content" in allowed, allowed

    denied = call("_memory_shared_recall", {
        "namespace": "legacy-ns", "query": "legacy", "actor": "stranger",
    })
    assert denied.startswith("Access denied"), denied


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
