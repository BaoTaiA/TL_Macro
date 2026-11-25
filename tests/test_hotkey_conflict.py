# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_defaults import make_default_config
from hotkey_conflict import (
    check_key_in_combination,
    find_intra_conflict,
    has_cross_conflict,
    keys_conflict,
    parse_combination_key,
)


class TestKeysConflict(unittest.TestCase):
    def test_exact_match_case_insensitive(self):
        self.assertTrue(keys_conflict("F1", "f1"))

    def test_combo_contains_single(self):
        self.assertTrue(keys_conflict("Ctrl&A", "A"))

    def test_combo_intersection(self):
        self.assertTrue(keys_conflict("Ctrl&Shift&A", "Ctrl&B"))

    def test_no_conflict(self):
        self.assertFalse(keys_conflict("F1", "F2"))


class TestFindIntraConflict(unittest.TestCase):
    def setUp(self):
        self.config = make_default_config()
        self.config["hotkey"] = "f1"
        self.config["single_key_macro"]["hotkey"] = "f2"
        self.config["image_macro"]["hotkey"] = "f3"
        self.config["macros"] = [{"key": "4", "press": 20, "interval": 20}]

    def test_multi_hotkey_conflict(self):
        result = find_intra_conflict("f1", "single", self.config)
        self.assertEqual(result[0], "多键宏启动热键")

    def test_no_conflict_same_source(self):
        self.assertIsNone(find_intra_conflict("f1", "multi", self.config))

    def test_combo_macro_conflict_label(self):
        self.config["macros"] = [{"key": "Ctrl&A", "press": 20, "interval": 20}]
        result = find_intra_conflict("A", "multi", self.config)
        self.assertEqual(result[0], "宏序列中的组合按键")

    def test_macro_key_conflicts_with_image_skill_combo(self):
        self.config["image_macro"]["skills"] = [
            {"id": "s1", "key": "Ctrl&A", "name": "test"}
        ]
        result = find_intra_conflict("A", "macro", self.config)
        self.assertEqual(result[0], "图像宏技能组合按键")

    def test_macro_key_conflicts_with_image_skill_exact(self):
        self.config["image_macro"]["skills"] = [
            {"id": "s1", "key": "4", "name": "test"}
        ]
        result = find_intra_conflict("4", "macro", self.config)
        self.assertEqual(result[0], "图像宏技能按键")


class TestHasCrossConflict(unittest.TestCase):
    def test_duplicate_startup_hotkey(self):
        cfg_a = make_default_config()
        cfg_a["hotkey"] = "f5"
        cfg_b = make_default_config()
        cfg_b["hotkey"] = "f5"
        self.assertTrue(has_cross_conflict("new_cfg", cfg_b, {"enabled_a": cfg_a}))

    def test_macro_contains_enabled_hotkey(self):
        cfg_a = make_default_config()
        cfg_a["single_key_macro"]["hotkey"] = "e"
        cfg_b = make_default_config()
        cfg_b["macros"] = [{"key": "e", "press": 20, "interval": 20}]
        self.assertTrue(has_cross_conflict("new_cfg", cfg_b, {"enabled_a": cfg_a}))


class TestParseCombinationKey(unittest.TestCase):
    def test_combination(self):
        self.assertEqual(parse_combination_key("Ctrl&Shift&A"), ["ctrl", "shift", "a"])


class TestCheckKeyInCombination(unittest.TestCase):
    def test_member(self):
        keys = ["ctrl", "shift", "a"]
        self.assertTrue(check_key_in_combination("ctrl", keys))


if __name__ == "__main__":
    unittest.main()
