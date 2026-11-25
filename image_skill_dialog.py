# -*- coding: utf-8 -*-
"""技能编辑对话框"""
import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QMessageBox, QTextEdit, QDialogButtonBox, QMainWindow, QRadioButton,
    QButtonGroup, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap

from hotkey import RecordHotkeyDialog
from screenshot_overlay import ScreenshotOverlay
from image_recognizer import (
    DEFAULT_RECOGNITION, DEFAULT_BUFF_RECOGNITION, DEFAULT_RECOVERY_MS,
    DEFAULT_EXECUTE_INTERVAL_MS, DEFAULT_ENSURE_PRESS_TIMEOUT_MS,
    DEFAULT_ENSURE_PRESS_RETRIES, MIN_PRIORITY, MAX_PRIORITY, clamp_skill_priority,
    IconMatcher, RegionIconMatcher, bgr_to_qpixmap, load_template_preview,
    resolve_buff_region, normalize_skill_precondition, normalize_image_skill,
    migrate_post_buff_icon_path, TRIGGER_MODE_PRESENT, TRIGGER_MODE_ABSENT,
    SKILL_KIND_ATTACK, SKILL_KIND_BUFF, resolve_skill_kind, MAX_SKILL_ICONS,
)
from asset_manager import (
    get_skill_icon_rel_path, get_buff_icon_rel_path,
    get_buff_region_preview_rel_path,
    save_icon_image, generate_skill_id,
)
from logger import get_logger
from screen_capture import CaptureUnavailableError, grab_region, release_thread_capture
from utils import pause_memory_cleanup, resume_memory_cleanup


BUFF_REGION_PREVIEW_H = 80


class DetectTestWorker(QThread):
    """后台执行截屏+模板匹配，避免阻塞 UI"""

    finished_with_result = pyqtSignal(object)
    finished_with_error = pyqtSignal(str)

    def __init__(self, matchers, labels=None, parent=None):
        """matchers: IconMatcher/RegionIconMatcher 列表；labels 与之对应（如图标序号）"""
        super().__init__(parent)
        if not isinstance(matchers, (list, tuple)):
            matchers = [matchers]
        self.matchers = list(matchers)
        self.labels = list(labels) if labels is not None else list(range(len(self.matchers)))

    def run(self):
        try:
            results = []
            for label, matcher in zip(self.labels, self.matchers):
                results.append((label, matcher.detect()))
            self.finished_with_result.emit(results)
        except CaptureUnavailableError:
            self.finished_with_error.emit(
                "截屏暂时不可用（DXGI 重建中），请稍后重试"
            )
        except Exception as e:
            self.finished_with_error.emit(str(e))
        finally:
            release_thread_capture()


