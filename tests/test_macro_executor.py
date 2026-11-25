# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_executor import MacroExecutor
from image_recognizer import (
    SkillRuntimeState, mark_skill_fired, begin_ensure_retry,
    update_ensure_press_state, should_enqueue_skill,
    resolve_skill_cooldown_ms, normalize_image_skill,
    SKILL_KIND_BUFF, SKILL_KIND_ATTACK,
)


class TestMacroExecutorFireKey(unittest.TestCase):
    def setUp(self):
        self.executor = MacroExecutor()

    def test_fire_skill_key_invalid_raises(self):
        skill = {"key": "", "press_time": 50, "repeat_count": 1, "repeat_interval": 100}
        with self.assertRaises(ValueError):
            self.executor._fire_skill_key(skill, MagicMock())

    @patch("image_macro_runner.input_simulator")
    def test_fire_skill_key_valid(self, mock_input):
        mock_input.get_virtual_key.return_value = 65
        mock_input.get_key_flags.return_value = 0
        skill = {"key": "A", "press_time": 50, "repeat_count": 1, "repeat_interval": 100}
        stop = MagicMock()
        stop.is_set.return_value = False
        self.executor._fire_skill_key(skill, stop)
        mock_input.send_key_event.assert_called()


class TestEnsurePressAndCooldown(unittest.TestCase):
    def test_ensure_press_blocks_until_not_ready(self):
        state = SkillRuntimeState()
        mark_skill_fired(
            state, 1.0, None,
            cooldown_ms=50,
            ensure_press=True,
            ensure_timeout_ms=800,
            ensure_retries=1,
        )
        self.assertTrue(state.awaiting_not_ready)
        self.assertFalse(
            should_enqueue_skill(None, True, True, True, state, 1.1, interval_ms=50)
        )
        self.assertEqual(update_ensure_press_state(state, True, 1.2), "waiting")
        self.assertEqual(update_ensure_press_state(state, False, 1.3), "confirmed")
        self.assertFalse(state.awaiting_not_ready)

    def test_ensure_press_timeout_retry_then_give_up(self):
        state = SkillRuntimeState()
        mark_skill_fired(
            state, 1.0, None,
            cooldown_ms=0,
            ensure_press=True,
            ensure_timeout_ms=100,
            ensure_retries=1,
        )
        self.assertEqual(update_ensure_press_state(state, True, 1.05), "waiting")
        self.assertEqual(update_ensure_press_state(state, True, 1.2), "timeout_retry")
        begin_ensure_retry(state, 1.2, cooldown_ms=0, ensure_timeout_ms=100)
        self.assertEqual(update_ensure_press_state(state, True, 1.35), "timeout_give_up")
        self.assertFalse(state.awaiting_not_ready)

    def test_cooldown_ms_uses_max_of_recovery_and_interval(self):
        skill = {"recovery_ms": 300, "execute_interval_ms": 100}
        self.assertEqual(resolve_skill_cooldown_ms(skill), 300)
        skill2 = {"recovery_ms": 20, "execute_interval_ms": 200}
        self.assertEqual(resolve_skill_cooldown_ms(skill2), 200)

    def test_normalize_image_skill_defaults(self):
        skill = normalize_image_skill({
            "name": "a",
            "icon": {"path": "assets/x/skills/1_icon.png", "x": 1, "y": 2},
        })
        self.assertEqual(skill["skill_kind"], SKILL_KIND_ATTACK)
        self.assertEqual(len(skill["icons"]), 1)
        self.assertEqual(skill["icon"]["path"], skill["icons"][0]["path"])
        self.assertFalse(skill["ensure_press"])

        buff = normalize_image_skill({"skill_kind": "buff", "icon": {"path": "p.png"}})
        self.assertEqual(buff["skill_kind"], SKILL_KIND_BUFF)


if __name__ == "__main__":
    unittest.main()
