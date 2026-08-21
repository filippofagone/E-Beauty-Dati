"""
Raccolta automatica della domanda di ricerca per E-Beauty Analyst.
Versione SerpApi: interroga Google Trends attraverso un servizio autorizzato,
perche' Google blocca le richieste dirette fatte dai computer di GitHub.

La chiave del servizio NON e' scritta qui dentro: viene letta da un
"secret" di GitHub chiamato SERPAPI_KEY. Mai incollare la chiave nel
codice, perche' questo repository e' pubblico.
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
GEO = "IT"
PERIODO = "today 5-y"
PAUSA = 3


def gruppi(termini, n=4):
    """Gruppi da 4 + l'ancora = 5, il massimo che Google Trends confronta."""
    altri = [t for t in termini if t != ANCORA]
    for i in range(0, len(altri), n):
        yield [ANCORA] + altri[i:i + n]


def scarica(chiave, termini):
    r = requests.get("https://serpapi.com/search.json", params={
        "engine": "google_trends",
        "q": ",".join(termini),
        "geo": GEO,
        "date": PERIODO,
        "data_type": "TIMESERIES",
        "api_key": chiave,
    }, timeout=90)
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


def main():
    chiave = os.environ.get("SERPAPI_KEY", "").strip()
    if not chiave:
        sys.exit("Manca il secret SERPAPI_KEY: aggiungilo in "
                 "Settings > Secrets and variables > Actions.")

    termini = json.loads((QUI / "termini.json").read_text(encoding="utf-8"))

    serie_tot = {}
    media_ancora = None
    falliti = []

    for i, gruppo in enumerate(gruppi(termini), 1):
        print(f"[{i}] {', '.join(gruppo[1:])}", flush=True)
        try:
            blocco = scarica(chiave, gruppo)
        except Exception as exc:
            print(f"    errore: {exc}", flush=True)
            falliti.extend(gruppo[1:])
            time.sleep(PAUSA)
            continue

        ancora = blocco.get(ANCORA)
        if not ancora:
            print("    manca l'ancora nella risposta: gruppo scartato", flush=True)
            falliti.extend(gruppo[1:])
            continue

        m = sum(x["v"] for x in ancora) / len(ancora)
        if media_ancora is None:
            media_ancora = m
            fattore = 1.0
        else:
            fattore = media_ancora / m if m > 0 else 1.0

        for t, punti in blocco.items():
            if t == ANCORA and ANCORA in serie_tot:
                continue
            serie_tot[t] = [{"w": x["w"], "v": round(x["v"] * fattore, 1)} for x in punti]

        print(f"    {len(ancora)} settimane, fattore {fattore:.2f}", flush=True)
        time.sleep(PAUSA)

    if not serie_tot:
        sys.exit("Nessun dato raccolto: interrompo senza sovrascrivere dati.json")

    uscita = {
        "generato": date.today().isoformat(),
        "geo": GEO,
        "ancora": ANCORA,
        "termini_raccolti": len(serie_tot),
        "termini_falliti": falliti,
        "trends": serie_tot,
    }
    (QUI / "dati.json").write_text(json.dumps(uscita, ensure_ascii=False), encoding="utf-8")
    print(f"\nScritti {len(serie_tot)} termini in dati.json")
    if falliti:
        print("Non raccolti:", ", ".join(falliti))


if __name__ == "__main__":
    main()
