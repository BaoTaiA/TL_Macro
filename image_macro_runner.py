# -*- coding: utf-8 -*-
"""图像宏执行 Mixin — Buff/攻击双线程并行；后摇为每技能冷却门控（不 sleep 堵轮）"""
import logging
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from input import input_simulator, high_precision_sleep
from window_manager import window_focus_manager
from utils import get_image_macro_mode_text
from image_recognizer import (
    RegionIconMatcher, SkillRuntimeState, union_search_rects,
    resolve_scan_interval_ms, resolve_trigger_mode, evaluate_buff_precondition,
    should_enqueue_skill, mark_skill_fired, begin_ensure_retry,
    update_ensure_press_state, cluster_skill_rects, rect_area,
    sort_candidates_by_priority, resolve_skill_cooldown_ms,
    normalize_image_skill, skill_has_usable_icon, build_icon_matchers,
    detect_skill_ready, resolve_skill_kind, resolve_ensure_press,
    resolve_ensure_press_timeout_ms, resolve_ensure_press_retries,
    SKILL_KIND_BUFF, SKILL_KIND_ATTACK,
)
from screen_capture import (
    grab_region, release_thread_capture, begin_capture_frame, end_capture_frame,
    get_capture_backoff_sec, was_last_capture_round_skipped,
)
from macro_types import MacroInfo, MacroState, MacroType


