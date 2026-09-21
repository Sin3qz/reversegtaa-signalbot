"""
ntfy-Push fuer den LetsGO Signal-Bot.
Wird NUR bei einem echten Signalwechsel (Buy/Sell) aufgerufen.

Kostenlos, kein Account noetig: https://ntfy.sh
Setup:
  1. ntfy-App aufs Handy (Android/iOS) oder https://ntfy.sh im Browser.
  2. In der App das TOPIC abonnieren (der Name aus dem GitHub-Secret NTFY_TOPIC).
  3. GitHub-Secret NTFY_TOPIC = genau dieser Topic-Name.

Sicherheit: Der Topic-Name ist wie ein Passwort — wer ihn kennt, sieht die
Nachrichten. Deshalb ein langer, nicht erratbarer Name (siehe Secret).
"""

import os
import urllib.request


def send_ntfy(title, message):
    """Sendet einen ntfy-Push. Gibt True/False zurueck. Wirft NIE."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("Kein NTFY_TOPIC gesetzt (ntfy uebersprungen).")
        return False

    # `or` faengt auch den leeren String ab (GitHub setzt ein nicht gesetztes
    # Secret als "" in die Umgebung, nicht als 'nicht vorhanden').
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"
    try:
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            method="POST",
        )
        # Header muessen ASCII sein -> title bewusst ASCII halten (siehe main.py).
        req.add_header("Title", title)
        req.add_header("Priority", "high")
        req.add_header("Tags", "rotating_light")
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"ntfy OK ({resp.status}) -> {url}")
        return True
    except Exception as e:
        print(f"ntfy failed: {e}")
        return False


if __name__ == "__main__":
    # Manueller Test (setze vorher NTFY_TOPIC in der Umgebung):
    send_ntfy("LetsGO: TEST", "ntfy Test-Nachricht ✅")
