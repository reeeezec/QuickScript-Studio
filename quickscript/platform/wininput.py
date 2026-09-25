# -*- coding: utf-8 -*-
"""QuickScript Studio —— Windows 底层能力封装（零第三方依赖）

包含四部分：
  1. 键鼠模拟     SendInput（硬件级注入，兼容 自绘窗口 / DirectInput 程序窗口）
  2. 窗口绑定     EnumWindows / GetClientRect / ClientToScreen（窗口相对坐标）
  3. 屏幕截取     GDI BitBlt + GetDIBits（用于找图找色、取色、截图取模板）
  4. 全局热键     RegisterHotKey + 消息循环（F8 取坐标 / F9 运行 / F10 急停）

所有坐标均为“物理屏幕像素”，与 GetCursorPos 一致。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import random
import subprocess
import sys
import threading
import time
from ctypes import POINTER, byref, sizeof

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:  # pragma: no cover - 仅 Windows 8 以下
    shcore = None

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class InputError(RuntimeError):
    """模拟输入失败（通常是被 UIPI 拦截：目标窗口以管理员身份运行）。"""


# --------------------------------------------------------------------------
# DPI
# --------------------------------------------------------------------------

def enable_dpi_awareness() -> None:
    """让进程使用物理像素坐标。

    必须在创建 Tk 窗口之前调用，否则高 DPI 缩放下
    GetCursorPos / BitBlt / SendInput 会使用不同的坐标系。
    """
    try:
        # PER_MONITOR_AWARE_V2 = -4
        ctx = ctypes.c_void_p(-4)
        if user32.SetProcessDpiAwarenessContext(ctx):
            return
    except Exception:
        pass
    try:
        if shcore is not None and shcore.SetProcessDpiAwareness(2) == 0:
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def system_dpi() -> int:
    """主显示器 DPI（96 = 100%）。"""
    try:
        return int(user32.GetDpiForSystem())
    except Exception:
        hdc = user32.GetDC(0)
        try:
            return int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
        finally:
            user32.ReleaseDC(0, hdc)


def dpi_scale() -> float:
    return max(1.0, system_dpi() / 96.0)


# --------------------------------------------------------------------------
# SendInput 结构体
# --------------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

XBUTTON1 = 1
XBUTTON2 = 2


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (w.UINT, POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = w.UINT


def _send(events) -> None:
    n = len(events)
    arr = (INPUT * n)(*events)
    sent = user32.SendInput(n, arr, sizeof(INPUT))
    if sent != n:
        err = ctypes.get_last_error()
        hint = "（若目标程序以管理员身份运行，请也用管理员身份启动本工具）" if err == 5 else ""
        raise InputError("SendInput 失败，错误码 %s%s" % (err, hint))


def _mouse_input(flags, dx=0, dy=0, data=0) -> INPUT:
    ev = INPUT()
    ev.type = INPUT_MOUSE
    ev.mi = MOUSEINPUT(dx, dy, data, flags, 0, 0)
    return ev


def _key_input(vk, flags=0, scan=0) -> INPUT:
    ev = INPUT()
    ev.type = INPUT_KEYBOARD
    ev.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return ev


# --------------------------------------------------------------------------
# 按键映射
# --------------------------------------------------------------------------

VK_NAMES = {
    "backspace": 0x08, "back": 0x08, "tab": 0x09, "clear": 0x0C, "enter": 0x0D,
    "return": 0x0D, "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "pause": 0x13, "capslock": 0x14, "caps": 0x14, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "spacebar": 0x20, "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "end": 0x23, "home": 0x24, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "select": 0x29, "print": 0x2A,
    "execute": 0x2B, "printscreen": 0x2C, "insert": 0x2D, "ins": 0x2D,
    "delete": 0x2E, "del": 0x2E, "help": 0x2F, "numlock": 0x90,
    "scrolllock": 0x91, "scroll": 0x91, "lshift": 0xA0, "rshift": 0xA1,
    "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5, "win": 0x5B,
    "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D, "sleep": 0x5F,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69, "multiply": 0x6A, "add": 0x6B,
    "separator": 0x6C, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0, "+": 0xBB,
    "minus": 0xBD, "equal": 0xBB, "plus": 0xBB, "comma": 0xBC,
    "period": 0xBE, "slash": 0xBF, "semicolon": 0xBA, "quote": 0xDE,
    # 中文别名
    "上": 0x26, "下": 0x28, "左": 0x25, "右": 0x27, "空格": 0x20,
    "回车": 0x0D, "退出": 0x1B, "控制": 0x11, "换挡": 0x10, "替换": 0x12,
    "删除": 0x2E, "退格": 0x08, "制表": 0x09, "大小写": 0x14,
}

EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x2C,
    0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA3, 0xA5,
}

for _i in range(1, 25):
    VK_NAMES["f%d" % _i] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_NAMES[_c] = ord(_c.upper())
for _c in "0123456789":
    VK_NAMES[_c] = ord(_c)


def vk_of(name: str) -> int:
    """把按键名解析成虚拟键码。支持 'a' / 'F1' / 'ctrl' / 'num5' / '空格'。"""
    key = str(name).strip().lower()
    if not key:
        raise InputError("按键名为空")
    if key in VK_NAMES:
        return VK_NAMES[key]
    if len(key) == 1:
        return ord(key.upper())
    raise InputError("无法识别的按键：%s" % name)


def parse_combo(combo: str):
    """'ctrl+shift+a' -> ([VK_CONTROL, VK_SHIFT], VK_A)"""
    parts = [p.strip() for p in str(combo).replace("＋", "+").split("+")]
    parts = [p for p in parts if p]
    if not parts:
        raise InputError("按键表达式为空")
    if len(parts) == 1 and str(combo).strip() in ("+", "＋"):
        parts = ["+"]
    mods, main = parts[:-1], parts[-1]
    return [vk_of(m) for m in mods], vk_of(main)


# --------------------------------------------------------------------------
# 鼠标 / 键盘
# --------------------------------------------------------------------------

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 0),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 0),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0),
    "x1": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON1),
    "x2": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON2),
}


def cursor_pos():
    pt = w.POINT()
    user32.GetCursorPos(byref(pt))
    return int(pt.x), int(pt.y)


def _virtual_desktop():
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    cx = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    cy = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if cx <= 1 or cy <= 1:
        cx, cy = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = y = 0
    return x, y, cx, cy


def to_absolute(x, y):
    vx, vy, vw, vh = _virtual_desktop()
    nx = int(round((float(x) - vx) * 65535.0 / max(1, vw - 1)))
    ny = int(round((float(y) - vy) * 65535.0 / max(1, vh - 1)))
    return max(0, min(65535, nx)), max(0, min(65535, ny))


class Mouse:
    """鼠标模拟器。stop_event 置位后所有等待都会立刻中断。"""

    def __init__(self, stop_event: threading.Event | None = None):
        self.stop = stop_event or threading.Event()

    # -- 内部 ------------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while True:
            if self.stop.is_set():
                return
            left = end - time.perf_counter()
            if left <= 0:
                return
            time.sleep(min(left, 0.02))

    def _flags(self, button: str):
        try:
            return BUTTONS[str(button)]
        except KeyError:
            raise InputError("未知鼠标按键：%s（可用 left/right/middle/x1/x2）" % button)

    # -- 查询 ------------------------------------------------------------
    def position(self):
        return cursor_pos()

    # -- 动作 ------------------------------------------------------------
    def move_instant(self, x, y) -> None:
        nx, ny = to_absolute(x, y)
        _send([_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny)])
        self.position()  # 等待生效

    def move_to(self, x, y, duration=0.0, steps=None, jitter=0) -> None:
        """平滑移动。duration 秒，steps 步数（None 自动），jitter 每步随机抖动像素。"""
        x, y = int(x), int(y)
        if duration <= 0 or (steps is not None and steps <= 1):
            if jitter:
                x += random.randint(-jitter, jitter)
                y += random.randint(-jitter, jitter)
            self.move_instant(x, y)
            return
        sx, sy = self.position()
        if steps is None:
            distance = max(abs(x - sx), abs(y - sy))
            steps = max(4, min(120, int(distance / 6) + 4))
        steps = max(2, int(steps))
        per = duration / float(steps)
        for i in range(1, steps + 1):
            if self.stop.is_set():
                return
            t = i / float(steps)
            # ease-out，起步快尾端稳，接近人手
            t = 1 - (1 - t) ** 2
            px = int(round(sx + (x - sx) * t))
            py = int(round(sy + (y - sy) * t))
            if jitter:
                px += random.randint(-jitter, jitter)
                py += random.randint(-jitter, jitter)
            self.move_instant(px, py)
            if i < steps:
                self._sleep(per)
        self.move_instant(x, y)

    def button_down(self, button="left") -> None:
        down, _up, data = self._flags(button)
        _send([_mouse_input(down, 0, 0, data)])

    def button_up(self, button="left") -> None:
        _down, up, data = self._flags(button)
        _send([_mouse_input(up, 0, 0, data)])

    def click(self, button="left", hold=0.05, clicks=1, interval=0.08) -> None:
        clicks = max(1, int(clicks))
        for i in range(clicks):
            if self.stop.is_set():
                return
            self.button_down(button)
            self._sleep(max(0.001, hold))
            self.button_up(button)
            if i < clicks - 1:
                self._sleep(max(0.0, interval))

    def wheel(self, amount: int = 1) -> None:
        _send([_mouse_input(MOUSEEVENTF_WHEEL, 0, 0, int(amount) * 120)])

    def drag(self, x1, y1, x2, y2, duration=0.3, steps=None, button="left", jitter=0) -> None:
        self.move_to(x1, y1, 0.0)
        self._sleep(0.03)
        self.button_down(button)
        try:
            self._sleep(0.03)
            self.move_to(x2, y2, duration, steps, jitter)
        finally:
            self._sleep(0.02)
            self.button_up(button)


class Keyboard:
    """键盘模拟器，支持组合键与按住时长。

    注入时同时提供虚拟键码和扫描码：某些自绘窗口程序只读扫描码
    （lParam 的高位字节），只给虚拟键码时这些程序收不到按键。
    """

    def __init__(self, stop_event: threading.Event | None = None):
        self.stop = stop_event or threading.Event()
        self._scan_cache = {}

    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        end = time.perf_counter() + seconds
        while True:
            if self.stop.is_set():
                return
            left = end - time.perf_counter()
            if left <= 0:
                return
            time.sleep(min(left, 0.02))

    def _scancode(self, vk: int) -> int:
        """取虚拟键对应的硬件扫描码（结果缓存）。"""
        if vk in self._scan_cache:
            return self._scan_cache[vk]
        scan = 0
        try:
            scan = int(user32.MapVirtualKeyW(vk, 0)) & 0xFF
        except Exception:
            scan = 0
        self._scan_cache[vk] = scan
        return scan

    def _flags_for(self, vk: int) -> int:
        return KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0

    def key_down(self, vk: int) -> None:
        scan = self._scancode(vk)
        flags = self._flags_for(vk)
        if scan:
            flags |= KEYEVENTF_SCANCODE
        _send([_key_input(vk, flags, scan)])

    def key_up(self, vk: int) -> None:
        scan = self._scancode(vk)
        flags = self._flags_for(vk) | KEYEVENTF_KEYUP
        if scan:
            flags |= KEYEVENTF_SCANCODE
        _send([_key_input(vk, flags, scan)])

    def press(self, combo: str, hold=0.05) -> None:
        """按一下（支持 ctrl+shift+a），hold 为按住时长（秒）。"""
        mods, main = parse_combo(combo)
        for m in mods:
            self.key_down(m)
        self.key_down(main)
        self._sleep(max(0.01, hold))
        self.key_up(main)
        for m in reversed(mods):
            self.key_up(m)

    def hold(self, combo: str, seconds: float) -> None:
        self.press(combo, hold=seconds)

    def release(self, combo: str) -> None:
        mods, main = parse_combo(combo)
        self.key_up(main)
        for m in reversed(mods):
            self.key_up(m)


# --------------------------------------------------------------------------
# 窗口
# --------------------------------------------------------------------------

WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
user32.GetWindowTextW.argtypes = (w.HWND, w.LPWSTR, ctypes.c_int)
user32.GetClassNameW.argtypes = (w.HWND, w.LPWSTR, ctypes.c_int)
user32.GetWindowThreadProcessId.argtypes = (w.HWND, POINTER(w.DWORD))
user32.GetClientRect.argtypes = (w.HWND, POINTER(w.RECT))
user32.ClientToScreen.argtypes = (w.HWND, POINTER(w.POINT))
user32.GetWindowRect.argtypes = (w.HWND, POINTER(w.RECT))
user32.IsWindow.argtypes = (w.HWND,)
user32.IsWindowVisible.argtypes = (w.HWND,)


def list_windows(include_hidden=False, skip_pid=None):
    """枚举顶层窗口 -> [{hwnd,title,class,rect,pid}]"""
    out = []
    own_pid = kernel32.GetCurrentProcessId()

    def cb(hwnd, _lparam):
        try:
            if not include_hidden and not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            pid = w.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, byref(pid))
            if skip_pid is not None and pid.value == skip_pid:
                return True
            cls = ctypes.create_unicode_buffer(512)
            user32.GetClassNameW(hwnd, cls, 512)
            rc = w.RECT()
            user32.GetWindowRect(hwnd, byref(rc))
            out.append({
                "hwnd": int(hwnd),
                "title": title,
                "class": cls.value,
                "pid": int(pid.value),
                "rect": (rc.left, rc.top, rc.right, rc.bottom),
            })
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    del own_pid
    return out


def window_client_rect(hwnd):
    """返回客户区 (left, top, width, height)（屏幕坐标 + 尺寸）。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rc = w.RECT()
    if not user32.GetClientRect(hwnd, byref(rc)):
        return None
    pt = w.POINT(0, 0)
    user32.ClientToScreen(hwnd, byref(pt))
    return int(pt.x), int(pt.y), int(rc.right - rc.left), int(rc.bottom - rc.top)