class ImageSkillDialog(QDialog):
    """新增/编辑技能对话框"""

    def __init__(
        self,
        parent=None,
        skill_data=None,
        config_name="",
        config_dir="config",
        check_key_conflict=None,
        check_priority_conflict=None,
        on_skill_commit=None,
        default_skill_kind=SKILL_KIND_ATTACK,
    ):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.config_name = config_name
        self.config_dir = config_dir
        self.check_key_conflict = check_key_conflict
        self.check_priority_conflict = check_priority_conflict
        self._on_skill_commit = on_skill_commit
        self.skill_data = skill_data.copy() if skill_data else None
        self._default_skill_kind = default_skill_kind or SKILL_KIND_ATTACK
        self._icon_imgs = [None] * MAX_SKILL_ICONS
        self._icon_metas = [{} for _ in range(MAX_SKILL_ICONS)]
        self._icon_dirty = [False] * MAX_SKILL_ICONS
        self._buff_img = None
        self._buff_region_img = None
        self._buff_meta = {}
        self._buff_region_meta = {}
        self._screenshot_overlay = None
        self._result_skill = None
        self._detect_worker = None
        self._memory_paused = False
        self._main_win_was_minimized = False
        self._main_win_minimized_by_us = False
        self.logger = get_logger()
        pause_memory_cleanup()
        self._memory_paused = True
        self.finished.connect(self._resume_memory_cleanup)
        self.init_ui()
        if self.skill_data:
            self._load_skill(self.skill_data)

    def _resume_memory_cleanup(self, *_args):
        if self._memory_paused:
            resume_memory_cleanup()
            self._memory_paused = False

    def init_ui(self):
        self.setWindowTitle("技能设置")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.skill_tab = QWidget()
        self.precond_tab = QWidget()
        self.tabs.addTab(self.skill_tab, "技能设置")
        self.tabs.addTab(self.precond_tab, "前置条件")
        layout.addWidget(self.tabs)

        self._build_skill_tab()
        self._build_precond_tab()
        self.precond_enabled.toggled.connect(self._on_precond_enabled_changed)
        self.trigger_present.toggled.connect(self._update_wait_label)
        self.trigger_absent.toggled.connect(self._update_wait_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setText("保存")
        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        layout.addLayout(btn_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        layout.addWidget(self.log_text)

    def _build_skill_tab(self):
        form = QFormLayout(self.skill_tab)

        kind_row = QHBoxLayout()
        self.kind_group = QButtonGroup(self)
        self.kind_attack = QRadioButton("普通技能")
        self.kind_buff = QRadioButton("Buff技能")
        self.kind_group.addButton(self.kind_attack)
        self.kind_group.addButton(self.kind_buff)
        if self._default_skill_kind == SKILL_KIND_BUFF:
            self.kind_buff.setChecked(True)
        else:
            self.kind_attack.setChecked(True)
        kind_row.addWidget(self.kind_attack)
        kind_row.addWidget(self.kind_buff)
        kind_row.addStretch()
        form.addRow("技能类型:", kind_row)

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        form.addRow("技能名称:", self.name_edit)

        key_row = QHBoxLayout()
        self.key_label = QLabel("未设置")
        self.key_label.setAlignment(Qt.AlignCenter)
        self.key_label.setStyleSheet("background:#f0f0f0;border:1px solid #ccc;padding:6px;")
        self.set_key_btn = QPushButton("设置按键")
        self.set_key_btn.clicked.connect(self.set_skill_key)
        key_row.addWidget(self.key_label, 1)
        key_row.addWidget(self.set_key_btn)
        form.addRow("技能按键:", key_row)

        self.icon_previews = []
        self.capture_icon_btns = []
        self.clear_icon_btns = []
        for i in range(MAX_SKILL_ICONS):
            icon_row = QHBoxLayout()
            preview = QLabel("无图标")
            preview.setFixedSize(64, 64)
            preview.setAlignment(Qt.AlignCenter)
            preview.setStyleSheet("border:1px solid #ccc;background:#f8f8f8;")
            capture_btn = QPushButton("框选截图")
            clear_btn = QPushButton("清除")
            idx = i
            capture_btn.clicked.connect(lambda _=False, n=idx: self.capture_icon(f"skill_{n}"))
            clear_btn.clicked.connect(lambda _=False, n=idx: self.clear_icon(f"skill_{n}"))
            icon_row.addWidget(preview)
            icon_row.addWidget(capture_btn)
            icon_row.addWidget(clear_btn)
            label = "技能图标:" if i == 0 else f"技能图标{i + 1}:"
            form.addRow(label, icon_row)
            self.icon_previews.append(preview)
            self.capture_icon_btns.append(capture_btn)
            self.clear_icon_btns.append(clear_btn)
        # 兼容旧测试按钮引用
        self.icon_preview = self.icon_previews[0]
        self.capture_icon_btn = self.capture_icon_btns[0]
        self.clear_icon_btn = self.clear_icon_btns[0]

        self.press_spin = QSpinBox()
        self.press_spin.setRange(10, 9999)
        self.press_spin.setValue(50)
        form.addRow("按下时间(ms):", self.press_spin)

        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 30)
        self.repeat_spin.setValue(1)
        form.addRow("重复次数:", self.repeat_spin)

        self.repeat_interval_spin = QSpinBox()
        self.repeat_interval_spin.setRange(10, 9999)
        self.repeat_interval_spin.setValue(100)
        form.addRow("重复间隔(ms):", self.repeat_interval_spin)

        self.recovery_spin = QSpinBox()
        self.recovery_spin.setRange(0, 9999)
        self.recovery_spin.setValue(DEFAULT_RECOVERY_MS)
        form.addRow("技能后摇(ms):", self.recovery_spin)

        self.execute_interval_spin = QSpinBox()
        self.execute_interval_spin.setRange(0, 99999)
        self.execute_interval_spin.setValue(DEFAULT_EXECUTE_INTERVAL_MS)
        self.execute_interval_spin.setToolTip(
            "与后摇取较大值作为该技能自身冷却；不再阻塞其它技能扫描"
        )
        form.addRow("执行间隔(ms):", self.execute_interval_spin)

        self.ensure_press_check = QCheckBox("严格模式")
        form.addRow("", self.ensure_press_check)
        self.ensure_timeout_spin = QSpinBox()
        self.ensure_timeout_spin.setRange(50, 99999)
        self.ensure_timeout_spin.setValue(DEFAULT_ENSURE_PRESS_TIMEOUT_MS)
        form.addRow("严格超时(ms):", self.ensure_timeout_spin)
        self.ensure_retries_spin = QSpinBox()
        self.ensure_retries_spin.setRange(0, 10)
        self.ensure_retries_spin.setValue(DEFAULT_ENSURE_PRESS_RETRIES)
        form.addRow("严格重试次数:", self.ensure_retries_spin)
        self.ensure_press_check.toggled.connect(self._on_ensure_press_toggled)
        self._on_ensure_press_toggled(False)

        priority_row = QHBoxLayout()
        self.priority_enabled = QCheckBox("设置优先级")
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(MIN_PRIORITY, MAX_PRIORITY)
        self.priority_spin.setValue(5)
        self.priority_spin.setEnabled(False)
        self.priority_enabled.toggled.connect(self._on_priority_enabled_changed)
        priority_row.addWidget(self.priority_enabled)
        priority_row.addWidget(self.priority_spin)
        priority_row.addStretch()
        form.addRow("优先级(1-10, 10最高):", priority_row)

        self.skill_conf = QDoubleSpinBox()
        self.skill_conf.setRange(0.5, 1.0)
        self.skill_conf.setSingleStep(0.05)
        self.skill_conf.setValue(DEFAULT_RECOGNITION["confidence"])
        self.skill_tol = QSpinBox()
        self.skill_tol.setRange(5, 100)
        self.skill_tol.setValue(DEFAULT_RECOGNITION["position_tolerance"])
        self.skill_margin = QSpinBox()
        self.skill_margin.setRange(20, 200)
        self.skill_margin.setValue(DEFAULT_RECOGNITION["search_margin"])
        self.skill_bright = QSpinBox()
        self.skill_bright.setRange(1, 255)
        self.skill_bright.setValue(DEFAULT_RECOGNITION["brightness_threshold"])
        form.addRow("置信度阈值:", self.skill_conf)
        form.addRow("位置容差(px):", self.skill_tol)
        form.addRow("搜索扩展(px):", self.skill_margin)
        form.addRow("亮度阈值:", self.skill_bright)

        self.skill_test_btn = QPushButton("测试识别")
        self.skill_test_btn.clicked.connect(lambda: self.start_test("skill"))
        form.addRow("", self.skill_test_btn)

    def _on_ensure_press_toggled(self, enabled):
        self.ensure_timeout_spin.setEnabled(enabled)
        self.ensure_retries_spin.setEnabled(enabled)

    def _build_precond_tab(self):
        form = QFormLayout(self.precond_tab)

        self.precond_enabled = QCheckBox("启用 buff 前置")
        form.addRow("", self.precond_enabled)

        mode_row = QHBoxLayout()
        self.trigger_mode_group = QButtonGroup(self)
        self.trigger_present = QRadioButton("存在触发")
        self.trigger_absent = QRadioButton("不在触发")
        self.trigger_present.setChecked(True)
        self.trigger_mode_group.addButton(self.trigger_present)
        self.trigger_mode_group.addButton(self.trigger_absent)
        mode_row.addWidget(self.trigger_present)
        mode_row.addWidget(self.trigger_absent)
        form.addRow("触发模式:", mode_row)

        self.buff_name_edit = QLineEdit()
        self.buff_name_edit.setMaxLength(6)
        self.buff_name_edit.setPlaceholderText("最多6个字符")
        form.addRow("Buff 名称:", self.buff_name_edit)

        region_block = QVBoxLayout()
        self.buff_region_preview = QLabel("未设置")
        self.buff_region_preview.setFixedHeight(BUFF_REGION_PREVIEW_H)
        self.buff_region_preview.setMinimumWidth(120)
        self.buff_region_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.buff_region_preview.setAlignment(Qt.AlignCenter)
        self.buff_region_preview.setScaledContents(False)
        self.buff_region_preview.setStyleSheet("border:1px solid #ccc;background:#f8f8f8;")
        region_block.addWidget(self.buff_region_preview)
        region_btn_row = QHBoxLayout()
        self.capture_buff_region_btn = QPushButton("框选 Buff 区域")
        self.capture_buff_region_btn.clicked.connect(lambda: self.capture_icon("buff_region"))
        self.clear_buff_region_btn = QPushButton("清除")
        self.clear_buff_region_btn.clicked.connect(self.clear_buff_region)
        region_btn_row.addWidget(self.capture_buff_region_btn)
        region_btn_row.addWidget(self.clear_buff_region_btn)
        region_btn_row.addStretch()
        region_block.addLayout(region_btn_row)
        form.addRow("Buff 搜索区域:", region_block)

        buff_row = QHBoxLayout()
        self.buff_preview = QLabel("无图标")
        self.buff_preview.setFixedSize(64, 64)
        self.buff_preview.setAlignment(Qt.AlignCenter)
        self.buff_preview.setStyleSheet("border:1px solid #ccc;background:#f8f8f8;")
        self.capture_buff_btn = QPushButton("截取Buff")
        self.capture_buff_btn.clicked.connect(lambda: self.capture_icon("buff"))
        self.clear_buff_btn = QPushButton("清除")
        self.clear_buff_btn.clicked.connect(lambda: self.clear_icon("buff"))
        buff_row.addWidget(self.buff_preview)
        buff_row.addWidget(self.capture_buff_btn)
        buff_row.addWidget(self.clear_buff_btn)
        form.addRow("Buff 图标:", buff_row)

        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(10, 5000)
        self.wait_spin.setValue(300)
        self.wait_label = QLabel("Buff 出现后等待(ms):")
        form.addRow(self.wait_label, self.wait_spin)

        self.buff_conf = QDoubleSpinBox()
        self.buff_conf.setRange(0.5, 1.0)
        self.buff_conf.setSingleStep(0.05)
        self.buff_conf.setValue(DEFAULT_BUFF_RECOGNITION["confidence"])
        form.addRow("Buff 置信度:", self.buff_conf)

        self.buff_test_btn = QPushButton("测试识别")
        self.buff_test_btn.clicked.connect(lambda: self.start_test("buff"))
        form.addRow("", self.buff_test_btn)

        self._on_precond_enabled_changed(self.precond_enabled.isChecked())
        self._update_wait_label()

    def _on_priority_enabled_changed(self, enabled):
        self.priority_spin.setEnabled(enabled)

    def _on_precond_enabled_changed(self, enabled):
        for w in (
            self.trigger_present, self.trigger_absent,
            self.buff_name_edit, self.capture_buff_region_btn, self.clear_buff_region_btn,
            self.capture_buff_btn, self.clear_buff_btn,
            self.wait_spin, self.buff_conf, self.buff_test_btn,
        ):
            w.setEnabled(enabled)

    def _update_wait_label(self):
        if self.trigger_absent.isChecked():
            self.wait_label.setText("Buff 消失后等待(ms):")
        else:
            self.wait_label.setText("Buff 出现后等待(ms):")

    def _get_trigger_mode(self):
        return TRIGGER_MODE_ABSENT if self.trigger_absent.isChecked() else TRIGGER_MODE_PRESENT

    def _load_skill(self, skill):
        skill = normalize_image_skill(skill)
        if resolve_skill_kind(skill) == SKILL_KIND_BUFF:
            self.kind_buff.setChecked(True)
        else:
            self.kind_attack.setChecked(True)
        self.name_edit.setText(skill.get("name", ""))
        key = skill.get("key", "")
        self.key_label.setText(key if key else "未设置")
        self.press_spin.setValue(skill.get("press_time", 50))
        self.repeat_spin.setValue(skill.get("repeat_count", 1))
        self.repeat_interval_spin.setValue(skill.get("repeat_interval", 100))
        self.recovery_spin.setValue(skill.get("recovery_ms", DEFAULT_RECOVERY_MS))
        self.execute_interval_spin.setValue(
            skill.get("execute_interval_ms", DEFAULT_EXECUTE_INTERVAL_MS)
        )
        self.ensure_press_check.setChecked(bool(skill.get("ensure_press")))
        self.ensure_timeout_spin.setValue(
            skill.get("ensure_press_timeout_ms", DEFAULT_ENSURE_PRESS_TIMEOUT_MS)
        )
        self.ensure_retries_spin.setValue(
            skill.get("ensure_press_retries", DEFAULT_ENSURE_PRESS_RETRIES)
        )
        self._on_ensure_press_toggled(self.ensure_press_check.isChecked())

        priority = clamp_skill_priority(skill.get("priority"))
        if priority is not None:
            self.priority_enabled.setChecked(True)
            self.priority_spin.setValue(priority)
        else:
            self.priority_enabled.setChecked(False)
            self.priority_spin.setValue(5)

        rec = skill.get("recognition", {})
        self.skill_conf.setValue(rec.get("confidence", 0.85))
        self.skill_tol.setValue(rec.get("position_tolerance", 30))
        self.skill_margin.setValue(rec.get("search_margin", 80))
        self.skill_bright.setValue(rec.get("brightness_threshold", 80))

        icons = skill.get("icons") or []
        for i in range(MAX_SKILL_ICONS):
            self._icon_imgs[i] = None
            self._icon_metas[i] = {}
            self._icon_dirty[i] = False
            self.icon_previews[i].setText("无图标")
            self.icon_previews[i].setPixmap(QPixmap())
            if i < len(icons) and icons[i].get("path"):
                img = load_template_preview(icons[i]["path"], self.config_dir)
                if img is not None:
                    self._icon_imgs[i] = img
                    self._icon_metas[i] = {
                        "x": icons[i].get("x", 0),
                        "y": icons[i].get("y", 0),
                        "path": icons[i].get("path", ""),
                    }
                    self.icon_previews[i].setPixmap(bgr_to_qpixmap(img))

        skill = migrate_post_buff_icon_path(
            normalize_skill_precondition(skill), self.config_dir, self.config_name
        )
        pre = skill.get("precondition", {})
        self.precond_enabled.setChecked(pre.get("enabled", False))
        if pre.get("trigger_mode") == TRIGGER_MODE_ABSENT:
            self.trigger_absent.setChecked(True)
        else:
            self.trigger_present.setChecked(True)
        self._on_precond_enabled_changed(self.precond_enabled.isChecked())
        self._update_wait_label()

        self.buff_name_edit.setText(pre.get("name", ""))
        self.wait_spin.setValue(pre.get("wait_after_buff_ms", 300))
        buff_rec = pre.get("recognition", {})
        self.buff_conf.setValue(buff_rec.get("confidence", 0.85))

        buff_region = pre.get("buff_region", {})
        if buff_region.get("width") and buff_region.get("height"):
            self._buff_region_meta = {
                "x": buff_region.get("x", 0),
                "y": buff_region.get("y", 0),
                "width": buff_region.get("width", 0),
                "height": buff_region.get("height", 0),
            }
            self._update_buff_region_preview()

        buff_icon = pre.get("buff_icon", {})
        if buff_icon.get("path"):
            img = load_template_preview(buff_icon["path"], self.config_dir)
            if img is not None:
                self._buff_img = img
                self.buff_preview.setPixmap(bgr_to_qpixmap(img))

    def _buff_region_preview_bounds(self):
        w = self.buff_region_preview.width()
        if w <= 0:
            w = max(120, self.width() - 140)
        return w, BUFF_REGION_PREVIEW_H

    def _update_buff_region_preview(self):
        w = self._buff_region_meta.get("width", 0)
        h = self._buff_region_meta.get("height", 0)
        if w <= 0 or h <= 0:
            self.buff_region_preview.setText("未设置")
            self.buff_region_preview.setPixmap(QPixmap())
            return

        img = self._buff_region_img
        if img is None:
            skill_id = self.skill_data.get("id") if self.skill_data else None
            if skill_id:
                rel = get_buff_region_preview_rel_path(self.config_name, skill_id)
                img = load_template_preview(rel, self.config_dir)
                if img is not None:
                    self._buff_region_img = img

        if img is None:
            x = int(self._buff_region_meta.get("x", 0))
            y = int(self._buff_region_meta.get("y", 0))
            try:
                img = grab_region(x, y, int(w), int(h))
                self._buff_region_img = img
            except CaptureUnavailableError:
                img = None
            except Exception as e:
                self.logger.warning(f"Buff 搜索区域预览截屏失败: {e}")
                img = None

        if img is not None:
            max_w, max_h = self._buff_region_preview_bounds()
            self.buff_region_preview.setText("")
            self.buff_region_preview.setPixmap(
                bgr_to_qpixmap(
                    img,
                    max_width=max_w,
                    max_height=max_h,
                )
            )
        else:
            self.buff_region_preview.setText("未设置")
            self.buff_region_preview.setPixmap(QPixmap())

    def set_skill_key(self):
        dialog = RecordHotkeyDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.hotkey:
            exclude_id = self.skill_data.get("id") if self.skill_data else None
            if self.check_key_conflict:
                conflict = self.check_key_conflict(dialog.hotkey, exclude_id)
                if conflict:
                    QMessageBox.warning(
                        self, "按键冲突",
                        f"该按键在当前配置中已被用于{conflict[0]}，请选择其他按键",
                    )
                    return
            self.key_label.setText(dialog.hotkey)

    def _get_main_window(self):
        """向上查找 QMainWindow 主窗口"""
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
            self.logger.debug(f"主窗口已最小化: {main_win.__class__.__name__}")
        elif not self._main_win_minimized_by_us:
            # 打开对话框前主窗已最小化，关闭时不应替用户恢复
            self._main_win_minimized_by_us = False
        # else: 主窗已被本对话框最小化，保持 flag=True

    def _restore_main_window(self):
        if not self._main_win_minimized_by_us:
            return
        main_win = self._get_main_window()
        if main_win:
            main_win.showNormal()
            main_win.raise_()
            main_win.activateWindow()
            self.logger.debug(f"主窗口已恢复: {main_win.__class__.__name__}")
        self._main_win_minimized_by_us = False

    def showEvent(self, event):
        super().showEvent(event)
        self._minimize_main_window()
        self.raise_()
        QTimer.singleShot(0, self._update_buff_region_preview)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._buff_region_meta.get("width") and self._buff_region_meta.get("height"):
            self._update_buff_region_preview()

    def capture_icon(self, icon_type):
        try:
            main_win = self._get_main_window()
            self.logger.info(
                f"框选截图开始: icon_type={icon_type}, "
                f"dialog={self.__class__.__name__} geo={self.geometry()}, "
                f"main_win={main_win.__class__.__name__ if main_win else None}"
            )
            self.hide()
            self.logger.debug("技能对话框已隐藏")
            if main_win and not main_win.isMinimized():
                self.logger.info(f"最小化主窗口: {main_win.__class__.__name__} geo={main_win.geometry()}")
                main_win.showMinimized()
                self._main_win_minimized_by_us = True
            QTimer.singleShot(500, lambda: self._show_overlay(icon_type))
        except Exception:
            self.logger.exception("框选截图启动失败")
            self.show()

    def _show_overlay(self, icon_type):
        try:
            self.logger.info(f"定时器触发 _show_overlay: icon_type={icon_type}")
            self._screenshot_overlay = ScreenshotOverlay(
                screenshot_callback=lambda img, rect, cancelled=False: self._on_captured(
                    img, rect, icon_type, cancelled=cancelled
                )
            )
            self.logger.info(
                f"遮罩已创建: visible={self._screenshot_overlay.isVisible()}, "
                f"geometry={self._screenshot_overlay.geometry()}"
            )
        except Exception:
            self.logger.exception("创建截图遮罩失败")
            self._restore_windows_after_capture()

    def _restore_windows_after_capture(self):
        """截图结束后恢复技能对话框（主窗口保持最小化）"""
        self.show()
        self.raise_()
        self.logger.debug("技能对话框已恢复显示")

    def _on_captured(self, img, rect, icon_type, cancelled=False):
        self._screenshot_overlay = None
        try:
            if cancelled:
                self.logger.info(f"框选截图已取消: icon_type={icon_type}")
                self._restore_windows_after_capture()
                return
            if img is None:
                self.logger.warning(f"框选截屏失败: icon_type={icon_type}")
                self._restore_windows_after_capture()
                QTimer.singleShot(
                    0,
                    lambda: QMessageBox.warning(
                        self,
                        "提示",
                        "截屏失败，请重试；若持续失败可在全局参数切换到 GDI (mss)",
                    ),
                )
                return
            self.logger.info(
                f"框选截图成功: icon_type={icon_type}, "
                f"选区=({rect.x()}, {rect.y()}, {rect.width()}x{rect.height()})"
            )
            h, w = img.shape[:2]
            meta = {"x": rect.x(), "y": rect.y(), "width": w, "height": h}
            if icon_type.startswith("skill"):
                idx = 0
                if "_" in icon_type:
                    try:
                        idx = int(icon_type.split("_", 1)[1])
                    except ValueError:
                        idx = 0
                idx = max(0, min(MAX_SKILL_ICONS - 1, idx))
                self._icon_imgs[idx] = img
                self._icon_metas[idx] = meta
                self._icon_dirty[idx] = True
                self.icon_previews[idx].setPixmap(bgr_to_qpixmap(img))
            elif icon_type == "buff_region":
                self._buff_region_img = img
                self._buff_region_meta = meta
                self._update_buff_region_preview()
            elif icon_type == "buff":
                self._buff_img = img
                self._buff_meta = meta
                self.buff_preview.setPixmap(bgr_to_qpixmap(img))
            self._restore_windows_after_capture()
        except Exception:
            self.logger.exception("框选截图回调处理失败")
            self._restore_windows_after_capture()

    def clear_icon(self, icon_type):
        if icon_type.startswith("skill"):
            idx = 0
            if "_" in icon_type:
                try:
                    idx = int(icon_type.split("_", 1)[1])
                except ValueError:
                    idx = 0
            idx = max(0, min(MAX_SKILL_ICONS - 1, idx))
            self._icon_imgs[idx] = None
            self._icon_metas[idx] = {}
            self._icon_dirty[idx] = True
            self.icon_previews[idx].setText("无图标")
            self.icon_previews[idx].setPixmap(QPixmap())
        elif icon_type == "buff":
            self._buff_img = None
            self._buff_meta = {}
            self.buff_preview.setText("无图标")
            self.buff_preview.setPixmap(QPixmap())

    def clear_buff_region(self):
        skill_id = self.skill_data.get("id") if self.skill_data else None
        if skill_id:
            rel = get_buff_region_preview_rel_path(self.config_name, skill_id)
            abs_path = os.path.join(self.config_dir, rel)
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                except Exception as e:
                    self.logger.warning(f"删除 Buff 区域预览失败 {abs_path}: {e}")
        self._buff_region_img = None
        self._buff_region_meta = {}
        self._update_buff_region_preview()

    def _get_skill_recognition(self):
        return {
            "confidence": self.skill_conf.value(),
            "position_tolerance": self.skill_tol.value(),
            "search_margin": self.skill_margin.value(),
            "brightness_threshold": self.skill_bright.value(),
        }

    def _get_buff_recognition(self):
        return {"confidence": self.buff_conf.value()}

    def _has_buff_region(self):
        if self._buff_region_meta.get("width") and self._buff_region_meta.get("height"):
            return True
        if self.skill_data:
            region = self.skill_data.get("precondition", {}).get("buff_region", {})
            return bool(region.get("width") and region.get("height"))
        return False

    def _validate(self):
        name = self.name_edit.text().strip()
        if not name:
            self.logger.debug("技能保存校验失败: 未输入技能名称")
            QMessageBox.warning(self, "提示", "请输入技能名称")
            return False
        if len(name) > 6:
            self.logger.debug("技能保存校验失败: 技能名称超过6个字符")
            QMessageBox.warning(self, "提示", "技能名称最多 6 个字符")
            return False
        key = self.key_label.text()
        if key == "未设置" or not key:
            self.logger.debug("技能保存校验失败: 未设置技能按键")
            QMessageBox.warning(self, "提示", "请设置技能按键")
            return False
        has_icon1 = self._icon_imgs[0] is not None
        if not has_icon1 and self.skill_data:
            icons = self.skill_data.get("icons") or []
            if icons and icons[0].get("path"):
                has_icon1 = True
            elif self.skill_data.get("icon", {}).get("path"):
                has_icon1 = True
        if not has_icon1:
            self.logger.debug("技能保存校验失败: 未设置技能图标")
            QMessageBox.warning(self, "提示", "请设置技能图标")
            return False
        if self.precond_enabled.isChecked():
            buff_name = self.buff_name_edit.text().strip()
            if not buff_name:
                self.logger.debug("技能保存校验失败: 启用前置条件但未填写 Buff 名称")
                QMessageBox.warning(self, "提示", "启用前置条件时请填写 Buff 名称（最多6字）")
                return False
            if len(buff_name) > 6:
                QMessageBox.warning(self, "提示", "Buff 名称最多 6 个字符")
                return False
            if not self._has_buff_region():
                self.logger.debug("技能保存校验失败: 启用前置条件但未设置 Buff 区域")
                QMessageBox.warning(self, "提示", "启用前置条件时请框选 Buff 搜索区域")
                return False
            if self._buff_img is None and not (self.skill_data and
                    self.skill_data.get("precondition", {}).get("buff_icon", {}).get("path")):
                self.logger.debug("技能保存校验失败: 启用前置条件但未设置 Buff 图标")
                QMessageBox.warning(self, "提示", "启用前置条件时请截取 Buff 图标")
                return False
        if self.priority_enabled.isChecked() and self.check_priority_conflict:
            exclude_id = self.skill_data.get("id") if self.skill_data else None
            kind = SKILL_KIND_BUFF if self.kind_buff.isChecked() else SKILL_KIND_ATTACK
            conflict = self.check_priority_conflict(
                self.priority_spin.value(), exclude_id, skill_kind=kind
            )
            if conflict:
                self.logger.debug(
                    f"技能保存校验失败: 优先级 {self.priority_spin.value()} 与「{conflict}」重复"
                )
                QMessageBox.warning(
                    self, "优先级重复",
                    f"优先级 {self.priority_spin.value()} 已被技能「{conflict}」使用，请更换",
                )
                return False
        return True

    def accept(self):
        if not self._validate():
            return
        try:
            self._result_skill = self._build_skill_data()
        except RuntimeError as e:
            self.logger.warning(f"技能数据组装失败: {e}")
            QMessageBox.warning(self, "保存失败", str(e))
            return
        if self._on_skill_commit:
            self._on_skill_commit(self._result_skill)
        self.logger.info(f"技能数据已提交: {self._result_skill.get('name')}")
        # 先关闭对话框，再延迟恢复主窗，避免与 commit 触发的 UI 刷新竞争
        need_restore = self._main_win_minimized_by_us
        self._main_win_minimized_by_us = False
        super().accept()
        if need_restore:
            self._main_win_minimized_by_us = True
            QTimer.singleShot(0, self._restore_main_window)

    def result_skill(self):
        return self._result_skill

    def _build_skill_data(self):
        skill_id = self.skill_data.get("id") if self.skill_data else generate_skill_id()
        old_icons = []
        if self.skill_data:
            old_skill = normalize_image_skill(self.skill_data)
            old_icons = list(old_skill.get("icons") or [])
        buff_icon = dict(self.skill_data.get("precondition", {}).get("buff_icon", {})) if self.skill_data else {}
        buff_region = {}

        icons = []
        for i in range(MAX_SKILL_ICONS):
            old = dict(old_icons[i]) if i < len(old_icons) else {}
            if self._icon_dirty[i]:
                if self._icon_imgs[i] is None:
                    continue
                rel = get_skill_icon_rel_path(self.config_name, skill_id, i)
                if not save_icon_image(self.config_dir, rel, self._icon_imgs[i]):
                    raise RuntimeError(f"技能图标保存失败: {os.path.join(self.config_dir, rel)}")
                icons.append({
                    "path": rel,
                    "x": int(self._icon_metas[i].get("x", old.get("x", 0))),
                    "y": int(self._icon_metas[i].get("y", old.get("y", 0))),
                    "width": int(self._icon_imgs[i].shape[1]),
                    "height": int(self._icon_imgs[i].shape[0]),
                })
            elif self._icon_imgs[i] is not None and old.get("path"):
                icons.append(old)
            elif self._icon_imgs[i] is not None:
                rel = get_skill_icon_rel_path(self.config_name, skill_id, i)
                if not save_icon_image(self.config_dir, rel, self._icon_imgs[i]):
                    raise RuntimeError(f"技能图标保存失败: {os.path.join(self.config_dir, rel)}")
                icons.append({
                    "path": rel,
                    "x": int(self._icon_metas[i].get("x", 0)),
                    "y": int(self._icon_metas[i].get("y", 0)),
                    "width": int(self._icon_imgs[i].shape[1]),
                    "height": int(self._icon_imgs[i].shape[0]),
                })

        if self._buff_img is not None:
            rel = get_buff_icon_rel_path(self.config_name, skill_id)
            if not save_icon_image(self.config_dir, rel, self._buff_img):
                raise RuntimeError(f"Buff 图标保存失败: {os.path.join(self.config_dir, rel)}")
            buff_icon = {
                "path": rel,
                "width": int(self._buff_img.shape[1]),
                "height": int(self._buff_img.shape[0]),
            }
        if self._buff_region_meta.get("width") and self._buff_region_meta.get("height"):
            buff_region = {
                "x": int(self._buff_region_meta.get("x", 0)),
                "y": int(self._buff_region_meta.get("y", 0)),
                "width": int(self._buff_region_meta.get("width", 0)),
                "height": int(self._buff_region_meta.get("height", 0)),
            }
            if self._buff_region_img is not None:
                rel = get_buff_region_preview_rel_path(self.config_name, skill_id)
                if not save_icon_image(self.config_dir, rel, self._buff_region_img):
                    raise RuntimeError(
                        f"Buff 搜索区域预览保存失败: {os.path.join(self.config_dir, rel)}"
                    )

        icon = dict(icons[0]) if icons else {}
        result = {
            "id": skill_id,
            "name": self.name_edit.text().strip(),
            "key": self.key_label.text(),
            "skill_kind": SKILL_KIND_BUFF if self.kind_buff.isChecked() else SKILL_KIND_ATTACK,
            "press_time": self.press_spin.value(),
            "repeat_count": self.repeat_spin.value(),
            "repeat_interval": self.repeat_interval_spin.value(),
            "recovery_ms": self.recovery_spin.value(),
            "execute_interval_ms": self.execute_interval_spin.value(),
            "ensure_press": self.ensure_press_check.isChecked(),
            "ensure_press_timeout_ms": self.ensure_timeout_spin.value(),
            "ensure_press_retries": self.ensure_retries_spin.value(),
            "recognition": self._get_skill_recognition(),
            "icon": icon,
            "icons": icons,
            "precondition": {
                "enabled": self.precond_enabled.isChecked(),
                "trigger_mode": self._get_trigger_mode(),
                "name": self.buff_name_edit.text().strip(),
                "wait_after_buff_ms": self.wait_spin.value(),
                "buff_region": buff_region,
                "buff_icon": buff_icon,
                "recognition": self._get_buff_recognition(),
            },
        }
        if self.priority_enabled.isChecked():
            result["priority"] = self.priority_spin.value()
        else:
            result["priority"] = None
        return migrate_post_buff_icon_path(result, self.config_dir, self.config_name)

    def start_test(self, icon_type):
        if self._detect_worker and self._detect_worker.isRunning():
            return
        label = "技能" if icon_type == "skill" else "Buff"
        matchers = []
        labels = []
        if icon_type == "skill":
            params = self._get_skill_recognition()
            old_icons = []
            if self.skill_data:
                old_icons = list(normalize_image_skill(self.skill_data).get("icons") or [])
            for i in range(MAX_SKILL_ICONS):
                img = self._icon_imgs[i]
                ax, ay = 0, 0
                if img is None and i < len(old_icons) and old_icons[i].get("path"):
                    img = load_template_preview(old_icons[i]["path"], self.config_dir)
                    ax = old_icons[i].get("x", 0)
                    ay = old_icons[i].get("y", 0)
                elif img is not None:
                    if self._icon_metas[i]:
                        ax = self._icon_metas[i].get("x", 0)
                        ay = self._icon_metas[i].get("y", 0)
                    elif i < len(old_icons):
                        ax = old_icons[i].get("x", 0)
                        ay = old_icons[i].get("y", 0)
                if img is None:
                    continue
                matchers.append(IconMatcher(img, ax, ay, params))
                labels.append(i + 1)
            if not matchers:
                QMessageBox.warning(self, "提示", "请先设置技能图标")
                return
        else:
            img = self._buff_img
            if img is None and self.skill_data:
                buff_icon = self.skill_data.get("precondition", {}).get("buff_icon", {})
                path = buff_icon.get("path", "")
                if path:
                    img = load_template_preview(path, self.config_dir)
            if img is None:
                QMessageBox.warning(self, "提示", "请先截取 Buff 图标")
                return
            region_meta = dict(self._buff_region_meta)
            if not (region_meta.get("width") and region_meta.get("height")) and self.skill_data:
                region_meta = dict(self.skill_data.get("precondition", {}).get("buff_region", {}))
            pre = {"enabled": True, "buff_region": region_meta}
            if self.skill_data:
                pre = {**self.skill_data.get("precondition", {}), "buff_region": region_meta}
            resolved = resolve_buff_region(pre)
            if resolved is None:
                QMessageBox.warning(self, "提示", "请先框选 Buff 搜索区域")
                return
            rx, ry, rw, rh = resolved
            params = self._get_buff_recognition()
            matchers = [RegionIconMatcher(img, rx, ry, rw, rh, params)]
            labels = [0]

        self.skill_test_btn.setEnabled(False)
        self.buff_test_btn.setEnabled(False)
        self.log_text.clear()
        self.log_text.append(f"[{label}] 识别中...")

        self._detect_worker = DetectTestWorker(matchers, labels=labels, parent=self)
        self._detect_worker.finished_with_result.connect(
            lambda r, it=icon_type, lb=label: self._on_detect_test_done(r, None, it, lb)
        )
        self._detect_worker.finished_with_error.connect(
            lambda err, it=icon_type, lb=label: self._on_detect_test_done(None, err, it, lb)
        )
        self._detect_worker.start()

    def _on_detect_test_done(self, result, error, icon_type, label):
        self.skill_test_btn.setEnabled(True)
        self.buff_test_btn.setEnabled(True)
        self._detect_worker = None
        if error:
            self.log_text.append(f"[{label}] 识别失败: {error}")
            return
        self.log_text.clear()
        self.log_text.append(f"[{label}] 开始测试识别...")
        trigger_mode = self._get_trigger_mode()

        if icon_type == "buff":
            r = result[0][1] if result else None
            if r is None:
                self.log_text.append(f"[{label}] 无结果")
                return
            if trigger_mode == TRIGGER_MODE_ABSENT:
                if not r.is_ready:
                    self.log_text.append(
                        f"[{label}] 就绪 置信度={r.confidence:.3f}（区域内未检测到 Buff）"
                    )
                else:
                    self.log_text.append(
                        f"[{label}] 未就绪 置信度={r.confidence:.3f}（仍检测到 Buff）"
                    )
            elif trigger_mode == TRIGGER_MODE_PRESENT:
                if r.is_ready:
                    self.log_text.append(
                        f"[{label}] 就绪 置信度={r.confidence:.3f}（区域内检测到 Buff）"
                    )
                else:
                    self.log_text.append(
                        f"[{label}] 未就绪 置信度={r.confidence:.3f}（未检测到 Buff）"
                    )
            return

        any_ready = False
        for slot, r in result or []:
            if r.is_ready:
                any_ready = True
                self.log_text.append(
                    f"[图标{slot}] 就绪 置信度={r.confidence:.3f} 亮度={r.brightness:.0f}"
                )
            else:
                self.log_text.append(
                    f"[图标{slot}] 未就绪 置信度={r.confidence:.3f} "
                    f"亮度={r.brightness:.0f} 偏差=({r.x_diff},{r.y_diff})"
                )
        if any_ready:
            self.log_text.append("[技能] 总览：任一图标就绪（可施放）")
        else:
            self.log_text.append("[技能] 总览：全部未就绪")

    def reject(self):
        self._restore_main_window()
        super().reject()

    def closeEvent(self, event):
        if self._detect_worker and self._detect_worker.isRunning():
            self._detect_worker.wait(500)
        self._restore_main_window()
        self._resume_memory_cleanup()
        super().closeEvent(event)
