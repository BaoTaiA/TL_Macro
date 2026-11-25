# -*- coding: utf-8 -*-
"""配置管理模块"""
import os
import json
from logger import get_logger
from hotkey_conflict import (
    find_intra_conflict,
    has_cross_conflict,
    parse_combination_key,
)


def sanitize_for_json(data):
    """将嵌套结构中的 numpy 标量转为 Python 原生类型，避免 json.dump 失败"""
    try:
        import numpy as np
        numpy_integer = (np.integer,)
        numpy_floating = (np.floating,)
    except ImportError:
        numpy_integer = ()
        numpy_floating = ()

    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_for_json(v) for v in data]
    if numpy_integer and isinstance(data, numpy_integer):
        return int(data)
    if numpy_floating and isinstance(data, numpy_floating):
        return float(data)
    return data


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir="config"):
        self.logger = get_logger()
        self.config_dir = config_dir
        self.enabled_configs_file = os.path.join(self.config_dir, "enabled_configs.json")
        self.enabled_configs = set()  # 已启用的配置集合
        self.enabled_configs_data = {}  # {config_name: config_dict}
        
    def create_config_dir(self):
        """创建配置目录"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def load_enabled_configs(self):
        """加载已启用的配置列表"""
        try:
            if os.path.exists(self.enabled_configs_file):
                with open(self.enabled_configs_file, 'r', encoding='utf-8') as f:
                    enabled_list = json.load(f)
                    self.enabled_configs = set(enabled_list)
            else:
                self.enabled_configs = set()
        except Exception as e:
            self.logger.error(f"加载启用配置列表失败: {e}", exc_info=True)
            self.enabled_configs = set()
    
    def save_enabled_configs(self):
        """保存已启用的配置列表"""
        try:
            with open(self.enabled_configs_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.enabled_configs), f, ensure_ascii=False, indent=2)
            self.logger.info(f"启用配置列表已更新: {sorted(self.enabled_configs)}")
        except Exception as e:
            self.logger.error(f"保存启用配置列表失败: {e}", exc_info=True)
    
    def load_config_by_name(self, config_name):
        """根据配置名加载配置"""
        try:
            config_path = os.path.join(self.config_dir, f"{config_name}.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                macro_count = len(config.get("macros", []))
                skill_count = len((config.get("image_macro") or {}).get("skills", []))
                self.logger.debug(
                    f"配置已加载: {config_name}, 宏序列={macro_count}, 图像技能={skill_count}"
                )
                return config
        except Exception as e:
            self.logger.error(f"加载配置 {config_name} 失败: {e}", exc_info=True)
        return None
    
    def save_config(self, config_name, config_data):
        """保存配置到文件"""
        if not config_name:
            return False
            
        config_path = os.path.join(self.config_dir, f"{config_name}.json")
        
        try:
            safe_data = sanitize_for_json(config_data)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(safe_data, f, ensure_ascii=False, indent=2)
            macro_count = len(config_data.get("macros", []))
            skill_count = len((config_data.get("image_macro") or {}).get("skills", []))
            self.logger.debug(
                f"配置已保存: {config_name}, 宏序列={macro_count}, 图像技能={skill_count}"
            )
            return True
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}", exc_info=True)
            return False
    
    def get_all_config_names(self):
        """获取所有配置文件名（排除系统配置文件）"""
        if not os.path.exists(self.config_dir):
            return []
            
        config_names = set()
        excluded_files = ["history.json", "enabled_configs.json", "global_settings.json"]
        for file in os.listdir(self.config_dir):
            if file.endswith(".json") and file not in excluded_files:
                name = os.path.splitext(file)[0]
                config_names.add(name)
        
        return sorted(config_names)
    
    def check_hotkey_conflict(self, hotkey, source, current_config, exclude_skill_id=None):
        """检查热键冲突（在当前配置内）"""
        return find_intra_conflict(
            hotkey, source, current_config, exclude_skill_id=exclude_skill_id
        )

    def check_cross_config_conflict(self, config_name):
        """检查跨配置的按键冲突（只检查已启用的配置）"""
        if not config_name:
            return False

        try:
            check_config = self.enabled_configs_data.get(config_name)
            if not check_config:
                config_path = os.path.join(self.config_dir, f"{config_name}.json")
                if not os.path.exists(config_path):
                    return False
                with open(config_path, 'r', encoding='utf-8') as f:
                    check_config = json.load(f)

            return has_cross_conflict(
                config_name, check_config, self.enabled_configs_data
            )
        except Exception as e:
            self.logger.error(f"检查跨配置冲突失败: {e}", exc_info=True)

        return False
    
    def format_conflict_message(self):
        """格式化冲突消息（简化版本）"""
        return "配置冲突，无法启用\n\n请检查以下规则：\n1. 多键宏启动热键不能一样\n2. 单键宏启动热键不能一样\n3. 图像宏启动热键不能一样\n4. 各类型启动热键之间不能一样\n5. 宏序列不能包含其他配置的启动热键"
    
    def refresh_enabled_configs_data(self):
        """刷新已启用配置的数据到内存（配置变更时调用）"""
        self.enabled_configs_data.clear()
        
        # 加载所有已启用配置的数据
        for config_name in self.enabled_configs:
            config = self.load_config_by_name(config_name)
            if config:
                self.enabled_configs_data[config_name] = config
        
        return self.enabled_configs_data

