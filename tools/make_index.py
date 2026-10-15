"""photos/ の中身を調べて photos/index.json を作る。

  photos/sakutyan/001.jpg  → {"sakutyan": ["sakutyan/001.jpg", ...]}
  photos/oidon.jpg (直置き) → {"oidon": ["oidon.jpg"]} も同じ扱い
"""
import json
from pathlib import Path

PHOTOS = Path(__file__).resolve().parent.parent / "photos"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def main() -> None:
    index: dict[str, list[str]] = {}
    for p in sorted(PHOTOS.iterdir()):
        if p.is_dir():
            files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in EXTS)
            index.setdefault(p.name, []).extend(f"{p.name}/{f.name}" for f in files)
        elif p.is_file() and p.suffix.lower() in EXTS:
            index.setdefault(p.stem, []).append(p.name)
    out = PHOTOS / "index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in index.items()})


if __name__ == "__main__":
    main()
