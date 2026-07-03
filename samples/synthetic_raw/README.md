# Amostra Sintetica

Arquivos pequenos e totalmente sinteticos para testar o pipeline. Nao representam dados reais da Receita Federal, IBGE ou empresas existentes.

Para testar:

```powershell
Copy-Item samples\synthetic_raw\*.csv data\raw\
python -m src.pipeline
```
