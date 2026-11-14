#!/usr/bin/env python3
# ============================================================
# 加图，一条命令搞定。
#
#   1. 把图片放进 images/<日期>/ 目录（文件夹名就是首屏显示的日期）
#      —— 文件名带上分类，比如 meme-12.jpg、beauty-03.jpg
#   2. 在项目根目录运行：  python tools/optimize-images.py
#   3. git push
#
# 脚本会做五件事：
#   - 原图长边超过 1600 的，先缩到 1600 再压一遍
#     （页面最大只用到 1600 档，缩了肉眼无差，仓库能小一半多）
#     不想动原图就加 --no-slim
#   - 给每张图生成 480/640/800/1200/1600 五档 WebP（只缩小，绝不放大），
#     放在 images/<日期>/w/ 下
#   - 算出每张图的主色调，用作加载前的占位底色
#   - 把 PHOTOS 和 TINT 两块自动写回 index.html
#     宽高直接从图片里读，不用手填
#   - 清掉已经删除的图片留下的 WebP
#
# 分类怎么定，三个来源，优先级从高到低：
#   1. 这个文件已经出现在 index.html 里 -> 保持原分类不变
#   2. 文件名里带分类（meme-01 / 02-foot / beauty03）-> 用它
#   3. 都没有 -> 用 --cat，默认取该日期下的第一个分类
#
# 新日期要先去 index.html 的 ALBUMS 里加一行，否则会被跳过。
# 档位必须和 index.html 里的 LADDER 一致，改一边就要改另一边。
# ============================================================

import argparse
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

LADDER = (480, 640, 800, 1200, 1600)
# 每档质量分开给：小图手机上根本看不出差别，压狠一点；
# 大图主要给灯箱放大用，留得好一些。
QUALITY = {480: 60, 640: 62, 800: 66, 1200: 70, 1600: 72}

# 原图瘦身：长边超过这个值就缩小（页面最大只用到 1600 档）
SLIM_MAX = 1600
SLIM_QUALITY = 84

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "images"
INDEX = ROOT / "index.html"
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

P_START = "    /* ---- PHOTOS 开始：由 tools/optimize-images.py 自动生成，不要手改 ---- */"
P_END = "    /* ---- PHOTOS 结束 ---- */"
T_START = "    /* ---- TINT 开始：同上 ---- */"
T_END = "    /* ---- TINT 结束 ---- */"
A_START = "    /* ---- ALBUMS 开始：手改这里（新日期、分类、显示名） ---- */"
A_END = "    /* ---- ALBUMS 结束 ---- */"

ENTRY_RE = re.compile(r"src: '([^']+)'[^}]*cat: '([^']+)'")
ALBUM_RE = re.compile(r"\{\s*id: '([^']+)',\s*name: '([^']+)',\s*cats: \[(.*?)\]\s*\}", re.S)
CAT_RE = re.compile(r"\{\s*id: '([^']+)',\s*name: '([^']+)'\s*\}")


def parse_albums(html: str) -> list[dict]:
    block = html[html.index(A_START):html.index(A_END)]
    out = []
    for m in ALBUM_RE.finditer(block):
        cats = [{"id": c.group(1), "name": c.group(2)} for c in CAT_RE.finditer(m.group(3))]
        out.append({"id": m.group(1), "name": m.group(2), "cats": cats})
    return out


def parse_existing(html: str) -> dict[str, str]:
    block = html[html.index(P_START):html.index(P_END)]
    return {m.group(1): m.group(2) for m in ENTRY_RE.finditer(block)}


def guess_cat(stem: str, cats: list[dict]) -> str | None:
    low = stem.lower()
    parts = set(re.split(r"[^0-9a-z]+", low))
    for c in cats:
        cid = c["id"].lower()
        if cid in parts or low.startswith(cid):
            return c["id"]
    return None


