# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_recognizer import (
    DetectResult, IconMatcher, RegionIconMatcher, SkillRuntimeState, union_search_rects,
    resolve_scan_interval_ms, resolve_buff_region, evaluate_buff_precondition,
    normalize_skill_precondition, should_fire_skill, can_fire_absent,
    should_enqueue_skill, mark_skill_fired, resolve_execute_interval_ms,
    cluster_skill_rects, rect_area, TRIGGER_MODE_PRESENT, TRIGGER_MODE_ABSENT,
    DEFAULT_SCAN_INTERVAL_MS, DEFAULT_EXECUTE_INTERVAL_MS, ABSENT_MIN_FIRE_INTERVAL_MS,
    MAX_CAPTURE_GROUP_AREA, sort_candidates_by_priority, clamp_skill_priority,
    MIN_PRIORITY, MAX_PRIORITY, find_skill_by_priority, find_duplicate_priorities,
)


class TestSearchRectClamp(unittest.TestCase):
    @patch("image_recognizer.get_primary_screen_size", return_value=(2560, 1600))
    def test_icon_matcher_clamps_right_edge(self, _mock_size):
        template = np.zeros((32, 32, 3), dtype=np.uint8)
        matcher = IconMatcher(template, 2500, 100, {"search_margin": 80})
        x, y, w, h = matcher.get_search_rect()
        self.assertEqual(x, 2420)
        self.assertEqual(y, 20)
        self.assertEqual(w, 140)
        self.assertEqual(h, 192)
        self.assertLessEqual(x + w, 2560)
        self.assertLessEqual(y + h, 1600)

    @patch("image_recognizer.get_primary_screen_size", return_value=(2560, 1600))
    def test_resolve_buff_region_clamps(self, _mock_size):
        pre = {"buff_region": {"x": 2500, "y": 0, "width": 200, "height": 100}}
        x, y, w, h = resolve_buff_region(pre)
        self.assertEqual((x, y, w, h), (2500, 0, 60, 100))


