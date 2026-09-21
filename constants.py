# ============================================================================
#  reverse-GTAA — Mean-Reversion-Sleeve, 3 Bausteine (QQQ / EM / GOLD).
#  Korb-Crosscheck: QQQ/EM/Gold schlaegt QQQ/EM/EU50 und QQQ/EM/EU50/Gold klar
#  (Sortino 1.07 vs 0.66/0.68) -- Gold ist die dekorrelierte Nicht-Aktien-Saeule.
#  MONATLICH. Invest-Entscheidung (Status/Dashboard) = LETZTER Handelstag/Monat
#  (backtest-bester Tag: CAGR 30.5 vs 27.3 am 1. Tag). ntfy trotzdem an BEIDEN
#  Tagen (Monatsletzter + 1. Handelstag) -> du waehlst den Ausfuehrungstag selbst.
#  Selektion flop2 (2 NIEDRIGSTE SMA-Werte). Ranking SMA110/175 (nur Rangfolge).
#  Rebound-Confirm 1+2+3M (Oe der 1M/2M/3M-Returns > 0, sonst Slot -> Cash).
#  Tilt 30/70 (schwaechstes 30%, 2.-schwaechstes 70%; Sortino/mm5/MaxDD-Optimum im
#  Sweep 0/100..50/50). Fallback slotfloor: nur 1 Asset bestaetigt -> max(Slot,0.5)
#  (bestes Sortino 1.11 / mm5 0.91 bei reasonable Turnover; besser als cash 0.77 mm5).
#  Verifiziert (v6, monatsletzter, 30/70, slotfloor, 3x): CAGR 35.7 / Sortino 1.11 /
#  MaxDD -44.4 / mm3 0.75 / mm5 0.91 / WorstYear -27.0 / Turn 5.3. Dekorrelierter Sleeve, NICHT eigenstaendiges Kern-Investment.
# ============================================================================
STRAT_NAME = "reverse-GTAA (Mean-Reversion-Sleeve)"
STRAT_ASCII = "reverseGTAA"
STRAT_KEY  = "reversegtaa"
REBALANCE_LABEL = "letzter Handelstag des Monats"
SIGNAL_CURRENCY_NOTE = "Signale auf zuverlaessigen USD-1x-Kursen (Yahoo); kein Xetra-Lag (B1)."
INFO_FOOTER = ("Gehebelte ETPs: Pfad-/Emittentenrisiko. Dekorrelierter Sleeve, kein Kern-Invest. "
               "KEINE ANLAGEBERATUNG.")
NTFY_MODE = "monthly"         # ntfy am Monatsletzten UND Monatsersten (du waehlst den Handelstag)
NOTIFY_DAYS = ["monthly_last", "monthly_first"]

# leverage = realer Produkthebel (3x-Aktien / 2x-Gold), Momentum/SMA auf 1x-Kursen.
ASSETS = {
 "NASDAQ100": dict(ticker="QQQ", leverage=3, display="Nasdaq 100",
                   product="WisdomTree NASDAQ 100 3x Daily Leveraged", isin="IE00BLRPRL42"),
 "EM":        dict(ticker="EEM", leverage=3, display="Emerging Markets",
                   product="3x Emerging Markets ETP (real; ISIN vom Nutzer bestaetigen)", isin=""),
 "GOLD":      dict(ticker="GLD", leverage=3, display="Gold",
                   product="WisdomTree Gold 3x Daily Leveraged", isin="IE00B8HGT870"),
}
CFG = dict(mode="reverse", rebalance="monthly_last", cooldown_days=0,
           S=110, L=175, N=2, lookbacks=(1,3,6,9), rebound_months=(1,2,3),
           pick="flop", weights=[0.3, 0.7], fallback="slotfloor", try_count=3)   # Tilt 30/70, Fallback max(slot,0.5)