def write_block(html: str, start: str, end: str, body: str) -> str:
    i = html.index(start)
    j = html.index(end, i) + len(end)
    return html[:i] + start + "\n" + body + "\n" + end + html[j:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default=None, help="文件名里没带分类时用的默认分类 id")
    ap.add_argument("--no-slim", dest="slim", action="store_false",
                    help="不改动原图，只生成 WebP 变体")
    args = ap.parse_args()

    html = INDEX.read_text(encoding="utf-8")
    albums = parse_albums(html)
    if not albums:
        print("!! index.html 里没读到 ALBUMS")
        return 1
    by_id = {a["id"]: a for a in albums}
    existing = parse_existing(html)

    on_disk = {p.name for p in IMAGES.iterdir() if p.is_dir() and p.name != "w"}
    unknown = on_disk - set(by_id)
    if unknown:
        print(f"!! 这些目录没有在 ALBUMS 里声明，已跳过：{', '.join(sorted(unknown))}")
        print("   先在 index.html 的 ALBUMS 里加一行再来。\n")

    entries, tints = [], []
    total_src = total_out = 0
    added, gone = [], []
    slimmed, slim_saved = 0, 0

    for album in albums:
        folder = IMAGES / album["id"]
        if not folder.is_dir():
            continue
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTS and p.is_file())
        if not files:
            continue

        out_dir = folder / "w"
        out_dir.mkdir(exist_ok=True)

        print(f"【{album['name']}】{len(files)} 张")
        allowed = {}
        for path in files:
            with Image.open(path) as raw:
                img = ImageOps.exif_transpose(raw).convert("RGB")

            w, h = img.size
            slim_note = ""

            # 原图太大就先瘦身，页面最大也只用到 1600 档
            # 重压后如果没明显变小（原图本来就压得很狠），就还原，绝不把一个文件改大
            if args.slim and path.suffix.lower() in (".jpg", ".jpeg") and max(w, h) > SLIM_MAX:
                ow, oh = w, h
                before = path.stat().st_size
                orig_bytes = path.read_bytes()
                scale = SLIM_MAX / max(w, h)
                nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
                cand = img.resize((nw, nh), Image.LANCZOS)
                cand.save(path, "JPEG", quality=SLIM_QUALITY, optimize=True, progressive=True)
                after = path.stat().st_size
                if after < before * 0.95:
                    img = cand
                    w, h = nw, nh
                    slimmed += 1
                    slim_saved += before - after
                    slim_note = f"\n      原图 {ow}x{oh} {before/1024:.0f}KB -> {nw}x{nh} {after/1024:.0f}KB"
                else:
                    path.write_bytes(orig_bytes)
                    slim_note = f"\n      原图 {w}x{h} {before/1024:.0f}KB 已经很紧凑，保持不动"

            r, g, b = img.resize((1, 1), Image.LANCZOS).getpixel((0, 0))[:3]
            tints.append((f"{album['id']}/{path.stem}", f"#{r:02x}{g:02x}{b:02x}"))

            targets = [t for t in LADDER if t <= w]
            size_out = 0
            for target in targets:
                nh2 = max(1, round(h * target / w))
                out = out_dir / f"{path.stem}-{target}.webp"
                img.resize((target, nh2), Image.LANCZOS).save(
                    out, "WEBP", quality=QUALITY[target], method=6
                )
                size_out += out.stat().st_size

            allowed[path.stem] = set(targets)
            total_src += path.stat().st_size
            total_out += size_out

            src = f"images/{album['id']}/{path.name}"
            cats = album["cats"]
            ids = [c["id"] for c in cats]
            cat = existing.get(src) or guess_cat(path.stem, cats)
            if cat is None:
                cat = args.cat if args.cat in ids else ids[0]
                print(f"    ? {path.name} 没写分类，先归到 {cat}")
            if cat not in ids:
                print(f"    !! {path.name} 的分类 {cat} 不在 {album['id']} 里，改归 {ids[0]}")
                cat = ids[0]

            if src not in existing:
                added.append((src, cat))
            entries.append((src, w, h, album["id"], cat))
            print(
                f"    {path.name:16}{w}x{h}{'':4}{size_out / 1024:7.0f}KB  [{cat}]"
                + slim_note
            )

        # 清掉已删除图片、以及档位已经不存在的残留
        for webp in out_dir.glob("*.webp"):
            stem, _, wpart = webp.stem.rpartition("-")
            if not wpart.isdigit() or int(wpart) not in allowed.get(stem, set()):
                webp.unlink()
                gone.append(webp.name)
        if not any(out_dir.iterdir()):
            shutil.rmtree(out_dir)
        print()

    if not entries:
        print("!! 没有可处理的图片")
        return 1

    print(
        f"合计 {len(entries)} 张：原图 {total_src / 1024 / 1024:.2f} MB，"
        f"全部档位 {total_out / 1024 / 1024:.2f} MB"
    )
    if slimmed:
        print(f"  原图瘦身 {slimmed} 张，省下 {slim_saved / 1024 / 1024:.1f} MB")
    for src, cat in added:
        print(f"  + 新增 {src} -> {cat}")
    if gone:
        print(f"  - 清理了 {len(gone)} 个已失效的 WebP")

    photos_body = ",\n".join(
        f"      {{ src: '{s}', w: {w}, h: {h}, a: '{a}', cat: '{c}' }}"
        for s, w, h, a, c in entries
    )
    tint_body = ",\n".join(f"      '{k}': '{v}'" for k, v in tints)

    html = write_block(html, P_START, P_END, "    const PHOTOS = [\n" + photos_body + "\n    ];")
    html = write_block(html, T_START, T_END, "    const TINT = {\n" + tint_body + "\n    };")
    INDEX.write_text(html, encoding="utf-8")
    print(f"\n已写回 {INDEX.name}：PHOTOS {len(entries)} 条，TINT {len(tints)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
