# -*- coding: utf-8 -*-
"""QuickScript Studio —— 图形界面

三栏布局：
  左  = 步骤工具箱（鼠标 / 键盘 / 判断 / 流程）
  中  = 步骤列表（可增删排序、单步测试、从某步开始运行）
  右  = 当前步骤的参数（全部可编辑）+ 脚本全局设置
  下  = 运行日志

全局热键：F8 拾取坐标/取色，F9 开始运行，F10 紧急停止。
"""
from __future__ import annotations

import os
import queue
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import compat as engine
from .metadata import (APP_NAME, APP_NAME_EN, VERSION,
                       about_text, version_string)
from . import storage as store
from .platform import vision
from .platform import wininput as wi
from .platform.overlays import PickBar, RegionCapture

UI = "Microsoft YaHei UI"
MONO = "Consolas"

TAG_COLORS = {
    "info": "#c9d1d9", "ok": "#6dd58c", "warn": "#e3b341", "error": "#ff7b72",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("QuickScript Studio")
        # 窗口尺寸按实际屏幕自适应：至少 1100x700，最大不超过屏幕可用区域
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = max(1100, min(1500, int(sw * 0.86)))
        h = max(700, min(920, int(sh * 0.88)))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.minsize(1040, 660)

        self.library = store.ScriptLibrary()
        self.script = self._initial_script()
        self.runner = None
        self.pickbar = None
        self.pick_target = None          # ("point"|"color", 回调)
        self.running_index = None
        self._loading_form = False
        self._dirty = False
        self.queue = queue.Queue()

        self._build_style()
        self._build_menu()
        # 主窗口用 grid 布局：工具栏 / 主体 / 日志 / 状态栏 各占一行，
        # 只有主体那一行带权重，这样日志永远不会被挤出窗口。
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_toolbar()
        self._build_body()
        self._build_log()
        self._build_statusbar()

        self.refresh_script_list()
        self.refresh_tree()
        self._refresh_space()
        # 脚本为空时 refresh_tree 不会选中任何步骤，右侧参数面板会是空白。
        # 这里显式渲染一次空状态提示，告诉用户下一步该做什么。
        if not self.script.steps:
            self._clear_form()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.hotkeys = wi.HotkeyManager(
            {
                1: (0, wi.vk_of("F8"), lambda: self.queue.put(("hotkey", "pick")), "F8"),
                2: (0, wi.vk_of("F9"), lambda: self.queue.put(("hotkey", "start")), "F9"),
                3: (0, wi.vk_of("F10"), lambda: self.queue.put(("hotkey", "stop")), "F10"),
            },
            on_error=lambda m: self.queue.put(("log", "warn", m)))
        self.hotkeys.start()
        self.hotkeys.wait_ready()

        self.log("info", "欢迎使用QuickScript Studio。")
        self.log("info", "流程：绑定目标窗口 → 用 F8 拾取坐标 → 在中间添加步骤并填参数 → F9 运行，F10 急停。")
        if not self.library.names():
            self.log("warn", "脚本库还是空的，点左上角「新建」开始，或从「帮助 → 载入示例脚本」看看效果。")

        self.after(60, self._drain_queue)
        self.after(120, self._tick)
        # 启动后自动做一次模拟输入自检，尽早发现问题（不弹窗，只写日志）
        self.after(900, self._startup_env_check)

    def _startup_env_check(self):
        try:
            ok, why = wi.test_input_injection()
        except Exception:
            return
        if ok:
            self.log("ok", "环境自检：模拟输入正常。")
        else:
            self.log("error", "环境自检：模拟输入被拦截！脚本会跑完但目标程序没反应。")
            self.log("error", why.replace("\n", "　"))
            self.log("warn", "请点「帮助 → 环境自检」查看详情并按其建议处理。")

        # 权限检查：目标程序是管理员权限时必须提权，否则切换窗口后输入全部失效
        if not wi.is_admin():
            self.log("warn", "当前以普通权限运行。若目标程序是管理员权限，"
                             "切换窗口后点击会无效 —— 请用「以管理员身份启动.bat」。")
        else:
            self.log("ok", "已以管理员身份运行，可操作管理员权限的目标程序。")

    # ==================================================================
    # 初始化
    # ==================================================================
    def _initial_script(self):
        cur = self.library.current()
        if cur:
            try:
                return self.library.load(cur)
            except Exception:
                pass
            self.library.set_current("")
        return engine.Script()

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(UI, 9))
        style.configure("TFrame", background="#f4f5f7")
        style.configure("TLabel", background="#f4f5f7", foreground="#1f2328")
        style.configure("TLabelframe", background="#f4f5f7")
        style.configure("TLabelframe.Label", background="#f4f5f7", foreground="#0b5cad",
                        font=(UI, 9, "bold"))
        style.configure("TButton", padding=(8, 4))
        style.configure("Tool.TButton", padding=(7, 5))
        style.configure("Accent.TButton", padding=(10, 5), font=(UI, 9, "bold"))
        style.configure("Treeview", rowheight=24, font=(UI, 9), background="white",
                        fieldbackground="white")
        style.configure("Treeview.Heading", font=(UI, 9, "bold"), padding=(4, 5))
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.map("Treeview", background=[("selected", "#0b5cad")],
                  foreground=[("selected", "white")])

    def _build_menu(self):
        bar = tk.Menu(self)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="新建脚本", accelerator="Ctrl+N", command=self.new_script)
        m.add_command(label="打开…", accelerator="Ctrl+O", command=self.open_script)
        m.add_separator()
        m.add_command(label="保存", accelerator="Ctrl+S", command=self.save_script)
        m.add_command(label="另存为…", command=self.save_script_as)
        m.add_command(label="重命名…", command=self.rename_script)
        m.add_command(label="删除当前脚本", command=self.delete_script)
        m.add_separator()
        m.add_command(label="导入脚本 (JSON)…", command=self.import_script)
        m.add_command(label="导出当前脚本 (JSON)…", command=self.export_script)
        m.add_separator()
        m.add_command(label="退出", command=self.on_close)
        bar.add_cascade(label="文件", menu=m)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="添加：移动鼠标", command=lambda: self.add_step("move"))
        m.add_command(label="添加：点击", command=lambda: self.add_step("click"))
        m.add_command(label="添加：等待", command=lambda: self.add_step("delay"))
        m.add_separator()
        m.add_command(label="拾取坐标 / 取色 (F8)", command=self.begin_pick_for_selection)
        m.add_command(label="截取找图模板…", command=self.capture_template)
        m.add_command(label="框选搜索区域…", command=self.capture_region_into_field)
        m.add_separator()
        m.add_command(label="测试选中步骤", command=self.test_selected_step)
        m.add_command(label="从选中步骤开始运行", command=self.run_from_selected)
        m.add_separator()
        m.add_command(label="编辑选中步骤的备注", accelerator="F2",
                      command=self.edit_selected_note)
        m.add_command(label="查看全部备注…", command=self.show_notes_overview)
        m.add_separator()
        m.add_command(label="批量清空所有备注…", command=self.clear_all_notes)
        bar.add_cascade(label="工具", menu=m)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="运行脚本 (F9)", command=self.run_script)
        m.add_command(label="紧急停止 (F10)", command=self.stop_script)
        bar.add_cascade(label="运行", menu=m)

        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="载入示例脚本（目标程序）", command=self.load_demo)
        m.add_command(label="环境自检（模拟输入 / 输入法 / 热键）", command=self.env_check)
        m.add_command(label="打开数据目录", command=self.open_data_dir)
        m.add_separator()
        m.add_command(label="使用说明", command=self.show_help)
        m.add_command(label="关于", command=self.show_about)
        bar.add_cascade(label="帮助", menu=m)

        self.config(menu=bar)
        self.bind_all("<Control-n>", lambda e: self.new_script())
        self.bind_all("<Control-o>", lambda e: self.open_script())
        self.bind_all("<Control-s>", lambda e: self.save_script())
        self.bind_all("<F2>", lambda e: self.edit_selected_note())
        self.bind_all("<Delete>", self._on_delete_key)

    def _build_toolbar(self):
        # 工具栏拆成两行：脚本管理 / 窗口绑定。
        # 分成两行后即使在高 DPI（字体更大）下也不会被挤出窗口。
        holder = tk.Frame(self, bg="#e8eaed")
        holder.grid(row=0, column=0, sticky="ew")
        bar = tk.Frame(holder, bg="#e8eaed", padx=8, pady=4)
        bar.pack(fill="x", pady=(4, 0))

        tk.Label(bar, text="脚本：", bg="#e8eaed", font=(UI, 9, "bold")).pack(side="left")
        self.script_var = tk.StringVar()
        self.script_combo = ttk.Combobox(bar, textvariable=self.script_var, width=22,
                                         state="readonly")
        self.script_combo.pack(side="left", padx=(0, 6))
        self.script_combo.bind("<<ComboboxSelected>>", lambda e: self.on_script_combo())

        for text, cmd, style in (("新建", self.new_script, "Tool.TButton"),
                                 ("保存", self.save_script, "Tool.TButton"),
                                 ("另存为", self.save_script_as, "Tool.TButton"),
                                 ("重命名", self.rename_script, "Tool.TButton"),
                                 ("删除", self.delete_script, "Tool.TButton")):
            ttk.Button(bar, text=text, command=cmd, style=style).pack(side="left", padx=1)

        bar2 = tk.Frame(holder, bg="#e8eaed", padx=8, pady=4)
        bar2.pack(fill="x", pady=(0, 4))
        tk.Label(bar2, text="绑定窗口：", bg="#e8eaed", font=(UI, 9, "bold")).pack(side="left")
        self.win_var = tk.StringVar()
        self.win_entry = ttk.Entry(bar2, textvariable=self.win_var, width=18)
        self.win_entry.pack(side="left", padx=(0, 3))
        self.win_var.trace_add("write", lambda *a: self.on_setting_change("window_title"))

        self.win_pick_combo = ttk.Combobox(bar2, width=26, state="readonly")
        self.win_pick_combo.pack(side="left", padx=(0, 3))
        self.win_pick_combo.bind("<<ComboboxSelected>>", lambda e: self.on_pick_window())
        ttk.Button(bar2, text="刷新窗口列表", command=self.refresh_window_list,
                   style="Tool.TButton").pack(side="left")
        ttk.Button(bar2, text="取前台窗口", command=self.take_foreground,
                   style="Tool.TButton").pack(side="left", padx=2)

        ttk.Separator(bar2, orient="vertical").pack(side="left", fill="y", padx=8)
        self.topmost_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="本工具置顶", variable=self.topmost_var,
                        command=self.apply_topmost).pack(side="left")
        self.space_var_top = tk.StringVar(value="")
        # 顶部状态文字可能很长，用固定宽度 + 左对齐，超出时由 Tk 截断而不是挤掉右边的按钮
        tk.Label(bar2, textvariable=self.space_var_top, bg="#e8eaed", fg="#1a7f37",
                 font=(UI, 8), anchor="e").pack(side="right", padx=(6, 0))

        self.refresh_window_list()

    def _build_body(self):
        body = tk.Frame(self, bg="#f4f5f7")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)   # 中间步骤列表吃掉所有富余宽度

        # ---------- 左：步骤工具箱（内容可能很长，做成可滚动） ----------
        left_outer = ttk.Labelframe(body, text="添加步骤", padding=4)
        left_outer.grid(row=0, column=0, sticky="nsw")
        left_canvas = tk.Canvas(left_outer, bg="#f4f5f7", highlightthickness=0,
                                width=214, height=420)
        left_sb = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(left_canvas)
        left_win = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: left_canvas.configure(
            scrollregion=left_canvas.bbox("all")))
        self._left_canvas = left_canvas
        for group in engine.GROUP_ORDER:
            box = ttk.Labelframe(left, text=group, padding=3)
            box.pack(fill="x", pady=2, padx=1)
            for stype, spec in engine.STEP_SPECS.items():
                if spec.get("group") != group:
                    continue
                b = ttk.Button(box, text="%s %s" % (spec.get("icon", ""),
                                                    engine.short_label(stype)),
                               style="Tool.TButton", width=17,
                               command=lambda t=stype: self.add_step(t))
                b.pack(fill="x", pady=1)
                b.bind("<Enter>", lambda e, t=stype: self._hint_step(t))
                b.bind("<Leave>", lambda e: self.hint_var.set(""))

        # ---------- 中：步骤列表 ----------
        mid = ttk.Frame(body)
        mid.grid(row=0, column=1, sticky="nsew", padx=8)

        # 工具条：运行按钮单独占一整行，编辑按钮用 3 列网格。
        # 这样按钮宽度无论多大（高 DPI）都不会被挤出窗口。
        tools = ttk.Frame(mid)
        tools.pack(fill="x", pady=(0, 4))

        self.run_from_btn = ttk.Button(tools, text="▶ 从选中步骤开始运行  (F9 运行整个脚本 / F10 停止)",
                                       command=self.run_from_selected, style="Accent.TButton")
        self.run_from_btn.pack(fill="x")

        # 每一行用独立的 frame，行内按钮均分整行宽度。
        # 这样按钮再宽（高 DPI 字体放大）也不会被截断或挤出窗口。
        row1 = ttk.Frame(tools)
        row1.pack(fill="x", pady=(3, 0))
        edit_specs = (("↑ 上移", lambda: self.move_step(-1)),
                      ("↓ 下移", lambda: self.move_step(1)),
                      ("复制", self.dup_step),
                      ("删除", self.del_step),
                      ("清空", self.clear_steps))
        for text, cmd in edit_specs:
            ttk.Button(row1, text=text, command=cmd, style="Tool.TButton").pack(
                side="left", fill="x", expand=True, padx=1)

        row2 = ttk.Frame(tools)
        row2.pack(fill="x", pady=(3, 0))
        run_specs = (("▶ 运行整个脚本 (F9)", self.run_script),
                     ("■ 紧急停止 (F10)", self.stop_script),
                     ("测试选中步骤", self.test_selected_step))
        for text, cmd in run_specs:
            ttk.Button(row2, text=text, command=cmd, style="Tool.TButton").pack(
                side="left", fill="x", expand=True, padx=1)

        wrap = ttk.Frame(mid)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=("no", "type", "desc", "note"),
                                 show="headings", selectmode="browse")
        self.tree.heading("no", text="#")
        self.tree.heading("type", text="类型")
        self.tree.heading("desc", text="内容")
        self.tree.heading("note", text="备注")
        self.tree.column("no", width=44, anchor="center", stretch=False)
        self.tree.column("type", width=126, anchor="w", stretch=False)
        self.tree.column("desc", width=380, anchor="w")
        self.tree.column("note", width=200, anchor="w")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_tree_select())
        self.tree.bind("<Double-1>", lambda e: self.test_selected_step())
        self.tree.tag_configure("running", background="#fff3cd")
        self.tree.tag_configure("odd", background="#fafbfc")
        self.tree.tag_configure("hasnote", foreground="#0b5cad")
        for grp, color in (("鼠标", "#0b5cad"), ("键盘", "#6f42c1"),
                           ("判断", "#b3541e"), ("流程", "#1a7f37")):
            self.tree.tag_configure("grp_" + grp, foreground=color)

        self.hint_var = tk.StringVar()
        tk.Label(mid, textvariable=self.hint_var, anchor="w", bg="#f4f5f7",
                 fg="#57606a", font=(UI, 8)).pack(fill="x", pady=(3, 0))

        # ---------- 右：参数 ----------
        right = ttk.Frame(body)
        right.grid(row=0, column=2, sticky="ns")
        self.nb = ttk.Notebook(right, width=488)
        self.nb.pack(fill="both", expand=True)

        step_tab = ttk.Frame(self.nb)
        self.nb.add(step_tab, text="步骤参数")
        self.form_canvas = tk.Canvas(step_tab, highlightthickness=0, bg="#f4f5f7")
        fvs = ttk.Scrollbar(step_tab, orient="vertical", command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=fvs.set)
        fvs.pack(side="right", fill="y")
        self.form_canvas.pack(side="left", fill="both", expand=True)
        self.form_frame = ttk.Frame(self.form_canvas)
        self._form_win = self.form_canvas.create_window((0, 0), window=self.form_frame, anchor="nw")
        self.form_frame.bind("<Configure>", lambda e: self.form_canvas.configure(
            scrollregion=self.form_canvas.bbox("all")))
        self.form_canvas.bind("<Configure>", lambda e: self.form_canvas.itemconfigure(
            self._form_win, width=e.width))
        self.form_canvas.bind_all("<MouseWheel>", self._on_wheel)

        cfg_tab = ttk.Frame(self.nb)
        self.nb.add(cfg_tab, text="脚本设置")
        self._build_settings(cfg_tab)
    def _build_log(self):
        # ---------- 底部日志 ----------
        bottom = ttk.Labelframe(self, text="运行日志", padding=4)
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        logbar = ttk.Frame(bottom)
        logbar.pack(fill="x")
        self.state_var = tk.StringVar(value="就绪")
        tk.Label(logbar, textvariable=self.state_var, bg="#f4f5f7", fg="#0b5cad",
                 font=(UI, 9, "bold")).pack(side="left")
        ttk.Button(logbar, text="清空日志", command=lambda: self.log_text.delete("1.0", "end"),
                   style="Tool.TButton").pack(side="right")
        self.log_text = tk.Text(bottom, height=7, bg="#0d1117", fg="#c9d1d9", bd=0,
                                font=(MONO, 9), wrap="none", insertbackground="#c9d1d9")
        lsb = ttk.Scrollbar(bottom, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set, state="disabled")
        lsb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)
        for name, color in TAG_COLORS.items():
            self.log_text.tag_configure(name, foreground=color)

    def _build_settings(self, parent):
        pad = {"padx": 8, "pady": 3}
        self.cfg_vars = {}

        # 设置页内容较多，同样做成可滚动，避免小窗口下被截断
        canvas = tk.Canvas(parent, bg="#f4f5f7", highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        self._cfg_canvas = canvas
        parent = inner

        box = ttk.Labelframe(parent, text="坐标与窗口", padding=6)
        box.pack(fill="x", **pad)

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        self.coord_var = tk.StringVar(value=self.script.coord_mode)
        ttk.Radiobutton(row, text="窗口相对坐标", value="window", variable=self.coord_var,
                        command=self.on_coord_mode).pack(side="left", padx=2)
        ttk.Radiobutton(row, text="屏幕绝对坐标", value="screen", variable=self.coord_var,
                        command=self.on_coord_mode).pack(side="left", padx=8)

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        tk.Label(row, text="窗口标题关键字：", bg="#f4f5f7").pack(side="left")
        self.win2_var = tk.StringVar(value=self.script.window_title)
        ttk.Entry(row, textvariable=self.win2_var).pack(side="left", fill="x", expand=True)
        self.win2_var.trace_add("write", lambda *a: self.on_setting_change("window_title"))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        tk.Label(row, text="匹配方式：", bg="#f4f5f7").pack(side="left")
        self.match_var = tk.StringVar(value=self.script.window_match)
        ttk.Combobox(row, textvariable=self.match_var, width=11, state="readonly",
                     values=["contains", "exact", "startswith"]).pack(side="left")
        self.match_var.trace_add("write", lambda *a: self.on_setting_change("window_match"))
        tk.Label(row, text="窗口类名：", bg="#f4f5f7").pack(side="left", padx=(8, 0))
        self.class_var = tk.StringVar(value=self.script.window_class)
        ttk.Entry(row, textvariable=self.class_var).pack(side="left", fill="x", expand=True)
        self.class_var.trace_add("write", lambda *a: self.on_setting_change("window_class"))

        self.front_var = tk.BooleanVar(value=self.script.bring_to_front)
        ttk.Checkbutton(box, text="运行时自动把目标窗口切到最前（推荐勾选）", variable=self.front_var,
                        command=lambda: self.on_setting_change("bring_to_front")).pack(anchor="w", pady=2)

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        self.fixed_var = tk.BooleanVar(value=self.script.use_fixed_origin)
        ttk.Checkbutton(row, text="使用固定原点（不跟随窗口）", variable=self.fixed_var,
                        command=self.on_fixed_toggle).pack(anchor="w")
        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        tk.Label(row2, text="原点  X:", bg="#f4f5f7").pack(side="left")
        self.ox_var = tk.StringVar(value=str(self.script.origin_x))
        ttk.Entry(row2, textvariable=self.ox_var, width=7).pack(side="left")
        tk.Label(row2, text="Y:", bg="#f4f5f7").pack(side="left")
        self.oy_var = tk.StringVar(value=str(self.script.origin_y))
        ttk.Entry(row2, textvariable=self.oy_var, width=7).pack(side="left")
        for v in (self.ox_var, self.oy_var):
            v.trace_add("write", lambda *a: self.on_setting_change("origin"))
        ttk.Button(row2, text="设为鼠标处", style="Tool.TButton",
                   command=self.set_origin_here).pack(side="left", padx=3)

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="用当前窗口客户区左上角设为原点", style="Tool.TButton",
                   command=self.set_origin_from_window).pack(side="left")
        ttk.Button(row, text="重新检测绑定", style="Tool.TButton",
                   command=self._refresh_space).pack(side="left", padx=4)

        self.space_var = tk.StringVar(value="")
        tk.Label(box, textvariable=self.space_var, bg="#f4f5f7", fg="#1a7f37",
                 font=(UI, 8), wraplength=390, justify="left").pack(anchor="w", pady=(3, 0))

        box2 = ttk.Labelframe(parent, text="运行节奏（真实感 / 防检测）", padding=6)
        box2.pack(fill="x", **pad)
        for label, attr, default in (
                ("开始前准备时间(秒)", "start_delay", 1.0),
                ("按下时长随机浮动(±秒)", "hold_jitter", 0.0),
                ("间隔随机浮动(±秒)", "delay_jitter", 0.0),
                ("每次点击后额外停顿(秒)", "move_after_click", 0.0)):
            row = ttk.Frame(box2)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg="#f4f5f7", anchor="w").pack(side="left")
            var = tk.StringVar(value=str(getattr(self.script, attr)))
            ttk.Entry(row, textvariable=var, width=9).pack(side="right")
            var.trace_add("write", lambda *a, k=attr: self.on_setting_change(k))
            self.cfg_vars[attr] = var

        box3 = ttk.Labelframe(parent, text="热键（全局有效）", padding=6)
        box3.pack(fill="x", **pad)
        for text in ("F8 = 拾取鼠标坐标 / 取色",
                     "F9 = 开始运行脚本",
                     "F10 = 紧急停止（会松开所有按住的键）"):
            tk.Label(box3, text=text, bg="#f4f5f7", anchor="w").pack(anchor="w")

        tk.Label(parent, text="提示：脚本坐标 = 屏幕坐标 − 原点。\n"
                              "原点默认取目标窗口客户区左上角，窗口移动或换分辨率后依旧可用。",
                 bg="#f4f5f7", fg="#57606a", justify="left", font=(UI, 8)).pack(anchor="w", padx=8, pady=6)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#d7dbe0", height=24)
        bar.grid(row=3, column=0, sticky="ew")
        self.mouse_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.mouse_var, bg="#d7dbe0", fg="#24292f",
                 font=(MONO, 9)).pack(side="left", padx=8)
        self.tip_var = tk.StringVar(value="F8 拾取坐标 · F9 运行 · F10 急停")
        tk.Label(bar, textvariable=self.tip_var, bg="#d7dbe0", fg="#57606a",
                 font=(UI, 9)).pack(side="right", padx=8)

    # ==================================================================
    # 定时任务：队列、鼠标位置、窗口原点
    # ==================================================================
    def _drain_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1], item[2])
                elif kind == "state":
                    self._on_run_state(item[1], item[2])
                elif kind == "step":
                    self._on_run_step(item[1])
                elif kind == "hotkey":
                    self._on_hotkey(item[1])
        except queue.Empty:
            pass
        except Exception:
            self._append_log("error", traceback.format_exc(limit=3))
        self.after(60, self._drain_queue)

    def _tick(self):
        try:
            x, y = wi.cursor_pos()
            sx, sy = self.space.to_script(x, y)
            self.mouse_var.set("鼠标 屏幕(%d, %d)   脚本(%d, %d)   [%s]" % (
                x, y, sx, sy, "屏幕绝对" if self.script.coord_mode == "screen" else "窗口相对"))
            if self.pickbar and self.pickbar.winfo_exists():
                self.pickbar.value_var.set("当前 (%d, %d)" % (sx, sy))
        except Exception:
            pass
        self.after(120, self._tick)

    def _refresh_space(self):
        try:
            self.space = engine.CoordSpace(self.script)
            bound = self.space.refresh(activate=False)
            text = self.space.describe()
            warn = ""
            if self.script.coord_mode == "window" and not bound and (
                    self.script.window_title or self.script.window_class):
                warn = "   ⚠ 未找到该窗口"
            self.space_var.set(text + warn)
            if hasattr(self, "space_var_top"):
                # 顶部条很窄，只放短摘要，完整信息在「脚本设置」里
                if self.script.coord_mode == "screen":
                    short, ok = "坐标：屏幕绝对", True
                elif bound:
                    short, ok = "坐标：已绑定窗口 %dx%d" % self.space.client_size, True
                elif self.script.use_fixed_origin:
                    short, ok = ("坐标：固定原点 (%d,%d)" % (self.script.origin_x,
                                                          self.script.origin_y)), True
                else:
                    # 没绑定窗口也没有固定原点 —— 这是要提醒用户的状态，不能打勾
                    short, ok = "坐标：未绑定窗口（按屏幕绝对坐标运行）", False
                if warn:
                    mark = "  ⚠"
                elif ok:
                    mark = "  ✓"
                else:
                    mark = "  ⚠"
                self.space_var_top.set(short + mark)
        except Exception as exc:
            self.space_var.set("坐标刷新失败：%s" % exc)
            if hasattr(self, "space_var_top"):
                self.space_var_top.set("坐标刷新失败")
        return self.space

    # ==================================================================
    # 脚本库
    # ==================================================================
    def refresh_script_list(self, select=None):
        names = self.library.names()
        self.script_combo["values"] = names
        target = select or self.script.name
        if target in names:
            self.script_var.set(target)
        elif names:
            self.script_var.set(names[0])
        else:
            self.script_var.set("")

    def on_script_combo(self):
        name = self.script_var.get()
        if not name or name == self.script.name:
            return
        if not self._confirm_discard():
            self.script_var.set(self.script.name)
            return
        try:
            self.script = self.library.load(name)
            self.library.set_current(name)
            self._load_script_into_ui()
            self.log("ok", "已打开脚本：%s" % name)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self)

    def _confirm_discard(self):
        if not self._dirty:
            return True
        ans = messagebox.askyesnocancel(
            "尚未保存", "当前脚本有未保存的修改，要先保存吗？", parent=self)
        if ans is None:
            return False
        if ans:
            return self.save_script()
        return True

    def _load_script_into_ui(self):
        sc = self.script
        self.win_var.set(sc.window_title)
        self.win2_var.set(sc.window_title)
        self.match_var.set(sc.window_match)
        self.class_var.set(sc.window_class)
        self.front_var.set(sc.bring_to_front)
        self.coord_var.set(sc.coord_mode)
        self.fixed_var.set(sc.use_fixed_origin)
        self.ox_var.set(str(sc.origin_x))
        self.oy_var.set(str(sc.origin_y))
        for attr, var in self.cfg_vars.items():
            var.set(str(getattr(sc, attr)))
        self.refresh_tree()
        self._refresh_space()
        self._dirty = False
        self._update_title()

    def _update_title(self):
        mark = " *" if self._dirty else ""
        self.title("QuickScript Studio —— %s%s" % (self.script.name, mark))

    def mark_dirty(self):
        self._dirty = True
        self._update_title()

    def new_script(self):
        if not self._confirm_discard():
            return
        name = self._ask_name("新建脚本", "给新脚本起个名字：", "新脚本")
        if not name:
            return
        if self.library.exists(name):
            messagebox.showwarning("重名", "已经有同名脚本了，请换个名字。", parent=self)
            return
        self.script = engine.Script(name)
        self.script.window_title = self.win_var.get().strip()
        try:
            self.library.save(self.script)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.refresh_script_list(select=name)
        self._load_script_into_ui()
        self.log("ok", "已新建脚本：%s" % name)

    def open_script(self):
        path = filedialog.askopenfilename(
            parent=self, title="打开脚本", initialdir=store.SCRIPT_DIR,
            filetypes=[("脚本文件", "*.json"), ("全部文件", "*.*")])
        if not path:
            return
        self.import_script(path)

    def save_script(self):
        try:
            self.script.name = store.safe_name(self.script.name)
            self.library.save(self.script)
            self.refresh_script_list(select=self.script.name)
            self._dirty = False
            self._update_title()
            self.log("ok", "已保存：%s" % self.script.name)
            return True
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return False

    def save_script_as(self):
        name = self._ask_name("另存为", "新脚本名：", self.script.name + " 副本")
        if not name:
            return
        name = store.safe_name(name)
        if self.library.exists(name):
            messagebox.showwarning("重名", "已经有同名脚本了。", parent=self)
            return
        self.script.name = name
        self.save_script()

    def rename_script(self):
        old = self.script.name
        name = self._ask_name("重命名", "新名字：", old)
        if not name or store.safe_name(name) == old:
            return
        try:
            new = self.library.rename(old, name)
            self.script = self.library.load(new)
            self.refresh_script_list(select=new)
            self._load_script_into_ui()
            self.log("ok", "已重命名为：%s" % new)
        except Exception as exc:
            messagebox.showerror("重命名失败", str(exc), parent=self)

    def delete_script(self):
        if not messagebox.askyesno("删除脚本", "确定删除「%s」吗？\n（会放进 data/trash 回收目录，可以手动恢复）"
                                   % self.script.name, parent=self):
            return
        try:
            self.library.delete(self.script.name)
            self.script = engine.Script()
            self.script.name = self.library.current() or engine.VALID_NAME
            if self.library.current():
                self.script = self.library.load(self.library.current())
            self.refresh_script_list()
            self._load_script_into_ui()
            self.log("warn", "脚本已删除。")
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self)

    def import_script(self, path=None):
        if not path:
            path = filedialog.askopenfilename(
                parent=self, title="导入脚本",
                filetypes=[("脚本文件", "*.json"), ("全部文件", "*.*")])
        if not path:
            return
        try:
            sc, name = self.library.import_from(path)
            self.script = sc
            self.refresh_script_list(select=name)
            self._load_script_into_ui()
            self.log("ok", "已导入脚本：%s（%d 个步骤）" % (name, len(sc.steps)))
            missing = [s.get("image") for s in sc.steps
                       if s["type"] == "if_image" and s.get("image")
                       and not os.path.isfile(str(s.get("image")))]
            if missing:
                self.log("warn", "有 %d 个找图步骤的模板图片不在本机，需要重新截取。" % len(missing))
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def export_script(self):
        if not self.script.steps:
            messagebox.showinfo("提示", "脚本是空的，没什么可导出的。", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="导出脚本", defaultextension=".json",
            initialfile=store.safe_name(self.script.name) + ".json",
            filetypes=[("脚本文件", "*.json")])
        if not path:
            return
        try:
            self.library.export_to(self.script, path)
            self.log("ok", "已导出到：%s" % path)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

    def _ask_name(self, title, prompt, initial=""):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        ttk.Label(dlg, text=prompt, padding=10).pack(anchor="w")
        var = tk.StringVar(value=initial)
        entry = ttk.Entry(dlg, textvariable=var, width=34)
        entry.pack(padx=10, pady=(0, 8))
        entry.focus_set()
        entry.select_range(0, "end")
        result = {"v": None}

        def ok(_e=None):
            result["v"] = var.get().strip()
            dlg.destroy()

        def cancel(_e=None):
            dlg.destroy()

        row = ttk.Frame(dlg)
        row.pack(pady=(0, 10))
        ttk.Button(row, text="确定", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="取消", command=cancel).pack(side="left", padx=4)
        entry.bind("<Return>", ok)
        dlg.bind("<Escape>", cancel)
        self.wait_window(dlg)
        return result["v"]

    # ==================================================================
    # 窗口绑定
    # ==================================================================
    def refresh_window_list(self):
        try:
            wins = wi.list_windows(include_hidden=False, skip_pid=os.getpid())
        except Exception:
            wins = []
        self._win_map = {}
        values = []
        for winfo in wins:
            title = winfo["title"]
            short = title if len(title) <= 42 else title[:42] + "…"
            label = "%s   [%s]" % (short, winfo["class"])
            values.append(label)
            self._win_map[label] = (title, winfo["class"])
        self.win_pick_combo["values"] = values

    def on_pick_window(self):
        label = self.win_pick_combo.get()
        info = getattr(self, "_win_map", {}).get(label)
        if not info:
            return
        title, cls = info
        self.win_var.set(title)
        self.win2_var.set(title)
        self.class_var.set(cls)
        self.script.window_match = "contains"
        self.match_var.set("contains")
        self.mark_dirty()
        self._refresh_space()
        self.log("ok", "已绑定窗口：「%s」" % title)

    def take_foreground(self):
        hwnd = wi.foreground_window()
        title = wi.window_title(hwnd)
        if not title:
            self.log("warn", "没能取到前台窗口（可能是本工具自己）。请先点一下目标窗口再按此按钮。")
            return
        self.win_var.set(title)
        self.win2_var.set(title)
        self.class_var.set(wi.window_class(hwnd))
        self.mark_dirty()
        self._refresh_space()
        self.log("ok", "已绑定前台窗口：「%s」" % title)

    def apply_topmost(self):
        try:
            self.attributes("-topmost", bool(self.topmost_var.get()))
        except Exception:
            pass

    # ==================================================================
    # 脚本设置变更
    # ==================================================================
    def on_coord_mode(self):
        self.script.coord_mode = self.coord_var.get()
        self.mark_dirty()
        self._refresh_space()

    def on_fixed_toggle(self):
        self.script.use_fixed_origin = bool(self.fixed_var.get())
        self.mark_dirty()
        self._refresh_space()

    def on_setting_change(self, key):
        sc = self.script
        try:
            if key == "window_title":
                sc.window_title = self.win_var.get()
                if self.win2_var.get() != sc.window_title:
                    self.win2_var.set(sc.window_title)
                self._refresh_space()
            elif key == "window_match":
                sc.window_match = self.match_var.get()
                self._refresh_space()
            elif key == "window_class":
                sc.window_class = self.class_var.get()
                self._refresh_space()
            elif key == "bring_to_front":
                sc.bring_to_front = bool(self.front_var.get())
            elif key == "origin":
                sc.origin_x = int(float(self.ox_var.get() or 0))
                sc.origin_y = int(float(self.oy_var.get() or 0))
                self._refresh_space()
            elif key in self.cfg_vars:
                setattr(sc, key, float(self.cfg_vars[key].get() or 0))
            self.mark_dirty()
        except ValueError:
            pass  # 用户正在输入，等下一次有效值

    def set_origin_here(self):
        x, y = wi.cursor_pos()
        self.ox_var.set(str(x))
        self.oy_var.set(str(y))
        self.fixed_var.set(True)
        self.on_fixed_toggle()
        self.log("ok", "固定原点设为 (%d, %d)" % (x, y))

    def set_origin_from_window(self):
        self.fixed_var.set(False)
        self.ox_var.set("0")
        self.oy_var.set("0")
        self.on_fixed_toggle()
        sp = self._refresh_space()
        if sp.hwnd:
            self.log("ok", "原点已跟随绑定窗口：客户区左上角 (%d, %d)" % sp.client_origin)
        else:
            self.log("warn", "没有绑定到窗口，请先绑定目标窗口。")

    # ==================================================================
    # 步骤列表
    # ==================================================================
    def add_step(self, stype):
        step = engine.new_step(stype)
        # 新步骤默认落在鼠标当前脚本坐标上，省得再拾取
        try:
            x, y = wi.cursor_pos()
            sx, sy = self.space.to_script(x, y)
            for k, v in (("x", sx), ("y", sy), ("x1", sx), ("y1", sy)):
                if k in step:
                    step[k] = v
            if stype == "drag":
                step["x2"] = step["x1"] + 120
                step["y2"] = step["y1"]
        except Exception:
            pass
        self.script.steps.append(step)
        self.refresh_tree(select=len(self.script.steps) - 1)
        self.mark_dirty()
        self.log("info", "已添加步骤：%s" % engine.STEP_SPECS[stype]["label"])

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def move_step(self, delta):
        i = self._selected_index()
        if i is None:
            return
        j = i + delta
        steps = self.script.steps
        if not (0 <= j < len(steps)):
            return
        steps[i], steps[j] = steps[j], steps[i]
        self.refresh_tree(select=j)
        self.mark_dirty()

    def dup_step(self):
        i = self._selected_index()
        if i is None:
            return
        copy = dict(self.script.steps[i])
        self.script.steps.insert(i + 1, copy)
        self.refresh_tree(select=i + 1)
        self.mark_dirty()

    def del_step(self):
        i = self._selected_index()
        if i is None:
            return
        del self.script.steps[i]
        n = len(self.script.steps)
        self.refresh_tree(select=min(i, n - 1) if n else None)
        self.mark_dirty()

    def clear_steps(self):
        if not self.script.steps:
            return
        if messagebox.askyesno("清空", "确定清空全部 %d 个步骤吗？" % len(self.script.steps), parent=self):
            self.script.steps = []
            self.refresh_tree()
            self.mark_dirty()

    def _on_delete_key(self, event):
        # 只有焦点不在输入框时才响应 Delete
        w = self.focus_get()
        if isinstance(w, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox)):
            return
        if self._selected_index() is not None:
            self.del_step()

    def _row_values(self, index, step):
        """列表一行的显示值。集中在一处，避免各处更新时不一致。"""
        spec = engine.STEP_SPECS.get(step["type"], {})
        note = engine.step_note(step)
        return (index + 1,
                "%s %s" % (spec.get("icon", ""), spec.get("label", step["type"])),
                engine.step_summary(step),
                note)

    def refresh_tree(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, step in enumerate(self.script.steps):
            spec = engine.STEP_SPECS.get(step["type"], {})
            tags = ["grp_" + spec.get("group", "流程")]
            if i % 2:
                tags.append("odd")
            if engine.step_note(step):
                tags.append("hasnote")
            self.tree.insert("", "end", iid=str(i), tags=tags,
                             values=self._row_values(i, step))
        if select is not None and 0 <= select < len(self.script.steps):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        elif self.script.steps and not self.tree.selection():
            # 载入脚本后自动选中第 1 步，右侧参数面板不会是空白
            self.tree.selection_set("0")
            self.tree.focus("0")
        self._update_title()

    def on_tree_select(self):
        i = self._selected_index()
        if i is None:
            self._clear_form()
            return
        self.build_form(i)

    # ==================================================================
    # 参数表单
    # ==================================================================
    def _clear_form(self):
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.form_vars = {}
        self.form_index = None
        ttk.Label(self.form_frame, text="在中间的列表里选中一个步骤，\n这里就会显示它的全部参数。",
                  justify="left", padding=14, foreground="#57606a").pack(anchor="w")

    def build_form(self, index):
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.form_vars = {}
        self.form_index = index
        step = self.script.steps[index]
        spec = engine.STEP_SPECS[step["type"]]
        self._loading_form = True
        try:
            head = ttk.Frame(self.form_frame)
            head.pack(fill="x", padx=8, pady=(8, 2))
            tk.Label(head, text="第 %d 步" % (index + 1), bg="#f4f5f7", fg="#0b5cad",
                     font=(UI, 10, "bold")).pack(side="left")
            tk.Label(head, text="  %s %s" % (spec.get("icon", ""), spec["label"]),
                     bg="#f4f5f7", font=(UI, 10, "bold")).pack(side="left")
            ttk.Separator(self.form_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)

            if not spec["fields"]:
                ttk.Label(self.form_frame, text="这个步骤没有需要设置的参数。",
                          padding=12, foreground="#57606a").pack(anchor="w")

            for f in spec["fields"]:
                self._build_field(step, f, spec)

            self._build_note_field(step)
        finally:
            self._loading_form = False
        self._add_step_actions(step)

    def _build_note_field(self, step):
        """备注输入框 —— 每个步骤都有，用来记录这一步是干什么的。"""
        box = ttk.Labelframe(self.form_frame, text="📝 备注", padding=6)
        box.pack(fill="x", padx=8, pady=(10, 4))
        tk.Label(box, text="给这一步写点说明，方便以后看懂（例如「记录说明文字」）",
                 bg="#f4f5f7", fg="#57606a", font=(UI, 8),
                 wraplength=430, justify="left").pack(anchor="w")

        var = tk.StringVar(value=engine.step_note(step))
        self.form_vars[engine.NOTE_KEY] = var

        entry = ttk.Entry(box, textvariable=var)
        entry.pack(fill="x", pady=(3, 2))
        var.trace_add("write", lambda *a: self._on_note_changed())

        row = ttk.Frame(box)
        row.pack(fill="x")
        self.note_count_var = tk.StringVar()
        tk.Label(row, textvariable=self.note_count_var, bg="#f4f5f7", fg="#8b949e",
                 font=(UI, 8)).pack(side="left")
        ttk.Button(row, text="清空", style="Tool.TButton", width=6,
                   command=lambda: var.set("")).pack(side="right")
        self._update_note_count(engine.step_note(step))

    def _update_note_count(self, text):
        if not hasattr(self, "note_count_var"):
            return
        self.note_count_var.set("%d / %d 字" % (len(text or ""), engine.NOTE_MAX_LEN))

    def _on_note_changed(self):
        if self._loading_form or self.form_index is None:
            return
        var = self.form_vars.get(engine.NOTE_KEY)
        if var is None:
            return
        # 输入时不做清洗（否则会把正在输入的空格吃掉），只限制长度。
        # 注意：截断后必须继续往下走把值写回模型，否则超长输入会被整段丢弃。
        text = var.get()
        if len(text) > engine.NOTE_MAX_LEN:
            text = text[:engine.NOTE_MAX_LEN]
            var.set(text)
        self._update_note_count(text)
        i = self.form_index
        if i >= len(self.script.steps):
            return
        step = self.script.steps[i]
        new_value = engine.clean_note(text)
        if step.get(engine.NOTE_KEY) == new_value:
            return
        step[engine.NOTE_KEY] = new_value
        tags = [t for t in self.tree.item(str(i), "tags") if t != "hasnote"]
        if new_value:
            tags.append("hasnote")
        self.tree.item(str(i), tags=tags, values=self._row_values(i, step))
        self.mark_dirty()

    def edit_selected_note(self):
        """弹出小窗口快速编辑选中步骤的备注（快捷键 F2）。"""
        i = self._selected_index()
        if i is None:
            self.log("warn", "先在中间列表里选中一个步骤，再按 F2 编辑备注。")
            return
        step = self.script.steps[i]
        spec = engine.STEP_SPECS.get(step["type"], {})

        dlg = tk.Toplevel(self)
        dlg.title("编辑备注 —— 第 %d 步" % (i + 1))
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("520x230")
        ttk.Label(dlg, text="第 %d 步  %s %s" % (i + 1, spec.get("icon", ""),
                                                spec.get("label", "")),
                  font=(UI, 10, "bold"), padding=(12, 10, 12, 2)).pack(anchor="w")
        ttk.Label(dlg, text=engine.step_summary(step), foreground="#57606a",
                  padding=(12, 0, 12, 6)).pack(anchor="w")

        var = tk.StringVar(value=engine.step_note(step))
        entry = ttk.Entry(dlg, textvariable=var, font=(UI, 10))
        entry.pack(fill="x", padx=12, pady=(0, 4))
        entry.focus_set()
        entry.select_range(0, "end")

        counter = tk.StringVar()
        tk.Label(dlg, textvariable=counter, fg="#8b949e", bg="#f4f5f7").pack(anchor="w", padx=12)

        def refresh_counter(*_a):
            counter.set("%d / %d 字（回车保存，Esc 取消）"
                        % (len(var.get()), engine.NOTE_MAX_LEN))
        var.trace_add("write", refresh_counter)
        refresh_counter()

        def save(_e=None):
            value = engine.clean_note(var.get())
            step[engine.NOTE_KEY] = value
            tags = [t for t in self.tree.item(str(i), "tags") if t != "hasnote"]
            if value:
                tags.append("hasnote")
            self.tree.item(str(i), tags=tags, values=self._row_values(i, step))
            if self.form_index == i:
                fv = self.form_vars.get(engine.NOTE_KEY)
                if fv is not None:
                    self._loading_form = True
                    fv.set(value)
                    self._loading_form = False
                self._update_note_count(value)
            self.mark_dirty()
            dlg.destroy()
            self.log("ok", "第 %d 步备注已保存：%s" % (i + 1, value or "(空)"))

        row = ttk.Frame(dlg)
        row.pack(fill="x", padx=12, pady=(6, 10))
        ttk.Button(row, text="确定", command=save).pack(side="right", padx=3)
        ttk.Button(row, text="取消", command=dlg.destroy).pack(side="right", padx=3)
        ttk.Button(row, text="清空备注",
                   command=lambda: var.set("")).pack(side="left")
        entry.bind("<Return>", save)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.wait_window(dlg)

    def show_notes_overview(self):
        """一览整个脚本的备注，并支持双击跳到对应步骤。"""
        rows = [(i, engine.step_note(s)) for i, s in enumerate(self.script.steps)
                if engine.step_note(s)]
        win = tk.Toplevel(self)
        win.title("全部备注")
        win.transient(self)
        win.geometry("760x520")

        head = ttk.Frame(win)
        head.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(head, text="脚本「%s」共 %d 步，其中 %d 步写了备注"
                  % (self.script.name, len(self.script.steps), len(rows)),
                  font=(UI, 10, "bold")).pack(side="left")
        ttk.Button(head, text="关闭", command=win.destroy).pack(side="right")

        if not rows:
            ttk.Label(win, text="\n还没有任何备注。\n\n"
                               "选中一个步骤，在右侧「📝 备注」里写点说明，"
                               "或直接按 F2 快速编辑。",
                      foreground="#57606a", justify="left",
                      padding=20).pack(anchor="w")
            return

        ttk.Label(win, text="双击某一行可以跳回该步骤", foreground="#57606a",
                  padding=(12, 0, 12, 6)).pack(anchor="w")

        wrap = ttk.Frame(win)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tree = ttk.Treeview(wrap, columns=("no", "type", "note"), show="headings",
                            selectmode="browse")
        tree.heading("no", text="#")
        tree.heading("type", text="类型")
        tree.heading("note", text="备注")
        tree.column("no", width=46, anchor="center", stretch=False)
        tree.column("type", width=140, anchor="w", stretch=False)
        tree.column("note", width=520, anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        for i, note in rows:
            step = self.script.steps[i]
            spec = engine.STEP_SPECS.get(step["type"], {})
            tree.insert("", "end", iid=str(i),
                        values=(i + 1, "%s %s" % (spec.get("icon", ""),
                                                  spec.get("label", "")), note))

        def jump(_e=None):
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            self.refresh_tree(select=idx)
            self.build_form(idx)
            win.destroy()

        tree.bind("<Double-1>", jump)
        ttk.Button(win, text="跳到选中步骤", command=jump).pack(pady=(0, 10))

    def clear_all_notes(self):
        n = sum(1 for s in self.script.steps if engine.step_note(s))
        if not n:
            messagebox.showinfo("清空备注", "当前脚本没有任何备注。", parent=self)
            return
        if not messagebox.askyesno("清空备注",
                                   "确定清空全部 %d 条备注吗？此操作不可撤销。" % n,
                                   parent=self):
            return
        for s in self.script.steps:
            s[engine.NOTE_KEY] = ""
        keep = self._selected_index()
        self.refresh_tree(select=keep)
        if keep is not None and 0 <= keep < len(self.script.steps):
            self.build_form(keep)
        self.mark_dirty()
        self.log("warn", "已清空 %d 条备注。" % n)

    def _add_step_actions(self, step):
        ttk.Separator(self.form_frame, orient="horizontal").pack(fill="x", padx=8, pady=8)
        box = ttk.Frame(self.form_frame)
        box.pack(fill="x", padx=8, pady=(0, 12))
        if step["type"] in ("move", "click", "drag", "if_color"):
            ttk.Button(box, text="🎯 F8 拾取屏幕坐标", style="Accent.TButton",
                       command=self.begin_pick_for_selection).pack(fill="x", pady=2)
        if step["type"] == "if_color":
            ttk.Button(box, text="🎨 拾取该点颜色", style="Tool.TButton",
                       command=lambda: self.begin_pick("color")).pack(fill="x", pady=2)
        if step["type"] == "if_image":
            ttk.Button(box, text="📷 截取屏幕区域做模板", style="Accent.TButton",
                       command=self.capture_template).pack(fill="x", pady=2)
            ttk.Button(box, text="浏览已有图片…", style="Tool.TButton",
                       command=self.browse_template).pack(fill="x", pady=2)
        ttk.Button(box, text="▶ 只测试这一步", style="Tool.TButton",
                   command=self.test_selected_step).pack(fill="x", pady=(8, 2))

    def _build_field(self, step, f, spec):
        key, kind = f["key"], f["kind"]
        row = ttk.Frame(self.form_frame)
        row.pack(fill="x", padx=8, pady=3)
        label = tk.Label(row, text=f["label"] + "：", bg="#f4f5f7", width=16, anchor="w",
                         justify="left")
        label.pack(side="left")
        value = step.get(key, f["default"])

        if kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            w = ttk.Checkbutton(row, variable=var, command=lambda: self._field_changed(key, var, f))
            w.pack(side="left")
            self.form_vars[key] = var
            return

        var = tk.StringVar(value="" if value is None else str(value))
        self.form_vars[key] = var
        var.trace_add("write", lambda *a, k=key, v=var, ff=f: self._field_changed(k, v, ff))

        if kind == "choice":
            labels = f.get("choice_labels") or {}
            vals = [labels.get(c, c) for c in f["choices"]]
            cur = labels.get(str(value), str(value))
            cb = ttk.Combobox(row, values=vals, width=18, state="readonly")
            cb.set(cur)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e, k=key, c=cb, ff=f: self._choice_changed(k, c, ff))
            self.form_vars[key] = var
            return

        width = 26 if kind in ("str", "image", "region") else 12
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side="left", fill="x", expand=kind in ("str", "image", "region"))
        entry.bind("<FocusOut>", lambda e, k=key, ff=f: self._normalize_entry(k, ff))

        if kind == "color":
            self.swatch = tk.Label(row, text="  ", bg=str(value) if str(value).startswith("#") else "#cccccc",
                                   relief="solid", bd=1, width=3)
            self.swatch.pack(side="left", padx=4)
            self.form_vars["__swatch_" + key] = self.swatch
            ttk.Button(row, text="取色", style="Tool.TButton",
                       command=lambda: self.begin_pick("color")
                       ).pack(side="left")
        elif kind == "image":
            ttk.Button(row, text="截取…", style="Tool.TButton",
                       command=self.capture_template).pack(side="left", padx=2)
            ttk.Button(row, text="浏览…", style="Tool.TButton",
                       command=self.browse_template).pack(side="left")
        elif kind == "region":
            ttk.Button(row, text="框选…", style="Tool.TButton",
                       command=self.capture_region_into_field).pack(side="left", padx=2)
            ttk.Button(row, text="清除", style="Tool.TButton",
                       command=lambda: var.set("")).pack(side="left")

        if f.get("help"):
            ttk.Label(self.form_frame, text="      " + f["help"], foreground="#57606a",
                      font=(UI, 8), wraplength=380, justify="left").pack(anchor="w", padx=8)

    def _choice_changed(self, key, combo, spec):
        if self._loading_form or self.form_index is None:
            return
        labels = spec.get("choice_labels") or {}
        inv = {v: k for k, v in labels.items()}
        raw = inv.get(combo.get(), combo.get())
        self._apply_field(key, raw)

    def _field_changed(self, key, var, spec):
        if self._loading_form or self.form_index is None:
            return
        kind = spec["kind"]
        text = var.get()
        if kind in ("int", "float"):
            try:
                val = int(float(text)) if kind == "int" else float(text)
            except (TypeError, ValueError):
                return
        elif kind == "bool":
            val = bool(var.get())
        else:
            val = text
        if kind == "color":
            try:
                vision.parse_color(val)
                sw = self.form_vars.get("__swatch_" + key)
                if sw is not None:
                    sw.configure(bg=vision.color_to_hex(vision.parse_color(val)))
            except Exception:
                pass
        self._apply_field(key, val)

    def _normalize_entry(self, key, spec):
        if self.form_index is None:
            return
        var = self.form_vars.get(key)
        if var is None or spec["kind"] not in ("int", "float"):
            return
        try:
            val = float(var.get())
        except (TypeError, ValueError):
            cur = self.script.steps[self.form_index].get(key, spec["default"])
            var.set(str(cur))
            return
        if spec["kind"] == "int":
            var.set(str(int(val)))
        else:
            var.set(str(round(val, 3)))

    def _apply_field(self, key, value):
        i = self.form_index
        if i is None or i >= len(self.script.steps):
            return
        step = self.script.steps[i]
        if key == engine.NOTE_KEY:
            value = engine.clean_note(value)
        if step.get(key) == value:
            return
        step[key] = value
        # 备注变化时同步更新行的标签（有备注的步骤用不同颜色标识）
        tags = [t for t in self.tree.item(str(i), "tags") if t != "hasnote"]
        if engine.step_note(step):
            tags.append("hasnote")
        self.tree.item(str(i), tags=tags, values=self._row_values(i, step))
        self.mark_dirty()

    def _hint_step(self, stype):
        hints = {
            "move": "把鼠标平滑移动到指定点，可设置耗时与随机抖动。",
            "click": "移动到目标点并点击，可精确控制按下时长、次数、连击间隔。",
            "drag": "按下并拖动到另一点再松开，适合拖准星、滑屏。",
            "wheel": "滚动滚轮，正数向上。",
            "key": "模拟按键，支持 ctrl+shift+a 这样的组合键与按住时长。",
            "key_down": "按住不放（配合后面的「松开按键」用，适合持续移动）。",
            "key_up": "松开之前按住的键。",
            "delay": "等待一段时间，可加随机浮动让节奏更自然。",
            "loop_begin": "循环开始，与「循环结束」配对；次数填 0 表示一直循环。",
            "loop_end": "循环结束，回到配对的「循环开始」。",
            "if_color": "判断屏幕某点的颜色，可以跳转到标签或停止脚本。",
            "if_image": "在画面上找一张小图，命中后跳转/继续/停止。",
            "label": "跳转的目标位置。",
            "goto": "无条件跳到某个标签，常用来做无限循环。",
            "stop": "结束脚本运行。",
        }
        self.hint_var.set(hints.get(stype, ""))

    def _on_wheel(self, event):
        """按鼠标位置决定滚哪个可滚动区域（左侧工具箱 / 右侧参数面板）。"""
        w = self.winfo_containing(event.x_root, event.y_root)
        target = None
        while w is not None:
            if w is self.form_canvas:
                target = self.form_canvas
                break
            if w is getattr(self, "_left_canvas", None):
                target = self._left_canvas
                break
            w = getattr(w, "master", None)
        if target is not None:
            target.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

    # ==================================================================
    # 拾取坐标 / 取色 / 截取模板
    # ==================================================================
    def begin_pick_for_selection(self):
        i = self._selected_index()
        if i is None:
            self.log("warn", "先在中间列表里选中一个步骤，再按 F8 拾取坐标。")
            return
        self.begin_pick("point")

    def begin_pick(self, mode="point"):
        """mode: point = 拾取坐标写回选中步骤；color = 同时取颜色"""
        if self.pickbar and self.pickbar.winfo_exists():
            return self._do_pick_now()
        i = self._selected_index()
        if i is None:
            self.log("warn", "没有选中任何步骤，拾取到的坐标只会显示在日志里。")
        self._refresh_space()
        self.pick_mode = mode
        self.pick_index = i
        self.pick_base = self.space.base
        self.pickbar = PickBar(self, on_done=self._on_pick_done, on_cancel=self._on_pick_cancel,
                               hint="移到要记录的位置 → 按 F8 拾取（可连续拾取多点）")
        self.tip_var.set("拾取中：把鼠标移到目标位置后按 F8，可连续拾取；拾完点浮条上的「完成」写回步骤。")
        # 让目标窗口重新拿到焦点，避免按键被浮条吃掉
        try:
            if getattr(self.space, "hwnd", 0):
                wi.activate_window(self.space.hwnd)
            else:
                self.pickbar.focus_force()
        except Exception:
            pass

    def _do_pick_now(self):
        if not (self.pickbar and self.pickbar.winfo_exists()):
            return
        x, y = wi.cursor_pos()
        sx, sy = int(x - self.pick_base[0]), int(y - self.pick_base[1])
        color = None
        try:
            color = wi.pixel_color(x, y)
        except Exception:
            color = None
        self.pickbar.add_pick(sx, sy, color)
        self.log("ok", "拾取：脚本坐标 (%d, %d)%s" % (
            sx, sy, "　颜色 %s" % vision.color_to_hex(color) if color else ""))

    def _on_pick_done(self, picks):
        self.pickbar = None
        self.tip_var.set("F8 拾取坐标 · F9 运行 · F10 急停")
        if not picks:
            return
        i = getattr(self, "pick_index", None)
        if i is None or i >= len(self.script.steps):
            self.log("info", "拾取结果：" + "，".join("(%d,%d)" % (p[0], p[1]) for p in picks))
            return
        step = self.script.steps[i]
        t = step["type"]
        mode = getattr(self, "pick_mode", "point")
        x, y, color = picks[0]
        changed = False
        if t in ("move", "click", "if_color"):
            step["x"], step["y"] = x, y
            changed = True
            if t == "if_color" and color:
                step["color"] = vision.color_to_hex(color)
        elif t == "drag":
            step["x1"], step["y1"] = x, y
            changed = True
            if len(picks) > 1:
                step["x2"], step["y2"] = picks[1][0], picks[1][1]
            else:
                self.log("warn", "拖动步骤建议再按一次 F8 拾取终点；当前终点保持原值。")
        if changed:
            self.refresh_tree(select=i)
            self.build_form(i)
            self.mark_dirty()
            self.log("ok", "已写入第 %d 步：%s" % (i + 1, engine.step_summary(step)))
        if mode == "color" and t == "if_color" and color:
            self.log("ok", "颜色已更新为 %s" % vision.color_to_hex(color))

    def _on_pick_cancel(self):
        self.pickbar = None
        self.tip_var.set("F8 拾取坐标 · F9 运行 · F10 急停")

    def capture_template(self):
        """全屏拖框 → 存成 PNG 模板 → 写入当前 if_image 步骤。"""
        i = self._selected_index()
        if i is None or self.script.steps[i]["type"] != "if_image":
            self.log("warn", "请先选中一个「如果屏幕上有图片」步骤，再截取模板。")
            return
        cap = {}

        def done(rect):
            cap["rect"] = rect
            if rect:
                self._finish_template(rect, i)

        RegionCapture(self, on_done=done, on_cancel=lambda: None,
                      hint="拖框选中目标画面里要识别的小图（越有特征越好，别太大）")

    def _finish_template(self, rect, index):
        try:
            w, h, buf = wi.grab_screen(rect)
            path = self.library.template_path("模板")
            vision.encode_png(path, w, h, buf)
        except Exception as exc:
            messagebox.showerror("截取失败", str(exc), parent=self)
            return
        step = self.script.steps[index]
        step["image"] = path
        # 顺手把搜索区域设成模板周围一大圈，减少搜索量
        try:
            sx, sy = self.space.to_script(rect[0], rect[1])
            step["region"] = "%d,%d,%d,%d" % (max(0, sx - 200), max(0, sy - 150),
                                              w + 400, h + 300)
        except Exception:
            step["region"] = ""
        self.refresh_tree(select=index)
        self.build_form(index)
        self.mark_dirty()
        self.log("ok", "模板已保存：%s（%dx%d），并已自动填写搜索区域。" % (
            os.path.basename(path), w, h))

    def browse_template(self):
        i = self._selected_index()
        if i is None or self.script.steps[i]["type"] != "if_image":
            return
        path = filedialog.askopenfilename(
            parent=self, title="选择模板图片", initialdir=store.TEMPLATE_DIR,
            filetypes=[("图片", "*.png *.bmp *.ppm"), ("全部文件", "*.*")])
        if not path:
            return
        self.script.steps[i]["image"] = path
        self.refresh_tree(select=i)
        self.build_form(i)
        self.mark_dirty()

    def capture_region_into_field(self):
        i = self._selected_index()
        if i is None:
            return
        self._refresh_space()
        base = self.space.base

        def done(rect):
            if not rect:
                return
            sx, sy = int(rect[0] - base[0]), int(rect[1] - base[1])
            text = "%d,%d,%d,%d" % (sx, sy, rect[2], rect[3])
            step = self.script.steps[i]
            for f in engine.STEP_SPECS[step["type"]]["fields"]:
                if f["kind"] == "region":
                    step[f["key"]] = text
            self.refresh_tree(select=i)
            self.build_form(i)
            self.mark_dirty()
            self.log("ok", "搜索区域已设为 (脚本坐标)：%s" % text)

        RegionCapture(self, on_done=done, on_cancel=lambda: None,
                      hint="拖框选中「找图」要搜索的范围（框小一点速度更快）")

    # ==================================================================
    # 运行
    # ==================================================================
    def run_script(self):
        self._start_run(0, None)

    def run_from_selected(self):
        i = self._selected_index()
        if i is None:
            self.log("warn", "先选中要从哪一步开始。")
            return
        self._start_run(i, None)

    def test_selected_step(self):
        i = self._selected_index()
        if i is None:
            self.log("warn", "先选中要测试的步骤。")
            return
        self._start_run(i, i)

    def _start_run(self, start, only):
        if self.runner and self.runner.running:
            self.log("warn", "脚本正在运行中，按 F10 可以先停下。")
            return
        errors, warnings = self.script.validate()
        for w in warnings:
            self.log("warn", w)
        if errors:
            for e in errors:
                self.log("error", e)
            if not messagebox.askyesno(
                    "脚本有问题", "检测到 %d 个问题：\n\n%s\n\n仍然要继续运行吗？" % (
                        len(errors), "\n".join(errors[:6])), parent=self):
                return
        snapshot = self.script.clone()
        self.runner = engine.Runner(
            snapshot,
            on_log=lambda level, msg: self.queue.put(("log", level, msg)),
            on_step=lambda idx: self.queue.put(("step", idx)),
            on_state=lambda running, reason: self.queue.put(("state", running, reason)))
        try:
            self.runner.start(start, only)
        except Exception as exc:
            self.log("error", "启动失败：%s" % exc)

    def stop_script(self):
        if self.runner and self.runner.running:
            self.runner.stop()
            self.log("warn", "已发出停止指令，正在松开所有按住的键…")
        else:
            self.log("info", "当前没有在运行的脚本。")

    def _on_run_state(self, running, reason):
        if running:
            self.state_var.set("● 运行中")
            self.run_from_btn.configure(state="disabled")
            self.tip_var.set("运行中：F10 紧急停止")
        else:
            self.state_var.set("就绪 —— %s" % reason)
            self.run_from_btn.configure(state="normal")
            self.tip_var.set("F8 拾取坐标 · F9 运行 · F10 急停")
            for iid in self.tree.get_children():
                tags = [t for t in self.tree.item(iid, "tags") if t != "running"]
                if int(iid) % 2 and "odd" not in tags:
                    tags.append("odd")
                self.tree.item(iid, tags=tags)
            self.running_index = None

    def _on_run_step(self, index):
        if self.running_index is not None and self.tree.exists(str(self.running_index)):
            iid = str(self.running_index)
            tags = [t for t in self.tree.item(iid, "tags") if t != "running"]
            self.tree.item(iid, tags=tags)
        self.running_index = index
        iid = str(index)
        if self.tree.exists(iid):
            tags = list(self.tree.item(iid, "tags"))
            if "running" not in tags:
                tags.append("running")
            self.tree.item(iid, tags=tags)
            self.tree.see(iid)

    def _on_hotkey(self, name):
        if name == "start":
            self.run_script()
        elif name == "stop":
            self.stop_script()
        elif name == "pick":
            if self.pickbar and self.pickbar.winfo_exists():
                self._do_pick_now()
            else:
                self.begin_pick_for_selection()

    # ==================================================================
    # 日志
    # ==================================================================
    def log(self, level, msg):
        self.queue.put(("log", level, msg))

    def _append_log(self, level, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "[%s] %s\n" % (ts, msg), level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if level == "error":
            self.state_var.set("⚠ 出错，详见日志")

    # ==================================================================
    # 帮助
    # ==================================================================
    def env_check(self):
        """环境自检：判断模拟输入在这台机器上到底能不能用。"""
        self.log("info", "开始环境自检……")
        self.update_idletasks()

        lines = []
        ok_all = True
        perm_fail = False
        perm_reason = ""

        # 1) 模拟输入（最关键）
        try:
            inject_ok, why = wi.test_input_injection()
        except Exception as exc:
            inject_ok, why = False, "自检异常：%s" % exc
        lines.append(("PASS" if inject_ok else "FAIL", "模拟输入", why))
        ok_all = ok_all and inject_ok

        # 2) 权限：如果目标程序是管理员权限，本工具也必须提权，否则输入会被 UIPI 拦截
        admin = wi.is_admin()
        try:
            bound_hwnd = getattr(getattr(self, "space", None), "hwnd", 0)
        except Exception:
            bound_hwnd = 0
        if bound_hwnd:
            perm_ok, perm_why = wi.can_send_to(bound_hwnd)
            if perm_ok:
                lines.append(("PASS", "权限", perm_why))
            else:
                lines.append(("FAIL", "权限", perm_why))
                ok_all = False
                perm_fail = True
                perm_reason = perm_why
        else:
            lines.append(("INFO" if admin else "WARN", "运行权限",
                          "以管理员身份运行" if admin else
                          "普通权限运行。若目标程序以管理员身份启动，"
                          "必须用「以管理员身份启动.bat」启动本工具，"
                          "否则切换窗口后点击无效。"))

        # 3) DPI
        try:
            scale = wi.dpi_scale()
            lines.append(("INFO", "显示缩放", "DPI %d（%d%%）%s" % (
                wi.system_dpi(), int(scale * 100),
                "，已按物理像素取坐标" if scale > 1.0 else "")))
        except Exception:
            pass

        # 4) 热键占用：这些键是本工具自己注册的，所以不能再拿它们去试注册
        #    （那样必然失败，会误报"被其它程序占用"）。改用启动时的真实注册结果。
        try:
            registered = set(self.hotkeys.registered)
        except Exception:
            registered = set()
        name_by_id = {1: "F8", 2: "F9", 3: "F10"}
        failed = [name_by_id.get(i, str(i)) for i in (1, 2, 3)
                  if i not in registered]
        if failed:
            lines.append(("WARN", "全局热键",
                          "以下键无法注册：%s（可能被其它程序占用，本工具将不响应它们）"
                          % "、".join(failed)))
        else:
            lines.append(("PASS", "全局热键", "F8 拾取 / F9 运行 / F10 急停 均已生效"))

        # 5) 键盘输入法：中文输入法会把注入按键吞成 VK_PROCESSKEY（按 W 没反应）
        try:
            hwnd = getattr(getattr(self, "space", None), "hwnd", 0)
            if hwnd:
                lay = wi.window_layout_id(hwnd)
                if lay == wi.LANG_ENGLISH_US:
                    lines.append(("PASS", "键盘输入法",
                                  "目标窗口当前是英文布局，按键不会被输入法吞掉"))
                elif lay == wi.LANG_CHINESE_SIMPLIFIED:
                    lines.append(("WARN", "键盘输入法",
                                  "目标窗口当前是中文输入法。中文输入法会把模拟按键转成"
                                  "「按键处理中」，导致目标程序收到无效按键（按 W 没反应）。\n"
                                  "本工具运行时会自动切到英文；也可以手动按 Win+空格 切到英文。"))
                elif lay:
                    lines.append(("INFO", "键盘输入法", "当前布局 0x%04X" % lay))
        except Exception:
            pass

        # 6) 前台占用者（当模拟输入失败时给出线索）
        if not inject_ok:
            try:
                fg = wi.foreground_window()
                lines.append(("INFO", "当前前台窗口", "%s　[%s]" % (
                    wi.window_title(fg) or "(无标题)", wi.window_class(fg))))
            except Exception:
                pass

        # 输出到日志
        for level, name, detail in lines:
            tag = {"PASS": "ok", "FAIL": "error", "WARN": "warn", "INFO": "info"}[level]
            self.log(tag, "【%s】%s：%s" % (
                {"PASS": "通过", "FAIL": "失败", "WARN": "注意", "INFO": "信息"}[level],
                name, detail.replace("\n", "\n          ")))

        # 失败时弹窗给出可执行的建议
        if not ok_all:
            # 权限不足是最好定位、也最好解决的一种：直接提供一键提权重启
            if perm_fail:
                if messagebox.askyesno(
                        "权限不足以操作目标窗口",
                        "%s\n\n"
                        "是否现在以管理员身份重新启动本工具？\n"
                        "（会弹出 Windows 的权限确认窗口，点「是」即可；"
                        "本工具会先关闭当前窗口）" % (perm_reason or ""),
                        parent=self):
                    self.relaunch_admin()
                return False

            messagebox.showwarning(
                "环境自检未通过",
                "模拟输入在这台机器上被拦截了，脚本会「跑完但目标程序没反应」。\n\n"
                "原因：\n%s\n\n"
                "请这样解决：\n"
                "1. 退出后台的游戏加速器或安全软件，"
                "或在其中关闭「游戏模式」「键鼠保护」；\n"
                "2. 同样检查安全软件的游戏模式 / 键鼠保护；\n"
                "3. 然后重新执行「帮助 → 环境自检」确认变为通过。" % why,
                parent=self)
        else:
            tip = "\n\n其余提示请查看运行日志。"
            if not admin:
                tip = ("\n\n提示：当前是普通权限运行。如果目标程序以管理员身份运行，"
                       "请改用「以管理员身份启动.bat」启动本工具。" + tip)
            messagebox.showinfo("环境自检", "模拟输入正常，可以放心使用。" + tip,
                                parent=self)
        return ok_all

    def relaunch_admin(self):
        """以管理员身份重新启动本工具（会弹出 UAC 确认框）。"""
        self.log("warn", "正在申请管理员权限，请在弹窗中点「是」……")
        self.update_idletasks()
        if wi.relaunch_as_admin():
            self.log("ok", "已启动管理员实例，正在关闭当前窗口…")
            try:
                self.hotkeys.stop()
            except Exception:
                pass
            self.after(400, self.destroy)
        else:
            messagebox.showwarning(
                "提权未成功",
                "无法自动提升权限（可能被取消，或被安全策略阻止）。\n\n"
                "请手动操作：关闭本工具，然后右键「以管理员身份启动.bat」"
                "→ 以管理员身份运行。",
                parent=self)

    def open_data_dir(self):
        try:
            os.startfile(store.DATA_DIR)
        except Exception as exc:
            self.log("error", "打开目录失败：%s" % exc)

    def load_demo(self):
        if not self._confirm_discard():
            return
        sc = engine.Script("示例_目标程序")
        sc.window_title = self.win_var.get().strip() or "目标程序"
        sc.start_delay = 1.5
        sc.delay_jitter = 0.05
        sc.hold_jitter = 0.01
        w, h = 960, 600
        sc.steps = [
            engine.new_step("label"), 
            engine.new_step("click"),
            engine.new_step("delay"),
            engine.new_step("key"),
            engine.new_step("key"),
            engine.new_step("delay"),
            engine.new_step("loop_begin"),
            engine.new_step("move"),
            engine.new_step("click"),
            engine.new_step("move"),
            engine.new_step("click"),
            engine.new_step("delay"),
            engine.new_step("loop_end"),
        ]
        sc.steps[0]["name"] = "开始"
        sc.steps[1].update({"x": int(w * 0.5), "y": int(h * 0.86), "hold": 0.06,
                            "clicks": 1, "move_time": 0.2})
        sc.steps[2].update({"seconds": 0.8, "random": 0.15})
        sc.steps[3].update({"keys": "f", "hold": 0.05, "times": 3, "interval": 0.12})
        sc.steps[4].update({"keys": "r", "hold": 0.05, "times": 1})
        sc.steps[5].update({"seconds": 0.6, "random": 0.1})
        sc.steps[6].update({"times": 0})
        sc.steps[7].update({"x": int(w * 0.25), "y": int(h * 0.45), "duration": 0.18, "jitter": 2})
        sc.steps[8].update({"x": int(w * 0.25), "y": int(h * 0.45), "hold": 0.08,
                            "clicks": 2, "interval": 0.1, "move_time": 0})
        sc.steps[9].update({"x": int(w * 0.75), "y": int(h * 0.45), "duration": 0.18, "jitter": 2})
        sc.steps[10].update({"x": int(w * 0.75), "y": int(h * 0.45), "hold": 0.08,
                             "clicks": 2, "interval": 0.1, "move_time": 0})
        sc.steps[11].update({"seconds": 1.2, "random": 0.2})
        # 给示例步骤写上备注，顺便展示备注功能
        for idx, note in (
                (1, "第一步：点击开始按钮"),
                (2, "等待界面加载完成"),
                (3, "连续发送三次按键"),
                (4, "发送一次按键"),
                (5, "等待一段时间"),
                (6, "下面进入无限循环，按 F10 停止"),
                (7, "移动到第一个目标点"),
                (8, "点两下（左）"),
                (9, "移动到第二个目标点"),
                (10, "点两下（右）"),
                (11, "一轮结束，等待后进入下一轮")):
            sc.steps[idx][engine.NOTE_KEY] = note
        name = "示例_目标程序"
        i = 2
        while self.library.exists(name):
            name = "示例_目标程序_%d" % i
            i += 1
        sc.name = name
        self.script = sc
        try:
            self.library.save(sc)
        except Exception as exc:
            self.log("error", "示例保存失败：%s" % exc)
        self.refresh_script_list(select=name)
        self._load_script_into_ui()
        self.log("ok", "已载入示例脚本。坐标是 960x600 画面下的相对坐标，请按你的实际目标画面重新拾取。")

    def show_help(self):
        win = tk.Toplevel(self)
        win.title("使用说明")
        win.geometry("760x620")
        txt = tk.Text(win, wrap="word", font=(UI, 10), padx=14, pady=12, bg="#ffffff")
        txt.pack(fill="both", expand=True)
        txt.insert("end", HELP_TEXT)
        txt.configure(state="disabled")

    def show_about(self):
        messagebox.showinfo(
            "关于",
            "QuickScript Studio\n\n"
            "纯 Python + Tkinter 编写，不依赖任何第三方库。\n"
            "模拟输入使用 Windows SendInput，找图找色自带解码器。\n\n"
            "仅供个人学习与合法授权范围内的自动化使用。",
            parent=self)

    # ==================================================================
    def on_close(self):
        if self.runner and self.runner.running:
            if not messagebox.askyesno("正在运行", "脚本还在运行，确定退出吗？", parent=self):
                return
            self.runner.stop()
            self.runner.join(1.0)
        if not self._confirm_discard():
            return
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.destroy()


HELP_TEXT = """【QuickScript Studio —— 使用说明】

一、最快上手流程
   1. 打开要操作的目标程序，让它保持窗口模式、不要最小化。
   2. 在顶部「绑定窗口」点「刷新窗口」→ 在下拉里选中目标窗口；
      或者点一下目标窗口，再回本工具点「取前台窗口」。
   3. 左侧点「点击」，中间出现第 1 步。选中它，按 F8，把鼠标移到目标画面里
      要点的位置，再按一次 F8 —— 坐标就写进这一步了。点浮条上的「完成」。
   4. 右侧把「按下时长」设成 0.05～0.12 秒，「连击间隔」0.08 秒。
   5. 继续添加「等待」「按键」等步骤，用「循环开始 / 循环结束」包住要重复的部分。
   6. 按 F9 运行（会有 1 秒准备时间，期间切到目标窗口）。随时按 F10 急停。

二、坐标模式
   · 窗口相对坐标（推荐）：脚本记的是「相对目标窗口左上角」的坐标。
     目标窗口移动、换分辨率、换电脑都不会失效。
   · 屏幕绝对坐标：直接记屏幕位置，简单但窗口一动就失效。
   · 固定原点：适合画布位置固定、但窗口标题不好绑定的情况。
     在目标画面上找一个永不移动的特征点（比如画布左上角），
     点「设为鼠标处」，之后所有坐标都相对这个点。

三、每个点击参数是什么意思
   X / Y          目标点（脚本坐标）
   鼠标键         左键 / 右键 / 中键 / 侧键
   按下时长       鼠标按下到松开之间保持的时间，0.03～0.15 秒最像真人
   点击次数       一次连点几下（比如双击填 2）
   连击间隔       两次点击之间的间隔
   移动耗时       从当前位置移过去用多久，0 = 瞬移（瞬移最容易被识别）

四、给步骤写备注
   每个步骤都能写一条备注，用来记住"这一步是干什么的"。
   脚本一长，光看"点击 (240,270)"根本想不起来它对应目标画面里哪个按钮，
   写个备注就一目了然了。
   · 选中步骤 → 右侧最下面的「📝 备注」框里直接写
   · 或者按 F2 弹出小窗快速编辑（回车保存，Esc 取消）
   · 列表最右边有「备注」列，写了备注的步骤会高亮显示
   · 菜单「工具 → 查看全部备注…」可以一览整个脚本的说明，
     双击某一行能直接跳回那一步
   备注会随脚本一起保存进 JSON，导入导出、分享给朋友都不会丢。

五、让脚本更像真人（右侧「脚本设置」）
   · 按下时长随机浮动：比如 0.01，表示每次按下时长上下浮动 0.01 秒
   · 间隔随机浮动：每次等待/连击间隔随机变化
   · 每次点击后额外停顿：给目标程序留出响应时间
   · 移动耗时不要填 0，用 0.1～0.25 秒的平滑移动，并给 1～3 像素抖动

六、键盘
   「按键」步骤的按键框支持组合键，用加号连接：
     空格 = space 或 空格        回车 = enter
     大招 = r                    前进 = w
     组合 = ctrl+shift+a         功能键 = F1 … F12
   「按住不放 / 松开按键」适合持续移动、持续开火。

七、判断（进阶）
   · 如果某点是指定颜色：判断血条、按钮、准星颜色，命中/未命中可以
     选择「跳转」到某个标签，从而实现"打中了就继续，没打中就重来"。
   · 如果屏幕上有图片：用「截取…」拖框框住目标画面里的小图标做模板，
     脚本会在画面上搜索它。搜索区域越小越快；匹配度默认 0.98，
     画面有压缩/缩放时适当调低到 0.9 左右。
   · 「标签 / 跳转」用来做循环和分支，标签名要和跳转目标完全一致。

七、脚本管理
   所有脚本存在程序目录 data/scripts/ 下，一个脚本一个 JSON 文件。
   「导出」出来的 JSON 可以直接发给别人，「导入」即可使用
   （找图用的模板图片需要一起拷贝，否则要重新截取）。

八、常见问题
   Q: 运行了但目标程序没反应？
   A: ① 目标程序可能以管理员身份运行 —— 那就也用管理员身份启动本工具；
      ② 确认绑定窗口是否正确（状态栏「脚本设置」里会显示"已绑定…"）；
      ③ 部分程序需要窗口处于激活状态，勾上「运行时自动把目标窗口切到最前」。
   Q: 找图总是找不到？
   A: 把搜索区域框小一点、匹配度降到 0.9，或者重新截取一张更有特征的模板。
   Q: 怎么停下来？
   A: 按 F10，任何按住的键都会被自动松开。

九、一点提醒
   模拟输入属于"用程序代替手动操作"，请只在单机目标画面里自己玩，别用于
   任何违反法律法规、服务条款或破坏公平性的场景。
"""


def main():
    wi.enable_dpi_awareness()
    store.ensure_dirs()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