def window_rect(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rc = w.RECT()
    user32.GetWindowRect(hwnd, byref(rc))
    return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)


def foreground_window():
    return int(user32.GetForegroundWindow() or 0)


def is_foreground(hwnd) -> bool:
    return bool(hwnd) and int(user32.GetForegroundWindow() or 0) == int(hwnd)


def window_at_point(x, y):
    """返回屏幕上某点最上层的顶层窗口句柄（用于判断目标是否被遮挡）。"""
    try:
        h = user32.WindowFromPoint(w.POINT(int(x), int(y)))
        if not h:
            return 0
        root = user32.GetAncestor(h, 2)   # GA_ROOT
        return int(root or h)
    except Exception:
        return 0


def window_title(hwnd) -> str:
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_class(hwnd) -> str:
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetClassNameW(hwnd, buf, 512)
    return buf.value


user32.SetForegroundWindow.argtypes = (w.HWND,)
user32.SetForegroundWindow.restype = w.BOOL
user32.BringWindowToTop.argtypes = (w.HWND,)
user32.SetWindowPos.argtypes = (w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, w.UINT)
user32.ShowWindow.argtypes = (w.HWND, ctypes.c_int)
user32.IsIconic.argtypes = (w.HWND,)
user32.GetForegroundWindow.restype = w.HWND
user32.WindowFromPoint.argtypes = (w.POINT,)
user32.WindowFromPoint.restype = w.HWND
user32.GetAncestor.argtypes = (w.HWND, w.UINT)
user32.GetAncestor.restype = w.HWND
user32.AttachThreadInput.argtypes = (w.DWORD, w.DWORD, w.BOOL)
user32.GetWindowThreadProcessId.restype = w.DWORD

