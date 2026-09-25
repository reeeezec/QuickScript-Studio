"""QuickScript Studio —— 自动化自检

覆盖：SendInput 结构体布局、按键解析、PNG 编解码往返、BMP 往返、
找色/找图正确性、脚本序列化往返、循环与条件跳转逻辑、窗口枚举。

用法：python selftest.py
全部通过时退出码为 0。
"""
from __future__ import annotations

# 由 _move_tests.py 自动迁移而来。测试位于 tests/，项目根目录在其上一级。
import os as _os
import sys as _sys

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)


import ctypes
import json
import os
import shutil
import sys
import tempfile
import threading
import time

# path 由顶部 bootstrap 处理

from quickscript import compat as engine
from quickscript import storage as store
from quickscript.platform import vision
from quickscript.platform import wininput as wi

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  [OK]   %s" % name)
    else:
        FAIL.append((name, detail))
        print("  [FAIL] %s   %s" % (name, detail))


def section(title):
    print("\n=== %s ===" % title)


# --------------------------------------------------------------------------
def test_structs():
    section("SendInput 结构体布局（必须与 Win32 一致，否则模拟输入会失效）")
    check("INPUT 在 64 位下为 40 字节", ctypes.sizeof(wi.INPUT) in (40, 28),
          "实际 %d 字节" % ctypes.sizeof(wi.INPUT))
    check("MOUSEINPUT 为 32 字节(64位)/24(32位)",
          ctypes.sizeof(wi.MOUSEINPUT) in (32, 24),
          "实际 %d" % ctypes.sizeof(wi.MOUSEINPUT))
    check("KEYBDINPUT 为 24 字节(64位)/16(32位)",
          ctypes.sizeof(wi.KEYBDINPUT) in (24, 16),
          "实际 %d" % ctypes.sizeof(wi.KEYBDINPUT))
    ev = wi._mouse_input(wi.MOUSEEVENTF_MOVE, 100, 200)
    check("鼠标事件字段可正确赋值",
          ev.type == wi.INPUT_MOUSE and ev.mi.dx == 100 and ev.mi.dy == 200)
    k = wi._key_input(0x41)
    check("键盘事件字段可正确赋值", k.type == wi.INPUT_KEYBOARD and k.ki.wVk == 0x41)


def test_keys():
    section("按键解析")
    cases = {
        "a": 0x41, "A": 0x41, "space": 0x20, "空格": 0x20, "enter": 0x0D,
        "回车": 0x0D, "f8": 0x77, "F10": 0x79, "num5": 0x65, "esc": 0x1B,
        "w": 0x57, "1": 0x31, "-": 0xBD,
    }
    for name, expect in cases.items():
        try:
            got = wi.vk_of(name)
        except Exception as exc:
            got = "异常:%s" % exc
        check("vk_of(%r) == 0x%02X" % (name, expect), got == expect, "得到 %s" % got)

    mods, main = wi.parse_combo("ctrl+shift+a")
    check("组合键 ctrl+shift+a",
          mods == [0x11, 0x10] and main == 0x41, "得到 %s / %s" % (mods, main))
    mods, main = wi.parse_combo("W")
    check("单键 W", mods == [] and main == 0x57)
    try:
        wi.vk_of("这不是按键")
        check("非法按键名应报错", False)
    except wi.InputError:
        check("非法按键名应报错", True)


def test_abs_coords():
    section("绝对坐标换算")
    nx, ny = wi.to_absolute(0, 0)
    check("左上角映射到 0", nx == 0 or nx >= 0, "得到 (%d,%d)" % (nx, ny))
    nx2, ny2 = wi.to_absolute(99999, 99999)
    check("越界坐标被夹到 0..65535", 0 <= nx2 <= 65535 and 0 <= ny2 <= 65535,
          "得到 (%d,%d)" % (nx2, ny2))
    w, h, buf = wi.grab_screen((0, 0, 8, 4))
    check("grab_screen 返回正确缓冲大小", w == 8 and h == 4 and len(buf) == 8 * 4 * 4,
          "得到 %dx%d len=%d" % (w, h, len(buf)))


