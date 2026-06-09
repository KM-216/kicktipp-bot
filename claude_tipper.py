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

    prompt = f"""Du bist ein hochspezialisierter Fußball-Tipp-Experte für die WM 2026.

## Deine Aufgabe
Tippe die folgenden Spiele mit genauen Ergebnissen (Heimtore : Gasttore).

## Spiele
{spiele_text}

## Deine Analysestrategie (in dieser Reihenfolge)

### 1. Aktuelle Nachrichten abrufen
Suche für jedes Spiel nach:
- Verletzungen und Sperren der Stammspieler (besonders Stürmer, Torhüter, Kapitäne)
- Aktuellen Buchmacher-Quoten (Sieg/Unentschieden/Niederlage sowie Over/Under 2.5 Tore)
- Form der letzten 3 Spiele beider Teams in dieser WM

### 2. WM-Turnierkontext berücksichtigen
- Analysiere den bisherigen Torschnitt dieser WM (viele Tore pro Spiel vs. wenige)
- Beachte Muster: Welche Teams spielen offensiv, welche defensiv?
- Gruppenphase vs. K.O.-Runde beeinflusst die Risikobereitschaft der Teams

### 3. Tipp-Philosophie
- Setze grundsätzlich auf den Favoriten
- Bei klaren Favoriten: tippe einen deutlicheren Sieg (z.B. 2:0 oder 3:1 statt nur 1:0)
- Riskiere kalkuliert wenn Quoten oder Form es rechtfertigen
- Unentschieden nur tippen wenn es wirklich ausgeglichen ist

### 4. Punktesystem-Optimierung
Das Punktesystem lautet:
- Nur Tendenz richtig (Sieg/Unentschieden): 2 Punkte
- Tendenz + Tordifferenz richtig: 3 Punkte  
- Genaues Ergebnis richtig: 4 Punkte
- Bei Unentschieden: kein Tordifferenz-Bonus, nur Tendenz (2P) oder genaues Ergebnis (4P)

Strategie daraus: Ein genaues Ergebnis bringt doppelt so viele Punkte wie nur die Tendenz.
Lieber präzise tippen als zu vorsichtig sein. Bei Favoriten lohnt sich ein konkretes Ergebnis
mehr als ein vorsichtiges 1:0.

## Ausgabe
Antworte NUR mit einem JSON-Array, ohne Erklärungen, ohne Markdown-Backticks.
Format:
[
  {{
    "home": "Teamname genau wie oben",
    "away": "Teamname genau wie oben", 
    "home_score": 2,
    "away_score": 0,
    "confidence": "hoch",
    "reasoning": "Kurze Begründung in einem Satz"
  }}
]

Wichtig: Die Teamnamen müssen exakt mit den oben genannten übereinstimmen."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Alle Text-Blöcke zusammenführen
    raw = ""
    for block in message.content:
        if block.type == "text":
            raw += block.text

    raw = raw.strip().replace("```json", "").replace("```", "").strip()

    # JSON extrahieren falls noch Text darum herum ist
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    tips = json.loads(raw)

    # Begründungen ausgeben
    print("\n🤖 Claude's Tipps:")
    for t in tips:
        confidence = t.get("confidence", "?")
        reasoning = t.get("reasoning", "")
        print(f"   {t['home']} {t['home_score']}:{t['away_score']} {t['away']} [{confidence}] – {reasoning}")

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

    # HTML ausgeben für Debugging
    page_source = driver.page_source
    print(f"   Seitengröße: {len(page_source)} Zeichen")

    matches = []

    # Verschiedene Selektoren versuchen
    selectors = [
        ("table.tippabgabe tr.datarow", ".heimmannschaft", ".gastmannschaft"),
        ("tr.datarow", ".heimmannschaft", ".gastmannschaft"),
        ("table.ranking tr", "td:nth-child(2)", "td:nth-child(4)"),
    ]

    for row_sel, home_sel, away_sel in selectors:
        rows = driver.find_elements(By.CSS_SELECTOR, row_sel)
        if rows:
            print(f"   Selektor '{row_sel}' gefunden: {len(rows)} Zeilen")
            for row in rows:
                try:
                    home = row.find_element(By.CSS_SELECTOR, home_sel).text.strip()
                    away = row.find_element(By.CSS_SELECTOR, away_sel).text.strip()
                    inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
                    if home and away and inputs and not inputs[0].get_attribute("value"):
                        matches.append({"home": home, "away": away, "row": row})
                        print(f"   + {home} vs {away}")
                except Exception:
                    continue
            if matches:
                break

    if not matches:
        # Alle input-Felder auf der Seite ausgeben für Debugging
        all_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
        print(f"   Gefundene input-Felder gesamt: {len(all_inputs)}")
        all_rows = driver.find_elements(By.CSS_SELECTOR, "tr")
        print(f"   Gefundene tr-Elemente gesamt: {len(all_rows)}")

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
            print("ℹ️  Keine offenen Spiele gefunden.")
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
