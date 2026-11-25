# -*- coding: utf-8 -*-
"""图像识别模块 - 技能图标模板匹配"""
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from logger import get_logger
from screen_capture import (
    grab_region, clamp_region, get_primary_screen_size, CaptureUnavailableError,
)


def clamp_search_rect(x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
    """将搜索矩形裁剪到主屏范围内"""
    sw, sh = get_primary_screen_size()
    return clamp_region(x, y, w, h, sw, sh)


DEFAULT_RECOGNITION = {
    "confidence": 0.85,
    "position_tolerance": 30,
    "search_margin": 80,
    "brightness_threshold": 80,
}

DEFAULT_BUFF_RECOGNITION = {
    "confidence": 0.85,
}

DEFAULT_SCAN_INTERVAL_MS = 50
DEFAULT_RECOVERY_MS = 100
DEFAULT_EXECUTE_INTERVAL_MS = 100
DEFAULT_ENSURE_PRESS_TIMEOUT_MS = 500
DEFAULT_ENSURE_PRESS_RETRIES = 3
MIN_PRIORITY = 1
MAX_PRIORITY = 10
ABSENT_MIN_FIRE_INTERVAL_MS = 500
MAX_CAPTURE_GROUP_AREA = 480_000
MAX_SKILL_ICONS = 3

SKILL_KIND_ATTACK = "attack"
SKILL_KIND_BUFF = "buff"


@dataclass
class DetectResult:
    is_ready: bool = False
    confidence: float = 0.0
    brightness: float = 0.0
    matched_x: int = 0
    matched_y: int = 0
    x_diff: int = 0
    y_diff: int = 0


TRIGGER_MODE_PRESENT = "present"
TRIGGER_MODE_ABSENT = "absent"


@dataclass
class SkillRuntimeState:
    last_ready: bool = False
    buff_last_ready: bool = False
    buff_ready_since: Optional[float] = None
    buff_gone_since: Optional[float] = None
    last_fire_time: Optional[float] = None
    awaiting_not_ready: bool = False
    ensure_deadline: Optional[float] = None
    ensure_retries_left: int = 0
    cooldown_until: Optional[float] = None


@dataclass
class CaptureGroup:
    union_x: int
    union_y: int
    union_w: int
    union_h: int
    skill_indices: list


class IconMatcher:
    """单个图标模板匹配器"""

    def __init__(self, template_bgr: np.ndarray, anchor_x: int, anchor_y: int, params: dict):
        self.template = template_bgr
        self.template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y
        self.params = {**DEFAULT_RECOGNITION, **(params or {})}
        self.template_h, self.template_w = template_bgr.shape[:2]
        self.logger = get_logger()

    @classmethod
    def from_icon_config(cls, icon_config: dict, params: dict, config_dir: str = "config"):
        path = icon_config.get("path", "")
        if not path:
            return None
        full_path = path if os.path.isabs(path) else os.path.join(config_dir, path)
        if not os.path.exists(full_path):
            return None
        template = load_template_image(full_path)
        if template is None:
            return None
        return cls(
            template,
            icon_config.get("x", 0),
            icon_config.get("y", 0),
            params,
        )

    def get_search_rect(self) -> Tuple[int, int, int, int]:
        """返回搜索区域 (x, y, w, h)"""
        margin = self.params.get("search_margin", 80)
        search_x = max(0, self.anchor_x - margin)
        search_y = max(0, self.anchor_y - margin)
        search_w = self.template_w + margin * 2
        search_h = self.template_h + margin * 2
        return clamp_search_rect(search_x, search_y, search_w, search_h)

    def detect_in_frame(
        self,
        frame_bgr: np.ndarray,
        origin_x: int,
        origin_y: int,
        frame_gray: Optional[np.ndarray] = None,
    ) -> DetectResult:
        """在已截取的合并帧内做匹配（不截屏）

        Args:
            frame_gray: 可选，与 frame_bgr 同尺寸的灰度图；多技能扫描时传入以避免重复 cvtColor
        """
        result = DetectResult()
        if self.template is None or frame_bgr is None or frame_bgr.size == 0:
            return result

        try:
            search_x, search_y, search_w, search_h = self.get_search_rect()
            lx = search_x - origin_x
            ly = search_y - origin_y
            fh, fw = frame_bgr.shape[:2]
            if lx < 0 or ly < 0 or lx + search_w > fw or ly + search_h > fh:
                return result

            if frame_gray is not None:
                screen_gray = frame_gray[ly:ly + search_h, lx:lx + search_w]
            else:
                screen_gray = cv2.cvtColor(
                    frame_bgr[ly:ly + search_h, lx:lx + search_w], cv2.COLOR_BGR2GRAY
                )
            match_result = cv2.matchTemplate(screen_gray, self.template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

            matched_abs_x = search_x + max_loc[0]
            matched_abs_y = search_y + max_loc[1]
            threshold = self.params.get("confidence", 0.85)
            tolerance = self.params.get("position_tolerance", 30)

            x_diff = abs(matched_abs_x - self.anchor_x)
            y_diff = abs(matched_abs_y - self.anchor_y)
            position_ok = x_diff <= tolerance and y_diff <= tolerance

            is_matched = max_val >= threshold and position_ok
            avg_brightness = 0.0
            if is_matched:
                icon_roi = screen_gray[max_loc[1]:max_loc[1] + self.template_h,
                                       max_loc[0]:max_loc[0] + self.template_w]
                avg_brightness = float(icon_roi.mean())

            brightness_threshold = self.params.get("brightness_threshold", 80)
            is_ready = is_matched and avg_brightness >= brightness_threshold

            result.is_ready = is_ready
            result.confidence = float(max_val)
            result.brightness = avg_brightness
            result.matched_x = matched_abs_x
            result.matched_y = matched_abs_y
            result.x_diff = x_diff
            result.y_diff = y_diff
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    f"图标匹配: conf={max_val:.3f}, threshold={threshold}, "
                    f"pos_ok={position_ok}, brightness={avg_brightness:.1f}, ready={is_ready}"
                )
        except Exception as e:
            self.logger.error(f"图像识别异常: {e}", exc_info=True)

        return result

    def detect(self) -> DetectResult:
        """单次独立截屏并匹配（供对话框测试识别等场景）"""
        result = DetectResult()
        if self.template is None:
            return result
        try:
            search_x, search_y, search_w, search_h = self.get_search_rect()
            frame_bgr = grab_region(search_x, search_y, search_w, search_h)
            return self.detect_in_frame(frame_bgr, search_x, search_y)
        except CaptureUnavailableError as e:
            self.logger.warning(f"图像识别截屏暂不可用: {e}")
            raise
        except Exception as e:
            self.logger.error(f"图像识别异常: {e}", exc_info=True)
            return result


def resolve_buff_region(precondition: dict) -> Optional[Tuple[int, int, int, int]]:
    """解析 Buff 搜索区域；旧配置无 buff_region 时从锚点+扩展推算"""
    region = precondition.get("buff_region") or {}
    rw = region.get("width", 0)
    rh = region.get("height", 0)
    if rw > 0 and rh > 0:
        return clamp_search_rect(region.get("x", 0), region.get("y", 0), rw, rh)

    buff_icon = precondition.get("buff_icon", {})
    if not buff_icon.get("path"):
        return None
    rec = precondition.get("recognition", {})
    margin = rec.get("search_margin", 80)
    tw = buff_icon.get("width") or 32
    th = buff_icon.get("height") or 32
    ax = buff_icon.get("x", 0)
    ay = buff_icon.get("y", 0)
    return clamp_search_rect(
        max(0, ax - margin), max(0, ay - margin), tw + margin * 2, th + margin * 2
    )


def resolve_scan_interval_ms(_image_macro: dict = None) -> int:
    """图像宏扫描间隔（全局参数）"""
    from global_settings import get_scan_interval_ms
    return get_scan_interval_ms()


def resolve_trigger_mode(precondition: dict) -> str:
    """解析 Buff 触发模式，缺省为 present"""
    mode = precondition.get("trigger_mode", TRIGGER_MODE_PRESENT)
    return mode if mode in (TRIGGER_MODE_PRESENT, TRIGGER_MODE_ABSENT) else TRIGGER_MODE_PRESENT


def evaluate_buff_precondition(
    buff_detected: bool,
    trigger_mode: str,
    state: SkillRuntimeState,
    now: float,
    wait_ms: int,
) -> bool:
    """评估 Buff 门控是否满足（present=上升沿+等待，absent=持续 absent+等待）"""
    wait_s = wait_ms / 1000.0
    if trigger_mode == TRIGGER_MODE_ABSENT:
        if buff_detected:
            state.buff_gone_since = None
            state.buff_last_ready = True
            return False
        if state.buff_gone_since is None:
            state.buff_gone_since = now
        state.buff_last_ready = False
        return (now - state.buff_gone_since) >= wait_s

    if buff_detected and not state.buff_last_ready:
        state.buff_ready_since = now
    if not buff_detected:
        state.buff_ready_since = None
    state.buff_last_ready = buff_detected
    if not buff_detected or state.buff_ready_since is None:
        return False
    return (now - state.buff_ready_since) >= wait_s


def resolve_execute_interval_ms(skill: dict) -> int:
    """同技能两次执行的最小间隔（ms）"""
    raw = skill.get("execute_interval_ms", DEFAULT_EXECUTE_INTERVAL_MS)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_EXECUTE_INTERVAL_MS


def resolve_recovery_ms(skill: dict) -> int:
    raw = skill.get("recovery_ms", DEFAULT_RECOVERY_MS)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_RECOVERY_MS


def resolve_skill_cooldown_ms(skill: dict, trigger_mode: Optional[str] = None) -> int:
    """该技能发键后的自身冷却（不 sleep 堵轮）：max(后摇, 执行间隔)；absent 下限保底"""
    cooldown = max(resolve_recovery_ms(skill), resolve_execute_interval_ms(skill))
    if trigger_mode == TRIGGER_MODE_ABSENT and cooldown < ABSENT_MIN_FIRE_INTERVAL_MS:
        cooldown = ABSENT_MIN_FIRE_INTERVAL_MS
    return cooldown


def resolve_skill_kind(skill: dict) -> str:
    kind = (skill or {}).get("skill_kind") or SKILL_KIND_ATTACK
    if kind == SKILL_KIND_BUFF:
        return SKILL_KIND_BUFF
    return SKILL_KIND_ATTACK


def resolve_ensure_press(skill: dict) -> bool:
    return bool((skill or {}).get("ensure_press"))


def resolve_ensure_press_timeout_ms(skill: dict) -> int:
    raw = (skill or {}).get("ensure_press_timeout_ms", DEFAULT_ENSURE_PRESS_TIMEOUT_MS)
    try:
        return max(50, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_ENSURE_PRESS_TIMEOUT_MS


def resolve_ensure_press_retries(skill: dict) -> int:
    raw = (skill or {}).get("ensure_press_retries", DEFAULT_ENSURE_PRESS_RETRIES)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_ENSURE_PRESS_RETRIES


def normalize_skill_icons(skill: dict) -> dict:
    """归一化 icons[]，并镜像 icon=icons[0]；最多 MAX_SKILL_ICONS 个有效图标"""
    skill = dict(skill)
    icons = []
    raw_icons = skill.get("icons")
    if isinstance(raw_icons, list):
        for item in raw_icons:
            if isinstance(item, dict) and item.get("path"):
                icons.append(dict(item))
                if len(icons) >= MAX_SKILL_ICONS:
                    break
    if not icons:
        icon = skill.get("icon") or {}
        if isinstance(icon, dict) and icon.get("path"):
            icons = [dict(icon)]
    skill["icons"] = icons
    skill["icon"] = dict(icons[0]) if icons else dict(skill.get("icon") or {})
    return skill


def normalize_image_skill(skill: dict) -> dict:
    """加载/运行前归一化技能字段"""
    skill = normalize_skill_precondition(skill)
    skill = normalize_skill_icons(skill)
    skill["skill_kind"] = resolve_skill_kind(skill)
    skill.setdefault("ensure_press", False)
    skill.setdefault("ensure_press_timeout_ms", DEFAULT_ENSURE_PRESS_TIMEOUT_MS)
    skill.setdefault("ensure_press_retries", DEFAULT_ENSURE_PRESS_RETRIES)
    return skill


def skill_has_usable_icon(skill: dict) -> bool:
    icons = skill.get("icons") or []
    if icons:
        return any(isinstance(i, dict) and i.get("path") for i in icons)
    return bool((skill.get("icon") or {}).get("path"))


def build_icon_matchers(skill: dict, config_dir: str = "config") -> List:
    """为技能构建最多 3 个 IconMatcher"""
    skill = normalize_skill_icons(skill)
    params = skill.get("recognition", {})
    matchers = []
    for icon in skill.get("icons") or []:
        m = IconMatcher.from_icon_config(icon, params, config_dir)
        if m is not None:
            matchers.append(m)
    return matchers


def detect_skill_ready(
    matchers: List,
    frame_bgr: np.ndarray,
    origin_x: int,
    origin_y: int,
    frame_gray: Optional[np.ndarray] = None,
) -> DetectResult:
    """任一形态匹配且就绪即视为技能就绪；返回最佳结果（优先 is_ready）"""
    best = DetectResult()
    for m in matchers or []:
        if m is None:
            continue
        result = m.detect_in_frame(frame_bgr, origin_x, origin_y, frame_gray=frame_gray)
        if result.is_ready:
            return result
        if result.confidence > best.confidence:
            best = result
    return best


def should_fire_skill(
    trigger_mode: Optional[str],
    pre_ok: bool,
    is_ready: bool,
    last_ready: bool = False,
) -> bool:
    """电平触发：门控通过且图标就绪即可（last_ready 保留兼容，不再参与判断）"""
    _ = last_ready
    if trigger_mode == TRIGGER_MODE_ABSENT:
        return bool(pre_ok and is_ready)
    return bool(pre_ok and is_ready)


def can_fire_by_interval(
    state: SkillRuntimeState,
    now: float,
    interval_ms: int,
) -> bool:
    """同技能最小执行间隔节流；cooldown_until 为硬冷却下限"""
    if state.cooldown_until is not None and now < state.cooldown_until:
        return False
    if state.last_fire_time is None:
        return True
    return (now - state.last_fire_time) * 1000.0 >= interval_ms


def can_fire_absent(
    state: SkillRuntimeState,
    now: float,
    interval_ms: int = ABSENT_MIN_FIRE_INTERVAL_MS,
) -> bool:
    """absent 模式最小触发间隔节流（兼容旧接口）"""
    return can_fire_by_interval(state, now, interval_ms)


def update_rearm_latch(state: SkillRuntimeState, is_ready: bool) -> None:
    """兼容保留：旧上升沿重臂已由电平+执行间隔替代"""
    if state.awaiting_not_ready and not is_ready:
        state.awaiting_not_ready = False
        state.ensure_deadline = None


def update_ensure_press_state(
    state: SkillRuntimeState,
    is_ready: bool,
    now: float,
) -> str:
    """处理确保按下等待。

    Returns:
        "idle" | "waiting" | "confirmed" | "timeout_retry" | "timeout_give_up"
    """
    if not state.awaiting_not_ready:
        return "idle"
    if not is_ready:
        state.awaiting_not_ready = False
        state.ensure_deadline = None
        state.ensure_retries_left = 0
        return "confirmed"
    deadline = state.ensure_deadline
    if deadline is not None and now >= deadline:
        if state.ensure_retries_left > 0:
            state.ensure_retries_left -= 1
            return "timeout_retry"
        state.awaiting_not_ready = False
        state.ensure_deadline = None
        return "timeout_give_up"
    return "waiting"


def should_enqueue_skill(
    trigger_mode: Optional[str],
    pre_ok: bool,
    is_ready: bool,
    last_ready: bool,
    state: SkillRuntimeState,
    now: float,
    interval_ms: int = DEFAULT_EXECUTE_INTERVAL_MS,
) -> bool:
    """判断本技能是否应立即执行（电平就绪 + 自身冷却；确保按下等待中不发）"""
    if state.awaiting_not_ready:
        return False
    if not should_fire_skill(trigger_mode, pre_ok, is_ready, last_ready):
        return False
    effective_ms = interval_ms
    if trigger_mode == TRIGGER_MODE_ABSENT and interval_ms < ABSENT_MIN_FIRE_INTERVAL_MS:
        effective_ms = ABSENT_MIN_FIRE_INTERVAL_MS
    return can_fire_by_interval(state, now, effective_ms)


def mark_skill_fired(
    state: SkillRuntimeState,
    now: float,
    trigger_mode: Optional[str] = None,
    *,
    cooldown_ms: int = 0,
    ensure_press: bool = False,
    ensure_timeout_ms: int = DEFAULT_ENSURE_PRESS_TIMEOUT_MS,
    ensure_retries: int = DEFAULT_ENSURE_PRESS_RETRIES,
) -> None:
    """按键完成后更新运行时：冷却时间戳；可选进入确保按下等待"""
    _ = trigger_mode
    state.last_fire_time = now
    state.cooldown_until = now + max(0, int(cooldown_ms)) / 1000.0
    if ensure_press:
        state.awaiting_not_ready = True
        state.ensure_deadline = now + max(50, int(ensure_timeout_ms)) / 1000.0
        state.ensure_retries_left = max(0, int(ensure_retries))
    else:
        state.awaiting_not_ready = False
        state.ensure_deadline = None
        state.ensure_retries_left = 0


def begin_ensure_retry(
    state: SkillRuntimeState,
    now: float,
    *,
    cooldown_ms: int = 0,
    ensure_timeout_ms: int = DEFAULT_ENSURE_PRESS_TIMEOUT_MS,
) -> None:
    """确保按下超时后重试发键：刷新冷却与等待截止时间"""
    state.last_fire_time = now
    state.cooldown_until = now + max(0, int(cooldown_ms)) / 1000.0
    state.awaiting_not_ready = True
    state.ensure_deadline = now + max(50, int(ensure_timeout_ms)) / 1000.0


def clamp_skill_priority(raw) -> Optional[int]:
    """将 priority 解析为 1–10；None/空表示未设置"""
    if raw is None or raw == "":
        return None
    try:
        return max(MIN_PRIORITY, min(MAX_PRIORITY, int(raw)))
    except (TypeError, ValueError):
        return None


def sort_candidates_by_priority(candidates: List[int], skills: List[dict]) -> List[int]:
    """同轮候选入队顺序：有 priority 的按数值降序；无 priority 的保持列表索引顺序并整体靠后"""

    def sort_key(idx: int):
        p = clamp_skill_priority(skills[idx].get("priority"))
        if p is None:
            return (1, idx)
        return (0, -p, idx)

    return sorted(candidates, key=sort_key)


def find_skill_by_priority(
    skills: List[dict],
    priority: int,
    exclude_skill_id: Optional[str] = None,
    skill_kind: Optional[str] = None,
) -> Optional[dict]:
    """返回已占用该 priority 的其他技能；exclude_skill_id 用于编辑自身"""
    for skill in skills:
        if exclude_skill_id and skill.get("id") == exclude_skill_id:
            continue
        if skill_kind is not None and resolve_skill_kind(skill) != skill_kind:
            continue
        if clamp_skill_priority(skill.get("priority")) == priority:
            return skill
    return None


def find_duplicate_priorities(
    skills: List[dict],
    skill_kind: Optional[str] = None,
) -> List[tuple]:
    """返回 [(priority, [skill_name, ...]), ...] 仅含重复项；可按 kind 过滤"""
    by_priority: dict = {}
    for skill in skills:
        if skill_kind is not None and resolve_skill_kind(skill) != skill_kind:
            continue
        p = clamp_skill_priority(skill.get("priority"))
        if p is None:
            continue
        by_priority.setdefault(p, []).append(skill.get("name") or "")
    return [(p, names) for p, names in sorted(by_priority.items()) if len(names) > 1]


def normalize_skill_precondition(skill: dict) -> dict:
    """合并旧 postcondition 到 precondition，移除 postcondition 键"""
    skill = dict(skill)
    pre = dict(skill.get("precondition") or {})
    post = skill.get("postcondition") or {}

    pre_on = bool(pre.get("enabled"))
    post_on = bool(post.get("enabled"))

    if post_on and not pre_on:
        for key in ("name", "buff_region", "buff_icon", "recognition"):
            post_val = post.get(key)
            if post_val:
                pre[key] = post_val
        pre["enabled"] = True
        pre["trigger_mode"] = TRIGGER_MODE_ABSENT
    elif pre_on:
        pre["trigger_mode"] = resolve_trigger_mode(pre)
        if pre.get("trigger_mode") == TRIGGER_MODE_ABSENT and not post_on:
            pass
    else:
        pre.setdefault("trigger_mode", TRIGGER_MODE_PRESENT)

    pre.setdefault("enabled", False)
    pre.setdefault("trigger_mode", TRIGGER_MODE_PRESENT)
    pre.setdefault("name", "")
    pre.setdefault("wait_after_buff_ms", 300)
    pre.setdefault("buff_region", {"x": 0, "y": 0, "width": 0, "height": 0})
    pre.setdefault("buff_icon", {"path": "", "width": 0, "height": 0})
    pre.setdefault("recognition", DEFAULT_BUFF_RECOGNITION.copy())

    skill["precondition"] = pre
    skill.pop("postcondition", None)
    return skill


def migrate_post_buff_icon_path(skill: dict, config_dir: str, config_name: str) -> dict:
    """将 post_buffs 路径迁移到 buffs 并删除旧文件"""
    from asset_manager import get_buff_icon_rel_path

    skill = normalize_skill_precondition(skill)
    pre = skill["precondition"]
    buff_icon = pre.get("buff_icon", {})
    path = buff_icon.get("path", "")
    if "/post_buffs/" not in path.replace("\\", "/"):
        return skill

    skill_id = skill.get("id", "")
    if not skill_id:
        return skill

    old_abs = path if os.path.isabs(path) else os.path.join(config_dir, path)
    new_rel = get_buff_icon_rel_path(config_name, skill_id)
    new_abs = os.path.join(config_dir, new_rel)

    if os.path.exists(old_abs):
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        if os.path.abspath(old_abs) != os.path.abspath(new_abs):
            if os.path.exists(new_abs):
                os.remove(new_abs)
            os.rename(old_abs, new_abs)
        buff_icon["path"] = new_rel
    elif not buff_icon.get("path"):
        buff_icon["path"] = new_rel

    pre["buff_icon"] = buff_icon
    return skill


class RegionIconMatcher:
    """在固定矩形区域内匹配模板（无锚点位置约束、无亮度阈值）"""

    def __init__(
        self,
        template_bgr: np.ndarray,
        region_x: int,
        region_y: int,
        region_w: int,
        region_h: int,
        params: dict,
    ):
        self.template = template_bgr
        self.template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        self.region_x = region_x
        self.region_y = region_y
        self.region_w = region_w
        self.region_h = region_h
        self.params = {**DEFAULT_BUFF_RECOGNITION, **(params or {})}
        self.template_h, self.template_w = template_bgr.shape[:2]
        self.logger = get_logger()

    @classmethod
    def from_buff_condition(cls, condition: dict, config_dir: str = "config"):
        if not condition.get("enabled"):
            return None
        region = resolve_buff_region(condition)
        if region is None:
            return None
        buff_icon = condition.get("buff_icon", {})
        path = buff_icon.get("path", "")
        if not path:
            return None
        full_path = path if os.path.isabs(path) else os.path.join(config_dir, path)
        if not os.path.exists(full_path):
            return None
        template = load_template_image(full_path)
        if template is None:
            return None
        rx, ry, rw, rh = region
        return cls(template, rx, ry, rw, rh, condition.get("recognition", {}))

    @classmethod
    def from_precondition(cls, precondition: dict, config_dir: str = "config"):
        return cls.from_buff_condition(precondition, config_dir)

    def get_search_rect(self) -> Tuple[int, int, int, int]:
        return clamp_search_rect(
            self.region_x, self.region_y, self.region_w, self.region_h
        )

    def detect_in_frame(
        self,
        frame_bgr: np.ndarray,
        origin_x: int,
        origin_y: int,
        frame_gray: Optional[np.ndarray] = None,
    ) -> DetectResult:
        result = DetectResult()
        if self.template is None or frame_bgr is None or frame_bgr.size == 0:
            return result
        _, _, search_w, search_h = self.get_search_rect()
        if search_w < self.template_w or search_h < self.template_h:
            return result

        try:
            search_x, search_y, search_w, search_h = self.get_search_rect()
            lx = search_x - origin_x
            ly = search_y - origin_y
            fh, fw = frame_bgr.shape[:2]
            if lx < 0 or ly < 0 or lx + search_w > fw or ly + search_h > fh:
                return result

            if frame_gray is not None:
                screen_gray = frame_gray[ly:ly + search_h, lx:lx + search_w]
            else:
                screen_gray = cv2.cvtColor(
                    frame_bgr[ly:ly + search_h, lx:lx + search_w], cv2.COLOR_BGR2GRAY
                )
            match_result = cv2.matchTemplate(screen_gray, self.template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

            threshold = self.params.get("confidence", 0.85)
            is_ready = max_val >= threshold

            result.is_ready = is_ready
            result.confidence = float(max_val)
            result.matched_x = search_x + max_loc[0]
            result.matched_y = search_y + max_loc[1]
        except Exception as e:
            self.logger.error(f"Buff 区域识别异常: {e}", exc_info=True)

        return result

    def detect(self) -> DetectResult:
        result = DetectResult()
        if self.template is None:
            return result
        try:
            search_x, search_y, search_w, search_h = self.get_search_rect()
            frame_bgr = grab_region(search_x, search_y, search_w, search_h)
            return self.detect_in_frame(frame_bgr, search_x, search_y)
        except Exception as e:
            self.logger.error(f"Buff 区域识别异常: {e}", exc_info=True)
            return result


def union_search_rects(rects) -> Optional[Tuple[int, int, int, int]]:
    """合并多个搜索区域为并集外接矩形"""
    if not rects:
        return None
    x = min(r[0] for r in rects)
    y = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return x, y, right - x, bottom - y


def rect_area(rect: Tuple[int, int, int, int]) -> int:
    return rect[2] * rect[3]


def cluster_skill_rects(
    skill_entries: list,
    max_area: int = MAX_CAPTURE_GROUP_AREA,
) -> list:
    """按 union 面积贪心分组，每组面积不超过 max_area"""
    if not skill_entries:
        return []

    all_rects = []
    for _, rects in skill_entries:
        all_rects.extend(rects)

    global_union = union_search_rects(all_rects)
    if global_union is None:
        return []

    if rect_area(global_union) <= max_area:
        return [CaptureGroup(
            global_union[0], global_union[1], global_union[2], global_union[3],
            [idx for idx, _ in skill_entries],
        )]

    @dataclass
    class _Group:
        union: Tuple[int, int, int, int]
        skill_indices: list

    groups: list = []
    for skill_idx, rects in skill_entries:
        skill_union = union_search_rects(rects)
        if skill_union is None:
            continue
        placed = False
        for g in groups:
            new_union = union_search_rects([g.union, skill_union])
            if new_union and rect_area(new_union) <= max_area:
                g.union = new_union
                g.skill_indices.append(skill_idx)
                placed = True
                break
        if not placed:
            groups.append(_Group(skill_union, [skill_idx]))

    return [
        CaptureGroup(g.union[0], g.union[1], g.union[2], g.union[3], g.skill_indices)
        for g in groups
    ]


def load_template_image(path: str) -> Optional[np.ndarray]:
    """加载 BGR 模板图片（支持 Windows 中文路径）"""
    logger = get_logger()
    try:
        if not os.path.exists(path):
            logger.warning(f"加载模板失败: 文件不存在 path={path}")
            return None
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            logger.warning(f"加载模板失败: 文件为空 path={path}")
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning(f"加载模板失败: imdecode 失败 path={path}")
        return img
    except Exception as e:
        logger.warning(f"加载模板失败: {path}, {e}")
        return None


def save_template_image(img_bgr: np.ndarray, save_path: str) -> bool:
    """保存 BGR 模板图片（支持 Windows 中文路径）"""
    logger = get_logger()
    try:
        if img_bgr is None or img_bgr.size == 0:
            logger.warning(f"保存模板失败: 图像为空 path={save_path}")
            return False
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        ext = os.path.splitext(save_path)[1] or ".png"
        ok, buf = cv2.imencode(ext, img_bgr)
        if not ok:
            logger.warning(f"保存模板失败: imencode 失败 path={save_path}")
            return False
        buf.tofile(save_path)
        return True
    except Exception as e:
        logger.warning(f"保存模板失败: {save_path}, {e}")
        return False


def load_template_preview(path: str, config_dir: str = "config") -> Optional[np.ndarray]:
    """加载模板用于预览"""
    full_path = path if os.path.isabs(path) else os.path.join(config_dir, path)
    return load_template_image(full_path)


def bgr_to_qpixmap(img_bgr, max_size=64, max_width=None, max_height=None):
    """BGR numpy 数组转 QPixmap"""
    from PyQt5.QtGui import QPixmap, QImage
    from PyQt5.QtCore import Qt
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    qt_image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(qt_image)
    if max_width is not None and max_height is not None:
        return pixmap.scaled(
            max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
    return pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
