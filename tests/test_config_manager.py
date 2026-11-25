# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import (
    ConfigManager,
    parse_combination_key,
    sanitize_for_json,
)
from hotkey_conflict import check_key_in_combination
from config_defaults import make_default_config


class TestParseCombinationKey(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse_combination_key(""), [])
        self.assertEqual(parse_combination_key(None), [])

    def test_single_key(self):
        self.assertEqual(parse_combination_key("A"), ["a"])

    def test_combination(self):
        self.assertEqual(parse_combination_key("Ctrl&Shift&A"), ["ctrl", "shift", "a"])

    def test_whitespace(self):
        self.assertEqual(parse_combination_key(" Ctrl & A "), ["ctrl", "a"])


class TestCheckKeyInCombination(unittest.TestCase):
    def test_member(self):
        keys = ["ctrl", "shift", "a"]
        self.assertTrue(check_key_in_combination("ctrl", keys))
        self.assertTrue(check_key_in_combination("CTRL", keys))

    def test_not_member(self):
        keys = ["ctrl", "a"]
        self.assertFalse(check_key_in_combination("b", keys))


class TestSanitizeForJson(unittest.TestCase):
    def test_numpy_scalars(self):
        data = {
            "count": np.int64(3),
            "score": np.float32(0.85),
            "nested": [np.int32(1)],
        }
        result = sanitize_for_json(data)
        self.assertIsInstance(result["count"], int)
        self.assertIsInstance(result["score"], float)
        self.assertEqual(result["count"], 3)
        self.assertAlmostEqual(result["score"], 0.85)
        json.dumps(result)

    def test_plain_types_unchanged(self):
        data = {"a": 1, "b": "x", "c": [True, None]}
        self.assertEqual(sanitize_for_json(data), data)


class TestHotkeyConflict(unittest.TestCase):
    def setUp(self):
        self.cm = ConfigManager()
        self.config = make_default_config()
        self.config["hotkey"] = "f1"
        self.config["single_key_macro"]["hotkey"] = "f2"
        self.config["image_macro"]["hotkey"] = "f3"
        self.config["macros"] = [{"key": "4", "press": 20, "interval": 20}]

    def test_multi_hotkey_conflict(self):
        result = self.cm.check_hotkey_conflict("f1", "single", self.config)
        self.assertEqual(result[0], "多键宏启动热键")

    def test_single_hotkey_conflict(self):
        result = self.cm.check_hotkey_conflict("f2", "multi", self.config)
        self.assertEqual(result[0], "单键宏热键")

    def test_image_hotkey_conflict(self):
        result = self.cm.check_hotkey_conflict("f3", "multi", self.config)
        self.assertEqual(result[0], "图像宏热键")

    def test_macro_key_conflict(self):
        result = self.cm.check_hotkey_conflict("4", "multi", self.config)
        self.assertEqual(result[0], "宏序列中的按键")

    def test_no_conflict_same_source(self):
        self.assertIsNone(self.cm.check_hotkey_conflict("f1", "multi", self.config))

    def test_image_skill_vs_single_hotkey(self):
        self.config["image_macro"]["skills"] = [{"id": "s1", "key": "F", "name": "技能1"}]
        result = self.cm.check_hotkey_conflict("f", "single", self.config)
        self.assertEqual(result[0], "图像宏技能按键")

    def test_image_skill_vs_other_image_skill(self):
        self.config["image_macro"]["skills"] = [
            {"id": "s1", "key": "F", "name": "技能1"},
            {"id": "s2", "key": "G", "name": "技能2"},
        ]
        result = self.cm.check_hotkey_conflict("g", "image_skill", self.config, exclude_skill_id="s1")
        self.assertEqual(result[0], "图像宏技能按键")

    def test_image_skill_exclude_self(self):
        self.config["image_macro"]["skills"] = [{"id": "s1", "key": "F", "name": "技能1"}]
        self.assertIsNone(
            self.cm.check_hotkey_conflict("f", "image_skill", self.config, exclude_skill_id="s1")
        )

    def test_single_hotkey_vs_image_skill(self):
        self.config["image_macro"]["skills"] = [{"id": "s1", "key": "F", "name": "技能1"}]
        result = self.cm.check_hotkey_conflict("f", "single", self.config)
        self.assertEqual(result[0], "图像宏技能按键")


class TestCrossConfigConflict(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = ConfigManager(self.tmpdir)
        self.cm.create_config_dir()

    def _save(self, name, config):
        path = os.path.join(self.tmpdir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f)

    def test_duplicate_multi_hotkey(self):
        cfg_a = make_default_config()
        cfg_a["hotkey"] = "f5"
        cfg_b = make_default_config()
        cfg_b["hotkey"] = "f5"
        self.cm.enabled_configs_data = {"enabled_a": cfg_a}
        self._save("new_cfg", cfg_b)
        self.assertTrue(self.cm.check_cross_config_conflict("new_cfg"))

    def test_no_conflict_different_hotkeys(self):
        cfg_a = make_default_config()
        cfg_a["hotkey"] = "f5"
        cfg_b = make_default_config()
        cfg_b["hotkey"] = "f6"
        self.cm.enabled_configs_data = {"enabled_a": cfg_a}
        self._save("new_cfg", cfg_b)
        self.assertFalse(self.cm.check_cross_config_conflict("new_cfg"))

    def test_macro_contains_enabled_hotkey(self):
        cfg_a = make_default_config()
        cfg_a["single_key_macro"]["hotkey"] = "e"
        cfg_b = make_default_config()
        cfg_b["macros"] = [{"key": "e", "press": 20, "interval": 20}]
        self.cm.enabled_configs_data = {"enabled_a": cfg_a}
        self._save("new_cfg", cfg_b)
        self.assertTrue(self.cm.check_cross_config_conflict("new_cfg"))


if __name__ == "__main__":
    unittest.main()
