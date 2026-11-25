# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
                             QPushButton, QRadioButton, QSpinBox, QMessageBox, QFormLayout)
from PyQt5.QtCore import Qt

from macro_tab_base import MacroTabBase
from utils import validate_time_input

_FORBIDDEN_MOUSE_KEYS = [
    '鼠标左键', '鼠标中键', '鼠标右键', '鼠标侧键1', '鼠标侧键2',
]


class SingleKeyMacroTab(MacroTabBase):
    """单键宏标签页"""

    def __init__(self, parent=None, *, has_config_fn=None, conflict_checker=None):
        super().__init__(
            parent,
            has_config_fn=has_config_fn,
            conflict_checker=conflict_checker,
        )
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 单键宏热键设置
        hotkey_group = QGroupBox("单键宏热键设置")
        hotkey_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        hotkey_layout = QFormLayout()
        
        self.single_hotkey_label = QLabel("未设置")
        self.single_hotkey_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 18px;
            }
        """)
        self.single_hotkey_label.setAlignment(Qt.AlignCenter)
        self.set_single_hotkey_btn = QPushButton("设置热键")
        self.reset_single_hotkey_btn = QPushButton("重置")
        
        hotkey_buttons_layout = QHBoxLayout()
        hotkey_buttons_layout.addWidget(self.set_single_hotkey_btn)
        hotkey_buttons_layout.addWidget(self.reset_single_hotkey_btn)
        
        hotkey_layout.addRow("热键:", self.single_hotkey_label)
        hotkey_layout.addRow("", hotkey_buttons_layout)
        
        # 时间设置
        self.single_press_time_edit = QSpinBox()
        self.single_press_time_edit.setRange(1, 9999)
        self.single_press_time_edit.setValue(20)
        self.single_interval_edit = QSpinBox()
        self.single_interval_edit.setRange(1, 9999)
        self.single_interval_edit.setValue(20)
        
        # 设置标签右对齐
        hotkey_layout.addRow("按下时间(ms):", self.single_press_time_edit)
        hotkey_layout.addRow("间隔时间(ms):", self.single_interval_edit)
        
        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)
        
        # 执行模式
        mode_group = QGroupBox("单键宏执行模式")
        mode_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        mode_layout = QVBoxLayout()
        
        self.single_mode1 = QRadioButton("模式1: 按下启动热键一直循环执行直到再次按下就停止")
        self.single_mode2 = QRadioButton("模式2: 按下启动热键一直循环执行，松开停止")
        self.single_mode1.setChecked(True)
        
        mode_layout.addWidget(self.single_mode1)
        mode_layout.addWidget(self.single_mode2)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        self.setLayout(layout)
        
        # 连接信号
        self.set_single_hotkey_btn.clicked.connect(self.set_single_hotkey)
        self.reset_single_hotkey_btn.clicked.connect(self.reset_single_hotkey)
        
        # 连接实时保存信号
        self.single_press_time_edit.editingFinished.connect(self.on_config_changed)
        self.single_interval_edit.editingFinished.connect(self.on_config_changed)
        self.single_mode1.toggled.connect(self.on_config_changed)
        self.single_mode2.toggled.connect(self.on_config_changed)
        
        # 连接时间输入验证信号（使用 editingFinished 避免输入过程中频繁触发）
        self.single_press_time_edit.editingFinished.connect(
            lambda: validate_time_input(self.single_press_time_edit)
        )
        self.single_interval_edit.editingFinished.connect(
            lambda: validate_time_input(self.single_interval_edit)
        )

    def set_single_hotkey(self):
        """设置单键宏热键（支持所有键盘按键）"""
        def _reject_mouse(hotkey):
            if hotkey in _FORBIDDEN_MOUSE_KEYS:
                return (
                    "单键宏不支持使用鼠标按键作为热键，请使用键盘按键。\n\n"
                    "原因：鼠标按键是事件触发，作为热键会导致执行逻辑冲突。\n\n"
                    "如果要用鼠标连发可以在多键宏的宏序列中添加鼠标按键。"
                )
            return None

        self._assign_hotkey(
            "single",
            self.single_hotkey_label,
            extra_validate=_reject_mouse,
        )
    
    def set_buttons_enabled(self, enabled):
        """设置按钮是否可用"""
        self.set_single_hotkey_btn.setEnabled(enabled)
        self.reset_single_hotkey_btn.setEnabled(enabled)
        self.single_press_time_edit.setEnabled(enabled)
        self.single_interval_edit.setEnabled(enabled)
        self.single_mode1.setEnabled(enabled)
        self.single_mode2.setEnabled(enabled)
            
    def reset_single_hotkey(self):
        """重置单键宏热键"""
        self._reset_hotkey_label(self.single_hotkey_label)

    def on_config_changed(self):
        """配置更改时发出信号"""
        self._on_user_changed()
    
    def get_config(self):
        """获取单键宏配置"""
        config = {
            "hotkey": self.single_hotkey_label.text() if self.single_hotkey_label.text() != "未设置" else "",
            "press_time": self.single_press_time_edit.value(),
            "interval": self.single_interval_edit.value(),
            "mode": 1 if self.single_mode1.isChecked() else 2
        }
        self.logger.debug(
            f"单键宏 get_config: hotkey={config['hotkey'] or '(未设置)'}, "
            f"mode={config['mode']}, press={config['press_time']}ms"
        )
        return config
    
    def load_config(self, config):
        """加载单键宏配置"""
        with self._guard_loading():
            single_macro = config.get("single_key_macro", {})
            hotkey_text = single_macro.get("hotkey", "未设置")
            self.single_hotkey_label.setText(hotkey_text if hotkey_text else "未设置")
            self.single_press_time_edit.setValue(single_macro.get("press_time", 20))
            self.single_interval_edit.setValue(single_macro.get("interval", 20))

            single_mode = single_macro.get("mode", 1)
            if single_mode == 1:
                self.single_mode1.setChecked(True)
            else:
                self.single_mode2.setChecked(True)
            self.logger.debug(
                f"单键宏 load_config: hotkey={hotkey_text or '(未设置)'}, mode={single_mode}"
            )