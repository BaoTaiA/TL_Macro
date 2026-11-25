# -*- coding: utf-8 -*-
"""宏序列录制模块 - 记录键鼠操作及真实时间"""
import queue
import threading
import time
from typing import Callable, Dict, List, Optional, Set

from pynput import keyboard, mouse
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QMainWindow,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont

from logger import get_logger
from key_mapping import key_mapping


def ms_from_seconds(delta_sec: float) -> int:
    """间隔毫秒：与回放 Sleep/QPC 取整一致（向下取整）"""
    if delta_sec <= 0:
        return 0
    return min(9999, int(delta_sec * 1000))


def press_ms_from_seconds(delta_sec: float) -> int:
    """按下持键毫秒：最小 1ms，最大 9999ms"""
    if delta_sec <= 0:
        return 1
    return max(1, min(9999, int(delta_sec * 1000)))


def build_steps_from_actions(actions: List[dict]) -> List[dict]:
    """由 press/release 时间戳批量结算步骤（与 execute_macro_sequence 语义一致）"""
    steps = []
    for i, act in enumerate(actions):
        press_ms = press_ms_from_seconds(act["release_ts"] - act["press_ts"])
        if i + 1 < len(actions):
            interval_ms = ms_from_seconds(
                actions[i + 1]["press_ts"] - act["release_ts"]
            )
        else:
            interval_ms = 0
        steps.append({
            "key": act["key"],
            "press": press_ms,
            "interval": interval_ms,
        })
    return steps


