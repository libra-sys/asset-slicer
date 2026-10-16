# -*- coding: utf-8 -*-
"""
asset-slicer · 切图 / 规格化 / 出图工具

子命令分两类：
  【本地算法，无需 API】
    trim         裁透明空边
    grid         网格切图（已知行列）
    detect       连通域算法切图（元素大小不一/ 位置随机首选）
    grid-detect  智能网格检测（自动推断行列）
    debg         边缘种子洪水填充去背景（保元素内部同色）
    dedup        感知哈希去重
    adapt        等比适配 + 留白对齐
    batch        批量处理目录
  【材料流水线】
    pdf2png      PDF 逐页转 PNG
    mask         隐私打码（按比例）
    cards        批量等比统一规格卡片
    spec         按 spec.json 落位留白/安全区/九宫格
  【需 API】
    artgen       调图片生成 API 出图（结果可直接被 detect/grid 切）
"""
import argparse
import base64
import json
import os
import sys
import time
import zipfile

from PIL import Image

DEFAULT_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _read_json(path):
    """⚠️ Windows 上 PowerShell 写的 JSON 常带 UTF-8 BOM，必须用 utf-8-sig 容错"""
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_cfg(path=None):
    p = path or os.environ.get("CONTEST_PPT_CONFIG") or DEFAULT_CFG
    if not os.path.exists(p):
        p2 = os.path.join(os.path.dirname(p), "config.example.json")
        if os.path.exists(p2):
            print("[cfg] config.json 缺失，改用模板：", p2)
            p = p2
        else:
            print("[cfg] 找不到配置文件：", DEFAULT_CFG)
            sys.exit(1)
    return _read_json(p)


def _load(path):
    return Image.open(path).convert("RGBA")


# ================================================================ trim

def do_trim(args):
    img = _load(args.input)
    bbox = img.split()[-1].getbbox()
    if not bbox:
        print("trim: 全透明，无可裁内容")
        return
    out = img.crop(bbox)
    out.save(args.output or args.input)
    print("trim:", img.size, "->", out.size, "->", args.output or args.input)


# ================================================================ grid

def do_grid(args):
    img = _load(args.input)
    W, H = img.size
    cols, rows = args.cols, args.rows
    cw, ch = W // cols, H // rows
    outdir = args.output or (os.path.splitext(args.input)[0] + "_grid")
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cw, r * ch
            x1 = W if c == cols - 1 else x0 + cw
            y1 = H if r == rows - 1 else y0 + ch
            img.crop((x0, y0, x1, y1)).save(
                os.path.join(outdir, "r%02d_c%02d.png" % (r, c)))
            n += 1
    print("grid: %dx%d -> %d 张-> %s" % (cols, rows, n, outdir))


# ================================================================ detect

def _connected_boxes(mask, min_size, connectivity, min_area=0):
    """
    mask: PIL 'L' 模式二值图（255=元素）
    返回 [(x0,y0,x1,y1), ...]
    优先 scipy.ndimage，无则纯 Python flood fill 回退。

    ⚠️ min_size 是**宽高**阈值，min_area 是**像素面积**阈值，两者解决不同问题：
       - min_size过滤「太窄/太矮」的碎片（如细线、描边）
       - min_area 过滤「宽高够但面积小」的碎片（如热力图小格子、图表里的小柱子）
         2026-10 实测：dashboard 图5 个面板里有热力图，用 min-size 只能提到 0 个，
         必须靠 min-area 才能把大面板留下、把 64 个小格子滤掉。
    """
    try:
        import numpy as np
        from scipy import ndimage
        arr = (np.array(mask) > 127).astype(np.uint8)
        structure = ndimage.generate_binary_structure(2, 1 if connectivity == 4 else 2)
        labeled, n = ndimage.label(arr, structure=structure)
        boxes = []
        for sl in ndimage.find_objects(labeled):
            if sl is None:
                continue
            y0, y1 = sl[0].start, sl[0].stop
            x0, x1 = sl[1].start, sl[1].stop
            if (x1 - x0) >= min_size and (y1 - y0) >= min_size:
                if min_area and (x1 - x0) * (y1 - y0) < min_area:
                    continue
                boxes.append((x0, y0, x1, y1))
        return boxes
    except ImportError:
        return _connected_boxes_py(mask, min_size, connectivity, min_area)


