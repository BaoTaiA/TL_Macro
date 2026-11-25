# -*- coding: utf-8 -*-
"""前台进程历史 - 供添加目标进程时从历史选择"""
import os
import sys
import threading
import time

from window_manager import window_focus_manager

MAX_HISTORY = 10
POLL_INTERVAL = 0.4


def _excluded_processes() -> set:
    names = {"python.exe", "pythonw.exe", "tl_macro.exe"}
    exe = os.path.basename(sys.executable).lower()
    if exe:
        names.add(exe)
    return names


class ProcessHistoryTracker:
    """内存进程历史，最多保留 MAX_HISTORY 条，按进程名去重"""

    def __init__(self):
        self._lock = threading.RLock()
        self._history: list[str] = []

    def record(self, process_name: str) -> None:
        name = (process_name or "").strip()
        if not name:
            return
        if name.lower() in _excluded_processes():
            return
        with self._lock:
            lowered = name.lower()
            self._history = [h for h in self._history if h.lower() != lowered]
            self._history.insert(0, name)
            if len(self._history) > MAX_HISTORY:
                self._history = self._history[:MAX_HISTORY]

    def get_recent(self) -> list[str]:
        with self._lock:
            return list(self._history)


class ProcessHistoryMonitor:
    """后台轮询前台窗口，记录进程切换历史"""

    def __init__(self, tracker: ProcessHistoryTracker):
        self._tracker = tracker
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="ProcessHistoryMonitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        last = ""
        while not self._stop_event.is_set():
            try:
                current = window_focus_manager.get_foreground_process_name()
                if current and current != last:
                    self._tracker.record(current)
                    last = current
            except Exception:
                pass
            self._stop_event.wait(POLL_INTERVAL)


process_history = ProcessHistoryTracker()
process_history_monitor = ProcessHistoryMonitor(process_history)
