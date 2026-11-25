# -*- coding: utf-8 -*-
import ctypes
from ctypes import wintypes, c_int64

from logger import get_logger
from key_mapping import key_mapping

# Windows API 常量
KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001  # 扩展键标志（用于右侧修饰键等）
KEYEVENTF_SCANCODE = 0x0008     # 使用扫描码而不是虚拟键码

# 鼠标事件常量
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002

# Windows 结构体定义
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]

# 输入类型常量
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

class HighPrecisionTimer:
    """高精度定时器 - 支持可中断的睡眠"""
    
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        self.frequency = c_int64()
        
        # 获取QPC频率
        if not self.kernel32.QueryPerformanceFrequency(ctypes.byref(self.frequency)):
            raise RuntimeError("QueryPerformanceFrequency failed")
        
        logger = get_logger()
        logger.info(f"高精度定时器初始化: 频率 = {self.frequency.value} Hz")
    
    def sleep(self, duration_sec, stop_event=None, check_interval=0.001):
        """高精度睡眠 - 支持中断
        
        Args:
            duration_sec: 睡眠时长（秒）
            stop_event: threading.Event，如果设置则中断睡眠
            check_interval: 检查停止事件的间隔（秒），默认1ms
        """
        if duration_sec <= 0:
            return
        
        if stop_event is None:
            # 没有停止事件，使用原始逻辑
            if duration_sec <= 0.002:  # 2ms以下：纯忙等待（最高精度）
                self._busy_wait(duration_sec)
            else:  # 2ms以上：精确sleep
                self._precise_sleep(duration_sec)
        else:
            # 有停止事件，使用可中断睡眠
            self._interruptible_sleep(duration_sec, stop_event, check_interval)
    
    def _busy_wait(self, duration_sec):
        """纯忙等待 - 用于极短时间（2ms以下）
        
        注意：此方法会占用CPU，但这是必要的权衡，用于实现微秒级精度。
        仅在极短时间（<=2ms）时使用，其他情况使用_precise_sleep。
        由于等待时间极短，CPU占用影响可忽略。
        """
        start = c_int64()
        if not self.kernel32.QueryPerformanceCounter(ctypes.byref(start)):
            return
            
        target_ticks = int(duration_sec * self.frequency.value)
        
        while True:
            current = c_int64()
            if not self.kernel32.QueryPerformanceCounter(ctypes.byref(current)):
                break
            if current.value - start.value >= target_ticks:
                break
    
    def _precise_sleep(self, duration_sec):
        """精确sleep - 用于较长时间"""
        sleep_ms = max(1, int(duration_sec * 1000))
        ctypes.windll.kernel32.Sleep(sleep_ms)
    
    def _interruptible_sleep(self, duration_sec, stop_event, check_interval):
        """可中断的睡眠 - 定期检查停止事件"""
        start = c_int64()
        if not self.kernel32.QueryPerformanceCounter(ctypes.byref(start)):
            return
        
        target_ticks = int(duration_sec * self.frequency.value)
        check_interval_ticks = int(check_interval * self.frequency.value)
        
        while True:
            # 检查停止事件
            if stop_event and stop_event.is_set():
                return
            
            current = c_int64()
            if not self.kernel32.QueryPerformanceCounter(ctypes.byref(current)):
                break
            
            elapsed = current.value - start.value
            if elapsed >= target_ticks:
                break
            
            # 计算剩余时间
            remaining = target_ticks - elapsed
            if remaining > check_interval_ticks:
                # 还有足够时间，sleep一小段
                sleep_ms = max(1, int(check_interval * 1000))
                ctypes.windll.kernel32.Sleep(sleep_ms)
            else:
                # 剩余时间很短，忙等待
                while True:
                    if stop_event and stop_event.is_set():
                        return
                    current = c_int64()
                    if not self.kernel32.QueryPerformanceCounter(ctypes.byref(current)):
                        return
                    if current.value - start.value >= target_ticks:
                        return

# 创建全局高精度定时器
_high_precision_timer = HighPrecisionTimer()

def high_precision_sleep(duration_sec, stop_event=None, check_interval=0.001):
    """高精度睡眠函数 - 支持中断
    
    Args:
        duration_sec: 睡眠时长（秒）
        stop_event: threading.Event，如果设置则中断睡眠
        check_interval: 检查停止事件的间隔（秒），默认1ms
    """
    _high_precision_timer.sleep(duration_sec, stop_event, check_interval)

