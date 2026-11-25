# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sequence_recorder import (
    ms_from_seconds,
    press_ms_from_seconds,
    build_steps_from_actions,
)


class TestMacroSequenceTiming(unittest.TestCase):
    def test_ms_from_seconds_floors(self):
        self.assertEqual(ms_from_seconds(0.1509), 150)
        self.assertEqual(ms_from_seconds(0.0), 0)
        self.assertEqual(ms_from_seconds(-0.01), 0)

    def test_ms_from_seconds_caps_at_9999(self):
        self.assertEqual(ms_from_seconds(15.0), 9999)

    def test_press_ms_from_seconds_minimum_one(self):
        self.assertEqual(press_ms_from_seconds(0.0), 1)
        self.assertEqual(press_ms_from_seconds(0.050), 50)

    def test_build_steps_two_keys(self):
        actions = [
            {"key": "A", "press_ts": 1.0, "release_ts": 2.0},
            {"key": "B", "press_ts": 3.0, "release_ts": 4.0},
        ]
        steps = build_steps_from_actions(actions)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["key"], "A")
        self.assertEqual(steps[0]["press"], 1000)
        self.assertEqual(steps[0]["interval"], 1000)
        self.assertEqual(steps[1]["key"], "B")
        self.assertEqual(steps[1]["press"], 1000)
        self.assertEqual(steps[1]["interval"], 0)

    def test_build_steps_last_interval_zero(self):
        actions = [
            {"key": "X", "press_ts": 1.0, "release_ts": 1.01},
        ]
        steps = build_steps_from_actions(actions)
        self.assertEqual(steps[0]["interval"], 0)

    def test_build_steps_combo_key_preserved(self):
        actions = [
            {
                "key": "LCtrl&A",
                "press_ts": 0.0,
                "release_ts": 0.08,
            },
        ]
        steps = build_steps_from_actions(actions)
        self.assertEqual(steps[0]["key"], "LCtrl&A")
        self.assertEqual(steps[0]["press"], 80)


if __name__ == "__main__":
    unittest.main()
