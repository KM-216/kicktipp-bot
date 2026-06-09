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
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

# ── Konfiguration aus GitHub Secrets ──────────────────────────────────────────
EMAIL       = os.environ["KICKTIPP_EMAIL"]
PASSWORD    = os.environ["KICKTIPP_PASSWORD"]
COMPETITION = os.environ["KICKTIPP_NAME_OF_COMPETITION"]
API_KEY     = os.environ["ANTHROPIC_API_KEY"]

# ── Alle Teams exakt wie in Kicktipp ──────────────────────────────────────────
TEAMS = [
    "Ägypten", "Algerien", "Argentinien", "Australien", "Belgien",
    "Bosnien-Herzegowina", "Brasilien", "Curaçao", "Deutschland", "DR Kongo",
    "Ecuador", "Elfenbeinküste", "England", "Frankreich", "Ghana", "Haiti",
    "Irak", "Iran", "Japan", "Jordanien", "Kanada", "Kap Verde", "Katar",
    "Kolumbien", "Kroatien", "Marokko", "Mexiko", "Neuseeland", "Niederlande",
    "Norwegen", "Österreich", "Panama", "Paraguay", "Portugal", "Saudi-Arabien",
    "Schottland", "Schweden", "Schweiz", "Senegal", "Spanien", "Südafrika",
    "Südkorea", "Tschechien", "Tunesien", "Türkei", "Uruguay", "USA", "Usbekistan"
]


# ── Claude: Spieltipps ────────────────────────────────────────────────────────
def get_tips_from_claude(matches: list) -> list:
    if not matches:
        return []

    client = anthropic.Anthropic(api_key=API_KEY)
    spiele_text = "\n".join(f"- {m['home']} vs {m['away']}" for m in matches)

    prompt = f"""Du bist ein hochspezialisierter Fußball-Tipp-Experte für die WM 2026.

## Spiele
{spiele_text}

## Analysestrategie
1. Suche aktuelle Verletzungsnews, Buchmacher-Quoten und Form der Teams
2. Berücksichtige den bisherigen Torschnitt dieser WM
3. Setze auf Favoriten, tippe präzise Ergebnisse (nicht nur 1:0)
4. Punktesystem: Genaues Ergebnis = 4 Punkte, Tordifferenz = 3, Tendenz = 2

## Ausgabe
NUR JSON-Array, keine Erklärungen, keine Backticks:
[
  {{
    "home": "Teamname exakt wie oben",
    "away": "Teamname exakt wie oben",
    "home_score": 2,
    "away_score": 0,
    "confidence": "hoch",
    "reasoning": "Kurze Begründung"
  }}
]"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        tools=[{{"type": "web_search_20250305", "name": "web_search"}}],
        messages=[{{"role": "user", "content": prompt}}]
    )

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw += block.text
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    tips = json.loads(raw)
    print("\n🤖 Spieltipps:")
    for t in tips:
        print(f"   {t['home']} {t['home_score']}:{t['away_score']} {t['away']} – {t.get('reasoning','')}")
    return tips


# ── Claude: Bonustipps ────────────────────────────────────────────────────────
def get_bonus_tips_from_claude() -> dict:
    client = anthropic.Anthropic(api_key=API_KEY)
    teams_str = ", ".join(TEAMS)

    prompt = f"""Du bist ein WM 2026 Experte. Beantworte folgende Bonusfragen.

## Verfügbare Teams (exakt diese Schreibweise!)
{teams_str}

## Fragen
1. Welche Mannschaft stellt den Torschützenkönig?
2. Wer erreicht das Halbfinale? (4 Teams)
3. Gruppensieger A bis L
4. Wer wird Weltmeister?

## Analysestrategie
Suche aktuelle WM 2026 Gruppenauslosung, FIFA-Weltrangliste und Favoritenanalysen.

