# -*- coding: utf-8 -*-
"""区域截屏 - 支持 GDI (mss) 与 DXGI (bettercam) 双后端"""
import threading
import time
from typing import Tuple

import cv2
import mss
import numpy as np

import global_settings
from global_settings import BACKEND_DXGI, BACKEND_MSS
from logger import get_logger

_tls = threading.local()
_logger = get_logger()

_capture_lock = threading.RLock()
_backend_generation = 0
_dxgi_device_info_logged = False
_dxgi_last_frame = None
_dxgi_last_frame_time = 0.0

_DXGI_STALE_MAX_SEC = 0.15
_DXGI_REBUILD_DELAYS_SEC = (0.15, 0.3, 0.5, 0.8, 1.2)
_DXGI_NONE_RETRY_SLEEP_SEC = 0.15
_DXGI_NONE_RETRY_COUNT = 3
_DXGI_REBUILD_WAIT_POLL_SEC = 0.05
_DXGI_REBUILD_WAIT_MAX_SEC = 0.5
_WARN_THROTTLE_SEC = 5.0
_BACKOFF_STEPS_SEC = (0.2, 0.5, 1.0, 2.0)

_dxgi = {
    "camera": None,
    "rebuilding": False,
    "failure_streak": 0,
    "recovery_until": 0.0,
    "last_warn_time": 0.0,
    "last_begin_failed": False,
}


class CaptureUnavailableError(RuntimeError):
    """截屏暂时不可用（DXGI 重建中或退避中）"""


def clamp_region(
    x: int, y: int, w: int, h: int, screen_w: int, screen_h: int
) -> Tuple[int, int, int, int]:
    """将截屏矩形裁剪到屏幕范围内（w/h 至少为 1）"""
    screen_w = max(1, int(screen_w))
    screen_h = max(1, int(screen_h))
    x = max(0, min(int(x), screen_w - 1))
    y = max(0, min(int(y), screen_h - 1))
    w = max(1, min(int(w), screen_w - x))
    h = max(1, min(int(h), screen_h - y))
    return x, y, w, h


def _primary_screen_size_mss() -> Tuple[int, int]:
    if not hasattr(_tls, "sct"):
        _tls.sct = mss.mss()
    mon = _tls.sct.monitors[1]
    return int(mon["width"]), int(mon["height"])


def get_primary_screen_size() -> Tuple[int, int]:
    """返回主显示器宽高（与当前截屏后端一致）"""
    if global_settings.get_backend() == BACKEND_DXGI:
        try:
            camera = _get_dxgi_camera()
            return int(camera.width), int(camera.height)
        except Exception as e:
            _logger.debug(f"DXGI 屏幕尺寸读取失败，回退 MSS: {e}")
    return _primary_screen_size_mss()


def _sync_tls_generation() -> None:
    gen = _backend_generation
    if getattr(_tls, "backend_generation", None) != gen:
        if hasattr(_tls, "dxgi_frame"):
            del _tls.dxgi_frame
        _tls.backend_generation = gen


def _log_dxgi_device_info(camera) -> None:
    """首次创建 DXGI camera 时记录适配器与输出信息（便于确认 GPU 路径）"""
    global _dxgi_device_info_logged
    if _dxgi_device_info_logged:
        return
    try:
        device = camera._device
        output = camera._output
        adapter = device.description
        vram_mb = device.vram_size // (1024 * 1024)
        vendor_id = device.vendor_id
        width, height = output.resolution
        monitor = output.devicename
        _logger.info(
            f"DXGI Desktop Duplication 已初始化: 适配器={adapter} "
            f"VendorId=0x{vendor_id:04X} VRAM={vram_mb}MB "
            f"输出={monitor} 分辨率={width}x{height}"
        )
        _dxgi_device_info_logged = True
    except Exception as e:
        _logger.warning(f"DXGI 设备信息读取失败: {e}")


def _log_capture_warning(message: str) -> None:
    now = time.time()
    if now - _dxgi["last_warn_time"] >= _WARN_THROTTLE_SEC:
        _dxgi["last_warn_time"] = now
        _logger.warning(message)


