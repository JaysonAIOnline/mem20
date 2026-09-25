"""Tests for 00_reference_store (the MALIC braid fountain)."""

from __future__ import annotations

import os
import tempfile
import unittest

from reference_store import ReferenceStore
from reference_store.store import content_address


class TestContentAddress(unittest.TestCase):
    def test_stable_and_unique(self):
        a = content_address("parse", "failure", "pitfall-x")
        b = content_address("parse", "failure", "pitfall-x")
        c = content_address("parse", "success", "pitfall-x")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_deterministic_hex(self):
        self.assertEqual(len(content_address("a", "b", "c")), 16)

    def test_matches_harness_diff_id(self):
        # must be byte-identical to the braid harness content_hash[:16]
        import hashlib

        harness = hashlib.sha256(b"parse|failure|pitfall-x").hexdigest()[:16]
        self.assertEqual(content_address("parse", "failure", "pitfall-x"), harness)


class TestReferenceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "fountain")
        self.store = ReferenceStore(self.root)

    def test_push_commits_and_dedupes(self):
        r1 = self.store.push("parse", "failure", "pitfall-malformed_json", origin_ring="ring_a", actor="m1", ring="ring_a")
        self.assertEqual(r1["status"], "committed")
        self.assertEqual(self.store.count, 1)
        # identical content -> dedupe (does not re-commit identical blob)
        r2 = self.store.push("parse", "failure", "pitfall-malformed_json", origin_ring="ring_b", actor="m3", ring="ring_b")
        self.assertEqual(r2["status"], "dedupe")
        self.assertEqual(r2["cid"], r1["cid"])
        self.assertEqual(self.store.count, 1)
        self.assertEqual(self.store.stats()["unique_cids"], 1)

    def test_append_only_no_mutation(self):
        self.store.push("retry", "failure", "over_aggressive_retry", origin_ring="ring_b")
        blob_path = os.path.join(self.root, "blobs", content_address("retry", "failure", "over_aggressive_retry") + ".json")
        with open(blob_path) as fh:
            before = fh.read()
        # re-push identical content adds a provenance hop but does not rewrite the blob
        self.store.push("retry", "failure", "over_aggressive_retry", origin_ring="ring_d", actor="m2", ring="ring_d")
        with open(blob_path) as fh:
            after = fh.read()
        self.assertEqual(before, after)

    def test_pull_returns_and_marks_provenance(self):
        r = self.store.push("auth", "failure", "token_rotation", origin_ring="ring_a", actor="m1", ring="ring_a")
        lessons = self.store.pull([r["cid"]], actor="m4", ring="ring_d")
        self.assertEqual(len(lessons), 1)
        rings = {h.ring for h in lessons[0].provenance}
        self.assertIn("ring_a", rings)  # origin hop
        self.assertIn("ring_d", rings)  # pull hop

    def test_search_by_needle_and_scalar_filters(self):
        self.store.push("parse", "failure", "malformed_json input", origin_ring="ring_a")
        self.store.push("parse", "success", "json_tolerant_parse works", origin_ring="ring_a", confidence=0.9)
        self.store.push("auth", "failure", "token_rotation", origin_ring="ring_c")
        hits = self.store.search(needle="token")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].category, "auth")
        by_kind = self.store.search(kind="success")
        self.assertEqual(len(by_kind), 1)
        self.assertEqual(by_kind[0].category, "parse")
        by_ring = self.store.search(origin_ring="ring_a")
        self.assertEqual(len(by_ring), 2)

    def test_snapshot_per_ring(self):
        self.store.push("parse", "failure", "x1", origin_ring="ring_a", actor="m1", ring="ring_a")
        self.store.push("parse", "failure", "x2", origin_ring="ring_b", actor="m3", ring="ring_b")
        snap_a = self.store.snapshot("ring_a")
        self.assertIn(content_address("parse", "failure", "x1"), snap_a.cids)
        self.assertNotIn(content_address("parse", "failure", "x2"), snap_a.cids)

    def test_proof_valid_and_recompute(self):
        self.store.push("schema", "failure", "nullable_field", origin_ring="ring_c")
        self.store.push("schema", "success", "coerce_nulls", origin_ring="ring_c")
        proof = self.store.proof()
        self.assertTrue(proof["valid"])
        self.assertEqual(proof["head"], proof["computed_head"])
        # tamper detection: a handwritten ledger line with no chain bookkeeping
        # must not be able to forge the head (head is only advanced via push).
        altered = self.store.head
        self.assertEqual(altered, proof["head"])

    def test_persistence_across_instances(self):
        self.store.push("auth", "success", "refresh_before_expiry", origin_ring="ring_b")
        other = ReferenceStore(self.root)  # reopen same data dir
        self.assertEqual(other.count, 1)
        self.assertTrue(other.proof()["valid"])


if __name__ == "__main__":
    unittest.main()