SW_RESTORE = 9
SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040


def _window_thread_id(hwnd) -> int:
    return int(user32.GetWindowThreadProcessId(hwnd, None) or 0)


def activate_window(hwnd) -> bool:
    """把窗口切到前台并确保它没有被最小化。

    目标窗口只有真正获得前台焦点才会接收并处理模拟输入，所以这一步很关键。
    Windows 有「前台锁定」保护：非前台进程不能直接抢焦点。这里用几种
    标准手段依次尝试，最后返回是否确实把窗口变成了前台窗口。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.12)

    target = int(hwnd)
    if int(user32.GetForegroundWindow() or 0) == target:
        return True

    # 1) 直接设置
    try:
        if user32.SetForegroundWindow(target):
            time.sleep(0.05)
            if int(user32.GetForegroundWindow() or 0) == target:
                return True
    except Exception:
        pass

    # 2) 经典技巧：把自己线程的输入队列临时附着到前台线程，
    #    绕开前台锁定，然后设置焦点。
    fg = int(user32.GetForegroundWindow() or 0)
    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = _window_thread_id(fg) if fg else 0
    tgt_thread = _window_thread_id(target)
    attached = []
    try:
        for tid in {fg_thread, tgt_thread}:
            if tid and tid != cur_thread:
                if user32.AttachThreadInput(cur_thread, tid, True):
                    attached.append(tid)
        user32.BringWindowToTop(target)
        user32.SetForegroundWindow(target)
        user32.SetFocus(target)
        if int(user32.GetForegroundWindow() or 0) == target:
            return True
    except Exception:
        pass
    finally:
        for tid in attached:
            try:
                user32.AttachThreadInput(cur_thread, tid, False)
            except Exception:
                pass

    # 3) 模拟一次 Alt 键按下，解除前台锁定后再设置
    try:
        kb = Keyboard()
        kb.key_down(0x12)   # VK_MENU
        kb.key_up(0x12)
        time.sleep(0.05)
        user32.SetForegroundWindow(target)
        if int(user32.GetForegroundWindow() or 0) == target:
            return True
    except Exception:
        pass

    # 4) 最后手段：置顶一下再取消置顶，这通常能把窗口带到最前
    try:
        user32.SetWindowPos(target, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(target)
        user32.SetWindowPos(target, HWND_NOTOPMOST, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
    except Exception:
        pass

    time.sleep(0.05)
    return int(user32.GetForegroundWindow() or 0) == target


def find_window(title, match="contains", class_name=None, include_hidden=True,
                skip_own=True):
    """按标题查找窗口，返回 hwnd 或 None。

    skip_own=True 时会跳过本进程自己的窗口 —— 否则本工具标题里含项目名关键字时
    会匹配到自己，导致坐标全部错位。

    多个窗口匹配时按「匹配程度 > 是否可见 > 窗口面积」排序取最优，
    避免绑定到标题相似的残留/隐藏窗口。
    """
    title = (title or "").strip()
    class_name = (class_name or "").strip()
    if not title and not class_name:
        return None
    own_pid = kernel32.GetCurrentProcessId() if skip_own else None
    candidates = []
    for info in list_windows(include_hidden=include_hidden):
        if own_pid is not None and info["pid"] == own_pid:
            continue
        t = info["title"]
        if class_name and info["class"] != class_name:
            continue
        score = 0
        if title:
            if match == "exact":
                if t != title:
                    continue
                score = 3
            elif match == "startswith":
                if not t.startswith(title):
                    continue
                score = 3 if t == title else 2
            else:
                if title not in t:
                    continue
                score = 3 if t == title else 1
        else:
            score = 1
        left, top, right, bottom = info["rect"]
        area = max(0, right - left) * max(0, bottom - top)
        visible = 1 if user32.IsWindowVisible(info["hwnd"]) else 0
        candidates.append((score, visible, area, info["hwnd"]))

    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[0], -c[1], -c[2]))
    return int(candidates[0][3])


# --------------------------------------------------------------------------
# 屏幕截取（GDI）
# --------------------------------------------------------------------------

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


user32.GetDC.argtypes = (w.HWND,)
user32.GetDC.restype = w.HDC
user32.ReleaseDC.argtypes = (w.HWND, w.HDC)
gdi32.GetPixel.argtypes = (w.HDC, ctypes.c_int, ctypes.c_int)
gdi32.GetPixel.restype = w.DWORD
gdi32.CreateCompatibleDC.argtypes = (w.HDC,)
gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateCompatibleBitmap.argtypes = (w.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = w.HBITMAP
gdi32.SelectObject.argtypes = (w.HDC, w.HGDIOBJ)
gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.BitBlt.argtypes = (w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD)
gdi32.DeleteObject.argtypes = (w.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (w.HDC,)
gdi32.GetDIBits.argtypes = (w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p,
                            POINTER(BITMAPINFOHEADER), w.UINT)


def grab_screen(region=None):
    """截取屏幕。region=(left,top,width,height)，None 表示整个虚拟桌面。

    返回 (width, height, bytes)。每像素 4 字节，顺序 B,G,R,X（自上而下）。
    """
    if region is None:
        left, top, width, height = _virtual_desktop()
    else:
        left, top, width, height = (int(v) for v in region)
    if width <= 0 or height <= 0:
        raise InputError("截图区域无效：%s" % (region,))

    hdc_screen = user32.GetDC(0)
    if not hdc_screen:
        raise InputError("无法获取屏幕 DC")
    hdc_mem = None
    hbmp = None
    old = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        if not hdc_mem or not hbmp:
            raise InputError("创建位图失败")
        old = gdi32.SelectObject(hdc_mem, hbmp)
        if not gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, 0x00CC0020):
            raise InputError("BitBlt 截图失败")
        bi = BITMAPINFOHEADER()
        bi.biSize = sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height  # 负数 = 自上而下
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(width * height * 4)
        got = gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, byref(bi), 0)
        if got == 0:
            raise InputError("GetDIBits 取像素失败")
        return width, height, buf.raw
    finally:
        if hdc_mem and old:
            gdi32.SelectObject(hdc_mem, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        if hdc_screen:
            user32.ReleaseDC(0, hdc_screen)


def pixel_color(x, y):
    """取单点颜色，返回 (r,g,b)；失败返回 None。"""
    hdc = user32.GetDC(0)
    if not hdc:
        return None
    try:
        val = gdi32.GetPixel(hdc, int(x), int(y))
        if val == 0xFFFFFFFF:
            return None
        return (val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF)
    finally:
        user32.ReleaseDC(0, hdc)


def save_bmp(path, width, height, bgra: bytes) -> None:
    """把 grab_screen 的缓冲写成 32 位 BMP（无压缩，自上而下）。"""
    import struct
    row = width * 4
    info = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, row * height, 2835, 2835, 0, 0)
    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 14 + 40, 0, 0, 14 + 40))
        f.write(info)
        f.write(bgra)


def save_ppm(path, width, height, bgra: bytes) -> None:
    """写成 P6 PPM（Tk PhotoImage 可直接读取，用于截图取模板的全屏叠加层）。"""
    out = bytearray()
    out += ("P6\n%d %d\n255\n" % (width, height)).encode("ascii")
    mv = memoryview(bgra)
    rgb = bytearray(width * height * 3)
    rgb[0::3] = mv[2::4]
    rgb[1::3] = mv[1::4]
    rgb[2::3] = mv[0::4]
    out += rgb
    with open(path, "wb") as f:
        f.write(bytes(out))


# --------------------------------------------------------------------------
# 全局热键
# --------------------------------------------------------------------------

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

user32.RegisterHotKey.argtypes = (w.HWND, ctypes.c_int, w.UINT, w.UINT)
user32.UnregisterHotKey.argtypes = (w.HWND, ctypes.c_int)
user32.PostThreadMessageW.argtypes = (w.DWORD, w.UINT, w.WPARAM, w.LPARAM)


class HotkeyManager(threading.Thread):
    """在独立线程里注册全局热键（RegisterHotKey + GetMessage 循环）。

    bindings: {热键ID: (修饰键, 虚拟键码, 回调函数, 说明)}
    """

    def __init__(self, bindings, on_error=None):
        super().__init__(daemon=True, name="hotkey")
        self.bindings = dict(bindings)
        self.on_error = on_error
        self._thread_id = None
        self._ready = threading.Event()
        self._registered = []

    @property
    def registered(self):
        return list(self._registered)

    def run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        for hid, (mods, vk, _cb, _desc) in self.bindings.items():
            if user32.RegisterHotKey(None, int(hid), int(mods) | MOD_NOREPEAT, int(vk)):
                self._registered.append(hid)
            elif self.on_error:
                self.on_error("热键注册失败：%s（可能被其它程序占用）" % _desc)
        self._ready.set()
        msg = w.MSG()
        while True:
            ret = user32.GetMessageW(byref(msg), None, 0, 0)
            if ret in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                entry = self.bindings.get(int(msg.wParam))
                if entry:
                    try:
                        entry[2]()
                    except Exception as exc:  # 回调异常不能杀掉热键线程
                        if self.on_error:
                            self.on_error("热键回调异常：%s" % exc)
        for hid in self._registered:
            user32.UnregisterHotKey(None, int(hid))
        self._registered = []

    def wait_ready(self, timeout=1.5):
        return self._ready.wait(timeout)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


def key_pressed(vk: int) -> bool:
    """查询按键/鼠标键当前是否按下（用于坐标拾取时捕捉鼠标点击）。"""
    return bool(user32.GetAsyncKeyState(int(vk)) & 0x8000)


# --------------------------------------------------------------------------
# 输入法(IME)干扰：中文输入法会把注入的按键吞成 VK_PROCESSKEY
# --------------------------------------------------------------------------

WM_INPUTLANGCHANGEREQUEST = 0x0050
HKL_ENGLISH_US = 0x04090409
LANG_CHINESE_SIMPLIFIED = 0x0804
LANG_ENGLISH_US = 0x0409

user32.GetKeyboardLayout.argtypes = (w.DWORD,)
user32.GetKeyboardLayout.restype = w.HANDLE
user32.LoadKeyboardLayoutW.argtypes = (w.LPCWSTR, w.UINT)
user32.LoadKeyboardLayoutW.restype = w.HANDLE
user32.PostMessageW.argtypes = (w.HWND, w.UINT, w.WPARAM, w.LPARAM)
user32.PostMessageW.restype = w.BOOL


def window_layout_id(hwnd) -> int:
    """取窗口所在线程的键盘布局语言 ID（0x0804=简体中文，0x0409=英文）。"""
    try:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        return int(user32.GetKeyboardLayout(tid) or 0) & 0xFFFF
    except Exception:
        return 0


def english_layout_handle() -> int:
    """取得英文（美国）键盘布局句柄，没有就加载一个。"""
    try:
        return int(user32.LoadKeyboardLayoutW("00000409", 0x00000001) or 0)
    except Exception:
        return HKL_ENGLISH_US


def ensure_english_input(hwnd):
    """确保目标窗口使用英文键盘布局。返回 (是否切换了, 说明文字)。

    为什么必须做这件事：
      中文输入法激活时（布局 0x0804），Windows 会把注入按键的 WM_KEYDOWN
      转成 VK_PROCESSKEY(0xE5)。靠按键消息读取键码的程序 —— 包括浏览器内核承载的页面 ——
      就收不到真实按键，表现为「按 W 没反应」。
      切到英文布局（0x0409）后按键即可正常送达。

    实测有效：给窗口 PostMessage(WM_INPUTLANGCHANGEREQUEST)。
    实测无效：AttachThreadInput + ActivateKeyboardLayout（改不动目标窗口）。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False, "窗口无效"

    before = window_layout_id(hwnd)
    if before == LANG_ENGLISH_US:
        return False, "已经是英文布局"
    if before == 0:
        return False, "无法读取键盘布局"

    hkl = english_layout_handle()
    if not hkl:
        return False, "找不到英文键盘布局"

    try:
        user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
    except Exception as exc:
        return False, "切换输入法失败：%s" % exc

    for _ in range(12):            # 异步生效，最多等 0.6 秒
        time.sleep(0.05)
        if window_layout_id(hwnd) == LANG_ENGLISH_US:
            name = ("中文" if before == LANG_CHINESE_SIMPLIFIED
                    else "0x%04X" % before)
            return True, "输入法已从 %s 切到英文（避免按键被输入法吞掉）" % name
    return False, ("请求切换输入法后目标窗口仍是非英文布局；"
                   "若按键无效，请手动按 Win+空格 切到英文输入法再运行。")


