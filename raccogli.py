"""
Raccolta automatica per E-Beauty Analyst - versione a tre aree.

Aree raccolte:
  IT    = Italia
  EU    = media di Germania e Francia (Google Trends non ha un'area "Europa")
  MONDO = tutto il mondo

Per stare nel piano gratuito di SerpApi: l'Italia viene raccolta ogni
settimana; Europa e Mondo nelle settimane pari. Il lancio manuale
(Run workflow) raccoglie sempre tutto. Le aree non raccolte in un giro
vengono conservate dal file precedente, mai cancellate.
"""

import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

QUI = Path(__file__).parent
ANCORA = "acido ialuronico viso"
PERIODO = "today 5-y"
PAUSA = 3

AREE = {
    "IT": ["IT"],
    "EU": ["DE", "FR"],
    "MONDO": [""],          # stringa vuota = mondo intero
}


def gruppi(termini, n=4):
    altri = [t for t in termini if t != ANCORA]
    for i in range(0, len(altri), n):
        yield [ANCORA] + altri[i:i + n]


def scarica(chiave, termini, geo):
    parametri = {
        "engine": "google_trends",
        "q": ",".join(termini),
        "date": PERIODO,
        "data_type": "TIMESERIES",
        "api_key": chiave,
    }
    if geo:
        parametri["geo"] = geo
    r = requests.get("https://serpapi.com/search.json", params=parametri, timeout=90)
    dati = r.json()
    if "error" in dati:
        raise RuntimeError(dati["error"])
    punti = dati.get("interest_over_time", {}).get("timeline_data", [])
    serie = {t: [] for t in termini}
    for p in punti:
        ts = p.get("timestamp")
        if ts is None:
            continue
        giorno = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        for v in p.get("values", []):
            q, val = v.get("query"), v.get("extracted_value")
            if q in serie and val is not None:
                serie[q].append({"w": giorno, "v": float(val)})
    return {t: s for t, s in serie.items() if s}


def raccogli_geo(chiave, termini, geo):
    """Tutti i gruppi per una singola area geografica, con riscalatura sull'ancora."""
    serie_tot = {}
    media_ancora = None
    falliti = []
    for i, gruppo in enumerate(gruppi(termini), 1):
        print(f"  [{geo or 'MONDO'} {i}] {', '.join(gruppo[1:])}", flush=True)
        try:
            blocco = scarica(chiave, gruppo, geo)
        except Exception as exc:
            print(f"      errore: {exc}", flush=True)
            falliti.extend(gruppo[1:])
            time.sleep(PAUSA)
            continue
        ancora = blocco.get(ANCORA)
        if not ancora:
            falliti.extend(gruppo[1:])
            continue
        m = sum(x["v"] for x in ancora) / len(ancora)
        if media_ancora is None:
            media_ancora, fattore = m, 1.0
        else:
            fattore = media_ancora / m if m > 0 else 1.0
        for t, punti in blocco.items():
            if t == ANCORA and ANCORA in serie_tot:
                continue
            serie_tot[t] = [{"w": x["w"], "v": round(x["v"] * fattore, 1)} for x in punti]
        time.sleep(PAUSA)
    return serie_tot, falliti


def media_paesi(liste):
    """Media punto per punto tra piu' paesi (per l'area Europa)."""
    out = {}
    termini = set()
    for l in liste:
        termini |= set(l)
    for t in termini:
        per_data = {}
        for l in liste:
            for p in l.get(t, []):
                per_data.setdefault(p["w"], []).append(p["v"])
        out[t] = [{"w": w, "v": round(sum(v) / len(v), 1)}
                  for w, v in sorted(per_data.items())]
    return out


def main():
    chiave = os.environ.get("SERPAPI_KEY", "").strip()
    if not chiave:
        sys.exit("Manca il secret SERPAPI_KEY: aggiungilo in "
                 "Settings > Secrets and variables > Actions.")

    termini = json.loads((QUI / "termini.json").read_text(encoding="utf-8"))

    manuale = os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch"
    settimana_pari = date.today().isocalendar()[1] % 2 == 0
    tutte = manuale or settimana_pari
    da_fare = list(AREE) if tutte else ["IT"]
    print("Aree in raccolta questa volta:", ", ".join(da_fare), flush=True)

    # conservo le aree gia' raccolte in passato
    aree_out = {}
    vecchio = QUI / "dati.json"
    if vecchio.exists():
        try:
            aree_out = json.loads(vecchio.read_text(encoding="utf-8")).get("aree", {})
        except Exception:
            aree_out = {}

    falliti_tot = []
    for nome in da_fare:
        print(f"\n== Area {nome} ==", flush=True)
        raccolte = []
        for geo in AREE[nome]:
            serie, falliti = raccogli_geo(chiave, termini, geo)
            falliti_tot.extend(falliti)
            if serie:
                raccolte.append(serie)
        if len(raccolte) == 1:
            aree_out[nome] = raccolte[0]
        elif len(raccolte) > 1:
            aree_out[nome] = media_paesi(raccolte)
        else:
            print(f"  area {nome}: nessun dato, conservo la versione precedente", flush=True)

    if not aree_out.get("IT"):
        sys.exit("Nessun dato per l'Italia: interrompo senza sovrascrivere dati.json")

    uscita = {
        "generato": date.today().isoformat(),
        "ancora": ANCORA,
        "aree": aree_out,
        "trends": aree_out["IT"],      # compatibilita' con versioni vecchie dell'app
        "termini_falliti": sorted(set(falliti_tot)),
    }
    vecchio.write_text(json.dumps(uscita, ensure_ascii=False), encoding="utf-8")
    print(f"\nScritte {len(aree_out)} aree in dati.json "
          f"({', '.join(aree_out)}); Italia: {len(aree_out['IT'])} termini")


if __name__ == "__main__":
    main()
