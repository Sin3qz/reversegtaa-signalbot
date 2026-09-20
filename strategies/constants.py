# ============================================================================
#  reverse-GTAA — Mean-Reversion-Sleeve, 3x-Aequivola (cap3), 3 Bausteine.
#  MONATLICH (ERSTER Handelstag/Monat -- wie levGTAA, von Patrick so gewaehlt;
#  Backtest-Plateau war letzter Tag, erster Tag ~gleichwertig: Korr 0.94, CAGR
#  27.3 statt 29.3, MaxDD -42.3 statt -39.6). Selektion flop2 (2 NIEDRIGSTE SMA-Werte).
#  Ranking SMA110/175 (nur Rangfolge, Vorzeichen egal). Rebound-Confirm 1+2+3M
#  (Oe der 1M/2M/3M-Returns > 0, sonst Slot -> Cash). N=2 gleichgewichtet.
#  Verifiziert (v6): CAGR 29.3 / Sortino 1.07 / MaxDD -39.6. Dekorrelierter Sleeve,
#  NICHT eigenstaendiges Kern-Investment.
# ============================================================================
STRAT_NAME = "reverse-GTAA (Mean-Reversion-Sleeve, 3x)"
STRAT_ASCII = "reverseGTAA"
STRAT_KEY  = "reversegtaa"
REBALANCE_LABEL = "erster Handelstag des Monats"
SIGNAL_CURRENCY_NOTE = "Signale auf zuverlaessigen USD-1x-Kursen (Yahoo); kein Xetra-Lag (B1)."
INFO_FOOTER = ("3x-ETNs: Pfad-/Emittentenrisiko. Dekorrelierter Sleeve, kein Kern-Invest. "
               "KEINE ANLAGEBERATUNG.")
NTFY_MODE = "monthly"         # ntfy am Monatsletzten UND Monatsersten (du waehlst den Handelstag)
NOTIFY_DAYS = ["monthly_last", "monthly_first"]

ASSETS = {
 "NASDAQ100": dict(ticker="QQQ", leverage=3.0, display="Nasdaq 100",
                   product="WisdomTree NASDAQ 100 3x", isin="IE00BLRPRL42"),
 "EM":        dict(ticker="EEM", leverage=2.4, display="Emerging Markets",
                   product="iShares Core MSCI EM IMI 1x (1x-Naeherung)", isin="IE00BKM4GZ66"),
 "GOLD":      dict(ticker="GLD", leverage=3.0, display="Gold",
                   product="WisdomTree Gold 3x", isin="IE00B8HGT870"),
}
CFG = dict(mode="reverse", rebalance="monthly_first", cooldown_days=0,
           S=110, L=175, N=2, lookbacks=(1,3,6,9), rebound_months=(1,2,3),
           pick="flop", weights=None, try_count=3)
