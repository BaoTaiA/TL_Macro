# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from window_manager import WindowFocusManager


class TestWindowManager(unittest.TestCase):
    def setUp(self):
        self.mgr = WindowFocusManager()

    def test_global_mode_always_active(self):
        self.mgr.apply_settings(True, [])
        self.assertTrue(self.mgr.is_target_window_active())

    def test_window_mode_empty_processes_inactive(self):
        self.mgr.apply_settings(False, [])
        self.assertFalse(self.mgr.is_target_window_active())

    @patch.object(WindowFocusManager, "_get_foreground_process_name", return_value="game.exe")
    def test_window_mode_matching_process(self, _mock_fg):
        self.mgr.apply_settings(False, ["game.exe"])
        self.assertTrue(self.mgr.is_target_window_active())

    @patch.object(WindowFocusManager, "_get_foreground_process_name", return_value="other.exe")
    def test_window_mode_non_matching_process(self, _mock_fg):
        self.mgr.apply_settings(False, ["game.exe"])
        self.assertFalse(self.mgr.is_target_window_active())

    @patch.object(WindowFocusManager, "_get_foreground_process_name", return_value="cached.exe")
    def test_apply_settings_invalidates_cache(self, mock_fg):
        self.mgr.apply_settings(False, ["game.exe"])
        self.mgr.is_target_window_active()
        self.assertEqual(mock_fg.call_count, 1)
        self.mgr.apply_settings(False, ["game.exe", "other.exe"])
        self.mgr.is_target_window_active()
        self.assertEqual(mock_fg.call_count, 2)


if __name__ == "__main__":
    unittest.main()
