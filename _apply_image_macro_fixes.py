# Temporary script to apply image macro review fixes
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# 1. hotkey_manager mode3 fix
p = ROOT / "hotkey_manager.py"
text = p.read_text(encoding="utf-8")
old = """                    def make_press_callback(cfg_name, hk_type):
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
                                        if not is_pressed or is_running:
                                            self.image_hotkey_pressed[cfg_name] = True
                                            self.on_image_hotkey_triggered(cfg_name)
                            except Exception as e:
                                self.logger.error(f"热键按下回调错误: {e}", exc_info=True)
                        return on_press"""
new = """                    def make_press_callback(cfg_name, hk_type, hk_mode):
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
                        return on_press"""
if old not in text:
    raise SystemExit("hotkey_manager block not found")
text = text.replace(old, new, 1)
text = text.replace(
    "press_callback = make_press_callback(config_name, hotkey_type)",
    "press_callback = make_press_callback(config_name, hotkey_type, mode)",
    1,
)
p.write_text(text, encoding="utf-8")
print("hotkey_manager ok")

# 2. hotkey_conflict
p = ROOT / "hotkey_conflict.py"
text = p.read_text(encoding="utf-8")
old = """    for skill in (config.get("image_macro") or {}).get("skills", []):
        if exclude_skill_id and skill.get("id") == exclude_skill_id:
            continue
        skill_key = (skill.get("key") or "").strip()
        if skill_key and skill_key.lower() == hotkey_lower:
            return ("图像宏技能按键", "")"""
new = """    for skill in (config.get("image_macro") or {}).get("skills", []):
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
            return ("图像宏技能组合按键", "")"""
if old not in text:
    raise SystemExit("hotkey_conflict block not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("hotkey_conflict ok")

# 3. image_recognizer anchor tolerance
p = ROOT / "image_recognizer.py"
text = p.read_text(encoding="utf-8")
old = """            position_ok = True
            x_diff = y_diff = 0
            if self.anchor_x or self.anchor_y:
                x_diff = abs(matched_abs_x - self.anchor_x)
                y_diff = abs(matched_abs_y - self.anchor_y)
                position_ok = x_diff <= tolerance and y_diff <= tolerance"""
new = """            x_diff = abs(matched_abs_x - self.anchor_x)
            y_diff = abs(matched_abs_y - self.anchor_y)
            position_ok = x_diff <= tolerance and y_diff <= tolerance"""
if old not in text:
    raise SystemExit("image_recognizer block not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("image_recognizer ok")

# 4. image_macro_runner fire_lock
p = ROOT / "image_macro_runner.py"
text = p.read_text(encoding="utf-8")
old = """            macro_info.stop_event.clear()
            macro_info.threads = []

            workers = []"""
new = """            macro_info.stop_event.clear()
            macro_info.threads = []
            if getattr(self, "_image_fire_lock", None) is None:
                self._image_fire_lock = threading.Lock()

            workers = []"""
if old not in text:
    raise SystemExit("image_macro_runner init block not found")
text = text.replace(old, new, 1)
old2 = """        fire_lock = getattr(self, "_image_fire_lock", None)
        if fire_lock is None:
            self._image_fire_lock = threading.Lock()
            fire_lock = self._image_fire_lock"""
new2 = """        fire_lock = self._image_fire_lock"""
if old2 not in text:
    raise SystemExit("image_macro_runner fire_lock block not found")
p.write_text(text.replace(old2, new2, 1), encoding="utf-8")
print("image_macro_runner ok")

print("All fixes applied.")
