from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from src.config import OUTPUTS_DIR, RAW_DIR, TMP_EXTRACT_DIR  # type: ignore
    from src.ingestao_receita import discover_receita_sources, iter_receita_rows  # type: ignore
    from src.utils import ensure_dirs, normalize_text  # type: ignore
else:
    from .config import OUTPUTS_DIR, RAW_DIR, TMP_EXTRACT_DIR
    from .ingestao_receita import discover_receita_sources, iter_receita_rows
    from .utils import ensure_dirs, normalize_text


def default_raw_paths() -> list[Path]:
    paths = [RAW_DIR]
    documents = Path.home() / "Documents"
    for candidate in documents.glob("*/download.zip"):
        paths.append(candidate)
        paths.append(candidate.parent)
    return paths


def _append_sample(samples: list[dict[str, str]], row: dict[str, str], limit: int) -> None:
    if len(samples) < limit:
        samples.append(dict(row))


def run_diagnostico(raw_paths: list[Path] | None = None) -> dict:
    ensure_dirs(OUTPUTS_DIR, TMP_EXTRACT_DIR)
    paths = raw_paths or default_raw_paths()
    sources, ignored = discover_receita_sources(paths)

    by_kind = {}
    for source in sources:
        by_kind.setdefault(source.kind, []).append(source)

    result: dict = {
        "raw_paths": [str(path) for path in paths],
        "arquivos_processados": [
            {
                "tipo": source.kind,
                "caminho": source.label,
                "tamanho_bytes": source.size,
                "processado": True,
            }
            for source in sources
        ],
        "arquivos_ignorados": [
            {
                "tipo": source.kind,
                "caminho": source.label,
                "tamanho_bytes": source.size if source.root_path.exists() else 0,
                "processado": False,
                "motivo": source.ignored_reason,
            }
            for source in ignored
        ],
        "bloqueios": [],
        "avisos": [],
    }

    estab_sources = by_kind.get("estabelecimentos", [])
    emp_sources = by_kind.get("empresas", [])
    required_estab = {f"Estabelecimentos{i}" for i in range(10)}
    required_emp = {f"Empresas{i}" for i in range(10)}
    found_estab = required_parts_found(estab_sources, "Estabelecimentos")
    found_emp = required_parts_found(emp_sources, "Empresas")
    result["partes_obrigatorias"] = {
        "estabelecimentos_esperados": sorted(required_estab),
        "estabelecimentos_encontrados": sorted(found_estab),
        "estabelecimentos_faltantes": sorted(required_estab - found_estab),
        "empresas_esperados": sorted(required_emp),
        "empresas_encontrados": sorted(found_emp),
        "empresas_faltantes": sorted(required_emp - found_emp),
    }
    if not estab_sources:
        result["bloqueios"].append("Nenhum arquivo de Estabelecimentos foi encontrado.")
    if not emp_sources:
        result["bloqueios"].append("Nenhum arquivo de Empresas foi encontrado.")
    if required_estab - found_estab:
        result["bloqueios"].append("Partes obrigatorias de Estabelecimentos ausentes: " + ", ".join(sorted(required_estab - found_estab)))
    if required_emp - found_emp:
        result["bloqueios"].append("Partes obrigatorias de Empresas ausentes: " + ", ".join(sorted(required_emp - found_emp)))
    if result["bloqueios"]:
        write_report(result)
        return result

    cnpjs_sc_ativos: set[str] = set()
    municipios_sc_ativos: set[str] = set()
    cnaes_sc_ativos: set[str] = set()
    uf_counter: Counter[str] = Counter()
    situacao_sc_counter: Counter[str] = Counter()
    strange_uf_counter: Counter[str] = Counter()
    estab_rows_by_file: dict[str, int] = {}
    estab_sample: list[dict[str, str]] = []
    sc_rows = 0
    sc_active_rows = 0

    for source in estab_sources:
        count = 0
        for row in iter_receita_rows(source, TMP_EXTRACT_DIR):
            count += 1
            _append_sample(estab_sample, row, 5)
            uf = row.get("uf", "").strip().upper()
            situacao = row.get("situacao_cadastral", "").strip()
            uf_counter[uf] += 1
            if not uf or len(uf) != 2 or not uf.isalpha():
                strange_uf_counter[uf] += 1
            if uf == "SC":
                sc_rows += 1
                situacao_sc_counter[situacao] += 1
                if situacao in {"02", "2"}:
                    sc_active_rows += 1
                    cnpj = row.get("cnpj_basico", "")
                    if cnpj:
                        cnpjs_sc_ativos.add(cnpj)
                    municipio = row.get("municipio", "")
                    if municipio:
                        municipios_sc_ativos.add(municipio)
                    cnae = row.get("cnae_fiscal_principal", "")
                    if cnae:
                        cnaes_sc_ativos.add(cnae)
        estab_rows_by_file[source.label] = count

    result["estabelecimentos"] = {
        "arquivos_encontrados": len(estab_sources),
        "arquivos_processados": len(estab_rows_by_file),
        "linhas_por_arquivo": estab_rows_by_file,
        "total_linhas_lidas": sum(estab_rows_by_file.values()),
        "amostra_primeiras_5": estab_sample,
        "top_10_ufs": uf_counter.most_common(10),
        "ufs_estranhas_top_20": strange_uf_counter.most_common(20),
        "registros_uf_sc": sc_rows,
        "situacao_cadastral_sc": dict(situacao_sc_counter),
        "registros_sc_ativos": sc_active_rows,
        "cnpj_basico_unicos_sc_ativos": len(cnpjs_sc_ativos),
        "municipios_distintos_sc_ativos": len(municipios_sc_ativos),
        "amostra_20_municipios_sc": sorted(municipios_sc_ativos)[:20],
        "cnaes_distintos_sc_ativos": len(cnaes_sc_ativos),
    }

    emp_rows_by_file: dict[str, int] = {}
    emp_sample: list[dict[str, str]] = []
    empresas_match = 0
    empresas_match_cnpjs: set[str] = set()
    naturezas_sc: set[str] = set()
    for source in emp_sources:
        count = 0
        for row in iter_receita_rows(source, TMP_EXTRACT_DIR):
            count += 1
            _append_sample(emp_sample, row, 5)
            cnpj = row.get("cnpj_basico", "")
            if cnpj in cnpjs_sc_ativos:
                empresas_match += 1
                empresas_match_cnpjs.add(cnpj)
                natureza = row.get("natureza_juridica", "")
                if natureza:
                    naturezas_sc.add(natureza)
        emp_rows_by_file[source.label] = count
    match_pct = 100 * len(empresas_match_cnpjs) / len(cnpjs_sc_ativos) if cnpjs_sc_ativos else 0
    result["empresas"] = {
        "arquivos_encontrados": len(emp_sources),
        "arquivos_processados": len(emp_rows_by_file),
        "linhas_por_arquivo": emp_rows_by_file,
        "total_linhas_lidas": sum(emp_rows_by_file.values()),
        "amostra_primeiras_5": emp_sample,
        "empresas_com_cnpj_sc_ativo": empresas_match,
        "cnpj_sc_ativos_com_match_empresa": len(empresas_match_cnpjs),
        "percentual_match_cnpj": round(match_pct, 2),
    }

    municipio_codes = set()
    municipio_sample = []
    municipio_total = 0
    for source in by_kind.get("municipios", []):
        for row in iter_receita_rows(source, TMP_EXTRACT_DIR):
            municipio_total += 1
            _append_sample(municipio_sample, row, 10)
            code = row.get("codigo_municipio_receita", "")
            if code:
                municipio_codes.add(code)
    municipio_match_pct = 100 * len(municipios_sc_ativos & municipio_codes) / len(municipios_sc_ativos) if municipios_sc_ativos else 0
    result["municipios"] = {
        "total_lido": municipio_total,
        "amostra_primeiras_10": municipio_sample,
        "codigos_sc_ativos_com_match": len(municipios_sc_ativos & municipio_codes),
        "percentual_match": round(municipio_match_pct, 2),
    }

    cnae_codes = set()
    cnae_sample = []
    cnae_total = 0
    for source in by_kind.get("cnaes", []):
        for row in iter_receita_rows(source, TMP_EXTRACT_DIR):
            cnae_total += 1
            _append_sample(cnae_sample, row, 10)
            code = row.get("cnae", "")
            if code:
                cnae_codes.add(code)
    cnae_match_pct = 100 * len(cnaes_sc_ativos & cnae_codes) / len(cnaes_sc_ativos) if cnaes_sc_ativos else 0
    result["cnaes"] = {
        "total_lido": cnae_total,
        "amostra_primeiras_10": cnae_sample,
        "cnaes_sc_ativos_distintos": len(cnaes_sc_ativos),
        "cnaes_sc_ativos_com_descricao": len(cnaes_sc_ativos & cnae_codes),
        "percentual_match": round(cnae_match_pct, 2),
    }

    natureza_codes = set()
    natureza_total = 0
    for source in by_kind.get("naturezas", []):
        for row in iter_receita_rows(source, TMP_EXTRACT_DIR):
            natureza_total += 1
            code = row.get("natureza_juridica", "")
            if code:
                natureza_codes.add(code)
    natureza_match_pct = 100 * len(naturezas_sc & natureza_codes) / len(naturezas_sc) if naturezas_sc else 0
    result["naturezas"] = {
        "total_lido": natureza_total,
        "naturezas_empresas_sc_distintas": len(naturezas_sc),
        "naturezas_empresas_sc_com_descricao": len(naturezas_sc & natureza_codes),
        "percentual_match": round(natureza_match_pct, 2),
    }

    apply_blockers(result, len(estab_sources), len(estab_rows_by_file), bool(cnae_codes))
    write_report(result)
    return result