# --------------------------------------------------------------------------
# 环境自检：模拟输入到底能不能用？
# --------------------------------------------------------------------------

def test_input_injection():
    """真实测试本机是否允许模拟输入。

    有些环境会「假装成功」—— SendInput 返回成功，但光标纹丝不动
    （常见于后台运行的加速器或安全软件的键鼠保护、或前台被特权进程占用）。
    这种情况必须先发现，否则脚本会跑完但目标程序毫无反应。

    返回 (是否可用, 说明文字)
    """
    try:
        start = cursor_pos()
    except Exception as exc:
        return False, "无法读取鼠标位置：%s" % exc
    try:
        m = Mouse()
        m.move_instant(start[0] + 60, start[1] + 40)
        time.sleep(0.12)
        moved = cursor_pos()
        m.move_instant(start[0], start[1])
        time.sleep(0.08)
    except Exception as exc:
        return False, "模拟输入失败：%s" % exc

    if (moved[0], moved[1]) != (start[0], start[1]):
        return True, "模拟输入正常（鼠标可被移动）"

    fg = foreground_window()
    title = window_title(fg)
    cls = window_class(fg)
    who = title or cls or ("hwnd=%d" % fg)
    return False, (
        "模拟输入被拦截：鼠标无法移动（SendInput 返回成功但无效）。\n"
        "当前占用前台的窗口：%s\n"
        "常见原因：后台运行的游戏加速器或安全软件、"
        "安全软件的「游戏模式 / 键鼠保护」等拦下了模拟输入，"
        "或前台被特权进程占用。\n"
        "解决办法：退出上述加速器/安全软件（或在其中关闭「游戏模式」「键鼠保护」），"
        "然后重跑环境自检；必要时用「以管理员身份运行」启动本工具。" % who)


