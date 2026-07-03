from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from io import TextIOWrapper
from pathlib import Path
from typing import Iterator

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from src.config import (  # type: ignore
        BRONZE_DIR,
        CNAES_COLUMNS,
        DB_PATH,
        EMPRESAS_COLUMNS,
        ESTABELECIMENTOS_COLUMNS,
        GOLD_DIR,
        MUNICIPIOS_COLUMNS,
        NATUREZAS_COLUMNS,
        OUTPUTS_DIR,
        SILVER_DIR,
        SIMPLES_COLUMNS,
        TMP_EXTRACT_DIR,
        UF_TARGET,
    )
    from src.diagnostico_ingestao import default_raw_paths, run_diagnostico  # type: ignore
    from src.ingestao_receita import ReceitaSource, discover_receita_sources, iter_receita_rows  # type: ignore
    from src.utils import clean_cell, ensure_dirs, normalize_text, only_digits, read_header  # type: ignore
else:
    from .config import (
        BRONZE_DIR,
        CNAES_COLUMNS,
        DB_PATH,
        EMPRESAS_COLUMNS,
        ESTABELECIMENTOS_COLUMNS,
        GOLD_DIR,
        MUNICIPIOS_COLUMNS,
        NATUREZAS_COLUMNS,
        OUTPUTS_DIR,
        SILVER_DIR,
        SIMPLES_COLUMNS,
        TMP_EXTRACT_DIR,
        UF_TARGET,
    )
    from .diagnostico_ingestao import default_raw_paths, run_diagnostico
    from .ingestao_receita import ReceitaSource, discover_receita_sources, iter_receita_rows
    from .utils import clean_cell, ensure_dirs, normalize_text, only_digits, read_header


def receita_rows(source: ReceitaSource, columns: list[str]):
    yield from iter_receita_rows(source, TMP_EXTRACT_DIR)


def sources_by_kind(sources: list[ReceitaSource], kind: str) -> Iterator[ReceitaSource]:
    yield from (source for source in sources if source.kind == kind)


def write_header(path: Path, columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=columns)
    writer.writeheader()
    return handle, writer


def process_estabelecimentos(sources: list[ReceitaSource], metrics: dict) -> set[str]:
    output = BRONZE_DIR / "estabelecimentos_sc_ativos.csv"
    cnpjs: set[str] = set()
    situacao_counter: Counter[str] = Counter()
    rows_by_file: dict[str, int] = {}
    sc_rows = 0
    active_sc_rows = 0

    handle, writer = write_header(output, ESTABELECIMENTOS_COLUMNS)
    try:
        for source in sources_by_kind(sources, "estabelecimentos"):
            count = 0
            for row in receita_rows(source, ESTABELECIMENTOS_COLUMNS):
                count += 1
                situacao = row["situacao_cadastral"]
                situacao_counter[situacao] += 1
                if row["uf"].strip().upper() != UF_TARGET:
                    continue
                sc_rows += 1
                if situacao not in {"02", "2"}:
                    continue
                active_sc_rows += 1
                writer.writerow(row)
                cnpjs.add(row["cnpj_basico"])
            rows_by_file[source.label] = count
    finally:
        handle.close()

    metrics["registros_estabelecimentos_por_arquivo"] = rows_by_file
    metrics["distribuicao_situacao_cadastral"] = dict(situacao_counter)
    metrics["estabelecimentos_sc"] = sc_rows
    metrics["estabelecimentos_ativos_sc"] = active_sc_rows
    metrics["cnpj_basico_unicos_sc"] = len(cnpjs)
    return cnpjs


def process_empresas(sources: list[ReceitaSource], cnpjs_sc: set[str], metrics: dict) -> None:
    output = BRONZE_DIR / "empresas_sc.csv"
    rows_by_file: dict[str, int] = {}
    matched = 0

    handle, writer = write_header(output, EMPRESAS_COLUMNS)
    try:
        for source in sources_by_kind(sources, "empresas"):
            count = 0
            for row in receita_rows(source, EMPRESAS_COLUMNS):
                count += 1
                if row["cnpj_basico"] in cnpjs_sc:
                    writer.writerow(row)
                    matched += 1
            rows_by_file[source.label] = count
    finally:
        handle.close()

    metrics["registros_empresas_por_arquivo"] = rows_by_file
    metrics["empresas_cruzadas_com_sucesso"] = matched


