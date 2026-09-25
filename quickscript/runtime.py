# -*- coding: utf-8 -*-
"""QuickScript Studio —— 执行引擎

把四层组合起来跑：

    目标层   解析窗口与坐标（TargetResolver）
    流程层   决定下一步去哪（loop / jump / stop）
    触发层   按条件分支（找色 / 找图）
    动作层   产生键鼠输入

引擎本身只负责「调度 + 上下文」，具体动作都在各层里。
"""
from __future__ import annotations

import os
import random
import threading
import time
import traceback

from .metadata import SCRIPT_FORMAT_VERSION
from .layers import actions, flow, triggers
from .layers.flow import Jump, LoopFrame, Stop, find_loop_end
from .layers.target import TargetResolver, SCREEN, WINDOW
from .model import ScriptError, MAX_TOTAL_STEPS, STEP_SPECS
from .platform import wininput as wi

__all__ = ["Runner", "LogLevel", "RunState", "SCRIPT_FORMAT_VERSION"]


class LogLevel:
    INFO = "info"
    OK = "ok"
    WARN = "warn"
    ERR = "error"


class RunState:
    """运行时状态，供 UI 显示。"""

    def __init__(self):
        self.running = False
        self.reason = ""
        self.step_count = 0


# --------------------------------------------------------------------------
# 执行上下文：动作层/流程层/触发层通过它访问公共能力
# --------------------------------------------------------------------------

class ExecContext:
    """执行上下文。

    把「动作层需要的东西」集中在这里，动作函数只依赖这个接口，
    因此新增动作不需要改动引擎。
    """

    def __init__(self, runner: "Runner"):
        self.runner = runner
        self.script = runner.script
        self.mouse = runner.mouse
        self.keyboard = runner.keyboard
        self.stop_event = runner.stop_event
        self._held_keys = runner.held_keys
        self._held_buttons = runner.held_buttons
        self._labels = {}

    # -- 基础能力 --------------------------------------------------------
    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def log(self, level, msg):
        self.runner._log(level, msg)

    def sleep(self, seconds):
        self.runner._sleep(seconds)

    @staticmethod
    def jitter(value, amount):
        return Runner._jitter(value, amount)

    # -- 按住状态跟踪（急停时要全部松开）--------------------------------
    def hold_key(self, combo):
        self._held_keys.add(combo)

    def release_key(self, combo):
        self._held_keys.discard(combo)

    def hold_button(self, button):
        self._held_buttons.add(button)

    def release_button(self, button):
        self._held_buttons.discard(button)

    # -- 标签 ------------------------------------------------------------
    def index_labels(self):
        self._labels = {}
        for i, s in enumerate(self.script.steps):
            if s.get("type") == "label":
                name = str(s.get("name") or "").strip()
                if name and name not in self._labels:
                    self._labels[name] = i
        return self._labels

    def label_index(self, name):
        idx = self._labels.get(name)
        if idx is None:
            self.log(LogLevel.ERR, "找不到标签：%s" % (name or "(空)"))
        return idx

    # -- 截屏（触发层用）-------------------------------------------------
    def grab(self, region=None):
        return self.runner._grab(region)


# --------------------------------------------------------------------------
# 运行器
# --------------------------------------------------------------------------