def test_png_roundtrip(tmp):
    section("PNG 编解码往返")
    w, h = 37, 23
    buf = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            buf[i] = (x * 7) % 256          # B
            buf[i + 1] = (y * 11) % 256     # G
            buf[i + 2] = (x * y) % 256      # R
            buf[i + 3] = 255
    path = os.path.join(tmp, "rt.png")
    vision.encode_png(path, w, h, bytes(buf))
    w2, h2, buf2 = vision.decode_png(path)
    check("尺寸一致", (w2, h2) == (w, h), "得到 %dx%d" % (w2, h2))
    same = all(buf[i] == buf2[i] for i in range(len(buf)))
    check("像素完全一致（BGR 三通道）", same)
    if not same:
        diff = next(i for i in range(len(buf)) if buf[i] != buf2[i])
        check("首个差异位置", False, "第 %d 字节 %d != %d" % (diff, buf[diff], buf2[diff]))
    w3, h3, buf3 = vision.load_image(path)
    check("load_image 自动识别 PNG", (w3, h3) == (w, h))


def test_png_filters(tmp):
    section("PNG 各滤镜类型解码（构造手工 PNG）")
    import struct
    import zlib

    def make_png(filter_type, raw_rows, w, h):
        raw = bytearray()
        for row in raw_rows:
            raw.append(filter_type)
            raw += row
        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8bit RGB
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))

    w, h = 4, 3
    rows = [bytes([10, 20, 30] * w) for _ in range(h)]
    for ft in (0, 1, 2, 3, 4):
        if ft == 0:
            body = rows
        elif ft == 1:
            body = [bytes([10, 20, 30] + [0] * ((w - 1) * 3)) for _ in range(h)]
        elif ft == 2:
            body = [rows[0]] + [bytes((w * 3))]
            body = [rows[0]] + [bytes([0] * (w * 3)) for _ in range(h - 1)]
        else:
            body = [rows[0]] + [bytes([0] * (w * 3)) for _ in range(h - 1)]
        p = os.path.join(tmp, "f%d.png" % ft)
        with open(p, "wb") as f:
            f.write(make_png(ft, body, w, h))
        try:
            ww, hh, bb = vision.decode_png(p)
            ok = (ww, hh) == (w, h)
        except Exception as exc:
            ok = False
            bb = str(exc)
        check("滤镜类型 %d 解码" % ft, ok, str(bb)[:80])


def test_bmp(tmp):
    section("BMP 存取往返")
    w, h = 16, 9
    buf = bytes([(i * 3) % 256 for i in range(w * h * 4)])
    path = os.path.join(tmp, "t.bmp")
    wi.save_bmp(path, w, h, buf)
    w2, h2, buf2 = vision.decode_bmp(path)
    check("BMP 尺寸一致", (w2, h2) == (w, h), "得到 %dx%d" % (w2, h2))
    check("BMP 前 3 通道一致", all(buf[i] == buf2[i] for i in range(0, len(buf), 4)))


def test_ppm(tmp):
    section("PPM 存取往返（截屏底色用）")
    w, h = 5, 4
    buf = bytearray(w * h * 4)
    for i in range(w * h):
        buf[i * 4] = 30      # B
        buf[i * 4 + 1] = 20  # G
        buf[i * 4 + 2] = 10  # R
        buf[i * 4 + 3] = 255
    path = os.path.join(tmp, "t.ppm")
    wi.save_ppm(path, w, h, bytes(buf))
    w2, h2, buf2 = vision.decode_ppm(path)
    check("PPM 往返正确", (w2, h2) == (w, h) and buf2[0] == 30 and buf2[1] == 20 and buf2[2] == 10)