def process_dimension(
    sources: list[ReceitaSource],
    kind: str,
    columns: list[str],
    output_name: str,
    metrics: dict,
    cnpjs_sc: set[str] | None = None,
) -> None:
    output = BRONZE_DIR / output_name
    extra_cols = ["municipio_norm"] if kind == "municipios" else []
    handle, writer = write_header(output, columns + extra_cols)
    rows_by_file: dict[str, int] = {}
    kept = 0
    try:
        for source in sources_by_kind(sources, kind):
            count = 0
            for row in receita_rows(source, columns):
                count += 1
                if cnpjs_sc is not None and row.get("cnpj_basico") not in cnpjs_sc:
                    continue
                if kind == "municipios":
                    row["municipio_norm"] = normalize_text(row["nome_municipio_receita"])
                writer.writerow(row)
                kept += 1
            rows_by_file[source.label] = count
    finally:
        handle.close()
    metrics[f"registros_{kind}_por_arquivo"] = rows_by_file
    metrics[f"registros_{kind}_mantidos"] = kept


def find_consolidated_csv(sources: list[ReceitaSource], raw_paths: list[Path]) -> Path | None:
    candidates = [source.root_path for source in sources_by_kind(sources, "consolidado") if not source.archive_members]
    for path in candidates:
        if path.suffix.lower() == ".csv":
            return path
    for raw_path in raw_paths:
        if raw_path.is_dir():
            for path in raw_path.rglob("*.csv"):
                try:
                    _, header = read_header(path)
                except Exception:
                    continue
                normalized = [normalize_text(col) for col in header]
                if any("PIB" in col for col in normalized) and any("POP" in col for col in normalized):
                    return path
    return None


def pick_column(header: list[str], options: tuple[str, ...]) -> str | None:
    normalized = {normalize_text(col): col for col in header}
    for wanted in options:
        wanted_norm = normalize_text(wanted)
        for norm, original in normalized.items():
            if wanted_norm in norm:
                return original
    return None


def process_consolidado(sources: list[ReceitaSource], metrics: dict, raw_paths: list[Path]) -> None:
    output = BRONZE_DIR / "consolidado_pib_populacao.csv"
    columns = ["municipio_norm", "codigo_municipio_ibge", "cnae_principal", "populacao", "pib_per_capita"]
    excel_rows = read_consolidado_excel(raw_paths)
    if excel_rows:
        handle, writer = write_header(output, columns)
        for row in excel_rows:
            writer.writerow(row)
        handle.close()
        metrics["consolidado_pib_populacao"] = "arquivos Excel locais de PIB/populacao"
        metrics["registros_consolidado_lidos"] = len(excel_rows)
        return

    source_path = find_consolidated_csv(sources, raw_paths)
    handle, writer = write_header(output, columns)
    if not source_path:
        handle.close()
        metrics["consolidado_pib_populacao"] = "arquivo nao encontrado"
        return

    encoding, header = read_header(source_path)
    municipio_col = pick_column(header, ("municipio", "nome_municipio", "cidade"))
    ibge_col = pick_column(header, ("codigo_municipio_ibge", "cod_municipio_ibge", "ibge"))
    cnae_col = pick_column(header, ("cnae", "cnae_principal"))
    pop_col = pick_column(header, ("populacao", "população"))
    pib_col = pick_column(header, ("pib_per_capita", "pib per capita"))

    count = 0
    with source_path.open("r", encoding=encoding, newline="") as input_handle:
        sample = input_handle.read(4096)
        input_handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.DictReader(input_handle, dialect=dialect)
        for row in reader:
            count += 1
            out = {
                "municipio_norm": normalize_text(row.get(municipio_col, "")) if municipio_col else "",
                "codigo_municipio_ibge": only_digits(row.get(ibge_col, "")) if ibge_col else "",
                "cnae_principal": only_digits(row.get(cnae_col, "")) if cnae_col else "",
                "populacao": row.get(pop_col, "") if pop_col else "",
                "pib_per_capita": row.get(pib_col, "") if pib_col else "",
            }
            writer.writerow(out)
    handle.close()
    metrics["consolidado_pib_populacao"] = str(source_path)
    metrics["registros_consolidado_lidos"] = count