def test_hotkey_available(vk: int) -> bool:
    """检测某个按键能否注册为全局热键（被占用则返回 False）。"""
    try:
        if user32.RegisterHotKey(None, 0xBEEF, MOD_NOREPEAT, int(vk)):
            user32.UnregisterHotKey(None, 0xBEEF)
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------
# 权限隔离(UIPI)：低权限进程无法向管理员权限的窗口注入输入
# --------------------------------------------------------------------------

advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
kernel32.OpenProcess.restype = w.HANDLE
kernel32.CloseHandle.argtypes = (w.HANDLE,)
advapi32.OpenProcessToken.argtypes = (w.HANDLE, w.DWORD, POINTER(w.HANDLE))
advapi32.GetTokenInformation.argtypes = (w.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         w.DWORD, POINTER(w.DWORD))
advapi32.GetSidSubAuthorityCount.argtypes = (ctypes.c_void_p,)
advapi32.GetSidSubAuthorityCount.restype = POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = (ctypes.c_void_p, w.DWORD)
advapi32.GetSidSubAuthority.restype = POINTER(w.DWORD)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25

LEVEL_MEDIUM = 0x2000
LEVEL_HIGH = 0x3000

LEVEL_NAMES = {
    0x0000: "不可信", 0x1000: "低", 0x2000: "普通",
    0x2100: "普通+", 0x2200: "普通++", 0x3000: "管理员", 0x4000: "系统",
}


