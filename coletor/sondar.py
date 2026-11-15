#!/usr/bin/env python3
"""Sondagem rápida da API: total de registros e exemplo de cada endpoint, com e sem filtros."""
import json, os, time, urllib.parse, urllib.request

BASE = "https://sapl.campinas.sp.leg.br/api"
UA = "RadarCampinas/0.1 (projeto cidadao; https://github.com/Ehosimao/radar-campinas)"
SESSAO = 2266  # 69a Reunião Ordinária, 10/11/2025

TESTES = [
    ("parlamentares/legislatura", {}),
    ("parlamentares/parlamentar", {}),
    ("parlamentares/mandato", {}),
    ("parlamentares/filiacao", {}),
    ("parlamentares/partido", {}),
    ("base/autor", {}),
    ("base/tipoautor", {}),
    ("sessao/tiposessaoplenaria", {}),
    ("sessao/sessaoplenaria", {}),
    ("sessao/sessaoplenaria", {"data_inicio__gte": "2025-01-01"}),
    ("sessao/sessaoplenaria", {"data_inicio__year": 2025}),
    ("sessao/sessaoplenariapresenca", {}),
    ("sessao/sessaoplenariapresenca", {"sessao_plenaria": SESSAO}),
    ("sessao/presencaordemdia", {}),
    ("sessao/presencaordemdia", {"sessao_plenaria": SESSAO}),
    ("sessao/justificativaausencia", {}),
    ("sessao/ordemdia", {}),
    ("sessao/ordemdia", {"sessao_plenaria": SESSAO}),
    ("sessao/expedientemateria", {}),
    ("sessao/registrovotacao", {}),
    ("sessao/registrovotacao", {"ordem__sessao_plenaria": SESSAO}),
    ("sessao/votoparlamentar", {}),
    ("materia/tipomaterialegislativa", {}),
    ("materia/materialegislativa", {}),
    ("materia/materialegislativa", {"ano": 2025}),
    ("materia/materialegislativa", {"ano": 2026}),
    ("materia/autoria", {}),
    ("materia/tramitacao", {}),
]

out = []
for caminho, filtro in TESTES:
    q = dict(filtro, page_size=3)
    url = f"{BASE}/{caminho}/?{urllib.parse.urlencode(q)}"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        pag = d.get("pagination", {}) if isinstance(d, dict) else {}
        res = d.get("results", d) if isinstance(d, dict) else d
        out.append({"endpoint": caminho, "filtro": filtro, "total": pag.get("total_entries", d.get("count") if isinstance(d, dict) else len(d)),
                    "segundos": round(time.time() - t0, 1), "pagination": pag, "exemplos": res[:3]})
    except Exception as e:  # noqa: BLE001
        out.append({"endpoint": caminho, "filtro": filtro, "erro": repr(e), "segundos": round(time.time() - t0, 1)})
    print(out[-1]["endpoint"], filtro, out[-1].get("total", out[-1].get("erro")), flush=True)
    time.sleep(0.5)

os.makedirs("data", exist_ok=True)
with open("data/sonda.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
