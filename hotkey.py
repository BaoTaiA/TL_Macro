# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import threading
import time
from pynput import keyboard, mouse

from logger import get_logger
from key_mapping import key_mapping


class UniversalHotkeyRecorder:
    """通用热键录制器 - 支持所有键盘按键和鼠标按键"""

    @staticmethod
    def record_universal_hotkey():
        """录制通用热键（支持所有键盘按键和鼠标按键）"""
        logger = get_logger()
        logger.debug("等待按键输入...")
        result = {"hotkey": None, "error_message": None}

        def on_click(x, y, button, pressed):
            if pressed and result["hotkey"] is None:
                try:
                    button_name = str(button).replace('Button.', '').lower()
                    display_name = key_mapping.pynput_mouse_to_display(button_name)

                    logger = get_logger()
                    logger.info(f"录制到鼠标按键: {display_name}")
                    result["hotkey"] = display_name
                    return False
                except Exception as e:
                    logger = get_logger()
                    logger.error(f"鼠标录制错误: {e}", exc_info=True)
                    result["error_message"] = f"鼠标录制错误: {e}"
                    return False
            return True

        def on_press(key):
            if result["hotkey"] is None:
                try:
                    if hasattr(key, 'char') and key.char:
                        key_name = key.char.upper()
                        display_name = key_name
                    else:
                        key_name = str(key).replace('Key.', '').replace('\'', '').lower()
                        display_name = key_mapping.pynput_keyboard_to_display(key_name)

                    logger = get_logger()
                    logger.info(f"录制到键盘按键: {display_name}")
                    result["hotkey"] = display_name
                    return False
                except Exception as e:
                    logger = get_logger()
                    logger.error(f"键盘录制错误: {e}", exc_info=True)
                    result["error_message"] = f"键盘录制错误: {e}"
            return False

        mouse_listener = mouse.Listener(on_click=on_click)
        keyboard_listener = keyboard.Listener(on_press=on_press)

        try:
            mouse_listener.start()
            keyboard_listener.start()

            start_time = time.time()
            while result["hotkey"] is None and (time.time() - start_time) < 5:
                if result["error_message"]:
                    break
                time.sleep(0.1)
        finally:
            try:
                mouse_listener.stop()
            except Exception:
                pass
            try:
                keyboard_listener.stop()
            except Exception:
                pass

        if result["error_message"]:
            logger = get_logger()
            logger.warning(result["error_message"])
            QTimer.singleShot(0, lambda: QMessageBox.warning(None, "录制失败", result["error_message"]))
            return None

        return result["hotkey"]


class RecordHotkeyDialog(QDialog):
    """录制通用热键对话框 - 支持所有键盘按键和鼠标按键"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger()
        self.setWindowTitle("录制热键")
        self.setFixedSize(500, 400)

        font = QFont("微软雅黑", 9)
        self.setFont(font)

        layout = QVBoxLayout()

        label = QLabel(
            "请按下任意键盘按键或鼠标按键\n支持：所有键盘按键、所有鼠标按键"
        )
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.status_label = QLabel("准备录制...")
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

        button_layout = QHBoxLayout()
        self.record_btn = QPushButton("开始录制")
        self.clear_btn = QPushButton("清空")
        button_layout.addWidget(self.record_btn)
        button_layout.addWidget(self.clear_btn)
        layout.addLayout(button_layout)

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

        self.record_btn.clicked.connect(self.toggle_recording)
        self.clear_btn.clicked.connect(self.clear_hotkey)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def toggle_recording(self):
        """切换录制状态"""
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        """开始录制"""
        self.recording = True
        self.record_btn.setText("停止录制")
        self.status_label.setText("正在录制...请按下按键")
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

        self.recorder_thread = threading.Thread(target=self.record_hotkey)
        self.recorder_thread.daemon = True
        self.recorder_thread.start()

    def stop_recording(self):
        """停止录制"""
        self.recording = False
        self.record_btn.setText("开始录制")
        self.status_label.setText("录制已停止")
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

    def record_hotkey(self):
        """录制热键"""
        try:
            hotkey = UniversalHotkeyRecorder.record_universal_hotkey()

            if hotkey and self.recording:
                self.hotkey = hotkey
                QTimer.singleShot(0, self.on_hotkey_recorded)
            elif hotkey is None and self.recording:
                QTimer.singleShot(0, self.on_record_error)
        except Exception as e:
            self.logger.error(f"录制热键错误: {e}", exc_info=True)
            QTimer.singleShot(0, self.on_record_error)

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

    def closeEvent(self, event):
        """对话框关闭时确保停止录制"""
        self.recording = False
        super().closeEvent(event)

    def reject(self):
        """取消时停止录制"""
        self.recording = False
        super().reject()
