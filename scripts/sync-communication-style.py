#!/usr/bin/env python3
"""
Синхронизирует communication-style слои с downstream-файлами.

Трёхслойная архитектура (WP-388 Ф8, АрхГейт 3 июня):
  L0 (платформа) — PACK-digital-platform/.../DP.SC.050-communication-style-base.md  → все downstream
  L1 (автор)     — DS-my-strategy/memory/communication-style-author.md              → авторские downstream
  L2 (пользователь) — у каждого свой, не синхронизируется скриптом

Источник истины: PACK-digital-platform (по решению АрхГейта).
FMT-файл, корневые CLAUDE.md/AGENTS.md, бот, шлюз, skill Гермеса = проекции.

Запуск:
    # Только L0 (все downstream)
    python3 scripts/sync-communication-style.py

    # L0 + L1 (авторские downstream)
    python3 scripts/sync-communication-style.py \\
        --author-style ~/IWE/DS-my-strategy/memory/communication-style-author.md

    # Проверка расхождений (Week Close)
    python3 scripts/sync-communication-style.py --check

    # Hermes memory export
    python3 scripts/sync-communication-style.py \\
        --author-style ~/IWE/DS-my-strategy/memory/communication-style-author.md \\
        --hermes-export /tmp/hermes-style-rules.txt
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Источник истины L0 (Pack) - относительно IWE root
PACK_BASE_FILE = Path("PACK-digital-platform/pack/digital-platform/08-service-clauses/DP.SC.050-communication-style-base.md")

# Fallback: FMT-копия (если Pack недоступен)
FMT_BASE_FILE = Path("FMT-exocortex-template/memory/communication-style-base.md")

# Маркеры для markdown-файлов
MD_START = "<!-- COMMUNICATION-STYLE-BASE-START -->"
MD_END = "<!-- COMMUNICATION-STYLE-BASE-END -->"

# Маркеры для JS/TS файлов
JS_START = "// COMMUNICATION-STYLE-BASE-START"
JS_END = "// COMMUNICATION-STYLE-BASE-END"

# Все downstream-файлы (относительно IWE root).
# type: "l0" = только база, "l0+l1" = база + авторский слой
# ftype: "markdown" | "js" | "copy" (полная копия без маркеров)
DOWNSTREAM_FILES = [
    # FMT-шаблон (проекция L0)
    ("FMT-exocortex-template/AGENTS.md", "markdown", "l0"),
    ("FMT-exocortex-template/CLAUDE.md", "markdown", "l0"),
    # Корневые файлы автора (L0+L1)
    ("DS-my-strategy/exocortex/AGENTS.md", "markdown", "l0+l1"),
    ("DS-my-strategy/exocortex/CLAUDE.md", "markdown", "l0+l1"),
    # Бот Aisystant
    ("DS-MCP/aisystant-bot/src/standard_claude.md", "markdown", "l0"),
    # Gateway MCP (браузерный Claude.ai)
    ("DS-MCP/gateway-mcp/src/index.ts", "js", "l0"),
]


def strip_frontmatter(text: str) -> str:
    """Убирает YAML frontmatter."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def read_base_content(iwe_root: Path) -> str:
    """Читает L0 из Pack (SoT). Fallback: FMT-копия."""
    pack_path = iwe_root / PACK_BASE_FILE
    if pack_path.exists():
        print(f"Source: Pack (SoT) - {pack_path}")
        return strip_frontmatter(pack_path.read_text(encoding="utf-8"))

    fmt_path = iwe_root / FMT_BASE_FILE
    if fmt_path.exists():
        print(f"WARNING: Pack SoT not found, falling back to FMT copy: {fmt_path}", file=sys.stderr)
        return strip_frontmatter(fmt_path.read_text(encoding="utf-8"))

    print(f"ERROR: L0 base file not found in Pack or FMT", file=sys.stderr)
    sys.exit(1)


def read_author_content(author_path: str) -> str:
    """Читает L1 communication-style-author.md."""
    path = Path(author_path)
    if not path.exists():
        print(f"WARNING: L1 author file not found: {path}, skipping L1 merge")
        return ""
    return strip_frontmatter(path.read_text(encoding="utf-8"))


def merge_l0_l1(l0: str, l1: str) -> str:
    """Объединяет L0 + L1 в один блок для авторских downstream."""
    if not l1:
        return l0
    return f"""{l0}

---

<!-- L1: авторские правила (поверх L0) -->

{l1}"""


def generate_hermes_export(l0: str, l1: str, output_path: str) -> None:
    """Генерирует компактный текст правил для Hermes memory/skill."""
    merged = merge_l0_l1(l0, l1)

    # Извлекаем нумерованные правила (строки начинающиеся с цифры и точки)
    rules = []
    for line in merged.split("\n"):
        line = line.strip()
        if re.match(r"^\d+\.\s+\*\*", line) or re.match(r"^###\s+R\d+", line):
            # Убираем markdown bold
            clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
            rules.append(clean)

    header = "# Правила разговорного стиля IWE (L0 + L1)\n"
    header += "# Автогенерация: sync-communication-style.py\n"
    header += f"# Правил: {len(rules)}\n\n"

    content = header + "\n".join(rules) + "\n"

    Path(output_path).write_text(content, encoding="utf-8")
    print(f"  HERMES  {output_path} ({len(rules)} rules)")


