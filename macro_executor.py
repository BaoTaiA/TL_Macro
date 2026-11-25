# -*- coding: utf-8 -*-
"""宏执行管理模块 - 门面类，组合各类型宏 Runner Mixin"""
import threading
from typing import Dict

from PyQt5.QtCore import pyqtSignal, QObject

from logger import get_logger
from macro_types import MacroInfo, MacroState, MacroType
from multi_macro_runner import MultiMacroRunnerMixin
from single_macro_runner import SingleMacroRunnerMixin
from image_macro_runner import ImageMacroRunnerMixin

# 向后兼容：外部模块可继续从 macro_executor 导入类型
__all__ = [
    'MacroExecutor', 'MacroInfo', 'MacroState', 'MacroType',
]


class MacroExecutor(
    QObject,
    MultiMacroRunnerMixin,
    SingleMacroRunnerMixin,
    ImageMacroRunnerMixin,
):
    """宏执行器"""

    show_message_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.logger = get_logger()

        self.multi_macros: Dict[str, MacroInfo] = {}
        self.single_macros: Dict[str, MacroInfo] = {}
        self.image_macros: Dict[str, MacroInfo] = {}
        self.config_dir = "config"

        self.MAX_CONCURRENT_MACROS = 2
        self.MAX_CONCURRENT_IMAGE_MACROS = 1
        self.global_lock = threading.RLock()

        self.logger.info("宏执行器初始化完成（全新设计版本）")

    @property
    def macro_lock(self):
        return self.global_lock

    def stop_all_macros(self):
        """停止所有宏执行"""
        self.logger.info("开始停止所有宏...")

        with self.global_lock:
            for config_name in list(self.multi_macros.keys()):
                self.stop_multi_macro(config_name, force=True, timeout=0.3)

            for config_name in list(self.single_macros.keys()):
                self.stop_single_macro(config_name, force=True, timeout=0.3)

            for config_name in list(self.image_macros.keys()):
                self.stop_image_macro(config_name, force=True, timeout=0.3)

            self._cleanup_stopped_macros()

        self.logger.info("所有宏执行已完全停止")

    def is_multi_macro_running(self, config_name: str) -> bool:
        with self.global_lock:
            if config_name not in self.multi_macros:
                return False

            macro_info = self.multi_macros[config_name]
            if macro_info.thread and not macro_info.thread.is_alive():
                if macro_info.is_running():
                    self.logger.warning(
                        f"检测到多键宏线程已死亡但状态仍为运行中（配置: {config_name}），自动修复"
                    )
                    macro_info.set_state(MacroState.STOPPED)
                return False

            return macro_info.is_running()

    def is_single_macro_running(self, config_name: str) -> bool:
        with self.global_lock:
            if config_name not in self.single_macros:
                return False

            macro_info = self.single_macros[config_name]
            if macro_info.thread and not macro_info.thread.is_alive():
                if macro_info.is_running():
                    self.logger.warning(
                        f"检测到单键宏线程已死亡但状态仍为运行中（配置: {config_name}），自动修复"
                    )
                    macro_info.set_state(MacroState.STOPPED)
                return False

            return macro_info.is_running()

    def recover_inconsistent_states(
        self,
        multi_hotkey_pressed: dict,
        single_hotkey_pressed: dict,
        mouse_pressed_multi: dict,
        mouse_pressed_single: dict,
        image_hotkey_pressed: dict = None,
        mouse_pressed_image: dict = None,
    ):
        """状态恢复机制 - 定期检查并修复不一致状态"""
        if image_hotkey_pressed is None:
            image_hotkey_pressed = {}
        if mouse_pressed_image is None:
            mouse_pressed_image = {}

        if (not self.multi_macros and not self.single_macros and not self.image_macros and
                not multi_hotkey_pressed and not single_hotkey_pressed and
                not mouse_pressed_multi and not mouse_pressed_single and
                not image_hotkey_pressed and not mouse_pressed_image):
            return

        with self.global_lock:
            for config_name, macro_info in list(self.multi_macros.items()):
                if macro_info.is_running():
                    if not macro_info.thread or not macro_info.thread.is_alive():
                        self.logger.warning(
                            f"状态恢复：检测到多键宏状态不一致（配置: {config_name}），自动修复"
                        )
                        macro_info.set_state(MacroState.STOPPED)
                        multi_hotkey_pressed.pop(config_name, None)
                        mouse_pressed_multi.pop(config_name, None)
                elif macro_info.thread and macro_info.thread.is_alive():
                    self.logger.warning(
                        f"状态恢复：检测到多键宏残留线程（配置: {config_name}），发送停止信号"
                    )
                    macro_info.stop_event.set()
                    if not macro_info.thread.is_alive():
                        self.multi_macros.pop(config_name, None)

            for config_name, macro_info in list(self.single_macros.items()):
                if macro_info.is_running():
                    if not macro_info.thread or not macro_info.thread.is_alive():
                        self.logger.warning(
                            f"状态恢复：检测到单键宏状态不一致（配置: {config_name}），自动修复"
                        )
                        macro_info.set_state(MacroState.STOPPED)
                        single_hotkey_pressed.pop(config_name, None)
                        mouse_pressed_single.pop(config_name, None)
                elif macro_info.thread and macro_info.thread.is_alive():
                    self.logger.warning(
                        f"状态恢复：检测到单键宏残留线程（配置: {config_name}），发送停止信号"
                    )
                    macro_info.stop_event.set()
                    if not macro_info.thread.is_alive():
                        self.single_macros.pop(config_name, None)

            for config_name, macro_info in list(self.image_macros.items()):
                if macro_info.is_running():
                    if not macro_info.any_worker_alive():
                        self.logger.warning(
                            f"状态恢复：检测到图像宏状态不一致（配置: {config_name}），自动修复"
                        )
                        macro_info.set_state(MacroState.STOPPED)
                        image_hotkey_pressed.pop(config_name, None)
                        mouse_pressed_image.pop(config_name, None)
                elif macro_info.any_worker_alive():
                    self.logger.warning(
                        f"状态恢复：检测到图像宏残留线程（配置: {config_name}），发送停止信号"
                    )
                    macro_info.stop_event.set()
                    if not macro_info.any_worker_alive():
                        self.image_macros.pop(config_name, None)

            for config_name in list(mouse_pressed_image.keys()):
                if config_name not in self.image_macros:
                    mouse_pressed_image.pop(config_name, None)
                    image_hotkey_pressed.pop(config_name, None)
                elif not self.image_macros[config_name].is_running():
                    mouse_pressed_image.pop(config_name, None)
                    image_hotkey_pressed.pop(config_name, None)

            for config_name in list(mouse_pressed_multi.keys()):
                if config_name not in self.multi_macros:
                    mouse_pressed_multi.pop(config_name, None)
                    multi_hotkey_pressed.pop(config_name, None)
                    self.logger.debug(
                        f"状态恢复：自动重置多键宏鼠标热键状态（配置: {config_name}）"
                    )
                elif not self.multi_macros[config_name].is_running():
                    mouse_pressed_multi.pop(config_name, None)
                    multi_hotkey_pressed.pop(config_name, None)
                    self.logger.debug(
                        f"状态恢复：自动重置多键宏鼠标热键状态（配置: {config_name}）"
                    )

            for config_name in list(mouse_pressed_single.keys()):
                if config_name not in self.single_macros:
                    mouse_pressed_single.pop(config_name, None)
                    single_hotkey_pressed.pop(config_name, None)
                    self.logger.debug(
                        f"状态恢复：自动重置单键宏鼠标热键状态（配置: {config_name}）"
                    )
                elif not self.single_macros[config_name].is_running():
                    mouse_pressed_single.pop(config_name, None)
                    single_hotkey_pressed.pop(config_name, None)
                    self.logger.debug(
                        f"状态恢复：自动重置单键宏鼠标热键状态（配置: {config_name}）"
                    )

            self._cleanup_stopped_macros()

    def _cleanup_stopped_macros(self):
        with self.global_lock:
            to_remove_multi = [
                name for name, info in self.multi_macros.items()
                if info.is_stopped() and (not info.thread or not info.thread.is_alive())
            ]
            for config_name in to_remove_multi:
                self.multi_macros.pop(config_name, None)
                self.logger.debug(f"清理已停止的多键宏（配置: {config_name}）")

            to_remove_single = [
                name for name, info in self.single_macros.items()
                if info.is_stopped() and (not info.thread or not info.thread.is_alive())
            ]
            for config_name in to_remove_single:
                self.single_macros.pop(config_name, None)
                self.logger.debug(f"清理已停止的单键宏（配置: {config_name}）")

            to_remove_image = [
                name for name, info in self.image_macros.items()
                if info.is_stopped() and not info.any_worker_alive()
            ]
            for config_name in to_remove_image:
                self.image_macros.pop(config_name, None)
                self.logger.debug(f"清理已停止的图像宏（配置: {config_name}）")
