# -*- coding: utf-8 -*-
"""兼容层 —— 让旧界面代码平滑迁移到新的分层架构。

界面（ui.py）正在逐步改用 quickscript.* 的正式接口；在迁移完成前，
这里提供一组与旧 engine/store/vision/win_input 同名的别名，
避免一次性大改带来的风险。

新代码请直接 import quickscript.model / runtime / storage / platform，
不要依赖本模块。
"""
from __future__ import annotations

# 数据模型
from .model import (  # noqa: F401
    Script, ScriptError, STEP_SPECS, GROUP_ORDER, NOTE_KEY, NOTE_MAX_LEN,
    VALID_NAME, DEFAULT_SCRIPT_NAME, MAX_TOTAL_STEPS,
    new_step, step_summary, step_note, clean_note, step_display,
    split_display, short_label, step_layer, steps_in_layer,
    RunSettings, LAYER_ACTION, LAYER_FLOW, LAYER_TRIGGER, LAYER_LABELS,
    detect_version, migrate,
)

# 执行引擎
from .runtime import Runner, LogLevel  # noqa: F401

# 目标层（坐标空间）
from .layers.target import (  # noqa: F401
    TargetResolver, TargetSpec, BoundTarget, SCREEN, WINDOW, COORD_MODES, MODE_LABELS,
)


class CoordSpace:
    """旧接口兼容：包装 TargetResolver。

    旧代码用它做坐标换算与「描述当前绑定状态」。
    """

    def __init__(self, script):
        self.script = script
        self._resolver = TargetResolver(script.target)
        self._bound = self._resolver.bound

    def refresh(self, activate=False):
        self._resolver.spec = self.script.target
        ok = self._resolver.refresh(activate=activate)
        self._bound = self._resolver.bound
        return ok

    @property
    def hwnd(self):
        return self._bound.hwnd

    @property
    def client_origin(self):
        return self._bound.client_origin

    @property
    def client_size(self):
        return self._bound.client_size

    @property
    def base(self):
        return self._bound.origin

    def to_screen(self, x, y):
        return self._bound.to_screen(x, y)

    def to_script(self, sx, sy):
        return self._bound.to_script(sx, sy)

    def describe(self, script_window=True):
        return self._bound.describe()
