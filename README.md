# reverse-GTAA (Mean-Reversion-Sleeve)

Discord- + ntfy-Signalbot (GitHub Actions) fuer die **reverse-GTAA (Mean-Reversion-Sleeve)**-Strategie.
Gleiche, bewaehrte Infrastruktur wie der 3xSpyTips-Bot (`letsgo-signalbot`) — alle
Bugfixes B1–B12/F1–F4 uebernommen. Der Strategie-Kern ist unabhaengig gegen den
verifizierten v6-Backtest geprueft (0 Abweichung auf 5517 Handelstagen).

## Strategie
3 Bausteine **QQQ/EM/Gold** (Korb-Crosscheck-Sieger), **flop2** (2 niedrigste SMA-Werte), Ranking **SMA110/175**, **Rebound-Confirm 1+2+3M** (sonst Cash), **Tilt 30/70** (schwaechstes/2.-schwaechstes), **Fallback slotfloor** (nur 1 Asset -> max(slot,0.5)). **Kein** SMA-Trendfilter. Verifiziert (monatsletzter, 3x): CAGR 35,7 / Sortino 1,11 / MaxDD −44,4 / mm5 0,91 / WorstYear −27,0.

- **Signale:** ausschliesslich auf zuverlaessigen **USD-1x-Kursen** (Yahoo), Entscheidung
  von gestern wirkt heute (`.shift(1)`, kein Look-Ahead). Momentum-Fenster = 21/42/63/126/189 Handelstage.
- **Rebalancing:** **Monatlich** — Invest-Entscheidung = **letzter Handelstag** des Monats (Dashboard/Status). ntfy an **beiden** Tagen (Monatsletzter + 1. Handelstag), du waehlst den Ausfuehrungstag.
- **ntfy (Handy-Push):** NUR bei echtem Handelswechsel am Monatsletzten UND am 1. Handelstag — jeweils mit eigener Entscheidung + Aenderung ggue. gleichem Tag im Vormonat. Taeglich laeuft eine
  Discord-Statusmeldung.

## Signal-Ticker
`QQQ` Nasdaq100 (3x) · `EEM` EM (3x) · `GLD` Gold (3x). Momentum/SMA auf 1x-Kursen.

## Dateien
```
main.py                      # Einstieg (Vertrag: run_strategy -> (signal, None, text))
send_ntfy.py                 # ntfy-Push, wirft nie (F1/B10)
strategies/constants.py      # ALLE Parameter (Single Source of Truth, B4/B11)
strategies/gtaa_botcore.py   # verifizierter Strategie-Kern (identisch in allen 3 Bots)
strategies/runner.py         # Download + Frische + History + Nachricht + status_*.json
.github/workflows/notify.yaml
history_reversegtaa.txt            # Allokations-Historie (committet, fuer Dashboard)
status_reversegtaa.json            # aktueller Stand (committet, fuer Dashboard)
```

## Setup (Kurz — Details im GTAA_Signalbots_Setup.md)
1. Repo **public** anlegen, Dateien am **exakten Pfad** ablegen (v.a. `.github/workflows/notify.yaml`, B12).
2. Secrets: `DISCORD_WEBHOOK_URL`, `NTFY_TOPIC` (langer, geheimer Name; optional `NTFY_SERVER`).
3. **Settings → Actions → General → Workflow permissions → „Read and write permissions"** (B8!).
4. Actions-Tab → „Run workflow" testen. Cron: `17 5 * * *` (07:17 Berlin).

KEINE ANLAGEBERATUNG.
