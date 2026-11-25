# -*- coding: utf-8 -*-
"""全局参数：焦点控制、图像宏扫描间隔、截屏引擎、日志级别"""
import json
import os
import threading

from logger import get_logger
from utils import get_app_base_dir

BACKEND_MSS = "mss"
BACKEND_DXGI = "dxgi"
DEFAULT_BACKEND = BACKEND_MSS
DEFAULT_SCAN_INTERVAL_MS = 50
DEFAULT_LOG_LEVEL = "WARNING"
MAX_TARGET_PROCESSES = 5
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})

BACKEND_LABELS = {
    BACKEND_MSS: "GDI (mss)",
    BACKEND_DXGI: "DXGI (bettercam)",
}
_LABEL_TO_BACKEND = {v: k for k, v in BACKEND_LABELS.items()}

DEFAULT_SETTINGS = {
    "global_mode": True,
    "processes": [],
    "scan_interval_ms": DEFAULT_SCAN_INTERVAL_MS,
    "capture_backend": DEFAULT_BACKEND,
    "log_level": DEFAULT_LOG_LEVEL,
}

_lock = threading.RLock()
_cached = DEFAULT_SETTINGS.copy()


def get_settings_path() -> str:
    return os.path.join(get_app_base_dir(), "config", "global_settings.json")


def _normalize_settings(data: dict) -> dict:
    settings = DEFAULT_SETTINGS.copy()
    settings["global_mode"] = bool(data.get("global_mode", True))
    processes = data.get("processes") or []
    settings["processes"] = [
        str(p).strip() for p in processes if str(p).strip()
    ][:MAX_TARGET_PROCESSES]
    try:
        scan_ms = int(data.get("scan_interval_ms", DEFAULT_SCAN_INTERVAL_MS))
    except (TypeError, ValueError):
        scan_ms = DEFAULT_SCAN_INTERVAL_MS
    settings["scan_interval_ms"] = max(30, min(500, scan_ms))
    backend = data.get("capture_backend", DEFAULT_BACKEND)
    if backend not in (BACKEND_MSS, BACKEND_DXGI):
        backend = DEFAULT_BACKEND
    settings["capture_backend"] = backend
    log_level = str(data.get("log_level", DEFAULT_LOG_LEVEL)).upper()
    if log_level not in VALID_LOG_LEVELS:
        log_level = DEFAULT_LOG_LEVEL
    settings["log_level"] = log_level
    return settings


def _log_settings_changes(old: dict, new: dict) -> None:
    """记录全局参数字段级变更（INFO）"""
    logger = get_logger()
    old_backend = old.get("capture_backend", DEFAULT_BACKEND)
    new_backend = new.get("capture_backend", DEFAULT_BACKEND)
    if old_backend != new_backend:
        logger.info(
            f"识别引擎已切换: {backend_label(old_backend)} -> {backend_label(new_backend)}"
        )

    old_scan = old.get("scan_interval_ms", DEFAULT_SCAN_INTERVAL_MS)
    new_scan = new.get("scan_interval_ms", DEFAULT_SCAN_INTERVAL_MS)
    if old_scan != new_scan:
        logger.info(f"图像宏扫描间隔已更改: {old_scan}ms -> {new_scan}ms")

    if old.get("global_mode") != new.get("global_mode"):
        old_mode = "全局" if old.get("global_mode", True) else "窗口"
        new_mode = "全局" if new.get("global_mode") else "窗口"
        logger.info(f"焦点模式已切换: {old_mode} -> {new_mode}")

    if old.get("processes") != new.get("processes"):
        logger.info(f"目标进程已更新: {new.get('processes', [])}")


def load_settings() -> dict:
    """加载全局参数到内存缓存"""
    global _cached
    path = get_settings_path()
    if not os.path.exists(path):
        with _lock:
            _cached = DEFAULT_SETTINGS.copy()
        return _cached.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        normalized = _normalize_settings(data)
        with _lock:
            _cached = normalized
        return normalized.copy()
    except Exception as e:
        get_logger().warning(f"加载全局参数失败: {e}", exc_info=True)
        with _lock:
            _cached = DEFAULT_SETTINGS.copy()
        return _cached.copy()


def save_settings(settings: dict) -> bool:
    """保存全局参数"""
    global _cached
    normalized = _normalize_settings(settings)
    path = get_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock:
            old = _cached.copy()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        _log_settings_changes(old, normalized)
        with _lock:
            _cached = normalized
        old_backend = old.get("capture_backend", DEFAULT_BACKEND)
        new_backend = normalized["capture_backend"]
        if old_backend != new_backend:
            from screen_capture import on_backend_changed
            on_backend_changed(old_backend, new_backend)
        get_logger().debug(
            f"全局参数已保存: mode={'global' if normalized['global_mode'] else 'window'}, "
            f"processes={len(normalized['processes'])}, "
            f"scan_ms={normalized['scan_interval_ms']}, "
            f"backend={normalized['capture_backend']}, "
            f"log_level={normalized['log_level']}"
        )
        return True
    except Exception as e:
        get_logger().error(f"保存全局参数失败: {e}", exc_info=True)
        return False


def get_global_mode() -> bool:
    with _lock:
        return bool(_cached.get("global_mode", True))


def get_processes() -> list:
    with _lock:
        return list(_cached.get("processes", []))


def get_scan_interval_ms() -> int:
    with _lock:
        return int(_cached.get("scan_interval_ms", DEFAULT_SCAN_INTERVAL_MS))


def get_backend() -> str:
    with _lock:
        return _cached.get("capture_backend", DEFAULT_BACKEND)


def get_log_level() -> str:
    with _lock:
        return str(_cached.get("log_level", DEFAULT_LOG_LEVEL))


def set_log_level_name(level_name: str) -> bool:
    """持久化并应用日志级别"""
    level = str(level_name).upper()
    if level not in VALID_LOG_LEVELS:
        return False
    with _lock:
        updated = _cached.copy()
    updated["log_level"] = level
    ok = save_settings(updated)
    if ok:
        from logger import log_level_from_name, set_log_level
        set_log_level(log_level_from_name(level))
    return ok


def set_backend(backend: str) -> bool:
    if backend not in (BACKEND_MSS, BACKEND_DXGI):
        return False
    with _lock:
        updated = _cached.copy()
    updated["capture_backend"] = backend
    return save_settings(updated)


def backend_label(backend: str) -> str:
    return BACKEND_LABELS.get(backend, BACKEND_LABELS[DEFAULT_BACKEND])


def backend_from_label(label: str) -> str:
    return _LABEL_TO_BACKEND.get(label, DEFAULT_BACKEND)