def is_admin() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def integrity_level(pid: int):
    """取进程完整性级别 RID（0x2000=普通，0x3000=管理员）。

    读不到通常说明那个进程权限比我们高（连查询都被拒），返回 None。
    """
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return None
    tok = w.HANDLE()
    try:
        if not advapi32.OpenProcessToken(h, TOKEN_QUERY, byref(tok)):
            return None
        size = w.DWORD(0)
        advapi32.GetTokenInformation(tok, TokenIntegrityLevel, None, 0, byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(tok, TokenIntegrityLevel, buf, size.value,
                                            byref(size)):
            return None
        sid = ctypes.cast(buf, POINTER(ctypes.c_void_p))[0]
        count = advapi32.GetSidSubAuthorityCount(sid)[0]
        return int(advapi32.GetSidSubAuthority(sid, count - 1)[0])
    except Exception:
        return None
    finally:
        if tok:
            kernel32.CloseHandle(tok)
        kernel32.CloseHandle(h)


def level_name(rid) -> str:
    if rid is None:
        return "更高权限"
    return LEVEL_NAMES.get(int(rid), "0x%04X" % int(rid))


def process_id_of_window(hwnd) -> int:
    try:
        pid = w.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def can_send_to(hwnd):
    """判断本进程能否向该窗口注入输入。

    返回 (是否可以, 说明文字)。Windows 的 UIPI 规则：低权限进程不能向
    更高权限的窗口发输入。这是「工具聚焦时点击生效、切到游戏就没反应」
    的典型原因 —— 因为游戏是以管理员身份运行的。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False, "窗口无效"
    my = integrity_level(kernel32.GetCurrentProcessId())
    pid = process_id_of_window(hwnd)
    if not pid:
        return True, "无法确定目标进程，跳过检查"
    target = integrity_level(pid)
    if target is None:
        target = LEVEL_HIGH      # 读不到 ⇒ 权限比我们高
    if my is None:
        my = LEVEL_MEDIUM

    if target > my:
        return False, (
            "权限不足：目标进程是「%s」权限，本工具是「%s」权限。\n"
            "Windows 的安全机制(UIPI)会拦截低权限进程向高权限窗口发送的模拟输入，"
            "所以切到目标窗口后点击无效。\n"
            "解决办法：用管理员身份重新启动本工具（双击「以管理员身份启动.bat」）。"
            % (level_name(target), level_name(my)))
    return True, "权限足够（本工具 %s / 目标 %s）" % (level_name(my), level_name(target))


def _project_root():
    """返回 `python -m quickscript` 能生效的工作目录。

    本文件位于 quickscript/platform/，所以：
        文件所在目录 = .../quickscript/platform
        上一级       = .../quickscript   （包的父目录，即项目根）
    打包成 exe 后没有源码树，直接用 exe 所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))          # .../quickscript/platform
    return os.path.dirname(os.path.dirname(here))              # .../<项目根>


