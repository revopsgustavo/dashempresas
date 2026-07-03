# Qualidade dos Dados

As validacoes sao gravadas em `outputs/qualidade_dados_sc.csv` durante o pipeline.

## Validacoes

- Quantidade de registros lidos por arquivo de Estabelecimentos.
- Quantidade de estabelecimentos de SC.
- Quantidade de estabelecimentos ativos de SC.
- Quantidade de `cnpj_basico` unicos em SC.
- Quantidade de empresas cruzadas com sucesso.
- Percentual de empresas sem CNAE.
- Percentual de empresas sem municipio.
- Percentual de registros sem match de PIB/populacao.
- Percentual de CNAEs sem descricao.
- Verificacao de duplicidade de `cnpj_completo`.
- Distribuicao por situacao cadastral.
- Distribuicao por porte.

## Problemas Encontrados

Na execucao real, o diagnostico foi aprovado. A validacao final registrou um alerta: 0,52% dos registros ficaram sem match de PIB/populacao. Isso indica pequena divergencia de padronizacao entre nomes/codigos municipais das bases de Receita e IBGE.

## Impactos Conhecidos

- Falhas de match em municipio reduzem a confiabilidade dos indicadores per capita.
- CNAEs sem descricao mantem codigo, mas reduzem legibilidade do dashboard.
- Duplicidade de CNPJ completo deve ser tratada como erro de qualidade.

## Resultado da Ultima Execucao

- Estabelecimentos lidos: 71.874.448
- Estabelecimentos ativos em SC: 1.533.998
- Municipios distintos em SC: 295
- CNAEs distintos em SC: 1.247
- Match entre estabelecimentos ativos de SC e Empresas: 100%
- Erros de validacao: 0
- Alertas de validacao: 1