def update_markdown(path: Path, content: str) -> bool:
    """Обновляет markdown-файл между MD маркерами."""
    if not path.exists():
        print(f"WARNING: file not found: {path}")
        return False

    text = path.read_text(encoding="utf-8")
    pattern = f"({re.escape(MD_START)})\\n*.*?\\n*({re.escape(MD_END)})"
    replacement = f"{MD_START}\\n\\n{content}\\n\\n{MD_END}"
    new_text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)

    if count == 0:
        print(f"WARNING: markers not found in {path}")
        return False

    path.write_text(new_text, encoding="utf-8")
    print(f"  OK  {path}")
    return True


def update_js(path: Path, content: str) -> bool:
    """Обновляет JS/TS файл между JS маркерами."""
    if not path.exists():
        print(f"WARNING: file not found: {path}")
        return False

    text = path.read_text(encoding="utf-8")
    escaped = content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    pattern = f"({re.escape(JS_START)})\\n*.*?\\n*({re.escape(JS_END)})"
    replacement = f"{JS_START}\\n{escaped}\\n{JS_END}"
    new_text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)

    if count == 0:
        print(f"WARNING: markers not found in {path}")
        return False

    path.write_text(new_text, encoding="utf-8")
    print(f"  OK  {path}")
    return True


def extract_between_markers(text: str, start_marker: str, end_marker: str) -> str:
    """Извлекает контент между маркерами."""
    pattern = f"{re.escape(start_marker)}\\n*(.+?)\\n*{re.escape(end_marker)}"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def check_drift(iwe_root: Path, l0_content: str) -> int:
    """Проверяет расхождение копий с SoT. Возвращает число drift'ов."""
    l0_hash = hashlib.md5(l0_content.encode()).hexdigest()
    drift_count = 0

    print(f"\nSoT md5: {l0_hash}")
    print(f"Checking {len(DOWNSTREAM_FILES)} downstream files...\n")

    for rel_path, ftype, layer_mode in DOWNSTREAM_FILES:
        path = iwe_root / rel_path
        if not path.exists():
            print(f"  SKIP  {rel_path} (not found)")
            continue

        text = path.read_text(encoding="utf-8")

        if ftype == "markdown":
            embedded = extract_between_markers(text, MD_START, MD_END)
        elif ftype == "js":
            embedded = extract_between_markers(text, JS_START, JS_END)
        else:
            continue

        if not embedded:
            print(f"  WARN  {rel_path} (no markers)")
            drift_count += 1
            continue

        # Для l0+l1 файлов, берём только L0 часть (до "<!-- L1:")
        if layer_mode == "l0+l1" and "<!-- L1:" in embedded:
            embedded = embedded.split("<!-- L1:")[0].strip()

        embedded_hash = hashlib.md5(embedded.encode()).hexdigest()

        if embedded_hash == l0_hash:
            print(f"  OK    {rel_path}")
        else:
            print(f"  DRIFT {rel_path} (md5: {embedded_hash})")
            drift_count += 1

    return drift_count


def main():
    parser = argparse.ArgumentParser(
        description="Sync communication style layers to downstream files (SoT: PACK-digital-platform)"
    )
    parser.add_argument(
        "--author-style",
        help="Path to L1 author style file (communication-style-author.md)",
    )
    parser.add_argument(
        "--hermes-export",
        help="Path to write Hermes-compatible rules export",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check for drift (md5 comparison), don't write",
    )
    parser.add_argument(
        "--iwe-root",
        default=str(Path.home() / "IWE"),
        help="IWE workspace root (default: ~/IWE)",
    )
    args = parser.parse_args()

    iwe_root = Path(args.iwe_root)
    l0 = read_base_content(iwe_root)
    l1 = read_author_content(args.author_style) if args.author_style else ""

    # Режим проверки drift
    if args.check:
        drift_count = check_drift(iwe_root, l0)
        if drift_count == 0:
            print(f"\nAll copies in sync.")
        else:
            print(f"\n{drift_count} drift(s) found. Run without --check to fix.")
        return 0 if drift_count == 0 else 1

    # Режим синхронизации
    ok_count = 0
    skip_count = 0

    print(f"Syncing L0 ({len(l0)} chars)" + (f" + L1 ({len(l1)} chars)" if l1 else "") + "...")

    for rel_path, ftype, layer_mode in DOWNSTREAM_FILES:
        path = iwe_root / rel_path
        if not path.exists():
            print(f"SKIP {rel_path} (not found)")
            skip_count += 1
            continue

        # Выбираем контент в зависимости от слоя
        if layer_mode == "l0+l1" and l1:
            content = merge_l0_l1(l0, l1)
        else:
            content = l0

        if ftype == "markdown":
            if update_markdown(path, content):
                ok_count += 1
        elif ftype == "js":
            if update_js(path, content):
                ok_count += 1
        else:
            print(f"UNKNOWN type {ftype} for {rel_path}")
            skip_count += 1

    # Hermes export
    if args.hermes_export:
        generate_hermes_export(l0, l1, args.hermes_export)

    print(f"Done: {ok_count} updated, {skip_count} skipped.")
    return 0 if skip_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