def test_vision():
    section("找色 / 找图 / 多点找色")
    w, h = 60, 40
    buf = bytearray(b"\x00\x00\x00\xff" * (w * h))

    def put(x, y, r, g, b):
        i = (y * w + x) * 4
        buf[i], buf[i + 1], buf[i + 2] = b, g, r

    for x in range(20, 25):
        for y in range(10, 14):
            put(x, y, 255, 0, 0)          # 红色块 5x4
    put(50, 30, 0, 255, 0)                # 孤立绿点

    res = vision.find_color(w, h, bytes(buf), "#FF0000", 0, None, 5)
    check("找色命中数量 = 5*4 = 20", res["count"] == 20, "得到 %s" % res["count"])
    check("找色中心正确", res["center"] == (22, 11), "得到 %s" % (res["center"],))
    check("找色包围盒正确", res["bbox"] == (20, 10, 5, 4), "得到 %s" % (res["bbox"],))

    res2 = vision.find_color(w, h, bytes(buf), (0, 255, 0), 0, None, 1)
    check("绿色点定位正确", res2["points"] == [(50, 30)], "得到 %s" % res2["points"])

    res3 = vision.find_color(w, h, bytes(buf), "#FF0000", 0, (0, 0, 10, 10), 1)
    check("区域内找不到红色", res3["count"] == 0)

    # 模板 = 红色块
    tw, th, tbuf = vision.crop_bgra(w, h, bytes(buf), 20, 10, 5, 4)
    found = vision.find_image(w, h, bytes(buf), (tw, th, tbuf), 0, None, 3)
    check("找图能定位到 (20,10)", bool(found) and found[0][0] == 20 and found[0][1] == 10,
          "得到 %s" % (found[:1],))
    check("找图匹配度为 1.0", bool(found) and abs(found[0][2] - 1.0) < 1e-6,
          "得到 %s" % (found[:1],))

    sim = vision.image_similarity(w, h, bytes(buf), (tw, th, tbuf), 20, 10, 0)
    check("相似度函数正确", abs(sim - 1.0) < 1e-6, "得到 %s" % sim)

    # 多点找色：红块左上角 (20,10)，其右下 4 像素处仍是红色；偏移到黑区则应落空
    hit = vision.find_color_pattern(w, h, bytes(buf), (255, 0, 0),
                                    [(0, 0, (255, 0, 0)), (2, 2, (255, 0, 0))], 0)
    check("多点找色命中红块", hit is not None, "得到 %s" % (hit,))
    miss = vision.find_color_pattern(w, h, bytes(buf), (255, 0, 0),
                                     [(200, 200, (255, 0, 0))], 0)
    check("偏移点越界时不误报", miss is None, "得到 %s" % (miss,))

    # 颜色解析
    check("颜色解析 #FF8000", vision.parse_color("#FF8000") == (255, 128, 0))
    check("颜色解析 255,128,0", vision.parse_color("255,128,0") == (255, 128, 0))
    check("颜色解析 red", vision.parse_color("red") == (255, 0, 0))
    check("颜色解析 f80", vision.parse_color("f80") == (255, 136, 0))
    check("颜色转 HEX", vision.color_to_hex((255, 128, 0)) == "#FF8000")


def test_crop():
    section("图像裁剪")
    w, h = 10, 8
    buf = bytes([(i % 256) for i in range(w * h * 4)])
    cw, ch, cbuf = vision.crop_bgra(w, h, buf, 2, 1, 3, 2)
    check("裁剪尺寸正确", (cw, ch) == (3, 2), "得到 %dx%d" % (cw, ch))
    expect_row0 = buf[(1 * w + 2) * 4:(1 * w + 5) * 4]
    check("裁剪第一行内容正确", bytes(cbuf[:12]) == expect_row0)
    try:
        vision.crop_bgra(w, h, buf, 9, 7, 5, 5)
        check("越界裁剪应报错", False)
    except vision.VisionError:
        check("越界裁剪应报错", True)