class TestUnionSearchRects(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(union_search_rects([]))

    def test_single_rect(self):
        self.assertEqual(union_search_rects([(10, 20, 30, 40)]), (10, 20, 30, 40))

    def test_merge_two(self):
        rects = [(0, 0, 50, 50), (40, 40, 50, 50)]
        self.assertEqual(union_search_rects(rects), (0, 0, 90, 90))


class TestIconMatcherDetectInFrame(unittest.TestCase):
    def _make_matcher(self, template_size=(20, 20), anchor=(100, 100), **params):
        template = np.zeros((template_size[1], template_size[0], 3), dtype=np.uint8)
        template[:, :] = (0, 128, 255)
        recognition = {"search_margin": 10, **params}
        return IconMatcher(template, anchor[0], anchor[1], recognition)

    def test_match_bright_icon(self):
        matcher = self._make_matcher(
            brightness_threshold=30,
            position_tolerance=15,
        )
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        x, y = 100, 100
        frame[y:y + 20, x:x + 20] = (0, 128, 255)

        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertIsInstance(result, DetectResult)
        self.assertGreaterEqual(result.confidence, 0.99)
        self.assertTrue(result.is_ready)

    def test_shared_gray_frame(self):
        matcher = self._make_matcher()
        frame_bgr = np.zeros((200, 200, 3), dtype=np.uint8)
        frame_bgr[100:120, 100:120] = (0, 128, 255)
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        result_bgr = matcher.detect_in_frame(frame_bgr, 0, 0)
        result_gray = matcher.detect_in_frame(frame_bgr, 0, 0, frame_gray=frame_gray)

        self.assertEqual(result_bgr.is_ready, result_gray.is_ready)
        self.assertAlmostEqual(result_bgr.confidence, result_gray.confidence, places=4)

    def test_dark_icon_not_ready(self):
        matcher = self._make_matcher()
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[100:120, 100:120] = (0, 128, 255)

        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertFalse(result.is_ready)

    def test_out_of_bounds_returns_empty(self):
        matcher = self._make_matcher(anchor=(500, 500))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertFalse(result.is_ready)
        self.assertEqual(result.confidence, 0.0)


class TestRegionIconMatcher(unittest.TestCase):
    def _make_region_matcher(self, template_size=(16, 16), region=(0, 0, 200, 60)):
        template = np.zeros((template_size[1], template_size[0], 3), dtype=np.uint8)
        template[:, :] = (40, 40, 40)
        rx, ry, rw, rh = region
        return RegionIconMatcher(template, rx, ry, rw, rh, {"confidence": 0.8})

    def test_match_anywhere_in_region(self):
        matcher = self._make_region_matcher()
        frame = np.zeros((60, 200, 3), dtype=np.uint8)
        frame[20:36, 120:136] = (40, 40, 40)

        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertTrue(result.is_ready)
        self.assertGreaterEqual(result.confidence, 0.99)

    def test_dark_template_no_brightness_gate(self):
        matcher = self._make_region_matcher()
        frame = np.zeros((60, 200, 3), dtype=np.uint8)
        frame[10:26, 30:46] = (40, 40, 40)

        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertTrue(result.is_ready)

    def test_template_outside_region_not_ready(self):
        template = np.zeros((16, 16, 3), dtype=np.uint8)
        template[:, :8] = (0, 0, 255)
        template[:, 8:] = (0, 255, 0)
        matcher = RegionIconMatcher(template, 0, 0, 80, 40, {"confidence": 0.8})
        frame = np.zeros((60, 200, 3), dtype=np.uint8)
        frame[10:26, 150:166] = template

        result = matcher.detect_in_frame(frame, 0, 0)
        self.assertFalse(result.is_ready)


class TestScanIntervalResolve(unittest.TestCase):
    def test_reads_global_settings(self):
        with patch("global_settings.get_scan_interval_ms", return_value=150):
            self.assertEqual(resolve_scan_interval_ms(), 150)


class TestResolveBuffRegion(unittest.TestCase):
    def test_explicit_region(self):
        pre = {"buff_region": {"x": 10, "y": 20, "width": 100, "height": 30}}
        self.assertEqual(resolve_buff_region(pre), (10, 20, 100, 30))

    def test_legacy_anchor_fallback(self):
        pre = {
            "buff_icon": {"path": "x.png", "x": 100, "y": 50, "width": 20, "height": 20},
            "recognition": {"search_margin": 10},
        }
        self.assertEqual(resolve_buff_region(pre), (90, 40, 40, 40))


class TestFromBuffCondition(unittest.TestCase):
    def test_builds_matcher_from_condition(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buff.png")
            img = np.zeros((12, 12, 3), dtype=np.uint8)
            img[:, :] = (50, 50, 50)
            cv2.imwrite(path, img)
            condition = {
                "enabled": True,
                "buff_region": {"x": 0, "y": 0, "width": 100, "height": 40},
                "buff_icon": {"path": path, "width": 12, "height": 12},
                "recognition": {"confidence": 0.85},
            }
            matcher = RegionIconMatcher.from_buff_condition(condition, tmp)
            self.assertIsNotNone(matcher)
            self.assertEqual(matcher.get_search_rect(), (0, 0, 100, 40))

    def test_disabled_returns_none(self):
        condition = {"enabled": False, "buff_region": {"x": 0, "y": 0, "width": 10, "height": 10}}
        self.assertIsNone(RegionIconMatcher.from_buff_condition(condition))


class TestEvaluateBuffPrecondition(unittest.TestCase):
    def test_present_requires_rising_edge_and_wait(self):
        state = SkillRuntimeState()
        self.assertFalse(evaluate_buff_precondition(True, TRIGGER_MODE_PRESENT, state, 1.0, 300))
        self.assertFalse(evaluate_buff_precondition(True, TRIGGER_MODE_PRESENT, state, 1.1, 300))
        self.assertTrue(evaluate_buff_precondition(True, TRIGGER_MODE_PRESENT, state, 1.31, 300))

    def test_present_resets_when_buff_gone(self):
        state = SkillRuntimeState()
        evaluate_buff_precondition(True, TRIGGER_MODE_PRESENT, state, 1.0, 0)
        evaluate_buff_precondition(True, TRIGGER_MODE_PRESENT, state, 1.5, 0)
        self.assertFalse(evaluate_buff_precondition(False, TRIGGER_MODE_PRESENT, state, 2.0, 0))

    def test_absent_steady_state_and_wait(self):
        state = SkillRuntimeState()
        self.assertFalse(evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 1.0, 300))
        self.assertFalse(evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 1.1, 300))
        self.assertTrue(evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 1.31, 300))

    def test_absent_from_start_without_prior_present(self):
        state = SkillRuntimeState()
        self.assertFalse(state.buff_last_ready)
        self.assertIsNone(state.buff_gone_since)
        self.assertFalse(evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 0.0, 300))
        self.assertIsNotNone(state.buff_gone_since)
        self.assertTrue(evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 0.31, 300))

    def test_absent_resets_when_buff_returns(self):
        state = SkillRuntimeState()
        evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 1.0, 0)
        evaluate_buff_precondition(False, TRIGGER_MODE_ABSENT, state, 1.5, 0)
        self.assertFalse(evaluate_buff_precondition(True, TRIGGER_MODE_ABSENT, state, 2.0, 0))
        self.assertIsNone(state.buff_gone_since)


