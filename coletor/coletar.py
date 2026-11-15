#!/usr/bin/env python3
"""Coleta os dados abertos do SAPL da Câmara Municipal de Campinas.

Baixa os dados brutos da API pública (https://sapl.campinas.sp.leg.br/api/)
e grava em data/raw/*.json.gz. Não interpreta nada: só baixa.

Coleta devagar, identificando-se, para não pesar no servidor da Câmara.
Se algo vier vazio ou estranho, sai com erro e a versão anterior é mantida.
"""
import gzip
import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# O servidor da Câmara anuncia IPv6, mas a conexão por IPv6 trava ~60 s.
# Forçamos IPv4.
_orig_gai = socket.getaddrinfo


def _so_ipv4(host, port, family=0, *a, **kw):
    return _orig_gai(host, port, socket.AF_INET, *a, **kw)


socket.getaddrinfo = _so_ipv4

BASE = os.environ.get("SAPL_BASE", "https://sapl.campinas.sp.leg.br/api")
DESDE = os.environ.get("DESDE", "2025-01-01")  # início da 19ª legislatura
ANOS = [int(a) for a in os.environ.get("ANOS", "2025,2026").split(",")]
PAUSA = float(os.environ.get("PAUSA", "0.3"))
UA = ("RadarCampinas/0.2 (projeto cidadao sem fins lucrativos; "
      "https://github.com/ehosimao/radar-campinas)")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
SAIDA = os.path.join(RAIZ, "raw")
TMP = SAIDA + ".tmp"

resumo = {"base": BASE, "desde": DESDE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"),
          "tabelas": {}, "avisos": []}
_n_req = 0
_t_req = 0.0


