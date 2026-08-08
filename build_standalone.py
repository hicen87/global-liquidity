# -*- coding: utf-8 -*-
"""从当前 index.html 精确内联三个本地数据脚本。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
OUTPUT = ROOT / "index_standalone.html"
SCRIPTS = ("data.js", "data_weekly.js", "summary.js")


def build() -> str:
    html = INDEX.read_text(encoding="utf-8")
    for name in SCRIPTS:
        tag = f'<script defer src="{name}"></script>'
        if html.count(tag) != 1:
            raise RuntimeError(f"expected exactly one script tag: {tag}")
        source = (ROOT / name).read_text(encoding="utf-8")
        html = html.replace(tag, f"<script>\n{source}\n</script>", 1)
    for name in SCRIPTS:
        if f'src="{name}"' in html:
            raise RuntimeError(f"local script reference remains: {name}")
    return html


if __name__ == "__main__":
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"WROTE {OUTPUT}")