class TestCanFireAbsent(unittest.TestCase):
    def test_first_fire_allowed(self):
        state = SkillRuntimeState()
        self.assertTrue(can_fire_absent(state, 1.0))

    def test_throttled_within_interval(self):
        state = SkillRuntimeState(last_fire_time=1.0)
        self.assertFalse(can_fire_absent(state, 1.4))
        self.assertTrue(can_fire_absent(state, 1.5))

    def test_custom_interval(self):
        state = SkillRuntimeState(last_fire_time=0.0)
        self.assertFalse(can_fire_absent(state, 0.2, interval_ms=300))
        self.assertTrue(can_fire_absent(state, 0.3, interval_ms=300))


class TestClusterSkillRects(unittest.TestCase):
    def test_empty_entries(self):
        self.assertEqual(cluster_skill_rects([]), [])

    def test_single_group_when_area_small(self):
        entries = [(0, [(0, 0, 100, 100)]), (1, [(200, 0, 100, 100)])]
        groups = cluster_skill_rects(entries, max_area=500_000)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].skill_indices, [0, 1])

    def test_splits_when_area_exceeds_threshold(self):
        entries = [
            (0, [(0, 0, 600, 600)]),
            (1, [(2000, 0, 600, 600)]),
        ]
        groups = cluster_skill_rects(entries, max_area=MAX_CAPTURE_GROUP_AREA)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].skill_indices, [0])
        self.assertEqual(groups[1].skill_indices, [1])

    def test_greedy_merge_adjacent_skills(self):
        entries = [
            (0, [(0, 0, 400, 400)]),
            (1, [(300, 0, 400, 400)]),
            (2, [(5000, 0, 400, 400)]),
        ]
        groups = cluster_skill_rects(entries, max_area=500_000)
        self.assertEqual(len(groups), 2)
        merged = next(g for g in groups if 0 in g.skill_indices)
        self.assertIn(1, merged.skill_indices)
        self.assertNotIn(2, merged.skill_indices)


class TestRectArea(unittest.TestCase):
    def test_area(self):
        self.assertEqual(rect_area((10, 20, 30, 40)), 1200)


class TestExecuteInterval(unittest.TestCase):
    def test_resolve_default(self):
        self.assertEqual(resolve_execute_interval_ms({}), DEFAULT_EXECUTE_INTERVAL_MS)

    def test_resolve_custom(self):
        self.assertEqual(resolve_execute_interval_ms({"execute_interval_ms": 500}), 500)

    def test_blocks_within_interval_allows_after(self):
        state = SkillRuntimeState()
        self.assertTrue(
            should_enqueue_skill(None, True, True, False, state, 1.0, interval_ms=200)
        )
        mark_skill_fired(state, 1.0, None)
        self.assertFalse(
            should_enqueue_skill(None, True, True, True, state, 1.1, interval_ms=200)
        )
        self.assertTrue(
            should_enqueue_skill(None, True, True, True, state, 1.3, interval_ms=200)
        )

    def test_not_ready_never_fires(self):
        state = SkillRuntimeState()
        self.assertFalse(
            should_enqueue_skill(None, True, False, False, state, 1.0, interval_ms=0)
        )

    def test_absent_uses_at_least_500ms(self):
        state = SkillRuntimeState()
        mark_skill_fired(state, 1.0, TRIGGER_MODE_ABSENT)
        self.assertFalse(
            should_enqueue_skill(
                TRIGGER_MODE_ABSENT, True, True, True, state, 1.2, interval_ms=100
            )
        )
        self.assertTrue(
            should_enqueue_skill(
                TRIGGER_MODE_ABSENT, True, True, True, state, 1.6, interval_ms=100
            )
        )


class TestShouldEnqueueSkill(unittest.TestCase):
    def test_level_trigger_while_still_ready(self):
        state = SkillRuntimeState()
        self.assertTrue(
            should_enqueue_skill(None, True, True, False, state, 1.0, interval_ms=0)
        )
        mark_skill_fired(state, 1.0)
        # 间隔为 0 时，常亮可立即再次执行
        self.assertTrue(
            should_enqueue_skill(None, True, True, True, state, 1.0, interval_ms=0)
        )


class TestShouldFireSkill(unittest.TestCase):
    def test_absent_level_trigger_while_ready(self):
        self.assertTrue(should_fire_skill(TRIGGER_MODE_ABSENT, True, True, True))
        self.assertTrue(should_fire_skill(TRIGGER_MODE_ABSENT, True, True, False))

    def test_absent_no_fire_when_pre_not_ok(self):
        self.assertFalse(should_fire_skill(TRIGGER_MODE_ABSENT, False, True, False))

    def test_present_level_while_ready(self):
        self.assertTrue(should_fire_skill(TRIGGER_MODE_PRESENT, True, True, False))
        self.assertTrue(should_fire_skill(TRIGGER_MODE_PRESENT, True, True, True))

    def test_no_precondition_level(self):
        self.assertTrue(should_fire_skill(None, True, True, False))
        self.assertTrue(should_fire_skill(None, True, True, True))
        self.assertFalse(should_fire_skill(None, True, False, False))