def _connected_boxes_py(mask, min_size, connectivity, min_area=0):
    """纯 Python flood fill 回退"""
    W, H = mask.size
    px = mask.load()
    seen = [[False] * H for _ in range(W)]
    out = []
    nbrs = ([(-1, 0), (1, 0), (0, -1), (0, 1)] if connectivity == 4
            else [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)])
    for sx in range(W):
        for sy in range(H):
            if px[sx, sy] <= 127 or seen[sx][sy]:
                continue
            stack = [(sx, sy)]
            seen[sx][sy] = True
            x0 = x1 = sx
            y0 = y1 = sy
            while stack:
                x, y = stack.pop()
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
                for dx, dy in nbrs:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H \
                            and not seen[nx][ny] and px[nx, ny] > 127:
                        seen[nx][ny] = True
                        stack.append((nx, ny))
            if (x1 - x0 + 1) >= min_size and (y1 - y0 + 1) >= min_size:
                if min_area and (x1 - x0 + 1) * (y1 - y0 + 1) < min_area:
                    continue
                out.append((x0, y0, x1 + 1, y1 + 1))
    return out


def do_detect(args):
    img = _load(args.input)
    alpha = img.split()[-1]
    mask = alpha.point(
        lambda a: 255 if a > args.alpha_threshold else 0).convert("L")
    boxes = _connected_boxes(mask, args.min_size, args.connectivity,
                             getattr(args, "min_area", 0))
    outdir = args.output or (os.path.splitext(args.input)[0] + "_detect")
    os.makedirs(outdir, exist_ok=True)
    man = []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        sub = img.crop((x0, y0, x1, y1))
        name = "e%03d_%dx%d.png" % (i, x1 - x0, y1 - y0)
        sub.save(os.path.join(outdir, name))
        man.append({"index": i, "file": name, "x": x0, "y": y0,
                    "w": x1 - x0, "h": y1 - y0})
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print("detect: 识别 %d 个元素 -> %s（+ manifest.json）" % (len(boxes), outdir))


# ================================================================ grid-detect

def _is_gap_pixel(p, mode, threshold):
    r, g, b = p[:3]
    lum = (r + g + b) / 3
    return lum <= 60 if mode == "dark" else lum >= threshold


def _is_line(prof, mode, threshold, line_ratio):
    if not prof:
        return False
    hits = sum(1 for p in prof if _is_gap_pixel(p, mode, threshold))
    return hits / len(prof) >= line_ratio


