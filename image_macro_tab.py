# -*- coding: utf-8 -*-
"""图像宏标签页"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton, QMessageBox,
    QDialog, QFormLayout, QAbstractItemView, QStyledItemDelegate,
    QApplication, QStyle, QStyleOptionViewItem, QTabBar,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QColor

from macro_tab_base import MacroTabBase
from image_skill_dialog import ImageSkillDialog
from image_recognizer import (
    bgr_to_qpixmap, load_template_preview,
    normalize_image_skill, migrate_post_buff_icon_path, TRIGGER_MODE_ABSENT,
    DEFAULT_EXECUTE_INTERVAL_MS, clamp_skill_priority,
    find_skill_by_priority, find_duplicate_priorities,
    resolve_skill_kind, SKILL_KIND_ATTACK, SKILL_KIND_BUFF,
)
from asset_manager import delete_skill_assets, DEFAULT_IMAGE_MACRO
from logger import get_logger


class CenterIconDelegate(QStyledItemDelegate):
    """表格单元格内图标居中绘制"""

    def paint(self, painter, option, index):
        icon = index.data(Qt.DecorationRole)
        text = index.data(Qt.DisplayRole)
        if icon and not text:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            opt.icon = QIcon()
            widget = opt.widget
            style = widget.style() if widget else QApplication.style()
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

            pm = icon.pixmap(opt.decorationSize)
            if not pm.isNull():
                r = option.rect
                x = r.x() + (r.width() - pm.width()) // 2
                y = r.y() + (r.height() - pm.height()) // 2
                painter.drawPixmap(x, y, pm)
            return

        opt = QStyleOptionViewItem(option)
        opt.displayAlignment = Qt.AlignCenter
        super().paint(painter, opt, index)


class ImageMacroTab(MacroTabBase):
    """图像宏标签页"""

    def __init__(self, parent=None, *, has_config_fn=None, conflict_checker=None):
        super().__init__(
            parent,
            has_config_fn=has_config_fn,
            conflict_checker=conflict_checker,
        )
        self.skills = []
        self.logger = get_logger()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        hotkey_group = QGroupBox("图像宏热键设置")
        hotkey_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        hotkey_layout = QFormLayout()

        self.hotkey_label = QLabel("未设置")
        self.hotkey_label.setAlignment(Qt.AlignCenter)
        self.hotkey_label.setStyleSheet(
            "background-color:#f0f0f0;border:1px solid #ccc;padding:8px;"
            "border-radius:4px;min-height:20px;font-size:18px;"
        )
        btn_row = QHBoxLayout()
        self.set_hotkey_btn = QPushButton("设置热键")
        self.reset_hotkey_btn = QPushButton("重置")
        btn_row.addWidget(self.set_hotkey_btn)
        btn_row.addWidget(self.reset_hotkey_btn)
        hotkey_layout.addRow("热键:", self.hotkey_label)
        hotkey_layout.addRow("", btn_row)
        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        mode_group = QGroupBox("图像宏执行模式")
        mode_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        mode_layout = QVBoxLayout()
        self.mode1 = QRadioButton("模式1: 按下启动热键开始扫描，再次按下停止")
        self.mode3 = QRadioButton("模式3: 按住启动热键开始扫描，松开停止")
        self.mode1.setChecked(True)
        mode_layout.addWidget(self.mode1)
        mode_layout.addWidget(self.mode3)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        list_group = QGroupBox("技能列表")
        list_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        list_layout = QVBoxLayout()

        self.kind_tabs = QTabBar()
        self.kind_tabs.addTab("普通技能")
        self.kind_tabs.addTab("Buff类")
        self.kind_tabs.setCurrentIndex(0)
        self.kind_tabs.setExpanding(False)
        self.kind_tabs.currentChanged.connect(lambda _i: self._refresh_table())
        list_layout.addWidget(self.kind_tabs)

        tool_row = QHBoxLayout()
        self.add_btn = QPushButton("新增技能")
        self.edit_btn = QPushButton("编辑")
        self.del_btn = QPushButton("删除")
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        for btn in (self.add_btn, self.edit_btn, self.del_btn, self.up_btn, self.down_btn):
            tool_row.addWidget(btn)
        list_layout.addLayout(tool_row)

        self.skill_table = QTableWidget(0, 6)
        self.skill_table.setHorizontalHeaderLabels(
            ["名称", "按键", "前置条件", "技能图标", "优先级", "执行间隔"]
        )
        self.skill_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.skill_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.skill_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.skill_table.setAlternatingRowColors(True)
        self.skill_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #ccc;
            }
            QTableWidget::item {
                text-align: center;
                padding: 4px;
            }
        """)
        self.skill_table.verticalHeader().setVisible(False)
        self.skill_table.verticalHeader().setDefaultSectionSize(52)
        self.skill_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.skill_table.setIconSize(QSize(48, 48))
        self.skill_table.setItemDelegateForColumn(3, CenterIconDelegate(self.skill_table))
        list_layout.addWidget(self.skill_table)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group, 1)

        self.set_hotkey_btn.clicked.connect(self.set_hotkey)
        self.reset_hotkey_btn.clicked.connect(self.reset_hotkey)
        self.mode1.toggled.connect(self.on_config_changed)
        self.mode3.toggled.connect(self.on_config_changed)
        self.add_btn.clicked.connect(self.add_skill)
        self.edit_btn.clicked.connect(self.edit_skill)
        self.del_btn.clicked.connect(self.delete_skill)
        self.up_btn.clicked.connect(lambda: self.move_skill(-1))
        self.down_btn.clicked.connect(lambda: self.move_skill(1))

    def _current_kind(self):
        return SKILL_KIND_ATTACK if self.kind_tabs.currentIndex() == 0 else SKILL_KIND_BUFF

    def _indices_of_kind(self, kind=None):
        kind = kind or self._current_kind()
        return [
            i for i, s in enumerate(self.skills)
            if resolve_skill_kind(s) == kind
        ]

    def _row_to_global(self, row):
        indices = self._indices_of_kind()
        if row < 0 or row >= len(indices):
            return -1
        return indices[row]

    def set_hotkey(self):
        self._assign_hotkey("image", self.hotkey_label)

    def reset_hotkey(self):
        self._reset_hotkey_label(self.hotkey_label)

    def _get_config_name(self):
        if self.parent and hasattr(self.parent, 'config_name'):
            return self.parent.config_name
        return ""

    def _get_config_dir(self):
        if self.parent and hasattr(self.parent, 'config_dir'):
            return self.parent.config_dir
        return "config"

    def _check_skill_key_conflict(self, key, exclude_skill_id=None):
        checker = self._resolve_conflict_checker()
        if checker:
            return checker(
                key, "image_skill", exclude_skill_id=exclude_skill_id
            )
        return None

    def _check_skill_priority_conflict(self, priority, exclude_skill_id=None, skill_kind=None):
        conflict = find_skill_by_priority(
            self.skills,
            priority,
            exclude_skill_id,
            skill_kind=skill_kind or self._current_kind(),
        )
        if conflict:
            return conflict.get("name") or ""
        return None

    def _format_duplicate_priority_warning(self, dups):
        lines = []
        for p, names in dups:
            lines.append(f"优先级 {p}：{', '.join(names)}")
        return "以下技能的优先级重复，请修改后再运行图像宏：\n\n" + "\n".join(lines)

    def _get_main_window(self):
        if self.parent is not None:
            return self.parent
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, 'save_config_immediate'):
                return widget
            widget = widget.parentWidget()
        return None

    def _persist_skill_changes(self):
        """技能变更后同步配置并立即写 JSON"""
        main_win = self._get_main_window()
        image_config = self.get_config()
        skill_count = len(image_config.get("image_macro", {}).get("skills", []))
        if main_win and hasattr(main_win, 'current_config'):
            main_win.current_config["image_macro"] = image_config["image_macro"]
        saved = False
        if main_win and hasattr(main_win, 'save_config_immediate'):
            saved = main_win.save_config_immediate()
        self.on_config_changed()
        if saved:
            self.logger.info(f"图像宏技能已写入配置，当前技能数: {skill_count}")
        else:
            self.logger.warning(f"图像宏技能配置保存失败，当前技能数: {skill_count}")
            QMessageBox.warning(self, "保存失败", "技能未能写入配置文件，请确认已选中配置后重试")

    def add_skill(self):
        if self.parent and hasattr(self.parent, 'has_config'):
            if not self.parent.has_config():
                QMessageBox.warning(self, "提示", "请先新增配置")
                return

        committed = [False]
        default_kind = self._current_kind()

        def commit_skill(skill):
            self.skills.append(normalize_image_skill(skill))
            # 切到新技能所属 Tab
            kind = resolve_skill_kind(skill)
            self.kind_tabs.setCurrentIndex(0 if kind == SKILL_KIND_ATTACK else 1)
            self._refresh_table()
            self._persist_skill_changes()
            committed[0] = True

        dialog = ImageSkillDialog(
            self,
            config_name=self._get_config_name(),
            config_dir=self._get_config_dir(),
            check_key_conflict=self._check_skill_key_conflict,
            check_priority_conflict=self._check_skill_priority_conflict,
            on_skill_commit=commit_skill,
            default_skill_kind=default_kind,
        )
        if dialog.exec_() == QDialog.Accepted and not committed[0]:
            QMessageBox.warning(self, "提示", "技能未能保存，请重试")

    def edit_skill(self):
        row = self.skill_table.currentRow()
        global_idx = self._row_to_global(row)
        if global_idx < 0:
            QMessageBox.warning(self, "提示", "请先选择要编辑的技能")
            return
        skill = self.skills[global_idx]

        committed = [False]

        def commit_skill(updated):
            if 0 <= global_idx < len(self.skills):
                self.skills[global_idx] = normalize_image_skill(updated)
            kind = resolve_skill_kind(updated)
            self.kind_tabs.setCurrentIndex(0 if kind == SKILL_KIND_ATTACK else 1)
            self._refresh_table()
            self._persist_skill_changes()
            committed[0] = True

        dialog = ImageSkillDialog(
            self,
            skill_data=skill,
            config_name=self._get_config_name(),
            config_dir=self._get_config_dir(),
            check_key_conflict=self._check_skill_key_conflict,
            check_priority_conflict=self._check_skill_priority_conflict,
            on_skill_commit=commit_skill,
            default_skill_kind=resolve_skill_kind(skill),
        )
        if dialog.exec_() == QDialog.Accepted and not committed[0]:
            QMessageBox.warning(self, "提示", "技能未能保存，请重试")

    def delete_skill(self):
        row = self.skill_table.currentRow()
        global_idx = self._row_to_global(row)
        if global_idx < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的技能")
            return
        skill = self.skills[global_idx]
        reply = QMessageBox.question(self, "确认", f"确定删除技能 '{skill.get('name', '')}' 吗？")
        if reply != QMessageBox.Yes:
            return
        config_name = self._get_config_name()
        if config_name and skill.get("id"):
            delete_skill_assets(self._get_config_dir(), config_name, skill["id"])
        del self.skills[global_idx]
        self._refresh_table()
        self._persist_skill_changes()

    def move_skill(self, direction):
        row = self.skill_table.currentRow()
        indices = self._indices_of_kind()
        if row < 0 or row >= len(indices):
            return
        new_row = row + direction
        if new_row < 0 or new_row >= len(indices):
            return
        i1, i2 = indices[row], indices[new_row]
        self.skills[i1], self.skills[i2] = self.skills[i2], self.skills[i1]
        self._refresh_table()
        self.skill_table.selectRow(new_row)
        self._persist_skill_changes()

    def _refresh_table(self):
        self.skill_table.setRowCount(0)
        config_dir = self._get_config_dir()
        kind = self._current_kind()
        kind_skills = [self.skills[i] for i in self._indices_of_kind(kind)]
        duplicate_priorities = {
            p for p, _ in find_duplicate_priorities(self.skills, skill_kind=kind)
        }
        for skill in kind_skills:
            row = self.skill_table.rowCount()
            self.skill_table.insertRow(row)
            for col, val in enumerate([
                skill.get("name", ""),
                skill.get("key", ""),
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.skill_table.setItem(row, col, item)

            pre_item = QTableWidgetItem()
            pre_item.setTextAlignment(Qt.AlignCenter)
            pre = skill.get("precondition", {})
            if not pre.get("enabled"):
                pre_item.setText("无")
            else:
                name = (pre.get("name") or "").strip()
                mode = pre.get("trigger_mode", "present")
                prefix = "无" if mode == TRIGGER_MODE_ABSENT else "有"
                display_name = name[:4]
                pre_item.setText(f"{prefix}:{display_name}" if display_name else prefix)
                if name:
                    pre_item.setToolTip(name)
                buff_path = pre.get("buff_icon", {}).get("path", "")
                if buff_path:
                    img = load_template_preview(buff_path, config_dir)
                    if img is not None:
                        pre_item.setIcon(QIcon(bgr_to_qpixmap(img, max_size=32)))
            self.skill_table.setItem(row, 2, pre_item)

            icon_item = QTableWidgetItem()
            icon_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            icons = skill.get("icons") or []
            icon_path = ""
            if icons:
                icon_path = icons[0].get("path", "")
            if not icon_path:
                icon_path = skill.get("icon", {}).get("path", "")
            if icon_path:
                img = load_template_preview(icon_path, config_dir)
                if img is not None:
                    icon_item.setIcon(QIcon(bgr_to_qpixmap(img, max_size=48)))
                else:
                    icon_item.setText("无")
            else:
                icon_item.setText("无")
            self.skill_table.setItem(row, 3, icon_item)

            priority = clamp_skill_priority(skill.get("priority"))
            if priority is None:
                priority_text = "-"
                priority_tip = ""
            elif priority in duplicate_priorities:
                priority_text = f"{priority}(重复)"
                priority_tip = f"优先级 {priority} 重复，请修改"
            else:
                priority_text = str(priority)
                priority_tip = ""
            priority_item = QTableWidgetItem(priority_text)
            priority_item.setTextAlignment(Qt.AlignCenter)
            if priority_tip:
                priority_item.setToolTip(priority_tip)
                priority_item.setForeground(QColor(200, 0, 0))
            self.skill_table.setItem(row, 4, priority_item)

            interval_ms = skill.get("execute_interval_ms", DEFAULT_EXECUTE_INTERVAL_MS)
            interval_item = QTableWidgetItem(f"{interval_ms}ms")
            interval_item.setTextAlignment(Qt.AlignCenter)
            self.skill_table.setItem(row, 5, interval_item)

    def on_config_changed(self):
        self._on_user_changed()

    def get_config(self):
        hotkey = self.hotkey_label.text()
        return {
            "image_macro": {
                "hotkey": hotkey if hotkey != "未设置" else "",
                "mode": 1 if self.mode1.isChecked() else 3,
                "skills": [normalize_image_skill(s.copy()) for s in self.skills],
            }
        }

    def load_config(self, config):
        with self._guard_loading():
            image_macro = config.get("image_macro", DEFAULT_IMAGE_MACRO.copy())
            hotkey = image_macro.get("hotkey", "")
            self.hotkey_label.setText(hotkey if hotkey else "未设置")
            mode = image_macro.get("mode", 1)
            if mode == 3:
                self.mode3.setChecked(True)
            else:
                self.mode1.setChecked(True)
            config_dir = self._get_config_dir()
            config_name = self._get_config_name()
            self.skills = [
                normalize_image_skill(
                    migrate_post_buff_icon_path(s.copy(), config_dir, config_name)
                )
                for s in image_macro.get("skills", [])
            ]
            self._refresh_table()
            dups = find_duplicate_priorities(self.skills, skill_kind=self._current_kind())
            if dups:
                QMessageBox.warning(
                    self, "优先级重复",
                    self._format_duplicate_priority_warning(dups),
                )

    def set_buttons_enabled(self, enabled):
        for w in (
            self.set_hotkey_btn, self.reset_hotkey_btn,
            self.mode1, self.mode3,
            self.add_btn, self.edit_btn, self.del_btn, self.up_btn, self.down_btn,
            self.kind_tabs,
        ):
            w.setEnabled(enabled)
