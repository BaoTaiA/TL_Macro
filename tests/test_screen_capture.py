# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import global_settings
import screen_capture


def _set_backend(backend: str) -> None:
    settings = global_settings.load_settings()
    settings["capture_backend"] = backend
    global_settings.save_settings(settings)


class TestScreenCapture(unittest.TestCase):
    def setUp(self):
        self._orig_backend = global_settings.get_backend()
        _set_backend(global_settings.BACKEND_MSS)
        screen_capture.shutdown_capture()

    def tearDown(self):
        _set_backend(self._orig_backend)
        screen_capture.shutdown_capture()

    def test_grab_region_invalid_size(self):
        with self.assertRaises(ValueError):
            screen_capture.grab_region(0, 0, 0, 10)

    @patch.object(screen_capture, "_grab_region_mss")
    def test_grab_region_mss_backend(self, mock_mss):
        fake = np.zeros((10, 10, 3), dtype=np.uint8)
        mock_mss.return_value = fake
        result = screen_capture.grab_region(1, 2, 10, 10)
        np.testing.assert_array_equal(result, fake)
        mock_mss.assert_called_once_with(1, 2, 10, 10)

    @patch.object(screen_capture, "_grab_region_mss")
    @patch.object(screen_capture, "_grab_region_dxgi")
    def test_dxgi_failure_raises_no_mss(self, mock_dxgi, mock_mss):
        _set_backend(global_settings.BACKEND_DXGI)
        mock_dxgi.side_effect = RuntimeError("dxgi failed")
        with self.assertRaises(RuntimeError):
            screen_capture.grab_region(0, 0, 5, 5)
        mock_mss.assert_not_called()

    @patch.object(screen_capture, "_grab_full_frame_dxgi")
    def test_begin_frame_slices_cached_region(self, mock_full):
        _set_backend(global_settings.BACKEND_DXGI)
        frame = np.arange(300, dtype=np.uint8).reshape(10, 10, 3)
        mock_full.return_value = frame
        self.assertTrue(screen_capture.begin_capture_frame())
        try:
            roi = screen_capture.grab_region(2, 3, 4, 5)
            self.assertEqual(roi.shape, (5, 4, 3))
            np.testing.assert_array_equal(roi, frame[3:8, 2:6].copy())
        finally:
            screen_capture.end_capture_frame()

    @patch.object(screen_capture, "_ensure_dxgi_camera_unlocked")
    def test_dxgi_reuse_fresh_last_frame_on_none(self, mock_ensure):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        camera.grab.return_value = None
        mock_ensure.return_value = camera
        last = np.arange(120, dtype=np.uint8).reshape(10, 4, 3)
        screen_capture._dxgi_last_frame = last
        screen_capture._dxgi_last_frame_time = __import__("time").time()

        with patch.object(screen_capture, "_grab_region_mss") as mock_mss:
            with patch.object(screen_capture, "time") as mock_time:
                mock_time.sleep = lambda _: None
                mock_time.time = __import__("time").time
                frame = screen_capture._grab_frame_dxgi_with_retry(region=None)
            np.testing.assert_array_equal(frame, last)
            mock_mss.assert_not_called()

    @patch.object(screen_capture, "_ensure_dxgi_camera_unlocked")
    def test_dxgi_stale_last_frame_raises(self, mock_ensure):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        camera.grab.return_value = None
        mock_ensure.return_value = camera
        last = np.arange(120, dtype=np.uint8).reshape(10, 4, 3)
        screen_capture._dxgi_last_frame = last
        screen_capture._dxgi_last_frame_time = 0.0

        with patch.object(screen_capture, "_grab_region_mss") as mock_mss:
            with patch.object(screen_capture, "time") as mock_time:
                mock_time.sleep = lambda _: None
                mock_time.time = __import__("time").time
                with self.assertRaises(RuntimeError):
                    screen_capture._grab_frame_dxgi_with_retry(region=None)
            mock_mss.assert_not_called()

    @patch.object(screen_capture, "_rebuild_dxgi_camera", return_value=True)
    @patch.object(screen_capture, "_get_dxgi_camera")
    def test_dxgi_camera_reset_on_attribute_error(self, mock_get_camera, mock_rebuild):
        _set_backend(global_settings.BACKEND_DXGI)
        broken = MagicMock()
        broken.grab.side_effect = AttributeError("duplicator is None")
        ok_cam = MagicMock()
        ok = np.ones((6, 6, 3), dtype=np.uint8) * 7
        ok_cam.grab.return_value = ok
        mock_get_camera.side_effect = [broken, ok_cam]

        with patch.object(screen_capture, "_ensure_dxgi_camera_unlocked") as mock_ensure:
            mock_ensure.side_effect = [broken, ok_cam]
            frame = screen_capture._grab_frame_dxgi_with_retry(region=None)
        np.testing.assert_array_equal(frame, ok)
        mock_rebuild.assert_called_once()

    @patch.object(screen_capture, "_get_dxgi_camera")
    def test_dxgi_retry_success(self, mock_get_camera):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        ok = np.ones((8, 8, 3), dtype=np.uint8) * 42
        camera.grab.side_effect = [None, None, ok]
        mock_get_camera.return_value = camera

        with patch.object(screen_capture, "_ensure_dxgi_camera_unlocked", return_value=camera):
            with patch.object(screen_capture, "time") as mock_time:
                mock_time.sleep = lambda _: None
                mock_time.time = __import__("time").time
                frame = screen_capture._grab_frame_dxgi_with_retry(region=None)
        np.testing.assert_array_equal(frame, ok)

    @patch.object(screen_capture, "_grab_region_mss")
    @patch.object(screen_capture, "_get_dxgi_camera")
    def test_dxgi_no_last_frame_raises_no_mss(self, mock_get_camera, mock_mss):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        camera.grab.return_value = None
        mock_get_camera.return_value = camera
        screen_capture._dxgi_last_frame = None

        with patch.object(screen_capture, "_ensure_dxgi_camera_unlocked", return_value=camera):
            with patch.object(screen_capture, "time") as mock_time:
                mock_time.sleep = lambda _: None
                mock_time.time = __import__("time").time
                with self.assertRaises(RuntimeError):
                    screen_capture.grab_region(0, 0, 4, 4)
        mock_mss.assert_not_called()

    @patch.object(screen_capture, "_grab_full_frame_dxgi")
    def test_begin_frame_no_stale_fallback(self, mock_full):
        _set_backend(global_settings.BACKEND_DXGI)
        screen_capture._dxgi_last_frame = np.arange(300, dtype=np.uint8).reshape(10, 10, 3)
        mock_full.side_effect = RuntimeError("DXGI grab returned None")

        self.assertFalse(screen_capture.begin_capture_frame())
        self.assertIs(getattr(screen_capture._tls, "dxgi_frame", "missing"), None)
        self.assertTrue(screen_capture.was_last_capture_round_skipped())

    def test_begin_frame_mss_always_true(self):
        _set_backend(global_settings.BACKEND_MSS)
        self.assertTrue(screen_capture.begin_capture_frame())

    def test_log_dxgi_device_info_once(self):
        camera = MagicMock()
        camera._device.description = "NVIDIA GeForce RTX"
        camera._device.vram_size = 8 * 1024 * 1024 * 1024
        camera._device.vendor_id = 0x10DE
        camera._output.resolution = (1920, 1080)
        camera._output.devicename = "\\\\.\\DISPLAY1"

        screen_capture._dxgi_device_info_logged = False
        with patch.object(screen_capture._logger, "info") as mock_info:
            screen_capture._log_dxgi_device_info(camera)
            screen_capture._log_dxgi_device_info(camera)
            mock_info.assert_called_once()
            msg = mock_info.call_args[0][0]
            self.assertIn("NVIDIA GeForce RTX", msg)
            self.assertIn("1920x1080", msg)
            self.assertIn("\\\\.\\DISPLAY1", msg)

    @patch.object(screen_capture, "_release_global_dxgi_camera")
    def test_on_backend_changed_releases_camera(self, mock_release):
        screen_capture.on_backend_changed(
            global_settings.BACKEND_MSS, global_settings.BACKEND_DXGI
        )
        mock_release.assert_called_once()

    def test_release_thread_does_not_destroy_global_dxgi(self):
        camera = MagicMock()
        screen_capture._dxgi["camera"] = camera
        screen_capture.release_thread_capture()
        self.assertIs(screen_capture._dxgi["camera"], camera)

    @patch.object(screen_capture, "_grab_frame_dxgi_with_retry")
    def test_macro_stop_start_reuses_dxgi(self, mock_grab):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        screen_capture._dxgi["camera"] = camera
        ok = np.ones((4, 4, 3), dtype=np.uint8)
        mock_grab.return_value = ok

        for _ in range(3):
            screen_capture.release_thread_capture()
            frame = screen_capture._grab_frame_dxgi_with_retry(region=None)
            np.testing.assert_array_equal(frame, ok)
        self.assertIs(screen_capture._dxgi["camera"], camera)

    def test_get_capture_backoff_after_begin_failure(self):
        screen_capture._dxgi["last_begin_failed"] = True
        screen_capture._dxgi["failure_streak"] = 2
        self.assertEqual(screen_capture.get_capture_backoff_sec(), 0.5)

    @patch.object(screen_capture, "_rebuild_dxgi_camera")
    @patch.object(screen_capture, "_ensure_dxgi_camera_unlocked")
    def test_dxgi_rebuild_on_broken_grab(self, mock_ensure, mock_rebuild):
        _set_backend(global_settings.BACKEND_DXGI)
        broken = MagicMock()
        broken.grab.side_effect = AttributeError("duplicator is None")
        ok_cam = MagicMock()
        ok = np.ones((4, 4, 3), dtype=np.uint8)
        ok_cam.grab.return_value = ok
        mock_ensure.side_effect = [broken, ok_cam]
        mock_rebuild.return_value = True

        frame = screen_capture._grab_frame_dxgi_with_retry(region=None)
        np.testing.assert_array_equal(frame, ok)
        mock_rebuild.assert_called_once()


