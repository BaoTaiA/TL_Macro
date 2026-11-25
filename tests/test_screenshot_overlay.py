# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QKeyEvent

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import screen_capture
from screenshot_overlay import ScreenshotOverlay


def _make_gradient_frame(w=200, h=100):
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            frame[y, x] = (x % 256, y % 256, (x + y) % 256)
    return frame


class TestScreenshotOverlay(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    @patch("screenshot_overlay.grab_full_screen")
    def test_selection_slices_frozen_frame(self, mock_grab):
        frame = _make_gradient_frame(200, 100)
        mock_grab.return_value = frame
        results = []

        overlay = ScreenshotOverlay(
            screenshot_callback=lambda img, rect, cancelled=False: results.append(
                (img, rect, cancelled)
            )
        )

        class PressEvent:
            def button(self):
                return Qt.LeftButton

            def pos(self):
                return QPoint(10, 20)

        class ReleaseEvent:
            def button(self):
                return Qt.LeftButton

            def pos(self):
                return QPoint(60, 50)

        overlay.mousePressEvent(PressEvent())
        overlay.mouseReleaseEvent(ReleaseEvent())
        QApplication.processEvents()

        self.assertEqual(len(results), 1)
        img, rect, cancelled = results[0]
        self.assertFalse(cancelled)
        self.assertIsNotNone(img)
        self.assertEqual(img.shape, (31, 51, 3))
        self.assertEqual(rect.width(), 51)
        self.assertEqual(rect.height(), 31)
        np.testing.assert_array_equal(img, frame[20:51, 10:61])

    @patch("screenshot_overlay.grab_full_screen")
    def test_escape_cancels_without_image(self, mock_grab):
        mock_grab.return_value = _make_gradient_frame()
        results = []

        overlay = ScreenshotOverlay(
            screenshot_callback=lambda img, rect, cancelled=False: results.append(
                (img, rect, cancelled)
            )
        )
        event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        overlay.keyPressEvent(event)
        QApplication.processEvents()

        self.assertEqual(len(results), 1)
        img, rect, cancelled = results[0]
        self.assertTrue(cancelled)
        self.assertIsNone(img)
        self.assertIsNone(rect)

    @patch("screenshot_overlay.grab_full_screen")
    def test_small_selection_resets_on_overlay(self, mock_grab):
        mock_grab.return_value = _make_gradient_frame()
        results = []

        overlay = ScreenshotOverlay(
            screenshot_callback=lambda img, rect, cancelled=False: results.append(
                (img, rect, cancelled)
            )
        )

        class PressEvent:
            def button(self):
                return Qt.LeftButton

            def pos(self):
                return QPoint(0, 0)

        class ReleaseEvent:
            def button(self):
                return Qt.LeftButton

            def pos(self):
                return QPoint(2, 2)

        overlay.mousePressEvent(PressEvent())
        overlay.mouseReleaseEvent(ReleaseEvent())
        QApplication.processEvents()

        self.assertEqual(len(results), 0)
        self.assertTrue(overlay.isVisible())
        self.assertIsNone(overlay.start_point)
        self.assertIsNone(overlay.end_point)
        self.assertFalse(overlay.is_drawing)
        self.assertEqual(overlay._hint_message, "选区太小，请重新框选")

    @patch("screenshot_overlay.grab_full_screen")
    def test_dismiss_hides_before_callback(self, mock_grab):
        mock_grab.return_value = _make_gradient_frame()
        states = []

        def callback(img, rect, cancelled=False):
            overlay_ref = states[0]["overlay"]
            states.append(
                {
                    "visible": overlay_ref.isVisible(),
                    "dismissing": overlay_ref._dismissing,
                }
            )

        overlay = ScreenshotOverlay()
        states.append({"overlay": overlay})
        overlay.screenshot_callback = callback

        overlay._dismiss(_make_gradient_frame(10, 10), None)
        self.assertFalse(overlay.isVisible())
        self.assertTrue(overlay._dismissing)

        QApplication.processEvents()
        self.assertEqual(len(states), 2)
        self.assertFalse(states[1]["visible"])
        self.assertTrue(states[1]["dismissing"])


class TestGrabFullScreen(unittest.TestCase):
    def setUp(self):
        screen_capture.release_thread_capture()

    def tearDown(self):
        screen_capture.release_thread_capture()

    def test_grab_full_screen_invalid_size(self):
        with self.assertRaises(ValueError):
            screen_capture.grab_full_screen(0, 0, 0, 10)

    @patch.object(screen_capture, "_grab_region_mss")
    def test_grab_full_screen_mss(self, mock_mss):
        fake = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_mss.return_value = fake
        with patch.object(screen_capture.global_settings, "get_backend", return_value=screen_capture.BACKEND_MSS):
            result = screen_capture.grab_full_screen(0, 0, 1920, 1080)
        np.testing.assert_array_equal(result, fake)
        mock_mss.assert_called_once_with(0, 0, 1920, 1080)

    @patch.object(screen_capture, "_grab_full_frame_dxgi")
    def test_grab_full_screen_dxgi_slices(self, mock_dxgi):
        fake = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_dxgi.return_value = fake
        with patch.object(screen_capture.global_settings, "get_backend", return_value=screen_capture.BACKEND_DXGI):
            result = screen_capture.grab_full_screen(10, 20, 100, 50)
        self.assertEqual(result.shape, (50, 100, 3))


if __name__ == "__main__":
    unittest.main()
