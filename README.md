# Radar Campinas

Site que mostra, só com dados oficiais da Câmara Municipal de Campinas-SP, o que cada vereador faz:
presença nas reuniões, propostas apresentadas (agrupadas em linguagem simples), votos registrados por nome
e o que foi pedido para cada bairro e rua.

Inspirado no [Radar de Hortolândia](https://radarptlandia.org).

## Como funciona

1. **Coleta** (`coletor/coletar.py`): toda madrugada, um robô do GitHub Actions baixa os dados abertos
   do [SAPL da Câmara](https://sapl.campinas.sp.leg.br/api/) e grava em `data/raw/`.
   Se a coleta vier incompleta ou estranha, nada é gravado e o site continua com a última versão boa.
2. **Geração** (`gerador/gerar.py`): transforma os dados brutos nos arquivos do site. Todas as regras
   (presença, grupos de propostas, pedidos repetidos) ficam nesse arquivo e valem igualmente para todos.
3. **Publicação**: o site estático (`site/`) é publicado no GitHub Pages.

O resumo da última coleta fica em `data/ultima_coleta.json`.

## Rodar localmente

```bash
python3 gerador/gerar.py           # usa os dados já coletados em data/raw
cd site && python3 -m http.server  # abre em http://localhost:8000
```

## Cuidados

- Só dado oficial. Mesma regra para todos os vereadores. O que é estimativa está escrito como estimativa.
- Só contato público de gabinete.
- Dado ausente não é falta: reuniões sem lista de presença não contam, e sequências longas fora da lista
  (provável licença ou afastamento) são separadas e explicadas.
- Achou um erro? [Abra uma issue](https://github.com/ehosimao/radar-campinas/issues/new).