class MacroSequenceRecorder(QObject):
    """宏序列录制引擎 - 事件入队 + 单 worker 顺序处理，停止时批量结算时间"""

    actionRecorded = pyqtSignal(dict)
    intervalUpdated = pyqtSignal(int, int)

    _SENTINEL = object()

    def __init__(self, ignore_mouse_callback: Optional[Callable[[int, int], bool]] = None):
        super().__init__()
        self.logger = get_logger()
        self._ignore_mouse_callback = ignore_mouse_callback
        self._lock = threading.RLock()
        self._recording = False
        self._steps: List[dict] = []
        self._raw_actions: List[dict] = []

        self._event_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None

        self._active_modifiers: Set[str] = set()
        self._pending_keyboard: Dict[str, dict] = {}
        self._pending_mouse: Dict[str, dict] = {}
        self._ui_suppressed_mouse: Set[str] = set()

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def steps(self) -> List[dict]:
        with self._lock:
            return list(self._steps)

    def start(self):
        """开始录制"""
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._steps.clear()
            self._raw_actions.clear()
            self._active_modifiers.clear()
            self._pending_keyboard.clear()
            self._pending_mouse.clear()
            self._ui_suppressed_mouse.clear()

        self._event_queue = queue.Queue()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="MacroRecordWorker",
        )
        self._worker_thread.start()

        self._keyboard_listener = keyboard.Listener(
            on_press=self._enqueue_key_press,
            on_release=self._enqueue_key_release,
        )
        self._mouse_listener = mouse.Listener(on_click=self._enqueue_mouse_click)
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self.logger.info("宏序列录制已开始")

    def stop(self):
        """停止录制：停监听、排空队列、等待 worker 结束并批量结算"""
        with self._lock:
            self._recording = False
            self._pending_keyboard.clear()
            self._pending_mouse.clear()
            self._ui_suppressed_mouse.clear()

        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass

        self._keyboard_listener = None
        self._mouse_listener = None

        try:
            self._event_queue.put(self._SENTINEL, timeout=1.0)
        except queue.Full:
            pass

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None

        self._finalize_steps()
        self.logger.info("宏序列录制已停止")

    def clear(self):
        """清空已录制的步骤"""
        with self._lock:
            self._steps.clear()
            self._raw_actions.clear()

    def _finalize_steps(self):
        with self._lock:
            self._steps = build_steps_from_actions(self._raw_actions)
        self.logger.debug(f"录制结算完成: {len(self._steps)} 步")

    def _enqueue_key_press(self, key):
        if not self.is_recording:
            return
        self._event_queue.put(("key_press", key, time.perf_counter()))

    def _enqueue_key_release(self, key):
        if not self.is_recording:
            return
        self._event_queue.put(("key_release", key, time.perf_counter()))

    def _enqueue_mouse_click(self, x, y, button, pressed):
        if not self.is_recording:
            return
        self._event_queue.put(
            ("mouse_click", x, y, button, pressed, time.perf_counter())
        )

    def _worker_loop(self):
        """单线程顺序处理事件，避免键盘/鼠标回调乱序"""
        while True:
            item = self._event_queue.get()
            if item is self._SENTINEL:
                break
            try:
                self._process_event(item)
            except Exception as e:
                self.logger.error(f"处理录制事件出错: {e}", exc_info=True)

    def _process_event(self, item):
        kind = item[0]
        if kind == "key_press":
            _, key, ts = item
            self._process_key_press(key, ts)
        elif kind == "key_release":
            _, key, ts = item
            self._process_key_release(key, ts)
        elif kind == "mouse_click":
            _, x, y, button, pressed, ts = item
            self._process_mouse_click(x, y, button, pressed, ts)

    def _pynput_key_to_display(self, key) -> str:
        if hasattr(key, "char") and key.char:
            return key.char.upper()
        key_name = str(key).replace("Key.", "").replace("'", "").lower()
        return key_mapping.pynput_keyboard_to_display(key_name)

    def _pynput_button_to_display(self, button) -> str:
        button_name = str(button).replace("Button.", "").lower()
        return key_mapping.pynput_mouse_to_display(button_name)

    def _record_action(self, key: str, press_ts: float, release_ts: float):
        press_ms = press_ms_from_seconds(release_ts - press_ts)
        interval_row = None
        interval_ms = None
        with self._lock:
            self._raw_actions.append({
                "key": key,
                "press_ts": press_ts,
                "release_ts": release_ts,
            })
            if len(self._raw_actions) >= 2:
                prev = self._raw_actions[-2]
                curr = self._raw_actions[-1]
                interval_row = len(self._raw_actions) - 2
                interval_ms = ms_from_seconds(curr["press_ts"] - prev["release_ts"])

        if interval_row is not None:
            self.intervalUpdated.emit(interval_row, interval_ms)
        self.actionRecorded.emit({"key": key, "press": press_ms})
        self.logger.debug(f"录制动作: key={key}, press={press_ms}ms")

    def _process_key_press(self, key, now: float):
        display_name = self._pynput_key_to_display(key)

        with self._lock:
            if key_mapping.is_modifier_key(display_name):
                self._active_modifiers.add(display_name)
                return

            if display_name in self._pending_keyboard:
                return

            self._pending_keyboard[display_name] = {
                "modifiers": set(self._active_modifiers),
                "press_time": now,
            }

    def _process_key_release(self, key, now: float):
        display_name = self._pynput_key_to_display(key)

        with self._lock:
            if key_mapping.is_modifier_key(display_name):
                self._active_modifiers.discard(display_name)
                return

            pending = self._pending_keyboard.pop(display_name, None)
            if pending is None:
                return

        key_string = key_mapping.build_combination_key(
            pending["modifiers"], display_name
        )
        self._record_action(key_string, pending["press_time"], now)

    def _should_ignore_mouse_at(self, x: int, y: int, display_name: str, pressed: bool) -> bool:
        if not self._ignore_mouse_callback:
            return False

        if self._ignore_mouse_callback(x, y):
            if pressed:
                self._ui_suppressed_mouse.add(display_name)
            else:
                self._ui_suppressed_mouse.discard(display_name)
            return True

        if not pressed and display_name in self._ui_suppressed_mouse:
            self._ui_suppressed_mouse.discard(display_name)
            return True

        return False

    def _process_mouse_click(self, x, y, button, pressed, now: float):
        display_name = self._pynput_button_to_display(button)

        if self._should_ignore_mouse_at(x, y, display_name, pressed):
            return

        with self._lock:
            if pressed:
                if display_name in self._pending_mouse:
                    return
                self._pending_mouse[display_name] = {"press_time": now}
            else:
                pending = self._pending_mouse.pop(display_name, None)
                if pending is None:
                    return

        if not pressed:
            self._record_action(display_name, pending["press_time"], now)