def apply_blockers(result: dict, estab_found: int, estab_processed: int, cnae_present: bool) -> None:
    est = result.get("estabelecimentos", {})
    emp = result.get("empresas", {})
    cnaes = result.get("cnaes", {})
    blocks = result["bloqueios"]

    if est.get("registros_sc_ativos", 0) < 100_000:
        blocks.append(f"Menos de 100.000 estabelecimentos ativos em SC: {est.get('registros_sc_ativos', 0)}.")
    if est.get("municipios_distintos_sc_ativos", 0) < 100:
        blocks.append(f"Menos de 100 municipios distintos em SC: {est.get('municipios_distintos_sc_ativos', 0)}.")
    if cnae_present and cnaes.get("cnaes_sc_ativos_com_descricao", 0) < 1_000:
        blocks.append(f"Menos de 1.000 CNAEs distintos descritos: {cnaes.get('cnaes_sc_ativos_com_descricao', 0)}.")
    if emp.get("percentual_match_cnpj", 0) < 80:
        blocks.append(f"Match entre estabelecimentos SC ativos e empresas abaixo de 80%: {emp.get('percentual_match_cnpj', 0)}%.")
    top_ufs = dict(est.get("top_10_ufs", []))
    if "SC" not in top_ufs and est.get("registros_uf_sc", 0) < 100_000:
        blocks.append("Contagem por UF nao mostra SC de forma relevante.")
    if estab_found > 2 and estab_processed <= 2:
        blocks.append(f"Apenas {estab_processed} arquivos de estabelecimentos processados, mas {estab_found} foram encontrados.")
    required = result.get("partes_obrigatorias", {})
    if required.get("estabelecimentos_faltantes"):
        blocks.append("Estabelecimentos0-9 nao foram encontrados por completo.")
    if required.get("empresas_faltantes"):
        blocks.append("Empresas0-9 nao foram encontrados por completo.")
    if est.get("ufs_estranhas_top_20"):
        strange_total = sum(count for _, count in est["ufs_estranhas_top_20"])
        if strange_total > max(1000, 0.01 * est.get("total_linhas_lidas", 0)):
            blocks.append("Campo UF tem muitos valores vazios, numericos ou estranhos; provavel schema deslocado.")
    situacoes = est.get("situacao_cadastral_sc", {})
    if not situacoes or ("02" not in situacoes and "2" not in situacoes):
        blocks.append("Situacao cadastral em SC nao contem valores 02/2; provavel schema, delimitador ou filtro incorreto.")


