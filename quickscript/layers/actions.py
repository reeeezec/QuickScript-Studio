# -*- coding: utf-8 -*-
"""动作层 —— 「做什么」：鼠标与键盘的原子动作

每个动作只关心自己的参数和物理操作，不关心流程（那是流程层的职责），
也不关心绑定的是哪个窗口（坐标换算是目标层提供的）。

动作统一接口：
    perform(ctx, step, target) -> None
        ctx     执行上下文（提供 mouse/keyboard/sleep/log/jitter 等）
        step    该步骤的参数字典
        target  已解析的目标（用于坐标换算）

新增一种动作只要：
    1. 在 STEP_SPECS 里加字段定义（model.py）
    2. 写一个函数并用 @action("类型名") 注册
"""
from __future__ import annotations

from ..platform import wininput as wi


class ActionError(RuntimeError):
    """动作执行失败（参数非法、或被系统拦截）。"""


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------

ACTIONS = {}


def action(step_type: str):
    """把一个函数注册成动作处理器。"""
    def deco(fn):
        ACTIONS[step_type] = fn
        return fn
    return deco


def get(step_type: str):
    return ACTIONS.get(step_type)


def registered_types():
    return sorted(ACTIONS)


# --------------------------------------------------------------------------
# 鼠标动作
# --------------------------------------------------------------------------

@action("move")
def do_move(ctx, step, target):
    """把鼠标移动到指定点。"""
    sx, sy = target.to_screen(step.get("x", 0), step.get("y", 0))
    ctx.mouse.move_to(sx, sy,
                      float(step.get("duration") or 0), None,
                      int(step.get("jitter") or 0))


@action("click")
def do_click(ctx, step, target):
    """移动到目标点并点击，可控制按下时长/次数/连击间隔。"""
    sx, sy = target.to_screen(step.get("x", 0), step.get("y", 0))
    move_time = float(step.get("move_time") or 0)
    if move_time > 0:
        ctx.mouse.move_to(sx, sy, move_time)
    else:
        ctx.mouse.move_instant(sx, sy)

    button = step.get("button") or "left"
    hold = ctx.jitter(step.get("hold"), ctx.script.hold_jitter)
    clicks = int(step.get("clicks") or 1)
    interval = ctx.jitter(step.get("interval"), ctx.script.delay_jitter)

    ctx.hold_button(button)
    try:
        ctx.mouse.click(button, hold, clicks, interval)
    finally:
        ctx.release_button(button)

    if ctx.script.move_after_click > 0:
        ctx.sleep(ctx.jitter(ctx.script.move_after_click, ctx.script.delay_jitter))


@action("drag")
def do_drag(ctx, step, target):
    """按下 -> 沿路径移动 -> 松开。"""
    x1, y1 = target.to_screen(step.get("x1", 0), step.get("y1", 0))
    x2, y2 = target.to_screen(step.get("x2", 0), step.get("y2", 0))
    button = step.get("button") or "left"
    ctx.hold_button(button)
    try:
        ctx.mouse.drag(x1, y1, x2, y2,
                       float(step.get("duration") or 0.3),
                       int(step.get("steps") or 0) or None,
                       button,
                       int(step.get("jitter") or 0))
    finally:
        ctx.release_button(button)


@action("wheel")
def do_wheel(ctx, step, target):
    """滚动滚轮。正数向上。"""
    times = max(1, int(step.get("times") or 1))
    amount = int(step.get("amount") or 1)
    for i in range(times):
        if ctx.stopped():
            break
        ctx.mouse.wheel(amount)
        if i < times - 1:
            ctx.sleep(ctx.jitter(step.get("interval"), ctx.script.delay_jitter))


# --------------------------------------------------------------------------
# 键盘动作
# --------------------------------------------------------------------------

@action("key")
def do_key(ctx, step, target):
    """按一次键（支持组合键），可连按、可保持按住。"""
    combo = str(step.get("keys") or "")
    if not combo.strip():
        raise ActionError("按键为空")

    if step.get("no_release"):
        mods, main = wi.parse_combo(combo)
        for m in mods:
            ctx.keyboard.key_down(m)
        ctx.keyboard.key_down(main)
        ctx.hold_key(combo)
        ctx.log("info", "持续按住 [%s]" % combo)
        return

    times = max(1, int(step.get("times") or 1))
    hold = ctx.jitter(step.get("hold"), ctx.script.hold_jitter)
    for i in range(times):
        if ctx.stopped():
            break
        ctx.keyboard.press(combo, hold)
        if i < times - 1:
            ctx.sleep(ctx.jitter(step.get("interval"), ctx.script.delay_jitter))


@action("key_down")
def do_key_down(ctx, step, target):
    """按住不放（配合「松开按键」使用）。"""
    combo = str(step.get("keys") or "")
    mods, main = wi.parse_combo(combo)
    for m in mods:
        ctx.keyboard.key_down(m)
    ctx.keyboard.key_down(main)
    ctx.hold_key(combo)


@action("key_up")
def do_key_up(ctx, step, target):
    """松开之前按住的键。"""
    combo = str(step.get("keys") or "")
    ctx.keyboard.release(combo)
    ctx.release_key(combo)
