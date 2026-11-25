# -*- coding: utf-8 -*-
"""宏标签页基类 - 共享热键设置与配置变更逻辑"""
from contextlib import contextmanager
from typing import Callable, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QMessageBox, QDialog

from hotkey import RecordHotkeyDialog
from logger import get_logger


class MacroTabBase(QWidget):
    """宏配置标签页基类"""

    configChanged = pyqtSignal()

    def __init__(
        self,
        parent=None,
        *,
        has_config_fn: Optional[Callable[[], bool]] = None,
        conflict_checker: Optional[Callable] = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.is_loading = False
        self.logger = get_logger()
        self._has_config_fn = has_config_fn
        self._conflict_checker = conflict_checker

    def _resolve_has_config_fn(self) -> Optional[Callable[[], bool]]:
        if self._has_config_fn:
            return self._has_config_fn
        if self.parent and hasattr(self.parent, 'has_config'):
            return self.parent.has_config
        return None

    def _resolve_conflict_checker(self) -> Optional[Callable]:
        if self._conflict_checker:
            return self._conflict_checker
        if self.parent and hasattr(self.parent, 'check_hotkey_conflict'):
            return self.parent.check_hotkey_conflict
        return None

    def _require_config(self) -> bool:
        """检查是否已选择配置，未选择时弹出提示。"""
        has_config = self._resolve_has_config_fn()
        if has_config and not has_config():
            QMessageBox.warning(self, "提示", "请先新增配置")
            return False
        return True

    def _on_user_changed(self):
        """用户修改配置时发出 configChanged（加载中不触发）。"""
        if self.is_loading:
            return
        self.configChanged.emit()

    @contextmanager
    def _guard_loading(self):
        self.is_loading = True
        try:
            yield
        finally:
            self.is_loading = False

    def _assign_hotkey(
        self,
        source: str,
        label,
        *,
        forbidden_keys=None,
        extra_validate: Optional[Callable[[str], Optional[str]]] = None,
        conflict_kwargs=None,
    ) -> bool:
        """录制热键、校验冲突并写入 label。成功返回 True。"""
        if not self._require_config():
            return False

        dialog = RecordHotkeyDialog(self)
        if dialog.exec_() != QDialog.Accepted or not dialog.hotkey:
            self.logger.debug(f"热键录制已取消: source={source}")
            return False

        hotkey = dialog.hotkey

        if forbidden_keys and hotkey in forbidden_keys:
            return False

        if extra_validate:
            error_msg = extra_validate(hotkey)
            if error_msg:
                QMessageBox.warning(self, "提示", error_msg)
                return False

        checker = self._resolve_conflict_checker()
        if checker:
            kwargs = conflict_kwargs or {}
            conflict = checker(hotkey, source, **kwargs)
            if conflict:
                conflict_type = conflict[0] if isinstance(conflict, tuple) else conflict
                self.logger.debug(
                    f"热键冲突拦截: source={source}, hotkey={hotkey}, type={conflict_type}"
                )
                QMessageBox.warning(
                    self, "热键冲突",
                    f"该热键在当前配置中已被用于{conflict_type}，请选择其他热键",
                )
                return False

        label.setText(hotkey)
        self.logger.debug(f"热键已设置: source={source}, hotkey={hotkey}")
        self._on_user_changed()
        return True

    def _reset_hotkey_label(self, label):
        label.setText("未设置")
        self._on_user_changed()