class TestClampRegion(unittest.TestCase):
    def setUp(self):
        self._orig_backend = global_settings.get_backend()
        _set_backend(global_settings.BACKEND_MSS)
        screen_capture.shutdown_capture()

    def tearDown(self):
        _set_backend(self._orig_backend)
        screen_capture.shutdown_capture()

    def test_clamp_right_edge(self):
        x, y, w, h = screen_capture.clamp_region(2500, 0, 200, 100, 2560, 1600)
        self.assertEqual((x, y, w, h), (2500, 0, 60, 100))

    def test_clamp_bottom_edge(self):
        x, y, w, h = screen_capture.clamp_region(0, 1550, 100, 200, 2560, 1600)
        self.assertEqual((x, y, w, h), (0, 1550, 100, 50))

    def test_clamp_fully_off_screen_x(self):
        x, y, w, h = screen_capture.clamp_region(3000, 0, 100, 100, 2560, 1600)
        self.assertEqual(x, 2559)
        self.assertEqual(w, 1)
        self.assertEqual(h, 100)

    @patch.object(screen_capture, "get_primary_screen_size", return_value=(2560, 1600))
    @patch.object(screen_capture, "_grab_region_dxgi")
    def test_grab_region_clamps_before_dxgi(self, mock_dxgi, _mock_size):
        _set_backend(global_settings.BACKEND_DXGI)
        mock_dxgi.return_value = np.zeros((100, 60, 3), dtype=np.uint8)
        screen_capture.grab_region(2500, 0, 200, 100)
        mock_dxgi.assert_called_once_with(2500, 0, 60, 100)

    @patch.object(screen_capture, "_get_dxgi_camera")
    def test_dxgi_grab_clamps_region_arg(self, mock_get_camera):
        _set_backend(global_settings.BACKEND_DXGI)
        camera = MagicMock()
        camera.width = 2560
        camera.height = 1600
        ok = np.ones((100, 60, 3), dtype=np.uint8)
        camera.grab.return_value = ok
        mock_get_camera.return_value = camera

        with patch.object(screen_capture, "_ensure_dxgi_camera_unlocked", return_value=camera):
            frame = screen_capture._grab_frame_dxgi_with_retry(region=(2500, 0, 200, 100))
        np.testing.assert_array_equal(frame, ok)
        camera.grab.assert_called_once_with(region=(2500, 0, 2560, 100))


if __name__ == "__main__":
    unittest.main()