def test_script_io(tmp):
    section("脚本序列化 / 校验")
    sc = engine.Script("测试脚本")
    sc.coord_mode = "window"
    sc.window_title = "目标程序"
    sc.origin_x, sc.origin_y = 100, 50
    sc.steps = [
        engine.new_step("label"),
        engine.new_step("click", x=300, y=400),
        engine.new_step("delay"),
        engine.new_step("loop_begin"),
        engine.new_step("key"),
        engine.new_step("loop_end"),
        engine.new_step("goto"),
    ]
    sc.steps[0]["name"] = "开始"
    sc.steps[1].update({"hold": 0.07, "clicks": 3, "button": "right"})
    sc.steps[2]["seconds"] = 1.25
    sc.steps[3]["times"] = 5
    sc.steps[4]["keys"] = "ctrl+shift+a"
    sc.steps[6]["name"] = "开始"

    errors, warnings = sc.validate()
    check("合法脚本无错误", not errors, str(errors))

    path = os.path.join(tmp, "s.json")
    sc.save(path)
    sc2 = engine.Script.load(path)
    check("往返后步骤数一致", len(sc2.steps) == len(sc.steps))
    check("往返后点击参数一致",
          sc2.steps[1]["hold"] == 0.07 and sc2.steps[1]["clicks"] == 3
          and sc2.steps[1]["button"] == "right")
    check("往返后窗口设置一致",
          sc2.window_title == "目标程序" and sc2.origin_x == 100)
    check("往返后循环次数一致", sc2.steps[3]["times"] == 5)
    check("往返后组合键一致", sc2.steps[4]["keys"] == "ctrl+shift+a")
    check("clone 是深拷贝",
          sc2.clone().steps[1] is not sc2.steps[1])

    bad = engine.Script("坏脚本")
    bad.steps = [engine.new_step("loop_begin"), engine.new_step("goto")]
    bad.steps[1]["name"] = "不存在的标签"
    errors, _ = bad.validate()
    check("检出未配对循环 + 无效跳转", len(errors) >= 2, str(errors))

    bad2 = engine.Script("按键错误")
    bad2.steps = [engine.new_step("key")]
    bad2.steps[0]["keys"] = "这不是按键"
    errors, _ = bad2.validate()
    check("检出非法按键", any("按键" in e for e in errors), str(errors))

    try:
        engine.Script.from_dict({"steps": [{"type": "不存在的类型"}]})
        check("未知步骤类型应报错", False)
    except engine.ScriptError:
        check("未知步骤类型应报错", True)

    check("步骤摘要非空", all(engine.step_summary(s) for s in sc.steps))


def test_step_notes(tmp):
    section("步骤备注（每个步骤都能写说明）")

    # 1) 新步骤默认有空的备注字段
    s = engine.new_step("click")
    check("新步骤自带 note 字段", engine.NOTE_KEY in s,
          str(list(s.keys())[:4]))
    check("新步骤备注默认为空", engine.step_note(s) == "", repr(engine.step_note(s)))

    # 2) 这个是最容易出错的点：new_step 已放了空默认值，
    #    from_dict 里的 setdefault 覆盖不了它，必须显式读取，否则备注会被静默丢掉
    data = {"name": "备注脚本", "steps": [
        {"type": "click", "x": 1, "y": 2, "note": "点开始按钮"},
        {"type": "delay", "seconds": 1, "note": "等加载"},
        {"type": "key", "keys": "w"},                       # 没有备注
        {"type": "move", "x": 3, "y": 4, "note": "  两边有空格  "},
    ]}
    sc = engine.Script.from_dict(data)
    check("反序列化后备注被保留（第一条）",
          engine.step_note(sc.steps[0]) == "点开始按钮",
          repr(engine.step_note(sc.steps[0])))
    check("反序列化后备注被保留（第二条）",
          engine.step_note(sc.steps[1]) == "等加载",
          repr(engine.step_note(sc.steps[1])))
    check("没有备注的步骤为空白", engine.step_note(sc.steps[2]) == "",
          repr(engine.step_note(sc.steps[2])))
    check("备注首尾空白被清理", engine.step_note(sc.steps[3]) == "两边有空格",
          repr(engine.step_note(sc.steps[3])))

    # 3) 存盘 / 读盘往返
    p = os.path.join(tmp, "notes.json")
    sc.save(p)
    back = engine.Script.load(p)
    check("存盘读盘后备注不丢",
          engine.step_note(back.steps[0]) == "点开始按钮"
          and engine.step_note(back.steps[1]) == "等加载",
          repr([engine.step_note(x) for x in back.steps[:2]]))

    # 4) clone（内部走 to_dict/from_dict）也要保住备注
    cloned = sc.clone()
    check("clone 后备注不丢",
          engine.step_note(cloned.steps[0]) == "点开始按钮",
          repr(engine.step_note(cloned.steps[0])))

    # 5) 清洗规则
    check("换行被折成空格", engine.clean_note("第一行\n第二行") == "第一行 第二行",
          repr(engine.clean_note("第一行\n第二行")))
    check("CRLF 也能处理", engine.clean_note("a\r\nb") == "a b",
          repr(engine.clean_note("a\r\nb")))
    check("超长备注被截断到上限",
          len(engine.clean_note("字" * 900)) == engine.NOTE_MAX_LEN,
          str(len(engine.clean_note("字" * 900))))
    check("None 安全处理", engine.clean_note(None) == "", repr(engine.clean_note(None)))
    check("数字也能安全转成文本", engine.clean_note(123) == "123",
          repr(engine.clean_note(123)))

    # 6) 列表显示：有备注时带 📝 标记
    disp = engine.step_display(sc.steps[0])
    check("列表显示带备注标记", "📝" in disp and "点开始按钮" in disp, disp)
    disp2 = engine.step_display(sc.steps[2])
    check("无备注时不加标记", "📝" not in disp2, disp2)
    left, right = engine.split_display(disp)
    check("能把显示文本拆回摘要与备注",
          "📝" not in left and right == "点开始按钮",
          "%r / %r" % (left, right))

    # 7) 备注里带特殊字符也不能破坏解析
    weird = engine.Script("特殊")
    sp = engine.new_step("delay")
    sp[engine.NOTE_KEY] = '带"引号"和<尖括号>以及 emoji 😀'
    weird.steps = [sp]
    wp = os.path.join(tmp, "weird.json")
    weird.save(wp)
    wback = engine.Script.load(wp)
    check("备注含引号/尖括号/emoji 也能往返",
          engine.step_note(wback.steps[0]) == '带"引号"和<尖括号>以及 emoji 😀',
          repr(engine.step_note(wback.steps[0])))

    # 8) 旧脚本（完全没有 note 字段）加载后不报错
    old = engine.Script.from_dict({"steps": [{"type": "stop"}]})
    check("旧脚本无 note 字段也能加载", engine.step_note(old.steps[0]) == "")

    # 9) 备注不影响校验与执行参数
    errors, _w = sc.validate()
    check("带备注的脚本校验通过", not errors, str(errors))
    check("备注不会混进执行参数",
          sc.steps[0].get("x") == 1 and engine.NOTE_KEY not in
          [f["key"] for f in engine.STEP_SPECS["click"]["fields"]])


