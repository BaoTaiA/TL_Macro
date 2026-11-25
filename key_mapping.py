# -*- coding: utf-8 -*-
"""
统一的键码映射表
"""
from logger import get_logger

class KeyMapping:
    """统一的键码映射类 - 以用户提供的显示名称为标准"""
    
    # 显示名称映射（作为统一标准）
    DISPLAY_MAPPING = {
        # 字母
        'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F', 'G': 'G', 
        'H': 'H', 'I': 'I', 'J': 'J', 'K': 'K', 'L': 'L', 'M': 'M', 'N': 'N', 
        'O': 'O', 'P': 'P', 'Q': 'Q', 'R': 'R', 'S': 'S', 'T': 'T', 'U': 'U', 
        'V': 'V', 'W': 'W', 'X': 'X', 'Y': 'Y', 'Z': 'Z',
        
        # 数字
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', 
        '6': '6', '7': '7', '8': '8', '9': '9',
        
        # 符号
        '-': '-', '=': '=', '[': '[', ']': ']', '\\': '\\', 
        ';': ';', "'": "'", ',': ',', '.': '.', '/': '/', '`': '`', '+': '+',
        
        # 功能键
        'Esc': 'Esc', 
        'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4', 'F5': 'F5', 'F6': 'F6',
        'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12',
        'Insert': 'Insert', 'Delete': 'Delete', 'Home': 'Home', 'End': 'End',
        'PgUp': 'PgUp', 'PgDn': 'PgDn',
        
        # 修饰键
        'Tab': 'Tab', 'CapsLock': 'CapsLock', 'Enter': 'Enter', 'Backspace': 'Backspace',
        'LShift': 'LShift', 'RShift': 'RShift', 'LCtrl': 'LCtrl', 'RCtrl': 'RCtrl',
        'LAlt': 'LAlt', 'RAlt': 'RAlt', 'Alt_gr': 'RAlt', 'AltGr': 'RAlt',  # AltGr 就是右Alt
        'LWin': 'LWin', 'RWin': 'RWin',
        'Menu': 'Menu', 'Space': 'Space',
        
        # 方向键
        'Up': '↑', 'Down': '↓', 'Left': '←', 'Right': '→',
        
        # 鼠标按键
        'MouseLeft': '鼠标左键',
        'MouseMiddle': '鼠标中键', 
        'MouseRight': '鼠标右键',
        'MouseX1': '鼠标侧键1',
        'MouseX2': '鼠标侧键2'
    }
    
    # pynput 键盘键名到显示名称的映射
    PYNPUT_KEYBOARD_TO_DISPLAY = {
        # 字母
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E', 'f': 'F', 'g': 'G',
        'h': 'H', 'i': 'I', 'j': 'J', 'k': 'K', 'l': 'L', 'm': 'M', 'n': 'N',
        'o': 'O', 'p': 'P', 'q': 'Q', 'r': 'R', 's': 'S', 't': 'T', 'u': 'U',
        'v': 'V', 'w': 'W', 'x': 'X', 'y': 'Y', 'z': 'Z',
        
        # 数字
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
        '6': '6', '7': '7', '8': '8', '9': '9',
        
        # 符号
        '-': '-', '=': '=', '[': '[', ']': ']', '\\': '\\',
        ';': ';', "'": "'", ',': ',', '.': '.', '/': '/', '`': '`',
        
        # 功能键
        'esc': 'Esc',
        'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4', 'f5': 'F5', 'f6': 'F6',
        'f7': 'F7', 'f8': 'F8', 'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
        'insert': 'Insert', 'delete': 'Delete', 'home': 'Home', 'end': 'End',
        'page_up': 'PgUp', 'page_down': 'PgDn',  # 修复：添加 page_up 和 page_down
        
        # 修饰键
        'tab': 'Tab', 'caps_lock': 'CapsLock', 'enter': 'Enter', 'backspace': 'Backspace',
        'shift': 'LShift', 'shift_l': 'LShift', 'shift_r': 'RShift',  # 修复：添加 shift 映射
        'ctrl': 'LCtrl', 'ctrl_l': 'LCtrl', 'ctrl_r': 'RCtrl',
        'alt': 'LAlt', 'alt_l': 'LAlt', 'alt_r': 'RAlt', 'alt_gr': 'RAlt',  # AltGr 就是右Alt
        'cmd': 'LWin', 'cmd_l': 'LWin', 'cmd_r': 'RWin',  # 修复：添加 cmd 映射
        'menu': 'Menu', 'space': 'Space',
        
        # 方向键 - 这里应该是键盘方向键
        'up': '↑', 'down': '↓', 'left': '←', 'right': '→',
    }
    
    # pynput 鼠标按键到显示名称的映射
    PYNPUT_MOUSE_TO_DISPLAY = {
        'left': '鼠标左键',
        'middle': '鼠标中键',
        'right': '鼠标右键',
        'x1': '鼠标侧键1',
        'x2': '鼠标侧键2'
    }
    
    # keyboard 库键名到显示名称的映射
    KEYBOARD_TO_DISPLAY = {
        # 字母
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E', 'f': 'F', 'g': 'G',
        'h': 'H', 'i': 'I', 'j': 'J', 'k': 'K', 'l': 'L', 'm': 'M', 'n': 'N',
        'o': 'O', 'p': 'P', 'q': 'Q', 'r': 'R', 's': 'S', 't': 'T', 'u': 'U',
        'v': 'V', 'w': 'W', 'x': 'X', 'y': 'Y', 'z': 'Z',
        
        # 数字
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
        '6': '6', '7': '7', '8': '8', '9': '9',
        
        # 符号
        '-': '-', '=': '=', '[': '[', ']': ']', '\\': '\\',
        ';': ';', "'": "'", ',': ',', '.': '.', '/': '/', '`': '`', 'plus': '+',
        
        # 功能键
        'esc': 'Esc',
        'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4', 'f5': 'F5', 'f6': 'F6',
        'f7': 'F7', 'f8': 'F8', 'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
        'insert': 'Insert', 'delete': 'Delete', 'home': 'Home', 'end': 'End',
        'page up': 'PgUp', 'page down': 'PgDn',
        
        # 修饰键 - 添加所有可能的变体
        'tab': 'Tab', 'caps lock': 'CapsLock', 'enter': 'Enter', 'backspace': 'Backspace',
        # Shift 键 - 支持多种格式
        'shift': 'LShift', 'left shift': 'LShift', 'shift left': 'LShift',
        'right shift': 'RShift', 'shift right': 'RShift',
        # Ctrl 键 - 支持多种格式
        'ctrl': 'LCtrl', 'left ctrl': 'LCtrl', 'ctrl left': 'LCtrl',
        'right ctrl': 'RCtrl', 'ctrl right': 'RCtrl',
        # Alt 键 - 支持多种格式
        'alt': 'LAlt', 'left alt': 'LAlt', 'alt left': 'LAlt',
        'right alt': 'RAlt', 'alt right': 'RAlt',
        # Windows 键 - 支持多种格式
        'windows': 'LWin', 'left windows': 'LWin', 'windows left': 'LWin',
        'right windows': 'RWin', 'windows right': 'RWin',
        'win': 'LWin', 'left win': 'LWin', 'win left': 'LWin',
        'right win': 'RWin', 'win right': 'RWin',
        # Cmd 键（Mac 风格，映射到 Win）
        'cmd': 'LWin', 'left cmd': 'LWin', 'cmd left': 'LWin',
        'right cmd': 'RWin', 'cmd right': 'RWin',
        'menu': 'Menu', 'space': 'Space',
        
        # 方向键
        'up': '↑', 'down': '↓', 'left': '←', 'right': '→',
    }
    
    # 显示名称到 keyboard 库键名的反向映射
    DISPLAY_TO_KEYBOARD = {
        # 字母
        'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f', 'G': 'g',
        'H': 'h', 'I': 'i', 'J': 'j', 'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n',
        'O': 'o', 'P': 'p', 'Q': 'q', 'R': 'r', 'S': 's', 'T': 't', 'U': 'u',
        'V': 'v', 'W': 'w', 'X': 'x', 'Y': 'y', 'Z': 'z',
        
        # 数字
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
        '6': '6', '7': '7', '8': '8', '9': '9',
        
        # 符号
        '-': '-', '=': '=', '[': '[', ']': ']', '\\': '\\',
        ';': ';', "'": "'", ',': ',', '.': '.', '/': '/', '`': '`', '+': 'plus',
        
        # 功能键
        'Esc': 'esc',
        'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
        'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12',
        'Insert': 'insert', 'Delete': 'delete', 'Home': 'home', 'End': 'end',
        'PgUp': 'page up', 'PgDn': 'page down',
        
        # 修饰键
        'Tab': 'tab', 'CapsLock': 'caps lock', 'Enter': 'enter', 'Backspace': 'backspace',
        'LShift': 'left shift', 'RShift': 'right shift', 
        'LCtrl': 'left ctrl', 'RCtrl': 'right ctrl',
        'LAlt': 'left alt', 'RAlt': 'right alt', 'Alt_gr': 'right alt', 'AltGr': 'right alt',  # AltGr 就是右Alt
        'LWin': 'left windows', 'RWin': 'right windows',
        'Menu': 'menu', 'Space': 'space',
        
        # 方向键
        '↑': 'up', '↓': 'down', '←': 'left', '→': 'right',
    }
    
    # 显示名称到 ctypes 虚拟键码的映射
    DISPLAY_TO_CTYPES = {
        # 字母
        'A': 0x41, 'B': 0x42, 'C': 0x43, 'D': 0x44, 'E': 0x45, 'F': 0x46, 'G': 0x47,
        'H': 0x48, 'I': 0x49, 'J': 0x4A, 'K': 0x4B, 'L': 0x4C, 'M': 0x4D, 'N': 0x4E,
        'O': 0x4F, 'P': 0x50, 'Q': 0x51, 'R': 0x52, 'S': 0x53, 'T': 0x54, 'U': 0x55,
        'V': 0x56, 'W': 0x57, 'X': 0x58, 'Y': 0x59, 'Z': 0x5A,
        
        # 数字
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
        '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
        
        # 符号
        '-': 0xBD, '=': 0xBB, '[': 0xDB, ']': 0xDD, '\\': 0xDC,
        ';': 0xBA, "'": 0xDE, ',': 0xBC, '.': 0xBE, '/': 0xBF, '`': 0xC0, '+': 0xBB,
        
        # 功能键
        'Esc': 0x1B,
        'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74, 'F6': 0x75,
        'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
        'Insert': 0x2D, 'Delete': 0x2E, 'Home': 0x24, 'End': 0x23,
        'PgUp': 0x21, 'PgDn': 0x22,
        
        # 修饰键
        'Tab': 0x09, 'CapsLock': 0x14, 'Enter': 0x0D, 'Backspace': 0x08,
        'LShift': 0xA0, 'RShift': 0xA1, 'LCtrl': 0xA2, 'RCtrl': 0xA3,
        'LAlt': 0xA4, 'RAlt': 0xA5, 'Alt_gr': 0xA5, 'AltGr': 0xA5,  # AltGr 就是右Alt，使用相同的虚拟键码
        'LWin': 0x5B, 'RWin': 0x5C,
        'Menu': 0x5D, 'Space': 0x20,
        
        # 方向键
        '↑': 0x26, '↓': 0x28, '←': 0x25, '→': 0x27,
        
        # 鼠标按键
        '鼠标左键': 0x01,      # VK_LBUTTON
        '鼠标中键': 0x04,    # VK_MBUTTON
        '鼠标右键': 0x02,     # VK_RBUTTON
        '鼠标侧键1': 0x05,        # VK_XBUTTON1
        '鼠标侧键2': 0x06         # VK_XBUTTON2
    }
    
    # 显示名称到扫描码的映射（用于右侧修饰键）
    # 扫描码参考：https://www.win.tue.nl/~aeb/linux/kbd/scancodes-1.html
    DISPLAY_TO_SCANCODE = {
        # 左侧修饰键（通常不需要扫描码，但为了完整性也添加）
        'LShift': 0x2A,   # Left Shift
        'LCtrl': 0x1D,    # Left Control
        'LAlt': 0x38,     # Left Alt
        'LWin': 0x5B,     # Left Windows (E0 5B)
        
        # 右侧修饰键（关键：需要扩展扫描码）
        'RShift': 0x36,   # Right Shift
        'RCtrl': 0x1D,    # Right Control (E0 1D) - 需要扩展标志
        'RAlt': 0x38,     # Right Alt (E0 38) - 需要扩展标志
        'RWin': 0x5C,     # Right Windows (E0 5C) - 需要扩展标志
        'Alt_gr': 0x38,   # AltGr = Right Alt
        'AltGr': 0x38,    # AltGr = Right Alt
    }
    
    # 需要扩展键标志（KEYEVENTF_EXTENDEDKEY）的按键列表
    EXTENDED_KEYS = {
        'RCtrl': True,
        'RAlt': True,
        'Alt_gr': True,
        'AltGr': True,
        'RWin': True,
        'Insert': True,
        'Delete': True,
        'Home': True,
        'End': True,
        'PgUp': True,
        'PgDn': True,
        '←': True,  # Left Arrow
        '→': True,  # Right Arrow
        '↑': True,  # Up Arrow
        '↓': True,  # Down Arrow
        '\\': True, # Backslash (数字键盘上的)
        'Enter': True,  # 数字键盘上的 Enter
    }
    
    @classmethod
    def pynput_keyboard_to_display(cls, pynput_key):
        """从 pynput 键盘键名转换为显示名称"""
        # 首先尝试直接映射
        if pynput_key in cls.PYNPUT_KEYBOARD_TO_DISPLAY:
            return cls.PYNPUT_KEYBOARD_TO_DISPLAY[pynput_key]
        
        # 如果找不到，尝试处理一些特殊情况
        if pynput_key.startswith('Key.'):
            key_name = pynput_key.replace('Key.', '')
            if key_name in cls.PYNPUT_KEYBOARD_TO_DISPLAY:
                return cls.PYNPUT_KEYBOARD_TO_DISPLAY[key_name]
        
        # 如果还是找不到，返回原始键名（大写）
        return pynput_key.capitalize() if isinstance(pynput_key, str) else str(pynput_key)
    
    @classmethod
    def pynput_mouse_to_display(cls, pynput_button):
        """从 pynput 鼠标按键转换为显示名称"""
        return cls.PYNPUT_MOUSE_TO_DISPLAY.get(pynput_button, pynput_button)
    
    @classmethod
    def display_to_keyboard(cls, display_key):
        """从显示名称转换为 keyboard 库键名"""
        result = cls.DISPLAY_TO_KEYBOARD.get(display_key)
        if result is None:
            # 如果找不到映射，尝试小写转换
            result = display_key.lower()
            logger = get_logger()
            logger.warning(f"未找到键 '{display_key}' 的 keyboard 库映射，使用默认值: '{result}'")
        return result
    
    @classmethod
    def display_to_ctypes(cls, display_key):
        """从显示名称转换为 ctypes 虚拟键码"""
        return cls.DISPLAY_TO_CTYPES.get(display_key, 0)
    
    @classmethod
    def display_to_scancode(cls, display_key):
        """从显示名称转换为扫描码"""
        return cls.DISPLAY_TO_SCANCODE.get(display_key, 0)
    
    @classmethod
    def is_extended_key(cls, display_key):
        """判断按键是否需要扩展键标志"""
        return cls.EXTENDED_KEYS.get(display_key, False)
    
    MODIFIER_KEYS = frozenset({
        'LShift', 'RShift', 'LCtrl', 'RCtrl',
        'LAlt', 'RAlt', 'LWin', 'RWin',
    })

    MODIFIER_ORDER = (
        'LCtrl', 'RCtrl', 'LShift', 'RShift',
        'LAlt', 'RAlt', 'LWin', 'RWin',
    )

    @classmethod
    def is_modifier_key(cls, display_key):
        """判断是否为修饰键"""
        return display_key in cls.MODIFIER_KEYS

    @classmethod
    def build_combination_key(cls, modifiers, main_key):
        """按固定顺序构建组合键字符串"""
        ordered = [m for m in cls.MODIFIER_ORDER if m in modifiers]
        if not ordered:
            return main_key
        return '&'.join(ordered + [main_key])

    @classmethod
    def is_mouse_key(cls, display_key):
        """判断是否为鼠标按键"""
        return display_key in ['鼠标左键', '鼠标中键', '鼠标右键', '鼠标侧键1', '鼠标侧键2']
    
    @classmethod
    def is_keyboard_key(cls, display_key):
        """判断是否为键盘按键"""
        return not cls.is_mouse_key(display_key)
    
    @classmethod
    def get_standard_key(cls, key_name, source_type='display'):
        """获取标准键名（用于兼容性）"""
        if source_type == 'display':
            return key_name  # 显示名称本身就是标准
        
        # 这里可以添加其他来源的转换逻辑
        return key_name


# 创建全局实例
key_mapping = KeyMapping()