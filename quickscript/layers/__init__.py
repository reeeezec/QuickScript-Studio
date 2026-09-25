# -*- coding: utf-8 -*-
"""四层架构。

    actions   动作层 —— 产生输入（鼠标 / 键盘）
    flow      流程层 —— 控制走向（等待 / 循环 / 跳转 / 停止）
    triggers  触发层 —— 条件分支（找色 / 找图）
    target    目标层 —— 绑定谁、坐标怎么算

依赖方向是单向的：actions / flow / triggers 都只依赖 target 抽象与执行上下文，
彼此不互相调用；由 runtime 负责组合。这样各层可以独立测试与替换。
"""
from __future__ import annotations

from . import actions, flow, triggers, target

__all__ = ["actions", "flow", "triggers", "target"]