def read_consolidado_excel(raw_paths: list[Path]) -> list[dict[str, object]]:
    try:
        import pandas as pd
    except ImportError:
        return []

    files: list[Path] = []
    for raw_path in raw_paths:
        if raw_path.is_dir():
            files.extend(path for path in raw_path.iterdir() if path.suffix.lower() in {".xls", ".xlsx"})

    pib_by_ibge: dict[str, dict[str, object]] = {}
    pop_by_ibge: dict[str, dict[str, object]] = {}

    for path in files:
        name = normalize_text(path.name)
        if "PIB" in name:
            df = pd.read_excel(path)
            uf_col = pick_dataframe_column(df.columns, ("Sigla da Unidade da Federação", "UF"))
            ibge_col = pick_dataframe_column(df.columns, ("Código do Município", "Codigo do Municipio"))
            municipio_col = pick_dataframe_column(df.columns, ("Nome do Município", "Nome do Municipio"))
            pib_col = pick_dataframe_column(df.columns, ("Produto Interno Bruto per capita", "PIB per capita"))
            if not all([uf_col, ibge_col, municipio_col, pib_col]):
                continue
            df = df[df[uf_col].astype(str).str.upper().str.strip() == "SC"]
            for _, row in df.iterrows():
                ibge = only_digits(row.get(ibge_col, ""))
                if not ibge:
                    continue
                pib_by_ibge[ibge] = {
                    "municipio_norm": normalize_text(row.get(municipio_col, "")),
                    "codigo_municipio_ibge": ibge,
                    "pib_per_capita": row.get(pib_col, ""),
                }
        elif "POP" in name:
            df = pd.read_excel(path)
            uf_col = pick_dataframe_column(df.columns, ("UF",))
            ibge_col = pick_dataframe_column(df.columns, ("Código do Município", "Codigo do Municipio"))
            municipio_col = pick_dataframe_column(df.columns, ("NOME DO MUNICÍPIO", "Nome do Município", "Nome do Municipio"))
            pop_col = pick_dataframe_column(df.columns, ("POPULAÇÃO ESTIMADA", "Populacao", "População"))
            if not all([uf_col, ibge_col, municipio_col, pop_col]):
                continue
            df = df[df[uf_col].astype(str).str.upper().str.strip() == "SC"]
            for _, row in df.iterrows():
                ibge = only_digits(row.get(ibge_col, ""))
                if not ibge:
                    continue
                pop_by_ibge[ibge] = {
                    "municipio_norm": normalize_text(row.get(municipio_col, "")),
                    "codigo_municipio_ibge": ibge,
                    "populacao": row.get(pop_col, ""),
                }

    rows = []
    for ibge in sorted(set(pib_by_ibge) | set(pop_by_ibge)):
        merged = {
            "municipio_norm": (pib_by_ibge.get(ibge) or pop_by_ibge.get(ibge) or {}).get("municipio_norm", ""),
            "codigo_municipio_ibge": ibge,
            "cnae_principal": "",
            "populacao": pop_by_ibge.get(ibge, {}).get("populacao", ""),
            "pib_per_capita": pib_by_ibge.get(ibge, {}).get("pib_per_capita", ""),
        }
        rows.append(merged)
    return rows


def pick_dataframe_column(columns, options: tuple[str, ...]) -> str | None:
    normalized = {normalize_text(col): col for col in columns}
    for option in options:
        option_norm = normalize_text(option)
        for norm, original in normalized.items():
            if option_norm in norm:
                return original
    return None


