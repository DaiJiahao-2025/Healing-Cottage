#!/usr/bin/env python3
# ============================================================
# 把 images/ 里的原图压成多尺寸 WebP，给 <picture><source srcset> 用。
#
# 用法（项目根目录下）：
#     python tools/optimize-images.py
#
# 产物：images/w/<文件名>-<宽度>.webp
#
# 规则：只在「档位宽度 <= 原图宽度」时生成，绝不放大。
#       这条规则必须和 app.js 里的 LADDER / widthsFor() 完全一致，
#       否则 srcset 会指向不存在的文件。
# ============================================================

import sys
from pathlib import Path

from PIL import Image, ImageOps

LADDER = (480, 800, 1200, 1600)  # 宽度档位，必须和 app.js 的 LADDER 一样
QUALITY = 76                     # WebP 质量：76 对照片够用，肉眼几乎无损

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "images"
OUT_DIR = SRC_DIR / "w"
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def main() -> int:
    if not SRC_DIR.is_dir():
        print(f"[ERROR] no images folder: {SRC_DIR}")
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    files = sorted(p for p in SRC_DIR.iterdir() if p.suffix.lower() in EXTS and p.is_file())
    if not files:
        print("[ERROR] no source images")
        return 1

    total_in = total_out = 0
    print(f"{'file':14} {'original':>12} {'variants':>10} {'new':>10} {'saved':>7}")
    print("-" * 58)

    for path in files:
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw)
            img = img.convert("RGB")
            w, h = img.size

            made, size_out = [], 0
            targets = [t for t in LADDER if t <= w]
            for target in targets:
                nh = max(1, round(h * target / w))
                out = OUT_DIR / f"{path.stem}-{target}.webp"
                img.resize((target, nh), Image.LANCZOS).save(
                    out, "WEBP", quality=QUALITY, method=6
                )
                made.append(target)
                size_out += out.stat().st_size

        size_in = path.stat().st_size
        total_in += size_in
        total_out += size_out
        saved = 100 * (1 - size_out / size_in) if size_in else 0
        print(
            f"{path.name:14} {size_in / 1024:9.0f} KB {str(made):>10} "
            f"{size_out / 1024:7.0f} KB {saved:6.0f}%"
        )

    print("-" * 58)
    print(
        f"TOTAL          {total_in / 1024 / 1024:8.2f} MB          "
        f"{total_out / 1024 / 1024:5.2f} MB "
        f"{100 * (1 - total_out / total_in) if total_in else 0:6.0f}%"
    )
    print(f"\n{len(files)} 张原图 -> {len(list(OUT_DIR.glob('*.webp')))} 个 WebP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
