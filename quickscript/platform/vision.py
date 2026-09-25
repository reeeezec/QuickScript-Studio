# -*- coding: utf-8 -*-
"""QuickScript Studio —— 图像识别模块（找色 / 找图）

零第三方依赖：内置 PNG 解码（zlib + 全滤镜反解）、BMP 解析。
若环境里恰好装了 numpy，则自动启用向量化加速，否则走纯 Python 快路径。

统一像素格式：bytes，每像素 4 字节，顺序 B,G,R,X（与 win_input.grab_screen 一致）。
"""
from __future__ import annotations

import os
import struct
import zlib

try:  # 可选加速
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

HAS_NUMPY = _np is not None


class VisionError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# 颜色解析
# --------------------------------------------------------------------------

_NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 255, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "orange": (255, 165, 0), "purple": (128, 0, 128),
}


def parse_color(value):
    """支持 '#RRGGBB' / 'RRGGBB' / 'r,g,b' / 'red' / (r,g,b) -> (r,g,b)"""
    if isinstance(value, (tuple, list)):
        if len(value) < 3:
            raise VisionError("颜色元组需要 3 个分量：%s" % (value,))
        return tuple(max(0, min(255, int(v))) for v in value[:3])
    text = str(value).strip().lower()
    if text in _NAMED:
        return _NAMED[text]
    if text.startswith("#"):
        text = text[1:]
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 3:
            raise VisionError("颜色格式错误：%s" % value)
        return tuple(max(0, min(255, int(float(p)))) for p in parts)
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    if len(text) == 3:
        try:
            return tuple(int(c * 2, 16) for c in text)
        except ValueError:
            pass
    raise VisionError("无法识别的颜色：%s（示例：#FF0000 或 255,0,0）" % value)


def color_to_hex(rgb) -> str:
    return "#%02X%02X%02X" % (int(rgb[0]) & 255, int(rgb[1]) & 255, int(rgb[2]) & 255)


def color_bgr(rgb):
    r, g, b = rgb
    return b, g, r


# --------------------------------------------------------------------------
# 图像解码
# --------------------------------------------------------------------------

