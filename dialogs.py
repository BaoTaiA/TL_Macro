# -*- coding: utf-8 -*-
"""对话框模块"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class NewConfigDialog(QDialog):
    """新建配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建配置")
        self.setFixedSize(300, 150)
        
        # 设置字体
        font = QFont("微软雅黑", 9)
        self.setFont(font)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("配置名:"))
        self.name_edit = QLineEdit("")
        self.name_edit.setMaxLength(10)  # 限制最多10个字符
        layout.addWidget(self.name_edit)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)


class RenameConfigDialog(QDialog):
    """重命名配置对话框"""
    def __init__(self, parent=None, current_name=""):
        super().__init__(parent)
        self.setWindowTitle("重命名配置")
        self.setFixedSize(300, 150)
        
        # 设置字体
        font = QFont("微软雅黑", 9)
        self.setFont(font)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("配置名:"))
        self.name_edit = QLineEdit(current_name)
        self.name_edit.setMaxLength(10)  # 限制最多10个字符
        layout.addWidget(self.name_edit)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

