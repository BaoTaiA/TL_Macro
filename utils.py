# -*- coding: utf-8 -*-
"""工具函数模块"""
import sys
import os
import ctypes
import gc
from logger import get_logger

_SINGLE_INSTANCE_MUTEX = None
_ERROR_ALREADY_EXISTS = 183

# 技能对话框等场景下暂停 EmptyWorkingSet，避免界面被“清掉”
_memory_cleanup_pause_count = 0


def pause_memory_cleanup():
    """暂停 cleanup_memory（可重入）"""
    global _memory_cleanup_pause_count
    _memory_cleanup_pause_count += 1


def resume_memory_cleanup():
    """恢复 cleanup_memory（可重入）"""
    global _memory_cleanup_pause_count
    if _memory_cleanup_pause_count > 0:
        _memory_cleanup_pause_count -= 1


def is_memory_cleanup_paused() -> bool:
    return _memory_cleanup_pause_count > 0


def ensure_single_instance() -> bool:
    """确保仅一个 TL_Macro 进程运行；若已有实例则弹窗提示并返回 False"""
    global _SINGLE_INSTANCE_MUTEX
    try:
        from version import APP_VERSION
        mutex_name = f"Global\\TL_Macro_SingleInstance_{APP_VERSION}"
    except Exception:
        mutex_name = "Global\\TL_Macro_SingleInstance"

    kernel32 = ctypes.windll.kernel32
    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, True, mutex_name)
    if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            None,
            "TL_Macro 已在运行中",
            "提示",
            0x30,
        )
        return False
    return True


