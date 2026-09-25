# -*- coding: utf-8 -*-
"""流程层 —— 「怎么走」：等待、循环、跳转、停止

流程步骤不产生输入，只改变执行指针。统一的返回值约定：

    None           继续执行下一步
    int            跳转到该下标
    Jump(target)   跳转到下标（等价于 int，语义更清楚）
    Stop(reason)   结束脚本运行
    StopAll        结束（默认原因）

循环用「开始/结束」配对表示，由运行时维护循环栈；
本模块只负责计算配对的结束位置与单次循环的推进。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Jump:
    """跳转到某个步骤下标。"""
    index: int


@dataclass
class Stop:
    """停止脚本。"""
    reason: str = "脚本主动停止"


@dataclass
class FlowResult:
    """流程处理结果。"""
    jump: Optional[int] = None
    stop: bool = False
    reason: str = ""


def is_flow_step(step_type: str) -> bool:
    return step_type in ("delay", "label", "goto", "stop",
                         "loop_begin", "loop_end")


# --------------------------------------------------------------------------
# 循环结构
# --------------------------------------------------------------------------

def find_loop_end(steps, start_pc: int) -> int:
    """找出与 steps[start_pc] 的「循环开始」配对的「循环结束」下标。

    支持嵌套（按深度配平）。找不到返回 -1。
    """
    depth = 1
    j = start_pc + 1
    total = len(steps)
    while j < total:
        t = steps[j].get("type")
        if t == "loop_begin":
            depth += 1
        elif t == "loop_end":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


class LoopFrame:
    """循环栈里的一帧。remaining 为剩余次数，0 且 declared!=0 表示该退出。"""

    __slots__ = ("start", "end", "remaining", "declared")

    def __init__(self, start: int, end: int, declared: int):
        self.start = start
        self.end = end
        self.declared = declared              # 0 = 无限循环
        self.remaining = 0 if declared == 0 else declared - 1

    @property
    def infinite(self) -> bool:
        return self.declared == 0

    def exhausted(self) -> bool:
        return (not self.infinite) and self.remaining <= 0

    def consume(self) -> None:
        if not self.infinite:
            self.remaining -= 1


def describe_loop(declared: int) -> str:
    return "无限" if declared == 0 else "%d 次" % declared


# --------------------------------------------------------------------------
# 流程步骤执行
# --------------------------------------------------------------------------

def handle(ctx, step, pc: int) -> Union[None, int, Jump, Stop]:
    """执行一个流程步骤。非流程步骤请交给动作层/触发层。"""
    t = step.get("type")

    if t == "delay":
        ctx.sleep(ctx.jitter(step.get("seconds"), step.get("random")))
        return None

    if t in ("label", "loop_begin", "loop_end"):
        return None

    if t == "goto":
        idx = ctx.label_index(str(step.get("name") or "").strip())
        return Jump(idx) if idx is not None else None

    if t == "stop":
        return Stop("脚本主动停止")

    return None