class Runner:
    """在后台线程执行脚本。

    回调都在后台线程触发，UI 侧需要自行转发到主线程。
    """

    def __init__(self, script, on_log=None, on_step=None, on_state=None):
        self.script = script
        self.on_log = on_log or (lambda level, msg: None)
        self.on_step = on_step or (lambda index: None)
        self.on_state = on_state or (lambda running, reason: None)

        self.stop_event = threading.Event()
        self._thread = None
        self.step_count = 0

        self.resolver = TargetResolver(script.target)
        self.mouse = wi.Mouse(self.stop_event)
        self.keyboard = wi.Keyboard(self.stop_event)
        self.held_keys = set()
        self.held_buttons = set()

        self.ctx = ExecContext(self)

    # -- 生命周期 --------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def target(self):
        """当前已解析的目标（坐标换算用）。"""
        return self.resolver.bound

    def start(self, start_index: int = 0, only_index=None):
        if self.running:
            raise ScriptError("脚本已经在运行了")
        self.step_count = 0
        self._thread = threading.Thread(target=self._run,
                                        args=(start_index, only_index),
                                        daemon=True, name="qs-runner")
        self._thread.start()

    def stop(self):
        self.stop_event.set()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # -- 工具 ------------------------------------------------------------
    def _log(self, level, msg):
        try:
            self.on_log(level, msg)
        except Exception:
            pass

    def _sleep(self, seconds):
        """可中断睡眠。"""
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while True:
            if self.stop_event.is_set():
                return
            left = end - time.perf_counter()
            if left <= 0:
                return
            time.sleep(min(left, 0.02))

    @staticmethod
    def _jitter(value, amount):
        v = float(value or 0)
        if amount and amount > 0:
            v += random.uniform(-amount, amount)
        return max(0.0, v)

    def _grab(self, region=None):
        """按当前坐标空间截屏 → (w, h, buf, 截屏原点屏幕坐标)"""
        target = self.target
        if region:
            x, y, rw, rh = (int(v) for v in region)
            sx, sy = target.to_screen(x, y)
            w, h, buf = wi.grab_screen((sx, sy, rw, rh))
            return w, h, buf, (sx, sy)

        if self.script.coord_mode == WINDOW and target.hwnd:
            rect = wi.window_client_rect(target.hwnd)
            if rect:
                target.client_origin = (rect[0], rect[1])
                target.client_size = (rect[2], rect[3])
                w, h, buf = wi.grab_screen(rect)
                return w, h, buf, (rect[0], rect[1])

        w, h, buf = wi.grab_screen(None)
        return w, h, buf, (0, 0)

    def _release_all(self):
        """急停/结束时松开所有还按着的键和鼠标键。"""
        for btn in list(self.held_buttons):
            try:
                self.mouse.button_up(btn)
            except Exception:
                pass
        self.held_buttons.clear()
        for combo in list(self.held_keys):
            try:
                self.keyboard.release(combo)
            except Exception:
                pass
        self.held_keys.clear()

    # -- 运行前检查 ------------------------------------------------------
    def _preflight(self) -> bool:
        """绑定目标、检查权限/前台/输入法。返回是否绑定到窗口。"""
        sc = self.script
        bound = self.resolver.refresh(activate=sc.bring_to_front)
        self._log(LogLevel.OK if bound else LogLevel.INFO, self.target.describe())

        if sc.coord_mode == WINDOW and not bound and not sc.use_fixed_origin:
            self._log(LogLevel.WARN, "没有找到绑定窗口，本次按屏幕绝对坐标执行。")

        if not (bound and self.target.hwnd):
            return bound

        hwnd = self.target.hwnd

        # 权限隔离(UIPI)：低权限进程无法向高权限窗口注入输入
        perm_ok, perm_why = wi.can_send_to(hwnd)
        if perm_ok:
            self._log(LogLevel.OK, "权限检查：%s" % perm_why)
        else:
            self._log(LogLevel.ERR, "权限检查未通过！脚本将无法操作目标窗口。")
            for line in perm_why.split("\n"):
                self._log(LogLevel.ERR, "  " + line)

        # 目标窗口必须在前台才会接收模拟输入
        if wi.is_foreground(hwnd):
            self._log(LogLevel.OK, "目标窗口已在前台，可以接收模拟输入。")
        else:
            fg = wi.foreground_window()
            blocker = wi.window_title(fg) or wi.window_class(fg) or "未知窗口"
            self._log(LogLevel.WARN,
                      "目标窗口没有取得前台焦点（当前前台是「%s」）。" % blocker)
            if not perm_ok:
                self._log(LogLevel.WARN,
                          "注意：即使目标窗口到了前台，权限不足仍会导致输入被拦截。")
            else:
                self._log(LogLevel.WARN, "请在开始前手动点一下目标窗口。")
            if sc.start_delay < 2.0:
                self._log(LogLevel.INFO,
                          "建议把「开始前准备时间」设为 2 秒以上，留出切换窗口的时间。")

        # 中文输入法会把注入按键吞成 VK_PROCESSKEY
        if any(s.get("type") in ("key", "key_down", "key_up") for s in sc.steps):
            switched, why = wi.ensure_english_input(hwnd)
            self._log(LogLevel.OK if switched else LogLevel.INFO,
                      "输入法检查：%s" % why)
        return bound

    # -- 主循环 ----------------------------------------------------------
    def _run(self, start_index, only_index):
        sc = self.script
        self.stop_event.clear()
        reason = "完成"
        try:
            self.on_state(True, "运行中")
            self._log(LogLevel.INFO, "══════ 开始运行：%s ══════" % sc.name)

            try:
                bound = self._preflight()
            except wi.InputError as exc:
                self._log(LogLevel.ERR, "环境检查失败：%s" % exc)
                bound = False
            del bound

            if sc.start_delay > 0:
                self._log(LogLevel.INFO,
                          "%.1f 秒后开始，请切到目标窗口……（F10 随时急停）"
                          % sc.start_delay)
                self._sleep(sc.start_delay)

            self.ctx.index_labels()

            loop_stack = []
            pc = max(0, int(start_index))
            total = len(sc.steps)
            end_index = total - 1 if only_index is None else int(only_index)

            while 0 <= pc < total and pc <= end_index:
                if self.stop_event.is_set():
                    reason = "已手动停止"
                    break
                if self.step_count > MAX_TOTAL_STEPS:
                    reason = "超过最大步数（可能是死循环）"
                    self._log(LogLevel.ERR,
                              "执行步数超过 %d，已强制停止。" % MAX_TOTAL_STEPS)
                    break

                step = sc.steps[pc]
                stype = step.get("type")
                try:
                    self.on_step(pc)
                except Exception:
                    pass
                self.step_count += 1

                result = self._dispatch(step, stype, pc, loop_stack, total)

                if result is _CONTINUE:
                    pc += 1
                elif isinstance(result, _JumpTo):
                    target_pc = result.index
                    while loop_stack and not (loop_stack[-1].start <= target_pc
                                              <= loop_stack[-1].end):
                        loop_stack.pop()
                    pc = target_pc
                elif isinstance(result, _StopRun):
                    reason = result.reason
                    break
                else:
                    pc += 1

                if only_index is not None:
                    break

            if reason == "完成" and not self.stop_event.is_set():
                self._log(LogLevel.OK, "══════ 执行完毕（共 %d 步）══════" % self.step_count)
            else:
                self._log(LogLevel.WARN,
                          "══════ 已停止：%s（共 %d 步）══════" % (reason, self.step_count))

        except wi.InputError as exc:
            reason = "模拟输入失败"
            self._log(LogLevel.ERR, "模拟输入失败：%s" % exc)
        except ScriptError as exc:
            reason = "脚本错误"
            self._log(LogLevel.ERR, "脚本错误：%s" % exc)
        except Exception as exc:
            reason = "运行异常"
            self._log(LogLevel.ERR, "运行异常：%s" % exc)
            self._log(LogLevel.ERR, traceback.format_exc(limit=4))
        finally:
            self._release_all()
            self._thread = None
            try:
                self.on_state(False, reason)
            except Exception:
                pass

    # -- 分发 ------------------------------------------------------------
    def _dispatch(self, step, stype, pc, loop_stack, total):
        """把一步分发给对应的层。"""
        # 循环结构由引擎维护（涉及跨步骤配对）
        if stype == "loop_begin":
            declared = int(step.get("times") or 0)
            end = find_loop_end(self.script.steps, pc)
            if end < 0:
                self._log(LogLevel.ERR, "第 %d 步的循环没有结束标记，跳过。" % (pc + 1))
                return _CONTINUE
            if declared != 1:
                loop_stack.append(LoopFrame(pc, end, declared))
                self._log(LogLevel.INFO, "进入循环：%s" % flow.describe_loop(declared))
            return _CONTINUE

        if stype == "loop_end":
            if not loop_stack:
                self._log(LogLevel.WARN, "多余的「循环结束」，忽略。")
                return _CONTINUE
            frame = loop_stack[-1]
            if frame.exhausted():
                loop_stack.pop()
                return _CONTINUE
            frame.consume()
            return _JumpTo(frame.start + 1)

        # 流程层
        if flow.is_flow_step(stype):
            return self._wrap(flow.handle(self.ctx, step, pc))

        # 触发层
        if triggers.is_trigger_step(stype):
            return self._wrap(triggers.handle(self.ctx, step, self.target))

        # 动作层
        handler = actions.get(stype)
        if handler is not None:
            handler(self.ctx, step, self.target)
            return _CONTINUE

        self._log(LogLevel.WARN, "未知步骤类型：%s" % stype)
        return _CONTINUE

    @staticmethod
    def _wrap(result):
        """把流程层/触发层的返回值翻译成引擎的内部信号。"""
        if result is None:
            return _CONTINUE
        if isinstance(result, Jump):
            return _JumpTo(result.index)
        if isinstance(result, Stop):
            return _StopRun(result.reason)
        if isinstance(result, bool):       # 布尔按"是否跳转"处理（兼容）
            return _CONTINUE
        if isinstance(result, int):
            return _JumpTo(result)
        return _CONTINUE


# --------------------------------------------------------------------------
# 内部信号
# --------------------------------------------------------------------------

class _Continue:
    __slots__ = ()


class _JumpTo:
    __slots__ = ("index",)

    def __init__(self, index):
        self.index = int(index)


class _StopRun:
    __slots__ = ("reason",)

    def __init__(self, reason):
        self.reason = reason


_CONTINUE = _Continue()
