from __future__ import annotations

import html
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "gold" / "inteligencia_b2b_sc.duckdb"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

CSV_TABLES = {
    "gold_empresas_ativas_sc": OUTPUTS_DIR / "empresas_ativas_sc.csv",
    "gold_ranking_municipios_sc": OUTPUTS_DIR / "ranking_municipios_sc.csv",
    "gold_ranking_cnaes_sc": OUTPUTS_DIR / "ranking_cnaes_sc.csv",
    "gold_municipio_cnae_sc": OUTPUTS_DIR / "municipio_cnae_sc.csv",
}
METRICS_PATH = OUTPUTS_DIR / "pipeline_metrics.json"


def br_number(value, decimals: int = 0) -> str:
    if value is None:
        return "-"
    try:
        text = f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "-"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def br_money(value) -> str:
    return f"R$ {br_number(value, 2)}"


def br_money_compact(value) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    abs_number = abs(number)
    if abs_number >= 1_000_000_000:
        return f"R$ {br_number(number / 1_000_000_000, 1)} bi"
    if abs_number >= 1_000_000:
        return f"R$ {br_number(number / 1_000_000, 1)} mi"
    if abs_number >= 1_000:
        return f"R$ {br_number(number / 1_000, 1)} mil"
    return br_money(number)


def br_percent(value, decimals: int = 1) -> str:
    if value is None:
        return "-"
    try:
        return f"{br_number(float(value), decimals)}%"
    except (TypeError, ValueError):
        return "-"


def render_metric_card(label: str, value: str, help_text: str | None = None) -> str:
    help_markup = f"<div class='metric-help'>{html.escape(help_text)}</div>" if help_text else ""
    return f"<div class='metric-card'><div class='metric-label'>{html.escape(label)}</div><div class='metric-value'>{html.escape(value)}</div>{help_markup}</div>"


def apply_chart_layout(fig, left_margin: int = 40, bottom_margin: int = 80):
    fig.update_layout(
        margin=dict(l=left_margin, r=24, t=64, b=bottom_margin),
        xaxis=dict(automargin=True),
        yaxis=dict(automargin=True),
        hoverlabel=dict(namelength=-1),
    )
    return fig


def has_final_tables() -> bool:
    return DB_PATH.exists() or all(path.exists() for path in CSV_TABLES.values())


def demo_tables() -> dict[str, pd.DataFrame]:
    empresas = pd.DataFrame(
        [
            {
                "cnpj_basico": "00000001",
                "cnpj_ordem": "0001",
                "cnpj_dv": "01",
                "cnpj_completo": "00000001000101",
                "razao_social": "ALFA SOLUCOES LTDA",
                "nome_fantasia": "ALFA TESTE",
                "situacao_cadastral": "02",
                "data_inicio_atividade": "2018-01-15",
                "idade_empresa_anos": 8,
                "uf": "SC",
                "codigo_municipio_receita": "8105",
                "municipio": "FLORIANOPOLIS",
                "cnae_fiscal_principal": "6201501",
                "cnae_principal": "6201501",
                "descricao_cnae": "DESENVOLVIMENTO DE PROGRAMAS DE COMPUTADOR SOB ENCOMENDA",
                "natureza_juridica": "2062",
                "descricao_natureza_juridica": "SOCIEDADE EMPRESARIA LIMITADA",
                "porte_empresa": "Microempresa",
                "capital_social": 150000.0,
                "opcao_simples": "S",
                "opcao_mei": "N",
                "populacao": 537211,
                "pib_per_capita": 74500.10,
            },
            {
                "cnpj_basico": "00000002",
                "cnpj_ordem": "0001",
                "cnpj_dv": "02",
                "cnpj_completo": "00000002000102",
                "razao_social": "BETA COMERCIO LTDA",
                "nome_fantasia": "BETA TESTE",
                "situacao_cadastral": "02",
                "data_inicio_atividade": "2019-05-20",
                "idade_empresa_anos": 7,
                "uf": "SC",
                "codigo_municipio_receita": "8047",
                "municipio": "JOINVILLE",
                "cnae_fiscal_principal": "4711302",
                "cnae_principal": "4711302",
                "descricao_cnae": "COMERCIO VAREJISTA DE MERCADORIAS EM GERAL",
                "natureza_juridica": "2062",
                "descricao_natureza_juridica": "SOCIEDADE EMPRESARIA LIMITADA",
                "porte_empresa": "Empresa de pequeno porte",
                "capital_social": 90000.0,
                "opcao_simples": "S",
                "opcao_mei": "S",
                "populacao": 616323,
                "pib_per_capita": 68000.30,
            },
        ]
    )
    municipio_cnae = (
        empresas.groupby(["uf", "municipio", "cnae_principal", "descricao_cnae"], dropna=False)
        .agg(
            total_empresas_ativas=("cnpj_completo", "count"),
            capital_social_total=("capital_social", "sum"),
            capital_social_mediano=("capital_social", "median"),
            idade_media_empresas=("idade_empresa_anos", "mean"),
            idade_mediana_empresas=("idade_empresa_anos", "median"),
            populacao=("populacao", "max"),
        )
        .reset_index()
    )
    municipio_cnae["participacao_cnae_no_municipio"] = 1.0
    municipio_cnae["empresas_por_10k_habitantes"] = municipio_cnae["total_empresas_ativas"] * 10000 / municipio_cnae["populacao"]

    ranking_municipios = (
        empresas.groupby("municipio", dropna=False)
        .agg(
            populacao=("populacao", "max"),
            pib_per_capita=("pib_per_capita", "max"),
            total_empresas_ativas=("cnpj_completo", "count"),
            total_cnaes_distintos=("cnae_principal", "nunique"),
            capital_social_total=("capital_social", "sum"),
        )
        .reset_index()
    )
    ranking_municipios["empresas_por_10k_habitantes"] = ranking_municipios["total_empresas_ativas"] * 10000 / ranking_municipios["populacao"]
    ranking_municipios["score_oportunidade"] = [100.0, 82.0]
    ranking_municipios["posicao_ranking"] = [1, 2]

    ranking_cnaes = (
        empresas.groupby(["cnae_principal", "descricao_cnae"], dropna=False)
        .agg(
            total_empresas_ativas=("cnpj_completo", "count"),
            total_municipios_com_presenca=("municipio", "nunique"),
            capital_social_total=("capital_social", "sum"),
            idade_media_empresas=("idade_empresa_anos", "mean"),
        )
        .reset_index()
    )
    ranking_cnaes["score_relevancia"] = [100.0, 80.0]

    return {
        "gold_empresas_ativas_sc": empresas,
        "gold_ranking_municipios_sc": ranking_municipios,
        "gold_ranking_cnaes_sc": ranking_cnaes,
        "gold_municipio_cnae_sc": municipio_cnae,
    }