## Ausgabe
NUR JSON, keine Erklärungen, keine Backticks:
{{
  "torschuetzenkoenigsland": "Teamname",
  "halbfinale": ["Team1", "Team2", "Team3", "Team4"],
  "gruppe_A": "Teamname",
  "gruppe_B": "Teamname",
  "gruppe_C": "Teamname",
  "gruppe_D": "Teamname",
  "gruppe_E": "Teamname",
  "gruppe_F": "Teamname",
  "gruppe_G": "Teamname",
  "gruppe_H": "Teamname",
  "gruppe_I": "Teamname",
  "gruppe_J": "Teamname",
  "gruppe_K": "Teamname",
  "gruppe_L": "Teamname",
  "weltmeister": "Teamname"
}}"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        tools=[{{"type": "web_search_20250305", "name": "web_search"}}],
        messages=[{{"role": "user", "content": prompt}}]
    )

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw += block.text
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = raw.find("{{"), raw.rfind("}}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    bonus = json.loads(raw)
    print("\n🏆 Bonustipps:")
    print(f"   Torschützenkönig-Land : {bonus.get('torschuetzenkoenigsland')}")
    print(f"   Halbfinale            : {', '.join(bonus.get('halbfinale', []))}")
    for g in list('ABCDEFGHIJKL'):
        print(f"   Gruppe {g}              : {bonus.get(f'gruppe_{g}')}")
    print(f"   Weltmeister           : {bonus.get('weltmeister')}")
    return bonus


# ── Chrome starten ────────────────────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


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


# ── Bonusfragen eintragen ─────────────────────────────────────────────────────
def enter_bonus_tips(driver, bonus: dict) -> int:
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    driver.get(url)
    time.sleep(3)

    # Alle Zeilen in der Bonusfragen-Tabelle
    rows = driver.find_elements(
        By.CSS_SELECTOR, "table#tippabgabeFragen tr.datarow"
    )
    print(f"\n📝 Bonusfragen-Zeilen gefunden: {len(rows)}")

    halbfinale_index = 0
    filled = 0

    for row in rows:
        try:
            # Fragetext aus col1
            frage = row.find_element(By.CSS_SELECTOR, "td.col1").text.strip().lower()

            # Dropdown in col2
            select_el = row.find_element(By.CSS_SELECTOR, "td.col2 select")
            select = Select(select_el)

            # Bereits befüllt? Überspringen
            current = select.first_selected_option.text.strip()
            if current != "-- Nicht getippt --":
                print(f"   ⏭  Bereits getippt: {frage[:40]} → {current}")
                continue

            value = None
            if "weltmeister" in frage:
                value = bonus.get("weltmeister")
            elif "meisten toren" in frage or "torschützen" in frage:
                value = bonus.get("torschuetzenkoenigsland")
            elif "halbfinale" in frage:
                hf = bonus.get("halbfinale", [])
                if halbfinale_index < len(hf):
                    value = hf[halbfinale_index]
                    halbfinale_index += 1
            elif "gruppe a" in frage:
                value = bonus.get("gruppe_A")
            elif "gruppe b" in frage:
                value = bonus.get("gruppe_B")
            elif "gruppe c" in frage:
                value = bonus.get("gruppe_C")
            elif "gruppe d" in frage:
                value = bonus.get("gruppe_D")
            elif "gruppe e" in frage:
                value = bonus.get("gruppe_E")
            elif "gruppe f" in frage:
                value = bonus.get("gruppe_F")
            elif "gruppe g" in frage:
                value = bonus.get("gruppe_G")
            elif "gruppe h" in frage:
                value = bonus.get("gruppe_H")
            elif "gruppe i" in frage:
                value = bonus.get("gruppe_I")
            elif "gruppe j" in frage:
                value = bonus.get("gruppe_J")
            elif "gruppe k" in frage:
                value = bonus.get("gruppe_K")
            elif "gruppe l" in frage:
                value = bonus.get("gruppe_L")

            if value:
                select.select_by_visible_text(value)
                print(f"   ✓ {frage[:40]} → {value}")
                filled += 1
            else:
                print(f"   ⚠️  Kein Wert für: {frage[:40]}")

        except Exception as e:
            print(f"   ❌ Fehler: {e}")
            continue

    return filled


# ── Spieltipps auslesen ───────────────────────────────────────────────────────
def get_open_matches(driver) -> list:
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    driver.get(url)
    time.sleep(3)

    matches = []
    rows = driver.find_elements(
        By.CSS_SELECTOR, "table#tippabgabeSpiele tr.datarow"
    )
    print(f"\n⚽ Spielzeilen gefunden: {len(rows)}")

    for row in rows:
        try:
            home = row.find_element(By.CSS_SELECTOR, ".heimmannschaft").text.strip()
            away = row.find_element(By.CSS_SELECTOR, ".gastmannschaft").text.strip()
            inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text']")
            if home and away and inputs and not inputs[0].get_attribute("value"):
                matches.append({"home": home, "away": away, "row": row})
                print(f"   + {home} vs {away}")
        except Exception:
            continue

    return matches


# ── Spieltipps eintragen ──────────────────────────────────────────────────────
def enter_tips(driver, matches: list, tips: list) -> int:
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
            print(f"❌ {match['home']} vs {match['away']}: {e}")
    return entered


# ── Speichern ─────────────────────────────────────────────────────────────────
def submit_tips(driver):
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
            )
        )
        btn.click()
        time.sleep(2)
        print("✓ Gespeichert!")
    except Exception as e:
        print(f"❌ Speichern fehlgeschlagen: {e}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("🚀 Kicktipp-Bot v5 startet...")
    driver = create_driver()

    try:
        login(driver)

        # Bonusfragen
        print("\n🏆 Bonustipps werden geholt...")
        bonus = get_bonus_tips_from_claude()
        filled = enter_bonus_tips(driver, bonus)
        print(f"   {filled} Bonusfrage(n) eingetragen")
        if filled > 0:
            submit_tips(driver)

        # Spieltipps
        print("\n⚽ Spieltipps werden geholt...")
        matches = get_open_matches(driver)
        if not matches:
            print("ℹ️  Keine offenen Spieltipps.")
        else:
            tips = get_tips_from_claude(matches)
            entered = enter_tips(driver, matches, tips)
            print(f"   {entered} Spieltipp(s) eingetragen")
            if entered > 0:
                submit_tips(driver)

    finally:
        driver.quit()
        print("\n✅ Bot beendet.")


if __name__ == "__main__":
    main()