def _paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(raw: bytes, width: int, height: int, bpp: int, stride: int) -> bytearray:
    """PNG 扫描线反滤镜。raw 为 zlib 解压后的数据（每行 1 字节滤镜 + stride 字节）。"""
    out = bytearray(height * stride)
    pos = 0
    prev_start = 0
    for y in range(height):
        ftype = raw[pos]
        pos += 1
        line_start = y * stride
        line = raw[pos:pos + stride]
        pos += stride
        if ftype == 0:
            out[line_start:line_start + stride] = line
        elif ftype == 1:
            for i in range(stride):
                a = out[line_start + i - bpp] if i >= bpp else 0
                out[line_start + i] = (line[i] + a) & 0xFF
        elif ftype == 2:
            if y == 0:
                out[line_start:line_start + stride] = line
            else:
                for i in range(stride):
                    out[line_start + i] = (line[i] + out[prev_start + i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = out[line_start + i - bpp] if i >= bpp else 0
                b = out[prev_start + i] if y > 0 else 0
                out[line_start + i] = (line[i] + ((a + b) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = out[line_start + i - bpp] if i >= bpp else 0
                b = out[prev_start + i] if y > 0 else 0
                c = out[prev_start + i - bpp] if (y > 0 and i >= bpp) else 0
                out[line_start + i] = (line[i] + _paeth(a, b, c)) & 0xFF
        else:
            raise VisionError("不支持的 PNG 滤镜类型：%d" % ftype)
        prev_start = line_start
    return out


def decode_png(path: str):
    """解码 PNG -> (width, height, bgra_bytes)。支持灰度/RGB/调色板/带 Alpha，8/16 位深。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise VisionError("不是有效的 PNG 文件：%s" % path)

    pos = 8
    width = height = bit_depth = color_type = interlace = None
    palette = b""
    idat = []
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
        elif ctype == b"PLTE":
            palette = body
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"IEND":
            break
    if width is None:
        raise VisionError("PNG 缺少 IHDR：%s" % path)
    if interlace:
        raise VisionError("暂不支持交错（Adam7）PNG，请用画图另存为普通 PNG：%s" % path)

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise VisionError("不支持的 PNG 颜色类型：%d" % color_type)

    raw = zlib.decompress(b"".join(idat))
    bits_pp = channels * bit_depth
    stride = (width * bits_pp + 7) // 8
    bpp = max(1, bits_pp // 8)
    lines = _unfilter(raw, width, height, bpp, stride)

    out = bytearray(width * height * 4)
    out[3::4] = b"\xff" * (width * height)   # 默认不透明，带 Alpha 的 PNG 稍后覆盖
    o = 0
    if bit_depth == 8:
        if color_type == 2:
            for i in range(0, width * height * 3, 3):
                out[o] = lines[i + 2]; out[o + 1] = lines[i + 1]; out[o + 2] = lines[i]; o += 4
        elif color_type == 6:
            for i in range(0, width * height * 4, 4):
                out[o] = lines[i + 2]; out[o + 1] = lines[i + 1]
                out[o + 2] = lines[i]; out[o + 3] = lines[i + 3]; o += 4
        elif color_type == 0:
            for i in range(width * height):
                v = lines[i]
                out[o] = out[o + 1] = out[o + 2] = v; o += 4
        elif color_type == 4:
            for i in range(0, width * height * 2, 2):
                v = lines[i]
                out[o] = out[o + 1] = out[o + 2] = v
                out[o + 3] = lines[i + 1]; o += 4
        elif color_type == 3:
            for i in range(width * height):
                idx = lines[i] * 3
                if idx + 2 >= len(palette):
                    raise VisionError("PNG 调色板越界：%s" % path)
                out[o] = palette[idx + 2]; out[o + 1] = palette[idx + 1]; out[o + 2] = palette[idx]; o += 4
    elif bit_depth == 16:
        step = channels * 2
        for i in range(0, width * height * step, step):
            if color_type == 2:
                out[o] = lines[i + 4]; out[o + 1] = lines[i + 2]; out[o + 2] = lines[i]
            elif color_type == 6:
                out[o] = lines[i + 4]; out[o + 1] = lines[i + 2]; out[o + 2] = lines[i]
            elif color_type in (0, 4):
                v = lines[i]
                out[o] = out[o + 1] = out[o + 2] = v
            else:
                raise VisionError("16 位调色板 PNG 不支持：%s" % path)
            o += 4
    else:  # 1 / 2 / 4 位，仅灰度与调色板
        per_byte = 8 // bit_depth
        mask = (1 << bit_depth) - 1
        for y in range(height):
            row = lines[y * stride:(y + 1) * stride]
            for x in range(width):
                byte = row[x // per_byte]
                shift = 8 - bit_depth * ((x % per_byte) + 1)
                val = (byte >> shift) & mask
                if color_type == 3:
                    idx = val * 3
                    out[o] = palette[idx + 2]; out[o + 1] = palette[idx + 1]; out[o + 2] = palette[idx]
                else:
                    v = int(val * 255 / mask)
                    out[o] = out[o + 1] = out[o + 2] = v
                o += 4
    return width, height, bytes(out)


def decode_bmp(path: str):
    """解码 BMP（支持 24/32 位、未压缩；本工具自己导出的模板就是 32 位 BMP）。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"BM":
        raise VisionError("不是有效的 BMP 文件：%s" % path)
    data_off = struct.unpack("<I", data[10:14])[0]
    header_size = struct.unpack("<I", data[14:18])[0]
    if header_size == 12:  # BITMAPCOREHEADER
        width, height, planes, bpp = struct.unpack("<HHHH", data[18:26])
    else:
        width, height = struct.unpack("<ii", data[18:26])
        planes, bpp = struct.unpack("<HH", data[26:30])
        compression = struct.unpack("<I", data[30:34])[0]
        if compression not in (0, 3):
            raise VisionError("仅支持未压缩 BMP（当前压缩方式 %d）：%s" % (compression, path))
    top_down = height < 0
    height = abs(height)
    row_size = ((width * bpp + 31) // 32) * 4
    out = bytearray(width * height * 4)
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        base = data_off + src_y * row_size
        row = data[base:base + row_size]
        o = y * width * 4
        if bpp == 32:
            out[o:o + width * 4] = row[:width * 4]
        elif bpp == 24:
            for x in range(width):
                i = x * 3
                out[o] = row[i]; out[o + 1] = row[i + 1]; out[o + 2] = row[i + 2]
                o += 4
        else:
            raise VisionError("仅支持 24/32 位 BMP：%s" % path)
    return width, height, bytes(out)


def decode_ppm(path: str):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"P6"):
        raise VisionError("不是 P6 PPM：%s" % path)
    parts = []
    pos = 2
    while len(parts) < 3:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos] != 0x0A:
                pos += 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        parts.append(int(data[start:pos]))
    pos += 1
    width, height, _maxv = parts
    src = data[pos:pos + width * height * 3]
    out = bytearray(width * height * 4)
    out[0::4] = src[2::3]
    out[1::4] = src[1::3]
    out[2::4] = src[0::3]
    return width, height, bytes(out)


def load_image(path: str):
    """按扩展名/文件头加载图片 -> (w, h, bgra_bytes)"""
    if not os.path.isfile(path):
        raise VisionError("图片不存在：%s" % path)
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"\x89PNG"):
        return decode_png(path)
    if head.startswith(b"BM"):
        return decode_bmp(path)
    if head.startswith(b"P6"):
        return decode_ppm(path)
    raise VisionError("不支持的图片格式（请用 PNG 或 BMP）：%s" % path)


def encode_png(path: str, w: int, h: int, bgra: bytes, level: int = 6) -> None:
    """把 BGRA 缓冲编码为 PNG（RGBA 真彩）保存。用于把截取的区域存成找图模板。"""
    stride_bytes = w * 4
    raw = bytearray((stride_bytes + 1) * h)
    pos = 0
    for y in range(h):
        raw[pos] = 0  # 滤镜 None
        pos += 1
        row = bgra[y * stride_bytes:(y + 1) * stride_bytes]
        # B,G,R,A -> R,G,B,A
        raw[pos:pos + stride_bytes:4] = row[2::4]
        raw[pos + 1:pos + stride_bytes:4] = row[1::4]
        raw[pos + 2:pos + stride_bytes:4] = row[0::4]
        raw[pos + 3:pos + stride_bytes:4] = b"\xff" * w   # GDI 的 Alpha 位不可信，强制不透明
        pos += stride_bytes

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)


def crop_bgra(w, h, buf, x, y, cw, ch):
    """从 BGRA 缓冲裁出一块 -> (cw, ch, bytes)"""
    x, y, cw, ch = int(x), int(y), int(cw), int(ch)
    if x < 0 or y < 0 or cw <= 0 or ch <= 0 or x + cw > w or y + ch > h:
        raise VisionError("裁剪区域越界：x=%d y=%d w=%d h=%d（源图 %dx%d）" % (x, y, cw, ch, w, h))
    mv = memoryview(buf)
    out = bytearray(cw * ch * 4)
    for row in range(ch):
        src = ((y + row) * w + x) * 4
        out[row * cw * 4:(row + 1) * cw * 4] = mv[src:src + cw * 4]
    return cw, ch, bytes(out)


# --------------------------------------------------------------------------
# 找色
# --------------------------------------------------------------------------

def _region_clip(w, h, region):
    if region is None:
        return 0, 0, w, h
    x, y, rw, rh = (int(v) for v in region)
    x = max(0, min(w, x))
    y = max(0, min(h, y))
    rw = max(0, min(w - x, rw))
    rh = max(0, min(h - y, rh))
    return x, y, rw, rh


def find_color(w, h, buf, color, tol=10, region=None, limit=1):
    """在整张图/区域内找指定颜色（±tol）。

    返回 dict：count（匹配像素总数）、points（前 limit 个坐标）、
    bbox（匹配区域包围盒 (x,y,w,h) 或 None）、center（包围盒中心或 None）。
    """
    tr, tg, tb = parse_color(color)
    tol = max(0, int(tol))
    x0, y0, rw, rh = _region_clip(w, h, region)
    if rw == 0 or rh == 0:
        return {"count": 0, "points": [], "bbox": None, "center": None}

    points = []
    count = 0
    minx, miny, maxx, maxy = w, h, -1, -1
    row_bytes = w * 4
    limit = max(1, int(limit))

    if _np is not None and rw * rh > 20000:
        arr = _np.frombuffer(buf, dtype=_np.uint8).reshape(h, w, 4)
        sub = arr[y0:y0 + rh, x0:x0 + rw, :3].astype(_np.int16)
        target = _np.array([tb, tg, tr], dtype=_np.int16)
        mask = (_np.abs(sub - target) <= tol).all(axis=2)
        count = int(mask.sum())
        if count:
            ys, xs = _np.nonzero(mask)
            minx = int(xs.min()) + x0; maxx = int(xs.max()) + x0
            miny = int(ys.min()) + y0; maxy = int(ys.max()) + y0
            for i in range(min(limit, len(xs))):
                points.append((int(xs[i]) + x0, int(ys[i]) + y0))
    else:
        mv = memoryview(buf)
        for y in range(y0, y0 + rh):
            base = y * row_bytes
            for x in range(x0, x0 + rw):
                i = base + x * 4
                if (abs(mv[i] - tb) <= tol and abs(mv[i + 1] - tg) <= tol
                        and abs(mv[i + 2] - tr) <= tol):
                    count += 1
                    if x < minx: minx = x
                    if x > maxx: maxx = x
                    if y < miny: miny = y
                    if y > maxy: maxy = y
                    if len(points) < limit:
                        points.append((x, y))

    bbox = None
    center = None
    if count:
        bbox = (minx, miny, maxx - minx + 1, maxy - miny + 1)
        center = (minx + (bbox[2] - 1) // 2, miny + (bbox[3] - 1) // 2)
    return {"count": count, "points": points, "bbox": bbox, "center": center}


def find_color_pattern(w, h, buf, anchor_color, offsets, tol=10, region=None, limit=500):
    """多点找色：在 anchor_color 命中的候选点上，再校验若干「相对偏移 + 颜色」。

    offsets = [(dx, dy, color), ...]，dx/dy 是相对锚点的偏移。
    返回第一个全部满足的锚点坐标 (x, y)，找不到返回 None。

    典型用法：血条为红色、其右边 30 像素处是黑色底 —— 单点找色容易误判，
    加上偏移点就能唯一确定目标。
    """
    ar, ag, ab = parse_color(anchor_color)
    checks = []
    for item in (offsets or []):
        if len(item) < 3:
            raise VisionError("偏移点格式应为 (dx, dy, 颜色)：%s" % (item,))
        dx, dy = int(item[0]), int(item[1])
        cr, cg, cb = parse_color(item[2])
        checks.append((dx, dy, cr, cg, cb))
    if not checks:
        raise VisionError("多点找色至少需要一个偏移点")

    tol = max(0, int(tol))
    hits = find_color(w, h, buf, (ar, ag, ab), tol, region, limit=limit)
    if hits["count"] == 0:
        return None
    mv = memoryview(buf)
    for (x, y) in hits["points"]:
        ok = True
        for (dx, dy, cr, cg, cb) in checks:
            px, py = x + dx, y + dy
            if px < 0 or py < 0 or px >= w or py >= h:
                ok = False
                break
            i = (py * w + px) * 4
            if (abs(mv[i] - cb) > tol or abs(mv[i + 1] - cg) > tol
                    or abs(mv[i + 2] - cr) > tol):
                ok = False
                break
        if ok:
            return (x, y)
    return None


# --------------------------------------------------------------------------
# 找图
# --------------------------------------------------------------------------

def _sample_offsets(tw, th, want=48):
    """在模板上均匀取 want 个点（相对模板左上角），用于快速筛候选。"""
    total = tw * th
    if total <= want:
        return [(x, y) for y in range(th) for x in range(tw)]
    step = max(1, int((total / float(want)) ** 0.5))
    pts = [(x, y) for y in range(0, th, step) for x in range(0, tw, step)]
    # 补上四个角，保证边界信息
    for corner in ((0, 0), (tw - 1, 0), (0, th - 1), (tw - 1, th - 1)):
        if corner not in pts:
            pts.append(corner)
    # 均匀抽稀到 want 个
    if len(pts) > want:
        stride = len(pts) / float(want)
        pts = [pts[int(i * stride)] for i in range(want)]
    return pts


def _match_at(hw, buf, tmpl, tx, ty, tol, offsets, full_check=True):
    mv = memoryview(buf)
    tw, th, tbuf = tmpl
    tmv = memoryview(tbuf)
    for (dx, dy) in offsets:
        ti = (dy * tw + dx) * 4
        hi = ((ty + dy) * hw + (tx + dx)) * 4
        if (abs(tmv[ti] - mv[hi]) > tol or abs(tmv[ti + 1] - mv[hi + 1]) > tol
                or abs(tmv[ti + 2] - mv[hi + 2]) > tol):
            return False
    if not full_check:
        return True
    for y in range(th):
        trow = y * tw * 4
        hrow = (ty + y) * hw * 4
        for x in range(tw):
            ti = trow + x * 4
            hi = hrow + (tx + x) * 4
            if (abs(tmv[ti] - mv[hi]) > tol or abs(tmv[ti + 1] - mv[hi + 1]) > tol
                    or abs(tmv[ti + 2] - mv[hi + 2]) > tol):
                return False
    return True


def find_image(w, h, buf, tmpl, tol=12, region=None, max_results=8, step=1):
    """在 haystack 中查找模板。

    tmpl = (tw, th, bgra_bytes)。返回 [(x, y, 匹配度 0~1), ...]，按匹配度降序。
    """
    tw, th, tbuf = tmpl
    if tw <= 0 or th <= 0:
        raise VisionError("模板尺寸无效")
    x0, y0, rw, rh = _region_clip(w, h, region)
    if rw < tw or rh < th:
        return []

    tol = max(0, int(tol))
    step = max(1, int(step))
    offsets = _sample_offsets(tw, th)
    seeds = offsets[:8]
    results = []
    y_end = y0 + rh - th
    x_end = x0 + rw - tw
    total_px = float(tw * th)

    for y in range(y0, y_end + 1, step):
        for x in range(x0, x_end + 1, step):
            if not _match_at(w, buf, tmpl, x, y, tol, seeds, full_check=False):
                continue
            if not _match_at(w, buf, tmpl, x, y, tol, offsets, full_check=True):
                continue
            # 统计匹配像素比例，作为匹配度
            mv = memoryview(buf)
            tmv = memoryview(tbuf)
            good = 0
            for yy in range(th):
                trow = yy * tw * 4
                hrow = (y + yy) * w * 4
                for xx in range(tw):
                    ti = trow + xx * 4
                    hi = hrow + (x + xx) * 4
                    if (abs(tmv[ti] - mv[hi]) <= tol and abs(tmv[ti + 1] - mv[hi + 1]) <= tol
                            and abs(tmv[ti + 2] - mv[hi + 2]) <= tol):
                        good += 1
            results.append((x, y, good / total_px))
            if len(results) >= max_results * 4:
                break
        if len(results) >= max_results * 4:
            break

    results.sort(key=lambda r: -r[2])
    # 去掉互相重叠的结果
    picked = []
    for (x, y, score) in results:
        if any(abs(x - px) < tw // 2 and abs(y - py) < th // 2 for (px, py, _s) in picked):
            continue
        picked.append((x, y, score))
        if len(picked) >= max_results:
            break
    return picked


def image_similarity(w, h, buf, tmpl, x, y, tol=12):
    """模板放在 (x,y) 处的匹配度（0~1）。"""
    tw, th, tbuf = tmpl
    if x < 0 or y < 0 or x + tw > w or y + th > h:
        return 0.0
    mv = memoryview(buf)
    tmv = memoryview(tbuf)
    good = 0
    for yy in range(th):
        trow = yy * tw * 4
        hrow = (y + yy) * w * 4
        for xx in range(tw):
            ti = trow + xx * 4
            hi = hrow + (x + xx) * 4
            if (abs(tmv[ti] - mv[hi]) <= tol and abs(tmv[ti + 1] - mv[hi + 1]) <= tol
                    and abs(tmv[ti + 2] - mv[hi + 2]) <= tol):
                good += 1
    return good / float(tw * th)