class ImageMacroRunnerMixin:
    def start_image_macro(self, config_name: str, config: dict, enabled_configs_data: dict = None):
        """启动图像宏：Buff 线程与攻击线程并行"""
        with self.global_lock:
            if config_name in self.image_macros:
                macro_info = self.image_macros[config_name]
                if not macro_info.any_worker_alive():
                    self.image_macros.pop(config_name, None)
                elif macro_info.is_running():
                    self.logger.debug(f"图像宏已在运行（配置: {config_name}），忽略重复启动")
                    return

            running_count = sum(1 for info in self.image_macros.values() if info.is_running())
            if running_count >= self.MAX_CONCURRENT_IMAGE_MACROS:
                self.show_message_signal.emit("警告", "已有图像宏在运行，同时只能执行一个配置")
                return

            if not window_focus_manager.is_target_window_active():
                self.logger.debug("当前窗口不是目标窗口，不执行图像宏")
                return

            image_macro = config.get("image_macro", {})
            hotkey = image_macro.get("hotkey", "")
            skills = [normalize_image_skill(s) for s in image_macro.get("skills", [])]
            mode = image_macro.get("mode", 1)

            if not hotkey:
                self.show_message_signal.emit("警告", "图像宏热键未设置")
                return
            if not skills:
                self.show_message_signal.emit("警告", "没有可执行的技能，请先添加技能")
                return

            err = self._validate_skills_for_start(skills)
            if err:
                self.show_message_signal.emit("警告", err)
                return

            buff_skills = [s for s in skills if resolve_skill_kind(s) == SKILL_KIND_BUFF]
            attack_skills = [s for s in skills if resolve_skill_kind(s) == SKILL_KIND_ATTACK]
            if not buff_skills and not attack_skills:
                self.show_message_signal.emit("警告", "没有可执行的技能，请先添加技能")
                return

            macro_info = MacroInfo(config_name, MacroType.IMAGE)
            macro_info.set_state(MacroState.STARTING)
            macro_info.start_time = time.time()
            macro_info.stop_event.clear()
            macro_info.threads = []
            if getattr(self, "_image_fire_lock", None) is None:
                self._image_fire_lock = threading.Lock()

            workers = []
            if buff_skills:
                workers.append((SKILL_KIND_BUFF, buff_skills, f"ImageMacro-Buff-{config_name}"))
            if attack_skills:
                workers.append((SKILL_KIND_ATTACK, attack_skills, f"ImageMacro-Atk-{config_name}"))

            for kind, kind_skills, thread_name in workers:
                t = threading.Thread(
                    target=self._execute_image_macro_kind,
                    args=(macro_info, image_macro, kind_skills, kind),
                    daemon=True,
                    name=thread_name,
                )
                macro_info.threads.append(t)

            macro_info.thread = macro_info.threads[0]
            self.image_macros[config_name] = macro_info
            for t in macro_info.threads:
                t.start()

            mode_text = get_image_macro_mode_text(mode)
            self.logger.info(
                f"图像宏开始执行（配置: {config_name}，{mode_text}，"
                f"Buff={len(buff_skills)}，攻击={len(attack_skills)}）"
            )

    def _validate_skills_for_start(self, skills: List[dict]) -> Optional[str]:
        for skill in skills:
            if not skill_has_usable_icon(skill):
                return f"技能 '{skill.get('name', '')}' 缺少图标"
            matchers = build_icon_matchers(skill, self.config_dir)
            if not matchers:
                for icon in skill.get("icons") or [skill.get("icon", {})]:
                    path = (icon or {}).get("path", "")
                    if not path:
                        continue
                    full_path = path if os.path.isabs(path) else os.path.join(self.config_dir, path)
                    if not os.path.exists(full_path):
                        return f"技能 '{skill.get('name', '')}' 图标文件不存在"
                return f"技能 '{skill.get('name', '')}' 图标无法加载，请重新设置"
            pre = skill.get("precondition", {})
            if pre.get("enabled"):
                buff_path = pre.get("buff_icon", {}).get("path", "")
                if not buff_path:
                    return f"技能 '{skill.get('name', '')}' 已启用前置但未设置 Buff 图标"
                buff_full = (
                    buff_path if os.path.isabs(buff_path)
                    else os.path.join(self.config_dir, buff_path)
                )
                if not os.path.exists(buff_full):
                    return f"技能 '{skill.get('name', '')}' Buff 图标文件不存在"
                buff_m = RegionIconMatcher.from_buff_condition(pre, self.config_dir)
                if buff_m is None:
                    return f"技能 '{skill.get('name', '')}' Buff 图标无法加载"
        return None

    def stop_image_macro(self, config_name: str, force: bool = False, timeout: float = 2.0):
        with self.global_lock:
            if config_name not in self.image_macros:
                return
            macro_info = self.image_macros[config_name]
            if macro_info.is_stopped():
                return
            macro_info.stop_event.set()
            macro_info.set_state(MacroState.STOPPING)
            self.logger.info(f"图像宏停止信号已发送（配置: {config_name}）")
            if force:
                workers = list(macro_info.threads) if macro_info.threads else (
                    [macro_info.thread] if macro_info.thread else []
                )
                per = timeout / max(1, len(workers))
                for t in workers:
                    if t and t.is_alive():
                        t.join(timeout=per)

    def stop_image_macro_fast(self, config_name: str) -> bool:
        if config_name not in self.image_macros:
            return False
        macro_info = self.image_macros[config_name]
        if macro_info.is_stopped():
            return False
        macro_info.stop_event.set()
        return True

    def is_image_macro_running(self, config_name: str) -> bool:
        with self.global_lock:
            if config_name not in self.image_macros:
                return False
            macro_info = self.image_macros[config_name]
            if not macro_info.any_worker_alive():
                if macro_info.is_running():
                    macro_info.set_state(MacroState.STOPPED)
                return False
            return macro_info.is_running()

    def _capture_skill_frames(
        self,
        config_name: str,
        skills: List[dict],
        matcher_lists: List[List],
        buff_matchers: List,
        stop_event: threading.Event,
    ) -> Optional[Dict[int, Tuple[np.ndarray, np.ndarray, int, int]]]:
        """分组截屏，返回 skill_idx -> (frame_bgr, frame_gray, origin_x, origin_y)"""
        skill_rect_entries = []
        for idx, skill in enumerate(skills):
            matchers = matcher_lists[idx] if idx < len(matcher_lists) else []
            buff_m = buff_matchers[idx]
            pre = skill.get("precondition", {})
            rects = []
            if pre.get("enabled") and buff_m:
                rects.append(buff_m.get_search_rect())
            for m in matchers or []:
                if m:
                    rects.append(m.get_search_rect())
            if rects:
                skill_rect_entries.append((idx, rects))

        capture_groups = cluster_skill_rects(skill_rect_entries)
        if not capture_groups:
            return {}

        all_rects = [r for _, rects in skill_rect_entries for r in rects]
        global_union = union_search_rects(all_rects)
        union_area = rect_area(global_union) if global_union else 0
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"[图像宏] 扫描轮次 配置={config_name} "
                f"union_area={union_area} group_count={len(capture_groups)}"
            )

        if not begin_capture_frame():
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    f"[图像宏] 本轮跳过（DXGI 无新帧） 配置={config_name}"
                )
            return None

        frames: Dict[int, Tuple[np.ndarray, np.ndarray, int, int]] = {}
        try:
            for group in capture_groups:
                if stop_event.is_set():
                    break
                try:
                    t0 = time.perf_counter()
                    frame_bgr = grab_region(
                        group.union_x, group.union_y, group.union_w, group.union_h
                    )
                    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                    if self.logger.isEnabledFor(logging.DEBUG):
                        capture_ms = (time.perf_counter() - t0) * 1000
                        self.logger.debug(
                            f"[图像宏] 分组截屏 配置={config_name} "
                            f"union=({group.union_x},{group.union_y},"
                            f"{group.union_w}x{group.union_h}) "
                            f"技能索引={group.skill_indices} "
                            f"截屏耗时={capture_ms:.1f}ms"
                        )
                except Exception as e:
                    msg = str(e)
                    if isinstance(e, RuntimeError) and "DXGI" in msg:
                        self.logger.warning(
                            f"图像宏截屏失败（配置: {config_name}）: {e}"
                        )
                    else:
                        self.logger.error(
                            f"图像宏截屏失败（配置: {config_name}）: {e}",
                            exc_info=True,
                        )
                    high_precision_sleep(0.1, stop_event, 0.001)
                    continue

                for idx in group.skill_indices:
                    frames[idx] = (frame_bgr, frame_gray, group.union_x, group.union_y)
        finally:
            end_capture_frame()

        return frames

    def _execute_image_macro_kind(
        self,
        macro_info: MacroInfo,
        image_macro: dict,
        skills: List[dict],
        kind: str,
    ):
        """单类技能扫描循环（Buff 或攻击）"""
        config_name = macro_info.config_name
        kind_label = "Buff" if kind == SKILL_KIND_BUFF else "攻击"
        skills = [normalize_image_skill(s) for s in skills]
        scan_ms = resolve_scan_interval_ms(image_macro)

        matcher_lists = []
        buff_matchers = []
        states = []
        for skill in skills:
            matcher_lists.append(build_icon_matchers(skill, self.config_dir))
            pre = skill.get("precondition", {})
            if pre.get("enabled"):
                buff_m = RegionIconMatcher.from_buff_condition(pre, self.config_dir)
            else:
                buff_m = None
            buff_matchers.append(buff_m)
            states.append(SkillRuntimeState())

        skill_summary = ", ".join(s["name"] for s in skills)
        self.logger.debug(
            f"[图像宏:{kind_label}] 初始化 配置={config_name} 技能数={len(skills)} "
            f"扫描间隔={scan_ms}ms 技能列表=[{skill_summary}]"
        )

        skill_order = sort_candidates_by_priority(list(range(len(skills))), skills)
        last_scan_time = 0.0
        fire_lock = self._image_fire_lock

        try:
            macro_info.set_state(MacroState.RUNNING)

            while not macro_info.stop_event.is_set():
                if not window_focus_manager.is_target_window_active():
                    self.logger.info(
                        f"窗口焦点已改变，停止图像宏（配置: {config_name}，{kind_label}）"
                    )
                    macro_info.stop_event.set()
                    break

                now = time.time()
                due_at = last_scan_time + scan_ms / 1000.0
                if now < due_at:
                    high_precision_sleep(max(0.001, due_at - now), macro_info.stop_event, 0.001)
                    continue

                last_scan_time = time.time()
                frames = self._capture_skill_frames(
                    config_name, skills, matcher_lists, buff_matchers, macro_info.stop_event
                )
                if was_last_capture_round_skipped():
                    backoff = get_capture_backoff_sec()
                    if backoff > 0:
                        high_precision_sleep(backoff, macro_info.stop_event, 0.001)
                if frames is None:
                    continue

                now = time.time()
                for idx in skill_order:
                    if macro_info.stop_event.is_set():
                        break
                    if idx not in frames:
                        continue

                    skill = skills[idx]
                    matchers = matcher_lists[idx]
                    state = states[idx]
                    if not matchers:
                        continue

                    frame_bgr, frame_gray, origin_x, origin_y = frames[idx]
                    pre = skill.get("precondition", {})
                    pre_ok = True
                    trigger_mode = resolve_trigger_mode(pre) if pre.get("enabled") else None
                    buff_m = buff_matchers[idx]
                    if pre.get("enabled") and buff_m:
                        buff_result = buff_m.detect_in_frame(
                            frame_bgr, origin_x, origin_y, frame_gray=frame_gray
                        )
                        wait_ms = int(pre.get("wait_after_buff_ms", 300))
                        pre_ok = evaluate_buff_precondition(
                            buff_result.is_ready, trigger_mode, state, now, wait_ms
                        )
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(
                                f"[图像宏:{kind_label}] Buff检测 技能={skill['name']} "
                                f"模式={trigger_mode} 检测到={buff_result.is_ready} "
                                f"置信度={buff_result.confidence:.3f} pre_ok={pre_ok}"
                            )

                    if not pre_ok:
                        state.last_ready = False
                        continue

                    result = detect_skill_ready(
                        matchers, frame_bgr, origin_x, origin_y, frame_gray=frame_gray
                    )
                    state.last_ready = result.is_ready

                    ensure_status = update_ensure_press_state(state, result.is_ready, now)
                    if ensure_status == "waiting":
                        continue
                    if ensure_status == "timeout_retry":
                        cooldown_ms = resolve_skill_cooldown_ms(skill, trigger_mode)
                        try:
                            with fire_lock:
                                self._fire_skill_key(skill, macro_info.stop_event)
                            fired_at = time.time()
                            begin_ensure_retry(
                                state,
                                fired_at,
                                cooldown_ms=cooldown_ms,
                                ensure_timeout_ms=resolve_ensure_press_timeout_ms(skill),
                            )
                            now = fired_at
                            macro_info.bump_iteration()
                            self.logger.info(
                                f"图像宏确保按下重试 '{skill.get('name')}'（{kind_label}）"
                            )
                        except Exception as e:
                            self.logger.error(
                                f"图像宏按键失败（配置: {config_name}，技能: {skill.get('name')}）: {e}",
                                exc_info=True,
                            )
                        continue
                    if ensure_status == "timeout_give_up":
                        self.logger.warning(
                            f"图像宏确保按下超时放弃 技能={skill.get('name')}（{kind_label}）"
                        )
                        continue

                    cooldown_ms = resolve_skill_cooldown_ms(skill, trigger_mode)
                    should_fire = should_enqueue_skill(
                        trigger_mode, pre_ok, result.is_ready, state.last_ready,
                        state, now, interval_ms=cooldown_ms,
                    )
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(
                            f"[图像宏:{kind_label}] 技能检测 名称={skill['name']} "
                            f"就绪={result.is_ready} 执行={should_fire} "
                            f"置信度={result.confidence:.3f} 亮度={result.brightness:.0f} "
                            f"冷却={cooldown_ms}ms"
                        )
                    if not should_fire:
                        continue

                    try:
                        with fire_lock:
                            self._fire_skill_key(skill, macro_info.stop_event)
                        fired_at = time.time()
                        mark_skill_fired(
                            state,
                            fired_at,
                            trigger_mode,
                            cooldown_ms=cooldown_ms,
                            ensure_press=resolve_ensure_press(skill),
                            ensure_timeout_ms=resolve_ensure_press_timeout_ms(skill),
                            ensure_retries=resolve_ensure_press_retries(skill),
                        )
                        now = fired_at
                        macro_info.bump_iteration()
                        self.logger.info(
                            f"图像宏触发技能 '{skill.get('name')}'（{kind_label}）"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"图像宏按键失败（配置: {config_name}，技能: {skill.get('name')}）: {e}",
                            exc_info=True,
                        )
                        continue

        except Exception as e:
            self.logger.error(
                f"执行图像宏失败（配置: {config_name}，{kind_label}）: {e}",
                exc_info=True,
            )
            macro_info.set_state(MacroState.ERROR, str(e))
            macro_info.stop_event.set()
        finally:
            release_thread_capture()
            # 排除当前线程：仍存活的其它工作线程数为 0 时落 STOPPED
            others_alive = 0
            workers = list(macro_info.threads) if macro_info.threads else (
                [macro_info.thread] if macro_info.thread else []
            )
            current = threading.current_thread()
            for t in workers:
                if t and t is not current and t.is_alive():
                    others_alive += 1
            if others_alive == 0:
                if macro_info.state in (
                    MacroState.RUNNING, MacroState.STOPPING, MacroState.STARTING
                ):
                    macro_info.set_state(MacroState.STOPPED)
                macro_info.stop_time = time.time()
                duration = (
                    macro_info.stop_time - macro_info.start_time
                    if macro_info.start_time else 0
                )
                self.logger.info(
                    f"图像宏已停止（配置: {config_name}，{kind_label}最后退出，"
                    f"运行时长: {duration:.2f}秒，触发次数: {macro_info.iteration_count}）"
                )
            else:
                self.logger.debug(
                    f"[图像宏:{kind_label}] 工作线程退出，仍有 {others_alive} 个线程运行 "
                    f"（配置: {config_name}）"
                )

    def _fire_skill_key(self, skill: dict, stop_event):
        """触发技能按键"""
        from key_mapping import key_mapping
        key = skill.get("key", "")
        press_time = skill.get("press_time", 50) / 1000.0
        repeat_count = skill.get("repeat_count", 1)
        repeat_interval = skill.get("repeat_interval", 100) / 1000.0
        is_mouse = key_mapping.is_mouse_key(key)
        vk_code = input_simulator.get_virtual_key(key)
        if vk_code == 0:
            raise ValueError(f"无效的按键: {key}")

        for i in range(repeat_count):
            if stop_event and stop_event.is_set():
                break
            if is_mouse:
                input_simulator.send_mouse_event(vk_code, True)
            else:
                flags = input_simulator.get_key_flags(key, True)
                input_simulator.send_key_event(vk_code, flags, key)
            high_precision_sleep(press_time, stop_event, 0.001)
            if is_mouse:
                input_simulator.send_mouse_event(vk_code, False)
            else:
                flags = input_simulator.get_key_flags(key, False)
                input_simulator.send_key_event(vk_code, flags, key)
            if i < repeat_count - 1:
                high_precision_sleep(repeat_interval, stop_event, 0.001)