def get_app_base_dir():
    """应用根目录：打包后为 exe 所在目录，开发时为项目根目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_icon_path():
    """应用图标路径（打包/开发环境均可用）"""
    base = get_app_base_dir()
    for rel in (
        os.path.join("_internal", "resource", "tl.ico"),
        os.path.join("resources", "tl.ico"),
    ):
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
    return os.path.join(base, "_internal", "resource", "tl.ico")


def is_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        get_logger().debug(f"检查管理员权限失败: {e}")
        return False


def request_admin_privileges():
    """请求管理员权限"""
    if not is_admin():
        # 重新以管理员权限启动程序
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)  # 退出当前实例


def cleanup_memory():
    """清理当前程序（宏软件）未使用的内存资源
    
    重要说明：此函数只清理当前程序的内存，不会影响系统其他程序或系统内存。
    
    执行以下操作（按奇游加速器原理实现）：
    1. Python 垃圾回收（强制回收当前进程的所有代）
    2. EmptyWorkingSet（强制清空工作集，将物理内存交换到虚拟内存）
    3. SetProcessWorkingSetSize（设置最小工作集，防止内存快速反弹）
    
    注意：
    - 只清理当前宏软件程序的内存，不影响其他程序
    - 不会影响程序功能，只是释放不再使用的物理内存
    - 虚拟内存仍然保留，程序可正常使用
    - 需要时系统会自动将页面从虚拟内存换回物理内存
    - 技能设置对话框打开期间应 pause_memory_cleanup，避免工作集强清导致界面消失
    """
    if is_memory_cleanup_paused():
        try:
            get_logger().debug("内存清理已暂停，跳过本次 cleanup_memory")
        except Exception:
            pass
        return

    try:
        # 1. Python 垃圾回收 - 强制回收当前进程的所有代
        # 先清理 Python 对象引用，为后续内存释放做准备
        collected = gc.collect()
        
        # 2. Windows 内存优化 - 仅针对当前进程
        try:
            kernel32 = ctypes.windll.kernel32
            # 获取当前进程句柄（只针对当前宏软件程序）
            # 方法1：使用 GetCurrentProcess（快速，但可能权限不足）
            process_handle = kernel32.GetCurrentProcess()
            
            # 方法2：使用 OpenProcess 获取有 PROCESS_SET_QUOTA 权限的句柄（更可靠）
            # PROCESS_SET_QUOTA = 0x0100, PROCESS_QUERY_INFORMATION = 0x0400
            need_close_handle = False
            try:
                current_pid = kernel32.GetCurrentProcessId()
                # 尝试打开进程，获取 PROCESS_SET_QUOTA 权限
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = kernel32.OpenProcess(
                    PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION,
                    False,  # bInheritHandle
                    current_pid
                )
                if handle:
                    # 如果成功打开，使用这个句柄（权限更完整）
                    process_handle = handle
                    need_close_handle = True  # 标记需要关闭
                # 如果失败，继续使用 GetCurrentProcess 返回的句柄
            except Exception:
                # 如果 OpenProcess 失败，继续使用 GetCurrentProcess 的句柄
                pass
            
            # 2.1 EmptyWorkingSet - 强制清空工作集（最关键，效果最明显）
            # 注意：EmptyWorkingSet 在 psapi.dll 中，不在 kernel32.dll
            # 将进程工作集中的所有内存页面标记为可交换
            # 系统会将物理内存页面交换到虚拟内存（磁盘）
            # 这是实现 80MB -> 20MB 效果的关键
            empty_working_set_success = False
            try:
                # 从 psapi.dll 加载 EmptyWorkingSet
                psapi = ctypes.windll.psapi
                # EmptyWorkingSet 函数签名：BOOL EmptyWorkingSet(HANDLE hProcess)
                # 返回非零表示成功，0 表示失败
                result = psapi.EmptyWorkingSet(process_handle)
                if result:
                    # 成功执行
                    empty_working_set_success = True
                else:
                    # 获取错误码（用于调试）
                    error_code = kernel32.GetLastError()
                    logger = get_logger()
                    logger.warning(f"EmptyWorkingSet 失败，错误码: {error_code}")
                    # 错误码 5 = 拒绝访问，可能需要 PROCESS_SET_QUOTA 权限
                    # 错误码 87 = 参数无效
            except AttributeError:
                # 如果 psapi 中没有 EmptyWorkingSet，尝试 kernel32（某些系统版本）
                try:
                    result = kernel32.EmptyWorkingSet(process_handle)
                    if result:
                        empty_working_set_success = True
                    else:
                        error_code = kernel32.GetLastError()
                        logger = get_logger()
                        logger.warning(f"EmptyWorkingSet (kernel32) 失败，错误码: {error_code}")
                except AttributeError:
                    logger = get_logger()
                    logger.warning("系统不支持 EmptyWorkingSet API")
            except Exception as e:
                logger = get_logger()
                logger.error(f"EmptyWorkingSet 调用异常: {e}", exc_info=True)
            
            # 2.2 SetProcessWorkingSetSize - 设置最小工作集
            # 设置最小工作集大小，防止内存快速反弹，保持较低的物理内存占用
            # 参数说明：
            #   hProcess: 进程句柄
            #   dwMinimumWorkingSetSize: 最小工作集大小（-1 = 系统最小值）
            #   dwMaximumWorkingSetSize: 最大工作集大小（-1 = 系统最大值，不限制）
            try:
                # 设置最小工作集，强制系统保持较小的物理内存占用
                # 使用 -1 表示使用系统默认的最小/最大值
                # 这会让系统尽量保持较小的物理内存占用
                result = kernel32.SetProcessWorkingSetSize(
                    process_handle, 
                    -1,  # 最小工作集：系统最小值
                    -1   # 最大工作集：系统最大值（不限制）
                )
            except Exception as e:
                # 如果设置失败，不影响程序运行
                pass
            
            # 如果使用了 OpenProcess 打开的句柄，需要关闭它
            if need_close_handle:
                try:
                    kernel32.CloseHandle(process_handle)
                except Exception:
                    pass
                
        except Exception as e:
            # 如果 Windows API 调用失败，不影响程序运行
            pass
        
        # 打印清理信息
        logger = get_logger()
        if empty_working_set_success:
            logger.debug(f"内存清理完成，回收了 {collected} 个对象，EmptyWorkingSet 执行成功")
        else:
            logger.debug(f"内存清理完成，回收了 {collected} 个对象，EmptyWorkingSet 执行失败（可能无权限或系统不支持）")
        
    except Exception as e:
        # 清理失败不应该影响程序运行
        logger = get_logger()
        logger.warning(f"内存清理时出现错误（不影响程序运行）: {e}", exc_info=True)


def validate_time_input(sender, min_value=1, max_value=9999, default_value=15):
    """验证时间输入（用于 QSpinBox）
    
    Args:
        sender: QSpinBox 对象（通过 self.sender() 获取）
        min_value: 最小值，默认 1
        max_value: 最大值，默认 9999
        default_value: 无效值时的默认值，默认 15
    
    Returns:
        bool: 如果值有效返回 True，否则返回 False
    """
    if sender is None:
        return False
    
    value = sender.value()
    if value < min_value or value > max_value:
        # 自动恢复为默认值
        sender.setValue(default_value)
        return False
    return True


# 宏执行模式文本映射
MULTI_MACRO_MODE_TEXT = {
    1: "循环执行（再次按下停止）",
    2: "执行一次",
    3: "循环执行（松开停止）"
}

SINGLE_MACRO_MODE_TEXT = {
    1: "循环执行（再次按下停止）",
    2: "循环执行（松开停止）"
}

IMAGE_MACRO_MODE_TEXT = {
    1: "循环扫描（再次按下停止）",
    3: "循环扫描（松开停止）",
}


def get_multi_macro_mode_text(mode):
    """获取多键宏模式文本
    
    Args:
        mode: 模式编号 (1, 2, 3)
    
    Returns:
        str: 模式文本描述
    """
    return MULTI_MACRO_MODE_TEXT.get(mode, f"模式{mode}")


def get_single_macro_mode_text(mode):
    """获取单键宏模式文本
    
    Args:
        mode: 模式编号 (1, 2)
    
    Returns:
        str: 模式文本描述
    """
    return SINGLE_MACRO_MODE_TEXT.get(mode, f"模式{mode}")


def get_image_macro_mode_text(mode):
    """获取图像宏模式文本"""
    return IMAGE_MACRO_MODE_TEXT.get(mode, f"模式{mode}")
