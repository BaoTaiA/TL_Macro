# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_defaults import make_default_config, merge_loaded_config


class TestConfigDefaults(unittest.TestCase):
    def test_make_default_is_deep_copy(self):
        a = make_default_config()
        b = make_default_config()
        a["macros"].append({"key": "1"})
        self.assertEqual(len(b["macros"]), 0)

    def test_press_time_override(self):
        cfg = make_default_config(press_time=15)
        self.assertEqual(cfg["single_key_macro"]["press_time"], 15)

    def test_merge_loaded_partial(self):
        loaded = {"hotkey": "f1", "mode": 1}
        merged = merge_loaded_config(loaded)
        self.assertEqual(merged["hotkey"], "f1")
        self.assertEqual(merged["mode"], 1)
        self.assertEqual(merged["single_key_macro"]["press_time"], 15)
        self.assertEqual(merged["image_macro"]["skills"], [])
        self.assertNotIn("scan_interval_ms", merged["image_macro"])

    def test_merge_empty(self):
        merged = merge_loaded_config({})
        self.assertEqual(merged["mode"], 2)


if __name__ == "__main__":
    unittest.main()
