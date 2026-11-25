# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont

from version import APP_VERSION


class AboutTab(QWidget):
    """关于标签页"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 开发信息区域
        dedication_group = QGroupBox("开发信息")
        dedication_layout = QVBoxLayout()
        dedication_layout.setSpacing(8)
        dedication_layout.setContentsMargins(12, 12, 12, 12)

        version_label = QLabel(f"TL_Macro v{APP_VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setFont(QFont("微软雅黑", 11, QFont.Bold))
        dedication_layout.addWidget(version_label)
        
        dedication_label = QLabel("为玩：王权与自由「ThroneandLiberty」开发")
        dedication_label.setAlignment(Qt.AlignCenter)
        dedication_label.setWordWrap(True)
        dedication_layout.addWidget(dedication_label)
        
        author_label = QLabel("献给 Juuuu（俊恩哥）")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setFont(QFont("微软雅黑", 10, QFont.Bold))
        dedication_layout.addWidget(author_label)

        dedication_group.setLayout(dedication_layout)
        main_layout.addWidget(dedication_group)
        
        # 技术栈区域
        tech_group = QGroupBox("技术栈")
        tech_layout = QVBoxLayout()
        tech_layout.setSpacing(6)
        tech_layout.setContentsMargins(12, 12, 12, 12)
        
        tech_list = [
            "PyQt5 — Native desktop shell, tabbed workflow UI, QThread-backed async workers",
            "OpenCV — Normalized cross-correlation template matching for skill/Buff recognition",
            "NumPy — High-performance ndarray pipeline for framebuffer and correlation maps",
            "mss — GDI framebuffer acquisition layer (software capture path)",
            "bettercam — DXGI Desktop Duplication API with zero-copy ROI slicing",
            "pynput — Low-level HID event capture for hotkey binding and macro recording",
            "keyboard — Global hotkey polling and synthesized key-event dispatch",
            "ctypes — Win32 SendInput virtual HID injection, QPC sub-millisecond timing",
            "ctypes (user32/kernel32) — Foreground HWND resolution, process affinity gating",
            "threading — Parallel Attack/Buff scan pipelines, lock-synchronized fire queue",
            "pywebview — Chromium-backed embedded web surface",
        ]
        
        for tech in tech_list:
            tech_item = QLabel(f"• {tech}")
            tech_item.setWordWrap(True)
            tech_layout.addWidget(tech_item)
        
        tech_group.setLayout(tech_layout)
        main_layout.addWidget(tech_group)
        
        # 链接区域 - 横向排列
        links_group = QGroupBox("相关链接")
        links_layout = QHBoxLayout()
        links_layout.setSpacing(20)
        links_layout.setContentsMargins(12, 12, 12, 12)
        links_layout.setAlignment(Qt.AlignCenter)
        
        # 问题反馈
        feedback_label = QLabel("问题反馈")
        feedback_label.setAlignment(Qt.AlignCenter)
        feedback_label.setCursor(Qt.PointingHandCursor)
        feedback_label.setStyleSheet("color: blue;")
        feedback_label.mousePressEvent = self.open_feedback_url
        links_layout.addWidget(feedback_label)
        
        # 版本信息
        version_link_label = QLabel("版本信息")
        version_link_label.setAlignment(Qt.AlignCenter)
        version_link_label.setCursor(Qt.PointingHandCursor)
        version_link_label.setStyleSheet("color: blue;")
        version_link_label.mousePressEvent = self.open_version_url
        links_layout.addWidget(version_link_label)
        
        links_group.setLayout(links_layout)
        main_layout.addWidget(links_group)
        
        # 添加弹性空间
        main_layout.addStretch()
        
    def open_feedback_url(self, event):
        """打开反馈链接"""
        QDesktopServices.openUrl(QUrl("https://tiax.cn/share/51.html"))
        
    def open_version_url(self, event):
        """打开版本信息链接"""
        QDesktopServices.openUrl(QUrl("https://p.tiax.cn/T/Macro"))