def _grab_region_mss(x: int, y: int, w: int, h: int) -> np.ndarray:
    if not hasattr(_tls, "sct"):
        _tls.sct = mss.mss()
    raw = _tls.sct.grab({
        "left": int(x),
        "top": int(y),
        "width": int(w),
        "height": int(h),
    })
    bgra = np.asarray(raw, dtype=np.uint8)
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def _store_dxgi_last_frame(frame: np.ndarray) -> None:
    global _dxgi_last_frame, _dxgi_last_frame_time
    _dxgi_last_frame = frame
    _dxgi_last_frame_time = time.time()


def _is_dxgi_last_frame_fresh() -> bool:
    if _dxgi_last_frame is None:
        return False
    return (time.time() - _dxgi_last_frame_time) <= _DXGI_STALE_MAX_SEC


def _create_dxgi_camera():
    import bettercam
    camera = bettercam.create(output_color="BGR")
    _log_dxgi_device_info(camera)
    return camera


def _release_global_dxgi_camera() -> None:
    with _capture_lock:
        camera = _dxgi["camera"]
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
        _dxgi["camera"] = None


def _ensure_dxgi_camera_unlocked():
    if _dxgi["rebuilding"]:
        raise CaptureUnavailableError("DXGI 重建中")
    if _dxgi["camera"] is None:
        _dxgi["camera"] = _create_dxgi_camera()
    return _dxgi["camera"]


def _wait_if_rebuilding() -> None:
    deadline = time.time() + _DXGI_REBUILD_WAIT_MAX_SEC
    while _dxgi["rebuilding"] and time.time() < deadline:
        time.sleep(_DXGI_REBUILD_WAIT_POLL_SEC)
    if _dxgi["rebuilding"]:
        raise CaptureUnavailableError("DXGI 重建中")


def _get_dxgi_camera():
    _wait_if_rebuilding()
    with _capture_lock:
        return _ensure_dxgi_camera_unlocked()


def _rebuild_dxgi_camera(reason: str) -> bool:
    if _dxgi["rebuilding"]:
        _wait_if_rebuilding()
        with _capture_lock:
            return _dxgi["camera"] is not None

    with _capture_lock:
        _dxgi["rebuilding"] = True

    try:
        _release_global_dxgi_camera()
        last_err = None
        for delay in _DXGI_REBUILD_DELAYS_SEC:
            time.sleep(delay)
            try:
                camera = _create_dxgi_camera()
                with _capture_lock:
                    _dxgi["camera"] = camera
                    _dxgi["failure_streak"] = 0
                    _dxgi["recovery_until"] = 0.0
                    _dxgi["last_begin_failed"] = False
                _logger.info(f"DXGI camera 重建成功（原因: {reason}）")
                return True
            except Exception as e:
                last_err = e
                with _capture_lock:
                    _dxgi["camera"] = None

        with _capture_lock:
            _dxgi["failure_streak"] += 1
            idx = min(_dxgi["failure_streak"] - 1, len(_BACKOFF_STEPS_SEC) - 1)
            _dxgi["recovery_until"] = time.time() + _BACKOFF_STEPS_SEC[idx]
        _log_capture_warning(
            f"DXGI camera 重建失败（原因: {reason}）: {last_err}"
        )
        return False
    finally:
        with _capture_lock:
            _dxgi["rebuilding"] = False


def _is_dxgi_grab_broken(exc: BaseException) -> bool:
    if isinstance(exc, AttributeError):
        return True
    return exc.__class__.__name__ == "COMError"


def _dxgi_camera_grab(camera, grab_region_arg):
    if grab_region_arg is None:
        return camera.grab()
    return camera.grab(region=grab_region_arg)


def _validate_bgr_frame(frame: np.ndarray) -> None:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise RuntimeError(f"unexpected DXGI frame shape: {frame.shape}")


