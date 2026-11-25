# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QRadioButton, QMessageBox, QDialog,
                             QGridLayout, QSpinBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import threading

from logger import get_logger
from macro_tab_base import MacroTabBase
from keyboard_selector import select_keys
from macro_sequence_recorder import SequenceRecordDialog
from utils import validate_time_input
from config_manager import parse_combination_key

class MultiMacroTab(MacroTabBase):
    """多键宏标签页"""

    def __init__(self, parent=None, *, has_config_fn=None, conflict_checker=None):
        super().__init__(
            parent,
            has_config_fn=has_config_fn,
            conflict_checker=conflict_checker,
        )
        self.logger = get_logger()
        self.init_ui()

    def set_hotkey(self):
        """设置启动宏热键（支持所有键盘按键和鼠标按键）"""
        self._assign_hotkey("multi", self.hotkey_label)
    
    def set_buttons_enabled(self, enabled):
        """设置按钮是否可用"""
        self.set_hotkey_btn.setEnabled(enabled)
        self.reset_hotkey_btn.setEnabled(enabled)
        self.record_seq_btn.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)
        self.del_btn.setEnabled(enabled)
        self.up_btn.setEnabled(enabled)
        self.down_btn.setEnabled(enabled)
        self.mode1.setEnabled(enabled)
        self.mode2.setEnabled(enabled)
        self.mode3.setEnabled(enabled)
    
    def _validate_macro_key(self, key):
        """检查宏按键是否与当前配置热键冲突，返回 (是否通过, 错误信息)"""
        if '&' in key:
            combination_keys = parse_combination_key(key)
            if self.parent and hasattr(self.parent, 'current_config'):
                multi_hotkey = self.parent.current_config.get("hotkey", "")
                single_hotkey = self.parent.current_config.get("single_key_macro", {}).get("hotkey", "")

                for single_key in combination_keys:
                    if multi_hotkey and single_key == multi_hotkey.lower():
                        return False, f"组合按键 '{key}' 中的 '{single_key}' 与多键宏启动热键冲突"
                    if single_hotkey and single_key == single_hotkey.lower():
                        return False, f"组合按键 '{key}' 中的 '{single_key}' 与单键宏热键冲突"

        checker = self._resolve_conflict_checker()
        if checker:
            conflict_info = checker(key, "macro")
            if conflict_info:
                conflict_type = conflict_info[0] if isinstance(conflict_info, tuple) else conflict_info
                return False, f"该按键在当前配置中已被用于{conflict_type}"

        return True, ""

    def _insert_macro_row(self, key, press_time, interval):
        """向宏表格插入一行"""
        row_position = self.macro_table.rowCount()
        self.macro_table.insertRow(row_position)
        self._set_macro_row(row_position, key, press_time, interval)

    def _set_macro_row(self, row, key, press_time, interval):
        """设置宏表格指定行内容"""
        for col, value in enumerate([key, press_time, interval]):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.macro_table.setItem(row, col, item)

    def record_sequence(self):
        """录制宏序列并替换当前表格内容"""
        if not self._require_config():
            return

        dialog = SequenceRecordDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return

        self._apply_recorded_macros(dialog.get_recorded_macros())

    def _apply_recorded_macros(self, macros):
        """将录制的宏序列替换到表格（跳过冲突项）"""
        valid_macros = []
        skipped = []

        for macro in macros:
            ok, error_msg = self._validate_macro_key(macro['key'])
            if ok:
                valid_macros.append(macro)
            else:
                skipped.append(f"{macro['key']}: {error_msg}")

        if not valid_macros:
            detail = "\n".join(skipped[:5]) if skipped else "无有效步骤"
            QMessageBox.warning(self, "无法写入", f"录制的步骤均存在冲突：\n{detail}")
            return

        self.macro_table.setRowCount(0)
        for macro in valid_macros:
            self._insert_macro_row(
                macro['key'], macro['press'], macro['interval']
            )

        self.configChanged.emit()

        if skipped:
            detail = "\n".join(skipped[:5])
            extra = f"\n...等共 {len(skipped)} 项" if len(skipped) > 5 else ""
            QMessageBox.warning(
                self, "部分步骤已跳过",
                f"已写入 {len(valid_macros)} 步，以下步骤因冲突被跳过：\n{detail}{extra}"
            )
    
    def reset_hotkey(self):
        """重置热键"""
        self._reset_hotkey_label(self.hotkey_label)
    
    def add_macro(self):
        """添加宏"""
        if not self._require_config():
            return

        # 创建自定义的宏录制对话框
        dialog = CustomMacroRecordDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.hotkey:
            key = dialog.hotkey

            ok, error_msg = self._validate_macro_key(key)
            if not ok:
                QMessageBox.warning(self, "热键冲突", error_msg)
                return

            time_settings = dialog.get_time_settings()
            if time_settings:
                press_time = time_settings["press"]
                interval = time_settings["interval"]
            else:
                press_time = 15
                interval = 20

            self._insert_macro_row(key, press_time, interval)
            self.configChanged.emit()

    def edit_macro(self):
        """编辑选中的宏步骤"""
        if not self._require_config():
            return

        selected_row = self.macro_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要编辑的宏步骤")
            return

        key_item = self.macro_table.item(selected_row, 0)
        press_item = self.macro_table.item(selected_row, 1)
        interval_item = self.macro_table.item(selected_row, 2)
        if not key_item or not press_item or not interval_item:
            QMessageBox.warning(self, "提示", "选中行数据无效")
            return

        try:
            initial_press = int(press_item.text())
            initial_interval = int(interval_item.text())
        except ValueError:
            initial_press, initial_interval = 15, 20

        dialog = CustomMacroRecordDialog(
            self,
            initial_key=key_item.text(),
            initial_press=initial_press,
            initial_interval=initial_interval,
            edit_mode=True,
        )
        if dialog.exec_() == QDialog.Accepted and dialog.hotkey:
            key = dialog.hotkey

            ok, error_msg = self._validate_macro_key(key)
            if not ok:
                QMessageBox.warning(self, "热键冲突", error_msg)
                return

            time_settings = dialog.get_time_settings()
            if time_settings:
                press_time = time_settings["press"]
                interval = time_settings["interval"]
            else:
                press_time = initial_press
                interval = initial_interval

            self._set_macro_row(selected_row, key, press_time, interval)
            self.macro_table.setCurrentCell(selected_row, 0)
            self.configChanged.emit()
    
    def delete_macro(self):
        """删除宏"""
        selected_row = self.macro_table.currentRow()
        if selected_row >= 0:
            self.macro_table.removeRow(selected_row)
            self.configChanged.emit()
    
    def move_up(self):
        """上移"""
        current_row = self.macro_table.currentRow()
        if current_row > 0:
            # 交换表格行
            for col in range(self.macro_table.columnCount()):
                current_item = self.macro_table.takeItem(current_row, col)
                above_item = self.macro_table.takeItem(current_row-1, col)
                self.macro_table.setItem(current_row-1, col, current_item)
                self.macro_table.setItem(current_row, col, above_item)
            
            self.macro_table.setCurrentCell(current_row-1, 0)
            self.configChanged.emit()
    
    def move_down(self):
        """下移"""
        current_row = self.macro_table.currentRow()
        if 0 <= current_row < self.macro_table.rowCount() - 1:
            # 交换表格行
            for col in range(self.macro_table.columnCount()):
                current_item = self.macro_table.takeItem(current_row, col)
                below_item = self.macro_table.takeItem(current_row+1, col)
                self.macro_table.setItem(current_row+1, col, current_item)
                self.macro_table.setItem(current_row, col, below_item)
            
            self.macro_table.setCurrentCell(current_row+1, 0)
            self.configChanged.emit()
    
    def on_mode_changed(self):
        """执行模式更改时的处理"""
        self._on_user_changed()
    
    def get_config(self):
        """获取多键宏配置"""
        macros = []
        for row in range(self.macro_table.rowCount()):
            key = self.macro_table.item(row, 0).text()
            press = int(self.macro_table.item(row, 1).text())
            interval = int(self.macro_table.item(row, 2).text())
            macros.append({
                "key": key,
                "press": press,
                "interval": interval
            })
        
        # 获取模式
        if self.mode1.isChecked():
            mode = 1
        elif self.mode2.isChecked():
            mode = 2
        else:
            mode = 3
        
        result = {
            "hotkey": self.hotkey_label.text() if self.hotkey_label.text() != "未设置" else "",
            "macros": macros,
            "mode": mode
        }
        self.logger.debug(
            f"多键宏 get_config: hotkey={result['hotkey'] or '(未设置)'}, "
            f"mode={mode}, steps={len(macros)}"
        )
        return result
    
    def load_config(self, config):
        """加载多键宏配置"""
        with self._guard_loading():
            # 更新热键
            hotkey = config.get("hotkey", "")
            self.hotkey_label.setText(hotkey if hotkey else "未设置")

            # 更新表格
            self.macro_table.setRowCount(0)

            # 获取当前的热键设置用于冲突检查（从当前配置中获取）
            multi_hotkey = config.get("hotkey", "")
            single_hotkey = config.get("single_key_macro", {}).get("hotkey", "")

            for macro in config.get("macros", []):
                # 检查组合按键冲突
                key = macro['key']
                if '&' in key:
                    combination_keys = parse_combination_key(key)

                    # 检查与多键宏启动热键冲突
                    if multi_hotkey and multi_hotkey.lower() in combination_keys:
                        self.logger.debug(f"配置中的组合按键 '{key}' 与多键宏启动热键冲突")
                        continue

                    # 检查与单键宏热键冲突
                    if single_hotkey and single_hotkey.lower() in combination_keys:
                        self.logger.debug(f"配置中的组合按键 '{key}' 与单键宏热键冲突")
                        continue

                # 添加到表格
                self._insert_macro_row(
                    macro['key'], macro['press'], macro['interval']
                )

            # 设置执行模式
            mode = config.get("mode", 2)
            if mode == 1:
                self.mode1.setChecked(True)
            elif mode == 2:
                self.mode2.setChecked(True)
            else:
                self.mode3.setChecked(True)

            self.logger.debug(
                f"多键宏 load_config: hotkey={multi_hotkey or '(未设置)'}, "
                f"mode={config.get('mode', 2)}, steps={self.macro_table.rowCount()}"
            )

    def init_ui(self):
        layout = QVBoxLayout()

        # 启动宏热键设置
        hotkey_group = QGroupBox("启动宏热键")
        hotkey_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        hotkey_layout = QVBoxLayout()
        
        self.hotkey_label = QLabel("未设置")
        self.hotkey_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 18px;
            }
        """)
        self.hotkey_label.setAlignment(Qt.AlignCenter)
        hotkey_layout.addWidget(self.hotkey_label)

        button_layout = QHBoxLayout()
        self.set_hotkey_btn = QPushButton("设置热键")
        self.reset_hotkey_btn = QPushButton("重置")
        button_layout.addWidget(self.set_hotkey_btn)
        button_layout.addWidget(self.reset_hotkey_btn)
        hotkey_layout.addLayout(button_layout)

        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        # 宏序列设置 - 表格形式
        macro_group = QGroupBox("宏序列设置")
        macro_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        macro_layout = QVBoxLayout()
        
        # 创建表格
        self.macro_table = QTableWidget(0, 3)
        self.macro_table.setHorizontalHeaderLabels(["按键", "按下时间(ms)", "间隔时间(ms)"])
        self.macro_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.macro_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.macro_table.setAlternatingRowColors(True)

        # 设置表格内容居中显示
        self.macro_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #ccc;
            }
            QTableWidget::item {
                text-align: center;
                padding: 4px;
            }
        """)

        # 隐藏行号
        self.macro_table.verticalHeader().setVisible(False)
        
        # 设置表格为只读
        self.macro_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 使用原生样式
        self.macro_table.setAlternatingRowColors(True)
        
        macro_layout.addWidget(self.macro_table)

        macro_buttons = QHBoxLayout()
        self.record_seq_btn = QPushButton("录制序列")
        self.add_btn = QPushButton("添加")
        self.edit_btn = QPushButton("编辑")
        self.del_btn = QPushButton("删除")
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        macro_buttons.addWidget(self.record_seq_btn)
        macro_buttons.addWidget(self.add_btn)
        macro_buttons.addWidget(self.edit_btn)
        macro_buttons.addWidget(self.del_btn)
        macro_buttons.addWidget(self.up_btn)
        macro_buttons.addWidget(self.down_btn)
        macro_layout.addLayout(macro_buttons)

        macro_group.setLayout(macro_layout)
        layout.addWidget(macro_group)

        # 执行模式
        mode_group = QGroupBox("执行模式")
        mode_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        mode_layout = QVBoxLayout()
        self.mode1 = QRadioButton("模式1: 按下启动宏热键 → 循环执行，直到再次按下结束")
        self.mode2 = QRadioButton("模式2: 按下启动宏热键 → 执行一次就结束")
        self.mode3 = QRadioButton("模式3: 按下启动宏热键 → 循环执行，松开停止")
        self.mode2.setChecked(True)

        mode_layout.addWidget(self.mode1)
        mode_layout.addWidget(self.mode2)
        mode_layout.addWidget(self.mode3)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        self.setLayout(layout)
        
        # 连接信号
        self.set_hotkey_btn.clicked.connect(self.set_hotkey)
        self.reset_hotkey_btn.clicked.connect(self.reset_hotkey)
        self.record_seq_btn.clicked.connect(self.record_sequence)
        self.add_btn.clicked.connect(self.add_macro)
        self.edit_btn.clicked.connect(self.edit_macro)
        self.del_btn.clicked.connect(self.delete_macro)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        
        # 连接实时保存信号
        self.mode1.toggled.connect(self.on_mode_changed)
        self.mode2.toggled.connect(self.on_mode_changed)
        self.mode3.toggled.connect(self.on_mode_changed)


