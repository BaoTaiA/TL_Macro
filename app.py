# -*- coding: utf-8 -*-
"""主窗口模块 - 负责UI和模块协调"""
import sys
import os
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QListWidget, QGroupBox, QLabel, QTabWidget, 
                             QMessageBox, QSystemTrayIcon, QMenu, QAction, 
                             QDialog, QStyle)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon

# 导入自定义模块
from version import APP_TITLE, APP_VERSION
from logger import get_logger, set_log_level, get_current_log_level, log_level_from_name
from utils import request_admin_privileges, cleanup_memory, get_app_base_dir, get_icon_path, ensure_single_instance, is_admin
from dialogs import NewConfigDialog, RenameConfigDialog
from config_manager import ConfigManager
from config_defaults import make_default_config, merge_loaded_config
from macro_executor import MacroExecutor
from hotkey_manager import HotkeyManager
from about import AboutTab
from home import HomeTab
from global_settings_tab import GlobalSettingsTab
from global_settings import (
    load_settings as load_global_settings,
    get_backend,
    backend_label,
    get_scan_interval_ms,
    get_global_mode,
    get_processes,
    get_log_level,
)
from process_history import process_history_monitor
from multi_macro_tab import MultiMacroTab
from single_macro_tab import SingleKeyMacroTab
from image_macro_tab import ImageMacroTab
from asset_manager import delete_config_assets, rename_config_assets, update_skill_paths_in_config


