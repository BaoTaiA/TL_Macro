# -*- coding: utf-8 -*-
"""热键监听管理模块"""
import logging
import threading
import time
from pynput import mouse

from logger import get_logger
from key_mapping import key_mapping


class HotkeyManager:
    """热键管理器"""
    
    def __init__(self, macro_executor, enabled_configs_data_getter, rebuild_hotkey_maps_callback):
        self.logger = get_logger()
        self.macro_executor = macro_executor
        self.enabled_configs_data_getter = enabled_configs_data_getter
        self.rebuild_hotkey_maps_callback = rebuild_hotkey_maps_callback
        
        # 热键映射（预计算，避免每次循环都计算）
        self.keyboard_hotkey_map = {}  # {keyboard_key: (config_name, "multi"/"single", original_hotkey, mode)}
        self.mouse_hotkey_map = {}  # {mouse_button: (config_name, "multi"/"single", mode)}
        
        # 热键状态跟踪 - 使用更严格的状态管理
        self.multi_hotkey_pressed = {}  # {config_name: bool} 多键宏热键按下状态
        self.single_hotkey_pressed = {}  # {config_name: bool} 单键宏热键按下状态
        self.mouse_pressed_multi = {}  # {config_name: bool} 鼠标多键宏按下状态
        self.mouse_pressed_single = {}  # {config_name: bool} 鼠标单键宏按下状态
        self.image_hotkey_pressed = {}  # {config_name: bool} 图像宏热键按下状态
        self.mouse_pressed_image = {}  # {config_name: bool} 鼠标图像宏按下状态
        
        # 热键监听相关属性
        self.is_listening = False
        self.keyboard_listener_thread = None
        self.mouse_listener_thread = None
        # 键盘事件驱动的hook列表（用于动态管理）
        self.keyboard_hooks = {}  # {keyboard_key: hook_handle}
        
        # 用于线程同步的事件（事件驱动优化）
        self._map_update_event = threading.Event()
        self._map_update_lock = threading.Lock()
    
    def rebuild_hotkey_maps(self):
        """重建热键映射（键盘和鼠标）"""
        enabled_configs_data = self.enabled_configs_data_getter()
        
        mouse_button_map = {
            "鼠标左键": mouse.Button.left,
            "鼠标中键": mouse.Button.middle,
            "鼠标右键": mouse.Button.right,
            "鼠标侧键1": mouse.Button.x1,
            "鼠标侧键2": mouse.Button.x2
        }
        
        with self._map_update_lock:
            self.keyboard_hotkey_map.clear()
            self.mouse_hotkey_map.clear()
            
            for config_name, config in enabled_configs_data.items():
                # 处理多键宏热键
                multi_hotkey = config.get("hotkey", "")
                if multi_hotkey:
                    if key_mapping.is_mouse_key(multi_hotkey):
                        # 鼠标热键
                        mouse_button = mouse_button_map.get(multi_hotkey)
                        if mouse_button:
                            mode = config.get("mode", 2)
                            self.mouse_hotkey_map[mouse_button] = (config_name, "multi", mode)
                    else:
                        # 键盘热键
                        keyboard_key = key_mapping.display_to_keyboard(multi_hotkey)
                        if keyboard_key:
                            mode = config.get("mode", 2)
                            self.keyboard_hotkey_map[keyboard_key] = (config_name, "multi", multi_hotkey, mode)
                
                # 处理单键宏热键
                single_macro = config.get("single_key_macro", {})
                single_hotkey = single_macro.get("hotkey", "")
                if single_hotkey:
                    if key_mapping.is_mouse_key(single_hotkey):
                        # 鼠标热键
                        mouse_button = mouse_button_map.get(single_hotkey)
                        if mouse_button:
                            mode = single_macro.get("mode", 1)
                            # 如果已有相同鼠标按键的多键宏，跳过（避免冲突）
                            if mouse_button not in self.mouse_hotkey_map:
                                self.mouse_hotkey_map[mouse_button] = (config_name, "single", mode)
                    else:
                        # 键盘热键
                        keyboard_key = key_mapping.display_to_keyboard(single_hotkey)
                        if keyboard_key:
                            mode = single_macro.get("mode", 1)
                            # 如果已有相同键盘按键的多键宏，跳过（避免冲突）
                            if keyboard_key not in self.keyboard_hotkey_map:
                                self.keyboard_hotkey_map[keyboard_key] = (config_name, "single", single_hotkey, mode)
                            else:
                                self.logger.warning(
                                    f"单键宏热键未注册（与更高优先级热键冲突）: "
                                    f"配置={config_name}, 热键={single_hotkey!r}"
                                )

                # 处理图像宏热键
                image_macro = config.get("image_macro", {})
                image_hotkey = image_macro.get("hotkey", "")
                if image_hotkey:
                    if key_mapping.is_mouse_key(image_hotkey):
                        mouse_button = mouse_button_map.get(image_hotkey)
                        if mouse_button and mouse_button not in self.mouse_hotkey_map:
                            mode = image_macro.get("mode", 1)
                            self.mouse_hotkey_map[mouse_button] = (config_name, "image", mode)
                        elif mouse_button and mouse_button in self.mouse_hotkey_map:
                            self.logger.warning(
                                f"图像宏热键未注册（与更高优先级热键冲突）: "
                                f"配置={config_name}, 热键={image_hotkey!r}"
                            )
                    else:
                        keyboard_key = key_mapping.display_to_keyboard(image_hotkey)
                        if keyboard_key and keyboard_key not in self.keyboard_hotkey_map:
                            mode = image_macro.get("mode", 1)
                            self.keyboard_hotkey_map[keyboard_key] = (config_name, "image", image_hotkey, mode)
                        elif keyboard_key and keyboard_key in self.keyboard_hotkey_map:
                            self.logger.warning(
                                f"图像宏热键未注册（与更高优先级热键冲突）: "
                                f"配置={config_name}, 热键={image_hotkey!r}"
                            )
        
        # 通知监听线程需要更新hooks（事件驱动优化）
        # 注意：事件设置在锁外，避免死锁
        self._map_update_event.set()
    
    def _join_listener_threads(self, timeout: float = 1.0):
        """等待监听线程退出"""
        for thread in (self.keyboard_listener_thread, self.mouse_listener_thread):
            if thread and thread.is_alive():
                thread.join(timeout=timeout)

    def start_hotkey_listener(self):
        """启动热键监听"""
        if self.is_listening:
            return

        if (
            (self.keyboard_listener_thread and self.keyboard_listener_thread.is_alive())
            or (self.mouse_listener_thread and self.mouse_listener_thread.is_alive())
        ):
            self.stop_hotkey_listener()

        try:
            self.is_listening = True
            self._map_update_event.clear()  # 清除事件状态
            
            # 启动键盘热键监听线程
            self.keyboard_listener_thread = threading.Thread(
                target=self.keyboard_hotkey_listen_loop, 
                daemon=True,
                name="HotkeyKeyboardListener"
            )
            self.keyboard_listener_thread.start()
            
            # 启动鼠标热键监听线程
            self.mouse_listener_thread = threading.Thread(
                target=self.mouse_hotkey_listen_loop, 
                daemon=True,
                name="HotkeyMouseListener"
            )
            self.mouse_listener_thread.start()
            
            self.logger.info("热键监听已启动（事件驱动模式）")
        except Exception as e:
            self.logger.error(f"启动热键监听失败: {e}", exc_info=True)
    
    def stop_hotkey_listener(self):
        """停止热键监听"""
        self.is_listening = False
        self._map_update_event.set()  # 唤醒等待的线程，确保能及时退出
        
        # 清理键盘hooks
        try:
            import keyboard as kb
            for keyboard_key, (hook_press, hook_release) in list(self.keyboard_hooks.items()):
                try:
                    kb.unhook(hook_press)
                    kb.unhook(hook_release)
                except Exception as e:
                    self.logger.debug(f"清理键盘 hook 失败: {e}")
            self.keyboard_hooks.clear()
        except Exception as e:
            self.logger.debug(f"停止键盘热键监听时清理失败: {e}")

        self._join_listener_threads()
    
    def keyboard_hotkey_listen_loop(self):
        """键盘热键监听循环（优化版：使用事件驱动，大幅降低CPU占用）"""
        import keyboard as kb
        
        # 注册所有热键的事件驱动回调
        def register_hotkey_hooks():
            """注册所有热键的hook"""
            # 清理旧的hooks
            for keyboard_key, (hook_press, hook_release) in list(self.keyboard_hooks.items()):
                try:
                    kb.unhook(hook_press)
                    kb.unhook(hook_release)
                except Exception as e:
                    self.logger.debug(f"清理旧键盘 hook 失败: {e}")
            self.keyboard_hooks.clear()
            
            # 在锁内读取映射（确保线程安全）
            with self._map_update_lock:
                keyboard_hotkey_map_copy = dict(self.keyboard_hotkey_map)
            
            # 在锁外注册hooks（避免在锁内执行可能阻塞的操作）
            for keyboard_key, (config_name, hotkey_type, original_hotkey, mode) in keyboard_hotkey_map_copy.items():
                try:
                    # 按下事件回调
                    def make_press_callback(cfg_name, hk_type, hk_mode):
                        def on_press(event):
                            if not self.is_listening:
                                return
                            try:
                                self.logger.debug(
                                    f"热键按下: config={cfg_name}, type={hk_type}"
                                )
                                if hk_type == "multi":
                                    with self.macro_executor.macro_lock:
                                        if not self.multi_hotkey_pressed.get(cfg_name, False):
                                            self.multi_hotkey_pressed[cfg_name] = True
                                            self.on_multi_hotkey_triggered(cfg_name)
                                elif hk_type == "single":
                                    with self.macro_executor.macro_lock:
                                        if not self.single_hotkey_pressed.get(cfg_name, False):
                                            self.single_hotkey_pressed[cfg_name] = True
                                            self.on_single_hotkey_triggered(cfg_name)
                                elif hk_type == "image":
                                    with self.macro_executor.macro_lock:
                                        is_pressed = self.image_hotkey_pressed.get(cfg_name, False)
                                        is_running = self.macro_executor.is_image_macro_running(cfg_name)
                                        if hk_mode == 3:
                                            should_toggle = not is_pressed and not is_running
                                        else:
                                            should_toggle = not is_pressed or is_running
                                        if should_toggle:
                                            self.image_hotkey_pressed[cfg_name] = True
                                            self.on_image_hotkey_triggered(cfg_name)
                            except Exception as e:
                                self.logger.error(f"热键按下回调错误: {e}", exc_info=True)
                        return on_press
                    
                    # 松开事件回调
                    def make_release_callback(cfg_name, hk_type, m):
                        def on_release(event):
                            if not self.is_listening:
                                return
                            try:
                                if hk_type == "multi":
                                    with self.macro_executor.macro_lock:
                                        macro_info = self.macro_executor.multi_macros.get(cfg_name)
                                        if macro_info and macro_info.is_running() and m == 3:
                                            self.macro_executor.stop_multi_macro(cfg_name)
                                        self.multi_hotkey_pressed[cfg_name] = False
                                elif hk_type == "single":
                                    with self.macro_executor.macro_lock:
                                        macro_info = self.macro_executor.single_macros.get(cfg_name)
                                        if macro_info and macro_info.is_running() and m == 2:
                                            self.macro_executor.stop_single_macro(cfg_name)
                                        self.single_hotkey_pressed[cfg_name] = False
                                elif hk_type == "image":
                                    with self.macro_executor.macro_lock:
                                        macro_info = self.macro_executor.image_macros.get(cfg_name)
                                        if macro_info and macro_info.is_running() and m == 3:
                                            self.macro_executor.stop_image_macro(cfg_name)
                                        self.image_hotkey_pressed[cfg_name] = False
                            except Exception as e:
                                self.logger.error(f"热键松开回调错误: {e}", exc_info=True)
                        return on_release
                    
                    # 注册按下和松开事件
                    press_callback = make_press_callback(config_name, hotkey_type, mode)
                    release_callback = make_release_callback(config_name, hotkey_type, mode)
                    
                    hook_press = kb.on_press_key(keyboard_key, press_callback, suppress=False)
                    hook_release = kb.on_release_key(keyboard_key, release_callback, suppress=False)
                    
                    # 保存hook句柄（用于后续清理）
                    self.keyboard_hooks[keyboard_key] = (hook_press, hook_release)
                    
                except Exception as e:
                    self.logger.error(f"注册热键 {keyboard_key} 失败: {e}", exc_info=True)
        
        # 初始注册所有热键（如果有已启用的配置）
        # 优化：如果热键映射为空，跳过注册，减少启动时的CPU占用
        with self._map_update_lock:
            has_hotkeys = len(self.keyboard_hotkey_map) > 0 or len(self.mouse_hotkey_map) > 0
        
        if has_hotkeys:
            register_hotkey_hooks()
            with self._map_update_lock:
                kb_map = dict(self.keyboard_hotkey_map)
                mouse_map = dict(self.mouse_hotkey_map)
            self.logger.debug(
                f"热键 hooks 已注册: keyboard={len(kb_map)}, mouse={len(mouse_map)}"
            )
            if self.logger.isEnabledFor(logging.DEBUG):
                for key, (cfg, hk_type, orig, mode) in kb_map.items():
                    self.logger.debug(
                        f"  键盘热键: key={key}, config={cfg}, type={hk_type}, mode={mode}"
                    )
        else:
            self.logger.debug("没有已启用的热键，跳过hooks注册")
        
        # 主循环：等待热键映射更新事件（事件驱动，不再轮询）
        while self.is_listening:
            try:
                # 等待更新事件（最多等待5秒，用于定期检查 is_listening 状态）
                # 如果5秒内没有更新事件，也会检查一次 is_listening，确保能及时响应停止请求
                if self._map_update_event.wait(timeout=5.0):
                    # 收到更新事件，重新注册hooks
                    self._map_update_event.clear()
                    
                    if not self.is_listening:
                        break
                    
                    # 重新注册所有hooks（如果有热键需要注册）
                    with self._map_update_lock:
                        has_hotkeys = len(self.keyboard_hotkey_map) > 0 or len(self.mouse_hotkey_map) > 0
                    
                    if has_hotkeys:
                        register_hotkey_hooks()
                        self.logger.info("热键映射已更新，重新注册事件驱动hooks（事件驱动模式）")
                    else:
                        # 如果没有热键，清理所有hooks
                        for keyboard_key, (hook_press, hook_release) in list(self.keyboard_hooks.items()):
                            try:
                                kb.unhook(hook_press)
                                kb.unhook(hook_release)
                            except Exception as e:
                                self.logger.debug(f"清理键盘 hook 失败: {e}")
                        self.keyboard_hooks.clear()
                
                # 即使没有更新事件，也定期检查 is_listening 状态（5秒一次）
                # 这样可以及时响应停止请求
                
            except Exception as e:
                self.logger.error(f"键盘热键监听错误: {e}", exc_info=True)
                time.sleep(0.5)
        
        # 清理所有hooks
        for keyboard_key, (hook_press, hook_release) in list(self.keyboard_hooks.items()):
            try:
                kb.unhook(hook_press)
                kb.unhook(hook_release)
            except Exception as e:
                self.logger.debug(f"清理键盘 hook 失败: {e}")
        self.keyboard_hooks.clear()
    
    def mouse_hotkey_listen_loop(self):
        """鼠标热键监听循环（监听所有已启用配置）"""
        def on_click(x, y, button, pressed):
            # 直接使用预计算的鼠标热键映射，无需读取文件
            if button in self.mouse_hotkey_map:
                config_name, hotkey_type, mode = self.mouse_hotkey_map[button]
                
                with self.macro_executor.macro_lock:
                    if hotkey_type == "multi":
                        if pressed:
                            # 修复：即使状态为True，如果宏正在运行，也应该允许触发停止
                            # 这样可以解决 Logitech G HUB 拦截鼠标事件导致的状态卡死问题
                            is_pressed = self.mouse_pressed_multi.get(config_name, False)
                            is_running = self.macro_executor.is_multi_macro_running(config_name)
                            
                            if not is_pressed or is_running:
                                # 如果状态未按下，或者宏正在运行，都允许触发
                                # 这样可以确保即使状态卡死，也能停止宏
                                self.mouse_pressed_multi[config_name] = True
                                self.on_multi_hotkey_triggered(config_name)
                        elif not pressed:
                            # 模式3：松开停止（必须在锁内检查，确保状态一致性）
                            macro_info = self.macro_executor.multi_macros.get(config_name)
                            if macro_info and macro_info.is_running() and mode == 3:
                                self.macro_executor.stop_multi_macro(config_name)
                            # 确保状态重置
                            self.mouse_pressed_multi[config_name] = False
                    elif hotkey_type == "single":
                        if pressed:
                            is_pressed = self.mouse_pressed_single.get(config_name, False)
                            is_running = self.macro_executor.is_single_macro_running(config_name)
                            if not is_pressed or is_running:
                                self.mouse_pressed_single[config_name] = True
                                self.on_single_hotkey_triggered(config_name)
                        elif not pressed:
                            macro_info = self.macro_executor.single_macros.get(config_name)
                            if macro_info and macro_info.is_running() and mode == 2:
                                self.macro_executor.stop_single_macro(config_name)
                            self.mouse_pressed_single[config_name] = False
                    elif hotkey_type == "image":
                        if pressed:
                            is_pressed = self.mouse_pressed_image.get(config_name, False)
                            is_running = self.macro_executor.is_image_macro_running(config_name)
                            if not is_pressed or is_running:
                                self.mouse_pressed_image[config_name] = True
                                self.on_image_hotkey_triggered(config_name)
                        elif not pressed:
                            macro_info = self.macro_executor.image_macros.get(config_name)
                            if macro_info and macro_info.is_running() and mode == 3:
                                self.macro_executor.stop_image_macro(config_name)
                            self.mouse_pressed_image[config_name] = False
            
            return True  # 继续监听
        
        listener = None
        try:
            listener = mouse.Listener(on_click=on_click)
            listener.start()
            # 使用事件驱动的监听，无需轮询
            while self.is_listening:
                time.sleep(0.5)  # 降低检查频率，减少CPU占用
        except Exception as e:
            self.logger.error(f"鼠标热键监听错误: {e}", exc_info=True)
        finally:
            # 确保监听器总是被停止
            if listener:
                try:
                    listener.stop()
                except Exception as e:
                    self.logger.debug(f"停止鼠标监听器失败: {e}")
    
    def on_multi_hotkey_triggered(self, config_name):
        """多键宏热键触发 - 专业级实现"""
        enabled_configs_data = self.enabled_configs_data_getter()
        config = enabled_configs_data.get(config_name)
        if not config:
            self.logger.warning(f"无法加载配置: {config_name}")
            return
        
        with self.macro_executor.macro_lock:
            # 检查宏是否正在运行（双重检查，确保准确性）
            is_running = self.macro_executor.is_multi_macro_running(config_name)
            
            if is_running:
                # 如果该配置的宏正在运行，停止它
                self.macro_executor.stop_multi_macro(config_name)
                # 重置热键按下状态
                self.multi_hotkey_pressed[config_name] = False
                self.mouse_pressed_multi[config_name] = False
            else:
                # 启动该配置的宏
                self.macro_executor.start_multi_macro(config_name, config, enabled_configs_data)
    
    def on_single_hotkey_triggered(self, config_name):
        """单键宏热键触发 - 专业级实现"""
        enabled_configs_data = self.enabled_configs_data_getter()
        config = enabled_configs_data.get(config_name)
        if not config:
            self.logger.warning(f"无法加载配置: {config_name}")
            return
        
        with self.macro_executor.macro_lock:
            # 检查宏是否正在运行（双重检查，确保准确性）
            is_running = self.macro_executor.is_single_macro_running(config_name)
            
            if is_running:
                # 如果该配置的宏正在运行，停止它
                self.macro_executor.stop_single_macro(config_name)
                # 重置热键按下状态
                self.single_hotkey_pressed[config_name] = False
                self.mouse_pressed_single[config_name] = False
            else:
                # 启动该配置的宏
                self.macro_executor.start_single_macro(config_name, config, enabled_configs_data)

    def on_image_hotkey_triggered(self, config_name):
        """图像宏热键触发"""
        enabled_configs_data = self.enabled_configs_data_getter()
        config = enabled_configs_data.get(config_name)
        if not config:
            self.logger.warning(f"无法加载配置: {config_name}")
            return

        with self.macro_executor.macro_lock:
            is_running = self.macro_executor.is_image_macro_running(config_name)
            if is_running:
                self.macro_executor.stop_image_macro(config_name)
                self.image_hotkey_pressed[config_name] = False
                self.mouse_pressed_image[config_name] = False
            else:
                self.macro_executor.start_image_macro(config_name, config, enabled_configs_data)

    def clear_hotkey_states(self):
        """清空热键状态"""
        self.multi_hotkey_pressed.clear()
        self.single_hotkey_pressed.clear()
        self.image_hotkey_pressed.clear()
        self.mouse_pressed_multi.clear()
        self.mouse_pressed_single.clear()
        self.mouse_pressed_image.clear()
    
