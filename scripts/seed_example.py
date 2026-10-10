#!/usr/bin/env python3
"""把 examples/ 下的示例笔记复制进笔记库（data/vault），用于首次体验。

用法：python scripts/seed_example.py [--force]
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_vault_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖同名文件")
    args = parser.parse_args()

    examples = ROOT / "examples"
    vault = get_vault_dir()
    count = 0
    for src in examples.rglob("*.md"):
        rel = src.relative_to(examples)
        dst = vault / rel
        if dst.exists() and not args.force:
            print(f"跳过（已存在）：{rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"已导入：{rel}")
        count += 1
    print(f"\n完成，共导入 {count} 个文件。笔记库位置：{vault}")


if __name__ == "__main__":
    main()
