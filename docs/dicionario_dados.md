# Dicionario de Dados

## gold_empresas_ativas_sc

Base analitica de estabelecimentos ativos em Santa Catarina cruzados com dados da empresa e dimensoes.

| Coluna | Origem | Regra |
|---|---|---|
| cnpj_basico | Empresas/Estabelecimentos | Chave de cruzamento |
| cnpj_completo | Estabelecimentos | Concatenacao de basico, ordem e DV |
| razao_social | Empresas | Valor original |
| nome_fantasia | Estabelecimentos | Valor original |
| uf | Estabelecimentos | Filtrado para SC |
| municipio | Municipios | Descricao pelo codigo da Receita |
| codigo_municipio_receita | Estabelecimentos | Codigo original da Receita |
| codigo_municipio_ibge | CSV consolidado | Match por municipio normalizado, quando disponivel |
| cnae_fiscal_principal | Estabelecimentos | CNAE fiscal principal |
| descricao_cnae | CNAEs | Descricao pelo codigo CNAE |
| natureza_juridica | Empresas | Codigo original |
| descricao_natureza_juridica | Naturezas | Descricao pelo codigo |
| porte_empresa | Empresas | Codigo traduzido para texto |
| capital_social | Empresas | Conversao para numero |
| data_inicio_atividade | Estabelecimentos | Conversao de AAAAMMDD para data |
| idade_empresa_anos | Derivado | Diferenca em anos ate a data de processamento |
| opcao_simples | Simples | Quando arquivo existir |
| opcao_mei | Simples | Quando arquivo existir |
| populacao | CSV consolidado | Match por municipio |
| pib_per_capita | CSV consolidado | Match por municipio |

## gold_municipio_cnae_sc

Agregacao por municipio e CNAE.

| Coluna | Regra |
|---|---|
| total_empresas_ativas | Contagem de empresas ativas |
| participacao_cnae_no_municipio | Empresas do CNAE dividido pelo total do municipio |
| empresas_por_10k_habitantes | Empresas do grupo por 10 mil habitantes |
| capital_social_total | Soma do capital social |
| capital_social_mediano | Mediana do capital social |
| idade_media_empresas | Media da idade das empresas |
| idade_mediana_empresas | Mediana da idade das empresas |

## gold_ranking_municipios_sc

Ranking municipal com potencial de oportunidade.

| Coluna | Regra |
|---|---|
| total_empresas_ativas | Contagem de empresas ativas |
| total_cnaes_distintos | Distintos CNAEs principais |
| empresas_por_10k_habitantes | Densidade empresarial |
| score_oportunidade | Media ponderada dos componentes normalizados |
| posicao_ranking | Ordem decrescente do score |

## gold_ranking_cnaes_sc

Ranking de CNAEs por relevancia estadual.

| Coluna | Regra |
|---|---|
| total_empresas_ativas | Contagem de empresas ativas no CNAE |
| total_municipios_com_presenca | Municipios distintos com pelo menos uma empresa |
| capital_social_total | Soma do capital social |
| idade_media_empresas | Media de idade |
| score_relevancia | Combinacao normalizada de volume, presenca e capital |
