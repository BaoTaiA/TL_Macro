# -*- coding: utf-8 -*-
"""全屏框选截图遮罩层（微信式：冻结画面 + ESC 取消）"""
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QRect, QPoint, QTimer
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap, QImage

from logger import get_logger
from screen_capture import grab_full_screen, slice_bgr_frame


def _bgr_to_pixmap(img_bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    qt_image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qt_image)


class ScreenshotOverlay(QWidget):
    """全屏截图遮罩层：显示冻结画面，支持拖拽框选并返回坐标"""

    _MIN_SELECTION = 5

    def __init__(self, parent=None, screenshot_callback=None):
        super().__init__(parent)
        self.logger = get_logger()
        self._logged_paint = False
        self._dismissing = False
        self.screenshot_callback = screenshot_callback

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.StrongFocus)

        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self._screen_origin = QPoint(screen_geometry.x(), screen_geometry.y())
        self.setGeometry(screen_geometry)

        self.start_point = None
        self.end_point = None
        self.is_drawing = False
        self._hint_message = None
        self._frozen_bgr = None
        self._frozen_pixmap = None

        try:
            self._frozen_bgr = grab_full_screen(
                screen_geometry.x(),
                screen_geometry.y(),
                screen_geometry.width(),
                screen_geometry.height(),
            )
            self._frozen_pixmap = _bgr_to_pixmap(self._frozen_bgr)
        except Exception as e:
            self.logger.warning(f"ScreenshotOverlay 冻结截屏失败: {e}", exc_info=True)
            self._dismiss(None, None)
            return

        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

        self.logger.info(
            f"ScreenshotOverlay 创建: geometry={screen_geometry}, "
            f"frozen={self._frozen_bgr.shape[1]}x{self._frozen_bgr.shape[0]}, "
            f"visible={self.isVisible()}"
        )

    def paintEvent(self, event):
        if not self._logged_paint:
            self._logged_paint = True
            self.logger.info(f"ScreenshotOverlay 首次绘制: rect={self.rect()}")

        painter = QPainter(self)
        if self._frozen_pixmap:
            painter.drawPixmap(self.rect(), self._frozen_pixmap)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.start_point is not None and self.end_point is not None:
            rect = QRect(self.start_point, self.end_point).normalized()
            if self._frozen_pixmap:
                painter.drawPixmap(rect, self._frozen_pixmap, rect)

            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.drawRect(rect)

            painter.setPen(QPen(QColor(255, 255, 0), 2))
            info = f"({rect.x()}, {rect.y()}) | {rect.width()}x{rect.height()}"
            painter.drawText(rect.x() + 5, rect.y() + 20, info)

        if self._hint_message:
            painter.setPen(QPen(QColor(255, 200, 0), 1))
            painter.drawText(12, self.height() - 36, self._hint_message)

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(12, self.height() - 12, "按 ESC 取消")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.logger.info("ScreenshotOverlay 用户按 ESC 取消")
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._hint_message = None
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_drawing = True
            self.logger.debug(
                f"ScreenshotOverlay 鼠标按下: pos=({event.pos().x()}, {event.pos().y()})"
            )

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if (
            event.button() != Qt.LeftButton
            or self.start_point is None
            or self.end_point is None
        ):
            return

        self.end_point = event.pos()
        rect = QRect(self.start_point, self.end_point).normalized()
        self.logger.info(
            f"ScreenshotOverlay 鼠标松开: 选区=({rect.x()}, {rect.y()}, "
            f"{rect.width()}x{rect.height()})"
        )

        if rect.width() > self._MIN_SELECTION and rect.height() > self._MIN_SELECTION:
            abs_rect = QRect(
                rect.x() + self._screen_origin.x(),
                rect.y() + self._screen_origin.y(),
                rect.width(),
                rect.height(),
            )
            try:
                img = slice_bgr_frame(
                    self._frozen_bgr,
                    rect.x(),
                    rect.y(),
                    rect.width(),
                    rect.height(),
                )
                self._dismiss(img, abs_rect)
            except Exception as e:
                self.logger.warning(f"ScreenshotOverlay 选区切片失败: {e}", exc_info=True)
                self._dismiss(None, abs_rect)
        else:
            self.logger.debug("ScreenshotOverlay 选区太小，请重新框选")
            self._reset_selection()

    def _reset_selection(self):
        self.start_point = None
        self.end_point = None
        self.is_drawing = False
        self._hint_message = "选区太小，请重新框选"
        self.logger.debug("ScreenshotOverlay 选区已重置")
        self.update()

    def _cancel(self):
        self._dismiss(None, None, cancelled=True)

    def _dismiss(self, img, rect, cancelled=False):
        if self._dismissing:
            return
        self._dismissing = True

        if cancelled:
            outcome = "cancelled"
        elif img is not None:
            outcome = "success"
        elif rect is not None:
            outcome = "failed"
        else:
            outcome = "init_failed"
        rect_info = (
            f"{rect.width()}x{rect.height()} @ ({rect.x()}, {rect.y()})"
            if rect is not None else "none"
        )
        self.logger.debug(f"ScreenshotOverlay dismiss: outcome={outcome}, rect={rect_info}")

        self.releaseKeyboard()
        self.hide()
        cb = self.screenshot_callback
        self.screenshot_callback = None
        self.close()
        self.deleteLater()

        if cb:
            QTimer.singleShot(0, lambda: cb(img, rect, cancelled=cancelled))

    def closeEvent(self, event):
        self.releaseKeyboard()
        self.logger.info("ScreenshotOverlay 关闭")
        super().closeEvent(event)
