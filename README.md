# Inteligencia de Mercado B2B - Santa Catarina

MVP local para inteligencia de mercado B2B em Santa Catarina usando arquivos publicos ja baixados da Receita Federal e um CSV consolidado com dados de PIB per capita e populacao.

O projeto nao baixa dados da internet. Coloque os arquivos brutos em `data/raw` e rode o pipeline local.

## Fontes de Dados

- Receita Federal: Empresas, Estabelecimentos, Municipios, CNAEs, Naturezas juridicas e Simples Nacional, quando disponivel.
- IBGE/consolidado local: CSV com municipio, populacao, PIB per capita e, se existir, CNAE.

## Estrutura

- `data/raw`: arquivos originais, sem alteracao.
- `data/bronze`: CSVs padronizados e filtrados quando necessario.
- `data/silver`: Parquets intermediarios filtrados para SC.
- `data/gold`: DuckDB e Parquets finais.
- `src`: pipeline e validacoes.
- `sql`: consultas de referencia.
- `dashboard`: app Streamlit.
- `outputs`: CSVs finais e relatorios de qualidade.
- `docs`: dicionario e qualidade dos dados.

## Arquivos Esperados

O pipeline descobre arquivos automaticamente em `data/raw`, inclusive dentro de ZIPs. Os nomes ou caminhos devem indicar o tipo de arquivo, por exemplo:

- `estabelecimentos`, `estab`
- `empresas`, `empre`
- `municipios`, `munic`
- `cnaes`, `cnae`
- `naturezas`, `natju`
- `simples`
- `pib`, `populacao`, `ibge` ou `consolidado`

## Como Rodar

Instalar dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Rodar diagnostico de ingestao:

```powershell
python -m src.diagnostico_ingestao --raw-dir "C:\Users\Gustavo Lazzaroto\Documents\Ação Santa Catarina"
```

O pipeline so deve seguir se `outputs/diagnostico_ingestao.md` indicar `APROVADO`.

Listar arquivos reconhecidos:

```powershell
python -m src.pipeline --discover-only --raw-dir "C:\Users\Gustavo Lazzaroto\Documents\Ação Santa Catarina"
```

Rodar pipeline:

```powershell
python -m src.pipeline --raw-dir "C:\Users\Gustavo Lazzaroto\Documents\Ação Santa Catarina"
```

Rodar validacoes:

```powershell
python -m src.validate
```

Abrir dashboard:

```powershell
streamlit run dashboard/app.py
```

## Tabelas Finais

- `gold_empresas_ativas_sc`
- `gold_municipio_cnae_sc`
- `gold_ranking_municipios_sc`
- `gold_ranking_cnaes_sc`

Tambem sao gerados CSVs em `outputs`.

## Tabelas Silver

- `data/silver/silver_estabelecimentos_sc_ativos.parquet`: estabelecimentos da Receita com `UF = SC` e `situacao_cadastral` ativa.
- `data/silver/silver_empresas_sc.parquet`: empresas da Receita cujo `cnpj_basico` aparece nos estabelecimentos ativos de SC.

## Indicadores

- Total de empresas ativas em SC
- Total de municipios analisados
- Total de CNAEs distintos
- Empresas por municipio
- Empresas por CNAE
- Empresas por 10 mil habitantes
- Participacao do CNAE dentro do municipio
- Idade media e mediana das empresas
- Capital social total, medio e mediano
- Ranking de municipios por potencial
- Ranking de CNAEs por relevancia

## Score de Oportunidade

O ranking municipal usa uma formula simples, de 0 a 100. Antes da combinacao, cada componente e normalizado por min-max para reduzir dominancia de escala.

Pesos iniciais:

- Populacao: 20%
- PIB per capita: 20%
- Total de empresas ativas: 20%
- Empresas por 10 mil habitantes: 15%
- Diversidade de CNAEs: 15%
- Capital social total: 10%

Formula:

```text
score = 100 * (
  0.20 * n_populacao +
  0.20 * n_pib_per_capita +
  0.20 * n_total_empresas +
  0.15 * n_empresas_por_10k +
  0.15 * n_diversidade_cnaes +
  0.10 * n_capital_social
)
```

## Limitacoes

- O MVP depende dos arquivos locais disponiveis e dos nomes permitirem classificacao automatica.
- O match com PIB/populacao depende de municipio padronizado e/ou codigo IBGE no CSV consolidado.
- CNAEs secundarios nao sao explodidos nesta primeira versao.
- O score e exploratorio e deve ser calibrado com regras comerciais.
- Arquivos brutos gigantes ficam fora do git. O pipeline le a pasta externa informada em `--raw-dir` e grava somente camadas processadas locais.

## Diagnostico Real Executado

Ultima execucao aprovada:

- Estabelecimentos lidos: 71.874.448
- Estabelecimentos em SC: 3.495.873
- Estabelecimentos ativos em SC: 1.533.998
- CNPJ basico unicos ativos em SC: 1.482.280
- Municipios distintos em SC: 295
- CNAEs distintos em SC: 1.247
- Match com Empresas: 100%

## Proximos Passos

- Adicionar georreferenciamento por municipio.
- Explodir CNAEs secundarios para analises complementares.
- Criar pesos de score por segmento-alvo.
- Adicionar testes com amostras sinteticas pequenas.
