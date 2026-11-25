# -*- coding: utf-8 -*-
"""全局参数标签页"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QRadioButton,
    QListWidget, QPushButton, QLabel, QMessageBox, QListWidgetItem,
    QSpinBox, QComboBox, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

import global_settings
from global_settings import (
    load_settings, save_settings, DEFAULT_SCAN_INTERVAL_MS, MAX_TARGET_PROCESSES,
    BACKEND_LABELS, backend_label, backend_from_label, get_backend,
)
from window_manager import window_focus_manager
from process_history import process_history
from logger import get_logger, get_current_log_level, log_level_from_name, set_log_level

_PROCESS_BOX_WIDTH = 240
_LIST_STYLE = """
    QListWidget { padding: 5px; outline: 0px; border: 1px solid #c0c0c0; background: #fff; }
    QListWidget::item { padding: 5px 0; margin: 2px 0; }
    QListWidget::item:selected { background-color: #d3d3d3; color: black; }
    QListWidget:disabled { background: #f5f5f5; color: #888; }
"""


class ProcessHistoryDialog(QDialog):
    """从历史记录选择进程添加"""

    def __init__(self, tab: "GlobalSettingsTab", parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self._add_buttons: list[QPushButton] = []
        self.setWindowTitle("从历史记录添加进程")
        self.setMinimumSize(420, 320)

        layout = QVBoxLayout(self)
        hint = QLabel("以下为最近使用的前台进程，点击「添加」加入生效列表")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        recent = process_history.get_recent()
        existing = {
            self.tab.process_list.item(i).text().lower()
            for i in range(self.tab.process_list.count())
        }
        at_limit = self.tab.process_list.count() >= MAX_TARGET_PROCESSES

        if not recent:
            empty = QLabel("暂无历史记录，请先切换到目标应用程序后再试")
            empty.setStyleSheet("QLabel { color: #888; padding: 16px 0; }")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        else:
            self.table = QTableWidget(len(recent), 3)
            self.table.setHorizontalHeaderLabels(["序号", "进程名称", "操作"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionMode(QTableWidget.NoSelection)
            self.table.setStyleSheet("""
                QTableWidget { outline: 0px; }
                QTableWidget::item { padding: 4px; }
            """)

            for row, process_name in enumerate(recent):
                self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                self.table.setItem(row, 1, QTableWidgetItem(process_name))
                btn = QPushButton("添加")
                if process_name.lower() in existing:
                    btn.setEnabled(False)
                    btn.setToolTip("该进程已在生效列表中")
                elif at_limit:
                    btn.setEnabled(False)
                    btn.setToolTip(f"最多添加 {MAX_TARGET_PROCESSES} 个进程")
                btn.clicked.connect(
                    lambda _checked=False, name=process_name, button=btn: self._add_process(name, button)
                )
                self._add_buttons.append(btn)
                self.table.setCellWidget(row, 2, btn)

            layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_process(self, process_name: str, button: QPushButton) -> None:
        if self.tab.process_list.count() >= MAX_TARGET_PROCESSES:
            QMessageBox.information(
                self, "提示", f"最多只能添加 {MAX_TARGET_PROCESSES} 个进程"
            )
            self._disable_all_add_buttons()
            return
        if self.tab.process_list.findItems(process_name, Qt.MatchExactly):
            QMessageBox.information(self, "提示", "该进程名已存在")
            button.setEnabled(False)
            return
        self.tab.process_list.addItem(QListWidgetItem(process_name))
        self.tab.logger.info(f"全局参数: 添加目标进程 {process_name}")
        self.tab._persist()
        self.tab._update_focus_mode_ui()
        button.setEnabled(False)
        button.setToolTip("已添加")
        if self.tab.process_list.count() >= MAX_TARGET_PROCESSES:
            self._disable_all_add_buttons()

    def _disable_all_add_buttons(self) -> None:
        tip = f"最多添加 {MAX_TARGET_PROCESSES} 个进程"
        for btn in self._add_buttons:
            if btn.isEnabled():
                btn.setEnabled(False)
                btn.setToolTip(tip)


class GlobalSettingsTab(QWidget):
    """全局参数标签页"""

    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.logger = get_logger()
        self.is_loading = False
        self._editable = True
        self._scan_persist_timer = QTimer(self)
        self._scan_persist_timer.setSingleShot(True)
        self._scan_persist_timer.setInterval(400)
        self._scan_persist_timer.timeout.connect(self._persist)
        self.init_ui()
        self.load_config()

    def init_ui(self):
        layout = QVBoxLayout(self)

        focus_group = QGroupBox("焦点控制（指定进程生效或全局生效）")
        focus_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        focus_grid = QGridLayout()
        focus_grid.setHorizontalSpacing(8)
        focus_grid.setVerticalSpacing(6)
        focus_grid.setColumnMinimumWidth(0, 280)

        self.global_mode_radio = QRadioButton("全局模式：在所有应用程序中生效")
        self.window_mode_radio = QRadioButton("窗口模式：只在指定应用程序中生效")
        self.global_mode_radio.setChecked(True)

        self.process_list = QListWidget()
        self.process_list.setFixedWidth(_PROCESS_BOX_WIDTH)
        self.process_list.setMinimumHeight(80)
        self.process_list.setMaximumHeight(120)
        self.process_list.setStyleSheet(_LIST_STYLE)
        self.process_list.setToolTip(
            f"窗口模式最多 {MAX_TARGET_PROCESSES} 个进程，至少 1 个后生效"
        )

        self.add_process_btn = QPushButton("添加")
        self.remove_process_btn = QPushButton("删除")
        proc_btn_widget = QWidget()
        proc_btn_col = QVBoxLayout(proc_btn_widget)
        proc_btn_col.setContentsMargins(0, 0, 0, 0)
        proc_btn_col.setSpacing(6)
        proc_btn_col.addWidget(self.add_process_btn)
        proc_btn_col.addWidget(self.remove_process_btn)
        proc_btn_col.addStretch()

        focus_grid.addWidget(self.global_mode_radio, 0, 0, Qt.AlignTop)
        focus_grid.addWidget(self.window_mode_radio, 1, 0, Qt.AlignTop)
        focus_grid.addWidget(self.process_list, 0, 1, 2, 1, Qt.AlignTop)
        focus_grid.addWidget(proc_btn_widget, 0, 2, 2, 1, Qt.AlignTop)
        focus_grid.setColumnStretch(3, 1)

        focus_group.setLayout(focus_grid)
        layout.addWidget(focus_group)

        macro_group = QGroupBox("图像宏参数")
        macro_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        macro_layout = QHBoxLayout()
        macro_layout.addWidget(QLabel("扫描间隔(ms):"))
        self.scan_interval_spin = QSpinBox()
        self.scan_interval_spin.setRange(30, 500)
        self.scan_interval_spin.setValue(DEFAULT_SCAN_INTERVAL_MS)
        self.scan_interval_spin.valueChanged.connect(self._schedule_scan_persist)
        macro_layout.addWidget(self.scan_interval_spin)
        macro_layout.addWidget(QLabel("识别引擎:"))
        self.capture_engine_combo = QComboBox()
        for label in BACKEND_LABELS.values():
            self.capture_engine_combo.addItem(label)
        self.capture_engine_combo.setToolTip(
            "GDI 适合窗口模式与小区域；DXGI 适合全屏 DirectX 游戏"
        )
        self.capture_engine_combo.currentIndexChanged.connect(self._on_capture_engine_changed)
        macro_layout.addWidget(self.capture_engine_combo)
        macro_layout.addStretch()
        macro_group.setLayout(macro_layout)
        layout.addWidget(macro_group)

        log_group = QGroupBox("日志级别")
        log_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        log_layout = QHBoxLayout()
        log_layout.addWidget(QLabel("日志级别:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        current_level = get_current_log_level()
        idx = self.log_level_combo.findText(current_level)
        if idx >= 0:
            self.log_level_combo.setCurrentIndex(idx)
        self.log_level_combo.setMaximumWidth(110)
        self.log_level_combo.currentTextChanged.connect(self._on_log_level_changed)
        log_layout.addWidget(self.log_level_combo)
        log_layout.addStretch()
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        layout.addStretch()

        self.global_mode_radio.toggled.connect(self._on_mode_changed)
        self.window_mode_radio.toggled.connect(self._on_mode_changed)
        self.add_process_btn.clicked.connect(self.add_process)
        self.remove_process_btn.clicked.connect(self.remove_process)
        self._update_focus_mode_ui()

    def _update_focus_mode_ui(self) -> None:
        """全局/窗口模式联动：进程列表与按钮启用状态"""
        if not self._editable:
            return
        is_global = self.global_mode_radio.isChecked()
        self.process_list.setEnabled(not is_global)
        self.remove_process_btn.setEnabled(not is_global)
        if is_global:
            self.add_process_btn.setEnabled(False)
            self.add_process_btn.setToolTip("")
        else:
            at_limit = self.process_list.count() >= MAX_TARGET_PROCESSES
            self.add_process_btn.setEnabled(not at_limit)
            if at_limit:
                self.add_process_btn.setToolTip(f"最多添加 {MAX_TARGET_PROCESSES} 个进程")
            else:
                self.add_process_btn.setToolTip("")

    def _collect_settings(self) -> dict:
        processes = [self.process_list.item(i).text() for i in range(self.process_list.count())]
        return {
            "global_mode": self.global_mode_radio.isChecked(),
            "processes": processes,
            "scan_interval_ms": self.scan_interval_spin.value(),
            "capture_backend": backend_from_label(self.capture_engine_combo.currentText()),
            "log_level": global_settings.get_log_level(),
        }

    def _apply_to_runtime(self, settings: dict) -> None:
        window_focus_manager.apply_settings(
            settings["global_mode"], settings["processes"]
        )
        mode = "global" if settings["global_mode"] else "window"
        self.logger.debug(
            f"全局参数已应用到运行时: mode={mode}, "
            f"processes={settings.get('processes', [])}"
        )

    def _focus_settings_changed(self, new: dict) -> bool:
        return (
            new["global_mode"] != global_settings.get_global_mode()
            or new["processes"] != global_settings.get_processes()
        )

    def _persist(self) -> None:
        if self.is_loading:
            return
        settings = self._collect_settings()
        focus_changed = self._focus_settings_changed(settings)
        if save_settings(settings):
            if focus_changed:
                self._apply_to_runtime(settings)
            self.configChanged.emit()
        self._update_focus_mode_ui()

    def _schedule_scan_persist(self, _value=None):
        self._scan_persist_timer.start()

    def _on_capture_engine_changed(self, _index):
        self._persist()

    def _on_mode_changed(self):
        self._persist()
        self._update_focus_mode_ui()

    def _on_log_level_changed(self, level_text: str) -> None:
        global_settings.set_log_level_name(level_text)

    def add_process(self):
        if self.process_list.count() >= MAX_TARGET_PROCESSES:
            QMessageBox.information(
                self, "提示", f"最多只能添加 {MAX_TARGET_PROCESSES} 个进程"
            )
            return
        ProcessHistoryDialog(self, self).exec_()

    def remove_process(self):
        current_item = self.process_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择要删除的进程")
            return
        row = self.process_list.row(current_item)
        removed = current_item.text()
        self.process_list.takeItem(row)
        self.logger.info(f"全局参数: 移除目标进程 {removed}")
        self._persist()

    def load_config(self):
        self.is_loading = True
        truncated = False
        try:
            settings = load_settings()
            self.global_mode_radio.blockSignals(True)
            self.window_mode_radio.blockSignals(True)
            self.scan_interval_spin.blockSignals(True)
            self.capture_engine_combo.blockSignals(True)
            self.log_level_combo.blockSignals(True)

            if settings.get("global_mode", True):
                self.global_mode_radio.setChecked(True)
            else:
                self.window_mode_radio.setChecked(True)

            processes = settings.get("processes", [])
            if len(processes) > MAX_TARGET_PROCESSES:
                processes = processes[:MAX_TARGET_PROCESSES]
                truncated = True

            self.process_list.clear()
            for process in processes:
                self.process_list.addItem(QListWidgetItem(process))

            self.scan_interval_spin.setValue(int(settings.get("scan_interval_ms", DEFAULT_SCAN_INTERVAL_MS)))
            label = backend_label(settings.get("capture_backend", get_backend()))
            idx = self.capture_engine_combo.findText(label)
            if idx >= 0:
                self.capture_engine_combo.setCurrentIndex(idx)

            log_level = settings.get("log_level", global_settings.DEFAULT_LOG_LEVEL)
            log_idx = self.log_level_combo.findText(log_level)
            if log_idx >= 0:
                self.log_level_combo.setCurrentIndex(log_idx)
            set_log_level(log_level_from_name(log_level))

            self.global_mode_radio.blockSignals(False)
            self.window_mode_radio.blockSignals(False)
            self.scan_interval_spin.blockSignals(False)
            self.capture_engine_combo.blockSignals(False)
            self.log_level_combo.blockSignals(False)

            if truncated:
                save_settings(self._collect_settings())
                self._apply_to_runtime(self._collect_settings())
            else:
                self._apply_to_runtime(settings)
            self._update_focus_mode_ui()
        finally:
            self.is_loading = False

    def set_editable(self, enabled: bool):
        """有启用配置时整页置灰"""
        self._editable = enabled
        widgets = (
            self.global_mode_radio, self.window_mode_radio,
            self.process_list, self.add_process_btn, self.remove_process_btn,
            self.scan_interval_spin, self.capture_engine_combo,
            self.log_level_combo,
        )
        for w in widgets:
            w.setEnabled(enabled)
        if enabled:
            self._update_focus_mode_ui()
