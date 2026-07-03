from __future__ import annotations

import csv
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from src.config import OUTPUTS_DIR  # type: ignore
else:
    from .config import OUTPUTS_DIR


def main() -> None:
    path = OUTPUTS_DIR / "qualidade_dados_sc.csv"
    if not path.exists():
        raise FileNotFoundError("Arquivo de qualidade nao encontrado. Rode o pipeline primeiro.")

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    errors = [row for row in rows if row.get("status") == "erro"]
    warnings = [row for row in rows if row.get("status") == "atencao"]

    print(f"Validacoes lidas: {len(rows)}")
    print(f"Erros: {len(errors)}")
    print(f"Atencoes: {len(warnings)}")
    for row in errors + warnings:
        print(f"- {row['status'].upper()} | {row['validacao']}: {row['valor']} {row.get('detalhe', '')}")

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
