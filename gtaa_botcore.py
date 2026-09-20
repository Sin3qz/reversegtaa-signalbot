#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GTAA-Bot-Kern (strategie-agnostisch, LIVE).  Reine, testbare Funktionen ohne I/O.
Deckt alle drei GTAA-Bots ab, gesteuert ueber ein cfg-dict (aus constants.py):

  mode           "gtaa"  (1x/lev: Top-N nach Momentum, Trend-Gate, Tilt, Cash-Fallback)
                 "reverse" (flop-N nach SMA-Rang + Rebound-Confirm 1+2+3M)
  rebalance      "cooldown"       (1xGTAA: taegliche Entscheidung, Full-Freeze N Handelstage)
                 "monthly_first"  (levGTAA: erster Handelstag/Monat)
                 "monthly_last"   (reverseGTAA: letzter Handelstag/Monat)

Alle Signale auf 1x-USD-Kursen, Entscheidung von gestern wirkt heute (kein Look-Ahead).
Reproduziert exakt den unabhaengig verifizierten v6-Backtest (siehe tests/).
"""
import numpy as np
import pandas as pd

MONTH_DAYS = {1: 21, 2: 42, 3: 63, 6: 126, 9: 189, 12: 252}


# ----------------------------------------------------------------------------
#  Indikatoren pro Asset
# ----------------------------------------------------------------------------
def per_asset_indicators(closes, S, L, lookbacks, trend_mode):
    """closes: DataFrame (Spalten = Assets). Gibt dict von DataFrames zurueck."""
    out = {"sma_l": {}, "sma_s": {}, "trend": {}, "mom": {}, "margin": {},
           "rank_val": {}, "rebound": {}}
    for a in closes.columns:
        P = closes[a]
        sma_l = P.rolling(L).mean()
        sma_s = P if S <= 1 else P.rolling(S).mean()
        if trend_mode == "price":
            trend = P > sma_l
        elif trend_mode == "smax":
            trend = sma_s > sma_l
        else:  # both
            trend = (P > sma_l) & (sma_s > sma_l)
        mom = sum(P / P.shift(MONTH_DAYS[m]) - 1 for m in lookbacks)
        out["sma_l"][a] = sma_l
        out["sma_s"][a] = sma_s
        out["trend"][a] = trend
        out["mom"][a] = mom
        out["margin"][a] = P / sma_l - 1.0
        out["rank_val"][a] = sma_s / sma_l - 1.0                       # reverse: SMA-Rangwert
        out["rebound"][a] = None                                       # gefuellt unten
    return {k: (pd.DataFrame(v) if v and isinstance(next(iter(v.values())), pd.Series) else v)
            for k, v in out.items()}


def rebound_confirm(closes, months):
    """Ø der 1M/2M/3M-Returns je Asset (reverse Rebound-Confirm)."""
    return pd.DataFrame({a: sum(closes[a] / closes[a].shift(MONTH_DAYS[m]) - 1 for m in months) / len(months)
                         for a in closes.columns})


# ----------------------------------------------------------------------------
#  Rebalancing-Tage
# ----------------------------------------------------------------------------
def rebalance_flags(index, mode, live=False):
    """Rebalancing-Tage. live=True korrigiert den JUENGSTEN Tag kalender-genau:
    bei 'monthly_last' ist der letzte vorliegende Tag NUR dann ein Rebalancing-
    Tag, wenn die NAECHSTE NYSE-Sitzung in einem anderen Monat liegt (sonst wuerde
    ein unvollstaendiger laufender Monat faelschlich als Monatsende gewertet)."""
    idx = pd.DatetimeIndex(index)
    if mode == "cooldown":
        return np.ones(len(idx), bool)
    per = idx.to_period("M")
    flags = np.zeros(len(idx), bool)
    ser = pd.Series(np.arange(len(idx)), index=per)
    for _, g in ser.groupby(level=0):
        flags[g.iloc[0] if mode == "monthly_first" else g.iloc[-1]] = True
    if live and mode == "monthly_last" and len(idx):
        flags[-1] = _next_session_new_month(idx[-1])   # kalender-genau statt groupby
    return flags


def _next_session_new_month(last_date):
    """True, wenn die naechste NYSE-Handelssitzung nach last_date in einem
    spaeteren Monat liegt (=> last_date ist der letzte Handelstag seines Monats)."""
    last_date = pd.Timestamp(last_date)
    try:
        import pandas_market_calendars as mcal
        sched = mcal.get_calendar("XNYS").schedule(
            start_date=last_date + pd.Timedelta(days=1),
            end_date=last_date + pd.Timedelta(days=8))
        future = [d for d in sched.index if d.date() > last_date.date()]
        if future:
            return future[0].month != last_date.month
        return False
    except Exception:
        # Fallback: naechster Wochentag (ohne Feiertage)
        d = last_date + pd.Timedelta(days=1)
        while d.weekday() >= 5:
            d += pd.Timedelta(days=1)
        return d.month != last_date.month


# ----------------------------------------------------------------------------
#  Zielallokation an einem Entscheidungstag
# ----------------------------------------------------------------------------
def _sig(alloc):
    """Kanonische Signatur einer Allokation (fuer Wechsel-Erkennung)."""
    if not alloc:
        return "CASH"
    return "|".join(f"{a}:{round(w, 4)}" for a, w in sorted(alloc.items()))


def target_gtaa(assets, trend_row, mom_row, N, weights, cash_fill, fallback="concentrate"):
    """fallback='concentrate' (verifiziert): rangiere NUR qualifizierte Assets, Top-N,
       Tilt auf 100% renormiert (bei 1 Asset -> 100%).
    fallback='slotgate' (Dual-Momentum, strikter Cash-Fallback): rangiere ALLE Assets
       nach Momentum, die Top-N sind feste Slots mit Gewicht weights[i]; ein Slot wird
       nur gefuellt, wenn sein Asset qualifiziert (Trend & Mom>0), sonst -> Cash.
       Ergibt z.B. 40/60, 40/0, 0/60 oder Cash (kein Renormieren, kein Nachruecken)."""
    if fallback == "slotgate":
        order = [a for a in assets if pd.notna(mom_row[a])]
        order.sort(key=lambda a: mom_row[a], reverse=True)
        alloc = {}
        for i, a in enumerate(order[:N]):
            if bool(trend_row[a]) and mom_row[a] > 0:
                alloc[a] = float(weights[i])
        return alloc
    ranked = [a for a in assets if bool(trend_row[a]) and pd.notna(mom_row[a]) and mom_row[a] > 0]
    ranked.sort(key=lambda a: mom_row[a], reverse=True)
    cand = ranked[:N]
    if not cand:
        return {}
    if fallback == "halfcash":
        # verifizierte Top-N-Auswahl (mit Promote); N erfuellt -> Tilt, sonst je 1/N + Rest Cash.
        if len(cand) == N and weights is not None:
            w = np.array(weights[:N], float); w = w / w.sum()
        else:
            w = np.array([1.0 / N] * len(cand))          # <N -> je 1/N (kein Renorm) -> Rest Cash
        return {a: float(w[k]) for k, a in enumerate(cand)}
    # fallback == "concentrate" (verifiziert): <N -> auf 100% renormiert
    w = np.array(weights[:len(cand)], float) if weights is not None else np.array([1.0/len(cand)]*len(cand))
    w = w / w.sum()
    return {a: float(w[k]) for k, a in enumerate(cand)}


def target_reverse(assets, rank_row, rebound_row, N, pick, weights):
    valid = [a for a in assets if pd.notna(rank_row[a])]
    valid.sort(key=lambda a: rank_row[a], reverse=(pick == "top"))
    order = valid[:N]
    conf = [a for a in order if pd.notna(rebound_row[a]) and rebound_row[a] > 0]
    if not conf:
        return {}
    if weights is not None and len(conf) == N:
        w = np.array(weights[:N], float); w = w / w.sum()
        return {a: float(w[k]) for k, a in enumerate(conf)}
    return {a: 1.0 / N for a in conf}       # 1/N je bestaetigt, Rest -> Cash


# ----------------------------------------------------------------------------
#  Ganze Allokations-Serie (mit Rebalancing/Cooldown)
# ----------------------------------------------------------------------------
def compute_series(closes, cfg, live=False):
    """Gibt (dates, allocs[list[dict]], cooldowns[list[int]], ind, rebound) zurueck.
    live=True => letzter Tag kalender-genau (monthly_last), fuer den Live-Bot."""
    assets = list(closes.columns)
    ind = per_asset_indicators(closes, cfg["S"], cfg["L"], cfg["lookbacks"], cfg.get("trend_mode", "smax"))
    rebound = rebound_confirm(closes, cfg["rebound_months"]) if cfg["mode"] == "reverse" else None
    trend, mom, rankv = ind["trend"], ind["mom"], ind["rank_val"]
    idx = closes.index
    reb = rebalance_flags(idx, cfg["rebalance"], live=live)

    # Warmup: erst ab genug Historie fuer SMA_L und die tatsaechlich genutzte Rueckschau
    if cfg["mode"] == "reverse":
        need = max(cfg["L"], max(MONTH_DAYS[m] for m in cfg["rebound_months"]))
    else:
        need = max(cfg["L"], max(MONTH_DAYS[m] for m in cfg["lookbacks"]))

    allocs, cds = [], []
    cur = {}; cooldown = 0
    for i in range(len(idx)):
        warm_ok = i >= need
        if cfg["rebalance"] == "cooldown":
            if cooldown > 0:
                cooldown -= 1
                pass_change = False
            else:
                pass_change = True
            if warm_ok and pass_change:
                tgt = target_gtaa(assets, trend.iloc[i], mom.iloc[i], cfg["N"],
                                  cfg.get("weights"), cfg.get("cash_fill", False),
                                  cfg.get("fallback", "concentrate"))
                if _sig(tgt) != _sig(cur):
                    cur = tgt; cooldown = cfg["cooldown_days"]
        else:  # monatlich
            if warm_ok and reb[i]:
                if cfg["mode"] == "reverse":
                    cur = target_reverse(assets, rankv.iloc[i], rebound.iloc[i], cfg["N"],
                                         cfg.get("pick", "flop"), cfg.get("weights"))
                else:
                    cur = target_gtaa(assets, trend.iloc[i], mom.iloc[i], cfg["N"],
                                      cfg.get("weights"), cfg.get("cash_fill", False),
                                      cfg.get("fallback", "concentrate"))
        allocs.append(dict(cur)); cds.append(cooldown)
    return idx, allocs, cds, ind, rebound


def alloc_signature(alloc):
    return _sig(alloc)
