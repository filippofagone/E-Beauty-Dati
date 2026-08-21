"""
Raccolta automatica della domanda di ricerca per E-Beauty Analyst.

Gira su GitHub una volta a settimana. Non serve lanciarlo a mano.
Produce dati.json, che la pagina dell'app legge all'apertura.

Punto delicato: Google Trends normalizza ogni interrogazione a 100 sul
termine piu' alto DI QUEL GRUPPO. Per confrontare termini presi da gruppi
diversi serve un termine presente in tutti che faccia da metro. Qui l'ancora
e' inserita automaticamente in ogni gruppo e i valori vengono riscalati.
Senza questo passaggio la classifica dei piu' ricercati sarebbe falsa.
"""

import json
import random
import sys
import time
from datetime import date
from pathlib import Path

QUI = Path(__file__).parent
ANCORA = "acido ialuronico viso"
GEO = "IT"
PERIODO = "today 5-y"
PAUSA = 14           # secondi tra un gruppo e l'altro: non abbassare
TENTATIVI = 4


def gruppi(termini, n=4):
    """Gruppi da 4 + l'ancora = 5, il massimo che Google accetta."""
    altri = [t for t in termini if t != ANCORA]
    for i in range(0, len(altri), n):
        yield [ANCORA] + altri[i:i + n]


def scarica(pytrends, termini):
    for k in range(TENTATIVI):
        try:
            pytrends.build_payload(termini, cat=0, timeframe=PERIODO, geo=GEO, gprop="")
            df = pytrends.interest_over_time()
            if df is not None and not df.empty:
                return df.drop(columns=["isPartial"], errors="ignore")
            return None
        except Exception as exc:
            attesa = PAUSA * (2 ** k) + random.uniform(0, 6)
            print(f"   {type(exc).__name__}: riprovo tra {attesa:.0f}s ({k+1}/{TENTATIVI})",
                  flush=True)
            time.sleep(attesa)
    return None


def main():
    try:
        from pytrends.request import TrendReq
    except ImportError:
        sys.exit("Manca pytrends: pip install pytrends")

    termini = json.loads((QUI / "termini.json").read_text(encoding="utf-8"))
        pytrends = TrendReq(hl="it-IT", tz=-60, timeout=(10, 30))

    serie = {}
    media_ancora = None
    falliti = []

    for i, gruppo in enumerate(gruppi(termini), 1):
        print(f"[{i}] {', '.join(gruppo[1:])}", flush=True)
        df = scarica(pytrends, gruppo)
        if df is None:
            falliti.extend(gruppo[1:])
            time.sleep(PAUSA)
            continue

        if ANCORA not in df.columns:
            falliti.extend(gruppo[1:])
            continue

        m = float(df[ANCORA].mean())
        if media_ancora is None:
            media_ancora = m
            fattore = 1.0
        else:
            fattore = media_ancora / m if m > 0 else 1.0

        for col in df.columns:
            if col == ANCORA and ANCORA in serie:
                continue
            serie[col] = [
                {"w": idx.date().isoformat(), "v": round(float(val) * fattore, 1)}
                for idx, val in df[col].items()
            ]

        print(f"    {len(df)} settimane, fattore {fattore:.2f}", flush=True)
        time.sleep(PAUSA + random.uniform(0, 6))

    if not serie:
        sys.exit("Nessun dato raccolto: interrompo senza sovrascrivere dati.json")

    uscita = {
        "generato": date.today().isoformat(),
        "geo": GEO,
        "ancora": ANCORA,
        "termini_raccolti": len(serie),
        "termini_falliti": falliti,
        "trends": serie,
    }
    (QUI / "dati.json").write_text(json.dumps(uscita, ensure_ascii=False), encoding="utf-8")
    print(f"\nScritti {len(serie)} termini in dati.json")
    if falliti:
        print("Non raccolti:", ", ".join(falliti))


if __name__ == "__main__":
    main()
