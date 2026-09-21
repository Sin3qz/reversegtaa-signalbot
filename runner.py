#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemeinsamer LIVE-Runner fuer die drei GTAA-Bots (1x / lev / reverse).
Strategie-agnostisch: alles Strategie-Spezifische steht in constants.py (CFG + ASSETS).
Mirror der bewaehrten letsgo-Infrastruktur (alle Bugfixes B1-B12/F1-F4).

Vertrag (fuer main.py):  run_strategy() -> (signal, None, text)
    signal in ("BUY","SELL","SWITCH") -> echter Handelswechsel HEUTE -> ntfy
    signal = None  -> nur Status (kein ntfy) ;  "Error" -> Fehlertext
"""
import os, json, time
import numpy as np
import pandas as pd

from .constants import (STRAT_NAME, STRAT_KEY, ASSETS, CFG, REBALANCE_LABEL,
                        SIGNAL_CURRENCY_NOTE, INFO_FOOTER)
from . import gtaa_botcore as B

STATUS_FILE = f"status_{STRAT_KEY}.json"
TICKERS = {a: meta["ticker"] for a, meta in ASSETS.items()}
ASSET_LIST = list(ASSETS.keys())


# ==========================================================================
#  DATEN
# ==========================================================================
def _download_close(ticker):
    import yahooquery as yq
    df = yq.Ticker(ticker).history(period="max", adj_ohlc=True, adj_timezone=False)
    date_level = pd.Index([str(x) for x in df.index.get_level_values("date")])
    colon = date_level.str.contains(":")
    df.index = pd.to_datetime(date_level.where(~colon, date_level.str.split(" ").str[0]))
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    y = pd.Timestamp.now(tz="Europe/Berlin").date() - pd.Timedelta(days=1)
    return close[close.index.date <= y]


def _fetch(ticker):
    for attempt in range(CFG.get("try_count", 3)):
        try:
            s = _download_close(ticker)
            if s is not None and not s.empty:
                return s
        except Exception as e:
            print(f"({attempt+1}) Download {ticker} failed: {e}")
            time.sleep(2)
    raise RuntimeError(f"Konnte {ticker} nicht laden.")


def _load_closes():
    """Alle Basket-Assets in USD laden. EUR-Assets (meta['fx']) werden ×FX nach USD
    konvertiert. Ausrichtung auf das NYSE-Handelstags-Gitter des Referenz-Assets
    mit Forward-Fill (B1: ein evtl. um 1 Tag verspaeteter .DE-Kurs verzoegert NICHT
    das ganze Signal, sondern nutzt schlimmstenfalls den Vortages-Wert dieses einen
    Bausteins — statt per Schnittmenge den ganzen Tag zu verlieren)."""
    fx_cache = {}
    raw = {}
    for asset, meta in ASSETS.items():
        s = _fetch(meta["ticker"])
        fx = meta.get("fx")
        if fx:                                   # EUR-Reihe -> USD
            if fx not in fx_cache:
                fx_cache[fx] = _fetch(fx)
            s = (s * fx_cache[fx].reindex(s.index).ffill()).dropna()
        raw[asset] = s
    # Referenz-Gitter = Handelstage des ersten (USD/NYSE-)Assets
    ref = ASSET_LIST[0]
    grid = raw[ref].index.sort_values()
    out = {}
    for a in ASSET_LIST:
        out[a] = raw[a].reindex(grid).ffill(limit=5)
    return pd.DataFrame(out).dropna(how="any")


# ==========================================================================
#  FRISCHE (kalender-genau, NYSE)  — B9
# ==========================================================================
def _expected_session_date():
    yday = pd.Timestamp.now(tz="Europe/Berlin").date() - pd.Timedelta(days=1)
    try:
        import pandas_market_calendars as mcal
        sched = mcal.get_calendar("XNYS").schedule(
            start_date=yday - pd.Timedelta(days=20), end_date=yday)
        if len(sched):
            return sched.index[-1].date()
    except Exception as e:
        print(f"NYSE-Kalender-Fallback: {e}")
    d = pd.Timestamp(yday)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d.date()


# ==========================================================================
#  ANZEIGE-HILFEN
# ==========================================================================
def _lev_tag(a):
    m = ASSETS[a]
    return f"{m['leverage']}x" if m["leverage"] != 1 else "1x"


def _alloc_lines(alloc):
    """Gehaltene Allokation — nur Asset + Hebel + %, KEINE konkreten ETFs/ISINs."""
    if not alloc:
        return ["\U0001F4B5 CASH — 100% nicht investiert"]
    lines = ["\U0001F4C8 Gehalten:"]
    tot = 0.0
    for a, w in sorted(alloc.items(), key=lambda kv: -kv[1]):
        tot += w
        lines.append(f"   • {int(round(w*100)):>3d}%  {ASSETS[a]['display']} ({_lev_tag(a)})")
    cash = 1.0 - tot
    if cash > 0.005:                                   # teil-investiert -> Cash-Rest
        lines.append(f"   • {int(round(cash*100)):>3d}%  Cash (Fallback)")
    return lines


def _col(s, w):
    s = str(s)
    return s + " " * max(0, w - len(s))


def _asset_detail_lines(alloc, ind, rebound, i):
    """Kompakte, monospaced Signaltabelle (Discord-Codeblock). Rangbestimmende
    Spalte LINKS: GTAA=Momentum, reverse=SMA110/175. SMA-Werte als ABSOLUTE %-Zahlen."""
    sel = set(alloc.keys())
    rows = []
    if CFG["mode"] == "reverse":
        rankv = ind["rank_val"]; S, L = CFG["S"], CFG["L"]
        valid = [a for a in ASSET_LIST if pd.notna(rankv[a].iloc[i])]
        order = sorted(valid, key=lambda a: rankv[a].iloc[i])       # aufsteigend = flop links
        flop_set = set(order[:CFG["N"]])
        head = [_col("Baustein", 18), _col(f"SMA{S}/{L}", 11), _col("Rebound", 11), "Status"]
        for a in order:
            rv = rankv[a].iloc[i]; rb = rebound[a].iloc[i]
            if a in sel:
                w = alloc[a]; status = f"HALT {int(round(w*100))}%"
            elif a in flop_set:
                status = "Flop2, Rebound<=0 -> Cash"
            else:
                status = "kein Flop2"
            rows.append([_col(ASSETS[a]['display'], 18), _col(_fmt_pct(rv), 11),
                         _col(_fmt_pct(rb), 11), status])
    else:
        mom = ind["mom"]; rankv = ind["rank_val"]; S, L = CFG["S"], CFG["L"]
        order = sorted(ASSET_LIST, key=lambda a: mom[a].iloc[i] if pd.notna(mom[a].iloc[i]) else -1e9, reverse=True)
        head = [_col("Baustein", 18), _col("Momentum", 11), _col(f"SMA{S}/{L}", 11), "Status"]
        for a in order:
            mv = mom[a].iloc[i]; rv = rankv[a].iloc[i]
            tr = bool(ind["trend"][a].iloc[i]) if pd.notna(ind["trend"][a].iloc[i]) else False
            elig = tr and (mv == mv) and mv > 0
            if a in sel:
                w = alloc[a]; status = f"HALT {int(round(w*100))}%"
            elif elig:
                status = "qualifiziert"
            else:
                status = "raus (Trend/Mom)"
            rows.append([_col(ASSETS[a]['display'], 18), _col(_fmt_pct(mv), 11),
                         _col(_fmt_pct(rv), 11), status])
    out = ["```", "".join(head)] + ["".join(r) for r in rows] + ["```"]
    return out


def _change_type(prev_sig, cur_sig):
    if prev_sig == cur_sig:
        return None
    if cur_sig == "CASH":
        return "SELL"
    if prev_sig == "CASH":
        return "BUY"
    return "SWITCH"


def _fmt_pct(x):
    return f"{x*100:+.1f}%" if x == x else "n/a"


def _de(d):
    try:
        return pd.to_datetime(d).strftime("%d.%m.%Y")
    except Exception:
        return str(d)


def _build_message(alloc, cooldown, ind, rebound, idx, closes, freshness, stale,
                   change, next_reb_date):
    i = len(idx) - 1
    lines = []
    if change == "BUY":
        lines += ["🟢 BUY — NEU INVESTIERT", ""]
    elif change == "SELL":
        lines += ["🔴 SELL — RAUS IN CASH", ""]
    elif change == "SWITCH":
        lines += ["🔄 UMSCHICHTUNG — neue Allokation", ""]

    lines += [f"📊 {STRAT_NAME}"]
    lines += _alloc_lines(alloc)

    # Rebalancing-/Cooldown-Info
    if CFG["rebalance"] == "cooldown":
        lines.append(f"({cooldown} Cooldown-Handelstage verbleibend)")
    else:
        lines.append(f"Nächstes Rebalancing: {_de(next_reb_date)} ({REBALANCE_LABEL})")

    # Handelsfrei-Hinweis
    last_dt = idx[-1].date()
    if (not stale) and last_dt < (pd.Timestamp.now(tz='Europe/Berlin').date() - pd.Timedelta(days=1)):
        lines.append(f"ℹ️ Kein neuer US-Handelstag seit {last_dt.strftime('%d.%m.')} (Wochenende/Feiertag)")

    # Signal-Detail je Asset
    lines += ["", "Signale je Baustein (USD, 1x-Kurse):"]
    lines += _asset_detail_lines(alloc, ind, rebound, i)

    lines += ["", f"Kursstand: {_de(idx[-1])}"]
    if stale:
        lines += ["", "⚠️ Kursdaten evtl. veraltet — ein erwarteter US-Handelstag fehlt. "
                      "Der Bot versucht es automatisch erneut; bitte pruefen, falls die Warnung bleibt."]
    lines += ["", SIGNAL_CURRENCY_NOTE, INFO_FOOTER]
    return "\n".join(lines)


# ==========================================================================
#  MONATS-NOTIFY (levGTAA / reverseGTAA): ntfy zum Monatswechsel IMMER
# ==========================================================================
NOTIFY_FILE = f"notify_state_{STRAT_KEY}.json"
try:
    from .constants import NTFY_MODE, NOTIFY_DAYS
except Exception:
    NTFY_MODE, NOTIFY_DAYS = "change", []
KINDLBL = {"monthly_first": "Monatserster Handelstag", "monthly_last": "Monatsletzter Handelstag"}


def _load_notify():
    try:
        with open(NOTIFY_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_notify(d):
    try:
        with open(NOTIFY_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception as e:
        print(f"notify-state write (ignoriert): {e}")


def _live_target(ind, rebound, i):
    """Zielallokation ZUM STICHTAG i (frische Rebalancing-Entscheidung, nicht die
    gehaltene Monats-Allokation) — genau das, was du an dem Handelstag umsetzen wuerdest."""
    if CFG["mode"] == "reverse":
        return B.target_reverse(ASSET_LIST, ind["rank_val"].iloc[i], rebound.iloc[i],
                                CFG["N"], CFG.get("pick", "flop"), CFG.get("weights"),
                                CFG.get("fallback", "cash"))
    return B.target_gtaa(ASSET_LIST, ind["trend"].iloc[i], ind["mom"].iloc[i],
                         CFG["N"], CFG.get("weights"), CFG.get("cash_fill", False),
                         CFG.get("fallback", "concentrate"))


def _is_notify_day(idx, i, kind):
    if kind == "monthly_first":
        return i == 0 or (idx[i].month != idx[i-1].month) or (idx[i].year != idx[i-1].year)
    if kind == "monthly_last":
        return B._next_session_new_month(idx[i])
    return False


def _build_message_monthly(live, ind, rebound, idx, kind, signal, prev_sig, ref_date, stale):
    i = len(idx) - 1
    lbl = KINDLBL.get(kind)
    lines = []
    if kind is None:                                    # normaler Tag (kein Meldetag)
        lines += [f"📊 {STRAT_NAME} — Tagesstatus (kein ntfy-Meldetag)"]
    elif signal in ("BUY", "SELL", "SWITCH"):
        head = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "SWITCH": "🔄 UMSCHICHTUNG"}[signal]
        lines += [f"{head} — Änderung ggü. Vormonat ({lbl})", ""]
    elif prev_sig is None:
        lines += [f"🟢 ERSTMELDUNG ({lbl})", ""]
    else:
        lines += [f"⚪ KEINE ÄNDERUNG zum Vormonat ({lbl})", ""]
    if kind is not None:
        lines += [f"📊 {STRAT_NAME}"]
    complbl = "Aktuelle Flop-2" if CFG["mode"] == "reverse" else "Aktuelle Top-2"
    lines += [f"{complbl}-Zusammensetzung ({_de(idx[-1])}):"]
    lines += _alloc_lines(live)
    if kind is not None and ref_date:
        lines.append(f"(Bezug: {lbl} des Vormonats, {_de(ref_date)})")
    if kind is None and NOTIFY_DAYS:
        nd = " & ".join("1. Handelstag" if k == "monthly_first" else "letzter Handelstag" for k in NOTIFY_DAYS)
        lines.append(f"(ntfy-Meldung jeweils am: {nd} des Monats)")
    lines += ["", "Signale je Baustein (USD, 1x-Kurse):"]
    lines += _asset_detail_lines(live, ind, rebound, i)
    lines += ["", f"Kursstand: {_de(idx[-1])}"]
    if stale:
        lines += ["", "⚠️ Kursdaten evtl. veraltet — ein erwarteter US-Handelstag fehlt. Retry laeuft; bitte pruefen."]
    lines += ["", SIGNAL_CURRENCY_NOTE, INFO_FOOTER]
    return "\n".join(lines)


# ==========================================================================
#  HAUPTFUNKTION
# ==========================================================================
def run_strategy(closes=None):
    if closes is None:
        try:
            closes = _load_closes()
        except Exception as e:
            return ("Error", None, f"{STRAT_NAME}: Daten konnten nicht geladen werden: {e}")

    exp = _expected_session_date()
    freshness = {a: {"last": closes[a].dropna().index[-1].date().isoformat(),
                     "fresh": bool(closes[a].dropna().index[-1].date() >= exp)}
                 for a in ASSET_LIST}
    stale = not all(f["fresh"] for f in freshness.values())

    idx, allocs, cds, ind, rebound = B.compute_series(closes, CFG, live=True)
    sigs = [B.alloc_signature(a) for a in allocs]
    i = len(idx) - 1
    next_reb = _next_rebalance_date(idx[-1]) if CFG["rebalance"] != "cooldown" else None

    if NTFY_MODE == "monthly":
        # ---- LIVE-Zielallokation + Monatswechsel-Meldung ----
        live = _live_target(ind, rebound, i); live_sig = B.alloc_signature(live)
        # Dashboard/Status = GEHALTENE Allokation aus dem Rebalancing-Plan
        # (reverse: monatsletzter; lev: monatserster). ntfy nutzt 'live' pro Meldetag.
        display_alloc, cur_cd = allocs[-1], 0
        state = _load_notify()
        fired_kind = None; prev_sig = None; ref_date = None; signal = None
        for kind in NOTIFY_DAYS:
            if _is_notify_day(idx, i, kind):
                prev = state.get(kind, {}); prev_sig = prev.get("sig"); ref_date = prev.get("date")
                fired_kind = kind
                state[kind] = {"date": idx[i].date().isoformat(), "sig": live_sig}
                break
        if fired_kind is not None:
            _save_notify(state)
            if prev_sig is None:
                signal = "HOLD"                                  # Erstmeldung (kein Fehl-BUY, B5)
            elif prev_sig != live_sig:
                signal = _change_type(prev_sig, live_sig) or "SWITCH"
            else:
                signal = "HOLD"                                  # keine Aenderung -> trotzdem ntfy
        text = _build_message_monthly(live, ind, rebound, idx, fired_kind, signal, prev_sig, ref_date, stale)
        change = signal
    else:
        # ---- 1xGTAA Cooldown: gehaltene Allokation, Wechsel aus letzten 2 Zeilen ----
        display_alloc, cur_cd = allocs[-1], cds[-1]
        prev_sig = sigs[-2] if len(sigs) >= 2 else sigs[-1]
        change = _change_type(prev_sig, sigs[-1])                # None/BUY/SELL/SWITCH
        text = _build_message(display_alloc, cur_cd, ind, rebound, idx, closes, freshness, stale, change, next_reb)

    # ---- History (Transparenz + Dashboard) ----
    try:
        with open(f"history_{STRAT_KEY}.txt", "w") as f:
            f.write("date,allocation,cooldown\n")
            for k in range(len(idx)):
                if sigs[k] == "CASH" and k < 200:
                    continue
                f.write(f"{idx[k].date()},{sigs[k]},{cds[k]}\n")
    except Exception as e:
        print(f"History-Schreibfehler (ignoriert): {e}")

    # ---- status.json ----
    status = {
        "strategy": STRAT_NAME, "key": STRAT_KEY,
        "updated": pd.Timestamp.now(tz="Europe/Berlin").isoformat(),
        "rebalance": CFG["rebalance"], "rebalanceLabel": REBALANCE_LABEL,
        "ntfyMode": NTFY_MODE, "notifyDays": NOTIFY_DAYS,
        "asOf": idx[-1].date().isoformat(), "needsRetry": bool(stale),
        "changedToday": bool(change in ("BUY", "SELL", "SWITCH")),
        "changeType": change, "cooldown": int(cur_cd),
        "nextRebalance": (next_reb.isoformat() if next_reb is not None else None),
        "allocation": [{"asset": a, "display": ASSETS[a]["display"], "weight": round(w, 4),
                        "leverage": ASSETS[a]["leverage"], "product": ASSETS[a]["product"],
                        "isin": ASSETS[a].get("isin", "")}
                       for a, w in sorted(display_alloc.items(), key=lambda kv: -kv[1])] or
                      [{"asset": "CASH", "display": "Cash", "weight": 1.0, "leverage": 1, "product": "—", "isin": ""}],
        "signals": _signal_snapshot(ind, rebound, i),
        "freshness": freshness, "history": _history_tail(idx, sigs, 400),
    }
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"status.json-Schreibfehler (ignoriert): {e}")

    return change, None, text


# ==========================================================================
#  Hilfsfunktionen
# ==========================================================================
def _next_rebalance_date(last_date):
    """Naechster Rebalancing-Tag (erster/letzter NYSE-Handelstag des kommenden bzw.
    laufenden Monats) — reine Info fuer die Anzeige."""
    last_date = pd.Timestamp(last_date)
    try:
        import pandas_market_calendars as mcal
        cal = mcal.get_calendar("XNYS")
        sched = cal.schedule(start_date=last_date, end_date=last_date + pd.Timedelta(days=70))
        days = [d.date() for d in sched.index if d.date() > last_date.date()]
        if CFG["rebalance"] == "monthly_first":
            for d in days:
                if d.month != last_date.month or d.year != last_date.year:
                    return d
        else:  # monthly_last
            # letzter Handelstag des laufenden Monats, sonst des naechsten
            cur_month = [d for d in days if d.month == last_date.month and d.year == last_date.year]
            if cur_month:
                return cur_month[-1]
            nxt = [d for d in days if (d.month, d.year) != (last_date.month, last_date.year)]
            if nxt:
                m0 = (nxt[0].month, nxt[0].year)
                return [d for d in nxt if (d.month, d.year) == m0][-1]
    except Exception as e:
        print(f"next-rebalance-Fallback: {e}")
    return None


def _signal_snapshot(ind, rebound, i):
    """Pro-Baustein-Kennzahlen fuer Dashboard. rankValue = SMA_kurz/SMA_lang-1
    (bei 1x/lev = SMA8/150-Abstand, entscheidet den Trend; bei reverse = SMA110/175-
    Rangwert). Immer mitgeliefert, damit das Dashboard ABSOLUTE SMA-Werte zeigen kann."""
    out = {}
    for a in ASSET_LIST:
        rec = {"momentum": _num(ind["mom"][a].iloc[i]),
               "trend": bool(ind["trend"][a].iloc[i]) if pd.notna(ind["trend"][a].iloc[i]) else None,
               "marginSMA": _num(ind["margin"][a].iloc[i]),
               "rankValue": _num(ind["rank_val"][a].iloc[i]),
               "display": ASSETS[a]["display"], "leverage": ASSETS[a]["leverage"]}
        if CFG["mode"] == "reverse":
            rec["rebound"] = _num(rebound[a].iloc[i]) if rebound is not None else None
        out[a] = rec
    return out


def _history_tail(idx, sigs, n):
    tail = []
    for k in range(max(0, len(idx) - n), len(idx)):
        tail.append({"date": idx[k].date().isoformat(), "allocation": sigs[k]})
    return tail


def _num(x):
    try:
        return round(float(x), 6) if x == x else None
    except Exception:
        return None
