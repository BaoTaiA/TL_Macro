# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asset_manager


class TestAssetManager(unittest.TestCase):
    def test_skill_icon_rel_path(self):
        rel = asset_manager.get_skill_icon_rel_path("cfg1", "abc123")
        self.assertEqual(rel, "assets/cfg1/skills/abc123_icon.png")
        rel1 = asset_manager.get_skill_icon_rel_path("cfg1", "abc123", 1)
        self.assertEqual(rel1, "assets/cfg1/skills/abc123_icon_1.png")
        rel2 = asset_manager.get_skill_icon_rel_path("cfg1", "abc123", 2)
        self.assertEqual(rel2, "assets/cfg1/skills/abc123_icon_2.png")

    def test_buff_icon_rel_path(self):
        rel = asset_manager.get_buff_icon_rel_path("cfg1", "abc123")
        self.assertEqual(rel, "assets/cfg1/buffs/abc123_buff.png")

    def test_buff_region_preview_rel_path(self):
        rel = asset_manager.get_buff_region_preview_rel_path("cfg1", "abc123")
        self.assertEqual(rel, "assets/cfg1/buff_regions/abc123_region.png")

    def test_rename_config_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = asset_manager.get_config_assets_dir(tmp, "old")
            os.makedirs(old_dir)
            marker = os.path.join(old_dir, "marker.txt")
            with open(marker, "w", encoding="utf-8") as f:
                f.write("x")
            asset_manager.rename_config_assets(tmp, "old", "new")
            new_dir = asset_manager.get_config_assets_dir(tmp, "new")
            self.assertTrue(os.path.isdir(new_dir))
            self.assertTrue(os.path.exists(os.path.join(new_dir, "marker.txt")))
            self.assertFalse(os.path.exists(old_dir))

    def test_delete_config_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets_dir = asset_manager.get_config_assets_dir(tmp, "cfg")
            os.makedirs(assets_dir)
            asset_manager.delete_config_assets(tmp, "cfg")
            self.assertFalse(os.path.exists(assets_dir))


if __name__ == "__main__":
    unittest.main()
