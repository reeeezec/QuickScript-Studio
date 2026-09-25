# -*- coding: utf-8 -*-
"""触发层 —— 「什么条件下做分支」：找色、找图

触发步骤本身不产生输入，只做一次判断，然后按配置分支：
    命中 / 未命中  →  继续 / 跳转到标签 / 停止脚本

判断所需的屏幕内容由目标层决定截取范围（窗口相对模式只截客户区）。
"""
from __future__ import annotations

import os

from ..platform import vision
from ..platform import wininput as wi
from .flow import Jump, Stop

# 分支动作
CONTINUE = "continue"
GOTO = "goto"
STOP = "stop"

BRANCH_ACTIONS = (CONTINUE, GOTO, STOP)

BRANCH_LABELS = {
    CONTINUE: "继续",
    GOTO: "跳转",
    STOP: "停止脚本",
}


def _parse_region(raw):
    """解析 'x,y,w,h' 形式的搜索区域，非法返回 None。"""
    raw = str(raw or "").strip()
    if not raw:
        return None
    try:
        nums = [int(float(v)) for v in
                raw.replace("，", ",").replace(" ", ",").split(",") if v.strip()]
        if len(nums) == 4:
            return tuple(nums)
    except Exception:
        return None
    return None


def _branch(ctx, step, hit):
    """根据命中与否决定后续走向。"""
    action = step.get("on_success" if hit else "on_fail") or CONTINUE
    if action == STOP:
        return Stop("条件判断主动停止")
    if action == GOTO:
        name = str(step.get("success_label" if hit else "fail_label") or "").strip()
        idx = ctx.label_index(name)
        if idx is None:
            return None
        ctx.log("info", "条件跳转 → 标签 <%s>（第 %d 步）" % (name, idx + 1))
        return Jump(idx)
    return None


# --------------------------------------------------------------------------
# 找色
# --------------------------------------------------------------------------

def check_color(ctx, step, target) -> bool:
    """判断某点颜色是否符合预期。返回是否命中。"""
    x = int(step.get("x") or 0)
    y = int(step.get("y") or 0)
    sx, sy = target.to_screen(x, y)
    tol = int(step.get("tol") or 0)

    try:
        px = wi.pixel_color(sx, sy)
    except Exception:
        px = None

    if px is None:
        ctx.log("warn", "找色 (%d,%d)：取色失败" % (x, y))
        return False

    want = vision.parse_color(step.get("color"))
    hit = (abs(px[0] - want[0]) <= tol and abs(px[1] - want[1]) <= tol
           and abs(px[2] - want[2]) <= tol)
    ctx.log("ok" if hit else "info",
            "找色 (%d,%d)：%s  实际 %s / 目标 %s（容差 %d）" % (
                x, y, "命中" if hit else "未命中",
                vision.color_to_hex(px), vision.color_to_hex(want), tol))
    return hit


# --------------------------------------------------------------------------
# 找图
# --------------------------------------------------------------------------

def check_image(ctx, step, target) -> bool:
    """在画面上查找模板图片。返回是否命中。"""
    path = str(step.get("image") or "").strip()
    if not path or not os.path.isfile(path):
        ctx.log("error", "模板图片不存在：%s" % (path or "(空)"))
        return False

    try:
        tw, th, tbuf = vision.load_image(path)
    except vision.VisionError as exc:
        ctx.log("error", "模板图片读取失败：%s" % exc)
        return False

    region = _parse_region(step.get("region"))
    if step.get("region") and region is None:
        ctx.log("warn", "搜索区域格式应为 x,y,w,h：%s" % step.get("region"))

    try:
        w, h, buf, origin = ctx.grab(region)
    except Exception as exc:
        ctx.log("error", "截图失败：%s" % exc)
        return False

    found = vision.find_image(w, h, buf, (tw, th, tbuf),
                              int(step.get("tol") or 12), None, 1)
    need = float(step.get("similarity") or 1.0)
    hit = bool(found) and found[0][2] + 1e-9 >= need

    name = os.path.basename(path)
    if found:
        lx, ly, score = found[0]
        rx, ry = target.to_script(origin[0] + lx, origin[1] + ly)
        ctx.log("ok" if hit else "info",
                "找图 [%s]：匹配度 %.1f%%（要求 %.0f%%）→ %s，位置 脚本坐标(%d,%d)" % (
                    name, score * 100, need * 100,
                    "命中" if hit else "未达标", rx, ry))
    else:
        ctx.log("info", "找图 [%s]：未命中" % name)
    return hit


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------

def handle(ctx, step, target):
    """执行触发步骤，返回分支结果（None / Jump / Stop）。"""
    t = step.get("type")
    if t == "if_color":
        return _branch(ctx, step, check_color(ctx, step, target))
    if t == "if_image":
        return _branch(ctx, step, check_image(ctx, step, target))
    return None


def is_trigger_step(step_type: str) -> bool:
    return step_type in ("if_color", "if_image")