class MacroTool(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger()
        self.setWindowTitle(APP_TITLE)
        # 设置初始窗口大小并进行DPI适配
        self.resize(1090, 900)
        self.setMinimumSize(800, 600)

        # 设置全局字体
        font = QFont("微软雅黑", 9)
        self.setFont(font)
        
        self.logger.info("初始化主窗口...")
        
        # 初始化配置
        self.config_name = ""  # 默认无配置
        self.config_dir = os.path.join(get_app_base_dir(), "config")
        self.current_config = make_default_config()
        self.current_config_enabled = False  # 当前配置是否启用
        
        # 创建管理器实例
        self.config_manager = ConfigManager(self.config_dir)
        self.macro_executor = MacroExecutor()
        self.macro_executor.config_dir = self.config_dir
        self.hotkey_manager = HotkeyManager(
            self.macro_executor,
            lambda: self.config_manager.enabled_configs_data,
            self._rebuild_hotkey_maps
        )
        
        # 连接宏执行器的信号
        self.macro_executor.show_message_signal.connect(self.show_message)
        
        # 状态恢复定时器 - 定期检查并修复不一致状态
        # 优化：启动时延迟3秒再开始，避免启动时的CPU占用
        self.state_recovery_timer = QTimer(self)
        self.state_recovery_timer.timeout.connect(self._recover_inconsistent_states)
        # 延迟3秒启动，然后每2秒检查一次（降低频率）
        QTimer.singleShot(3000, lambda: self.state_recovery_timer.start(2000))

        # 内存清理定时器 - 每2分钟自动清理一次未使用的内存
        self.memory_cleanup_timer = QTimer(self)
        self.memory_cleanup_timer.timeout.connect(cleanup_memory)
        self.memory_cleanup_timer.start(120000)  # 每2分钟执行一次（120000毫秒）

        # 配置保存防抖定时器 - 避免频繁保存文件
        self._save_config_timer = QTimer(self)
        self._save_config_timer.setSingleShot(True)  # 单次触发
        self._save_config_timer.timeout.connect(self._do_save_config)
        self._pending_config_save = False

        # 创建系统托盘图标
        self.create_system_tray()

        # 创建UI
        self.init_ui()

    def create_system_tray(self):
        """创建系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 尝试使用tl.ico图标，如果不存在则使用系统默认图标
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        # 创建托盘菜单
        tray_menu = QMenu()
        restore_action = QAction("显示窗口", self)
        quit_action = QAction("退出程序", self)  # 修改文字明确表示是退出
        
        restore_action.triggered.connect(self.show_window)
        quit_action.triggered.connect(self.quit_application)  # 连接到真正的退出方法
        
        tray_menu.addAction(restore_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # 添加双击托盘图标显示窗口的功能
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def show_window(self):
        """显示窗口"""
        self.showNormal()
        self.activateWindow()
        self.raise_()  # 确保窗口在最前面

    def quit_application(self):
        """退出应用"""
        self.flush_pending_save()
        # 停止所有宏执行
        self.macro_executor.stop_all_macros()
        # 清空热键状态
        self.hotkey_manager.clear_hotkey_states()
        # 停止热键监听
        self.hotkey_manager.stop_hotkey_listener()
        process_history_monitor.stop()
        from screen_capture import shutdown_capture
        shutdown_capture()
        # 完全退出应用
        QApplication.instance().quit()

    def closeEvent(self, event):
        """重写关闭事件，实现最小化到托盘"""
        # 不要停止热键监听，只是隐藏窗口
        event.ignore()
        self.hide()
        self.tray_icon.setIcon(QIcon(get_icon_path()))
        self.tray_icon.showMessage(
            APP_TITLE,
            "程序已在后台运行点击托盘图标恢复窗口",
            QSystemTrayIcon.Information,
            2000
        )

    
    def _recover_inconsistent_states(self):
        """状态恢复机制 - 定期检查并修复不一致状态"""
        self.macro_executor.recover_inconsistent_states(
            self.hotkey_manager.multi_hotkey_pressed,
            self.hotkey_manager.single_hotkey_pressed,
            self.hotkey_manager.mouse_pressed_multi,
            self.hotkey_manager.mouse_pressed_single,
            self.hotkey_manager.image_hotkey_pressed,
            self.hotkey_manager.mouse_pressed_image,
        )

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)  # 使用横向布局分割左右

        # ==================== 左侧：配置文件列表 ====================
        left_group = QGroupBox("配置文件列表")
        left_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        left_group.setMaximumWidth(210)  # 设置最大宽度为200像素
        left_layout = QVBoxLayout()

        # 已启用配置列表
        enabled_label = QLabel("已启用")
        enabled_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #0066cc;")
        left_layout.addWidget(enabled_label)
        
        self.enabled_config_list = QListWidget()
        self.enabled_config_list.itemClicked.connect(self.on_config_item_clicked)
        self.enabled_config_list.itemDoubleClicked.connect(self.toggle_config_enabled)
        self.enabled_config_list.setStyleSheet("""
            QListWidget {
                padding: 5px;
                outline: 0px;
                min-height: 80px;
            }
            QListWidget::item {
                padding: 5px 0;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background-color: #d3d3d3;
                color: black;
            }
        """)
        left_layout.addWidget(self.enabled_config_list)

        # 未启用配置列表
        disabled_label = QLabel("未启用")
        disabled_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #666666; margin-top: 10px;")
        left_layout.addWidget(disabled_label)
        
        self.disabled_config_list = QListWidget()
        self.disabled_config_list.itemClicked.connect(self.on_config_item_clicked)
        self.disabled_config_list.itemDoubleClicked.connect(self.toggle_config_enabled)
        self.disabled_config_list.setStyleSheet("""
            QListWidget {
                padding: 5px;
                outline: 0px;
                min-height: 80px;
            }
            QListWidget::item {
                padding: 5px 0;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background-color: #d3d3d3;
                color: black;
            }
        """)
        left_layout.addWidget(self.disabled_config_list)

        # 第一行：新增、重命名
        first_row = QHBoxLayout()
        self.new_btn = QPushButton("新增")
        self.rename_btn = QPushButton("重命名")
        first_row.addWidget(self.new_btn)
        first_row.addWidget(self.rename_btn)
        left_layout.addLayout(first_row)
        
        # 第二行：删除配置
        second_row = QHBoxLayout()
        self.delete_btn = QPushButton("删除配置")
        second_row.addWidget(self.delete_btn)
        left_layout.addLayout(second_row)

        left_group.setLayout(left_layout)
        main_layout.addWidget(left_group, 1)  # 占比1（左侧配置文件列表，宽度更窄）

        # ==================== 右侧：功能区 ====================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

    # 主页和标签页（主页放在最前面，默认打开）

        # 使用标签页组织功能
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-top: none;
            }
            QTabBar::tab {
                font-weight: bold;
                padding: 8px 20px;
                margin: 2px;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #f0f0f0;
            }
            QTabBar::tab:!selected {
                background: #e0e0e0;
            }
        """)
        
        # 主页标签页（默认打开）
        self.home_tab = HomeTab(self)
        self.tab_widget.addTab(self.home_tab, "主页")

        tab_deps = dict(
            has_config_fn=self.has_config,
            conflict_checker=self.check_hotkey_conflict,
        )

        # 多键宏标签页
        self.multi_macro_tab = MultiMacroTab(self, **tab_deps)
        self.tab_widget.addTab(self.multi_macro_tab, "多键宏")

        # 单键宏标签页
        self.single_macro_tab = SingleKeyMacroTab(self, **tab_deps)
        self.tab_widget.addTab(self.single_macro_tab, "单键宏")

        # 图像宏标签页
        self.image_macro_tab = ImageMacroTab(self, **tab_deps)
        self.tab_widget.addTab(self.image_macro_tab, "图像宏")
        
        # 全局参数标签页
        self.global_settings_tab = GlobalSettingsTab(self)
        self.tab_widget.addTab(self.global_settings_tab, "全局参数")
        
        # 关于标签页
        self.about_tab = AboutTab()
        self.tab_widget.addTab(self.about_tab, "关于")
        
        right_layout.addWidget(self.tab_widget)

        # 默认选中主页
        self.tab_widget.setCurrentIndex(0)

        right_widget.setLayout(right_layout)
        main_layout.addWidget(right_widget, 15)  # 占比15，右侧更大（调整比例让左侧更窄）

        # 连接信号
        self.new_btn.clicked.connect(self.new_config)
        self.rename_btn.clicked.connect(self.rename_config)
        self.delete_btn.clicked.connect(self.delete_config)
        
        # 连接多键宏配置更改信号
        self.multi_macro_tab.configChanged.connect(self.on_multi_macro_config_changed)
        
        # 连接单键宏配置更改信号
        self.single_macro_tab.configChanged.connect(self.on_single_macro_config_changed)

        # 连接图像宏配置更改信号
        self.image_macro_tab.configChanged.connect(self.on_image_macro_config_changed)
        
        # 连接全局参数更改信号
        self.global_settings_tab.configChanged.connect(self.on_global_settings_changed)

        # 初始化
        self.config_manager.create_config_dir()
        self.config_manager.load_enabled_configs()
        self.load_configs()
        
        # 加载已启用配置的数据到内存
        self.refresh_enabled_configs_data()
        
        # 如果有已启用的配置，加载第一个
        if self.enabled_config_list.count() > 0:
            self.enabled_config_list.setCurrentRow(0)
            self.load_config(self.enabled_config_list.item(0))
        elif self.disabled_config_list.count() > 0:
            # 如果没有已启用的，加载第一个未启用的
            self.disabled_config_list.setCurrentRow(0)
            self.load_config(self.disabled_config_list.item(0))
        else:
            # 没有任何配置
            self.config_name = ""
            self.current_config_enabled = False
            self.update_ui()
            
        # 启动热键监听
        self.hotkey_manager.start_hotkey_listener()
        process_history_monitor.start()
        self.logger.info("主窗口初始化完成")

    def load_configs(self):
        """加载所有配置文件，分成已启用和未启用"""
        self.enabled_config_list.clear()
        self.disabled_config_list.clear()
        
        # 获取所有配置文件名
        config_names = self.config_manager.get_all_config_names()
        
        # 分别添加到已启用和未启用列表
        for name in config_names:
            if name in self.config_manager.enabled_configs:
                self.enabled_config_list.addItem(name)
            else:
                self.disabled_config_list.addItem(name)
            
        # 刷新配置列表显示
        self.enabled_config_list.repaint()
        self.disabled_config_list.repaint()

    def on_config_item_clicked(self, item):
        """配置文件项点击事件处理 - 支持单击选中/取消选中，两个列表总共只能选中一个"""
        if not item:
            return
        
        clicked_config_name = item.text()
        sender_list = self.sender()  # 获取触发事件的列表控件
        
        # 如果点击的是当前已选中的配置，取消选中
        if self.config_name == clicked_config_name:
            # 取消当前列表的选中状态
            sender_list.setCurrentItem(None)
            # 如果另一个列表也选中了同一个配置，也取消选中
            if sender_list == self.enabled_config_list:
                other_list = self.disabled_config_list
            else:
                other_list = self.enabled_config_list
            
            # 检查另一个列表是否也选中了同一个配置
            other_item = other_list.currentItem()
            if other_item and other_item.text() == clicked_config_name:
                other_list.setCurrentItem(None)
            
            self.flush_pending_save()
            # 清空当前配置
            self.config_name = ""
            self.current_config = make_default_config()
            self.current_config_enabled = False
            self.update_ui()
            self.logger.debug(f"已取消选中配置 {clicked_config_name}")
            return
        
        # 清除另一个列表的选中状态（确保两个列表总共只能选中一个配置）
        if sender_list == self.enabled_config_list:
            other_list = self.disabled_config_list
        else:
            other_list = self.enabled_config_list
        
        # 清除另一个列表的所有选中状态
        other_list.setCurrentItem(None)
        
        # 加载配置（仅显示，不停止宏）
        self.load_config(item, stop_macros=False)

    def load_config(self, item=None, stop_macros=False):
        """加载配置
        
        Args:
            item: 配置项（QListWidgetItem）
            stop_macros: 是否在加载前停止所有宏（默认False，仅显示时不停止）
        """
        # 获取要加载的配置名
        target_config_name = ""
        if item:
            target_config_name = item.text()
        
        # 如果加载的是当前已选中的配置，直接返回（避免重复加载）
        if target_config_name and target_config_name == self.config_name:
            self.logger.debug(f"配置 {target_config_name} 已加载，跳过重复加载")
            return

        # 切换配置前先保存当前配置的待写入数据
        if self.config_name and target_config_name != self.config_name:
            self.flush_pending_save()
        
        # 如果需要停止宏（比如切换配置、禁用配置等操作）
        if stop_macros:
            self.logger.info("切换配置前，停止所有宏...")
            self.macro_executor.stop_all_macros()
            self.hotkey_manager.clear_hotkey_states()
        
        if item:
            self.config_name = item.text()
        
        # 检查当前配置是否启用
        self.current_config_enabled = self.config_name in self.config_manager.enabled_configs
            
        self.logger.info(f"正在加载配置: {self.config_name} (启用状态: {self.current_config_enabled})")
        
        if not self.config_name:
            # 没有配置
            self.current_config = make_default_config()
            self.update_ui()
            return
        
        try:
            # 从配置管理器加载配置
            loaded_config = self.config_manager.load_config_by_name(self.config_name)
            if loaded_config is None:
                loaded_config = {}
            
            self.current_config = merge_loaded_config(loaded_config)
            
            self.update_ui()
            
            self.logger.info(f"配置 {self.config_name} 加载完成")
            
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"加载配置失败: {e}")

    def update_ui(self):
        """更新UI显示"""
        # 更新主页数据（如果存在主页标签）
        try:
            if hasattr(self, 'home_tab') and self.home_tab:
                self.home_tab.load_data()
        except Exception as e:
            self.logger.warning(f"更新主页数据失败: {e}", exc_info=True)
        
        # 更新多键宏UI
        self.multi_macro_tab.load_config(self.current_config)
        
        # 更新单键宏UI
        self.single_macro_tab.load_config(self.current_config)

        # 更新图像宏UI
        self.image_macro_tab.load_config(self.current_config)
        
        # 根据启用状态设置按钮是否可用
        is_enabled = self.current_config_enabled and self.config_name
        self.multi_macro_tab.set_buttons_enabled(not is_enabled)
        self.single_macro_tab.set_buttons_enabled(not is_enabled)
        self.image_macro_tab.set_buttons_enabled(not is_enabled)
        any_enabled = bool(self.config_manager.enabled_configs)
        self.global_settings_tab.set_editable(not any_enabled)

    def check_hotkey_conflict(self, hotkey, source, exclude_skill_id=None):
        """检查热键冲突（在当前配置内）
        source: "multi" - 多键宏热键, "single" - 单键宏热键, "image" - 图像宏热键,
                "macro" - 宏序列按键, "image_skill" - 图像宏技能按键
        返回: (冲突类型, 配置文件名) 或 None
        """
        if not self.config_name:
            return None
        result = self.config_manager.check_hotkey_conflict(
            hotkey, source, self.current_config, exclude_skill_id=exclude_skill_id
        )
        if result:
            return (result[0], self.config_name)
        return None
    
    def check_cross_config_conflict(self, config_name):
        """检查跨配置的按键冲突（只检查已启用的配置）
        返回: True 表示有冲突，False 表示无冲突
        """
        return self.config_manager.check_cross_config_conflict(config_name)
    

    def on_multi_macro_config_changed(self):
        """多键宏配置更改时的处理"""
        multi_config = self.multi_macro_tab.get_config()
        self.current_config.update(multi_config)
        self.save_config()
        # 如果当前配置已启用，更新内存中的配置数据
        if self.config_name in self.config_manager.enabled_configs:
            self.config_manager.enabled_configs_data[self.config_name] = self.current_config.copy()
            self._rebuild_hotkey_maps()

    def on_single_macro_config_changed(self):
        """单键宏配置更改时的处理"""
        single_config = self.single_macro_tab.get_config()
        self.current_config["single_key_macro"] = single_config
        self.save_config()
        # 如果当前配置已启用，更新内存中的配置数据
        if self.config_name in self.config_manager.enabled_configs:
            self.config_manager.enabled_configs_data[self.config_name] = self.current_config.copy()
            self._rebuild_hotkey_maps()

    def on_image_macro_config_changed(self):
        """图像宏配置更改时的处理"""
        image_config = self.image_macro_tab.get_config()
        self.current_config["image_macro"] = image_config["image_macro"]
        self.save_config()
        if self.config_name in self.config_manager.enabled_configs:
            self.config_manager.enabled_configs_data[self.config_name] = self.current_config.copy()
            self._rebuild_hotkey_maps()

    def on_global_settings_changed(self):
        """全局参数更改时刷新主页"""
        try:
            if hasattr(self, 'home_tab') and self.home_tab:
                self.home_tab.load_data()
        except Exception:
            pass

    def new_config(self):
        """新建配置（默认未启用）"""
        dialog = NewConfigDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            name = dialog.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "提示", "配置名不能为空")
                return
            
            # 检查配置名是否已存在
            config_path = os.path.join(self.config_dir, f"{name}.json")
            if os.path.exists(config_path):
                QMessageBox.warning(self, "提示", f"配置 '{name}' 已存在")
                return
            
            # 创建包含所有设置的配置文件
            config_data = make_default_config(press_time=15)
            
            try:
                if self.config_manager.save_config(name, config_data):
                    # 设置新配置为当前配置（默认未启用）
                    self.config_name = name
                    self.current_config = config_data
                    self.current_config_enabled = False
                    
                    # 更新UI显示
                    self.update_ui()
                    
                    # 重新加载配置列表
                    self.load_configs()
                    
                    # 选中新创建的配置（在未启用列表中）
                    items = self.disabled_config_list.findItems(name, Qt.MatchExactly)
                    if items:
                        self.disabled_config_list.setCurrentItem(items[0])
                    
                    self.logger.info(f"新配置 {name} 创建成功（未启用）")
                else:
                    QMessageBox.critical(self, "错误", "创建配置失败")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建配置失败: {e}")

    def rename_config(self):
        """重命名配置"""
        # 获取当前选中的配置
        item = None
        if self.enabled_config_list.currentItem():
            item = self.enabled_config_list.currentItem()
        elif self.disabled_config_list.currentItem():
            item = self.disabled_config_list.currentItem()
        
        if not item:
            QMessageBox.warning(self, "提示", "请先新增配置或选择一个配置")
            return
        
        old_name = item.text()
        
        # 检查配置是否已启用，已启用的配置不能重命名
        if old_name in self.config_manager.enabled_configs:
            QMessageBox.warning(self, "提示", "启用中的配置不能重命名，请先禁用该配置")
            return
        dialog = RenameConfigDialog(self, old_name)
        if dialog.exec_() == QDialog.Accepted:
            new_name = dialog.name_edit.text().strip()
            if not new_name:
                QMessageBox.warning(self, "提示", "配置名不能为空")
                return
            
            if new_name == old_name:
                return
            
            # 检查新名称是否已存在
            new_config_path = os.path.join(self.config_dir, f"{new_name}.json")
            if os.path.exists(new_config_path):
                QMessageBox.warning(self, "提示", f"配置 '{new_name}' 已存在")
                return
            
            try:
                old_config_path = os.path.join(self.config_dir, f"{old_name}.json")
                if os.path.exists(old_config_path):
                    # 重命名文件
                    os.rename(old_config_path, new_config_path)

                    # 重命名资源目录并更新 JSON 内路径
                    rename_config_assets(self.config_dir, old_name, new_name)
                    with open(new_config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                    update_skill_paths_in_config(cfg, old_name, new_name)
                    with open(new_config_path, 'w', encoding='utf-8') as f:
                        json.dump(cfg, f, ensure_ascii=False, indent=2)
                    
                    # 如果原配置是启用的，更新启用列表
                    if old_name in self.config_manager.enabled_configs:
                        self.config_manager.enabled_configs.remove(old_name)
                        self.config_manager.enabled_configs.add(new_name)
                        self.config_manager.save_enabled_configs()
                    
                    # 如果当前配置是被重命名的，更新当前配置名
                    if self.config_name == old_name:
                        self.config_name = new_name
                    
                    # 重新加载配置列表
                    self.load_configs()
                    
                    # 选中重命名后的配置
                    if new_name in self.config_manager.enabled_configs:
                        items = self.enabled_config_list.findItems(new_name, Qt.MatchExactly)
                        if items:
                            self.enabled_config_list.setCurrentItem(items[0])
                            self.load_config(items[0])
                    else:
                        items = self.disabled_config_list.findItems(new_name, Qt.MatchExactly)
                        if items:
                            self.disabled_config_list.setCurrentItem(items[0])
                            self.load_config(items[0])
                    
                    self.logger.info(f"配置 '{old_name}' 已重命名为 '{new_name}'")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重命名配置失败: {e}")
    
    def toggle_config_enabled(self, item):
        """切换配置的启用/未启用状态"""
        if not item:
            return
        
        config_name = item.text()
        
        if config_name in self.config_manager.enabled_configs:
            # 当前是启用状态，切换为未启用
            self.config_manager.enabled_configs.remove(config_name)
            self.config_manager.save_enabled_configs()
            self.logger.info(f"配置 '{config_name}' 已禁用")
        else:
            # 当前是未启用状态，切换为启用
            # 先检查跨配置冲突
            has_conflict = self.check_cross_config_conflict(config_name)
            if has_conflict:
                # 使用配置管理器格式化冲突消息
                conflict_msg = self.config_manager.format_conflict_message()
                self.logger.warning(f"配置 '{config_name}' 启用失败：配置冲突")
                QMessageBox.warning(self, "配置冲突", conflict_msg)
                return
            
            self.config_manager.enabled_configs.add(config_name)
            self.config_manager.save_enabled_configs()
            self.logger.info(f"配置 '{config_name}' 已启用")
        
        # 重新加载配置列表
        self.load_configs()
        
        # 如果当前配置是被切换的配置，更新状态
        if self.config_name == config_name:
            self.flush_pending_save()
            self.current_config_enabled = config_name in self.config_manager.enabled_configs
            self.update_ui()
        
        # 重新加载已启用配置到运行环境
        self.reload_enabled_configs()
        # 刷新主页显示
        try:
            self.update_ui()
        except Exception:
            pass
    
    def reload_enabled_configs(self):
        """重新加载所有已启用的配置到运行环境"""
        # 停止所有正在运行的宏
        self.macro_executor.stop_all_macros()
        # 清空热键状态
        self.hotkey_manager.clear_hotkey_states()
        # 刷新已启用配置的数据和热键映射
        self.refresh_enabled_configs_data()
        self.logger.info("已重新加载启用配置到运行环境")
    
    def refresh_enabled_configs_data(self):
        """刷新已启用配置的数据到内存（配置变更时调用）"""
        self.config_manager.refresh_enabled_configs_data()
        self._rebuild_hotkey_maps()
    
    def _rebuild_hotkey_maps(self):
        """重建热键映射（键盘和鼠标）"""
        self.hotkey_manager.rebuild_hotkey_maps()
    
    def delete_config(self):
        """删除配置"""
        # 获取当前选中的配置
        item = None
        if self.enabled_config_list.currentItem():
            item = self.enabled_config_list.currentItem()
        elif self.disabled_config_list.currentItem():
            item = self.disabled_config_list.currentItem()
        
        if not item:
            QMessageBox.warning(self, "提示", "请先新增配置或选择一个配置")
            return
        
        name = item.text()
        
        # 检查配置是否已启用，已启用的配置不能删除
        if name in self.config_manager.enabled_configs:
            QMessageBox.warning(self, "提示", "启用中的配置不能删除，请先禁用该配置")
            return
        
        # 确认删除
        reply = QMessageBox.question(self, "确认删除", f"确定要删除配置 '{name}' 吗？", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        try:
            # 从启用列表中移除
            if name in self.config_manager.enabled_configs:
                self.config_manager.enabled_configs.remove(name)
                self.config_manager.save_enabled_configs()
                # 从内存中移除配置数据
                if name in self.config_manager.enabled_configs_data:
                    del self.config_manager.enabled_configs_data[name]
                    self._rebuild_hotkey_maps()
            
            # 删除配置文件
            config_path = os.path.join(self.config_dir, f"{name}.json")
            if os.path.exists(config_path):
                os.remove(config_path)

            delete_config_assets(self.config_dir, name)
            
            # 如果删除的是当前配置，清空当前配置并重置UI
            if self.config_name == name:
                self.config_name = ""
                self.current_config_enabled = False
                # 重置配置数据
                self.current_config = make_default_config()
                self.update_ui()
            
            # 重新加载配置列表
            self.load_configs()
            
            # 如果还有其他配置，自动加载第一个
            if self.config_name == "":
                if self.enabled_config_list.count() > 0:
                    self.enabled_config_list.setCurrentRow(0)
                    self.load_config(self.enabled_config_list.item(0))
                elif self.disabled_config_list.count() > 0:
                    self.disabled_config_list.setCurrentRow(0)
                    self.load_config(self.disabled_config_list.item(0))
            
            self.logger.info(f"配置 '{name}' 已删除")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除配置失败: {e}")
        finally:
            # 无论成功或失败都刷新主页数据和配置列表显示
            try:
                self.update_ui()
            except Exception:
                pass

    def save_config(self):
        """保存当前配置（防抖版本，避免频繁保存）
        
        优化：使用防抖机制，500ms内的多次保存请求只会执行最后一次
        """
        if not self.config_name:
            return
        
        # 标记需要保存
        self._pending_config_save = True
        
        # 500ms后执行保存（防抖）
        self._save_config_timer.start(500)

    def flush_pending_save(self):
        """切换配置或退出前，立即写入防抖队列中的待保存内容"""
        if self._save_config_timer.isActive():
            self._save_config_timer.stop()
        if self._pending_config_save:
            self._do_save_config()

    def save_config_immediate(self):
        """立即保存（跳过防抖，用于技能 CRUD 等关键操作）"""
        if not self.config_name:
            return False
        self._pending_config_save = True
        self._save_config_timer.stop()
        return self._do_save_config()
    
    def _do_save_config(self):
        """执行实际的配置保存（内部方法）"""
        if not self._pending_config_save:
            return False
        
        self._pending_config_save = False
        
        if not self.config_name:
            return False
            
        try:
            # 获取多键宏配置
            multi_config = self.multi_macro_tab.get_config()
            
            # 获取单键宏配置
            single_config = self.single_macro_tab.get_config()

            # 获取图像宏配置
            image_config = self.image_macro_tab.get_config()
            
            # 保存所有配置到单个文件（不包含window_focus）
            config_data = {
                "mode": multi_config["mode"],
                "macros": multi_config["macros"],
                "hotkey": multi_config["hotkey"],
                "single_key_macro": single_config,
                "image_macro": image_config["image_macro"],
            }
            
            if not self.config_manager.save_config(self.config_name, config_data):
                QMessageBox.critical(self, "错误", "保存失败")
                return False

            self.current_config = config_data
            skill_count = len(config_data.get("image_macro", {}).get("skills", []))
            self.logger.info(
                f"配置 '{self.config_name}' 已保存，图像宏技能数: {skill_count}"
            )
            return True
                
        except Exception as e:
            self.logger.exception(f"保存配置 '{self.config_name}' 失败")
            QMessageBox.critical(self, "错误", f"保存失败: {e}")
            return False
    
    def has_config(self):
        """检查是否有配置文件"""
        return self.config_name != ""

    def load_config_by_name(self, config_name):
        """根据配置名加载配置"""
        return self.config_manager.load_config_by_name(config_name)

    @property
    def enabled_configs(self):
        """获取已启用的配置集合（兼容性属性）"""
        return self.config_manager.enabled_configs

    def show_message(self, title, message):
        """显示消息（在UI线程中）"""
        QMessageBox.warning(self, title, message)


def main():
    import time
    start_time = time.time()

    request_admin_privileges()

    if not ensure_single_instance():
        sys.exit(0)

    load_global_settings()
    set_log_level(log_level_from_name(get_log_level()))

    logger = get_logger()
    logger.info("=" * 60)
    logger.info(f"TL_Macro v{APP_VERSION} 启动")
    logger.info("=" * 60)
    logger.info(f"日志级别: {get_current_log_level()}")
    logger.info(f"管理员权限: {'是' if is_admin() else '否'}")
    logger.info(f"截屏后端: {backend_label(get_backend())}")
    logger.info(f"图像宏扫描间隔: {get_scan_interval_ms()}ms")
    if get_global_mode():
        logger.info("焦点模式: 全局")
    else:
        logger.info(f"焦点模式: 窗口 ({get_processes()})")

    app = QApplication(sys.argv)
    font = QFont("微软雅黑", 9)
    app.setFont(font)

    icon_path = get_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    try:
        window = MacroTool()
        enabled = sorted(window.config_manager.enabled_configs)
        logger.info(f"已启用配置: {enabled if enabled else '(无)'}")
        window.show()
        logger.info("主窗口已显示")
        sys.exit(app.exec_())
    except Exception:
        logger.exception("程序运行出错")
        raise
    finally:
        elapsed = time.time() - start_time
        logger.info(f"TL_Macro 退出（运行 {elapsed:.1f}s）")


if __name__ == "__main__":
    main()