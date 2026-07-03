from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
TMP_EXTRACT_DIR = DATA_DIR / "tmp_extract"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"

DB_PATH = GOLD_DIR / "inteligencia_b2b_sc.duckdb"

ENCODINGS = ("latin1", "cp1252", "utf-8-sig", "utf-8")
RECEITA_DELIMITER = ";"
UF_TARGET = "SC"
SITUACAO_ATIVA = "02"

ESTABELECIMENTOS_COLUMNS = [
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "identificador_matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "nome_cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "cnae_fiscal_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd_1",
    "telefone_1",
    "ddd_2",
    "telefone_2",
    "ddd_fax",
    "fax",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
]

EMPRESAS_COLUMNS = [
    "cnpj_basico",
    "razao_social",
    "natureza_juridica",
    "qualificacao_responsavel",
    "capital_social",
    "porte_empresa",
    "ente_federativo_responsavel",
]

CNAES_COLUMNS = ["cnae", "descricao_cnae"]
MUNICIPIOS_COLUMNS = ["codigo_municipio_receita", "nome_municipio_receita"]
NATUREZAS_COLUMNS = ["natureza_juridica", "descricao_natureza_juridica"]
MOTIVOS_COLUMNS = ["motivo_situacao_cadastral", "descricao_motivo_situacao_cadastral"]
SIMPLES_COLUMNS = [
    "cnpj_basico",
    "opcao_simples",
    "data_opcao_simples",
    "data_exclusao_simples",
    "opcao_mei",
    "data_opcao_mei",
    "data_exclusao_mei",
]

PORTE_LABELS = {
    "00": "Nao informado",
    "01": "Microempresa",
    "03": "Empresa de pequeno porte",
    "05": "Demais",
}
