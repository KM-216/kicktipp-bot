import os
import json
import time
import anthropic
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ── Konfiguration aus GitHub Secrets ──────────────────────────────────────────
EMAIL      = os.environ["KICKTIPP_EMAIL"]
PASSWORD   = os.environ["KICKTIPP_PASSWORD"]
COMPETITION= os.environ["KICKTIPP_NAME_OF_COMPETITION"]
API_KEY    = os.environ["ANTHROPIC_API_KEY"]

# ── Schritt 1: Claude nach Tipps fragen ───────────────────────────────────────
def get_tips_from_claude(matches: list[dict]) -> list[dict]:
    """Fragt Claude nach genauen Ergebnistipps für die übergebenen Spiele."""
    if not matches:
        return []

    client = anthropic.Anthropic(api_key=API_KEY)

    spiele_text = "\n".join(
        f"- {m['home']} vs {m['away']} (Spieltag {m.get('round', '?')}, {m.get('date', '?')})"
        for m in matches
    )

    prompt = f"""Du bist ein Fußball-Experte. Tippe die folgenden WM-Spiele mit genauen Ergebnissen.
Berücksichtige aktuelle Form, Stärke der Teams und WM-Dynamik.

Spiele:
{spiele_text}

Antworte NUR mit einem JSON-Array, ohne weitere Erklärungen, ohne Markdown-Backticks.
Format:
[
  {{"home": "Teamname", "away": "Teamname", "home_score": 2, "away_score": 1}},
  ...
]"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    tips = json.loads(raw)
    return tips


# ── Schritt 2: Kicktipp öffnen und Spiele auslesen ────────────────────────────
def get_open_matches(driver) -> list[dict]:
    """Liest alle noch nicht getippten Spiele aus Kicktipp aus."""
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    driver.get(url)
    time.sleep(3)

    matches = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table.tippabgabe tr.datarow")
        for row in rows:
            try:
                home = row.find_element(By.CSS_SELECTOR, ".heimmannschaft").text.strip()
                away = row.find_element(By.CSS_SELECTOR, ".gastmannschaft").text.strip()
                date = row.find_element(By.CSS_SELECTOR, ".spielzeit").text.strip()
                # Nur Spiele ohne Tipp aufnehmen
                inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
                if inputs and not inputs[0].get_attribute("value"):
                    matches.append({
                        "home": home,
                        "away": away,
                        "date": date,
                        "row": row
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Fehler beim Auslesen der Spiele: {e}")

    return matches


# ── Schritt 3: Tipps in Kicktipp eintragen ────────────────────────────────────
def enter_tips(driver, matches: list[dict], tips: list[dict]):
    """Trägt die Claude-Tipps in die Kicktipp-Eingabefelder ein."""
    # Erstelle ein Lookup-Dict: (heimteam, gastteam) -> tipp
    tip_lookup = {
        (t["home"].lower(), t["away"].lower()): t
        for t in tips
    }

    entered = 0
    for match in matches:
        key = (match["home"].lower(), match["away"].lower())
        tip = tip_lookup.get(key)
        if not tip:
            print(f"Kein Tipp gefunden für: {match['home']} vs {match['away']}")
            continue

        try:
            inputs = match["row"].find_elements(By.CSS_SELECTOR, "input[type='text']")
            if len(inputs) >= 2:
                inputs[0].clear()
                inputs[0].send_keys(str(tip["home_score"]))
                inputs[1].clear()
                inputs[1].send_keys(str(tip["away_score"]))
                print(f"✓ {match['home']} {tip['home_score']}:{tip['away_score']} {match['away']}")
                entered += 1
        except Exception as e:
            print(f"Fehler beim Eintragen von {match['home']} vs {match['away']}: {e}")

    return entered


# ── Schritt 4: Tipps absenden ─────────────────────────────────────────────────
def submit_tips(driver):
    """Klickt den Speichern-Button."""
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'], button[type='submit']"))
        )
        btn.click()
        print("✓ Tipps erfolgreich gespeichert!")
        time.sleep(2)
    except Exception as e:
        print(f"Fehler beim Speichern: {e}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("🚀 Kicktipp-Bot startet...")

    # Chrome im Headless-Modus (kein sichtbares Fenster)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    try:
        # Login
        print("🔑 Einloggen bei Kicktipp...")
        driver.get("https://www.kicktipp.de/info/profil/login")
        time.sleep(2)

        driver.find_element(By.NAME, "kennung").send_keys(EMAIL)
        driver.find_element(By.NAME, "passwort").send_keys(PASSWORD)
        driver.find_element(By.NAME, "submitbutton").click()
        time.sleep(3)

        # Offene Spiele auslesen
        print("📋 Offene Spiele werden geladen...")
        matches = get_open_matches(driver)

        if not matches:
            print("ℹ️  Keine offenen Spiele gefunden.")
            return

        print(f"📌 {len(matches)} Spiel(e) gefunden – frage Claude...")

        # Claude um Tipps bitten
        tips = get_tips_from_claude(matches)
        print(f"🤖 Claude hat {len(tips)} Tipp(s) geliefert")

        # Tipps eintragen
        entered = enter_tips(driver, matches, tips)
        print(f"✏️  {entered} Tipp(s) eingetragen")

        if entered > 0:
            submit_tips(driver)

    finally:
        driver.quit()
        print("✅ Fertig!")


if __name__ == "__main__":
    main()
