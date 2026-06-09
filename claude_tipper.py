import os
import json
import time
import anthropic
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ── Konfiguration aus GitHub Secrets ──────────────────────────────────────────
EMAIL       = os.environ["KICKTIPP_EMAIL"]
PASSWORD    = os.environ["KICKTIPP_PASSWORD"]
COMPETITION = os.environ["KICKTIPP_NAME_OF_COMPETITION"]
API_KEY     = os.environ["ANTHROPIC_API_KEY"]


# ── Schritt 1: Claude nach Tipps fragen ───────────────────────────────────────
def get_tips_from_claude(matches: list) -> list:
    if not matches:
        return []

    client = anthropic.Anthropic(api_key=API_KEY)

    spiele_text = "\n".join(
        f"- {m['home']} vs {m['away']}"
        for m in matches
    )

    prompt = f"""Du bist ein Fußball-Experte. Tippe die folgenden WM-Spiele mit genauen Ergebnissen.
Berücksichtige aktuelle Form, Stärke der Teams und WM-Dynamik.

Spiele:
{spiele_text}

Antworte NUR mit einem JSON-Array, ohne Erklärungen und ohne Markdown-Backticks.
Beispiel-Format:
[
  {{"home": "Deutschland", "away": "Brasilien", "home_score": 2, "away_score": 1}}
]"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    # Backticks entfernen falls Claude sie doch verwendet
    raw = raw.replace("```json", "").replace("```", "").strip()
    tips = json.loads(raw)
    return tips


# ── Schritt 2: Chrome starten ─────────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


# ── Schritt 3: Bei Kicktipp einloggen ─────────────────────────────────────────
def login(driver):
    print("🔑 Einloggen bei Kicktipp...")
    driver.get("https://www.kicktipp.de/info/profil/login")
    time.sleep(2)
    driver.find_element(By.NAME, "kennung").send_keys(EMAIL)
    driver.find_element(By.NAME, "passwort").send_keys(PASSWORD)
    driver.find_element(By.NAME, "submitbutton").click()
    time.sleep(3)
    print("✓ Login erfolgreich")


# ── Schritt 4: Offene Spiele auslesen ─────────────────────────────────────────
def get_open_matches(driver) -> list:
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    print(f"📋 Öffne: {url}")
    driver.get(url)
    time.sleep(3)

    matches = []
    rows = driver.find_elements(By.CSS_SELECTOR, "table.tippabgabe tr.datarow")
    print(f"   Gefundene Zeilen: {len(rows)}")

    for row in rows:
        try:
            home = row.find_element(By.CSS_SELECTOR, ".heimmannschaft").text.strip()
            away = row.find_element(By.CSS_SELECTOR, ".gastmannschaft").text.strip()
            inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
            if inputs and not inputs[0].get_attribute("value"):
                matches.append({"home": home, "away": away, "row": row})
                print(f"   + {home} vs {away}")
        except Exception:
            continue

    return matches


# ── Schritt 5: Tipps eintragen ────────────────────────────────────────────────
def enter_tips(driver, matches: list, tips: list) -> int:
    tip_lookup = {
        (t["home"].lower(), t["away"].lower()): t
        for t in tips
    }

    entered = 0
    for match in matches:
        key = (match["home"].lower(), match["away"].lower())
        tip = tip_lookup.get(key)
        if not tip:
            print(f"⚠️  Kein Tipp für: {match['home']} vs {match['away']}")
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
            print(f"❌ Fehler bei {match['home']} vs {match['away']}: {e}")

    return entered


# ── Schritt 6: Speichern ──────────────────────────────────────────────────────
def submit_tips(driver):
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
            )
        )
        btn.click()
        time.sleep(2)
        print("✓ Tipps gespeichert!")
    except Exception as e:
        print(f"❌ Fehler beim Speichern: {e}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("🚀 Kicktipp-Bot startet...")
    driver = create_driver()

    try:
        login(driver)

        matches = get_open_matches(driver)
        if not matches:
            print("ℹ️  Keine offenen Spiele – fertig.")
            return

        print(f"\n🤖 Frage Claude nach {len(matches)} Tipp(s)...")
        tips = get_tips_from_claude(matches)
        print(f"   Claude-Tipps erhalten: {len(tips)}")

        entered = enter_tips(driver, matches, tips)
        print(f"\n✏️  {entered} Tipp(s) eingetragen")

        if entered > 0:
            submit_tips(driver)

    finally:
        driver.quit()
        print("✅ Bot beendet.")


if __name__ == "__main__":
    main()