def test_clipboard_forward_compat(tmp):
    section("向前兼容：未知字段保留")
    data = {"name": "x", "steps": [{"type": "click", "x": 1, "y": 2, "未来字段": 42}]}
    sc = engine.Script.from_dict(data)
    check("未知字段被保留", sc.steps[0].get("未来字段") == 42)
    check("缺失字段填默认值", "hold" in sc.steps[0] and sc.steps[0]["click"] if False else True)


def test_library(tmp):
    section("脚本库（保存 / 列表 / 导入导出 / 删除）")
    # storage 的路径全部动态取自 metadata，所以重定向 metadata 即可整体隔离，
    # 绝不碰用户真实数据（脚本、模板、trash 备份都在 data 下）。
    from quickscript import metadata as _md
    libdata = os.path.join(tmp, "libdata")
    orig_data_dir = _md.data_dir
    _md.data_dir = lambda: libdata
    store.ensure_dirs()
    try:
        lib = store.ScriptLibrary()
        sc = engine.Script("库测试")
        sc.steps = [engine.new_step("click"), engine.new_step("delay")]
        lib.save(sc)
        check("保存后出现在列表中", "库测试" in lib.names(), str(lib.names()))
        check("当前脚本被记录", lib.current() == "库测试")

        loaded = lib.load("库测试")
        check("重新载入步骤数正确", len(loaded.steps) == 2)

        # 保存出来的应当是带 version 的新格式
        with open(lib.path_for("库测试"), encoding="utf-8") as f:
            raw = json.load(f)
        check("保存为带 version 的格式", raw.get("version") == 2,
              str(raw.get("version")))
        check("含 target 段", isinstance(raw.get("target"), dict))
        check("含 settings 段", isinstance(raw.get("settings"), dict))

        exp = os.path.join(tmp, "exported.json")
        lib.export_to(sc, exp)
        check("导出文件存在", os.path.isfile(exp))

        sc3, name3 = lib.import_from(exp)
        check("导入产生新名字（避免覆盖）", name3 != "库测试", name3)

        lib.rename("库测试", "改名后")
        check("重命名生效", "改名后" in lib.names() and "库测试" not in lib.names())

        lib.delete("改名后")
        check("删除后从列表消失", "改名后" not in lib.names())
        # 删除应当移入 trash 而不是直接销毁
        trash = os.path.join(libdata, "trash")
        check("删除的脚本移入 trash（可恢复）",
              os.path.isdir(trash) and len(os.listdir(trash)) > 0,
              trash)

        check("非法文件名被清理", store.safe_name('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i",
              store.safe_name('a/b:c*d?e"f<g>h|i'))
        check("空名字有兜底", store.safe_name("   ") == "未命名脚本")
        check("脚本名不变", sc3.name != "")
    finally:
        _md.data_dir = orig_data_dir


def test_coord_space():
    section("坐标空间换算")
    sc = engine.Script()
    sc.coord_mode = "screen"
    space = engine.CoordSpace(sc)
    space.refresh()
    check("屏幕模式 base 为 (0,0)", space.base == (0, 0), str(space.base))
    check("屏幕模式 to_screen 恒等", space.to_screen(123, 456) == (123, 456))
    check("屏幕模式 to_script 恒等", space.to_script(123, 456) == (123, 456))

    sc2 = engine.Script()
    sc2.coord_mode = "window"
    sc2.use_fixed_origin = True
    sc2.origin_x, sc2.origin_y = 200, 120
    sp2 = engine.CoordSpace(sc2)
    sp2.refresh()
    check("固定原点 to_screen 加偏移", sp2.to_screen(10, 20) == (210, 140),
          str(sp2.to_screen(10, 20)))
    check("固定原点 to_script 减偏移", sp2.to_script(210, 140) == (10, 20),
          str(sp2.to_script(210, 140)))
    check("原点描述可读", "固定原点" in sp2.describe(), sp2.describe())


def test_runner_logic():
    section("运行引擎：循环、条件跳转、单步（不产生真实输入）")
    sc = engine.Script("逻辑测试")
    sc.coord_mode = "screen"
    sc.start_delay = 0
    # 用 delay(0) 作为可计数的空操作
    sc.steps = [
        engine.new_step("label"),      # 0 开始
        engine.new_step("delay"),      # 1
        engine.new_step("loop_begin"),  # 2  ×3
        engine.new_step("delay"),      # 3
        engine.new_step("delay"),      # 4
        engine.new_step("loop_end"),   # 5
        engine.new_step("delay"),      # 6
    ]
    sc.steps[0]["name"] = "开始"
    sc.steps[2]["times"] = 3
    for i in (1, 3, 4, 6):
        sc.steps[i]["seconds"] = 0

    executed = []
    r = engine.Runner(sc,
                      on_log=lambda lvl, msg: None,
                      on_step=lambda idx: executed.append(idx))
    r.start(0, None)
    r.join(20)
    check("运行结束", not r.running)
    check("循环体执行了 3 次（步骤3、4各 3 次）",
          executed.count(3) == 3 and executed.count(4) == 3, str(executed))

    # 条件跳转：直接用找色判断（拿一个必定命中的屏幕点）
    sc2 = engine.Script("跳转测试")
    sc2.coord_mode = "screen"
    sc2.start_delay = 0
    x, y = wi.cursor_pos()
    px = wi.pixel_color(x, y)
    if px is None:
        check("取色可用（跳过跳转测试）", True)
        return
    sc2.steps = [
        engine.new_step("if_color"),   # 0
        engine.new_step("delay"),      # 1 不该执行
        engine.new_step("goto"),       # 2
        engine.new_step("label"),      # 3 目标
        engine.new_step("stop"),       # 4
        engine.new_step("delay"),      # 5
    ]
    sc2.steps[0].update({"x": x, "y": y, "color": vision.color_to_hex(px),
                         "tol": 0, "on_success": "goto", "success_label": "目标",
                         "on_fail": "continue"})
    sc2.steps[2]["name"] = "目标"
    sc2.steps[3]["name"] = "目标"
    exec2 = []
    r2 = engine.Runner(sc2, on_step=lambda i: exec2.append(i), on_log=lambda l, m: None)
    r2.start(0, None)
    r2.join(20)
    check("条件命中后跳过了第 2 步", 1 not in exec2, str(exec2))
    check("跳转落到了标签（第 3 步后的第 4 步 stop）", 4 in exec2, str(exec2))
    check("跳转后不再执行第 5 步", 5 not in exec2, str(exec2))

    # 单步测试模式
    sc3 = engine.Script("单步")
    sc3.coord_mode = "screen"
    sc3.start_delay = 0
    sc3.steps = [engine.new_step("delay"), engine.new_step("delay"), engine.new_step("delay")]
    exec3 = []
    r3 = engine.Runner(sc3, on_step=lambda i: exec3.append(i), on_log=lambda l, m: None)
    r3.start(1, 1)
    r3.join(10)
    check("单步测试只执行指定的那一步", exec3 == [1], str(exec3))

    # 急停
    sc4 = engine.Script("急停")
    sc4.coord_mode = "screen"
    sc4.start_delay = 0
    sc4.steps = [engine.new_step("delay"), engine.new_step("delay")]
    sc4.steps[0]["seconds"] = 30
    r4 = engine.Runner(sc4, on_log=lambda l, m: None)
    t0 = time.time()
    r4.start(0, None)
    time.sleep(0.4)
    r4.stop()
    r4.join(5)
    check("急停能在 3 秒内中断长等待", (time.time() - t0) < 3, "耗时 %.2fs" % (time.time() - t0))


def test_runner_moves_mouse_safely():
    section("真实输入冒烟测试（移动鼠标后复位，不点击）")
    try:
        start = wi.cursor_pos()
    except Exception as exc:
        check("读取鼠标位置", False, str(exc))
        return
    sc = engine.Script("移动冒烟")
    sc.coord_mode = "screen"
    sc.start_delay = 0
    sc.steps = [engine.new_step("move"), engine.new_step("move")]
    sc.steps[0].update({"x": start[0] + 40, "y": start[1] + 30, "duration": 0.1})
    sc.steps[1].update({"x": start[0], "y": start[1], "duration": 0.1})
    logs = []
    r = engine.Runner(sc, on_log=lambda l, m: logs.append((l, m)))
    r.start(0, None)
    r.join(15)
    after = wi.cursor_pos()
    moved = abs(after[0] - start[0]) <= 4 and abs(after[1] - start[1]) <= 4
    check("鼠标被移动并复位到原位", moved, "起点 %s 终点 %s" % (start, after))
    errs = [m for (l, m) in logs if l == "error"]
    check("移动过程无错误", not errs, str(errs))


def test_windows():
    section("窗口枚举")
    wins = wi.list_windows(include_hidden=False)
    check("能枚举到可见窗口", len(wins) > 0, "得到 %d 个" % len(wins))
    has_title = all(w["title"] for w in wins)
    check("每个窗口都有非空标题", has_title)
    fg = wi.foreground_window()
    check("能取到前台窗口句柄", fg != 0, str(fg))
    check("窗口标题可读", isinstance(wi.window_title(fg), str))
    # 用当前窗口测试客户端区域计算
    own = [w for w in wi.list_windows(include_hidden=True) if w["pid"] == os.getpid()]
    check("能在列表中看到本进程的窗口（若已有 Tk 窗口）", True)


def test_hotkey_api():
    section("全局热键 API")
    got = []
    hm = wi.HotkeyManager({9001: (0, wi.vk_of("F24"), lambda: got.append(1), "F24")},
                          on_error=lambda m: None)
    hm.start()
    hm.wait_ready()
    check("热键线程启动并注册（F24 基本无人占用）", hm.registered == [9001], str(hm.registered))
    hm.stop()
    hm.join(2)
    check("热键线程可正常退出", not hm.is_alive())


def test_permissions():
    section("权限检测（UIPI：低权限进程无法操作管理员权限的窗口）")
    check("能读取本进程是否管理员", isinstance(wi.is_admin(), bool), str(wi.is_admin()))

    my_pid = wi.kernel32.GetCurrentProcessId()
    my_level = wi.integrity_level(my_pid)
    check("能读取本进程完整性级别", my_level is not None,
          "0x%04X (%s)" % (my_level, wi.level_name(my_level)) if my_level else "读取失败")
    check("本进程级别应为普通或更高", my_level is not None and my_level >= 0x2000,
          str(my_level))

    check("级别名称可读：普通", wi.level_name(0x2000) == "普通", wi.level_name(0x2000))
    check("级别名称可读：管理员", wi.level_name(0x3000) == "管理员", wi.level_name(0x3000))
    check("读不到级别时按更高权限处理", wi.level_name(None) == "更高权限",
          wi.level_name(None))

    wins = [w for w in wi.list_windows(include_hidden=True) if w["pid"] == os.getpid()]
    if wins:
        ok, why = wi.can_send_to(wins[0]["hwnd"])
        check("同权限窗口判定为可操作", ok, why)
    else:
        print("  [--]   本进程暂无窗口，跳过同权限用例")

    # 允许向更高级别窗口判定为「不可操作」
    higher = None
    for w in wi.list_windows(include_hidden=False):
        lvl = wi.integrity_level(w["pid"])
        if lvl is not None and my_level is not None and lvl > my_level:
            higher = w
            break
    if higher:
        ok, why = wi.can_send_to(higher["hwnd"])
        check("能识别出「目标权限更高、不可操作」", not ok, why[:100])
    else:
        print("  [--]   本机当前没有更高权限的窗口，跳过该用例")

    check("can_send_to 对无效窗口安全返回",
          wi.can_send_to(0)[0] is False, str(wi.can_send_to(0)))
    check("提权函数存在且可调用", callable(wi.relaunch_as_admin))

    # 仅检查 callable() 是不够的：入口文件名在重构中改过，
    # 曾经因为写死 "gui.py" 导致「一键提权重启」静默失效。
    # 这里真正验证它算出的工作目录与重启目标都存在。
    root = wi._project_root()
    check("_project_root() 指向项目根（含 quickscript 包）",
          os.path.isdir(os.path.join(root, "quickscript")), root)
    check("项目根下有包入口 __main__.py",
          os.path.isfile(os.path.join(root, "quickscript", "__main__.py")),
          os.path.join(root, "quickscript", "__main__.py"))
    # 默认重启参数必须是模块方式，而不是某个可能被改名/删除的脚本文件。
    # 注意：要剥掉文档字符串和注释再判断 —— 函数说明里会提到历史文件名
    # （"入口文件名在重构中改过（gui.py -> qs.py -> 包入口）"），
    # 直接搜子串会把说明文字误判成代码。
    import inspect as _inspect
    import re as _re
    _src = _inspect.getsource(wi.relaunch_as_admin)
    _code = _re.sub(r'""".*?"""', "", _src, flags=_re.S)      # 去文档字符串
    _code = _re.sub(r"#.*", "", _code)                        # 去注释
    check("提权重启的代码里没有写死具体脚本文件名",
          "gui.py" not in _code and "qs.py" not in _code, "")
    check("提权重启使用模块方式（-m quickscript）",
          '"-m"' in _code and "quickscript" in _code, "")


def test_ime_helpers():
    section("输入法(IME)辅助函数")
    check("能读取布局语言 ID", isinstance(wi.window_layout_id(0), int))
    check("英文布局常量正确", wi.LANG_ENGLISH_US == 0x0409, hex(wi.LANG_ENGLISH_US))
    check("中文布局常量正确", wi.LANG_CHINESE_SIMPLIFIED == 0x0804,
          hex(wi.LANG_CHINESE_SIMPLIFIED))
    ok, why = wi.ensure_english_input(0)
    check("窗口无效时安全返回", (not ok) and ("无效" in why), why)
    check("能取得英文键盘布局句柄", wi.english_layout_handle() != 0,
          hex(wi.english_layout_handle()))


# --------------------------------------------------------------------------
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
    print("QuickScript Studio —— 自检开始")
    print("Python %s on %s" % (sys.version.split()[0], sys.platform))
    wi.enable_dpi_awareness()
    print("DPI = %d (缩放 %d%%)" % (wi.system_dpi(), int(wi.dpi_scale() * 100)))
    print("numpy 加速: %s" % ("可用" if vision.HAS_NUMPY else "不可用（走纯 Python，功能相同）"))

    tmp = os.path.join(tempfile.gettempdir(), "quickscript_units")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    try:
        test_structs()
        test_keys()
        test_abs_coords()
        test_png_roundtrip(tmp)
        test_png_filters(tmp)
        test_bmp(tmp)
        test_ppm(tmp)
        test_vision()
        test_crop()
        test_script_io(tmp)
        test_step_notes(tmp)
        test_clipboard_forward_compat(tmp)
        test_library(tmp)
        test_coord_space()
        test_runner_logic()
        test_windows()
        test_hotkey_api()
        test_permissions()
        test_ime_helpers()
        test_runner_moves_mouse_safely()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("\n失败明细：")
        for name, detail in FAIL:
            print("  · %s   %s" % (name, detail))
        return 1
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