def write_report(result: dict) -> None:
    path = OUTPUTS_DIR / "diagnostico_ingestao.md"
    json_path = OUTPUTS_DIR / "diagnostico_ingestao.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Diagnostico de Ingestao", ""]
    lines.append("## Status")
    if result["bloqueios"]:
        lines.append("BLOQUEADO")
        lines.extend(f"- {item}" for item in result["bloqueios"])
    else:
        lines.append("APROVADO")
    lines.append("")

    if "partes_obrigatorias" in result:
        lines.append("## Partes obrigatorias Empresas0-9 e Estabelecimentos0-9")
        lines.append("```json")
        lines.append(json.dumps(result["partes_obrigatorias"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    lines.append("## Fontes analisadas")
    for path_item in result.get("raw_paths", []):
        lines.append(f"- {path_item}")
    lines.append("")

    lines.append("## Arquivos encontrados")
    for item in result.get("arquivos_processados", []) + result.get("arquivos_ignorados", []):
        status = "processado" if item["processado"] else f"ignorado: {item.get('motivo', '')}"
        lines.append(f"- {item['tipo']} | {item['tamanho_bytes']} bytes | {status} | {item['caminho']}")
    lines.append("")

    for section in ("estabelecimentos", "empresas", "municipios", "cnaes", "naturezas"):
        if section in result:
            lines.append(f"## {section.capitalize()}")
            lines.append("```json")
            lines.append(json.dumps(result[section], indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def required_parts_found(sources, prefix: str) -> set[str]:
    found: set[str] = set()
    for source in sources:
        text = source.label.lower()
        for index in range(10):
            token = f"{prefix}{index}".lower()
            if token in text:
                found.add(f"{prefix}{index}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostico auditavel da ingestao Receita/IBGE.")
    parser.add_argument("--raw-dir", action="append", type=Path, help="Pasta ou arquivo bruto. Pode repetir.")
    args = parser.parse_args()
    result = run_diagnostico(args.raw_dir)
    print((OUTPUTS_DIR / "diagnostico_ingestao.md").read_text(encoding="utf-8"))
    if result["bloqueios"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