def relaunch_as_admin(script_path=None, extra_args=None):
    """以管理员身份重新启动本程序。成功返回 True。

    默认用 `pythonw -m quickscript` 重启，而不是指向某个具体脚本文件：
    入口文件名在重构中改过（gui.py -> qs.py -> 包入口），写死文件名会失效。
    打包成 exe 后则直接重启自身。
    """
    try:
        if is_admin():
            return False

        frozen = getattr(sys, "frozen", False)
        if frozen:
            # 已打包：重启 exe 自身
            exe = sys.executable
            args = list(extra_args or [])
            workdir = os.path.dirname(os.path.abspath(exe))
        else:
            exe = sys.executable
            # 优先用 pythonw（无黑窗口）
            cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.isfile(cand):
                exe = cand
            if script_path:
                # 调用方显式指定了脚本：按原样使用
                args = [script_path] + list(extra_args or [])
                workdir = os.path.dirname(os.path.abspath(script_path))
            else:
                # 默认：按模块方式重启，不依赖入口文件名
                args = ["-m", "quickscript"] + list(extra_args or [])
                workdir = _project_root()

        # ShellExecuteW 的 runas 动词会弹出 UAC 提权对话框；
        # lpDirectory 决定工作目录，模块方式启动时必须是项目根目录。
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, subprocess.list2cmdline(args), workdir, 1)
        return int(ret) > 32
    except Exception:
        return False


# --------------------------------------------------------------------------
# 窗口样式（让提示浮层可以“点击穿透”，不挡住目标程序操作）
# --------------------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

try:
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
except AttributeError:  # 32 位 Python
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW

_get_long.argtypes = (w.HWND, ctypes.c_int)
_get_long.restype = ctypes.c_ssize_t
_set_long.argtypes = (w.HWND, ctypes.c_int, ctypes.c_ssize_t)
_set_long.restype = ctypes.c_ssize_t
user32.GetParent.argtypes = (w.HWND,)
user32.GetParent.restype = w.HWND


def set_click_through(tk_widget, no_activate=True) -> bool:
    """给 Tk 顶层窗口加上鼠标穿透 + 不抢焦点。失败返回 False（不影响功能）。"""
    try:
        tk_widget.update_idletasks()
        hwnd = int(tk_widget.winfo_id())
        parent = user32.GetParent(hwnd)
        target = int(parent) if parent else hwnd
        style = _get_long(target, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        if no_activate:
            style |= WS_EX_NOACTIVATE
        _set_long(target, GWL_EXSTYLE, style)
        return True
    except Exception:
        return False



VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
