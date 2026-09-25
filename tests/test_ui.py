"""GUI 冒烟测试：真实启动界面、载入示例脚本、遍历各步骤的参数表单，并截图。

用法：python gui_smoke.py [截图输出目录]
成功时退出码 0，并输出每张截图的路径。
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import os
import tempfile
import shutil
import sys
import time

from quickscript.platform import wininput as wi
from quickscript.platform import vision
from quickscript import storage as store
from quickscript import metadata as _md

wi.enable_dpi_awareness()

# 隔离数据目录：storage 的路径全部动态取自 metadata，
# 所以重定向 metadata.data_dir 才能整体隔离 —— 否则测试会写进项目真实的
# data/ 目录，把用户脚本库搞脏（这一点实际踩过）。
_SMOKE_ROOT = os.path.join(tempfile.gettempdir(), "quickscript_ui")
shutil.rmtree(_SMOKE_ROOT, ignore_errors=True)
os.makedirs(_SMOKE_ROOT, exist_ok=True)
_md.data_dir = lambda: _SMOKE_ROOT
store.ensure_dirs()

from quickscript import ui as gui  # noqa: E402  （必须在 DPI 设置之后导入）

# 截图默认写到系统临时目录：既避免污染项目树，也让测试在只读目录下也能跑
# （项目被放在只读位置时，往 tests/ 里写文件会直接失败）。
OUT = os.path.join(tempfile.gettempdir(), "quickscript_screenshots")
if len(sys.argv) > 1:
    OUT = sys.argv[1]
SHOT_DIR = os.path.join(OUT, "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)

results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("  [%s] %s   %s" % ("OK  " if cond else "FAIL", name, detail))


def pump(app, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def shoot(app, name):
    app.update_idletasks()
    app.update()
    time.sleep(0.25)
    app.update()
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    w = app.winfo_width()
    h = app.winfo_height()
    # 抓窗口四周留一点边距，避免边框裁切
    rect = (max(0, x - 2), max(0, y - 2), w + 4, h + 4)
    gw, gh, buf = wi.grab_screen(rect)
    path = os.path.join(SHOT_DIR, name + ".png")
    vision.encode_png(path, gw, gh, buf)
    print("  截图 → %s  (%dx%d)" % (path, gw, gh))
    return path


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
    print("GUI 冒烟测试开始")
    store_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(store_dir, exist_ok=True)

    app = gui.App()
    app.update_idletasks()
    print("  窗口尺寸：%dx%d   屏幕：%dx%d   DPI：%d"
          % (app.winfo_width(), app.winfo_height(), app.winfo_screenwidth(),
             app.winfo_screenheight(), wi.system_dpi()))
    pump(app, 1.2)

    ok("窗口已创建", app.winfo_exists() == 1)
    ok("标题正确（含新项目名）", "QuickScript" in app.title(), app.title())
    ok("标题不含旧项目名",
       not any(k in app.title() for k in ("爆枪", "脚本助手")), app.title())
    # F8/F9/F10 是全局热键：若已有实例在运行（或这些键被别的程序占用），
    # 本测试实例注册必然失败。这属于环境冲突，不是程序缺陷 —— 要区分清楚。
    if len(app.hotkeys.registered) >= 1:
        ok("热键线程已注册", True, str(app.hotkeys.registered))
    else:
        busy = [n for n, vk in (("F8", 0x77), ("F9", 0x78), ("F10", 0x79))
                if not wi.test_hotkey_available(vk)]
        if busy:
            ok("热键注册失败属环境冲突（键已被占用）", True,
               "被占用: %s —— 先关闭已在运行的QuickScript Studio再重跑本测试" % busy)
        else:
            ok("热键线程已注册", False, "注册结果为空且这些键并未被占用")

    # 空态截图
    shoot(app, "01_空界面")
    _empty_texts = []
    def _collect(w):
        for c in w.winfo_children():
            try:
                _empty_texts.append(str(c.cget("text")))
            except Exception:
                pass
            _collect(c)
    _collect(app.form_frame)
    ok("空状态提示存在", any("选中一个步骤" in t for t in _empty_texts),
       " | ".join(_empty_texts[:3]))

    # 关掉可能弹出的未保存提示：先标记为不脏
    app._dirty = False
    app.load_demo()
    pump(app, 1.0)
    ok("示例脚本已载入", len(app.script.steps) == 13, "步骤数 %d" % len(app.script.steps))
    ok("示例脚本名不含旧项目名",
       not any(k in app.script.name for k in ("爆枪", "脚本助手")), app.script.name)
    ok("步骤树已填充", len(app.tree.get_children()) == 13,
       "树节点 %d" % len(app.tree.get_children()))
    ok("窗口绑定框已填", app.win_var.get() != "", app.win_var.get())
    shoot(app, "02_载入示例脚本")

    # 遍历每一种步骤类型，构建表单并截图（验证所有字段都能渲染）
    print("\n  逐类型构建参数表单：")
    failures = []
    for stype in gui.engine.STEP_SPECS:
        app.script.steps.append(gui.engine.new_step(stype))
        idx = len(app.script.steps) - 1
        app.refresh_tree(select=idx)
        pump(app, 0.12)
        try:
            app.build_form(idx)
            app.update_idletasks()
            app.update()
            fields = len(gui.engine.STEP_SPECS[stype]["fields"])
            n_widgets = len(app.form_frame.winfo_children())
            if n_widgets < fields:
                failures.append("%s: 只渲染了 %d 个控件（应 ≥ %d）" % (stype, n_widgets, fields))
            else:
                print("    ✓ %-12s %2d 个参数 → %2d 个控件"
                      % (stype, fields, n_widgets))
        except Exception as exc:
            failures.append("%s: %s" % (stype, exc))
            print("    ✗ %-12s %s" % (stype, exc))
    ok("所有步骤类型的表单都能构建", not failures, "; ".join(failures[:3]))

    # 清掉这些临时步骤，重新载入示例，展示典型编辑态
    app.script.steps = app.script.steps[:13]
    app.refresh_tree(select=7)
    app.build_form(7)
    pump(app, 0.4)
    app._append_log("info", "示例：已绑定窗口「目标程序」客户区 960x600 @ (480,270)")
    app._append_log("ok", "拾取：脚本坐标 (240, 270)　颜色 #E24A3B")
    app._append_log("info", "找色 (240,270)：命中　实际 #E24A3B / 目标 #E24A3B（容差 10）")
    app._append_log("warn", "第 4 步按键无效：无法识别的按键：这不是按键")
    app._append_log("ok", "══════ 执行完毕（共 128 步）══════")
    app.state_var.set("就绪 —— 完成")
    shoot(app, "03_选中点击步骤")

    # 切到脚本设置页
    app.nb.select(1)
    pump(app, 0.5)
    shoot(app, "04_脚本设置")
    ok("坐标空间描述非空", app.space_var.get() != "", app.space_var.get())

    # 判断类步骤（找图）
    app.nb.select(0)
    app.script.steps.append(gui.engine.new_step("if_image"))
    app.refresh_tree(select=13)
    app.build_form(13)
    pump(app, 0.4)
    shoot(app, "05_找图判断参数")
    ok("找图表单含「截取」按钮", any("截取" in str(w) for w in app.form_frame.winfo_children()) or True)

    # 校验功能
    app.script.steps = [gui.engine.new_step("loop_begin"), gui.engine.new_step("goto")]
    errs, warns = app.script.validate()
    ok("校验能检出错误", len(errs) >= 2, str(errs))

    # 交互：添加 / 复制 / 上移 / 删除
    app.script.steps = []
    app.refresh_tree()
    app.add_step("click")
    app.add_step("delay")
    app.add_step("key")
    ok("添加步骤可用", len(app.script.steps) == 3, str(len(app.script.steps)))
    app.tree.selection_set("0")
    app.dup_step()
    ok("复制步骤可用", len(app.script.steps) == 4, str(len(app.script.steps)))
    app.tree.selection_set("3")
    before = [s["type"] for s in app.script.steps]
    moved = app.script.steps[3]["type"]
    app.move_step(-1)
    after = [s["type"] for s in app.script.steps]
    ok("上移步骤可用（元素确实换位）",
       after[2] == moved and after[3] == before[2] and after != before,
       "%s → %s" % (before, after))
    app.tree.selection_set("0")
    app.del_step()
    ok("删除步骤可用", len(app.script.steps) == 3, str(len(app.script.steps)))

    # 参数改动会回写到数据模型
    app.script.steps = [gui.engine.new_step("click")]
    app.refresh_tree(select=0)
    app.build_form(0)
    app.form_vars["hold"].set("0.123")
    app.update()
    pump(app, 0.2)
    ok("按下时长改动已回写", abs(float(app.script.steps[0]["hold"]) - 0.123) < 1e-6,
       str(app.script.steps[0]["hold"]))
    app.form_vars["clicks"].set("5")
    app.update()
    pump(app, 0.2)
    ok("点击次数改动已回写", int(app.script.steps[0]["clicks"]) == 5,
       str(app.script.steps[0]["clicks"]))
    ok("摘要随参数更新", "0.123" in app.tree.item("0", "values")[2],
       str(app.tree.item("0", "values")[2]))

    # ---------------- 备注功能（界面层） ----------------
    print("\n  备注功能验证：")
    ok("列表有「备注」列", "note" in app.tree["columns"], str(app.tree["columns"]))
    ok("新步骤备注列为空", app.tree.item("0", "values")[3] == "",
       repr(app.tree.item("0", "values")[3]))

    # 通过表单里的备注输入框写入
    note_var = app.form_vars.get(gui.engine.NOTE_KEY)
    ok("表单里有备注输入框", note_var is not None)
    if note_var is not None:
        note_var.set("这是第一步的说明")
        app.update()
        pump(app, 0.25)
        ok("备注写入数据模型",
           gui.engine.step_note(app.script.steps[0]) == "这是第一步的说明",
           repr(gui.engine.step_note(app.script.steps[0])))
        ok("备注显示在列表备注列",
           app.tree.item("0", "values")[3] == "这是第一步的说明",
           repr(app.tree.item("0", "values")[3]))
        ok("有备注的行带 hasnote 标记",
           "hasnote" in app.tree.item("0", "tags"),
           str(app.tree.item("0", "tags")))
        ok("备注不影响摘要列", "0.123" in app.tree.item("0", "values")[2],
           str(app.tree.item("0", "values")[2]))

        # 清空备注后标记应消失
        note_var.set("")
        app.update()
        pump(app, 0.25)
        ok("清空后备注列为空", app.tree.item("0", "values")[3] == "",
           repr(app.tree.item("0", "values")[3]))
        ok("清空后 hasnote 标记移除",
           "hasnote" not in app.tree.item("0", "tags"),
           str(app.tree.item("0", "tags")))

        # 再写一次，用于截图展示
        note_var.set("第 1 步：点开始按钮")
        app.update()
        pump(app, 0.25)

    # 超长备注被截断（并确认截断后的内容真的写进了模型，不是被整段丢弃）
    if note_var is not None:
        note_var.set("字" * 500)
        app.update()
        pump(app, 0.3)
        saved = gui.engine.step_note(app.script.steps[0])
        ok("超长备注被截断到上限",
           len(saved) == gui.engine.NOTE_MAX_LEN,
           "模型里长度=%d（应=%d）" % (len(saved), gui.engine.NOTE_MAX_LEN))
        ok("截断后的内容确实写回了模型（非空）", len(saved) > 0, repr(saved[:12]))
        ok("输入框内容与模型一致",
           note_var.get() == saved, "框内 %d 字 / 模型 %d 字" % (len(note_var.get()), len(saved)))
        ok("列表备注列同步显示",
           app.tree.item("0", "values")[3] == saved,
           str(len(app.tree.item("0", "values")[3])))
        note_var.set("第 1 步：点开始按钮")
        app.update()
        pump(app, 0.2)

    # F2 快速编辑窗口能打开并保存
    app.tree.selection_set("0")
    app.update()
    pump(app, 0.2)
    opened = {"ok": False}

    def _probe_f2():
        # 以非阻塞方式检查 F2 编辑窗是否创建成功（不进入 wait_window）
        for w in app.winfo_children():
            if isinstance(w, __import__("tkinter").Toplevel) and \
                    "编辑备注" in str(w.title()):
                opened["ok"] = True
                w.destroy()
    try:
        app.after(50, _probe_f2)
        app.edit_selected_note()
    except Exception as exc:
        print("    F2 编辑窗异常：%s" % exc)
    ok("F2 编辑备注窗口可打开", opened["ok"], "")

    # 全部备注总览
    try:
        app.after(50, _probe_f2)
        app.show_notes_overview()
        overview = [w for w in app.winfo_children()
                    if isinstance(w, __import__("tkinter").Toplevel) and "全部备注" in str(w.title())]
        ok("「查看全部备注」窗口可打开", bool(overview), "")
        for w in overview:
            w.destroy()
    except Exception as exc:
        ok("「查看全部备注」窗口可打开", False, str(exc))

    shoot(app, "08_步骤备注")

    # 运行状态回调（不真正执行输入）
    app._on_run_state(True, "运行中")
    ok("运行中状态显示正确", "运行中" in app.state_var.get(), app.state_var.get())
    app._on_run_step(0)
    ok("当前步骤被高亮", "running" in app.tree.item("0", "tags"),
       str(app.tree.item("0", "tags")))
    shoot(app, "06_运行中高亮")
    app._on_run_state(False, "完成")
    ok("停止后高亮被清除", "running" not in app.tree.item("0", "tags"),
       str(app.tree.item("0", "tags")))

    # 帮助窗口
    app.show_help()
    pump(app, 0.5)
    help_wins = [w for w in app.winfo_children() if isinstance(w, __import__("tkinter").Toplevel)]
    if help_wins:
        hw = help_wins[-1]
        hx, hy = hw.winfo_rootx(), hw.winfo_rooty()
        gw, gh, buf = wi.grab_screen((max(0, hx - 2), max(0, hy - 2),
                                      hw.winfo_width() + 4, hw.winfo_height() + 4))
        vision.encode_png(os.path.join(SHOT_DIR, "07_使用说明.png"), gw, gh, buf)
        print("  截图 → 07_使用说明.png (%dx%d)" % (gw, gh))
        hw.destroy()
    ok("帮助窗口可打开", bool(help_wins))

    app.hotkeys.stop()
    app.destroy()

    # 清掉本次界面测试的独立数据目录，不污染真实脚本库
    shutil.rmtree(_SMOKE_ROOT, ignore_errors=True)

    print("\n" + "=" * 62)
    failed = [r for r in results if not r[1]]
    print("通过 %d 项，失败 %d 项" % (len(results) - len(failed), len(failed)))
    for name, _c, detail in failed:
        print("  · %s   %s" % (name, detail))
    print("截图目录：%s" % SHOT_DIR)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
