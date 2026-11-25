# -*- coding: utf-8 -*-
"""配置默认值工厂"""
import copy


def make_default_config(press_time=15):
    """创建一份新的默认配置字典（深拷贝，可安全修改）

    Args:
        press_time: 单键宏默认按键时长（毫秒），新建配置时使用 15
    """
    return {
        "hotkey": "",
        "macros": [],
        "mode": 2,
        "single_key_macro": {
            "hotkey": "",
            "press_time": press_time,
            "interval": 20,
            "mode": 1,
        },
        "image_macro": {
            "hotkey": "",
            "mode": 1,
            "skills": [],
        },
    }


def merge_loaded_config(loaded_config: dict) -> dict:
    """将磁盘加载的配置与默认值合并"""
    defaults = make_default_config()
    if not loaded_config:
        return defaults
    return {
        "hotkey": loaded_config.get("hotkey", defaults["hotkey"]),
        "macros": loaded_config.get("macros", defaults["macros"]),
        "mode": loaded_config.get("mode", defaults["mode"]),
        "single_key_macro": loaded_config.get("single_key_macro", copy.deepcopy(defaults["single_key_macro"])),
        "image_macro": loaded_config.get("image_macro", copy.deepcopy(defaults["image_macro"])),
    }
