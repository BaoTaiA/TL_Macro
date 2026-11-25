# -*- coding: utf-8 -*-
"""多键宏执行 Mixin"""
import threading
import time
from typing import List

from input import input_simulator, high_precision_sleep
from window_manager import window_focus_manager
from utils import get_multi_macro_mode_text
from screen_capture import release_thread_capture
from macro_types import MacroInfo, MacroState, MacroType


class MultiMacroRunnerMixin:
    def start_multi_macro(self, config_name: str, config: dict, enabled_configs_data: dict):
        """启动多键宏
        
        Args:
            config_name: 配置名称
            config: 配置字典
            enabled_configs_data: 已启用配置数据
        """
        with self.global_lock:
            # 检查是否已存在
            if config_name in self.multi_macros:
                macro_info = self.multi_macros[config_name]
                # 清理已死亡的线程
                if macro_info.thread and not macro_info.thread.is_alive():
                    self.logger.warning(f"清理已死亡的多键宏线程（配置: {config_name}）")
                    self.multi_macros.pop(config_name, None)
                elif macro_info.is_running():
                    self.logger.debug(f"多键宏已在运行（配置: {config_name}），忽略重复启动")
                    return
            
            # 检查并发数
            running_count = sum(1 for info in self.multi_macros.values() if info.is_running())
            if running_count >= self.MAX_CONCURRENT_MACROS:
                self.logger.debug(f"多键宏并发数已达上限（{self.MAX_CONCURRENT_MACROS}个），忽略启动请求（配置: {config_name}）")
                return
            
            # 检查窗口焦点
            if not window_focus_manager.is_target_window_active():
                self.logger.debug("当前窗口不是目标窗口，不执行多键宏")
                return
            
            # 验证配置
            macros = config.get("macros", [])
            mode = config.get("mode", 2)
            
            if not macros:
                self.show_message_signal.emit("警告", "没有可执行的宏序列，请先添加宏序列")
                return
            
            # 创建宏信息
            macro_info = MacroInfo(config_name, MacroType.MULTI)
            macro_info.set_state(MacroState.STARTING)
            macro_info.start_time = time.time()
            macro_info.stop_event.clear()
            
            # 创建线程
            thread = threading.Thread(
                target=self._execute_multi_macro,
                args=(macro_info, macros, mode),
                daemon=True,
                name=f"MultiMacro-{config_name}"
            )
            macro_info.thread = thread
            
            # 保存到字典
            self.multi_macros[config_name] = macro_info
            
            # 启动线程
            thread.start()
            
            mode_text = get_multi_macro_mode_text(mode)
            self.logger.info(f"多键宏开始执行（配置: {config_name}，{mode_text}）")
    
    def stop_multi_macro(self, config_name: str, force: bool = False, timeout: float = 2.0):
        """停止多键宏
        
        Args:
            config_name: 配置名称
            force: 是否强制停止（等待线程结束）
            timeout: 超时时间（秒）
        """
        with self.global_lock:
            if config_name not in self.multi_macros:
                return
            
            macro_info = self.multi_macros[config_name]
            
            if macro_info.is_stopped():
                return
            
            # 设置停止事件
            macro_info.stop_event.set()
            macro_info.set_state(MacroState.STOPPING)
            
            self.logger.info(f"多键宏停止信号已发送（配置: {config_name}）")
            
            # 如果需要强制停止，等待线程结束
            if force and macro_info.thread and macro_info.thread.is_alive():
                macro_info.thread.join(timeout=timeout)
                if macro_info.thread.is_alive():
                    self.logger.warning(f"警告：多键宏线程未在{timeout}秒内结束（配置: {config_name}）")
    
    def stop_multi_macro_fast(self, config_name: str) -> bool:
        """快速停止多键宏（无锁版本，用于热键触发）
        
        Returns:
            bool: 是否成功发送停止信号
        """
        # 不使用锁，直接访问（线程安全，因为只是读取和设置Event）
        if config_name not in self.multi_macros:
            return False
        
        macro_info = self.multi_macros[config_name]
        if macro_info.is_stopped():
            return False
        
        macro_info.stop_event.set()
        self.logger.debug(f"多键宏快速停止信号已发送（配置: {config_name}）")
        return True
    
    def _execute_multi_macro(self, macro_info: MacroInfo, macros: List[dict], mode: int):
        """执行多键宏（内部方法）
        
        Args:
            macro_info: 宏信息对象
            macros: 宏序列
            mode: 执行模式（1=循环直到再次按下, 2=执行一次, 3=循环直到松开）
        """
        config_name = macro_info.config_name
        
        try:
            # 更新状态为运行中
            macro_info.set_state(MacroState.RUNNING)
            
            if mode == 2:
                # 模式2：执行一次
                self._execute_multi_macro_once(macro_info, macros)
            else:
                # 模式1和3：循环执行
                self._execute_multi_macro_loop(macro_info, macros, mode)
            
        except Exception as e:
            self.logger.error(f"执行多键宏失败（配置: {config_name}）: {e}", exc_info=True)
            macro_info.set_state(MacroState.ERROR, str(e))
        finally:
            release_thread_capture()
            # 确保状态正确更新
            if macro_info.state == MacroState.RUNNING:
                macro_info.set_state(MacroState.STOPPED)
            macro_info.stop_time = time.time()
            
            duration = macro_info.stop_time - macro_info.start_time if macro_info.start_time else 0
            self.logger.info(f"多键宏已停止（配置: {config_name}，运行时长: {duration:.2f}秒，迭代次数: {macro_info.iteration_count}）")
    
    def _execute_multi_macro_once(self, macro_info: MacroInfo, macros: List[dict]):
        """执行多键宏一次"""
        config_name = macro_info.config_name
        
        try:
            # 执行宏序列
            input_simulator.execute_macro_sequence(macros, macro_info.stop_event)
            macro_info.iteration_count = 1
            
        except Exception as e:
            self.logger.error(f"执行多键宏序列失败（配置: {config_name}）: {e}", exc_info=True)
            raise
    
    def _execute_multi_macro_loop(self, macro_info: MacroInfo, macros: List[dict], mode: int):
        """循环执行多键宏
        
        Args:
            macro_info: 宏信息对象
            macros: 宏序列
            mode: 执行模式（1=循环直到再次按下, 3=循环直到松开）
        """
        config_name = macro_info.config_name
        
        try:
            while not macro_info.stop_event.is_set():
                # 检查窗口焦点
                if not window_focus_manager.is_target_window_active():
                    self.logger.info(f"窗口焦点已改变，停止多键宏（配置: {config_name}）")
                    break
                
                # 执行宏序列
                input_simulator.execute_macro_sequence(macros, macro_info.stop_event)
                
                # 再次检查停止信号
                if macro_info.stop_event.is_set():
                    break
                
                macro_info.iteration_count += 1
                
                # 模式1和3的区别：
                # - 模式1：循环直到再次按下（通过stop_event控制）
                # - 模式3：循环直到松开（通过stop_event控制，在热键松开时设置）
                # 两者在循环逻辑上相同，区别在于触发停止的方式
                
                # 使用可中断的sleep（避免长时间阻塞）
                high_precision_sleep(0.01, macro_info.stop_event, 0.001)
                
        except Exception as e:
            self.logger.error(f"执行多键宏循环失败（配置: {config_name}）: {e}", exc_info=True)
            raise