def do_grid_detect(args):
    img = _load(args.input).convert("RGB")
    W, H = img.size
    px = img.load()

    col_prof = [[px[x, y] for y in range(H)] for x in range(W)]
    row_prof = [[px[x, y] for x in range(W)] for y in range(H)]

    def count(prof_list):
        """
        格数 = 内部缝数 + 1
        ⚠️ 必须用 _gap_runs（内部已做 edge 过滤），否则图像外边距
        会被当成格间分隔，3×3 会误判成 4×4 / 5×5。
        """
        runs = []
        for i, prof in enumerate(prof_list):
            if _is_line(prof, args.mode, args.threshold, args.line_ratio):
                runs.append((i, i + 1))
        # 合并连续的线成缝区间，再剔除紧贴图像边缘的外边距
        merged = []
        for a, b in runs:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        edge = max(1, int(len(prof_list) * 0.02))
        inner = [r for r in merged if r[0] > edge and r[1] < len(prof_list) - edge]
        return inner

    col_runs = count(col_prof)
    row_runs = count(row_prof)
    cols = len(col_runs) + 1
    rows = len(row_runs) + 1
    print("grid-detect: 推断 %d x %d" % (cols, rows))

    if not args.force and sys.stdin is not None and sys.stdin.isatty():
        try:
            ans = input("确认？直接回车继续，或输入 CxR 覆盖：").strip()
            if ans and "x" in ans.lower():
                r, c = ans.lower().split("x")
                rows, cols = int(r), int(c)
                print("已覆盖为 %dx%d" % (rows, cols))
        except Exception:
            pass

    outdir = args.output or (os.path.splitext(args.input)[0] + "_grid")
    os.makedirs(outdir, exist_ok=True)
    src = _load(args.input)
    xs = [0] + [(a + b) // 2 for a, b in col_runs] + [W]
    ys = [0] + [(a + b) // 2 for a, b in row_runs] + [H]
    n = 0
    for r in range(rows):
        for c in range(cols):
            src.crop((xs[c], ys[r], xs[c + 1], ys[r + 1])).save(
                os.path.join(outdir, "r%02d_c%02d.png" % (r, c)))
            n += 1
    print("grid-detect: 切出 %d 张 -> %s" % (n, outdir))


# ================================================================ debg

def do_debg(args):
    import numpy as np
    img = _load(args.input)
    rgb = np.array(img.convert("RGB")).astype(np.int16)
    H, W = rgb.shape[:2]
    flat = rgb.reshape(-1, 3)

    # 边缘像素做背景色采样
    edges = np.concatenate([rgb[0, :, :], rgb[-1, :, :],
                            rgb[:, 0, :], rgb[:, -1, :]])
    bg = np.median(edges, axis=0)

    dist = np.linalg.norm(flat - bg, axis=1)
    is_bg = dist <= args.tolerance

    # 从四边种子向内泛洪（只波及与边缘连通的同色区）
    from collections import deque
    reach = np.zeros(H * W, dtype=bool)
    q = deque()
    def push(x, y):
        i = y * W + x
        if not reach[i] and is_bg[i]:
            reach[i] = True
            q.append(i)
    for x in range(W):
        push(x, 0); push(x, H - 1)
    for y in range(H):
        push(0, y); push(W - 1, y)
    while q:
        i = q.popleft()
        y, x = divmod(i, W)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                push(nx, ny)

    # 边缘一致性检查
    consistency = is_bg[:W].mean()
    if consistency < args.min_consistency:
        print("debg: 边缘一致性仅 %.0f%%（< %d%%），放弃去背。请改用 rembg 或 AI 抠图"
              % (consistency * 100, args.min_consistency * 100))
        return

    a = np.array(img.split()[-1])
    a[reach.reshape(H, W)] = 0
    out = img.copy()
    out.putalpha(Image.fromarray(a))
    if args.trim:
        bbox = out.split()[-1].getbbox()
        if bbox:
            out = out.crop(bbox)
    dst = args.output or args.input
    out.save(dst)
    print("debg: 一致性 %.0f%%，透明 %d 像素 -> %s%s"
          % (consistency * 100, int(reach.sum()), dst, "（已 trim）" if args.trim else ""))


# ================================================================ dedup

def do_dedup(args):
    try:
        import imagehash
        from PIL import Image as I
    except ImportError:
        print("dedup: 需要 imagehash，pip install imagehash")
        return

    folder = args.folder
    files = sorted(f for f in os.listdir(folder)
                   if f.lower().endswith((".png", ".jpg", ".jpeg")))
    hashes = {}
    for f in files:
        hashes[f] = imagehash.phash(I.open(os.path.join(folder, f)))

    print("共 %d 张" % len(files))
    dups = []
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            d = hashes[files[i]] - hashes[files[j]]
            if d <= args.threshold:
                dups.append((files[i], files[j], d))
                print("  重复 %s <- %s  (距离 %d)" % (files[i], files[j], d))

    if dups and args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        with open(os.path.join(args.outdir, "duplicates.json"), "w",
                  encoding="utf-8") as f:
            # ⚠️ numpy 的汉明距离是 int64，直接 dump 会报 not JSON serializable
            json.dump([{"a": a, "b": b, "distance": int(d)} for a, b, d in dups],
                      f, ensure_ascii=False, indent=2)
        print("重复清单 -> %s" % os.path.join(args.outdir, "duplicates.json"))
    if not dups:
        print("无重复")


# ================================================================ adapt

def do_adapt(args):
    img = _load(args.input)
    W, H = args.width, args.height
    if args.trim:
        bbox = img.split()[-1].getbbox()
        if bbox:
            img = img.crop(bbox)
    iw, ih = img.size
    if args.mode == "cover":
        s = max(W / iw, H / ih)
    else:
        s = min(W / iw, H / ih)
    nw, nh = int(iw * s), int(ih * s)
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ox = (W - nw) // 2 + args.offset_x
    oy = (H - nh) // 2 + args.offset_y
    canvas.paste(img, (ox, oy))
    out = args.output or args.input
    canvas.save(out)
    print("adapt: %s(%dx%d) -> %dx%d，mode=%s，不变形"
          % (os.path.basename(args.input), iw, ih, nw, nh, args.mode))


# ================================================================ batch

def do_batch(args):
    files = sorted(f for f in os.listdir(args.input)
                   if f.lower().endswith((".png", ".jpg", ".jpeg")))
    os.makedirs(args.output, exist_ok=True)
    for f in files:
        do_adapt(argparse.Namespace(
            input=os.path.join(args.input, f), width=args.width, height=args.height,
            mode=args.mode, offset_x=0, offset_y=0, trim=args.trim,
            output=os.path.join(args.output, f)))
    print("batch: 共 %d 张 -> %s" % (len(files), args.output))


# ================================================================ pdf2png

def _pdf2png_one(mod, path, outdir, tag, scale):
    doc = mod.open(path)
    n = 0
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=mod.Matrix(scale, scale))
        pix.save(os.path.join(outdir, "%s_p%02d.png" % (tag, i)))
        n += 1
    doc.close()
    print("  %s -> %d 页" % (tag, n))
    return n


def _safe(s):
    out = [ch if (ch.isalnum() or ch in "-_") else "" for ch in s]
    return "".join(out)[:24] or "doc"


def do_pdf2png(args):
    import glob
    import pymupdf

    os.makedirs(args.outdir, exist_ok=True)
    files = []
    if os.path.isdir(args.path):
        files += sorted(glob.glob(os.path.join(args.path, "*.pdf")))
        files += sorted(glob.glob(os.path.join(args.path, "**", "*.pdf"),
                                  recursive=True))
    elif args.path:
        files = [args.path]

    zips = sorted(glob.glob(os.path.join(args.path if os.path.isdir(args.path)
                                           else os.path.dirname(args.path),
                                           "*.zip")))
    tmp = os.path.join(args.outdir, "_tmp.pdf")
    total = 0
    for f in files:
        tag = args.tag or _safe(os.path.splitext(os.path.basename(f))[0])
        total += _pdf2png_one(pymupdf, f, args.outdir, tag, args.scale)

    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for nm in zf.namelist():
                if not nm.lower().endswith(".pdf"):
                    continue
                if args.only and args.only not in nm:
                    continue
                with open(tmp, "wb") as fh:
                    fh.write(zf.read(nm))
                tag = args.tag or _safe(os.path.splitext(os.path.basename(nm))[0])
                total += _pdf2png_one(pymupdf, tmp, args.outdir, tag, args.scale)
        if os.path.exists(tmp):
            os.remove(tmp)

    print("[pdf2png] 共 %d 页 -> %s" % (total, args.outdir))


# ================================================================ mask

def do_mask(args):
    from PIL import ImageDraw

    ratios = []
    for grp in args.ratios.split(";"):
        grp = grp.strip()
        if grp:
            ratios.append(tuple(float(x) for x in grp.split(",")))
    if any(len(r) != 4 for r in ratios):
        print("mask: --ratios 格式 x0,y0,x1,y1（多块用分号隔开）")
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    src = args.input
    files = ([src] if os.path.isfile(src)
             else sorted(f for f in os.listdir(src) if f.lower().endswith(".png")))

    for f in files:
        p = f if os.path.isfile(src) else os.path.join(src, f)
        img = Image.open(p).convert("RGB")
        W, Hh = img.size
        d = ImageDraw.Draw(img)
        for rx0, ry0, rx1, ry1 in ratios:
            box = [int(rx0 * W), int(ry0 * Hh),
                   min(int(rx1 * W), W), min(int(ry1 * Hh), Hh)]
            if box[2] > box[0] and box[3] > box[1]:
                d.rectangle(box, fill=(255, 255, 255))
        out = os.path.join(args.outdir, os.path.basename(p))
        img.save(out)
        print("mask:", os.path.basename(p), "->", out, img.size)


# ================================================================ cards

def do_cards(args):
    os.makedirs(args.outdir, exist_ok=True)
    files = sorted(f for f in os.listdir(args.input)
                   if f.lower().endswith((".png", ".jpg", ".jpeg")))
    man = []
    for f in files:
        src = os.path.join(args.input, f)
        img = Image.open(src).convert("RGB")
        iw, ih = img.size
        s = min(args.width / iw, args.height / ih)
        nw, nh = int(iw * s), int(ih * s)
        small = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (args.width, args.height), (255, 255, 255))
        canvas.paste(small, ((args.width - nw) // 2, (args.height - nh) // 2))
        out = os.path.join(args.outdir, "card_" + f)
        canvas.save(out)
        man.append({"file": f, "orig": [iw, ih], "card": "card_" + f,
                    "card_size": [args.width, args.height]})
        print("cards:", f, "->", out, (nw, nh))
    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    print("cards: 共 %d 张，manifest.json 已写入" % len(man))


# ================================================================ spec

def do_spec(args):
    from PIL import ImageDraw

    sp = _read_json(args.spec)
    cc = sp.get("canvas", {})
    cw, ch = cc.get("width", 1024), cc.get("height", 1024)
    pad = sp.get("padding", {})
    pt_, pr = pad.get("top", 0), pad.get("right", 0)
    pb, pl = pad.get("bottom", 0), pad.get("left", 0)
    safe = sp.get("safe_area", {}).get("inset", 0)
    nine = sp.get("nine_grid", {})

    os.makedirs(args.outdir, exist_ok=True)
    files = sorted(f for f in os.listdir(args.input)
                   if f.lower().endswith((".png", ".jpg", ".jpeg")))
    for f in files:
        img = Image.open(os.path.join(args.input, f)).convert("RGBA")
        iw, ih = img.size
        bw, bh = cw - pl - pr, ch - pt_ - pb
        s = min(bw / iw, bh / ih)
        img = img.resize((int(iw * s), int(ih * s)), Image.LANCZOS)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ox = pl + (bw - img.width) // 2
        oy = pt_ + (bh - img.height) // 2
        canvas.paste(img, (ox, oy))

        if args.guides:
            d = ImageDraw.Draw(canvas)
            if safe:
                m = int(cw * safe)
                d.rectangle([m, m, cw - m, ch - m], outline=(255, 0, 0, 90), width=2)
            if nine.get("rows") and nine.get("cols"):
                for i in range(1, nine["rows"]):
                    y = ch * i // nine["rows"]
                    d.line([0, y, cw, y], fill=(255, 255, 0, 70), width=2)
                for j in range(1, nine["cols"]):
                    x = cw * j // nine["cols"]
                    d.line([x, 0, x, ch], fill=(255, 255, 0, 70), width=2)

        out = os.path.join(args.outdir, f)
        canvas.save(out)
        print("spec:", f, "->", out, (cw, ch))
    print("spec: 完成。留白 上%d 右%d 下%d 左%d，安全区 %.0f%%"
          % (pt_, pr, pb, pl, safe * 100))


# ================================================================ artgen

PROVIDER_MAP = {
    "gpt-image-2": "openai",
    "gpt-image-2.5-flare": "openai",
    "gpt-image-2.5-sunburst": "openai",
    "gpt-image-2-official": "openai",
    "gemini-3-pro-image": "google",
}


def _hdr(key):
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def _extract_b64(resp):
    """同步端点返回 Gemini 原生格式；同时兼容 OpenAI 的 data[].b64_json"""
    cands = resp.get("candidates")
    if isinstance(cands, list):
        for c in cands:
            for part in c.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    return part["inlineData"]["data"]
    for d in (resp.get("data") or []):
        if isinstance(d, dict) and d.get("b64_json"):
            return d["b64_json"]
    return None


def _poll(base, key, task_id, tries, gap):
    import requests
    url = base + "/v1/images/generation/tasks/" + task_id
    for i in range(tries):
        try:
            r = requests.get(url, headers={"Authorization": "Bearer " + key},
                             timeout=45)
            if r.status_code != 200:
                print("  poll %d http %d" % (i, r.status_code))
                time.sleep(gap)
                continue
            d = r.json().get("data", {})
            st = d.get("status")
            print("  poll %d status=%s" % (i, st))
            if st in ("success", "succeeded", "completed"):
                return (d.get("images") or [{}])[0].get("url")
            if st in ("failed", "error"):
                return None
        except requests.exceptions.Timeout:
            print("  poll %d timeout, retry" % i)   # ⚠️ 实测会偶发超时
        except Exception as e:
            print("  poll %d %s" % (i, type(e).__name__))
        time.sleep(gap)
    return None


def do_artgen(args):
    import requests

    cfg = load_cfg(args.config)
    if args.provider not in cfg["供应商"]:
        print("artgen: 配置里没有供应商 %s" % args.provider)
        sys.exit(1)
    pc = cfg["供应商"][args.provider]
    key = pc.get("api_key", "")
    if not key or key.startswith("在此填入") or key == "sk-...":
        print("artgen: api_key 还是占位符 —— 请在 %s 里填真实密钥" % args.config)
        sys.exit(2)
    base = pc["base_url"].rstrip("/")
    os.makedirs(args.outdir, exist_ok=True)

    if args.jobsjson:
        jobs = _read_json(args.jobsjson)
    else:
        if args.prompt_file:
            with open(args.prompt_file, encoding="utf-8") as f:
                pr = f.read().strip()
        elif args.prompt:
            pr = args.prompt
        else:
            print("artgen: 需要 --prompt / --prompt-file / --jobsjson")
            sys.exit(1)
        jobs = [{"name": args.name, "prompt": pr,
                 "model": args.model or pc.get("model"), "size": args.size}]

    if not args.skip_estimate:
        try:
            r = requests.post(base + "/v1/images/generation/estimate-credits",
                              headers=_hdr(key),
                              json={"provider": args.provider_name,
                                    "model": jobs[0].get("model", "gpt-image-2"),
                                    "prompt": "estimate"}, timeout=90)
            d = r.json().get("data", {})
            print("[artgen] 预估积分 %s（单张），canGenerate=%s，共%d 张"
                  % (d.get("credits"), d.get("canGenerate"), len(jobs)))
            if d.get("canGenerate") is False:
                print("artgen: 积分不足")
                sys.exit(3)
        except Exception as e:
            print("[artgen] 预估失败（不阻断）：", type(e).__name__)

    # ⚠️ 实测单张 1K 出图要 3-10 分钟，串行跑 6 张 = 1 小时。默认并发 4。
    n = max(1, min(args.jobs, len(jobs)))
    if n > 1:
        from concurrent.futures import ThreadPoolExecutor
        print("[artgen] 并发 %d 路开跑（共 %d 张）" % (n, len(jobs)))
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(_one_image, base, key, j, pc, args, args.provider_name)
                    for j in jobs]
            for fu in futs:
                nm, ok, msg = fu.result()
                print("  %s %s — %s" % ("✔" if ok else "✗", nm, msg))
        return

    for j in jobs:
        name = j["name"]
        model = j.get("model") or pc.get("model") or "gpt-image-2"
        provider = (j.get("provider") or pc.get("provider")
                    or PROVIDER_MAP.get(model) or args.provider_name)
        size = j.get("size") or args.size
        print("\n[artgen] === %s (%s / %s / %s) ==="
              % (name, model, provider, size))
        payload = {"provider": provider, "model": model,
                   "prompt": j["prompt"], "imageSize": size}
        try:
            r = requests.post(base + "/v1/images/generation", headers=_hdr(key),
                              json=payload, timeout=args.timeout)
            if r.status_code == 200:
                b64 = _extract_b64(r.json())
                if b64:
                    p = os.path.join(args.outdir, name + ".png")
                    with open(p, "wb") as f:
                        f.write(base64.b64decode(b64))
                    print("  ✔ SYNC ->", p)
                    continue
        except Exception as e:
            print("  sync 异常，转异步：", type(e).__name__)

        r = requests.post(base + "/v1/images/generation/async", headers=_hdr(key),
                          json=payload, timeout=60)
        r.raise_for_status()
        tid = r.json()["data"]["taskId"]
        print("  taskId=%s（1K 实测 60-90s）" % tid)
        url = _poll(base, key, tid, args.tries, args.gap)
        if not url:
            print("  ✗ 失败：", name)
            continue
        p = os.path.join(args.outdir, name + ".png")
        with open(p, "wb") as f:
            f.write(requests.get(url, timeout=120).content)
        print("  ✔ ASYNC ->", p)


def _one_image(base, key, j, pc, args, provider_name):
    """出单张图：先同步，失败/超时转异步轮询。返回 (name, ok, msg)"""
    name = j["name"]
    model = j.get("model") or pc.get("model") or "gpt-image-2"
    provider = (j.get("provider") or pc.get("provider")
                or PROVIDER_MAP.get(model) or provider_name)
    size = j.get("size") or args.size
    payload = {"provider": provider, "model": model,
               "prompt": j["prompt"], "imageSize": size}
    p = os.path.join(args.outdir, name + ".png")
    try:
        r = requests.post(base + "/v1/images/generation", headers=_hdr(key),
                          json=payload, timeout=args.timeout)
        if r.status_code == 200:
            b64 = _extract_b64(r.json())
            if b64:
                with open(p, "wb") as f:
                    f.write(base64.b64decode(b64))
                return name, True, "SYNC"
    except Exception:
        pass
    try:
        r = requests.post(base + "/v1/images/generation/async", headers=_hdr(key),
                          json=payload, timeout=60)
        r.raise_for_status()
        tid = r.json()["data"]["taskId"]
        url = _poll(base, key, tid, args.tries, args.gap)
        if not url:
            return name, False, "轮询超时"
        with open(p, "wb") as f:
            f.write(requests.get(url, timeout=120).content)
        return name, True, "ASYNC %s" % tid
    except Exception as e:
        return name, False, "%s: %s" % (type(e).__name__, e)


# ================================================================ CLI

def build_parser():
    ap = argparse.ArgumentParser(
        prog="slice.py", description="切图 / 规格化 / 出图工具")
    s = ap.add_subparsers(dest="cmd", required=True)

    g = s.add_parser("trim", help="裁透明空边")
    g.add_argument("input")
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_trim)

    g = s.add_parser("grid", help="网格切图")
    g.add_argument("input")
    g.add_argument("--cols", type=int, required=True)
    g.add_argument("--rows", type=int, required=True)
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_grid)

    g = s.add_parser("detect", help="★连通域算法切图")
    g.add_argument("input")
    g.add_argument("--min-size", type=int, default=8,
                   help="宽高阈值（像素），滤掉太窄/太矮的碎片")
    g.add_argument("--min-area", type=int, default=0,
                   help="★面积阈值（像素²）。滤掉宽高够但面积小的碎片——"
                        "热力图/图表里的小格子只能靠这个滤")
    g.add_argument("--alpha-threshold", type=int, default=10)
    g.add_argument("--connectivity", type=int, choices=[4, 8], default=8)
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_detect)

    g = s.add_parser("grid-detect", help="★智能网格检测")
    g.add_argument("input")
    g.add_argument("--mode", choices=["light", "dark"], default="light")
    g.add_argument("--threshold", type=int, default=230)
    g.add_argument("--line-ratio", type=float, default=0.85)
    g.add_argument("--force", action="store_true")
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_grid_detect)

    g = s.add_parser("debg", help="★边缘种子洪水填充去背景")
    g.add_argument("input")
    g.add_argument("--tolerance", type=int, default=25)
    g.add_argument("--min-consistency", type=float, default=0.42)
    g.add_argument("--trim", action="store_true")
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_debg)

    g = s.add_parser("dedup", help="★感知哈希去重")
    g.add_argument("folder")
    g.add_argument("--threshold", type=int, default=5)
    g.add_argument("--outdir", help="重复清单输出目录")
    g.set_defaults(fn=do_dedup)

    g = s.add_parser("adapt", help="等比适配 + 留白对齐")
    g.add_argument("input")
    g.add_argument("--width", type=int, required=True)
    g.add_argument("--height", type=int, required=True)
    g.add_argument("--mode", choices=["contain", "cover"], default="contain")
    g.add_argument("--offset-x", type=int, default=0)
    g.add_argument("--offset-y", type=int, default=0)
    g.add_argument("--trim", action="store_true")
    g.add_argument("-o", "--output")
    g.set_defaults(fn=do_adapt)

    g = s.add_parser("batch", help="批量等比适配目录")
    g.add_argument("--input", required=True)
    g.add_argument("--output", required=True)
    g.add_argument("--width", type=int, required=True)
    g.add_argument("--height", type=int, required=True)
    g.add_argument("--mode", choices=["contain", "cover"], default="contain")
    g.add_argument("--trim", action="store_true")
    g.set_defaults(fn=do_batch)

    g = s.add_parser("pdf2png", help="PDF 逐页转 PNG（材料前置）")
    g.add_argument("--path", required=True)
    g.add_argument("--outdir", default="./pdf_out")
    g.add_argument("--tag")
    g.add_argument("--scale", type=float, default=2.0)
    g.add_argument("--only", help="zip 内文件名含此串才转")
    g.set_defaults(fn=do_pdf2png)

    g = s.add_parser("mask", help="★隐私打码（按比例）")
    g.add_argument("--input", required=True)
    g.add_argument("--outdir", required=True)
    g.add_argument("--ratios", required=True, help="x0,y0,x1,y1；多块用分号隔开")
    g.set_defaults(fn=do_mask)

    g = s.add_parser("cards", help="★批量等比统一规格卡片 + manifest")
    g.add_argument("--input", required=True)
    g.add_argument("--outdir", required=True)
    g.add_argument("--width", type=int, default=600)
    g.add_argument("--height", type=int, default=840)
    g.set_defaults(fn=do_cards)

    g = s.add_parser("spec", help="按 spec.json 落位留白/安全区/九宫格")
    g.add_argument("--input", required=True)
    g.add_argument("--outdir", required=True)
    g.add_argument("--spec", required=True)
    g.add_argument("--guides", action="store_true")
    g.set_defaults(fn=do_spec)

    g = s.add_parser("artgen", help="★出图（需 API，结果可直接被 detect/grid 切）")
    g.add_argument("--prompt")
    g.add_argument("--prompt-file")
    g.add_argument("--jobsjson", help='[{"name","prompt","model","size"}]')
    g.add_argument("--provider", default="listenhub-image")
    g.add_argument("--provider-name", default="openai",
                   help="provider 字段值（openai/google/quotaflow/alibaba/bytedance）")
    g.add_argument("--name", default="image")
    g.add_argument("--model")
    g.add_argument("--size", default="1K", choices=["1K", "2K", "4K"])
    g.add_argument("--outdir", default="./artgen_out")
    g.add_argument("--config")
    g.add_argument("--tries", type=int, default=40)
    g.add_argument("--gap", type=int, default=6)
    g.add_argument("--timeout", type=int, default=240)
    g.add_argument("--jobs", type=int, default=4,
                   help="★并发路数。单张 1K 实测 3-10 分钟，串行 6 张≈1 小时，"
                        "批量出图务必并发（默认 4，1=串行）")
    g.add_argument("--skip-estimate", action="store_true")
    g.set_defaults(fn=do_artgen)

    return ap


def main():
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()