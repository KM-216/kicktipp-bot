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


# ── Schritt 1: Claude nach Spieltipps fragen ──────────────────────────────────
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

## Analysestrategie

### 1. Aktuelle Nachrichten abrufen
Suche für jedes Spiel nach:
- Verletzungen und Sperren der Stammspieler
- Aktuellen Buchmacher-Quoten
- Form der letzten Spiele beider Teams in dieser WM

### 2. WM-Turnierkontext
- Analysiere den bisherigen Torschnitt dieser WM
- Beachte Muster: offensive vs. defensive Teams
- Gruppenphase vs. K.O.-Runde beeinflusst Risikobereitschaft

### 3. Tipp-Philosophie
- Setze grundsätzlich auf den Favoriten
- Bei klaren Favoriten: tippe deutlichere Siege (2:0 oder 3:1 statt 1:0)
- Riskiere kalkuliert wenn Quoten oder Form es rechtfertigen
- Unentschieden nur wenn wirklich ausgeglichen

### 4. Punktesystem
- Nur Tendenz richtig: 2 Punkte
- Tendenz + Tordifferenz richtig: 3 Punkte
- Genaues Ergebnis: 4 Punkte
Strategie: Lieber präzise tippen als zu vorsichtig sein.

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
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw += block.text

    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    tips = json.loads(raw)

    print("\n🤖 Claude's Spieltipps:")
    for t in tips:
        print(f"   {t['home']} {t['home_score']}:{t['away_score']} {t['away']} [{t.get('confidence','?')}] – {t.get('reasoning','')}")

    return tips


