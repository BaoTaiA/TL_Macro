# -*- coding: utf-8 -*-
"""图像宏资源文件管理"""
import os
import shutil
import uuid

from logger import get_logger


DEFAULT_IMAGE_MACRO = {
    "hotkey": "",
    "mode": 1,
    "skills": [],
}


def get_config_assets_dir(config_dir: str, config_name: str) -> str:
    return os.path.join(config_dir, "assets", config_name)


def get_skill_icon_rel_path(config_name: str, skill_id: str, form_index: int = 0) -> str:
    """技能图标相对路径；form_index 0/1/2 对应最多 3 个形态"""
    if form_index <= 0:
        return f"assets/{config_name}/skills/{skill_id}_icon.png"
    return f"assets/{config_name}/skills/{skill_id}_icon_{form_index}.png"


def get_buff_icon_rel_path(config_name: str, skill_id: str) -> str:
    return f"assets/{config_name}/buffs/{skill_id}_buff.png"


def get_buff_region_preview_rel_path(config_name: str, skill_id: str) -> str:
    return f"assets/{config_name}/buff_regions/{skill_id}_region.png"


MAX_SKILL_ICONS = 3


def generate_skill_id() -> str:
    return uuid.uuid4().hex[:8]


def save_icon_image(config_dir: str, rel_path: str, img_bgr) -> bool:
    from image_recognizer import save_template_image
    abs_path = os.path.join(config_dir, rel_path)
    return save_template_image(img_bgr, abs_path)


def delete_skill_assets(config_dir: str, config_name: str, skill_id: str):
    logger = get_logger()
    rels = [
        get_skill_icon_rel_path(config_name, skill_id, i)
        for i in range(MAX_SKILL_ICONS)
    ]
    rels.append(get_buff_icon_rel_path(config_name, skill_id))
    rels.append(get_buff_region_preview_rel_path(config_name, skill_id))
    for rel in rels:
        abs_path = os.path.join(config_dir, rel)
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception as e:
                logger.warning(f"删除资源失败 {abs_path}: {e}")


def delete_config_assets(config_dir: str, config_name: str):
    assets_dir = get_config_assets_dir(config_dir, config_name)
    if os.path.exists(assets_dir):
        try:
            shutil.rmtree(assets_dir)
        except Exception as e:
            get_logger().warning(f"删除配置资源目录失败 {assets_dir}: {e}")


def rename_config_assets(config_dir: str, old_name: str, new_name: str):
    logger = get_logger()
    old_dir = get_config_assets_dir(config_dir, old_name)
    new_dir = get_config_assets_dir(config_dir, new_name)
    if os.path.exists(old_dir):
        try:
            if os.path.exists(new_dir):
                shutil.rmtree(new_dir)
            os.rename(old_dir, new_dir)
        except Exception as e:
            logger.warning(f"重命名配置资源目录失败: {e}")


def update_skill_paths_in_config(config: dict, old_name: str, new_name: str):
    """重命名配置后更新 JSON 中的相对路径"""
    prefix_old = f"assets/{old_name}/"
    prefix_new = f"assets/{new_name}/"
    image_macro = config.get("image_macro", {})
    for skill in image_macro.get("skills", []):
        icon = skill.get("icon", {})
        if icon.get("path", "").startswith(prefix_old):
            icon["path"] = icon["path"].replace(prefix_old, prefix_new, 1)
        for alt in skill.get("icons", []) or []:
            if isinstance(alt, dict) and alt.get("path", "").startswith(prefix_old):
                alt["path"] = alt["path"].replace(prefix_old, prefix_new, 1)
        pre = skill.get("precondition", {})
        buff = pre.get("buff_icon", {})
        if buff.get("path", "").startswith(prefix_old):
            buff["path"] = buff["path"].replace(prefix_old, prefix_new, 1)

