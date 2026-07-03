-- Referencia das tabelas finais criadas por src/pipeline.py.
-- O pipeline usa DuckDB para materializar estas tabelas em data/gold/inteligencia_b2b_sc.duckdb.

SELECT * FROM gold_empresas_ativas_sc;
SELECT * FROM gold_municipio_cnae_sc;
SELECT * FROM gold_ranking_municipios_sc;
SELECT * FROM gold_ranking_cnaes_sc;