class InputSimulator:
    """输入模拟器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.user32 = ctypes.windll.user32
        
    def get_virtual_key(self, key_name):
        """获取虚拟键码"""
        vk_code = key_mapping.display_to_ctypes(key_name)
        
        if vk_code == 0:
            self.logger.warning(f"未找到按键 '{key_name}' 的虚拟键码映射")
            # 尝试查找可能的变体
            key_lower = key_name.lower()
            if key_lower != key_name:
                vk_code_alt = key_mapping.display_to_ctypes(key_lower)
                if vk_code_alt != 0:
                    self.logger.debug(f"尝试使用小写 '{key_lower}' 找到虚拟键码 0x{vk_code_alt:02X}")
                    return vk_code_alt
        
        return vk_code
    
    def get_key_flags(self, key_name, is_keydown):
        """获取按键事件标志
        对于右侧修饰键，需要使用扩展键标志和扫描码
        """
        flags = KEYEVENTF_KEYDOWN if is_keydown else KEYEVENTF_KEYUP
        
        # 检查是否为扩展键（需要 KEYEVENTF_EXTENDEDKEY 标志）
        if key_mapping.is_extended_key(key_name):
            flags |= KEYEVENTF_EXTENDEDKEY
        
        return flags
    
    def send_key_event(self, vk_code, flags, key_name=None):
        """发送按键事件
        对于右侧修饰键，使用扫描码 + 扩展键标志确保正确识别
        """
        extra = ctypes.c_ulong(0)
        ii_ = INPUT_UNION()
        
        # 对于右侧修饰键，使用扫描码方式发送以确保 Windows 正确识别左右侧
        # 这样可以避免仅使用虚拟键码时可能出现的左右侧识别问题
        if key_name and key_name in ['RShift', 'RCtrl', 'RAlt', 'RWin', 'Alt_gr', 'AltGr']:
            # 获取扫描码
            scan_code = key_mapping.display_to_scancode(key_name)
            
            if scan_code != 0:
                # 使用扫描码方式发送（虚拟键码设为0，使用扫描码）
                # 扩展键标志已经在 get_key_flags 中设置（如果需要）
                # 注意：RShift 不需要扩展标志，但 RCtrl、RAlt、RWin 需要
                ii_.ki = KEYBDINPUT(0, scan_code, flags | KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
                x = INPUT(INPUT_KEYBOARD, ii_)
                result = self.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
                if result != 1:
                    self.logger.warning(f"SendInput 失败 (右侧修饰键: {key_name}, 扫描码: 0x{scan_code:02X}, 标志: 0x{flags | KEYEVENTF_SCANCODE:04X})")
                return
        
        # 对于其他按键（包括左侧修饰键和普通按键），使用虚拟键码方式
        # 扩展键标志已经在 get_key_flags 中设置（如果需要，如方向键）
        ii_.ki = KEYBDINPUT(vk_code, 0, flags, 0, ctypes.pointer(extra))
        x = INPUT(INPUT_KEYBOARD, ii_)
        result = self.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        if result != 1 and vk_code != 0:
            self.logger.warning(f"SendInput 失败 (按键: {key_name}, 虚拟键码: 0x{vk_code:02X}, 标志: 0x{flags:04X})")
    
    def send_mouse_event(self, vk_code, is_press):
        """发送鼠标事件"""
        extra = ctypes.c_ulong(0)
        ii_ = INPUT_UNION()
        
        # 设置鼠标事件标志
        if is_press:
            if vk_code == 0x01:  # 鼠标左键
                flags = MOUSEEVENTF_LEFTDOWN
                mouse_data = 0
            elif vk_code == 0x02:  # 鼠标右键
                flags = MOUSEEVENTF_RIGHTDOWN
                mouse_data = 0
            elif vk_code == 0x04:  # 鼠标中键
                flags = MOUSEEVENTF_MIDDLEDOWN
                mouse_data = 0
            elif vk_code == 0x05:  # 鼠标侧键1
                flags = MOUSEEVENTF_XDOWN
                mouse_data = XBUTTON1
            elif vk_code == 0x06:  # 鼠标侧键2
                flags = MOUSEEVENTF_XDOWN
                mouse_data = XBUTTON2
            else:
                return
        else:
            if vk_code == 0x01:  # 鼠标左键
                flags = MOUSEEVENTF_LEFTUP
                mouse_data = 0
            elif vk_code == 0x02:  # 鼠标右键
                flags = MOUSEEVENTF_RIGHTUP
                mouse_data = 0
            elif vk_code == 0x04:  # 鼠标中键
                flags = MOUSEEVENTF_MIDDLEUP
                mouse_data = 0
            elif vk_code == 0x05:  # 鼠标侧键1
                flags = MOUSEEVENTF_XUP
                mouse_data = XBUTTON1
            elif vk_code == 0x06:  # 鼠标侧键2
                flags = MOUSEEVENTF_XUP
                mouse_data = XBUTTON2
            else:
                return
        
        ii_.mi = MOUSEINPUT(0, 0, mouse_data, flags, 0, ctypes.pointer(extra))
        x = INPUT(INPUT_MOUSE, ii_)
        self.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    
    def press_key(self, key_name):
        """按下按键"""
        vk_code = self.get_virtual_key(key_name)
        if vk_code != 0:
            if key_mapping.is_mouse_key(key_name):
                self.send_mouse_event(vk_code, True)
            else:
                flags = self.get_key_flags(key_name, True)
                self.send_key_event(vk_code, flags, key_name)
    
    def release_key(self, key_name):
        """释放按键"""
        vk_code = self.get_virtual_key(key_name)
        if vk_code != 0:
            if key_mapping.is_mouse_key(key_name):
                self.send_mouse_event(vk_code, False)
            else:
                flags = self.get_key_flags(key_name, False)
                self.send_key_event(vk_code, flags, key_name)
    
    def tap_key(self, key_name, press_delay=0.02, release_delay=0.02):
        """点击按键"""
        self.press_key(key_name)
        high_precision_sleep(press_delay)
        self.release_key(key_name)
        high_precision_sleep(release_delay)
    
    def execute_macro_sequence(self, macros, stop_event=None):
        """执行宏序列，支持单个按键和组合按键"""
        try:
            for macro in macros:
                # 检查停止事件
                if stop_event and stop_event.is_set():
                    break
                
                key_string = macro['key']
                
                # 检查是否为组合按键（包含 & 符号）
                if '&' in key_string:
                    # 执行组合按键
                    self.execute_combination_key(key_string, macro, stop_event)
                else:
                    # 执行单个按键
                    self.execute_single_key(key_string, macro, stop_event)
                
                # 检查停止事件
                if stop_event and stop_event.is_set():
                    break
                
                # 间隔时间（可中断）
                high_precision_sleep(macro['interval'] / 1000.0, stop_event, 0.001)
                    
        except Exception as e:
            self.logger.error(f"执行宏序列时出错: {e}", exc_info=True)
    
    def execute_combination_key(self, key_string, macro, stop_event=None):
        """执行组合按键（支持键盘+鼠标混合）"""
        try:
            # 解析组合按键，按 & 分割
            keys = [key.strip() for key in key_string.split('&') if key.strip()]
            
            # 分类按键类型
            keyboard_keys = []
            mouse_keys = []
            
            for key in keys:
                if key_mapping.is_mouse_key(key):
                    mouse_keys.append(key)
                else:
                    keyboard_keys.append(key)
            
            # 第一步：同时按下所有按键
            
            # 按下键盘按键
            for key in keyboard_keys:
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    flags = self.get_key_flags(key, True)
                    self.send_key_event(vk_code, flags, key)
            
            # 按下鼠标按键
            for key in mouse_keys:
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    self.send_mouse_event(vk_code, True)
            
            # 保持按下状态（可中断）
            high_precision_sleep(macro['press'] / 1000.0, stop_event, 0.001)
            
            # 检查停止事件
            if stop_event and stop_event.is_set():
                # 如果停止，释放所有已按下的按键
                for key in keyboard_keys:
                    vk_code = self.get_virtual_key(key)
                    if vk_code != 0:
                        flags = self.get_key_flags(key, False)
                        self.send_key_event(vk_code, flags, key)
                for key in mouse_keys:
                    vk_code = self.get_virtual_key(key)
                    if vk_code != 0:
                        self.send_mouse_event(vk_code, False)
                return
            
            # 第二步：同时释放所有按键
            
            # 释放键盘按键
            for key in keyboard_keys:
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    flags = self.get_key_flags(key, False)
                    self.send_key_event(vk_code, flags, key)
            
            # 释放鼠标按键
            for key in mouse_keys:
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    self.send_mouse_event(vk_code, False)
            
        except Exception as e:
            self.logger.error(f"执行组合按键时出错: {e}", exc_info=True)
    
    def execute_single_key(self, key_string, macro, stop_event=None):
        """执行单个按键"""
        try:
            key = key_string.strip()
            
            # 判断是否是鼠标按键
            if key_mapping.is_mouse_key(key):
                # 鼠标按键处理
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    # 发送鼠标按下事件
                    self.send_mouse_event(vk_code, True)
                    high_precision_sleep(macro['press'] / 1000.0, stop_event, 0.001)
                    
                    # 检查停止事件
                    if stop_event and stop_event.is_set():
                        self.send_mouse_event(vk_code, False)
                        return
                    
                    # 发送鼠标释放事件
                    self.send_mouse_event(vk_code, False)
            else:
                # 键盘按键处理
                vk_code = self.get_virtual_key(key)
                if vk_code != 0:
                    flags_down = self.get_key_flags(key, True)
                    flags_up = self.get_key_flags(key, False)
                    self.send_key_event(vk_code, flags_down, key)
                    high_precision_sleep(macro['press'] / 1000.0, stop_event, 0.001)
                    
                    # 检查停止事件
                    if stop_event and stop_event.is_set():
                        self.send_key_event(vk_code, flags_up, key)
                        return
                    
                    self.send_key_event(vk_code, flags_up, key)
                    
        except Exception as e:
            self.logger.error(f"执行单个按键时出错: {e}", exc_info=True)

# 创建全局实例
input_simulator = InputSimulator()

# 确保在导入时能够正确导出
__all__ = ['input_simulator', 'InputSimulator', 'high_precision_sleep']