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

WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]


# ── Claude: Spieltipps holen ──────────────────────────────────────────────────
def get_tips_from_claude(matches):
    if not matches:
        return []

    client = anthropic.Anthropic(api_key=API_KEY)
    spiele_text = "\n".join(f"- {m['home']} vs {m['away']}" for m in matches)

    prompt = (
        "Du bist ein Fußball-Tipp-Experte für die WM 2026.\n\n"
        "## Spiele zum Tippen\n"
        + spiele_text +
        "\n\n## Deine Analysestrategie\n"
        "1. Suche aktuelle Verletzungsnews und Sperren der Stammspieler\n"
        "2. Suche aktuelle Buchmacher-Quoten für diese Spiele\n"
        "3. Berücksichtige die bisherige WM-Performance der Teams\n"
        "4. Beachte den bisherigen Torschnitt dieser WM\n"
        "5. Setze grundsätzlich auf den Favoriten\n"
        "6. Tippe präzise Ergebnisse - nicht nur 1:0\n\n"
        "## Punktesystem\n"
        "Genaues Ergebnis = 4 Punkte, Tordifferenz = 3 Punkte, Tendenz = 2 Punkte\n"
        "Strategie: Lieber präzise tippen als zu vorsichtig sein!\n\n"
        "## Ausgabe\n"
        "NUR JSON-Array, keine Erklärungen, keine Backticks:\n"
        '[{"home":"Teamname","away":"Teamname","home_score":2,"away_score":0,'
        '"confidence":"hoch","reasoning":"Kurze Begruendung"}]'
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        tools=WEB_SEARCH_TOOL,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    tips = json.loads(raw[start:end])

    print("\n🤖 Claude's Tipps:")
    for t in tips:
        print(f"   {t['home']} {t['home_score']}:{t['away_score']} {t['away']}"
              f" [{t.get('confidence','?')}] – {t.get('reasoning','')}")
    return tips


# ── Chrome starten ────────────────────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )


# ── Login ─────────────────────────────────────────────────────────────────────
def login(driver):
    print("🔑 Einloggen...")
    driver.get("https://www.kicktipp.de/info/profil/login")
    time.sleep(2)
    driver.find_element(By.NAME, "kennung").send_keys(EMAIL)
    driver.find_element(By.NAME, "passwort").send_keys(PASSWORD)
    driver.find_element(By.NAME, "submitbutton").click()
    time.sleep(3)
    print("✓ Login erfolgreich")


# ── Offene Spiele auslesen ────────────────────────────────────────────────────
def get_open_matches(driver):
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    print(f"\n📋 Öffne: {url}")
    driver.get(url)
    time.sleep(3)

    matches = []
    rows = driver.find_elements(
        By.CSS_SELECTOR, "table#tippabgabeSpiele tr.datarow"
    )
    print(f"   Gefundene Zeilen: {len(rows)}")

    for row in rows:
        try:
            # Heimteam in td.col1, Gastteam in td.col2
            home = row.find_element(By.CSS_SELECTOR, "td.col1").text.strip()
            away = row.find_element(By.CSS_SELECTOR, "td.col2").text.strip()

            # Nur Spiele ohne bereits eingetragenen Tipp
            inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
            if home and away and inputs and not inputs[0].get_attribute("value"):
                matches.append({"home": home, "away": away, "row": row})
                print(f"   + {home} vs {away}")
        except Exception as e:
            print(f"   ⚠️  Zeile übersprungen: {e}")
            continue

    return matches


# ── Tipps eintragen ───────────────────────────────────────────────────────────
def enter_tips(driver, matches, tips):
    tip_lookup = {(t["home"].lower(), t["away"].lower()): t for t in tips}
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


# ── Tipps speichern ───────────────────────────────────────────────────────────
def submit_tips(driver):
    print("\n💾 Speichere Tipps...")
    try:
        # Kicktipp verwendet einen Submit-Button mit name="submitbutton"
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "submitbutton"))
        )
        btn.click()
        time.sleep(3)
        print("✓ Tipps erfolgreich gespeichert!")
    except Exception:
        # Fallback: generischer Submit-Button
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
                )
            )
            btn.click()
            time.sleep(3)
            print("✓ Tipps gespeichert (Fallback)!")
        except Exception as e:
            print(f"❌ Speichern fehlgeschlagen: {e}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("🚀 Kicktipp-Bot startet...")
    driver = create_driver()

    try:
        login(driver)

        matches = get_open_matches(driver)

        if not matches:
            print("\nℹ️  Keine offenen Spiele gefunden.")
            return

        print(f"\n🤖 {len(matches)} Spiel(e) gefunden – frage Claude...")
        tips = get_tips_from_claude(matches)

        if not tips:
            print("❌ Keine Tipps von Claude erhalten.")
            return

        print(f"\n✏️  Trage {len(tips)} Tipp(s) ein...")
        entered = enter_tips(driver, matches, tips)
        print(f"   {entered} Tipp(s) eingetragen")

        if entered > 0:
            submit_tips(driver)
        else:
            print("⚠️  Nichts eingetragen, kein Speichern nötig.")

    finally:
        driver.quit()
        print("\n✅ Bot beendet.")


if __name__ == "__main__":
    main()