# ── Schritt 2: Claude nach Bonusfragen fragen ─────────────────────────────────
def get_bonus_tips_from_claude() -> dict:
    client = anthropic.Anthropic(api_key=API_KEY)

    teams_str = ", ".join(TEAMS)

    prompt = f"""Du bist ein WM 2026 Experte. Beantworte folgende Bonusfragen für die WM 2026.

## Verfügbare Teams (exakt diese Schreibweise verwenden!)
{teams_str}

## Bonusfragen

1. Welche Mannschaft stellt den Spieler mit den meisten Toren (Torschützenkönig)?
2. Wer erreicht das Halbfinale? (4 Teams nennen)
3. Wer gewinnt Gruppe A?
4. Wer gewinnt Gruppe B?
5. Wer gewinnt Gruppe C?
6. Wer gewinnt Gruppe D?
7. Wer gewinnt Gruppe E?
8. Wer gewinnt Gruppe F?
9. Wer gewinnt Gruppe G?
10. Wer gewinnt Gruppe H?
11. Wer gewinnt Gruppe I?
12. Wer gewinnt Gruppe J?
13. Wer gewinnt Gruppe K?
14. Wer gewinnt Gruppe L?
15. Wer wird Weltmeister?

## Analysestrategie
- Suche aktuelle WM 2026 Gruppenauslosungen und Favoritenanalysen
- Berücksichtige FIFA-Weltrangliste, aktuelle Form und Kaderqualität
- Setze auf Favoriten, aber berücksichtige auch Außenseiterchancen

## Ausgabe
NUR JSON-Objekt, keine Erklärungen, keine Backticks:
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
}}

Wichtig: Nur Teamnamen aus der obigen Liste verwenden!"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw += block.text

    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    bonus = json.loads(raw)

    print("\n🏆 Claude's Bonustipps:")
    print(f"   Torschützenkönig-Land: {bonus.get('torschuetzenkoenigsland')}")
    print(f"   Halbfinale: {', '.join(bonus.get('halbfinale', []))}")
    for g in ['A','B','C','D','E','F','G','H','I','J','K','L']:
        print(f"   Gruppe {g}: {bonus.get(f'gruppe_{g}')}")
    print(f"   Weltmeister: {bonus.get('weltmeister')}")

    return bonus


# ── Schritt 3: Chrome starten ─────────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


# ── Schritt 4: Bei Kicktipp einloggen ─────────────────────────────────────────
def login(driver):
    print("🔑 Einloggen bei Kicktipp...")
    driver.get("https://www.kicktipp.de/info/profil/login")
    time.sleep(2)
    driver.find_element(By.NAME, "kennung").send_keys(EMAIL)
    driver.find_element(By.NAME, "passwort").send_keys(PASSWORD)
    driver.find_element(By.NAME, "submitbutton").click()
    time.sleep(3)
    print("✓ Login erfolgreich")


# ── Schritt 5: Offene Spiele auslesen ─────────────────────────────────────────
def get_open_matches(driver) -> list:
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    print(f"📋 Öffne: {url}")
    driver.get(url)
    time.sleep(3)

    matches = []
    selectors = [
        ("table.tippabgabe tr.datarow", ".heimmannschaft", ".gastmannschaft"),
        ("tr.datarow", ".heimmannschaft", ".gastmannschaft"),
    ]

    for row_sel, home_sel, away_sel in selectors:
        rows = driver.find_elements(By.CSS_SELECTOR, row_sel)
        if rows:
            print(f"   Selektor '{row_sel}': {len(rows)} Zeilen")
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

    return matches


# ── Schritt 6: Bonusfragen eintragen ──────────────────────────────────────────
def enter_bonus_tips(driver, bonus: dict):
    print("\n📝 Bonusfragen werden eingetragen...")
    url = f"https://www.kicktipp.de/{COMPETITION}/tippabgabe"
    driver.get(url)
    time.sleep(3)

    # Alle Dropdowns auf der Seite finden
    selects = driver.find_elements(By.CSS_SELECTOR, "select")
    print(f"   Gefundene Dropdowns: {len(selects)}")

    # Labels zu den Selects finden
    filled = 0
    for select_el in selects:
        try:
            # Frage aus dem nächstgelegenen Label oder vorangehenden Text ermitteln
            label = ""
            try:
                row = select_el.find_element(By.XPATH, "./ancestor::tr[1]")
                label = row.text.lower()
            except Exception:
                pass

            select = Select(select_el)
            value = None

            if "weltmeister" in label:
                value = bonus.get("weltmeister")
            elif "torschützen" in label or "meisten toren" in label:
                value = bonus.get("torschuetzenkoenigsland")
            elif "halbfinale" in label:
                halbfinale = bonus.get("halbfinale", [])
                # Welcher der 4 Slots ist das? Zähle bereits befüllte
                if filled < len(halbfinale):
                    value = halbfinale[filled % 4]
            elif "gruppe a" in label:
                value = bonus.get("gruppe_A")
            elif "gruppe b" in label:
                value = bonus.get("gruppe_B")
            elif "gruppe c" in label:
                value = bonus.get("gruppe_C")
            elif "gruppe d" in label:
                value = bonus.get("gruppe_D")
            elif "gruppe e" in label:
                value = bonus.get("gruppe_E")
            elif "gruppe f" in label:
                value = bonus.get("gruppe_F")
            elif "gruppe g" in label:
                value = bonus.get("gruppe_G")
            elif "gruppe h" in label:
                value = bonus.get("gruppe_H")
            elif "gruppe i" in label:
                value = bonus.get("gruppe_I")
            elif "gruppe j" in label:
                value = bonus.get("gruppe_J")
            elif "gruppe k" in label:
                value = bonus.get("gruppe_K")
            elif "gruppe l" in label:
                value = bonus.get("gruppe_L")

            if value:
                select.select_by_visible_text(value)
                print(f"   ✓ '{label.strip()[:40]}' → {value}")
                filled += 1

        except Exception as e:
            print(f"   ⚠️  Fehler bei Dropdown: {e}")
            continue

    return filled


# ── Schritt 7: Spieltipps eintragen ───────────────────────────────────────────
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


# ── Schritt 8: Speichern ──────────────────────────────────────────────────────
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
        print(f"❌ Fehler beim Speichern: {e}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("🚀 Kicktipp-Bot startet...")
    driver = create_driver()

    try:
        login(driver)

        # ── Bonusfragen ───────────────────────────────────────────────────────
        print("\n🏆 Hole Bonustipps von Claude...")
        bonus = get_bonus_tips_from_claude()
        bonus_filled = enter_bonus_tips(driver, bonus)
        print(f"   {bonus_filled} Bonusfrage(n) eingetragen")
        if bonus_filled > 0:
            submit_tips(driver)

        # ── Spieltipps ────────────────────────────────────────────────────────
        print("\n⚽ Hole Spieltipps von Claude...")
        matches = get_open_matches(driver)
        if not matches:
            print("ℹ️  Keine offenen Spieltipps gefunden.")
        else:
            tips = get_tips_from_claude(matches)
            entered = enter_tips(driver, matches, tips)
            print(f"\n✏️  {entered} Spieltipp(s) eingetragen")
            if entered > 0:
                submit_tips(driver)

    finally:
        driver.quit()
        print("\n✅ Bot beendet.")


if __name__ == "__main__":
    main()