class TestNormalizeSkillPrecondition(unittest.TestCase):
    def test_migrate_post_enabled_to_absent(self):
        skill = {
            "precondition": {"enabled": False, "name": ""},
            "postcondition": {
                "enabled": True,
                "name": "海啸",
                "buff_region": {"x": 1, "y": 2, "width": 10, "height": 20},
            },
        }
        out = normalize_skill_precondition(skill)
        self.assertNotIn("postcondition", out)
        pre = out["precondition"]
        self.assertTrue(pre["enabled"])
        self.assertEqual(pre["trigger_mode"], TRIGGER_MODE_ABSENT)
        self.assertEqual(pre["name"], "海啸")

    def test_present_when_pre_enabled(self):
        skill = {
            "precondition": {"enabled": True, "name": "盾"},
            "postcondition": {"enabled": False},
        }
        out = normalize_skill_precondition(skill)
        self.assertEqual(out["precondition"]["trigger_mode"], TRIGGER_MODE_PRESENT)
        self.assertEqual(out["precondition"]["name"], "盾")


class TestClampSkillPriority(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertIsNone(clamp_skill_priority(None))
        self.assertIsNone(clamp_skill_priority(""))

    def test_in_range(self):
        self.assertEqual(clamp_skill_priority(5), 5)
        self.assertEqual(clamp_skill_priority("10"), 10)

    def test_clamp_out_of_range(self):
        self.assertEqual(clamp_skill_priority(0), MIN_PRIORITY)
        self.assertEqual(clamp_skill_priority(99), MAX_PRIORITY)

    def test_invalid(self):
        self.assertIsNone(clamp_skill_priority("abc"))


class TestSortCandidatesByPriority(unittest.TestCase):
    def _skills(self, priorities):
        return [{"priority": p} for p in priorities]

    def test_empty(self):
        self.assertEqual(sort_candidates_by_priority([], []), [])

    def test_all_unset_preserves_list_order(self):
        skills = self._skills([None] * 4)
        self.assertEqual(sort_candidates_by_priority([0, 1, 2, 3], skills), [0, 1, 2, 3])

    def test_prioritized_before_unset(self):
        skills = self._skills([None, 5, None, 10, None])
        self.assertEqual(
            sort_candidates_by_priority([0, 1, 2, 3, 4], skills),
            [3, 1, 0, 2, 4],
        )

    def test_higher_priority_first(self):
        skills = self._skills([1, 10, 5])
        self.assertEqual(sort_candidates_by_priority([0, 1, 2], skills), [1, 2, 0])

    def test_same_priority_by_list_index(self):
        skills = self._skills([10, 10])
        self.assertEqual(sort_candidates_by_priority([1, 0], skills), [0, 1])

    def test_clamp_invalid_priority(self):
        skills = self._skills([99, 0])
        self.assertEqual(sort_candidates_by_priority([0, 1], skills), [0, 1])


class TestPriorityUniqueness(unittest.TestCase):
    def _skill(self, name, priority, skill_id=None):
        s = {"name": name, "priority": priority}
        if skill_id:
            s["id"] = skill_id
        return s

    def test_find_skill_by_priority_none_when_unique(self):
        skills = [self._skill("A", 10, "a"), self._skill("B", None, "b")]
        self.assertIsNone(find_skill_by_priority(skills, 5))
        self.assertIsNotNone(find_skill_by_priority(skills, 10))

    def test_find_skill_by_priority_excludes_self(self):
        skills = [self._skill("A", 10, "a"), self._skill("B", 9, "b")]
        self.assertIsNone(find_skill_by_priority(skills, 10, exclude_skill_id="a"))
        self.assertEqual(
            find_skill_by_priority(skills, 10, exclude_skill_id="b").get("name"),
            "A",
        )

    def test_find_duplicate_priorities_empty(self):
        self.assertEqual(find_duplicate_priorities([]), [])

    def test_find_duplicate_priorities_none_not_duplicate(self):
        skills = [self._skill("A", None), self._skill("B", None)]
        self.assertEqual(find_duplicate_priorities(skills), [])

    def test_find_duplicate_priorities_no_conflict(self):
        skills = [self._skill("A", 10), self._skill("B", 9)]
        self.assertEqual(find_duplicate_priorities(skills), [])

    def test_find_duplicate_priorities_two_same(self):
        skills = [self._skill("A", 10), self._skill("B", 10)]
        self.assertEqual(find_duplicate_priorities(skills), [(10, ["A", "B"])])

    def test_find_duplicate_priorities_three_same(self):
        skills = [self._skill("A", 5), self._skill("B", 5), self._skill("C", 5)]
        self.assertEqual(find_duplicate_priorities(skills), [(5, ["A", "B", "C"])])


if __name__ == "__main__":
    unittest.main()
