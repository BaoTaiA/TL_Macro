# -*- coding: utf-8 -*-
"""单键宏执行 Mixin"""
import threading
import time

from input import input_simulator, high_precision_sleep
from window_manager import window_focus_manager
from utils import get_single_macro_mode_text
from screen_capture import release_thread_capture
from macro_types import MacroInfo, MacroState, MacroType


class SingleMacroRunnerMixin:
    def start_single_macro(self, config_name: str, config: dict, enabled_configs_data: dict):
        """启动单键宏
        
        Args:
            config_name: 配置名称
            config: 配置字典
            enabled_configs_data: 已启用配置数据
        """
        with self.global_lock:
            # 检查是否已存在
            if config_name in self.single_macros:
                macro_info = self.single_macros[config_name]
                # 清理已死亡的线程
                if macro_info.thread and not macro_info.thread.is_alive():
                    self.logger.warning(f"清理已死亡的单键宏线程（配置: {config_name}）")
                    self.single_macros.pop(config_name, None)
                elif macro_info.is_running():
                    self.logger.debug(f"单键宏已在运行（配置: {config_name}），忽略重复启动")
                    return
            
            # 检查并发数
            running_count = sum(1 for info in self.single_macros.values() if info.is_running())
            if running_count >= self.MAX_CONCURRENT_MACROS:
                self.logger.debug(f"单键宏并发数已达上限（{self.MAX_CONCURRENT_MACROS}个），忽略启动请求（配置: {config_name}）")
                return
            
            # 检查窗口焦点
            if not window_focus_manager.is_target_window_active():
                self.logger.debug("当前窗口不是目标窗口，不执行单键宏")
                return
            
            # 验证配置
            single_macro = config.get("single_key_macro", {})
            hotkey = single_macro.get("hotkey", "")
            press_time = single_macro.get("press_time", 20)
            interval = single_macro.get("interval", 20)
            mode = single_macro.get("mode", 1)
            
            if not hotkey:
                self.show_message_signal.emit("警告", "单键宏热键未设置")
                return
            
            # 创建宏信息
            macro_info = MacroInfo(config_name, MacroType.SINGLE)
            macro_info.set_state(MacroState.STARTING)
            macro_info.start_time = time.time()
            macro_info.stop_event.clear()
            
            # 创建线程
            thread = threading.Thread(
                target=self._execute_single_macro,
                args=(macro_info, hotkey, press_time, interval, mode),
                daemon=True,
                name=f"SingleMacro-{config_name}"
            )
            macro_info.thread = thread
            
            # 保存到字典
            self.single_macros[config_name] = macro_info
            
            # 启动线程
            thread.start()
            
            mode_text = get_single_macro_mode_text(mode)
            self.logger.info(f"单键宏开始执行（配置: {config_name}，按键: {hotkey}，{mode_text}）")
    
    def stop_single_macro(self, config_name: str, force: bool = False, timeout: float = 2.0):
        """停止单键宏
        
        Args:
            config_name: 配置名称
            force: 是否强制停止（等待线程结束）
            timeout: 超时时间（秒）
        """
        with self.global_lock:
            if config_name not in self.single_macros:
                return
            
            macro_info = self.single_macros[config_name]
            
            if macro_info.is_stopped():
                return
            
            # 设置停止事件
            macro_info.stop_event.set()
            macro_info.set_state(MacroState.STOPPING)
            
            self.logger.info(f"单键宏停止信号已发送（配置: {config_name}）")
            
            # 如果需要强制停止，等待线程结束
            if force and macro_info.thread and macro_info.thread.is_alive():
                macro_info.thread.join(timeout=timeout)
                if macro_info.thread.is_alive():
                    self.logger.warning(f"警告：单键宏线程未在{timeout}秒内结束（配置: {config_name}）")
    
    def stop_single_macro_fast(self, config_name: str) -> bool:
        """快速停止单键宏（无锁版本，用于热键触发）
        
        Returns:
            bool: 是否成功发送停止信号
        """
        # 不使用锁，直接访问（线程安全，因为只是读取和设置Event）
        if config_name not in self.single_macros:
            return False
        
        macro_info = self.single_macros[config_name]
        if macro_info.is_stopped():
            return False
        
        macro_info.stop_event.set()
        self.logger.debug(f"单键宏快速停止信号已发送（配置: {config_name}）")
        return True
    
    def _execute_single_macro(self, macro_info: MacroInfo, key: str, press_time: int,
                             interval: int, mode: int):
        """执行单键宏（内部方法）
        
        Args:
            macro_info: 宏信息对象
            key: 按键名称
            press_time: 按下时间（毫秒）
            interval: 间隔时间（毫秒）
            mode: 执行模式（1=循环直到再次按下, 2=循环直到松开）
        """
        config_name = macro_info.config_name
        
        try:
            # 更新状态为运行中
            macro_info.set_state(MacroState.RUNNING)
            
            # 转换为秒
            press_time_sec = press_time / 1000.0
            interval_time_sec = interval / 1000.0
            
            # 获取虚拟键码
            vk_code = input_simulator.get_virtual_key(key)
            if vk_code == 0:
                raise ValueError(f"无效的按键: {key}")
            
            # 判断是否为鼠标按键
            from key_mapping import key_mapping
            is_mouse = key_mapping.is_mouse_key(key)
            
            # 循环执行
            while not macro_info.stop_event.is_set():
                # 检查窗口焦点
                if not window_focus_manager.is_target_window_active():
                    self.logger.info(f"窗口焦点已改变，停止单键宏（配置: {config_name}）")
                    break
                
                # 按下按键
                if is_mouse:
                    input_simulator.send_mouse_event(vk_code, True)
                else:
                    flags_down = input_simulator.get_key_flags(key, True)
                    input_simulator.send_key_event(vk_code, flags_down, key)
                
                # 保持按下状态（可中断）
                high_precision_sleep(press_time_sec, macro_info.stop_event, 0.001)
                
                # 检查停止事件
                if macro_info.stop_event.is_set():
                    # 确保释放按键
                    if is_mouse:
                        input_simulator.send_mouse_event(vk_code, False)
                    else:
                        flags_up = input_simulator.get_key_flags(key, False)
                        input_simulator.send_key_event(vk_code, flags_up, key)
                    break
                
                # 释放按键
                if is_mouse:
                    input_simulator.send_mouse_event(vk_code, False)
                else:
                    flags_up = input_simulator.get_key_flags(key, False)
                    input_simulator.send_key_event(vk_code, flags_up, key)
                
                # 检查停止事件
                if macro_info.stop_event.is_set():
                    break
                
                # 间隔时间（可中断）
                high_precision_sleep(interval_time_sec, macro_info.stop_event, 0.001)
                
                macro_info.iteration_count += 1
                
        except Exception as e:
            self.logger.error(f"执行单键宏失败（配置: {config_name}）: {e}", exc_info=True)
            macro_info.set_state(MacroState.ERROR, str(e))
        finally:
            release_thread_capture()
            # 确保状态正确更新
            if macro_info.state == MacroState.RUNNING:
                macro_info.set_state(MacroState.STOPPED)
            macro_info.stop_time = time.time()
            
            duration = macro_info.stop_time - macro_info.start_time if macro_info.start_time else 0
            self.logger.info(f"单键宏已停止（配置: {config_name}，运行时长: {duration:.2f}秒，迭代次数: {macro_info.iteration_count}）")
