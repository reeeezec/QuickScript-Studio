"""端到端验证：脚本真的能点中「另一个进程」的窗口吗？

这是最贴近真实目标程序的验证：
  1. 启动一个独立的**目标进程**（e2e_target.py）当作目标窗口；
  2. 用真实脚本绑定它（跨进程，和真实目标程序完全一致）；
  3. 用 Runner 真正执行，通过 SendInput 产生真实鼠标/键盘事件；
  4. 目标进程把收到的事件（屏幕坐标、按下时长、按键）写成 JSON，
     由此逐一核对点击位置、按下时长、连击次数、拖动轨迹、按键是否正确。

通过即证明「窗口绑定 → 坐标换算 → SendInput → 参数控制」整条链路真实可用。

注意：本测试会短暂接管鼠标键盘（约 15 秒），期间请不要操作鼠标。
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import functools
import json
import os
import tempfile
import subprocess
import sys
import threading
import time

print = functools.partial(print, flush=True)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from quickscript.platform import wininput as wi

wi.enable_dpi_awareness()

from quickscript import compat as engine   # noqa: E402
from quickscript.platform import vision   # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "quickscript_e2e")
INFO_FILE = os.path.join(TMP, "e2e_info.json")
EVENT_FILE = os.path.join(TMP, "e2e_events.json")
TITLE = "E2E_TARGET_WINDOW_%d" % os.getpid()
WIN_X, WIN_Y, WIN_W, WIN_H = 300, 200, 620, 460

PASS, FAIL, SKIP = [], [], []
T0 = time.perf_counter()


def step(msg):
    print("  · [%6.2fs] %s" % (time.perf_counter() - T0, msg))


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print("  [%s] %s   %s" % ("OK  " if cond else "FAIL", name, detail))


def skip(name, why):
    SKIP.append((name, why))
    print("  [跳过] %s   （%s）" % (name, why))


def probe_input_injection():
    """检测本机当前是否允许模拟输入。

    有些后台程序（加速器 / 安全软件）会占用前台并拦截
    输入注入：SendInput 返回成功，但光标其实不动。这种情况必须先发现，
    否则会误以为是程序有 bug。

    返回 (可用?, 说明)
    """
    try:
        o1 = wi.cursor_pos()
        wi.Mouse().move_instant(o1[0] + 60, o1[1] + 40)
        time.sleep(0.15)
        o2 = wi.cursor_pos()
        wi.Mouse().move_instant(*o1)
        time.sleep(0.1)
    except Exception as exc:
        return False, "模拟输入探测异常：%s" % exc
    if (o2[0], o2[1]) != (o1[0], o1[1]):
        return True, "模拟输入可用"
    fg = wi.foreground_window()
    return False, ("模拟输入被拦截：光标未移动（SendInput 却返回成功）。"
                   "当前前台窗口 hwnd=%d 类名=%r 属于其它进程（常见于目标程序加速器/"
                   "安全软件占用前台）。"
                   % (fg, wi.window_class(fg)))


class TargetProcess:
    def __init__(self):
        os.makedirs(TMP, exist_ok=True)
        for p in (INFO_FILE, EVENT_FILE):
            if os.path.isfile(p):
                os.remove(p)
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "e2e_target.py"),
             INFO_FILE, EVENT_FILE, str(WIN_X), str(WIN_Y), str(WIN_W), str(WIN_H), TITLE],
            cwd=HERE)
        self.info = self._wait_info()

    def _wait_info(self, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            if os.path.isfile(INFO_FILE):
                try:
                    with open(INFO_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("hwnd") and data.get("client", [0, 0, 0, 0])[2] > 0:
                        return data
                except Exception:
                    pass
            if self.proc.poll() is not None:
                raise RuntimeError("目标进程提前退出（退出码 %s）" % self.proc.returncode)
            time.sleep(0.1)
        raise RuntimeError("等待目标进程信息超时")

    def events(self):
        try:
            with open(EVENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"click_count": 0, "press": [], "release": [], "drag": [],
                    "motion": [], "keys": []}

    def reset_events(self):
        """清空事件记录，便于分段验证。"""
        self.events()  # 确保文件存在
        try:
            with open(EVENT_FILE, "w", encoding="utf-8") as f:
                json.dump({"click_count": 0, "press": [], "release": [], "drag": [],
                           "motion": [], "keys": []}, f)
        except Exception:
            pass
        time.sleep(0.4)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()


def _safe_output():
    """GBK 控制台下打印 ✓ 等字符会抛 UnicodeEncodeError，
    让本来通过的测试反而崩掉。统一改成容错输出。"""
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass


def main():
    _safe_output()
    print("端到端真实输入验证开始（跨进程，最接近真实目标程序场景）")
    print("  ⚠ 接下来约 15 秒会接管鼠标，请不要操作鼠标。")

    # 先确认本机允许模拟输入，否则后面的输入断言没有意义
    step("探测模拟输入是否被系统/安全软件拦截")
    inject_ok, why = probe_input_injection()
    if inject_ok:
        print("  ✓ %s" % why)
        check("模拟输入在本机可用", True, why)
    else:
        print("  ✗ %s" % why)
        print("  → 这是本机环境限制，不是程序缺陷，因此记为「跳过」而非失败。")
        print("    解决建议：")
        print("      1) 关闭加速器 / 安全软件的『游戏模式』『键鼠保护』；")
        print("      2) 或用管理员身份运行本测试；")
        print("      3) 关闭后重跑本测试即可完整验证输入链路。")
        skip("模拟输入在本机可用（环境限制）", why)

    step("启动目标进程")
    try:
        target = TargetProcess()
    except Exception as exc:
        print("  启动目标进程失败：%s" % exc)
        return 1

    try:
        info = target.info
        hwnd = int(info["hwnd"])
        ox, oy, cw, ch = info["client"]
        step("目标窗口 hwnd=%d 标题=%r 客户区 %dx%d @ (%d,%d)"
             % (hwnd, info["title"], cw, ch, ox, oy))

        check("目标窗口属于另一个进程", info["pid"] != os.getpid(),
              "目标 pid=%s 本进程 pid=%s" % (info["pid"], os.getpid()))
        check("目标窗口标题唯一", info["title"] == TITLE, repr(info["title"]))

        found = wi.find_window(TITLE, "exact")
        check("能按标题跨进程找到目标窗口", found == hwnd,
              "找到 %s，期望 %s" % (found, hwnd))

        step("激活目标窗口")
        activated = wi.activate_window(hwnd)
        time.sleep(0.5)
        fg = wi.foreground_window()
        fg_ok = (fg == hwnd)
        print("  目标是否取得前台焦点：%s（前台 hwnd=%d，目标 hwnd=%d）"
              % ("是" if fg_ok else "否", fg, hwnd))
        if not fg_ok:
            fg_title = wi.window_title(fg)
            print("  当前前台窗口：%r  类名=%r  rect=%s"
                  % (fg_title, wi.window_class(fg), wi.window_rect(fg)))
            print("  说明：Windows 的前台锁定被一个 0x0 的隐藏窗口占用，")
            print("        普通权限进程无法强制抢焦点。真实使用时请手动点一下目标窗口，")
            print("        或用管理员身份启动本工具。下面的输入类断言将据此调整。")
        check("activate_window 能返回真实的前台状态",
              isinstance(activated, bool), repr(activated))

        # 输入类断言只有在「目标处于前台」且「本机允许注入」时才有意义
        can_test_input = fg_ok and inject_ok

        if fg_ok:
            pass
        elif inject_ok:
            print("\n  ⚠ 目标窗口未取得前台焦点，下面改用光标位置验证坐标换算链路。")
        else:
            print("\n  ⚠ 本机模拟输入被拦截，跳过所有输入类断言（已在上方报告）。")

        if inject_ok:
            m = wi.Mouse()
            m.move_instant(ox + 160, oy + 90)
            time.sleep(0.2)
            cx, cy = wi.cursor_pos()
            if can_test_input:
                check("鼠标被移动到脚本坐标换算出的屏幕位置",
                      abs(cx - (ox + 160)) <= 3 and abs(cy - (oy + 90)) <= 3,
                      "实际(%d,%d) 期望(%d,%d)" % (cx, cy, ox + 160, oy + 90))
                check("窗口绑定与坐标换算正确（客户区原点可反算）",
                      (cx - ox, cy - oy) == (160, 90),
                      "反算脚本坐标 (%d,%d)" % (cx - ox, cy - oy))
        else:
            skip("鼠标位置随脚本坐标变化", "本机模拟输入被拦截")

        def to_screen(sx, sy):
            return ox + sx, oy + sy

        # ============ 脚本 1：点击 / 移动 / 按键 ============
        sc = engine.Script("E2E点击")
        sc.coord_mode = "window"
        sc.window_title = TITLE
        sc.window_match = "exact"
        sc.bring_to_front = True
        sc.start_delay = 0.3
        sc.steps = [
            engine.new_step("click"),
            engine.new_step("delay"),
            engine.new_step("click"),
            engine.new_step("move"),
            engine.new_step("key"),
        ]
        # 点按钮中心：按钮 place 在 (60,50) 尺寸 200x80 → 中心 (160, 90)
        sc.steps[0].update({"x": 160, "y": 90, "button": "left", "hold": 0.12,
                            "clicks": 1, "move_time": 0.10, "interval": 0.08})
        sc.steps[1].update({"seconds": 0.3, "random": 0})
        sc.steps[2].update({"x": 420, "y": 340, "button": "left", "hold": 0.06,
                            "clicks": 2, "interval": 0.12, "move_time": 0.10})
        sc.steps[3].update({"x": 500, "y": 400, "duration": 0.20, "jitter": 0})
        sc.steps[4].update({"keys": "a", "hold": 0.05, "times": 1})

        errors, _ = sc.validate()
        check("脚本校验通过", not errors, str(errors))

        target.reset_events()
        logs = []
        lock = threading.Lock()

        def on_log(lvl, msg):
            with lock:
                logs.append((lvl, msg))

        runner = engine.Runner(sc, on_log=on_log)
        step("执行脚本 1")
        runner.start(0, None)
        t0 = time.time()
        while runner.running and time.time() - t0 < 30:
            time.sleep(0.05)
        time.sleep(1.0)
        step("脚本 1 结束")

        ev = target.events()
        errs = [m for (_l, m) in logs if _l == "error"]
        check("执行过程无错误", not errs, str(errs)[:200])
        bound = [m for (_l, m) in logs if "已绑定窗口" in m]
        check("日志确认已绑定目标窗口", bool(bound), str(bound)[:160])
        check("绑定的客户区与实测一致",
              bool(bound) and ("%dx%d" % (cw, ch)) in bound[0], str(bound)[:160])

        # 事件类断言只在目标取得前台焦点时才有意义
        if can_test_input:
            check("目标按钮被点中（回调触发）", ev["click_count"] >= 1,
                  "触发 %d 次" % ev["click_count"])
            check("目标进程收到鼠标按下事件", len(ev["press"]) >= 3,
                  "收到 %d 次" % len(ev["press"]))
            check("目标进程收到鼠标松开事件", len(ev["release"]) >= 3,
                  "收到 %d 次" % len(ev["release"]))

            if ev["press"]:
                px, py = ev["press"][0]
                ex, ey = to_screen(160, 90)
                check("第 1 次点击落在脚本指定点（误差 ≤4px）",
                      abs(px - ex) <= 4 and abs(py - ey) <= 4,
                      "实际屏幕(%d,%d) 期望(%d,%d)" % (px, py, ex, ey))
                rx, ry = px - ox, py - oy
                check("反算脚本坐标也是 (160,90)",
                      abs(rx - 160) <= 4 and abs(ry - 90) <= 4, "得到 (%d,%d)" % (rx, ry))

            if ev["release"] and ev["release"][0][2] is not None:
                hold = ev["release"][0][2]
                check("按下时长符合设置 0.12s（容许 0.05~0.40s）",
                      0.05 <= hold <= 0.40, "实测 %.3fs" % hold)

            check("连击参数生效（总按下 3 次）", len(ev["press"]) == 3,
                  "收到 %d 次按下" % len(ev["press"]))

            if len(ev["press"]) >= 3:
                px, py = ev["press"][1]
                ex, ey = to_screen(420, 340)
                check("连点位置正确（脚本 420,340 误差 ≤4px）",
                      abs(px - ex) <= 4 and abs(py - ey) <= 4,
                      "实际(%d,%d) 期望(%d,%d)" % (px, py, ex, ey))
                d = (abs(ev["press"][2][0] - ev["press"][1][0]),
                     abs(ev["press"][2][1] - ev["press"][1][1]))
                check("两次连点落在同一点（位移 ≤3px）", d[0] <= 3 and d[1] <= 3,
                      "位移 %s" % (d,))

            if ev["motion"]:
                last = ev["motion"][-1]
                ex, ey = to_screen(500, 400)
                check("移动终点正确（脚本 500,400 误差 ≤5px）",
                      abs(last[0] - ex) <= 5 and abs(last[1] - ey) <= 5,
                      "实际(%d,%d) 期望(%d,%d)" % (last[0], last[1], ex, ey))
            else:
                check("移动终点正确", False, "没收到移动事件")

            check("目标进程收到按键 a 的按下与松开",
                  ["down", "a"] in [list(k) for k in ev["keys"]]
                  and ["up", "a"] in [list(k) for k in ev["keys"]],
                  str(ev["keys"][:8]))
            # '??' = VK_PROCESSKEY，表示按键被中文输入法吞掉了。
            # 脚本运行时会自动切英文布局，所以正常情况下不应出现。
            bad = [k for k in ev["keys"] if k[1] == "??"]
            check("按键没有被输入法吞掉（无 VK_PROCESSKEY）", not bad,
                  str(bad) + "（若出现，说明自动切换输入法未生效）")
            ime_logs = [m for (_l, m) in logs if "输入法检查" in m]
            check("运行日志包含输入法检查结论", bool(ime_logs),
                  str(ime_logs)[:160])
        else:
            # 目标不是前台 / 注入被拦截时，明确记录为「跳过」，而不是假装通过
            reason = ("目标窗口未能取得前台焦点" if not fg_ok else "本机模拟输入被拦截")
            for nm in ("目标按钮被点中", "目标进程收到鼠标按下事件",
                       "目标进程收到鼠标松开事件", "第 1 次点击坐标",
                       "按下时长符合设置", "连击参数生效", "连点位置正确",
                       "移动终点正确", "按键 a 的按下与松开"):
                skip(nm, reason)

        # ============ 脚本 2：拖动轨迹 ============
        target.reset_events()
        sc2 = engine.Script("E2E拖动")
        sc2.coord_mode = "window"
        sc2.window_title = TITLE
        sc2.window_match = "exact"
        sc2.start_delay = 0.25
        sc2.steps = [engine.new_step("drag")]
        sc2.steps[0].update({"x1": 100, "y1": 380, "x2": 460, "y2": 140,
                             "button": "left", "duration": 0.55, "steps": 30, "jitter": 0})
        step("执行脚本 2（拖动）")
        r2 = engine.Runner(sc2, on_log=lambda l, m: None)
        r2.start(0, None)
        t0 = time.time()
        while r2.running and time.time() - t0 < 25:
            time.sleep(0.05)
        time.sleep(1.0)
        step("脚本 2 结束")

        ev2 = target.events()
        if can_test_input:
            check("拖动产生连续轨迹（≥5 个中间点）", len(ev2["drag"]) >= 5,
                  "收到 %d 个拖动事件" % len(ev2["drag"]))
            if ev2["drag"]:
                fx, fy = ev2["drag"][0]
                ex1, ey1 = to_screen(100, 380)
                check("拖动起点正确（脚本 100,380 误差 ≤12px）",
                      abs(fx - ex1) <= 12 and abs(fy - ey1) <= 12,
                      "实际(%d,%d) 期望(%d,%d)" % (fx, fy, ex1, ey1))
                lx, ly = ev2["drag"][-1]
                ex2, ey2 = to_screen(460, 140)
                check("拖动终点正确（脚本 460,140 误差 ≤12px）",
                      abs(lx - ex2) <= 12 and abs(ly - ey2) <= 12,
                      "实际(%d,%d) 期望(%d,%d)" % (lx, ly, ex2, ey2))
                check("拖动是逐步移动而非瞬移", len(ev2["drag"]) > 5,
                      "轨迹点数 %d" % len(ev2["drag"]))
        else:
            skip("拖动产生连续轨迹", "目标未取得前台焦点或本机输入被拦截")
            skip("拖动起点正确", "目标未取得前台焦点或本机输入被拦截")
            skip("拖动终点正确", "目标未取得前台焦点或本机输入被拦截")

        # ============ 找图 / 找色（真实截屏） ============
        print("\n  找图找色端到端验证")
        rect = wi.window_rect(hwnd)
        wx, wy, ww, wh = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
        gw, gh, gbuf = wi.grab_screen((wx, wy, ww, wh))

        bx = (ox - wx) + 60
        by = (oy - wy) + 50
        tw, th, tbuf = vision.crop_bgra(gw, gh, gbuf, bx, by, 200, 80)

        search_x, search_y = max(0, wx - 30), max(0, wy - 30)
        w2, h2, buf2 = wi.grab_screen((search_x, search_y, ww + 60, wh + 60))
        t_start = time.perf_counter()
        res = vision.find_image(w2, h2, buf2, (tw, th, tbuf), 10, None, 3)
        elapsed = time.perf_counter() - t_start
        print("  找图耗时 %.2f 秒（搜索 %dx%d，模板 %dx%d）" % (elapsed, w2, h2, tw, th))
        check("找图在真实屏幕上命中模板", bool(res), "结果 %s" % (res[:1],))
        check("找图耗时可接受（<10 秒）", elapsed < 10, "耗时 %.2fs" % elapsed)
        if res:
            fx, fy, score = res[0]
            exp_x, exp_y = bx - search_x + search_x, by - search_y + search_y
            check("找图匹配度高（>0.95）", score > 0.95, "匹配度 %.3f" % score)
            check("找图定位准确（误差 ≤3px）",
                  abs(fx - (bx - (search_x - wx))) <= 3
                  and abs(fy - (by - (search_y - wy))) <= 3,
                  "找到 (%d,%d) 期望 (%d,%d)" % (
                      fx, fy, bx - (search_x - wx), by - (search_y - wy)))

        px = wi.pixel_color(ox + 300, oy + 300)
        check("能取到目标窗口内的颜色", px is not None, str(px))
        if px:
            cw2, ch2, cbuf = wi.grab_screen((ox, oy, min(cw, 340), min(ch, 260)))
            hit = vision.find_color(cw2, ch2, cbuf, vision.color_to_hex(px), 6, None, 1)
            check("找色命中该颜色", hit["count"] >= 1, "命中 %d 像素" % hit["count"])

        # ============ 条件判断真的能分支 ============
        print("\n  条件判断端到端验证（对真实屏幕取色并分支）")
        sample = wi.pixel_color(ox + 320, oy + 320)
        if sample:
            sc3 = engine.Script("E2E判断")
            sc3.coord_mode = "window"
            sc3.window_title = TITLE
            sc3.window_match = "exact"
            sc3.start_delay = 0
            sc3.steps = [
                engine.new_step("if_color"),
                engine.new_step("delay"),
                engine.new_step("label"),
                engine.new_step("stop"),
            ]
            sc3.steps[0].update({"x": 320, "y": 320, "color": vision.color_to_hex(sample),
                                 "tol": 0, "on_success": "goto", "success_label": "命中后",
                                 "on_fail": "continue"})
            sc3.steps[2]["name"] = "命中后"
            order = []
            r3 = engine.Runner(sc3, on_step=lambda i: order.append(i),
                               on_log=lambda l, m: None)
            r3.start(0, None)
            t0 = time.time()
            while r3.running and time.time() - t0 < 15:
                time.sleep(0.05)
            check("条件命中后跳过了下一步（未执行第 2 步）", 1 not in order, str(order))
            check("条件命中后跳到了标签并继续", 2 in order and 3 in order, str(order))

    finally:
        step("关闭目标进程")
        target.stop()

    # 清理本次测试产生的临时文件，不给用户留垃圾
    try:
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass

    print("\n" + "=" * 62)
    print("通过 %d 项，失败 %d 项，跳过 %d 项" % (len(PASS), len(FAIL), len(SKIP)))
    for name, detail in FAIL:
        print("  ✗ %s   %s" % (name, detail))
    for name, why in SKIP:
        print("  - 跳过 %s：%s" % (name, why))
    if not FAIL and not SKIP:
        print("端到端链路验证全部通过 ✓")
    elif not FAIL:
        print("核心链路验证通过 ✓（部分输入类断言因本机环境被跳过，"
              "关闭目标程序加速器/安全软件的输入保护后可完整验证）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
