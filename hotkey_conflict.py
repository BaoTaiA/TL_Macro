# -*- coding: utf-8 -*-
"""热键冲突检测（纯函数，无 Qt 依赖）"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from logger import get_logger

_logger = get_logger()


def parse_combination_key(key_string) -> List[str]:
    """解析组合按键字符串，返回小写的按键列表。"""
    if not key_string:
        return []
    return [k.strip().lower() for k in key_string.split('&') if k.strip()]


def check_key_in_combination(key, combination_keys) -> bool:
    """检查单个按键是否在组合按键列表中。"""
    return key.lower() in combination_keys


def _parse_key_set(key: str) -> frozenset:
    if not key:
        return frozenset()
    key = key.strip()
    if '&' in key:
        return frozenset(parse_combination_key(key))
    return frozenset({key.lower()})


def keys_conflict(a: str, b: str) -> bool:
    """判断两个按键是否冲突（精确匹配、单键属于组合、组合键交集）。"""
    if not a or not b:
        return False
    a = a.strip()
    b = b.strip()
    if not a or not b:
        return False

    if a.lower() == b.lower():
        return True

    a_combo = '&' in a
    b_combo = '&' in b
    if not a_combo and not b_combo:
        return False

    a_keys = _parse_key_set(a)
    b_keys = _parse_key_set(b)
    if a_combo and not b_combo:
        return b.lower() in a_keys
    if b_combo and not a_combo:
        return a.lower() in b_keys
    return bool(a_keys & b_keys)


def _startup_hotkeys(config: dict) -> List[str]:
    keys = []
    multi = (config.get("hotkey") or "").strip()
    single = (config.get("single_key_macro") or {}).get("hotkey", "").strip()
    image = (config.get("image_macro") or {}).get("hotkey", "").strip()
    for key in (multi, single, image):
        if key:
            keys.append(key)
    return keys


def _macro_keys(config: dict) -> List[str]:
    return [
        (macro.get("key") or "").strip()
        for macro in config.get("macros", [])
        if (macro.get("key") or "").strip()
    ]


def find_intra_conflict(
    hotkey: str,
    source: str,
    config: dict,
    exclude_skill_id=None,
) -> Optional[Tuple[str, str]]:
    """检查配置内热键冲突，返回 (冲突类型, 配置名) 或 None。"""
    if not config or not hotkey:
        return None

    hotkey_lower = hotkey.lower()

    if source != "multi":
        multi = config.get("hotkey", "")
        if multi and keys_conflict(hotkey, multi):
            _logger.debug(f"热键冲突(配置内): {hotkey!r} vs 多键宏启动热键 {multi!r}")
            return ("多键宏启动热键", "")

    if source != "single":
        single = (config.get("single_key_macro") or {}).get("hotkey", "")
        if single and keys_conflict(hotkey, single):
            _logger.debug(f"热键冲突(配置内): {hotkey!r} vs 单键宏热键 {single!r}")
            return ("单键宏热键", "")

    if source != "image":
        image = (config.get("image_macro") or {}).get("hotkey", "")
        if image and keys_conflict(hotkey, image):
            _logger.debug(f"热键冲突(配置内): {hotkey!r} vs 图像宏热键 {image!r}")
            return ("图像宏热键", "")

    if source != "macro":
        for macro in config.get("macros", []):
            macro_key = macro.get("key", "")
            if not macro_key:
                continue
            if macro_key.lower() == hotkey_lower:
                return ("宏序列中的按键", "")
            if keys_conflict(hotkey, macro_key):
                if '&' in hotkey and '&' not in macro_key:
                    return ("宏序列中的按键", "")
                return ("宏序列中的组合按键", "")

    for skill in (config.get("image_macro") or {}).get("skills", []):
        if exclude_skill_id and skill.get("id") == exclude_skill_id:
            continue
        skill_key = (skill.get("key") or "").strip()
        if not skill_key:
            continue
        if skill_key.lower() == hotkey_lower:
            return ("图像宏技能按键", "")
        if keys_conflict(hotkey, skill_key):
            if '&' in hotkey and '&' not in skill_key:
                return ("图像宏技能按键", "")
            return ("图像宏技能组合按键", "")

    return None


def has_cross_conflict(
    config_name: str,
    check_config: dict,
    enabled_configs: Dict[str, dict],
) -> bool:
    """检查与已启用配置之间的跨配置热键冲突。"""
    if not config_name or not check_config:
        return False

    check_hotkeys = _startup_hotkeys(check_config)
    check_macros = _macro_keys(check_config)

    for enabled_name, enabled_config in enabled_configs.items():
        if enabled_name == config_name:
            continue

        enabled_hotkeys = _startup_hotkeys(enabled_config)
        enabled_macros = _macro_keys(enabled_config)

        for check_hk in check_hotkeys:
            for enabled_hk in enabled_hotkeys:
                if keys_conflict(check_hk, enabled_hk):
                    _logger.debug(
                        f"热键冲突(跨配置): {config_name!r} {check_hk!r} "
                        f"vs {enabled_name!r} {enabled_hk!r}"
                    )
                    return True

        for macro_key in check_macros:
            for enabled_hk in enabled_hotkeys:
                if keys_conflict(macro_key, enabled_hk):
                    return True

        for enabled_macro_key in enabled_macros:
            for check_hk in check_hotkeys:
                if keys_conflict(enabled_macro_key, check_hk):
                    return True

    return False
