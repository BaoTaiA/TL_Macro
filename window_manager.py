# -*- coding: utf-8 -*-
"""窗口焦点管理 - 按前台进程名判断宏是否可执行"""
import ctypes
from ctypes import wintypes
import threading
import time

from logger import get_logger


class WindowFocusManager:
    """窗口焦点管理器"""

    def __init__(self):
        self.logger = get_logger()
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.target_processes = set()
        self.enabled = False
        self.global_mode = True
        self._lock = threading.RLock()
        self._query_cache = None
        self._cache_timestamp = 0
        self._cache_ttl = 0.05
        self._last_execute_allowed = None

    def _invalidate_query_cache(self) -> None:
        self._query_cache = None
        self._cache_timestamp = 0

    def apply_settings(self, global_mode: bool, processes: list) -> None:
        with self._lock:
            self.global_mode = bool(global_mode)
            self.target_processes = {p.lower() for p in processes if p}
            self.enabled = not self.global_mode
            self._invalidate_query_cache()
            self._last_execute_allowed = None
        mode = "global" if global_mode else "window"
        self.logger.debug(
            f"窗口焦点设置: mode={mode}, targets={sorted(self.target_processes)}"
        )

    def set_global_mode(self, enabled: bool) -> None:
        with self._lock:
            self.global_mode = enabled
            if enabled:
                self.enabled = False
            self._invalidate_query_cache()

    def add_target_process(self, process_name: str) -> None:
        with self._lock:
            self.target_processes.add(process_name.lower())
            self._invalidate_query_cache()

    def remove_target_process(self, process_name: str) -> None:
        with self._lock:
            self.target_processes.discard(process_name.lower())
            self._invalidate_query_cache()

    def clear_targets(self) -> None:
        with self._lock:
            self.target_processes.clear()
            self._invalidate_query_cache()

    def get_foreground_process_name(self) -> str:
        """获取当前前台窗口的进程名（如 game.exe）"""
        return self._get_foreground_process_name()

    def _get_foreground_process_name(self) -> str:
        current_time = time.time()
        with self._lock:
            if (
                self._query_cache is not None
                and current_time - self._cache_timestamp < self._cache_ttl
            ):
                return self._query_cache

        try:
            hwnd = self.user32.GetForegroundWindow()
            if not hwnd:
                process_name = ""
            else:
                process_name = self._get_window_process_name(hwnd)
            with self._lock:
                self._query_cache = process_name
                self._cache_timestamp = current_time
            return process_name
        except Exception as e:
            self.logger.error(f"获取前台进程失败: {e}", exc_info=True)
            return ""

    def _get_window_process_name(self, hwnd) -> str:
        if not hwnd:
            return ""
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return ""
        process_handle = self.kernel32.OpenProcess(0x0400, False, process_id.value)
        if not process_handle:
            return ""
        try:
            buff = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            if self.kernel32.QueryFullProcessImageNameW(
                process_handle, 0, buff, ctypes.byref(size)
            ):
                full_path = buff.value
                return full_path.split("\\")[-1] if "\\" in full_path else full_path
        except Exception:
            pass
        finally:
            self.kernel32.CloseHandle(process_handle)
        return ""

    def is_target_window_active(self) -> bool:
        """全局模式放行；窗口模式要求前台进程在目标列表中"""
        with self._lock:
            if self.global_mode or not self.enabled:
                allowed = True
                process_name = ""
            elif not self.target_processes:
                allowed = False
                process_name = ""
            else:
                targets = set(self.target_processes)
                process_name = self._get_foreground_process_name()
                allowed = bool(process_name) and process_name.lower() in targets

        if allowed != self._last_execute_allowed:
            self._last_execute_allowed = allowed
            if self.global_mode or not self.enabled:
                self.logger.debug("窗口焦点: 全局模式，允许执行宏")
            else:
                self.logger.debug(
                    f"窗口焦点: 前台={process_name or '(无)'}, "
                    f"允许执行={'是' if allowed else '否'}"
                )
        return allowed


window_focus_manager = WindowFocusManager()
