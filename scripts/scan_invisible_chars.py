from __future__ import annotations

import argparse
from pathlib import Path

BAD_CHARS = {
    "\u00a0": "U+00A0 non-breaking space",
    "\u200b": "U+200B zero-width space",
    "\u200c": "U+200C zero-width non-joiner",
    "\u200d": "U+200D zero-width joiner",
    "\ufeff": "U+FEFF BOM",
}

TEXT_SUFFIXES = {".py", ".md", ".txt", ".sql", ".toml", ".yaml", ".yml", ".json", ".csv", ".gitignore"}
SKIP_PARTS = {".git", ".venv", "__pycache__", "data", "outputs"}


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore"


def scan(root: Path) -> list[str]:
    problems: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if not is_text_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for char, label in BAD_CHARS.items():
                if char in line:
                    problems.append(f"{path}:{line_no}: {label}")
            for col, char in enumerate(line, start=1):
                if ord(char) < 32 and char not in "\t\r\n":
                    problems.append(f"{path}:{line_no}:{col}: control char U+{ord(char):04X}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    problems = scan(Path(args.root))
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("Nenhum caractere invisivel ou controle invalido encontrado.")


if __name__ == "__main__":
    main()
