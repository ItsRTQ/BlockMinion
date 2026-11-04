import unittest
from mod_orchestra.kb import search

class TestKB(unittest.TestCase):
    def test_retrieval_finds_source_note(self):
        entries=search("fabric loom profile",limit=5)
        self.assertTrue(entries)
        self.assertTrue(any("fabric" in x["path"] for x in entries))
    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            search("  ")
    def test_blockbench_formats_note_is_version_filtered(self):
        for q in ("box uv", "armor bones", "java_block rotation angle", "display presets handheld"):
            entries = search(q, "fabric-1.21.1", limit=3)
            self.assertTrue(entries and "formats-java-1.21.1" in entries[0]["path"], (q, entries))
        self.assertFalse(any("formats-java-1.21.1" in x["path"] for x in search("box uv", "fabric-1.22.0", limit=5)))