def build_gold(metrics: dict) -> None:
    import duckdb

    con = duckdb.connect(str(DB_PATH))
    today = date.today().isoformat()

    con.execute(
        """
        CREATE OR REPLACE TABLE bronze_estabelecimentos AS
        SELECT * FROM read_csv_auto(?, header=true, all_varchar=true);
        """,
        [str(BRONZE_DIR / "estabelecimentos_sc_ativos.csv")],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE bronze_empresas AS
        SELECT * FROM read_csv_auto(?, header=true, all_varchar=true);
        """,
        [str(BRONZE_DIR / "empresas_sc.csv")],
    )
    con.execute("COPY bronze_estabelecimentos TO ? (FORMAT PARQUET);", [str(SILVER_DIR / "silver_estabelecimentos_sc_ativos.parquet")])
    con.execute("COPY bronze_empresas TO ? (FORMAT PARQUET);", [str(SILVER_DIR / "silver_empresas_sc.parquet")])

    for table, filename in {
        "dim_municipios": "municipios.csv",
        "dim_cnaes": "cnaes.csv",
        "dim_naturezas": "naturezas.csv",
        "dim_simples": "simples_sc.csv",
        "dim_consolidado": "consolidado_pib_populacao.csv",
    }.items():
        path = BRONZE_DIR / filename
        if path.exists() and path.stat().st_size > 0:
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto(?, header=true, all_varchar=true);",
                [str(path)],
            )

    con.execute(
        """
        CREATE OR REPLACE TABLE silver_empresas_ativas_sc AS
        WITH estab AS (
            SELECT
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                cnpj_basico || cnpj_ordem || cnpj_dv AS cnpj_completo,
                nome_fantasia,
                situacao_cadastral,
                try_strptime(data_inicio_atividade, '%Y%m%d')::DATE AS data_inicio_atividade,
                cnae_fiscal_principal AS cnae_principal,
                uf,
                municipio AS codigo_municipio_receita
            FROM bronze_estabelecimentos
        ),
        emp AS (
            SELECT
                cnpj_basico,
                razao_social,
                natureza_juridica,
                CASE porte_empresa
                    WHEN '00' THEN 'Nao informado'
                    WHEN '01' THEN 'Microempresa'
                    WHEN '03' THEN 'Empresa de pequeno porte'
                    WHEN '05' THEN 'Demais'
                    ELSE NULLIF(porte_empresa, '')
                END AS porte_empresa,
                try_cast(replace(replace(capital_social, '.', ''), ',', '.') AS DOUBLE) AS capital_social
            FROM bronze_empresas
        ),
        pib_municipio AS (
            SELECT
                municipio_norm,
                max(nullif(codigo_municipio_ibge, '')) AS codigo_municipio_ibge,
                max(try_cast(replace(replace(populacao, '.', ''), ',', '.') AS DOUBLE)) AS populacao,
                max(try_cast(replace(replace(pib_per_capita, '.', ''), ',', '.') AS DOUBLE)) AS pib_per_capita
            FROM dim_consolidado
            GROUP BY municipio_norm
        ),
        mun_dedup AS (
            SELECT
                codigo_municipio_receita,
                max(nome_municipio_receita) AS nome_municipio_receita,
                max(municipio_norm) AS municipio_norm
            FROM dim_municipios
            GROUP BY 1
        ),
        cnae_dedup AS (
            SELECT cnae, max(descricao_cnae) AS descricao_cnae
            FROM dim_cnaes
            GROUP BY 1
        ),
        nat_dedup AS (
            SELECT natureza_juridica, max(descricao_natureza_juridica) AS descricao_natureza_juridica
            FROM dim_naturezas
            GROUP BY 1
        ),
        simples_dedup AS (
            SELECT cnpj_basico, max(opcao_simples) AS opcao_simples, max(opcao_mei) AS opcao_mei
            FROM dim_simples
            GROUP BY 1
        )
        SELECT
            emp.cnpj_basico,
            estab.cnpj_ordem,
            estab.cnpj_dv,
            estab.cnpj_completo,
            emp.razao_social,
            estab.nome_fantasia,
            estab.situacao_cadastral,
            estab.uf,
            mun.nome_municipio_receita AS municipio,
            estab.codigo_municipio_receita,
            pib.codigo_municipio_ibge,
            estab.cnae_principal AS cnae_fiscal_principal,
            estab.cnae_principal,
            cnae.descricao_cnae,
            emp.natureza_juridica,
            nat.descricao_natureza_juridica,
            emp.porte_empresa,
            emp.capital_social,
            estab.data_inicio_atividade,
            greatest(0, date_diff('year', estab.data_inicio_atividade, cast(? AS DATE))) AS idade_empresa_anos,
            simp.opcao_simples,
            simp.opcao_mei,
            pib.populacao,
            pib.pib_per_capita
        FROM estab
        INNER JOIN emp ON emp.cnpj_basico = estab.cnpj_basico
        LEFT JOIN mun_dedup mun ON mun.codigo_municipio_receita = estab.codigo_municipio_receita
        LEFT JOIN cnae_dedup cnae ON cnae.cnae = estab.cnae_principal
        LEFT JOIN nat_dedup nat ON nat.natureza_juridica = emp.natureza_juridica
        LEFT JOIN simples_dedup simp ON simp.cnpj_basico = emp.cnpj_basico
        LEFT JOIN pib_municipio pib ON pib.municipio_norm = mun.municipio_norm;
        """,
        [today],
    )

    con.execute("CREATE OR REPLACE TABLE gold_empresas_ativas_sc AS SELECT * FROM silver_empresas_ativas_sc;")
    con.execute(
        """
        CREATE OR REPLACE TABLE gold_municipio_cnae_sc AS
        WITH base AS (
            SELECT
                uf,
                municipio,
                cnae_principal,
                descricao_cnae,
                count(*) AS total_empresas_ativas,
                sum(coalesce(capital_social, 0)) AS capital_social_total,
                median(capital_social) AS capital_social_mediano,
                avg(idade_empresa_anos) AS idade_media_empresas,
                median(idade_empresa_anos) AS idade_mediana_empresas,
                max(populacao) AS populacao
            FROM gold_empresas_ativas_sc
            GROUP BY 1, 2, 3, 4
        ),
        mun AS (
            SELECT municipio, sum(total_empresas_ativas) AS total_municipio
            FROM base
            GROUP BY 1
        )
        SELECT
            base.uf,
            base.municipio,
            base.cnae_principal,
            base.descricao_cnae,
            base.total_empresas_ativas,
            base.total_empresas_ativas / nullif(mun.total_municipio, 0) AS participacao_cnae_no_municipio,
            base.total_empresas_ativas * 10000.0 / nullif(base.populacao, 0) AS empresas_por_10k_habitantes,
            base.capital_social_total,
            base.capital_social_mediano,
            base.idade_media_empresas,
            base.idade_mediana_empresas
        FROM base
        LEFT JOIN mun USING (municipio);
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE gold_ranking_municipios_sc AS
        WITH base AS (
            SELECT
                municipio,
                max(populacao) AS populacao,
                max(pib_per_capita) AS pib_per_capita,
                count(*) AS total_empresas_ativas,
                count(DISTINCT cnae_principal) AS total_cnaes_distintos,
                count(*) * 10000.0 / nullif(max(populacao), 0) AS empresas_por_10k_habitantes,
                sum(coalesce(capital_social, 0)) AS capital_social_total
            FROM gold_empresas_ativas_sc
            GROUP BY 1
        ),
        norm AS (
            SELECT
                *,
                (populacao - min(populacao) OVER()) / nullif(max(populacao) OVER() - min(populacao) OVER(), 0) AS n_populacao,
                (pib_per_capita - min(pib_per_capita) OVER()) / nullif(max(pib_per_capita) OVER() - min(pib_per_capita) OVER(), 0) AS n_pib,
                (total_empresas_ativas - min(total_empresas_ativas) OVER()) / nullif(max(total_empresas_ativas) OVER() - min(total_empresas_ativas) OVER(), 0) AS n_empresas,
                (empresas_por_10k_habitantes - min(empresas_por_10k_habitantes) OVER()) / nullif(max(empresas_por_10k_habitantes) OVER() - min(empresas_por_10k_habitantes) OVER(), 0) AS n_densidade,
                (total_cnaes_distintos - min(total_cnaes_distintos) OVER()) / nullif(max(total_cnaes_distintos) OVER() - min(total_cnaes_distintos) OVER(), 0) AS n_diversidade,
                (capital_social_total - min(capital_social_total) OVER()) / nullif(max(capital_social_total) OVER() - min(capital_social_total) OVER(), 0) AS n_capital
            FROM base
        ),
        scored AS (
            SELECT
                municipio,
                populacao,
                pib_per_capita,
                total_empresas_ativas,
                total_cnaes_distintos,
                empresas_por_10k_habitantes,
                capital_social_total,
                100 * (
                    0.20 * coalesce(n_populacao, 0) +
                    0.20 * coalesce(n_pib, 0) +
                    0.20 * coalesce(n_empresas, 0) +
                    0.15 * coalesce(n_densidade, 0) +
                    0.15 * coalesce(n_diversidade, 0) +
                    0.10 * coalesce(n_capital, 0)
                ) AS score_oportunidade
            FROM norm
        )
        SELECT *, row_number() OVER (ORDER BY score_oportunidade DESC) AS posicao_ranking
        FROM scored
        ORDER BY posicao_ranking;
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE gold_ranking_cnaes_sc AS
        WITH base AS (
            SELECT
                cnae_principal,
                descricao_cnae,
                count(*) AS total_empresas_ativas,
                count(DISTINCT municipio) AS total_municipios_com_presenca,
                sum(coalesce(capital_social, 0)) AS capital_social_total,
                avg(idade_empresa_anos) AS idade_media_empresas
            FROM gold_empresas_ativas_sc
            GROUP BY 1, 2
        ),
        norm AS (
            SELECT
                *,
                (total_empresas_ativas - min(total_empresas_ativas) OVER()) / nullif(max(total_empresas_ativas) OVER() - min(total_empresas_ativas) OVER(), 0) AS n_empresas,
                (total_municipios_com_presenca - min(total_municipios_com_presenca) OVER()) / nullif(max(total_municipios_com_presenca) OVER() - min(total_municipios_com_presenca) OVER(), 0) AS n_presenca,
                (capital_social_total - min(capital_social_total) OVER()) / nullif(max(capital_social_total) OVER() - min(capital_social_total) OVER(), 0) AS n_capital
            FROM base
        )
        SELECT
            cnae_principal,
            descricao_cnae,
            total_empresas_ativas,
            total_municipios_com_presenca,
            capital_social_total,
            idade_media_empresas,
            100 * (0.45 * coalesce(n_empresas, 0) + 0.35 * coalesce(n_presenca, 0) + 0.20 * coalesce(n_capital, 0)) AS score_relevancia
        FROM norm
        ORDER BY score_relevancia DESC;
        """
    )

    validations = compute_quality(con, metrics)
    write_quality_csv(validations)
    con.execute(
        """
        CREATE OR REPLACE TABLE gold_qualidade_dados_sc AS
        SELECT * FROM read_csv_auto(?, header=true, all_varchar=true);
        """,
        [str(OUTPUTS_DIR / "qualidade_dados_sc.csv")],
    )

    for table, filename in {
        "gold_empresas_ativas_sc": "empresas_ativas_sc.csv",
        "gold_municipio_cnae_sc": "municipio_cnae_sc.csv",
        "gold_ranking_municipios_sc": "ranking_municipios_sc.csv",
        "gold_ranking_cnaes_sc": "ranking_cnaes_sc.csv",
        "gold_qualidade_dados_sc": "qualidade_dados_sc.csv",
    }.items():
        con.execute(f"COPY {table} TO ? (HEADER, DELIMITER ',');", [str(OUTPUTS_DIR / filename)])
        con.execute(f"COPY {table} TO ? (FORMAT PARQUET);", [str(GOLD_DIR / f"{table}.parquet")])

    metrics["duckdb"] = str(DB_PATH)
    metrics["validacoes"] = validations
    (OUTPUTS_DIR / "pipeline_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    con.close()


def compute_quality(con, metrics: dict) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []

    def add(metric: str, value: object, status: str = "ok", detail: str = "") -> None:
        result.append({"validacao": metric, "valor": value, "status": status, "detalhe": detail})

    add("registros_lidos_estabelecimentos", sum(metrics.get("registros_estabelecimentos_por_arquivo", {}).values()))
    add("estabelecimentos_sc", metrics.get("estabelecimentos_sc", 0))
    add("estabelecimentos_ativos_sc", metrics.get("estabelecimentos_ativos_sc", 0))
    add("cnpj_basico_unicos_sc", metrics.get("cnpj_basico_unicos_sc", 0))
    add("empresas_cruzadas_com_sucesso", metrics.get("empresas_cruzadas_com_sucesso", 0))

    checks = con.execute(
        """
        SELECT
            count(*) AS total,
            100.0 * sum(CASE WHEN cnae_principal IS NULL OR cnae_principal = '' THEN 1 ELSE 0 END) / nullif(count(*), 0) AS pct_sem_cnae,
            100.0 * sum(CASE WHEN municipio IS NULL OR municipio = '' THEN 1 ELSE 0 END) / nullif(count(*), 0) AS pct_sem_municipio,
            100.0 * sum(CASE WHEN populacao IS NULL OR pib_per_capita IS NULL THEN 1 ELSE 0 END) / nullif(count(*), 0) AS pct_sem_pib_pop,
            100.0 * sum(CASE WHEN descricao_cnae IS NULL OR descricao_cnae = '' THEN 1 ELSE 0 END) / nullif(count(*), 0) AS pct_cnae_sem_descricao,
            count(*) - count(DISTINCT cnpj_completo) AS duplicidades_cnpj_completo
        FROM gold_empresas_ativas_sc;
        """
    ).fetchone()
    total, pct_sem_cnae, pct_sem_municipio, pct_sem_pib, pct_cnae_sem_desc, dup = checks
    add("total_gold_empresas_ativas_sc", total)
    add("percentual_empresas_sem_cnae", round(pct_sem_cnae or 0, 2), "atencao" if (pct_sem_cnae or 0) > 0 else "ok")
    add("percentual_empresas_sem_municipio", round(pct_sem_municipio or 0, 2), "atencao" if (pct_sem_municipio or 0) > 0 else "ok")
    add("percentual_municipios_sem_match_pib_populacao", round(pct_sem_pib or 0, 2), "atencao" if (pct_sem_pib or 0) > 0 else "ok")
    add("percentual_cnaes_sem_descricao", round(pct_cnae_sem_desc or 0, 2), "atencao" if (pct_cnae_sem_desc or 0) > 0 else "ok")
    add("duplicidade_cnpj_completo", dup, "erro" if dup else "ok")

    porte_rows = con.execute(
        "SELECT coalesce(porte_empresa, 'Sem porte') AS porte, count(*) AS total FROM gold_empresas_ativas_sc GROUP BY 1 ORDER BY 2 DESC;"
    ).fetchall()
    add("distribuicao_porte", json.dumps(dict(porte_rows), ensure_ascii=False))
    add("distribuicao_situacao_cadastral", json.dumps(metrics.get("distribuicao_situacao_cadastral", {}), ensure_ascii=False))
    return result


def write_quality_csv(validations: list[dict[str, object]]) -> None:
    path = OUTPUTS_DIR / "qualidade_dados_sc.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["validacao", "valor", "status", "detalhe"])
        writer.writeheader()
        writer.writerows(validations)


def run_pipeline(raw_paths: list[Path] | None = None, skip_diagnostic: bool = False) -> dict:
    ensure_dirs(BRONZE_DIR, SILVER_DIR, GOLD_DIR, OUTPUTS_DIR, TMP_EXTRACT_DIR)
    paths = raw_paths or default_raw_paths()
    if not skip_diagnostic:
        diagnostic = run_diagnostico(paths)
        if diagnostic.get("bloqueios"):
            raise RuntimeError(
                "Diagnostico bloqueou o pipeline. Veja outputs/diagnostico_ingestao.md. "
                + " | ".join(diagnostic["bloqueios"])
            )
    metrics: dict = {"fontes_descobertas": defaultdict(list)}
    sources, _ignored = discover_receita_sources(paths)
    for source in sources:
        metrics["fontes_descobertas"][source.kind].append(source.label)

    if not list(sources_by_kind(sources, "estabelecimentos")):
        raise FileNotFoundError("Nenhum arquivo de Estabelecimentos foi encontrado em data/raw.")
    if not list(sources_by_kind(sources, "empresas")):
        raise FileNotFoundError("Nenhum arquivo de Empresas foi encontrado em data/raw.")

    cnpjs_sc = process_estabelecimentos(sources, metrics)
    process_empresas(sources, cnpjs_sc, metrics)
    process_dimension(sources, "municipios", MUNICIPIOS_COLUMNS, "municipios.csv", metrics)
    process_dimension(sources, "cnaes", CNAES_COLUMNS, "cnaes.csv", metrics)
    process_dimension(sources, "naturezas", NATUREZAS_COLUMNS, "naturezas.csv", metrics)
    process_dimension(sources, "simples", SIMPLES_COLUMNS, "simples_sc.csv", metrics, cnpjs_sc=cnpjs_sc)
    process_consolidado(sources, metrics, paths)
    build_gold(metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline local de inteligencia de mercado B2B para SC.")
    parser.add_argument("--discover-only", action="store_true", help="Apenas lista as fontes encontradas em data/raw.")
    parser.add_argument("--raw-dir", action="append", type=Path, help="Pasta ou arquivo bruto. Pode repetir.")
    parser.add_argument("--skip-diagnostic", action="store_true", help="Nao recomendado: pula os criterios bloqueantes.")
    args = parser.parse_args()
    raw_paths = args.raw_dir or default_raw_paths()

    if args.discover_only:
        sources, ignored = discover_receita_sources(raw_paths)
        for source in sources:
            print(f"{source.kind}: {source.label}")
        for source in ignored:
            print(f"ignorado: {source.label} ({source.ignored_reason})")
        return

    metrics = run_pipeline(raw_paths, skip_diagnostic=args.skip_diagnostic)
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