class CustomMacroRecordDialog(QDialog):
    """自定义宏录制对话框，支持组合按键选择"""
    
    def __init__(
        self,
        parent=None,
        *,
        initial_key=None,
        initial_press=15,
        initial_interval=20,
        edit_mode=False,
    ):
        super().__init__(parent)
        self.logger = get_logger()
        self.setWindowTitle("编辑宏按键" if edit_mode else "录制宏按键")
        self.setFixedSize(500, 400)
        
        # 设置字体
        font = QFont("微软雅黑", 9)
        self.setFont(font)

        layout = QVBoxLayout()

        # 说明文字
        label = QLabel("请选择录制方式：\n1. 使用单个录制（录制单个按键）\n2. 组合按键（选择多个按键组合）")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        # 状态显示
        self.status_label = QLabel("请选择录制方式")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 15px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # 按钮区域 - 两种录制方式
        button_layout = QHBoxLayout()
        
        self.record_btn = QPushButton("单个录制")
        self.combination_btn = QPushButton("组合按键")
        self.clear_btn = QPushButton("清空")
        
        button_layout.addWidget(self.record_btn)
        button_layout.addWidget(self.combination_btn)
        button_layout.addWidget(self.clear_btn)
        
        layout.addLayout(button_layout)

        # 时间设置区域
        time_group = QGroupBox("时间设置 (毫秒)")
        time_layout = QGridLayout()
        
        time_layout.addWidget(QLabel("按下时间:"), 0, 0)
        self.press_time_edit = QSpinBox()
        self.press_time_edit.setRange(1, 9999)
        self.press_time_edit.setValue(max(1, min(9999, int(initial_press))))
        time_layout.addWidget(self.press_time_edit, 0, 1)
        
        time_layout.addWidget(QLabel("间隔时间:"), 1, 0)
        self.interval_edit = QSpinBox()
        self.interval_edit.setRange(1, 9999)
        self.interval_edit.setValue(max(1, min(9999, int(initial_interval))))
        time_layout.addWidget(self.interval_edit, 1, 1)
        
        # 添加时间设置说明
        time_info = QLabel("时间范围: 1-9999ms")
        time_info.setStyleSheet("QLabel { color: #888; font-size: 8pt; }")
        time_layout.addWidget(time_info, 2, 0, 1, 2)
        
        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # 确定取消按钮
        button_box = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        button_box.addWidget(ok_btn)
        button_box.addWidget(cancel_btn)
        layout.addLayout(button_box)

        self.setLayout(layout)

        self.hotkey = None
        self.recording = False
        self.recorder_thread = None

        # 连接信号
        self.record_btn.clicked.connect(self.start_single_recording)
        self.combination_btn.clicked.connect(self.start_combination_recording)
        self.clear_btn.clicked.connect(self.clear_hotkey)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        # 连接时间输入验证信号
        self.press_time_edit.editingFinished.connect(
            lambda: validate_time_input(self.press_time_edit)
        )
        self.interval_edit.editingFinished.connect(
            lambda: validate_time_input(self.interval_edit)
        )

        if initial_key:
            self.hotkey = initial_key
            self.status_label.setText(f"当前按键: {initial_key}")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #d1ecf1;
                    border: 1px solid #bee5eb;
                    padding: 15px;
                    border-radius: 4px;
                    min-height: 20px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #0c5460;
                }
            """)
            
    def start_single_recording(self):
        """开始单个按键录制"""
        if not self.recording:
            self.recording = True
            self.record_btn.setText("停止录制")
            self.status_label.setText("正在录制...请按下单个按键")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    padding: 15px;
                    border-radius: 4px;
                    min-height: 20px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #856404;
                }
            """)
            
            # 在新线程中录制热键
            self.recorder_thread = threading.Thread(target=self.record_single_key)
            self.recorder_thread.daemon = True
            self.recorder_thread.start()

    def record_single_key(self):
        """录制单个按键"""
        try:
            # 使用新的通用宏按键录制逻辑
            from hotkey import UniversalHotkeyRecorder
            hotkey = UniversalHotkeyRecorder.record_universal_hotkey()
            
            if hotkey and self.recording:
                self.hotkey = hotkey
                # 使用QTimer在主线程中更新UI
                QTimer.singleShot(0, self.on_hotkey_recorded)
            elif hotkey is None and self.recording:
                # 录制失败，在主线程中显示错误消息
                QTimer.singleShot(0, self.on_record_error)
        except Exception as e:
            self.logger.error(f"录制热键错误: {e}", exc_info=True)
            QTimer.singleShot(0, self.on_record_error)

    def start_combination_recording(self):
        """开始组合按键录制 - 打开键盘选择器"""
        try:
            # 调用键盘选择器
            key_combination = select_keys()
            
            if key_combination:
                # 将选择结果设置为热键
                self.hotkey = key_combination
                self.status_label.setText(f"已选择组合键: {key_combination}")
                self.status_label.setStyleSheet("""
                    QLabel {
                        background-color: #d1ecf1;
                        border: 1px solid #bee5eb;
                        padding: 15px;
                        border-radius: 4px;
                        min-height: 20px;
                        font-size: 14px;
                        font-weight: bold;
                        color: #0c5460;
                    }
                """)
                self.logger.info(f"用户选择了组合键: {key_combination}")
            else:
                self.logger.debug("用户取消了组合键选择")
                
        except Exception as e:
            self.logger.error(f"打开键盘选择器错误: {e}", exc_info=True)
            QMessageBox.warning(self, "错误", f"打开键盘选择器失败: {e}")

    def on_hotkey_recorded(self):
        """热键录制完成"""
        if self.hotkey:
            self.status_label.setText(f"已录制: {self.hotkey}")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #d1ecf1;
                    border: 1px solid #bee5eb;
                    padding: 15px;
                    border-radius: 4px;
                    min-height: 20px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #0c5460;
                }
            """)
        self.recording = False
        self.record_btn.setText("开始录制")

    def on_record_error(self):
        """录制错误"""
        self.status_label.setText("录制失败，请重试")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                padding: 15px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 14px;
                font-weight: bold;
                color: #721c24;
            }
        """)
        self.recording = False
        self.record_btn.setText("开始录制")

    def clear_hotkey(self):
        """清空热键"""
        self.hotkey = None
        self.recording = False
        self.record_btn.setText("开始录制")
        self.status_label.setText("已清空")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 15px;
                border-radius: 4px;
                min-height: 20px;
                font-size: 14px;
                font-weight: bold;
            }
        """)

    def get_time_settings(self):
        """获取时间设置"""
        return {
            "press": self.press_time_edit.value(),
            "interval": self.interval_edit.value()
        }

    def closeEvent(self, event):
        """对话框关闭时确保停止录制"""
        self.recording = False
        super().closeEvent(event)

    def reject(self):
        """取消时停止录制"""
        self.recording = False
        super().reject()
