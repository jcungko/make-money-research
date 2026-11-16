"""Checkpoint corruption, cursor rollback, and recovery tests (stdlib only)."""
import json
import tempfile
import unittest
from pathlib import Path
from research_usdjpy.checkpoint import verify, restore, seal, read, PROTOCOL

class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "results"
        (self.root / "experiments").mkdir(parents=True)
        self.write("state.json", {"protocol": PROTOCOL, "cursor": 2, "completed": 2})
        self.write("run_2026-11-16T00-00-00_aaaa.json", {
            "protocol": PROTOCOL, "from_cursor": 0, "status": "EXPERIMENTS_COMPLETED",
            "experiments": [{"id": "UJ-R1-%03d" % i, "status": "REJECTED",
                             "trades": 1, "net_usd": -1} for i in range(2)]})
        for i in range(2):
            self.write("experiments/UJ-R1-%03d.json" % i, {
                "config": {"id": "UJ-R1-%03d" % i}, "status": "REJECTED",
                "metrics": {"trades": 1, "net_usd": -1}})

    def write(self, name, item):
        (self.root / name).write_text(json.dumps(item))

    def test_legacy_migration_then_seal(self):
        state, index = verify(self.root)
        self.assertEqual(index["legacy_unindexed"], 2)
        dest = Path(self.tmp.name) / "restored"
        restore(self.root, dest)
        self.assertEqual(read(dest / "index.json")["cursor"], 2)
        self.assertEqual(read(dest / "state.json")["cursor"], 2)

    def test_sealed_corruption_detected(self):
        seal(self.root)
        verify(self.root)
        self.write("state.json", {"protocol": PROTOCOL, "cursor": 0, "completed": 0})
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_proof_is_fatal(self):
        seal(self.root)
        (self.root / "experiments/UJ-R1-001.json").unlink()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_hash_tampering_detected(self):
        seal(self.root)
        proof = self.root / "experiments/UJ-R1-001.json"
        proof.write_text(proof.read_text() + "\n")
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_nonsequential_cursor_detected(self):
        self.write("state.json", {"protocol": PROTOCOL, "cursor": 3, "completed": 3})
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_bogus_experiment_id_detected(self):
        p = next(self.root.glob("run_*.json"))
        report = read(p)
        report["experiments"][1]["id"] = "UJ-R1-095"
        self.write(p.name, report)
        with self.assertRaises(ValueError):
            verify(self.root)

if __name__ == "__main__":
    unittest.main()
