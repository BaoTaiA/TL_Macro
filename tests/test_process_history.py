# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from process_history import ProcessHistoryTracker, _excluded_processes, MAX_HISTORY


class TestProcessHistory(unittest.TestCase):
    def setUp(self):
        self.tracker = ProcessHistoryTracker()

    def test_record_dedupe_and_move_to_front(self):
        self.tracker.record("game.exe")
        self.tracker.record("chrome.exe")
        self.tracker.record("game.exe")
        self.assertEqual(self.tracker.get_recent(), ["game.exe", "chrome.exe"])

    def test_max_history_truncated(self):
        for i in range(MAX_HISTORY + 5):
            self.tracker.record(f"app{i}.exe")
        recent = self.tracker.get_recent()
        self.assertEqual(len(recent), MAX_HISTORY)
        self.assertEqual(recent[0], f"app{MAX_HISTORY + 4}.exe")

    def test_excludes_self_processes(self):
        for name in _excluded_processes():
            self.tracker.record(name)
        self.assertEqual(self.tracker.get_recent(), [])

    def test_empty_and_whitespace_ignored(self):
        self.tracker.record("")
        self.tracker.record("   ")
        self.assertEqual(self.tracker.get_recent(), [])

    def test_get_recent_returns_copy(self):
        self.tracker.record("a.exe")
        recent = self.tracker.get_recent()
        recent.append("b.exe")
        self.assertEqual(self.tracker.get_recent(), ["a.exe"])


if __name__ == "__main__":
    unittest.main()
