# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import global_settings
from logger import log_level_from_name, get_current_log_level, set_log_level
import logging


def _base_settings(**overrides):
    data = {
        "global_mode": True,
        "processes": [],
        "scan_interval_ms": 100,
        "capture_backend": global_settings.BACKEND_MSS,
        "log_level": "WARNING",
    }
    data.update(overrides)
    return data


class TestLoggerSettings(unittest.TestCase):
    def test_log_level_from_name(self):
        self.assertEqual(log_level_from_name("DEBUG"), logging.DEBUG)
        self.assertEqual(log_level_from_name("info"), logging.INFO)
        self.assertEqual(log_level_from_name("unknown"), logging.WARNING)

    def test_save_and_load_log_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                global_settings.save_settings(_base_settings(log_level="DEBUG"))
                loaded = global_settings.load_settings()
                self.assertEqual(loaded["log_level"], "DEBUG")
                self.assertEqual(global_settings.get_log_level(), "DEBUG")

    def test_invalid_log_level_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                global_settings.save_settings({"log_level": "VERBOSE"})
                self.assertEqual(global_settings.get_log_level(), "WARNING")

    def test_set_log_level_name_applies_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                global_settings.load_settings()
                self.assertTrue(global_settings.set_log_level_name("ERROR"))
                self.assertEqual(get_current_log_level(), "ERROR")
                self.assertEqual(global_settings.get_log_level(), "ERROR")

    def test_save_settings_logs_backend_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                mock_logger = MagicMock()
                with patch.object(global_settings, "get_logger", return_value=mock_logger):
                    global_settings.load_settings()
                    global_settings.save_settings(_base_settings())
                    global_settings.save_settings(
                        _base_settings(capture_backend=global_settings.BACKEND_DXGI)
                    )
                    info_messages = [
                        str(call.args[0]) for call in mock_logger.info.call_args_list
                    ]
                    self.assertTrue(
                        any("识别引擎已切换" in msg for msg in info_messages),
                        info_messages,
                    )

    def test_save_settings_logs_scan_interval_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                mock_logger = MagicMock()
                with patch.object(global_settings, "get_logger", return_value=mock_logger):
                    global_settings.load_settings()
                    global_settings.save_settings(_base_settings(scan_interval_ms=100))
                    global_settings.save_settings(_base_settings(scan_interval_ms=110))
                    info_messages = [
                        str(call.args[0]) for call in mock_logger.info.call_args_list
                    ]
                    self.assertTrue(
                        any("图像宏扫描间隔已更改" in msg for msg in info_messages),
                        info_messages,
                    )

    def test_save_settings_no_scan_log_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "global_settings.json")
            with patch.object(global_settings, "get_settings_path", return_value=path):
                mock_logger = MagicMock()
                with patch.object(global_settings, "get_logger", return_value=mock_logger):
                    global_settings.load_settings()
                    global_settings.save_settings(_base_settings(scan_interval_ms=100))
                    mock_logger.reset_mock()
                    global_settings.save_settings(_base_settings(scan_interval_ms=100))
                    info_messages = [
                        str(call.args[0]) for call in mock_logger.info.call_args_list
                    ]
                    self.assertFalse(
                        any("图像宏扫描间隔已更改" in msg for msg in info_messages),
                        info_messages,
                    )


if __name__ == "__main__":
    unittest.main()
