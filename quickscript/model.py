# -*- coding: utf-8 -*-
"""QuickScript Studio —— 脚本数据模型与格式定义

一份脚本 = 元信息 + 目标设置 + 一组有序步骤。

步骤按**四层**组织，每层职责单一：

    动作层 (action)   产生输入：鼠标移动/点击/拖动/滚轮，键盘按键
    流程层 (flow)     控制走向：等待、循环、跳转、停止
    触发层 (trigger)  条件分支：找色、找图
    目标层 (target)   不体现在步骤里，而是脚本级设置 —— 绑定哪个窗口、坐标怎么算
                      （见 layers/target.py）

文件格式
--------
带 version 字段的 JSON：

    {
      "version": 2,
      "name": "脚本名",
      "target": { "coord_mode": "window", ... },
      "settings": { "start_delay": 1.0, ... },
      "steps": [ { "type": "click", "x": 100, "y": 200, "note": "..." } ]
    }

旧版本（schema:1，配置平铺在根节点）会在载入时自动迁移到 v2。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

from .metadata import SCRIPT_FORMAT_VERSION
from .layers import actions, flow, triggers
from .layers.target import TargetSpec, COORD_MODES, WINDOW
from .platform import wininput as wi
from .platform import vision

# 兼容别名：外部（UI/测试）用 model.Script / model.STEP_SPECS
DEFAULT_SCRIPT_NAME = "未命名脚本"
VALID_NAME = DEFAULT_SCRIPT_NAME          # 旧名，保留兼容
MAX_TOTAL_STEPS = 300000          # 死循环保护
NOTE_KEY = "note"
NOTE_MAX_LEN = 300

# 步骤所属的层
LAYER_ACTION = "action"
LAYER_FLOW = "flow"
LAYER_TRIGGER = "trigger"

LAYER_LABELS = {
    LAYER_ACTION: "动作层",
    LAYER_FLOW: "流程层",
    LAYER_TRIGGER: "触发层",
}


# --------------------------------------------------------------------------
# 字段定义
# --------------------------------------------------------------------------

def F(key, label, kind="float", default=0, **kw):
    d = {"key": key, "label": label, "kind": kind, "default": default}
    d.update(kw)
    return d


# 步骤类型 -> 定义。UI 与执行引擎共用，保证界面显示与实际执行永远一致。
STEP_SPECS = {
    # ---------------- 动作层：鼠标 ----------------
    "move": {
        "label": "移动鼠标", "icon": "➤", "group": "鼠标", "layer": LAYER_ACTION,
        "fields": [
            F("x", "X", "int", 0),
            F("y", "Y", "int", 0),
            F("duration", "移动耗时(秒)", "float", 0.15, min=0, max=30, step=0.01),
            F("jitter", "抖动(像素)", "int", 0, min=0, max=200),
        ],
    },
    "click": {
        "label": "点击", "icon": "●", "group": "鼠标", "layer": LAYER_ACTION,
        "fields": [
            F("x", "X", "int", 0),
            F("y", "Y", "int", 0),
            F("button", "鼠标键", "choice", "left",
              choices=["left", "right", "middle", "x1", "x2"],
              choice_labels={"left": "左键", "right": "右键", "middle": "中键",
                             "x1": "侧键1", "x2": "侧键2"}),
            F("hold", "按下时长(秒)", "float", 0.05, min=0.001, max=60, step=0.005),
            F("clicks", "点击次数", "int", 1, min=1, max=1000),
            F("interval", "连击间隔(秒)", "float", 0.08, min=0, max=60, step=0.005),
            F("move_time", "移动耗时(秒)", "float", 0.12, min=0, max=30, step=0.01,
              help="从当前位置移到目标点的耗时，0 = 瞬移"),
        ],
    },
    "drag": {
        "label": "拖动", "icon": "✥", "group": "鼠标", "layer": LAYER_ACTION,
        "fields": [
            F("x1", "起点X", "int", 0), F("y1", "起点Y", "int", 0),
            F("x2", "终点X", "int", 0), F("y2", "终点Y", "int", 0),
            F("button", "鼠标键", "choice", "left",
              choices=["left", "right", "middle"],
              choice_labels={"left": "左键", "right": "右键", "middle": "中键"}),
            F("duration", "拖动耗时(秒)", "float", 0.3, min=0.01, max=60, step=0.01),
            F("steps", "步数(0=自动)", "int", 0, min=0, max=5000),
            F("jitter", "抖动(像素)", "int", 0, min=0, max=200),
        ],
    },
    "wheel": {
        "label": "滚轮", "icon": "↕", "group": "鼠标", "layer": LAYER_ACTION,
        "fields": [
            F("amount", "滚动格数(正=上)", "int", 1, min=-100, max=100),
            F("times", "次数", "int", 1, min=1, max=1000),
            F("interval", "间隔(秒)", "float", 0.05, min=0, max=60, step=0.005),
        ],
    },
    # ---------------- 动作层：键盘 ----------------
    "key": {
        "label": "按键", "icon": "⌨", "group": "键盘", "layer": LAYER_ACTION,
        "fields": [
            F("keys", "按键(组合用+)", "str", "space",
              help="例：space / ctrl+shift+a / a / F1 / 空格 / 回车"),
            F("hold", "按住时长(秒)", "float", 0.05, min=0.001, max=600, step=0.005),
            F("times", "次数", "int", 1, min=1, max=10000),
            F("interval", "间隔(秒)", "float", 0.1, min=0, max=600, step=0.005),
            F("no_release", "结束时保持按住", "bool", False),
        ],
    },
    "key_down": {
        "label": "按住不放", "icon": "⬇", "group": "键盘", "layer": LAYER_ACTION,
        "fields": [F("keys", "按键(组合用+)", "str", "space")],
    },
    "key_up": {
        "label": "松开按键", "icon": "⬆", "group": "键盘", "layer": LAYER_ACTION,
        "fields": [F("keys", "按键(组合用+)", "str", "space")],
    },
    # ---------------- 流程层 ----------------
    "delay": {
        "label": "等待", "icon": "⏱", "group": "流程", "layer": LAYER_FLOW,
        "fields": [
            F("seconds", "秒", "float", 0.5, min=0, max=3600, step=0.01),
            F("random", "额外随机(±秒)", "float", 0, min=0, max=60, step=0.01),
        ],
    },
    "loop_begin": {
        "label": "循环开始", "icon": "🔁", "group": "流程", "layer": LAYER_FLOW,
        "fields": [F("times", "循环次数(0=无限)", "int", 0, min=0, max=1000000)],
    },
    "loop_end": {
        "label": "循环结束", "icon": "🔚", "group": "流程", "layer": LAYER_FLOW,
        "fields": [],
    },
    "label": {
        "label": "标签", "icon": "🏷", "group": "流程", "layer": LAYER_FLOW,
        "fields": [F("name", "标签名", "str", "标记1")],
    },
    "goto": {
        "label": "跳转", "icon": "↪", "group": "流程", "layer": LAYER_FLOW,
        "fields": [F("name", "目标标签", "str", "标记1")],
    },
    "stop": {
        "label": "停止脚本", "icon": "⏹", "group": "流程", "layer": LAYER_FLOW,
        "fields": [],
    },
    # ---------------- 触发层 ----------------
    "if_color": {
        "label": "如果某点颜色符合", "icon": "🎯", "group": "条件", "layer": LAYER_TRIGGER,
        "fields": [
            F("x", "X", "int", 0), F("y", "Y", "int", 0),
            F("color", "颜色", "color", "#FF0000", help="#RRGGBB 或 r,g,b"),
            F("tol", "容差", "int", 10, min=0, max=255),
            F("on_success", "命中 →", "choice", "continue",
              choices=["continue", "goto", "stop"],
              choice_labels=triggers.BRANCH_LABELS),
            F("success_label", "命中跳转标签", "str", ""),
            F("on_fail", "未命中 →", "choice", "continue",
              choices=["continue", "goto", "stop"],
              choice_labels=triggers.BRANCH_LABELS),
            F("fail_label", "未命中跳转标签", "str", ""),
        ],
    },
    "if_image": {
        "label": "如果画面上有图片", "icon": "🔍", "group": "条件", "layer": LAYER_TRIGGER,
        "fields": [
            F("image", "模板图片", "image", ""),
            F("tol", "颜色容差", "int", 12, min=0, max=255),
            F("similarity", "最低匹配度", "float", 0.98, min=0.3, max=1.0, step=0.01),
            F("region", "搜索区域(x,y,w,h)", "region", "",
              help="留空 = 搜索整个画面。区域越小，找图越快越准。"),
            F("on_success", "命中 →", "choice", "continue",
              choices=["continue", "goto", "stop"],
              choice_labels=triggers.BRANCH_LABELS),
            F("success_label", "命中跳转标签", "str", ""),
            F("on_fail", "未命中 →", "choice", "continue",
              choices=["continue", "goto", "stop"],
              choice_labels=triggers.BRANCH_LABELS),
            F("fail_label", "未命中跳转标签", "str", ""),
        ],
    },
}

# 界面上分组的显示顺序
GROUP_ORDER = ["鼠标", "键盘", "流程", "条件"]

# 工具箱按钮上的短标签（完整名称太长会撑破左侧面板）
SHORT_LABELS = {
    "if_color": "如果某点颜色符合…",
    "if_image": "如果画面上有图片…",
    "loop_begin": "循环开始",
    "drag": "拖动",
    "key_down": "按住不放",
    "key_up": "松开按键",
    "wheel": "滚轮",
}


def short_label(step_type: str) -> str:
    return SHORT_LABELS.get(step_type, STEP_SPECS[step_type]["label"])


def step_layer(step_type: str) -> str:
    return STEP_SPECS.get(step_type, {}).get("layer", LAYER_FLOW)


def steps_in_layer(layer: str):
    return [t for t, s in STEP_SPECS.items() if s.get("layer") == layer]


# --------------------------------------------------------------------------
# 备注
# --------------------------------------------------------------------------

def clean_note(value) -> str:
    """规整备注文本：去掉首尾空白、换行压成空格、限制长度。"""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(line.strip() for line in text.split("\n"))
    text = text.strip()
    if len(text) > NOTE_MAX_LEN:
        text = text[:NOTE_MAX_LEN]
    return text


def step_note(step: dict) -> str:
    return clean_note(step.get(NOTE_KEY))


def new_step(step_type: str, x=None, y=None) -> dict:
    """创建一个带默认值的步骤。"""
    if step_type not in STEP_SPECS:
        raise ScriptError("未知步骤类型：%s" % step_type)
    spec = STEP_SPECS[step_type]
    step = {"type": step_type, NOTE_KEY: ""}
    for f in spec["fields"]:
        step[f["key"]] = f["default"]
    if x is not None:
        if "x" in step:
            step["x"] = int(x)
        if "x1" in step:
            step["x1"] = int(x)
    if y is not None:
        if "y" in step:
            step["y"] = int(y)
        if "y1" in step:
            step["y1"] = int(y)
    return step


# --------------------------------------------------------------------------
# 人类可读摘要
# --------------------------------------------------------------------------

def step_summary(step: dict) -> str:
    t = step.get("type")
    spec = STEP_SPECS.get(t)
    base = spec["label"] if spec else str(t)
    try:
        if t == "move":
            return "%s → (%s, %s)  耗时 %.2fs" % (
                base, step["x"], step["y"], float(step["duration"]))
        if t == "click":
            labels = spec["fields"][2]["choice_labels"]
            return "%s %s (%s, %s)  按下 %.3fs ×%s" % (
                base, labels.get(step.get("button"), step.get("button")),
                step["x"], step["y"], float(step["hold"]), step.get("clicks", 1))
        if t == "drag":
            return "%s (%s,%s) → (%s,%s)  %.2fs" % (
                base, step["x1"], step["y1"], step["x2"], step["y2"],
                float(step["duration"]))
        if t == "wheel":
            return "%s %s 格 ×%s" % (base, step["amount"], step.get("times", 1))
        if t == "key":
            extra = "  结束时保持按住" if step.get("no_release") else ""
            return "%s [%s]  按下 %.3fs ×%s%s" % (
                base, step["keys"], float(step["hold"]), step.get("times", 1), extra)
        if t in ("key_down", "key_up"):
            return "%s [%s]" % (base, step["keys"])
        if t == "delay":
            r = float(step.get("random") or 0)
            return "%s %.2fs%s" % (base, float(step["seconds"]),
                                   ("  ±%.2fs" % r) if r else "")
        if t == "loop_begin":
            n = int(step.get("times") or 0)
            return "%s ×%s" % (base, "无限" if n == 0 else n)
        if t == "if_color":
            return "%s (%s,%s) = %s  容差%s" % (
                base, step["x"], step["y"], step["color"], step.get("tol"))
        if t == "if_image":
            name = os.path.basename(str(step.get("image") or "")) or "(未选择图片)"
            return "%s [%s]" % (base, name)
        if t in ("label", "goto"):
            return "%s <%s>" % (base, step.get("name"))
    except Exception:
        return base
    return base


def step_display(step: dict) -> str:
    """列表里显示的一整行：摘要 + 备注。"""
    summary = step_summary(step)
    note = step_note(step)
    return "%s    📝 %s" % (summary, note) if note else summary


def split_display(text: str):
    if "    📝 " in text:
        left, right = text.split("    📝 ", 1)
        return left, right
    return text, ""


class ScriptError(Exception):
    pass


# --------------------------------------------------------------------------
# 脚本级设置（运行节奏）
# --------------------------------------------------------------------------

@dataclass
class RunSettings:
    """影响整体节奏的设置，用来让操作更自然、也给目标程序留出响应时间。"""

    start_delay: float = 1.0        # 按下运行后的准备时间
    hold_jitter: float = 0.0        # 按下时长随机浮动 ±秒
    delay_jitter: float = 0.0       # 间隔随机浮动 ±秒
    move_after_click: float = 0.0   # 每次点击后额外停顿

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunSettings":
        data = data or {}
        return cls(
            start_delay=float(data.get("start_delay", 1.0) or 0),
            hold_jitter=float(data.get("hold_jitter", 0) or 0),
            delay_jitter=float(data.get("delay_jitter", 0) or 0),
            move_after_click=float(data.get("move_after_click", 0) or 0),
        )


# --------------------------------------------------------------------------
# 脚本
# --------------------------------------------------------------------------

class Script:
    """一份完整的脚本。"""

    def __init__(self, name: str = DEFAULT_SCRIPT_NAME):
        self.name = name
        self.target = TargetSpec()
        self.settings = RunSettings()
        self.steps: list = []

    # -- 便捷属性（兼容旧代码/UI，读写都落到 self.target） ---------------
    @property
    def coord_mode(self):
        return self.target.coord_mode

    @coord_mode.setter
    def coord_mode(self, v):
        self.target.coord_mode = v if v in COORD_MODES else WINDOW

    @property
    def window_title(self):
        return self.target.window_title

    @window_title.setter
    def window_title(self, v):
        self.target.window_title = str(v or "")

    @property
    def window_match(self):
        return self.target.window_match

    @window_match.setter
    def window_match(self, v):
        self.target.window_match = v

    @property
    def window_class(self):
        return self.target.window_class

    @window_class.setter
    def window_class(self, v):
        self.target.window_class = str(v or "")

    @property
    def bring_to_front(self):
        return self.target.bring_to_front

    @bring_to_front.setter
    def bring_to_front(self, v):
        self.target.bring_to_front = bool(v)

    @property
    def use_fixed_origin(self):
        return self.target.use_fixed_origin

    @use_fixed_origin.setter
    def use_fixed_origin(self, v):
        self.target.use_fixed_origin = bool(v)

    @property
    def origin_x(self):
        return self.target.origin_x

    @origin_x.setter
    def origin_x(self, v):
        self.target.origin_x = int(v or 0)

    @property
    def origin_y(self):
        return self.target.origin_y

    @origin_y.setter
    def origin_y(self, v):
        self.target.origin_y = int(v or 0)

    def _settings_prop(attr):
        def getter(self):
            return getattr(self.settings, attr)

        def setter(self, v):
            setattr(self.settings, attr, float(v or 0))
        return property(getter, setter)

    start_delay = _settings_prop("start_delay")
    hold_jitter = _settings_prop("hold_jitter")
    delay_jitter = _settings_prop("delay_jitter")
    move_after_click = _settings_prop("move_after_click")
    del _settings_prop

    # -- 序列化 ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": SCRIPT_FORMAT_VERSION,
            "name": self.name,
            "target": self.target.to_dict(),
            "settings": self.settings.to_dict(),
            "steps": [dict(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data) -> "Script":
        if not isinstance(data, dict):
            raise ScriptError("脚本格式错误：根节点必须是 JSON 对象")
        data = migrate(data)

        sc = cls(str(data.get("name") or DEFAULT_SCRIPT_NAME))
        sc.target = TargetSpec.from_dict(data.get("target"))
        sc.settings = RunSettings.from_dict(data.get("settings"))

        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ScriptError("脚本格式错误：缺少 steps 数组")

        out = []
        for i, raw in enumerate(steps):
            if not isinstance(raw, dict):
                raise ScriptError("第 %d 个步骤不是对象" % (i + 1))
            t = raw.get("type")
            if t not in STEP_SPECS:
                raise ScriptError("第 %d 个步骤类型未知：%s" % (i + 1, t))
            merged = new_step(t)
            # 备注显式读取：new_step 已放空默认值，后面的 setdefault 覆盖不了它
            merged[NOTE_KEY] = clean_note(raw.get(NOTE_KEY))
            for f in STEP_SPECS[t]["fields"]:
                k = f["key"]
                if k in raw and raw[k] is not None:
                    merged[k] = raw[k]
            for k, v in raw.items():        # 保留未知字段，向前兼容
                merged.setdefault(k, v)
            out.append(merged)
        sc.steps = out
        return sc

    def clone(self) -> "Script":
        return Script.from_dict(self.to_dict())

    # -- 存取 ------------------------------------------------------------
    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "Script":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # -- 校验 ------------------------------------------------------------
    def validate(self):
        """返回 (errors, warnings)"""
        errors, warnings = [], []
        if not self.steps:
            errors.append("脚本是空的，请先添加步骤。")

        t = self.target
        if (t.coord_mode == WINDOW and not t.use_fixed_origin
                and not t.window_title.strip() and not t.window_class.strip()):
            warnings.append("没有绑定目标窗口，运行时将按屏幕绝对坐标执行。")

        labels = [s.get("name") for s in self.steps if s["type"] == "label"]
        targets = set()
        for s in self.steps:
            if s["type"] == "goto":
                targets.add(str(s.get("name") or ""))
            if s["type"] in ("if_color", "if_image"):
                if s.get("on_success") == "goto":
                    targets.add(str(s.get("success_label") or ""))
                if s.get("on_fail") == "goto":
                    targets.add(str(s.get("fail_label") or ""))
        for name in sorted(targets):
            if name not in labels:
                errors.append("跳转目标标签不存在：%s" % (name or "(空)"))

        depth = 0
        for i, s in enumerate(self.steps):
            if s["type"] == "loop_begin":
                depth += 1
            elif s["type"] == "loop_end":
                depth -= 1
                if depth < 0:
                    errors.append("第 %d 步「循环结束」没有对应的「循环开始」。" % (i + 1))
                    depth = 0
        if depth > 0:
            errors.append("有 %d 个「循环开始」缺少「循环结束」。" % depth)

        for i, s in enumerate(self.steps):
            if s["type"] == "if_image":
                path = str(s.get("image") or "").strip()
                if not path:
                    warnings.append("第 %d 步是找图判断，但还没有选择模板图片。" % (i + 1))
                elif not os.path.isfile(path):
                    warnings.append("第 %d 步的模板图片不存在：%s" % (i + 1, path))
            if s["type"] in ("key", "key_down", "key_up"):
                try:
                    wi.parse_combo(s.get("keys") or "")
                except Exception as exc:
                    errors.append("第 %d 步按键无效：%s" % (i + 1, exc))
            if s["type"] == "if_color":
                try:
                    vision.parse_color(s.get("color"))
                except Exception as exc:
                    errors.append("第 %d 步颜色无效：%s" % (i + 1, exc))
        return errors, warnings


# --------------------------------------------------------------------------
# 格式迁移
# --------------------------------------------------------------------------

def detect_version(data: dict) -> int:
    """判断一份脚本数据的格式版本。"""
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("version"), int):
        return int(data["version"])
    if "schema" in data:                 # v1 用的是 schema
        return 1
    if "target" in data and "settings" in data:
        return SCRIPT_FORMAT_VERSION
    return 1                             # 没有版本号，按最早的格式处理


def migrate(data: dict) -> dict:
    """把任意历史版本的脚本数据升级到当前格式。

    v1 -> v2：
        · 版本号从 "schema": 1 改为 "version": 2
        · 目标相关字段（coord_mode/window_*/origin_*）从根节点收进 "target"
        · 运行节奏字段（start_delay 等）收进 "settings"
        · 步骤结构与步骤字段保持不变
    """
    if not isinstance(data, dict):
        return data

    version = detect_version(data)
    if version >= SCRIPT_FORMAT_VERSION:
        return data

    out = dict(data)
    out.pop("schema", None)

    target_keys = ("coord_mode", "window_title", "window_match", "window_class",
                   "bring_to_front", "use_fixed_origin", "origin_x", "origin_y")
    if not isinstance(out.get("target"), dict):
        out["target"] = {k: out.pop(k) for k in target_keys if k in out}
    else:
        for k in target_keys:
            if k in out:
                out["target"].setdefault(k, out.pop(k))

    settings_keys = ("start_delay", "hold_jitter", "delay_jitter",
                     "move_after_click")
    if not isinstance(out.get("settings"), dict):
        out["settings"] = {k: out.pop(k) for k in settings_keys if k in out}
    else:
        for k in settings_keys:
            if k in out:
                out["settings"].setdefault(k, out.pop(k))

    out["version"] = SCRIPT_FORMAT_VERSION

    steps = out.get("steps")
    if isinstance(steps, list):
        fixed = []
        for s in steps:
            if isinstance(s, dict):
                s = dict(s)
                s.setdefault(NOTE_KEY, "")
                # 拖动/滑屏 改名后类型不变，这里保证老脚本仍能跑
            fixed.append(s)
        out["steps"] = fixed

    return out