def get(url, tentativas=5):
    global _n_req, _t_req
    for i in range(tentativas):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                dados = json.load(r)
            _n_req += 1
            _t_req += time.time() - t0
            time.sleep(PAUSA)
            return dados
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            espera = 5 * (i + 1) * (4 if e.code == 429 else 1)
            print(f"  HTTP {e.code} em {url}; nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
        except Exception as e:  # noqa: BLE001
            espera = 5 * (i + 1)
            print(f"  erro {e!r} em {url}; nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
    raise RuntimeError(f"falhou depois de {tentativas} tentativas: {url}")


def url_de(caminho, params):
    return f"{BASE}/{caminho.strip('/')}/?{urllib.parse.urlencode(params)}"


def total_de(caminho, **params):
    d = get(url_de(caminho, dict(params, page_size=1)))
    if not isinstance(d, dict):
        return None
    return (d.get("pagination") or {}).get("total_entries", d.get("count"))


def listar(caminho, rotulo=None, **params):
    """Percorre todas as páginas de um endpoint do SAPL."""
    params = {k: v for k, v in params.items() if v is not None}
    params["page_size"] = 100
    pagina, itens, total = 1, [], None
    t0 = time.time()
    while True:
        params["page"] = pagina
        dados = get(url_de(caminho, params))
        if dados is None:
            break
        if isinstance(dados, list):
            itens.extend(dados)
            break
        itens.extend(dados.get("results", []))
        pag = dados.get("pagination") or {}
        total = pag.get("total_entries", dados.get("count", total))
        if rotulo and pagina % 20 == 0:
            print(f"  {rotulo}: página {pagina}/{pag.get('total_pages', '?')} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        if not (pag.get("next_page") if pag else dados.get("next")):
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
    print(f"{nome}: {len(itens)} registros  [{_n_req} req, média {(_t_req / max(_n_req, 1)):.1f}s]",
          flush=True)


def tabela(nome, caminho, **params):
    itens, total = listar(caminho, rotulo=nome, **params)
    gravar(nome, itens, total, params or None)
    return itens


def filtro_funciona(caminho, campo, valor):
    """Confere se a API respeita o filtro (o total filtrado tem de ser menor que o total geral)."""
    geral = total_de(caminho)
    filtrado = total_de(caminho, **{campo: valor})
    ok = geral is not None and filtrado is not None and filtrado < geral
    print(f"  filtro {caminho}?{campo}={valor}: {filtrado} de {geral} -> {'ok' if ok else 'IGNORADO'}",
          flush=True)
    return ok, geral


def por_chave(nome, caminho, campo, valores, limite_tabela_inteira=40000):
    """Busca um endpoint filtrando por um valor de cada vez.

    Se a API ignorar o filtro, baixa a tabela inteira uma vez (se não for gigante)
    e filtra aqui.
    """
    valores = list(valores)
    if not valores:
        gravar(nome, [], None, {campo: 0})
        return []
    ok, geral = filtro_funciona(caminho, campo, valores[0])
    if not ok:
        if geral and geral <= limite_tabela_inteira:
            resumo["avisos"].append(f"{nome}: filtro '{campo}' ignorado; baixei a tabela inteira")
            itens, total = listar(caminho, rotulo=nome)
            alvo = {str(v) for v in valores}
            itens = [i for i in itens if str(i.get(campo)) in alvo]
            gravar(nome, itens, total, {campo: "filtrado localmente"})
            return itens
        resumo["avisos"].append(f"{nome}: filtro '{campo}' ignorado e tabela grande demais ({geral}); pulei")
        gravar(nome, [], geral, {campo: "PULADO"})
        return []
    todos = []
    for n, v in enumerate(valores, 1):
        itens, _ = listar(caminho, **{campo: v})
        todos.extend(itens)
        if n % 25 == 0:
            print(f"  {nome}: {n}/{len(valores)}", flush=True)
    vistos, unicos = set(), []
    for i in todos:
        chave = i.get("id")
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(i)
    gravar(nome, unicos, None, {campo: f"{len(valores)} valores"})
    return unicos


def main():
    # --- Vereadores ---
    legislaturas = tabela("legislaturas", "parlamentares/legislatura")
    tabela("parlamentares", "parlamentares/parlamentar")
    mandatos = tabela("mandatos", "parlamentares/mandato")
    tabela("filiacoes", "parlamentares/filiacao")
    tabela("partidos", "parlamentares/partido")
    autores = tabela("autores", "base/autor")
    tabela("tipos_autor", "base/tipoautor")
    tabela("tipos_materia", "materia/tipomaterialegislativa")
    tabela("tipos_sessao", "sessao/tiposessaoplenaria")

    leg_atual = max(legislaturas, key=lambda l: str(l.get("data_inicio") or ""))
    resumo["legislatura_atual"] = leg_atual
    parl_ids = sorted({m["parlamentar"] for m in mandatos if m.get("legislatura") == leg_atual["id"]})
    print(f"legislatura atual: {leg_atual.get('numero')} ({len(parl_ids)} parlamentares com mandato)", flush=True)

    # --- Reuniões ---
    sessoes = tabela("sessoes", "sessao/sessaoplenaria")
    recentes = sorted(s["id"] for s in sessoes if str(s.get("data_inicio") or "") >= DESDE)
    print(f"reuniões desde {DESDE}: {len(recentes)}", flush=True)
    por_chave("presencas", "sessao/sessaoplenariapresenca", "sessao_plenaria", recentes)
    por_chave("presencas_ordemdia", "sessao/presencaordemdia", "sessao_plenaria", recentes)
    por_chave("justificativas_ausencia", "sessao/justificativaausencia", "sessao_plenaria", recentes)
    ordem = por_chave("ordemdia", "sessao/ordemdia", "sessao_plenaria", recentes)
    expediente = por_chave("expediente_materia", "sessao/expedientemateria", "sessao_plenaria", recentes)

    # Votações: o filtro por sessão não existe; a tabela tem ~28 mil linhas, baixamos inteira.
    ids_ordem = {o["id"] for o in ordem}
    ids_exp = {e["id"] for e in expediente}
    regs, total = listar("sessao/registrovotacao", rotulo="registros_votacao")
    regs = [r for r in regs if r.get("ordem") in ids_ordem or r.get("expediente") in ids_exp]
    gravar("registros_votacao", regs, total, {"local": "ordem/expediente desde " + DESDE})

    # Votos nominais por vereador
    votos = por_chave("votos_nominais", "sessao/votoparlamentar", "parlamentar", parl_ids)
    ids_votacao = {r["id"] for r in regs}
    resumo["votos_nominais_recentes"] = sum(1 for v in votos if v.get("votacao") in ids_votacao)

    # --- Propostas ---
    materias = []
    for ano in ANOS:
        itens, total = listar("materia/materialegislativa", rotulo=f"materias {ano}", ano=ano)
        itens = [m for m in itens if str(m.get("ano")) == str(ano)]
        print(f"matérias {ano}: {len(itens)} (API informou {total})", flush=True)
        materias.extend(itens)
    gravar("materias", materias, None, {"ano": ANOS})

    # Autoria: só dos autores ligados aos vereadores da legislatura atual
    autores_parl = [a for a in autores if a.get("object_id") in parl_ids
                    and "parlamentar" in json.dumps(a, ensure_ascii=False).lower()]
    resumo["autores_parlamentares"] = len(autores_parl)
    ids_mat = {m["id"] for m in materias}
    autorias = por_chave("autorias", "materia/autoria", "autor", [a["id"] for a in autores_parl],
                         limite_tabela_inteira=0)
    resumo["autorias_no_periodo"] = sum(1 for a in autorias if a.get("materia") in ids_mat)

    # --- Conferência mínima antes de publicar ---
    t = resumo["tabelas"]
    problemas = []
    if len(parl_ids) < 30:
        problemas.append(f"só {len(parl_ids)} vereadores na legislatura atual")
    if len(recentes) < 50:
        problemas.append(f"só {len(recentes)} reuniões desde {DESDE}")
    if t["presencas"]["registros"] < 1000:
        problemas.append("poucas presenças")
    if t["materias"]["registros"] < 10000:
        problemas.append("poucas matérias")
    if resumo["autorias_no_periodo"] < 5000:
        problemas.append("poucas autorias no período")
    resumo["fim"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    resumo["requisicoes"] = _n_req
    resumo["segundos_por_requisicao"] = round(_t_req / max(_n_req, 1), 2)
    resumo["problemas"] = problemas
    os.makedirs(TMP, exist_ok=True)
    for destino in (os.path.join(TMP, "_resumo.json"), os.path.join(RAIZ, "ultima_coleta.json")):
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=1, default=str)
    if problemas:
        print("COLETA SUSPEITA, NÃO VOU PUBLICAR:", problemas, file=sys.stderr)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)

    if os.path.isdir(SAIDA):
        shutil.rmtree(SAIDA)
    os.rename(TMP, SAIDA)
    print(f"OK: {_n_req} requisições", flush=True)


if __name__ == "__main__":
    main()
