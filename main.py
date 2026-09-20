import traceback
from strategies.runner import run_strategy
from strategies.constants import STRAT_ASCII

try:
    from send_ntfy import send_ntfy
except Exception:
    def send_ntfy(_title, _msg):
        print("send_ntfy module not available.")
        return False


def saveText(text):
    if not text:
        return
    with open("message.txt", "w") as d:
        d.write(text)


def main():
    # signal: None (nur Status), BUY/SELL/SWITCH (Wechsel), HOLD (Monatswechsel o. Aenderung), Error
    signal, _unused, text = run_strategy()
    if text is None:
        print("Skipped")
        return
    saveText(text)

    # ntfy: 1xGTAA nur bei echtem Wechsel; lev/reverse zum Monatswechsel IMMER
    # (auch "HOLD" = keine Aenderung). Titel bewusst ASCII (Header-Zwang).
    if signal in ("BUY", "SELL", "SWITCH", "HOLD"):
        title = {
            "BUY":    f"{STRAT_ASCII}: BUY - neue Allokation",
            "SELL":   f"{STRAT_ASCII}: SELL - raus in Cash",
            "SWITCH": f"{STRAT_ASCII}: SWITCH - Umschichtung",
            "HOLD":   f"{STRAT_ASCII}: Monatswechsel - keine Aenderung",
        }[signal]
        try:
            send_ntfy(title, text)
        except Exception as e:
            print(f"ntfy send raised (ignored): {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error = "".join(traceback.format_exception(e))
        saveText("Error\n\n" + error)
