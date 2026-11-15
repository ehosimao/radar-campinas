#!/usr/bin/env python3
"""Coleta os dados abertos do SAPL da Câmara Municipal de Campinas.

Baixa os dados brutos da API pública (https://sapl.campinas.sp.leg.br/api/)
e grava em data/raw/*.json.gz. Não interpreta nada: só baixa.

Coleta devagar, identificando-se, para não pesar no servidor da Câmara.
Se algo vier vazio ou estranho, sai com erro e nada é gravado.
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("SAPL_BASE", "https://sapl.campinas.sp.leg.br/api")
DESDE = os.environ.get("DESDE", "2025-01-01")  # início da 19ª legislatura
ANOS = [int(a) for a in os.environ.get("ANOS", "2025,2026").split(",")]
PAUSA = float(os.environ.get("PAUSA", "0.4"))
UA = ("RadarCampinas/0.1 (projeto cidadao sem fins lucrativos; "
      "https://github.com/Ehosimao/radar-campinas)")
SAIDA = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
TMP = SAIDA + ".tmp"

resumo = {"base": BASE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "tabelas": {}, "avisos": []}
_n_req = 0


def get(url, tentativas=5):
    global _n_req
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                _n_req += 1
                time.sleep(PAUSA)
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            espera = 5 * (i + 1) * (3 if e.code == 429 else 1)
            print(f"  HTTP {e.code} em {url}; nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
        except Exception as e:  # noqa: BLE001
            espera = 5 * (i + 1)
            print(f"  erro {e!r} em {url}; nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
    raise RuntimeError(f"falhou depois de {tentativas} tentativas: {url}")


def listar(caminho, **params):
    """Percorre todas as páginas de um endpoint do SAPL."""
    params = {k: v for k, v in params.items() if v is not None}
    params.setdefault("page_size", 100)
    pagina, itens, total = 1, [], None
    while True:
        params["page"] = pagina
        url = f"{BASE}/{caminho.strip('/')}/?{urllib.parse.urlencode(params)}"
        dados = get(url)
        if dados is None:
            break
        if isinstance(dados, list):
            itens.extend(dados)
            break
        itens.extend(dados.get("results", []))
        pag = dados.get("pagination") or {}
        total = pag.get("total_entries", dados.get("count", total))
        tem_proxima = pag.get("next_page") if pag else dados.get("next")
        if not tem_proxima:
            break
        pagina += 1
    return itens, total


def gravar(nome, itens, total=None, filtro=None):
    os.makedirs(TMP, exist_ok=True)
    with gzip.open(os.path.join(TMP, f"{nome}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, sort_keys=True)
    resumo["tabelas"][nome] = {
        "registros": len(itens),
        "total_informado": total,
        "filtro": filtro,
        "campos": sorted(itens[0].keys()) if itens and isinstance(itens[0], dict) else [],
        "exemplo": itens[0] if itens else None,
    }
    print(f"{nome}: {len(itens)} registros", flush=True)


def tabela(nome, caminho, **params):
    itens, total = listar(caminho, **params)
    gravar(nome, itens, total, params or None)
    return itens


def por_chave(nome, caminho, campo, valores, **extra):
    """Busca um endpoint filtrando por um valor de cada vez e confere se o filtro funcionou."""
    todos, ignorado = [], False
    for v in valores:
        itens, _ = listar(caminho, **{campo: v}, **extra)
        if itens and campo in itens[0] and str(itens[0][campo]) != str(v):
            ignorado = True
        todos.extend(itens)
    if ignorado:
        resumo["avisos"].append(f"{nome}: o filtro '{campo}' parece ter sido ignorado pela API")
    # remove duplicatas por id
    vistos, unicos = set(), []
    for i in todos:
        chave = i.get("id") if isinstance(i, dict) else json.dumps(i)
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(i)
    gravar(nome, unicos, None, {campo: f"{len(valores)} valores"})
    return unicos


def main():
    # --- Vereadores ---
    legislaturas = tabela("legislaturas", "parlamentares/legislatura")
    tabela("parlamentares", "parlamentares/parlamentar")
    tabela("mandatos", "parlamentares/mandato")
    tabela("filiacoes", "parlamentares/filiacao")
    tabela("partidos", "parlamentares/partido")
    autores = tabela("autores", "base/autor")
    tabela("tipos_autor", "base/tipoautor")

    # --- Sessões (reuniões) ---
    tabela("tipos_sessao", "sessao/tiposessaoplenaria")
    sessoes = tabela("sessoes", "sessao/sessaoplenaria")
    recentes = [s["id"] for s in sessoes if str(s.get("data_inicio") or "") >= DESDE]
    print(f"sessões desde {DESDE}: {len(recentes)}", flush=True)
    por_chave("presencas", "sessao/sessaoplenariapresenca", "sessao_plenaria", recentes)
    por_chave("presencas_ordemdia", "sessao/presencaordemdia", "sessao_plenaria", recentes)
    por_chave("justificativas_ausencia", "sessao/justificativaausencia", "sessao_plenaria", recentes)
    por_chave("ordemdia", "sessao/ordemdia", "sessao_plenaria", recentes)
    por_chave("expediente_materia", "sessao/expedientemateria", "sessao_plenaria", recentes)
    por_chave("registros_votacao", "sessao/registrovotacao", "ordem__sessao_plenaria", recentes)

    # --- Propostas ---
    tabela("tipos_materia", "materia/tipomaterialegislativa")
    materias = []
    for ano in ANOS:
        itens, total = listar("materia/materialegislativa", ano=ano)
        errados = [m for m in itens if str(m.get("ano")) != str(ano)]
        if errados:
            resumo["avisos"].append(f"materias {ano}: {len(errados)} itens de outro ano (filtro ignorado?)")
            itens = [m for m in itens if str(m.get("ano")) == str(ano)]
        print(f"matérias {ano}: {len(itens)} (API informou {total})", flush=True)
        materias.extend(itens)
    gravar("materias", materias, None, {"ano": ANOS})

    # autoria: só dos autores que são parlamentares
    ids_parl_autor = [a["id"] for a in autores
                      if a.get("object_id") and "parlamentar" in json.dumps(a, ensure_ascii=False).lower()]
    if not ids_parl_autor:
        resumo["avisos"].append("não identifiquei autores-parlamentar; baixando autoria de todos")
        ids_parl_autor = [a["id"] for a in autores]
    por_chave("autorias", "materia/autoria", "autor", ids_parl_autor)

    # votos nominais, por vereador
    parl_ids = sorted({m["parlamentar"] for m in json.load(gzip.open(os.path.join(TMP, "mandatos.json.gz"), "rt"))
                       if m.get("legislatura") == max((l["id"] for l in legislaturas), default=None)})
    por_chave("votos_nominais", "sessao/votoparlamentar", "parlamentar", parl_ids)

    # --- Conferência mínima antes de publicar ---
    t = resumo["tabelas"]
    problemas = []
    if t["parlamentares"]["registros"] < 20:
        problemas.append("poucos parlamentares")
    if len(recentes) < 10:
        problemas.append("poucas sessões recentes")
    if t["presencas"]["registros"] < 100:
        problemas.append("poucas presenças")
    if t["materias"]["registros"] < 500:
        problemas.append("poucas matérias")
    resumo["fim"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    resumo["requisicoes"] = _n_req
    resumo["problemas"] = problemas
    for destino in (os.path.join(TMP, "_resumo.json"),
                    os.path.join(SAIDA, "..", "ultima_coleta.json")):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=1, default=str)
    if problemas:
        print("COLETA SUSPEITA, NÃO VOU PUBLICAR:", problemas, file=sys.stderr)
        sys.exit(1)

    # troca a pasta antiga pela nova só no final, de uma vez
    import shutil
    if os.path.isdir(SAIDA):
        shutil.rmtree(SAIDA)
    os.rename(TMP, SAIDA)
    print(f"OK: {_n_req} requisições", flush=True)


if __name__ == "__main__":
    main()