def _slice_bgr_frame(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    fh, fw = frame.shape[:2]
    x2 = min(int(x) + int(w), fw)
    y2 = min(int(y) + int(h), fh)
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    if x1 >= x2 or y1 >= y2:
        raise ValueError(f"invalid grab region after clamp: {x},{y},{w},{h}")
    return frame[y1:y2, x1:x2].copy()


def _check_dxgi_recovery_window() -> None:
    if time.time() < _dxgi["recovery_until"]:
        raise CaptureUnavailableError("DXGI 暂不可用，退避中")


def _grab_frame_dxgi_with_retry(region=None) -> np.ndarray:
    """DXGI 截屏：进程级单例 + 重建退避；无新帧且上一帧已过期则抛错（不回退 MSS）"""
    _sync_tls_generation()
    _check_dxgi_recovery_window()
    _wait_if_rebuilding()

    grab_region_arg = None
    clamped_region = None
    if region is not None:
        x, y, w, h = region
        try:
            camera = _get_dxgi_camera()
            sw, sh = int(camera.width), int(camera.height)
        except CaptureUnavailableError:
            raise
        except Exception:
            sw, sh = _primary_screen_size_mss()
        x, y, w, h = clamp_region(x, y, w, h, sw, sh)
        clamped_region = (x, y, w, h)
        grab_region_arg = (x, y, x + w, y + h)

    for none_attempt in range(_DXGI_NONE_RETRY_COUNT):
        try:
            with _capture_lock:
                if _dxgi["rebuilding"]:
                    raise CaptureUnavailableError("DXGI 重建中")
                camera = _ensure_dxgi_camera_unlocked()
                frame = _dxgi_camera_grab(camera, grab_region_arg)

            if frame is not None:
                _validate_bgr_frame(frame)
                frame = np.ascontiguousarray(frame)
                if grab_region_arg is None:
                    _store_dxgi_last_frame(frame)
                return frame

            if none_attempt < _DXGI_NONE_RETRY_COUNT - 1:
                time.sleep(_DXGI_NONE_RETRY_SLEEP_SEC)
                continue
        except CaptureUnavailableError:
            raise
        except Exception as e:
            if _is_dxgi_grab_broken(e):
                _log_capture_warning(f"DXGI grab 异常，尝试重建: {e}")
                if _rebuild_dxgi_camera(str(e)):
                    continue
                raise CaptureUnavailableError(f"DXGI 重建失败: {e}") from e
            raise

    if _is_dxgi_last_frame_fresh():
        last = _dxgi_last_frame
        if clamped_region is None:
            _logger.debug("DXGI grab 无新帧，复用未过期的上一整帧")
            return last.copy()
        x, y, w, h = clamped_region
        _logger.debug("DXGI grab 无新帧，从未过期整帧切片")
        return _slice_bgr_frame(last, x, y, w, h)

    raise RuntimeError("DXGI grab returned None")


def _grab_full_frame_dxgi() -> np.ndarray:
    return _grab_frame_dxgi_with_retry(region=None)


def _grab_region_dxgi(x: int, y: int, w: int, h: int) -> np.ndarray:
    cached = getattr(_tls, "dxgi_frame", None)
    if cached is not None:
        return _slice_bgr_frame(cached, x, y, w, h)
    return _grab_frame_dxgi_with_retry(region=(x, y, w, h))


def _grab_by_backend(x: int, y: int, w: int, h: int) -> np.ndarray:
    """按全局设置选用截屏后端，互不自动回退"""
    if global_settings.get_backend() == BACKEND_DXGI:
        return _grab_region_dxgi(x, y, w, h)
    return _grab_region_mss(x, y, w, h)


def get_capture_backoff_sec() -> float:
    """连续截屏失败后建议的扫描退避时长（秒）"""
    if not _dxgi["last_begin_failed"]:
        return 0.0
    idx = min(max(_dxgi["failure_streak"] - 1, 0), len(_BACKOFF_STEPS_SEC) - 1)
    return _BACKOFF_STEPS_SEC[idx]


def was_last_capture_round_skipped() -> bool:
    """上一轮 begin_capture_frame 是否因截屏失败而跳过"""
    return bool(_dxgi["last_begin_failed"])


def on_backend_changed(old_backend: str, new_backend: str) -> None:
    """识别引擎切换时释放截屏资源（调用方保证无图像宏在运行）"""
    global _backend_generation, _dxgi_last_frame, _dxgi_last_frame_time, _dxgi_device_info_logged
    _release_global_dxgi_camera()
    _backend_generation += 1
    _dxgi["failure_streak"] = 0
    _dxgi["recovery_until"] = 0.0
    _dxgi["rebuilding"] = False
    _dxgi["last_begin_failed"] = False
    _dxgi["last_warn_time"] = 0.0
    _dxgi_last_frame = None
    _dxgi_last_frame_time = 0.0
    _dxgi_device_info_logged = False
    _logger.info(
        f"识别引擎已切换，截屏资源已重置: "
        f"{global_settings.backend_label(old_backend)} -> "
        f"{global_settings.backend_label(new_backend)}"
    )


def shutdown_capture() -> None:
    """应用退出时释放全部截屏资源"""
    global _backend_generation, _dxgi_last_frame, _dxgi_last_frame_time, _dxgi_device_info_logged
    _release_global_dxgi_camera()
    release_thread_capture()
    _backend_generation += 1
    _dxgi["failure_streak"] = 0
    _dxgi["recovery_until"] = 0.0
    _dxgi["rebuilding"] = False
    _dxgi["last_begin_failed"] = False
    _dxgi["last_warn_time"] = 0.0
    _dxgi_last_frame = None
    _dxgi_last_frame_time = 0.0
    _dxgi_device_info_logged = False


def begin_capture_frame() -> bool:
    """一轮图像宏扫描开始前调用；DXGI 下 dup 一次整帧供后续 grab_region 切片。

    Returns:
        True 表示本轮可继续分组截屏；False 表示 DXGI 无新帧，调用方应跳过本轮。
    """
    _sync_tls_generation()
    if global_settings.get_backend() != BACKEND_DXGI:
        _dxgi["last_begin_failed"] = False
        return True
    try:
        _tls.dxgi_frame = _grab_full_frame_dxgi()
        _dxgi["last_begin_failed"] = False
        fh, fw = _tls.dxgi_frame.shape[:2]
        _logger.debug(f"DXGI begin_capture_frame 成功: {fw}x{fh}")
        return True
    except CaptureUnavailableError as e:
        _tls.dxgi_frame = None
        _dxgi["last_begin_failed"] = True
        _log_capture_warning(f"DXGI begin_capture_frame 失败，跳过本轮扫描: {e}")
        return False
    except Exception as e:
        _tls.dxgi_frame = None
        _dxgi["last_begin_failed"] = True
        _log_capture_warning(f"DXGI begin_capture_frame 失败，跳过本轮扫描: {e}")
        return False


def end_capture_frame():
    """一轮图像宏扫描结束后调用，释放线程内帧缓存"""
    if hasattr(_tls, "dxgi_frame"):
        del _tls.dxgi_frame


def release_thread_capture():
    """释放当前线程的截屏线程本地缓存（不释放进程级 DXGI camera）"""
    sct = getattr(_tls, "sct", None)
    if sct is not None:
        try:
            sct.close()
        except Exception:
            pass
        del _tls.sct
    for attr in ("dxgi_frame", "backend_generation"):
        if hasattr(_tls, attr):
            delattr(_tls, attr)


def slice_bgr_frame(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """从 BGR 整帧中裁剪区域（坐标为帧内像素）"""
    return _slice_bgr_frame(frame, x, y, w, h)


def grab_full_screen(x: int, y: int, w: int, h: int) -> np.ndarray:
    """截取屏幕矩形区域（通常为整屏），返回 BGR numpy 数组"""
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid full screen region: {w}x{h}")
    _sync_tls_generation()
    backend = global_settings.get_backend()
    if backend == BACKEND_DXGI:
        frame = _grab_full_frame_dxgi()
        result = _slice_bgr_frame(frame, x, y, w, h)
    else:
        result = _grab_region_mss(x, y, w, h)
    _logger.debug(f"grab_full_screen: backend={backend}, region=({x},{y},{w}x{h})")
    return result


def grab_region(x: int, y: int, w: int, h: int) -> np.ndarray:
    """截取屏幕区域，返回 BGR numpy 数组"""
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid grab region: {w}x{h}")
    _sync_tls_generation()
    sw, sh = get_primary_screen_size()
    x, y, w, h = clamp_region(x, y, w, h, sw, sh)
    backend = global_settings.get_backend()
    result = _grab_by_backend(x, y, w, h)
    _logger.debug(f"grab_region: backend={backend}, region=({x},{y},{w}x{h})")
    return result
