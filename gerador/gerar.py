#!/usr/bin/env python3
"""Transforma os dados brutos do SAPL (data/raw) nos arquivos do site (site/dados).

Todas as regras ficam aqui, num lugar só, e valem igualmente para todos os vereadores.
"""
import datetime as dt
import gzip
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(AQUI, "..", "data", "raw")
SITE = os.path.join(AQUI, "..", "site", "dados")
HOJE = os.environ.get("HOJE", dt.date.today().isoformat())
DESDE = os.environ.get("DESDE", "2025-01-01")
SAPL = "https://sapl.campinas.sp.leg.br"
SEQUENCIA_LONGA = 10   # reuniões seguidas fora da lista = provável licença/afastamento
MINIMO_REUNIOES = 10   # abaixo disso não mostramos porcentagem


def ler(nome):
    with gzip.open(os.path.join(RAW, nome + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").upper()


def tem(texto, *palavras):
    t = sem_acento(texto)
    return any(p in t for p in palavras)


# ---------------------------------------------------------------- grupos
GRUPOS = {
    "melhoria": {
        "nome": "Pedidos à Prefeitura (melhorias e serviços)",
        "explicacao": "Indicações e protocolados: o vereador pede à Prefeitura uma obra ou um serviço, como tapa-buraco, poda, iluminação, limpeza ou reforma de um posto de saúde.",
        "regra": "toda Indicação e todo Protocolado enviado direto à Prefeitura, exceto os que só pedem informações.",
    },
    "cobranca": {
        "nome": "Perguntas e cobranças",
        "explicacao": "Requerimentos em que o vereador pede informações ou providências à Prefeitura ou a outros órgãos.",
        "regra": "Requerimentos que pedem informações ou providências, e Protocolados que pedem informações. Ficam de fora os Requerimentos de homenagem e os de procedimento interno da Câmara (urgência, arquivamento, vista, retirada, audiência, frente parlamentar).",
    },
    "homenagem": {
        "nome": "Homenagens",
        "explicacao": "Parabéns, pesar, título de cidadão, medalhas, nomes de rua e datas comemorativas.",
        "regra": ("Moções e Requerimentos de congratulação, aplauso, louvor ou pesar; projetos que dão nome a rua ou "
                  "lugar público, concedem título, medalha ou diploma, ou criam data, dia ou semana comemorativa."),
    },
    "lei": {
        "nome": "Propostas de lei",
        "explicacao": "Projetos de lei, de lei complementar, de decreto legislativo, de resolução e de emenda à Lei Orgânica, exceto os de homenagem.",
        "regra": "Projetos de Lei, Lei Complementar, Decreto Legislativo, Resolução e Emenda à Lei Orgânica que não sejam de homenagem.",
    },
    "outros": {
        "nome": "Outros documentos",
        "explicacao": "Moções de apoio, apelo ou protesto, requerimentos de procedimento interno, emendas (inclusive as emendas impositivas ao orçamento), substitutivos e outros documentos.",
        "regra": "o que não se encaixa nos grupos acima (moções de apoio ou repúdio, emendas, substitutivos, recursos etc.).",
    },
}

HOMENAGEM_MOCAO = ("CONGRATULA", "APLAUSO", "LOUVOR", "PESAR", "PARABENIZA", "PARABENS", "HOMENAGE",
                   "RECONHECIMENTO", "JUBILO", "FELICITA", "CONDOLENCIA", "VOTO DE", "VOTOS DE")
HOMENAGEM_LEI = ("DENOMINA", "DA DENOMINACAO", "DENOMINACAO DE", "TITULO DE CIDADA", "TITULO DE CIDADAO",
                 "CIDADAO CAMPINEIRO", "CIDADA CAMPINEIRA", "CIDADAO HONORARIO", "CIDADA HONORARIA", "MEDALHA",
                 "DIPLOMA", "COMENDA", "HONRA AO MERITO", "VOTO DE", "VOTOS DE", "CONCEDE TITULO", "CONCEDE O TITULO", "INSTITUI O DIA", "INSTITUI A SEMANA",
                 "INSTITUI O MES", "INSTITUI, NO MUNICIPIO DE CAMPINAS, O DIA", "INSTITUI NO MUNICIPIO DE CAMPINAS O DIA",
                 "NO CALENDARIO", "CALENDARIO OFICIAL", "DATA COMEMORATIVA", "SEMANA MUNICIPAL", "DIA MUNICIPAL")


PROCEDIMENTO_REQ = ("REQUER TRAMITACAO", "REQUER O ARQUIVAMENTO", "REQUER ARQUIVAMENTO", "REQUER A REALIZACAO",
                    "REQUER REALIZACAO", "REQUER A CRIACAO", "REQUER INCLUSAO", "REQUER DISPENSA", "REQUER A RETIRADA",
                    "REQUER RETIRADA", "REQUER VISTA", "REQUER PRORROGACAO", "REQUER ADIAMENTO", "REQUER URGENCIA",
                    "REQUER LICENCA", "REQUER O DESARQUIVAMENTO", "REQUER DESARQUIVAMENTO", "REQUER NOS TERMOS")


def classificar(sigla, tipo_desc, ementa):
    t = sem_acento(tipo_desc)
    e = sem_acento(ementa).strip()
    if sigla == "IND" or t.startswith("INDICA"):
        return "melhoria"
    if sigla == "PPREF":  # protocolados enviados direto à Prefeitura
        if "INFORMA" in e[:40]:
            return "cobranca"
        return "melhoria"
    if sigla == "MOC" or t.startswith("MOCAO"):
        return "homenagem" if tem(e, *HOMENAGEM_MOCAO) else "outros"
    if sigla == "REQ" or t.startswith("REQUERIMENTO"):
        if tem(e, *HOMENAGEM_MOCAO):
            return "homenagem"
        if e.startswith(PROCEDIMENTO_REQ):
            return "outros"
        return "cobranca"
    if "EMENDA" in t and "LEI ORGANICA" not in t:
        return "outros"
    if "SUBSTITUTIVO" in t:
        return "outros"
    if t.startswith("PROJETO") or t.startswith("PROPOSTA DE EMENDA"):
        return "homenagem" if tem(e, *HOMENAGEM_LEI) else "lei"
    return "outros"


# ---------------------------------------------------------------- pedidos por lugar
TEMAS = [
    ("Buracos e asfalto", ("BURACO", "RECAPE", "PAVIMENTA", "ASFALT", "OPERACAO TAPA", "CRATERA")),
    ("Poda e árvores", ("PODA", "ARVORE", "GALHO", "SUPRESSAO", "EXTRACAO DE ARV", "REMOCAO DE ARV")),
    ("Iluminação", ("ILUMINA", "LAMPADA", "LUMINARIA", "POSTE", "REATOR")),
    ("Limpeza, mato e entulho", ("LIMPEZA", "ROCAG", "ROCADA", "CAPINA", "MATO ", "ENTULHO", "DESCARTE", "LIXO", "VARRI")),
    ("Bueiros e drenagem", ("BUEIRO", "BOCA DE LOBO", "BOCAS DE LOBO", "GALERIA", "DRENAG", "ALAGA", "CORREGO", "ESGOTO", "GUIAS E SARJETAS", "SARJETA")),
    ("Trânsito e sinalização", ("LOMBADA", "REDUTOR", "SINALIZA", "FAIXA DE PEDESTRE", "SEMAFORO", "RADAR", "VAGA", "ESTACIONAMENTO")),
    ("Calçadas", ("CALCADA", "PASSEIO PUBLICO")),
    ("Ônibus", ("ONIBUS", "PONTO DE ONIBUS", "ABRIGO", "LINHA ", "TRANSPORTE COLETIVO")),
    ("Praças e áreas verdes", ("PRACA", "PARQUINHO", "ACADEMIA AO AR LIVRE", "AREA VERDE")),
]
LOGRADOURO = re.compile(
    r"\b(RUA|R\.|AVENIDA|AV\.|ALAMEDA|AL\.|TRAVESSA|ESTRADA|PRACA|VIELA|RODOVIA|LARGO|VIADUTO)\s+"
    r"([A-Z0-9][A-Z0-9 .'ºª°\-]{2,70}?)"
    r"(?=\s*(?:,|;|\(|\.(?:\s|$)|\s-\s|\s+N[º°O.]|\s+NUMERO|\s+ALTURA|\s+PROXIMO|\s+ESQUINA|\s+NO BAIRRO|\s+BAIRRO|\s+NO JARDIM|\s+NA VILA|\s+NO PARQUE|\s+JARDIM|\s+EM FRENTE|\s+ENTRE|\s+DEFRONTE|\s+E\s+(?:RUA|AV)|$))")
BAIRRO = re.compile(
    r"\b((?:JARDIM|JD\.|VILA|PARQUE|PQ\.|CONJUNTO HABITACIONAL|CONJ\. HAB\.|RESIDENCIAL|CHACARA|CHACARAS|NUCLEO RESIDENCIAL|BAIRRO|DISTRITO DE|CIDADE|PROFILURB|DIC|SAO|SANTA|SANTO)"
    r"\s+[A-Z0-9][A-Z0-9 .'\-]{2,40}?)(?=\s*(?:,|;|\.|\(|\s-\s|$|\s+E\s|\s+NA\s|\s+NO\s|\s+EM\s|\s+REGIAO))")
TIPO_LOG = {"R.": "RUA", "AV.": "AVENIDA", "AL.": "ALAMEDA"}


NOME_GENERICO = re.compile(r"^(LOCALIZAD|SITUAD|PUBLIC|SEM |EXISTENTE|DO BAIRRO|DA REGIAO|ENTRE|PRINCIPAL|LATERAL|PROXIM|"
                           r"ACIMA|ABAIXO|DE ACESSO|SEM DENOMINACAO|SEM NOME|DENOMINAD|CONHECID|EM FRENTE|ONDE|QUE |TODA|DAS |DOS |"
                           r"DO |DA |NA |NO |E |A |O |AS |OS |S/N)")


def lugares(ementa):
    e = sem_acento(ementa)
    ruas, bairros, resto = [], [], e
    for m in LOGRADOURO.finditer(e):
        tipo = TIPO_LOG.get(m.group(1), m.group(1))
        nome = re.sub(r"\s+", " ", m.group(2)).strip(" .-")
        resto = resto.replace(m.group(0), " | ")
        if len(nome) >= 3 and not NOME_GENERICO.match(nome):
            ruas.append(f"{tipo} {nome}")
    for m in BAIRRO.finditer(resto):
        b = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
        b = re.sub(r"^BAIRRO\s+", "", b)
        b = b.replace("JD. ", "JARDIM ").replace("PQ. ", "PARQUE ")
        if len(b) >= 6 and not NOME_GENERICO.match(b.split(" ", 1)[-1]):
            bairros.append(b)
    return list(dict.fromkeys(ruas)), list(dict.fromkeys(bairros))


def tema(ementa):
    e = sem_acento(ementa)
    for nome, chaves in TEMAS:
        if any(c in e for c in chaves):
            return nome
    return None


def titulo(s):
    pequenas = {"DE", "DA", "DO", "DAS", "DOS", "E"}
    return " ".join(p.lower() if p in pequenas else p.capitalize() for p in s.split())


# ---------------------------------------------------------------- principal
def main():
    leg = [l for l in ler("legislaturas")]
    leg_atual = max(leg, key=lambda l: l["data_inicio"])
    parlamentares = {p["id"]: p for p in ler("parlamentares")}
    partidos = {p["id"]: p for p in ler("partidos")}
    tipos_materia = {t["id"]: t for t in ler("tipos_materia")}
    autores = {a["id"]: a for a in ler("autores")}

    # mandatos na legislatura atual (um vereador pode ter mais de um período)
    periodos = defaultdict(list)
    titular = defaultdict(bool)
    for m in ler("mandatos"):
        if m["legislatura"] != leg_atual["id"]:
            continue
        ini = m.get("data_inicio_mandato") or leg_atual["data_inicio"]
        fim = m.get("data_fim_mandato") or leg_atual["data_fim"]
        periodos[m["parlamentar"]].append((ini, fim))
        titular[m["parlamentar"]] |= bool(m.get("titular"))

    def no_mandato(pid, dia):
        return any(i <= dia <= f for i, f in periodos[pid])

    # partido atual (última filiação sem desfiliação)
    partido = {}
    for f in sorted(ler("filiacoes"), key=lambda f: f.get("data") or ""):
        if f.get("data_desfiliacao"):
            if partido.get(f["parlamentar"], (None, None))[1] == f["id"]:
                partido.pop(f["parlamentar"], None)
            continue
        p = partidos.get(f["partido"])
        if p:
            partido[f["parlamentar"]] = (p["sigla"], f["id"])

    autor_para_parl = {a["id"]: a["object_id"] for a in autores.values()
                       if a.get("tipo") == 1 and a.get("object_id") in periodos}

    # ---------------- presença
    sessoes = {s["id"]: s for s in ler("sessoes")}
    presentes_por_sessao = defaultdict(set)
    for p in ler("presencas"):
        presentes_por_sessao[p["sessao_plenaria"]].add(p["parlamentar"])
    presentes_ordemdia = defaultdict(set)
    for p in ler("presencas_ordemdia"):
        presentes_ordemdia[p["sessao_plenaria"]].add(p["parlamentar"])
    # reuniões sem a lista da abertura mas com a lista da Ordem do Dia: usamos a da Ordem do Dia
    so_ordemdia = [sid for sid in presentes_ordemdia if sid not in presentes_por_sessao and presentes_ordemdia[sid]]
    for sid in so_ordemdia:
        presentes_por_sessao[sid] = set(presentes_ordemdia[sid])
    deliberativas = [s for s in sessoes.values()
                     if DESDE <= s["data_inicio"] <= HOJE
                     and re.search(r"ordin|extraordin", sem_acento(s.get("tipo")), re.I)]
    sem_lista = [s for s in deliberativas if not presentes_por_sessao.get(s["id"])]
    contadas = [s for s in deliberativas if presentes_por_sessao.get(s["id"])]

    def nome_sessao(s):
        return f"{s['numero']}ª Reunião {s['tipo']} de {s['data_inicio'][:4]}"

    # ---------------- matérias
    materias = {m["id"]: m for m in ler("materias")}
    props = defaultdict(list)
    pedidos = []
    for m in materias.values():
        parls = sorted({autor_para_parl[a] for a in (m.get("autores") or []) if a in autor_para_parl})
        if not parls:
            continue
        tipo = tipos_materia.get(m["tipo"], {})
        g = classificar(tipo.get("sigla", ""), tipo.get("descricao", ""), m.get("ementa"))
        item = {"id": m["id"], "t": tipo.get("sigla", ""), "tipo": tipo.get("descricao", "Matéria"),
                "n": m["numero"], "a": m["ano"], "d": m.get("data_apresentacao"),
                "e": (m.get("ementa") or "").strip(), "g": g}
        if len(m.get("autores") or []) > 1:
            item["co"] = 1
        for pid in parls:
            props[pid].append(item)
        if g == "melhoria":
            pedidos.append({"id": m["id"], "t": tipo.get("descricao", ""), "n": m["numero"], "a": m["ano"], "d": m.get("data_apresentacao"),
                            "e": item["e"][:400], "v": parls})

    # ---------------- votos nominais
    regs = {r["id"]: r for r in ler("registros_votacao")}
    ordem = {o["id"]: o for o in ler("ordemdia")}
    expediente = {o["id"]: o for o in ler("expediente_materia")}
    votos = defaultdict(list)
    for v in ler("votos_nominais"):
        r = regs.get(v.get("votacao"))
        if not r:
            continue
        item_pauta = ordem.get(r.get("ordem")) or expediente.get(r.get("expediente"))
        d = (item_pauta or {}).get("data_ordem") or (r.get("data_hora") or "")[:10]
        if not d or d < DESDE:
            continue
        mat = materias.get(r.get("materia"))
        if mat:
            mn = f"{tipos_materia.get(mat['tipo'], {}).get('descricao', 'Matéria')} nº {mat['numero']}/{mat['ano']}"
        else:
            mn = (r.get("__str__") or "").split(" - Matéria: ")[-1]
        res = re.search(r"Votação: (.*?) - Matéria", r.get("__str__") or "")
        votos[v["parlamentar"]].append({"d": d, "m": r.get("materia"), "mn": mn, "voto": v.get("voto"),
                                        "r": res.group(1) if res else ""})

    # ---------------- arquivos
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, "v"))

    lista = []
    for pid in sorted(periodos):
        p = parlamentares[pid]
        ini = min(i for i, _ in periodos[pid])
        fim = max(f for _, f in periodos[pid])
        minhas = sorted((s for s in contadas if no_mandato(pid, s["data_inicio"])), key=lambda s: s["data_inicio"])
        # Sequências longas sem presença: provável licença/afastamento/posse posterior. Não entram na conta.
        excluidas, periodos_fora, run = set(), [], []
        for s_ in minhas + [None]:
            if s_ is not None and pid not in presentes_por_sessao[s_["id"]]:
                run.append(s_)
                continue
            if len(run) >= SEQUENCIA_LONGA:
                excluidas.update(x["id"] for x in run)
                periodos_fora.append({"de": run[0]["data_inicio"], "ate": run[-1]["data_inicio"], "reunioes": len(run)})
            run = []
        minhas = [s_ for s_ in minhas if s_["id"] not in excluidas]
        aus = [s_ for s_ in minhas if pid not in presentes_por_sessao[s_["id"]]]
        pres = len(minhas) - len(aus)
        com_od = [s_ for s_ in minhas if presentes_ordemdia.get(s_["id"])]
        pres_od = sum(1 for s_ in com_od if pid in presentes_ordemdia[s_["id"]])
        grupos = Counter(x["g"] for x in props[pid])
        em_exercicio = no_mandato(pid, HOJE) and bool(p.get("ativo"))
        resumo = {
            "id": pid, "nome": p["nome_parlamentar"], "partido": (partido.get(pid) or (None,))[0],
            "foto": p.get("fotografia"), "titular": titular[pid], "em_exercicio": em_exercicio,
            "mandato": {"inicio": ini, "fim": fim},
            "presenca": {"presentes": pres, "total": len(minhas),
                         "pct": round(100 * pres / len(minhas)) if len(minhas) >= MINIMO_REUNIOES else None,
                         "fora": periodos_fora,
                         "ordemdia": {"presentes": pres_od, "total": len(com_od),
                                      "pct": round(100 * pres_od / len(com_od)) if len(com_od) >= MINIMO_REUNIOES else None}},
            "propostas": {**{g: grupos.get(g, 0) for g in GRUPOS}, "total": len(props[pid])},
            "votos_nominais": len(votos[pid]),
        }
        # vereador sem nenhuma atividade e sem mandato hoje (ex.: suplente que nunca assumiu) fica de fora
        if not em_exercicio and not minhas and not props[pid]:
            continue
        lista.append(resumo)
        ficha = dict(resumo)
        ficha.update({
            "nome_completo": p.get("nome_completo"),
            "email": p.get("email") or None,
            "telefone": p.get("telefone") or None,  # telefone do gabinete; celular nunca é publicado
            "presenca": dict(resumo["presenca"], ausencias=[
                {"id": s["id"], "data": s["data_inicio"], "nome": nome_sessao(s)}
                for s in sorted(aus, key=lambda s: s["data_inicio"], reverse=True)]),
            "propostas": sorted(props[pid], key=lambda x: x["d"] or "", reverse=True),
            "votos": sorted(votos[pid], key=lambda x: x["d"], reverse=True),
        })
        with open(os.path.join(SITE, "v", f"{pid}.json"), "w", encoding="utf-8") as f:
            json.dump(ficha, f, ensure_ascii=False, separators=(",", ":"))

    # pedidos repetidos no mesmo lugar e com o mesmo tema
    grupos_lugar = defaultdict(list)
    bairros_da_rua = defaultdict(Counter)
    for p in pedidos:
        tm = tema(p["e"])
        ruas, bairros = lugares(p["e"])
        for r in ruas:
            for b in bairros:
                bairros_da_rua[r][b] += 1
        if not tm:
            continue
        for r in ruas:
            grupos_lugar[(tm, r)].append(p)
    recorrentes = []
    for (tm, rua), ps in grupos_lugar.items():
        ps = sorted({p["id"]: p for p in ps}.values(), key=lambda p: p["d"] or "")
        if len(ps) < 3:
            continue
        b = bairros_da_rua[rua].most_common(1)
        local = titulo(rua) + (f", {titulo(b[0][0])}" if b else "")
        recorrentes.append({"tema": tm, "local": local, "ids": [p["id"] for p in ps],
                            "datas": [p["d"] for p in ps],
                            "autores": sorted({a for p in ps for a in p["v"]})})
    recorrentes.sort(key=lambda r: (-len(r["ids"]), r["local"]))

    with open(os.path.join(SITE, "pedidos.json"), "w", encoding="utf-8") as f:
        json.dump({"pedidos": sorted(pedidos, key=lambda p: p["d"] or "", reverse=True),
                   "recorrentes": recorrentes}, f, ensure_ascii=False, separators=(",", ":"))

    agora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3)))
    geral = {
        "atualizado": agora.strftime("%d/%m/%Y às %Hh%M"),
        "legislatura": f"{leg_atual['numero']}ª legislatura, {leg_atual['data_inicio'][:4]} a {leg_atual['data_fim'][:4]}",
        "periodo": {"desde": DESDE, "ate": HOJE},
        "reunioes": {"contadas": len(contadas), "sem_lista": len(sem_lista), "so_ordemdia": len(so_ordemdia)},
        "grupos": GRUPOS,
        "regra_presenca": (
            f"Contamos as reuniões ordinárias e extraordinárias realizadas desde {DESDE[8:]}/{DESDE[5:7]}/{DESDE[:4]} "
            f"em que a Câmara registrou a lista de presença ({len(contadas)} reuniões até agora). Para cada vereador, só entram "
            "as reuniões em que ele estava no mandato. Presença é aparecer na lista oficial de presença da reunião, feita na abertura. "
            f"Em {len(so_ordemdia)} reuniões o sistema só tem a lista da Ordem do Dia, e usamos essa. "
            "A Câmara também registra uma segunda lista, a da Ordem do Dia, que é a parte da reunião em que acontecem as votações. "
            "As duas listas nem sempre coincidem (alguém pode chegar depois da abertura ou sair antes das votações), então a ficha mostra as duas. "
            f"{len(sem_lista)} reuniões não têm lista registrada no sistema e não entram na conta de ninguém. "
            "O sistema da Câmara não registra licenças, afastamentos nem justificativas de ausência. Por isso, quando um vereador fica "
            f"{SEQUENCIA_LONGA} ou mais reuniões seguidas fora da lista, tratamos esse período como provável licença, afastamento "
            "ou mandato ainda não iniciado: ele não entra na conta e aparece separado na ficha. Ausências mais curtas entram na conta. "
            f"Com menos de {MINIMO_REUNIOES} reuniões contadas, o site não mostra porcentagem."),
        "limites": [
            "Uma ausência na lista não quer dizer, sozinha, falta sem motivo: licenças médicas, missões oficiais e justificativas não aparecem no sistema.",
            f"Os períodos tratados como “provável licença ou afastamento” são uma estimativa nossa ({SEQUENCIA_LONGA} ou mais reuniões seguidas fora da lista), não um registro oficial da Câmara.",
            "A maioria das votações é simbólica e não registra o voto de cada vereador. Por isso a seção de votos mostra só as votações nominais.",
            "Os grupos de propostas seguem uma regra automática por tipo de documento e palavras da ementa. Pode haver erros pontuais de classificação; o documento original está sempre a um toque.",
            "Os “pedidos que se repetem” são encontrados lendo o nome da rua e o assunto escritos na ementa. Ementas escritas de jeitos diferentes podem não ser agrupadas, e o contrário também pode acontecer.",
            "Propostas com vários autores contam para cada um deles.",
        ],
        "vereadores": lista,
    }
    with open(os.path.join(SITE, "geral.json"), "w", encoding="utf-8") as f:
        json.dump(geral, f, ensure_ascii=False, separators=(",", ":"))

    # resumo para conferência
    print(f"legislatura {leg_atual['numero']}: {len(lista)} vereadores no site, {len(contadas)} reuniões contadas, "
          f"{len(sem_lista)} sem lista, {len(pedidos)} indicações, {len(recorrentes)} grupos de pedidos repetidos")
    if len(lista) < 30 or len(contadas) < 50:
        print("RESULTADO ESTRANHO, abortando", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
