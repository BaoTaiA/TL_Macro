# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from version import APP_VERSION
from window_manager import window_focus_manager
from global_settings import get_scan_interval_ms, get_backend, backend_label
from utils import (
    get_multi_macro_mode_text,
    get_single_macro_mode_text,
    get_image_macro_mode_text,
)


class HomeTab(QWidget):
    """主页标签页 - 仪表盘：版本、统计、启用配置与窗口焦点"""

    CARD_STYLE = """
        QFrame#configCard {
            background-color: #f8f9fa;
            border-radius: 6px;
            border: none;
        }
    """
    STATS_STYLE = """
        QFrame#statsBar {
            background-color: #f0f2f5;
            border-radius: 6px;
            border: none;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from logger import get_logger
        self.logger = get_logger()
        self.parent = parent
        self.config_widgets = []
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

        hero_frame = QFrame()
        hero_frame.setFrameShape(QFrame.NoFrame)
        hero_layout = QVBoxLayout(hero_frame)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        app_title = QLabel("欢迎使用👏")
        app_title.setFont(QFont("微软雅黑", 18, QFont.Bold))
        app_title.setStyleSheet("color: #333;")
        title_row.addWidget(app_title)
        title_row.addStretch()
        version_badge = QLabel(f"v{APP_VERSION}")
        version_badge.setFont(QFont("微软雅黑", 10))
        version_badge.setStyleSheet(
            "color: #0066cc; background: #e7f1ff; padding: 4px 10px; border-radius: 4px;"
        )
        title_row.addWidget(version_badge)
        hero_layout.addLayout(title_row)

        subtitle = QLabel("双击配置文件名称启用配置or禁用配置")
        subtitle.setFont(QFont("微软雅黑", 9))
        subtitle.setStyleSheet("color: #666;")
        hero_layout.addWidget(subtitle)
        main_layout.addWidget(hero_frame)

        self.stats_bar = QFrame()
        self.stats_bar.setObjectName("statsBar")
        self.stats_bar.setStyleSheet(self.STATS_STYLE)
        stats_layout = QHBoxLayout(self.stats_bar)
        stats_layout.setContentsMargins(14, 10, 14, 10)
        self.enabled_count_label = QLabel("已启用配置: 0")
        self.enabled_count_label.setStyleSheet("color: #333; font-weight: bold;")
        self.focus_summary_label = QLabel("窗口焦点: --")
        self.focus_summary_label.setStyleSheet("color: #666;")
        stats_layout.addWidget(self.enabled_count_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.focus_summary_label)
        main_layout.addWidget(self.stats_bar)

        self.enabled_group = QGroupBox("已启用配置")
        enabled_layout = QVBoxLayout()
        enabled_layout.setSpacing(8)
        enabled_layout.setContentsMargins(12, 12, 12, 12)

        self.no_enabled_label = QLabel("当前没有启用的配置，请双击配置列表项启用")
        self.no_enabled_label.setAlignment(Qt.AlignCenter)
        self.no_enabled_label.setWordWrap(True)
        self.no_enabled_label.setStyleSheet("color: #999; padding: 24px;")
        enabled_layout.addWidget(self.no_enabled_label)

        self.config_container = QVBoxLayout()
        self.config_container.setSpacing(10)
        enabled_layout.addLayout(self.config_container)
        enabled_layout.addStretch()
        self.enabled_group.setLayout(enabled_layout)
        main_layout.addWidget(self.enabled_group, 1)

        focus_group = QGroupBox("全局参数")
        focus_layout = QVBoxLayout()
        focus_layout.setSpacing(4)
        focus_layout.setContentsMargins(10, 10, 10, 10)

        self.global_mode_label = QLabel()
        self.window_mode_label = QLabel()
        self.processes_label = QLabel()
        self.macro_params_label = QLabel()
        for lbl in (
            self.global_mode_label,
            self.window_mode_label,
            self.processes_label,
            self.macro_params_label,
        ):
            lbl.setAlignment(Qt.AlignLeft)
            lbl.setWordWrap(True)
            focus_layout.addWidget(lbl)

        focus_group.setLayout(focus_layout)
        main_layout.addWidget(focus_group)

    def _get_macro_executor(self):
        if self.parent and hasattr(self.parent, "macro_executor"):
            return self.parent.macro_executor
        return None

    def _is_any_macro_running(self, config_name):
        executor = self._get_macro_executor()
        if not executor:
            return False
        return (
            executor.is_multi_macro_running(config_name)
            or executor.is_single_macro_running(config_name)
            or executor.is_image_macro_running(config_name)
        )

    def _macro_running_mark(self, config_name, check_fn):
        executor = self._get_macro_executor()
        if executor and check_fn(config_name):
            return " ●"
        return ""

    def _build_config_card(self, name, cfg):
        multi_hotkey = cfg.get("hotkey", "") if cfg else ""
        single_hotkey = cfg.get("single_key_macro", {}).get("hotkey", "") if cfg else ""
        multi_mode = cfg.get("mode", 2) if cfg else 2
        single_mode = cfg.get("single_key_macro", {}).get("mode", 1) if cfg else 1
        image_hotkey = cfg.get("image_macro", {}).get("hotkey", "") if cfg else ""
        image_mode = cfg.get("image_macro", {}).get("mode", 1) if cfg else 1
        skill_count = len(cfg.get("image_macro", {}).get("skills", [])) if cfg else 0

        executor = self._get_macro_executor()
        running = self._is_any_macro_running(name)
        status_text = "运行中" if running else "空闲"
        status_color = "#28a745" if running else "#999"

        config_frame = QFrame()
        config_frame.setObjectName("configCard")
        config_frame.setStyleSheet(self.CARD_STYLE)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setSpacing(6)
        config_layout.setContentsMargins(14, 12, 14, 12)

        header_row = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setFont(QFont("微软雅黑", 10, QFont.Bold))
        name_label.setStyleSheet("color: #333;")
        header_row.addWidget(name_label)
        header_row.addStretch()
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color: {status_color}; font-weight: bold;")
        header_row.addWidget(status_label)
        config_layout.addLayout(header_row)

        if multi_hotkey:
            mode_text = get_multi_macro_mode_text(multi_mode)
            mark = ""
            if executor:
                mark = self._macro_running_mark(name, executor.is_multi_macro_running)
            multi_label = QLabel(f"多键宏: {multi_hotkey}  |  {mode_text}{mark}")
            multi_label.setStyleSheet("color: #333; padding-left: 4px;")
        else:
            multi_label = QLabel("多键宏: 未设置")
            multi_label.setStyleSheet("color: #999; padding-left: 4px;")
        config_layout.addWidget(multi_label)

        if single_hotkey:
            mode_text = get_single_macro_mode_text(single_mode)
            mark = ""
            if executor:
                mark = self._macro_running_mark(name, executor.is_single_macro_running)
            single_label = QLabel(f"单键宏: {single_hotkey}  |  {mode_text}{mark}")
            single_label.setStyleSheet("color: #333; padding-left: 4px;")
        else:
            single_label = QLabel("单键宏: 未设置")
            single_label.setStyleSheet("color: #999; padding-left: 4px;")
        config_layout.addWidget(single_label)

        if image_hotkey:
            mode_text = get_image_macro_mode_text(image_mode)
            mark = ""
            if executor:
                mark = self._macro_running_mark(name, executor.is_image_macro_running)
            image_label = QLabel(
                f"图像宏: {image_hotkey}  |  {mode_text}  |  技能数: {skill_count}{mark}"
            )
            image_label.setStyleSheet("color: #333; padding-left: 4px;")
        else:
            image_label = QLabel("图像宏: 未设置")
            image_label.setStyleSheet("color: #999; padding-left: 4px;")
        config_layout.addWidget(image_label)

        return config_frame

    def _update_focus_summary(self):
        try:
            if window_focus_manager.global_mode:
                self.focus_summary_label.setText("窗口焦点: 全局模式")
                self.focus_summary_label.setStyleSheet("color: #28a745;")
            else:
                procs = window_focus_manager.target_processes
                if not procs:
                    self.focus_summary_label.setText("窗口焦点: 窗口模式（未配置进程）")
                    self.focus_summary_label.setStyleSheet("color: #856404;")
                else:
                    self.focus_summary_label.setText("窗口焦点: 窗口模式")
                    self.focus_summary_label.setStyleSheet("color: #28a745;")
        except Exception:
            self.focus_summary_label.setText("窗口焦点: --")
            self.focus_summary_label.setStyleSheet("color: #666;")

    def _update_focus_details(self):
        try:
            if window_focus_manager.global_mode:
                self.global_mode_label.setText("全局模式：已启用")
                self.global_mode_label.setStyleSheet("color: #28a745; font-weight: bold;")
                self.window_mode_label.setText("")
                self.processes_label.setText("")
                self.macro_params_label.setText(
                    f"图像宏: 扫描间隔 {get_scan_interval_ms()}ms  |  "
                    f"识别引擎 {backend_label(get_backend())}"
                )
                self.macro_params_label.setStyleSheet("color: #333;")
            else:
                self.global_mode_label.setText("全局模式：未启用")
                self.global_mode_label.setStyleSheet("color: #6c757d;")
                procs = sorted(list(window_focus_manager.target_processes))
                if not procs:
                    self.window_mode_label.setText("窗口模式：未配置进程（宏不会执行）")
                    self.window_mode_label.setStyleSheet("color: #856404; font-weight: bold;")
                else:
                    self.window_mode_label.setText("窗口模式：已启用")
                    self.window_mode_label.setStyleSheet("color: #28a745; font-weight: bold;")

                if procs:
                    self.processes_label.setText(f"目标进程: {', '.join(procs)}")
                    self.processes_label.setStyleSheet("color: #333;")
                else:
                    self.processes_label.setText("目标进程: 未设置")
                    self.processes_label.setStyleSheet("color: #999;")

                self.macro_params_label.setText(
                    f"图像宏: 扫描间隔 {get_scan_interval_ms()}ms  |  "
                    f"识别引擎 {backend_label(get_backend())}"
                )
                self.macro_params_label.setStyleSheet("color: #333;")
        except Exception as e:
            self.logger.warning(f"获取全局参数信息失败: {e}", exc_info=True)
            self.global_mode_label.setText("")
            self.window_mode_label.setText("")
            self.processes_label.setText("")
            self.macro_params_label.setText("")

    def load_data(self):
        """加载并刷新主页展示的数据"""
        for widget in self.config_widgets:
            widget.deleteLater()
        self.config_widgets.clear()

        while self.config_container.count() > 0:
            item = self.config_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        enabled = []
        try:
            if self.parent and hasattr(self.parent, "enabled_configs"):
                enabled = sorted(list(self.parent.enabled_configs))
        except Exception as e:
            self.logger.warning(f"获取启用配置失败: {e}", exc_info=True)
            enabled = []

        self.enabled_count_label.setText(f"已启用配置: {len(enabled)}")
        self._update_focus_summary()

        if not enabled:
            self.no_enabled_label.show()
        else:
            self.no_enabled_label.hide()
            for name in enabled:
                cfg = None
                try:
                    if self.parent and hasattr(self.parent, "load_config_by_name"):
                        cfg = self.parent.load_config_by_name(name)
                except Exception as e:
                    self.logger.warning(f"加载配置 {name} 失败: {e}", exc_info=True)
                    cfg = None
                card = self._build_config_card(name, cfg)
                self.config_container.addWidget(card)
                self.config_widgets.append(card)

        self._update_focus_details()
