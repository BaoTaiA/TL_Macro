# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import global_settings


class TestGlobalSettings(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                data = {
                    "global_mode": False,
                    "processes": ["game.exe"],
                    "scan_interval_ms": 150,
                    "capture_backend": global_settings.BACKEND_DXGI,
                }
                self.assertTrue(global_settings.save_settings(data))
                loaded = global_settings.load_settings()
                self.assertFalse(loaded["global_mode"])
                self.assertEqual(loaded["processes"], ["game.exe"])
                self.assertEqual(loaded["scan_interval_ms"], 150)
                self.assertEqual(loaded["capture_backend"], global_settings.BACKEND_DXGI)

    def test_scan_interval_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                global_settings.save_settings({"scan_interval_ms": 10})
                self.assertEqual(global_settings.get_scan_interval_ms(), 30)
                global_settings.save_settings({"scan_interval_ms": 999})
                self.assertEqual(global_settings.get_scan_interval_ms(), 500)

    def test_backend_label_roundtrip(self):
        for backend, label in global_settings.BACKEND_LABELS.items():
            self.assertEqual(global_settings.backend_from_label(label), backend)
            self.assertEqual(global_settings.backend_label(backend), label)

    def test_set_backend_invalid(self):
        self.assertFalse(global_settings.set_backend("invalid"))

    def test_processes_truncated_to_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                processes = [f"app{i}.exe" for i in range(6)]
                global_settings.save_settings({"processes": processes})
                loaded = global_settings.load_settings()
                self.assertEqual(len(loaded["processes"]), global_settings.MAX_TARGET_PROCESSES)
                self.assertEqual(loaded["processes"], processes[:global_settings.MAX_TARGET_PROCESSES])


if __name__ == "__main__":
    unittest.main()