@st.cache_data(show_spinner=False)
def load_table(table: str):
    if DB_PATH.exists():
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            return con.execute(f"SELECT * FROM {table}").fetchdf()
    csv_path = CSV_TABLES[table]
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return demo_tables()[table]


st.set_page_config(page_title="Inteligencia B2B SC", layout="wide")
st.markdown(
    """
    <style>
    div.block-container {
        max-width: 100%;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 0.75rem;
        margin: 1rem 0 1.35rem;
    }

    .metric-card {
        min-width: 0;
        min-height: 112px;
        border: 1px solid rgba(49, 51, 63, 0.16);
        border-radius: 8px;
        background: #ffffff;
        padding: 0.9rem 1rem;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        overflow: visible;
    }

    .metric-label {
        color: rgba(49, 51, 63, 0.72);
        font-size: 0.86rem;
        font-weight: 600;
        line-height: 1.25;
        white-space: normal;
        overflow-wrap: anywhere;
    }

    .metric-value {
        color: rgb(38, 39, 48);
        font-size: clamp(1.35rem, 2.2vw, 2rem);
        font-weight: 750;
        line-height: 1.08;
        letter-spacing: 0;
        white-space: normal;
        overflow: visible;
        overflow-wrap: anywhere;
        word-break: normal;
    }

    .metric-help {
        color: rgba(49, 51, 63, 0.62);
        font-size: 0.74rem;
        line-height: 1.2;
        margin-top: 0.35rem;
        white-space: normal;
        overflow-wrap: anywhere;
    }

    @media (max-width: 700px) {
        div.block-container {
            padding-left: 0.85rem;
            padding-right: 0.85rem;
        }

        .metric-grid {
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.6rem;
        }

        .metric-card {
            min-height: 104px;
            padding: 0.75rem;
        }

        .metric-value {
            font-size: 1.32rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Inteligencia de Mercado B2B - Santa Catarina")
st.caption("Dashboard atualizado - carrega somente data/gold ou outputs, sem depender de data/raw na visualizacao.")

if METRICS_PATH.exists():
    metrics_text = METRICS_PATH.read_text(encoding="utf-8", errors="ignore").lower()
    if "sintetico" in metrics_text:
        st.warning("Base carregada gerada a partir da amostra sintetica de teste. Substitua `data/raw` pelos arquivos reais e rode o pipeline para uso analitico.")

if not has_final_tables():
    st.warning(
        "Base final completa nao esta disponivel neste ambiente. "
        "Exibindo uma amostra sintetica pequena para demonstracao do dashboard. "
        "Para analise real, gere `data/gold` localmente com o pipeline."
    )
elif not DB_PATH.exists():
    st.info("Carregando CSVs finais de `outputs`, sem acesso aos arquivos brutos.")

empresas = load_table("gold_empresas_ativas_sc")
ranking_municipios = load_table("gold_ranking_municipios_sc")
ranking_cnaes = load_table("gold_ranking_cnaes_sc")
municipio_cnae = load_table("gold_municipio_cnae_sc")

with st.sidebar:
    st.header("Filtros")
    municipios = sorted(empresas["municipio"].dropna().unique().tolist())
    cnaes_labels = (
        empresas[["cnae_principal", "descricao_cnae"]]
        .dropna(subset=["cnae_principal"])
        .drop_duplicates()
        .assign(label=lambda df: df["cnae_principal"].astype(str) + " - " + df["descricao_cnae"].fillna("Sem descricao"))
        ["label"]
        .sort_values()
        .tolist()
    )
    portes = sorted(empresas["porte_empresa"].dropna().unique().tolist())
    naturezas = sorted(empresas["descricao_natureza_juridica"].dropna().unique().tolist())

    filtro_municipio = st.multiselect("Municipio", municipios)
    filtro_cnae = st.multiselect("CNAE", cnaes_labels)
    filtro_porte = st.multiselect("Porte da empresa", portes)
    filtro_natureza = st.multiselect("Natureza juridica", naturezas)

    if "opcao_simples" in empresas.columns and empresas["opcao_simples"].notna().any():
        filtro_simples = st.multiselect("Opcao pelo Simples", sorted(empresas["opcao_simples"].dropna().unique().tolist()))
    else:
        filtro_simples = []

    if "opcao_mei" in empresas.columns and empresas["opcao_mei"].notna().any():
        filtro_mei = st.multiselect("MEI", sorted(empresas["opcao_mei"].dropna().unique().tolist()))
    else:
        filtro_mei = []

    idade_max = int(empresas["idade_empresa_anos"].dropna().max() or 0)
    idade_range = st.slider("Faixa de idade da empresa", 0, max(idade_max, 1), (0, max(idade_max, 1)))

    capital_max = float(empresas["capital_social"].dropna().max() or 0)
    capital_range = st.slider("Faixa de capital social", 0.0, max(capital_max, 1.0), (0.0, max(capital_max, 1.0)))

filtered = empresas.copy()
if filtro_municipio:
    filtered = filtered[filtered["municipio"].isin(filtro_municipio)]
if filtro_cnae:
    codigos = [item.split(" - ")[0] for item in filtro_cnae]
    filtered = filtered[filtered["cnae_principal"].astype(str).isin(codigos)]
if filtro_porte:
    filtered = filtered[filtered["porte_empresa"].isin(filtro_porte)]
if filtro_natureza:
    filtered = filtered[filtered["descricao_natureza_juridica"].isin(filtro_natureza)]
if filtro_simples:
    filtered = filtered[filtered["opcao_simples"].isin(filtro_simples)]
if filtro_mei:
    filtered = filtered[filtered["opcao_mei"].isin(filtro_mei)]
filtered = filtered[
    filtered["idade_empresa_anos"].fillna(0).between(idade_range[0], idade_range[1])
    & filtered["capital_social"].fillna(0).between(capital_range[0], capital_range[1])
]

capital_total = filtered["capital_social"].fillna(0).sum()
metric_cards = [
    render_metric_card("Empresas ativas", br_number(len(filtered))),
    render_metric_card("Municipios", br_number(filtered["municipio"].nunique())),
    render_metric_card("CNAEs", br_number(filtered["cnae_principal"].nunique())),
    render_metric_card("PIB per capita medio", br_money(filtered["pib_per_capita"].dropna().mean())),
    render_metric_card("Capital social total", br_money_compact(capital_total), help_text=f"Valor completo: {br_money(capital_total)}"),
    render_metric_card("Idade mediana", br_number(filtered["idade_empresa_anos"].dropna().median(), 1)),
]
st.markdown(f"<div class='metric-grid'>{''.join(metric_cards)}</div>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["Municipios", "CNAEs", "Distribuicoes", "Empresas"])

with tab1:
    base_mun = (
        filtered.groupby("municipio", dropna=False)
        .agg(
            total_empresas_ativas=("cnpj_completo", "count"),
            capital_social_total=("capital_social", "sum"),
            populacao=("populacao", "max"),
            pib_per_capita=("pib_per_capita", "max"),
        )
        .reset_index()
        .sort_values("total_empresas_ativas", ascending=False)
    )
    fig_mun = px.bar(base_mun.head(30), x="municipio", y="total_empresas_ativas", title="Empresas por municipio")
    fig_mun.update_xaxes(tickangle=-35)
    st.plotly_chart(apply_chart_layout(fig_mun, bottom_margin=120), use_container_width=True)
    st.dataframe(
        ranking_municipios.rename(
            columns={
                "municipio": "Municipio",
                "populacao": "Populacao",
                "pib_per_capita": "PIB per capita",
                "total_empresas_ativas": "Empresas ativas",
                "total_cnaes_distintos": "CNAEs distintos",
                "empresas_por_10k_habitantes": "Empresas por 10 mil hab.",
                "capital_social_total": "Capital social total",
                "score_oportunidade": "Score oportunidade",
                "posicao_ranking": "Posicao",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    base_cnae = (
        filtered.groupby(["cnae_principal", "descricao_cnae"], dropna=False)
        .agg(total_empresas_ativas=("cnpj_completo", "count"), capital_social_total=("capital_social", "sum"))
        .reset_index()
        .sort_values("total_empresas_ativas", ascending=False)
    )
    base_cnae["cnae"] = base_cnae["cnae_principal"].astype(str) + " - " + base_cnae["descricao_cnae"].fillna("Sem descricao")
    fig_cnae = px.bar(base_cnae.head(30), x="total_empresas_ativas", y="cnae", orientation="h", title="Empresas por CNAE")
    fig_cnae.update_layout(height=780)
    st.plotly_chart(apply_chart_layout(fig_cnae, left_margin=220, bottom_margin=56), use_container_width=True)
    st.dataframe(
        ranking_cnaes.rename(
            columns={
                "cnae_principal": "CNAE principal",
                "descricao_cnae": "Descricao CNAE",
                "total_empresas_ativas": "Empresas ativas",
                "total_municipios_com_presenca": "Municipios com presenca",
                "capital_social_total": "Capital social total",
                "idade_media_empresas": "Idade media",
                "score_relevancia": "Score relevancia",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    col1, col2 = st.columns(2)
    with col1:
        porte = filtered["porte_empresa"].fillna("Sem porte").value_counts().reset_index()
        porte.columns = ["porte_empresa", "total"]
        fig_porte = px.pie(porte, names="porte_empresa", values="total", title="Distribuicao por porte")
        st.plotly_chart(apply_chart_layout(fig_porte, bottom_margin=40), use_container_width=True)
    with col2:
        natureza = filtered["descricao_natureza_juridica"].fillna("Sem descricao").value_counts().head(20).reset_index()
        natureza.columns = ["natureza_juridica", "total"]
        fig_natureza = px.bar(natureza, x="total", y="natureza_juridica", orientation="h", title="Distribuicao por natureza juridica")
        fig_natureza.update_layout(height=620)
        st.plotly_chart(apply_chart_layout(fig_natureza, left_margin=180, bottom_margin=50), use_container_width=True)
    pivot = municipio_cnae.pivot_table(index="municipio", columns="descricao_cnae", values="total_empresas_ativas", aggfunc="sum", fill_value=0)
    st.dataframe(pivot, use_container_width=True)

with tab4:
    busca = st.text_input("Buscar por razao social, nome fantasia, municipio ou CNAE")
    table = filtered.copy()
    if busca:
        text = busca.upper()
        mask = (
            table["razao_social"].fillna("").str.upper().str.contains(text, regex=False)
            | table["nome_fantasia"].fillna("").str.upper().str.contains(text, regex=False)
            | table["municipio"].fillna("").str.upper().str.contains(text, regex=False)
            | table["descricao_cnae"].fillna("").str.upper().str.contains(text, regex=False)
            | table["cnae_principal"].fillna("").astype(str).str.contains(text, regex=False)
        )
        table = table[mask]

    friendly = table.rename(
        columns={
            "cnpj_completo": "CNPJ",
            "razao_social": "Razao social",
            "nome_fantasia": "Nome fantasia",
            "municipio": "Municipio",
            "cnae_principal": "CNAE principal",
            "descricao_cnae": "Descricao CNAE",
            "porte_empresa": "Porte",
            "capital_social": "Capital social",
            "idade_empresa_anos": "Idade da empresa",
        }
    )
    st.dataframe(friendly, use_container_width=True, hide_index=True)
    st.download_button(
        "Exportar CSV",
        data=friendly.to_csv(index=False).encode("utf-8"),
        file_name="empresas_ativas_sc_filtradas.csv",
        mime="text/csv",
    )
