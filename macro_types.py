# -*- coding: utf-8 -*-
"""宏执行器共享类型定义"""
import threading
from enum import Enum
from typing import List, Optional


IMAGE_MACRO_FIRE_STOP = object()


class MacroState(Enum):
    """宏执行状态枚举"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MacroType(Enum):
    """宏类型枚举"""
    MULTI = "multi"
    SINGLE = "single"
    IMAGE = "image"


class MacroInfo:
    """宏信息类 - 封装宏的所有状态信息"""

    def __init__(self, config_name: str, macro_type: MacroType):
        self.config_name = config_name
        self.macro_type = macro_type
        self.state = MacroState.IDLE
        self.thread: Optional[threading.Thread] = None
        self.threads: List[threading.Thread] = []
        self.stop_event = threading.Event()
        self.start_time: Optional[float] = None
        self.stop_time: Optional[float] = None
        self.error_message: Optional[str] = None
        self.iteration_count = 0
        self._iteration_lock = threading.Lock()
        self.lock = threading.RLock()

    def bump_iteration(self):
        with self._iteration_lock:
            self.iteration_count += 1

    def any_worker_alive(self) -> bool:
        workers = list(self.threads) if self.threads else (
            [self.thread] if self.thread else []
        )
        return any(t and t.is_alive() for t in workers)

    def is_running(self) -> bool:
        with self.lock:
            return self.state in (MacroState.STARTING, MacroState.RUNNING)

    def is_stopped(self) -> bool:
        with self.lock:
            return self.state in (MacroState.STOPPED, MacroState.ERROR)

    def set_state(self, new_state: MacroState, error_msg: Optional[str] = None):
        with self.lock:
            old_state = self.state
            self.state = new_state
            if error_msg:
                self.error_message = error_msg
            return old_state