class SequenceRecordDialog(QDialog):
    """宏序列录制对话框 - 实时显示录制的按键序列"""

    START_DELAY_MS = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger()
        self.setWindowTitle("录制宏序列")
        self.setMinimumSize(620, 520)
        self.resize(620, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        font = QFont("微软雅黑", 9)
        self.setFont(font)

        self.recorder = MacroSequenceRecorder(
            ignore_mouse_callback=self._should_ignore_mouse
        )
        self.recorder.actionRecorded.connect(self._on_action_recorded)
        self.recorder.intervalUpdated.connect(self._on_interval_updated)
        self._hotkey_was_paused = False
        self._start_pending = False
        self._main_win_was_minimized = False
        self._main_win_minimized_by_us = False

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout()

        hint = QLabel(
            "点击「开始录制」后，按下键盘或鼠标按键。\n"
            "修饰键单独按下不会记录，与主键组合时会录为组合键（如 LCtrl&A）。"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.status_label = QLabel("准备录制")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(self._status_style("#f0f0f0", "#333"))
        layout.addWidget(self.status_label)

        self.record_table = QTableWidget(0, 3)
        self.record_table.setHorizontalHeaderLabels(
            ["按键", "按下时间(ms)", "间隔时间(ms)"]
        )
        header = self.record_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.record_table.setHorizontalHeaderItem(
            1,
            self._header_item(
                "按下时间(ms)",
                "持键时长：从按下到释放",
            ),
        )
        self.record_table.setHorizontalHeaderItem(
            2,
            self._header_item(
                "间隔时间(ms)",
                "上一步释放到下一步按下的等待时间",
            ),
        )
        self.record_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.record_table.setAlternatingRowColors(True)
        self.record_table.verticalHeader().setVisible(False)
        self.record_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.record_table)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始录制")
        self.stop_btn = QPushButton("停止录制")
        self.clear_btn = QPushButton("清空")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.clear_btn)
        layout.addLayout(btn_layout)

        bottom_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.cancel_btn = QPushButton("取消")
        bottom_layout.addWidget(self.ok_btn)
        bottom_layout.addWidget(self.cancel_btn)
        layout.addLayout(bottom_layout)

        self.setLayout(layout)

    @staticmethod
    def _header_item(text: str, tooltip: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(tooltip)
        return item

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn.clicked.connect(self._stop_recording)
        self.clear_btn.clicked.connect(self._clear_recording)
        self.ok_btn.clicked.connect(self._on_accept)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _status_style(bg: str, color: str) -> str:
        return f"""
            QLabel {{
                background-color: {bg};
                border: 1px solid #ccc;
                padding: 12px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 13px;
                font-weight: bold;
                color: {color};
            }}
        """

    def showEvent(self, event):
        super().showEvent(event)
        self._minimize_main_window()
        self.raise_()

    def _should_ignore_mouse(self, x, y) -> bool:
        """忽略对话框区域内的鼠标点击（避免误录 UI 按钮操作）"""
        return self.frameGeometry().contains(x, y)

    def _get_main_window(self):
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QMainWindow):
                return widget
            widget = widget.parentWidget()
        return None

    def _minimize_main_window(self):
        main_win = self._get_main_window()
        if not main_win:
            return
        self._main_win_was_minimized = main_win.isMinimized()
        if not self._main_win_was_minimized:
            main_win.showMinimized()
            self._main_win_minimized_by_us = True
        else:
            self._main_win_minimized_by_us = False

    def _restore_main_window(self):
        if not self._main_win_minimized_by_us:
            return
        main_win = self._get_main_window()
        if main_win:
            main_win.showNormal()
        self._main_win_minimized_by_us = False

    def _pause_hotkey_listener(self):
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, "hotkey_manager"):
            main_window.hotkey_manager.stop_hotkey_listener()
            self._hotkey_was_paused = True

    def _resume_hotkey_listener(self):
        if not self._hotkey_was_paused:
            return
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, "hotkey_manager"):
            main_window.hotkey_manager.start_hotkey_listener()
        self._hotkey_was_paused = False

    def _start_recording(self):
        self._pause_hotkey_listener()
        self._start_pending = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.record_table.setRowCount(0)
        self.status_label.setText("正在启动录制...")
        self.status_label.setStyleSheet(self._status_style("#fff3cd", "#856404"))
        QTimer.singleShot(self.START_DELAY_MS, self._delayed_start_recorder)

    def _delayed_start_recorder(self):
        if not self._start_pending:
            return
        self._start_pending = False
        self.recorder.start()
        self.raise_()
        self._set_recording_status()

    def _set_recording_status(self):
        self.status_label.setText("正在录制...")
        self.status_label.setStyleSheet(self._status_style("#fff3cd", "#856404"))

    def _stop_recording(self):
        self._start_pending = False
        self.recorder.stop()
        self._resume_hotkey_listener()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._refresh_table_from_steps()
        count = self.record_table.rowCount()
        self.status_label.setText(f"录制已停止，共 {count} 步")
        self.status_label.setStyleSheet(self._status_style("#d1ecf1", "#0c5460"))

    def _clear_recording(self):
        self._start_pending = False
        was_recording = self.recorder.is_recording
        if was_recording:
            self.recorder.stop()
            self._resume_hotkey_listener()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

        self.recorder.clear()
        self.record_table.setRowCount(0)
        self.status_label.setText("已清空，可重新开始录制")
        self.status_label.setStyleSheet(self._status_style("#f0f0f0", "#333"))

    def _on_action_recorded(self, step: dict):
        row = self.record_table.rowCount()
        self.record_table.insertRow(row)
        values = [step["key"], step["press"], "-"]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.record_table.setItem(row, col, item)
        self.record_table.scrollToBottom()
        if self.recorder.is_recording:
            self._set_recording_status()

    def _on_interval_updated(self, row_index: int, interval_ms: int):
        if 0 <= row_index < self.record_table.rowCount():
            item = QTableWidgetItem(str(interval_ms))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.record_table.setItem(row_index, 2, item)

    def _refresh_table_from_steps(self):
        steps = self.recorder.steps
        self.record_table.setRowCount(0)
        for step in steps:
            row = self.record_table.rowCount()
            self.record_table.insertRow(row)
            for col, value in enumerate([
                step["key"], step["press"], step["interval"]
            ]):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.record_table.setItem(row, col, item)
        if steps:
            self.record_table.scrollToBottom()

    def _on_accept(self):
        if self.recorder.is_recording or self._start_pending:
            self._stop_recording()

        if not self.recorder.steps:
            QMessageBox.warning(self, "提示", "没有录制的宏步骤，请先录制")
            return

        self.accept()

    def _finish_dialog(self):
        self._restore_main_window()
        self._resume_hotkey_listener()

    def get_recorded_macros(self) -> List[dict]:
        return self.recorder.steps

    def closeEvent(self, event):
        self._start_pending = False
        if self.recorder.is_recording:
            self.recorder.stop()
        self._finish_dialog()
        super().closeEvent(event)

    def reject(self):
        self._start_pending = False
        if self.recorder.is_recording:
            self.recorder.stop()
        self._finish_dialog()
        super().reject()

    def accept(self):
        self._finish_dialog()
        super().accept()
