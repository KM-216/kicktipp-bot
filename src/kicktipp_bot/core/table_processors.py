"""Table processing utilities for game tipping."""

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from ..utils.selenium_utils import SeleniumUtils

logger = logging.getLogger(__name__)


class TimeExtractor:
    """Handles time extraction from table rows."""

    @staticmethod
    def extract_from_rowheader(header_row) -> Optional[datetime]:
        """Extract time from a rowheader element using multiple approaches."""
        try:
            # Approach 1: Look for any td with time-like content
            time_cells = SeleniumUtils.safe_find_elements(
                header_row, By.TAG_NAME, 'td')
            for cell in time_cells:
                time_text = SeleniumUtils.safe_get_text(
                    cell, 'header time cell')
                if time_text and time_text.strip():
                    text = time_text.strip()
                    if TimeExtractor._looks_like_time(text):
                        logger.debug(f"Found time in rowheader cell: '{text}'")
                        return TimeExtractor._parse_time_string(text)

            # Approach 2: Look for specific time-related classes or attributes
            time_element = SeleniumUtils.safe_find_element(
                header_row, By.XPATH, './/td[contains(@class, "time") or contains(text(), ":") or contains(text(), ".")]')
            if time_element:
                time_text = SeleniumUtils.safe_get_text(
                    time_element, 'header time xpath')
                if time_text and time_text.strip():
                    logger.debug(
                        f"Found time via xpath in rowheader: '{time_text.strip()}'")
                    return TimeExtractor._parse_time_string(time_text.strip())

            logger.debug(
                "Could not extract time from rowheader using any method")
            return None

        except Exception as e:
            logger.error(f"Error extracting time from rowheader: {e}")
            return None

    @staticmethod
    def extract_from_datarow(data_row, fallback_time: Optional[datetime] = None) -> datetime:
        """Extract time from a datarow or use fallback time."""
        time_cell = SeleniumUtils.safe_find_element(
            data_row, By.XPATH, './td[1]')
        if time_cell:
            class_attr = SeleniumUtils.safe_get_attribute(
                time_cell, 'class', 'time cell') or ''
            logger.debug(f"Time cell class: '{class_attr}'")

            # Only use if not hidden
            if 'hide' not in class_attr:
                time_text = SeleniumUtils.safe_get_text(
                    time_cell, 'datarow time')
                if time_text and time_text.strip():
                    logger.debug(
                        f"Found visible time in datarow: {time_text.strip()}")
                    return TimeExtractor._parse_time_string(time_text.strip())
            else:
                logger.debug("Time cell is hidden, will use fallback time")

        # Use fallback time or current time
        if fallback_time:
            logger.debug(
                f"Using fallback time: {fallback_time.strftime('%d.%m.%y %H:%M')}")
            return fallback_time
        else:
            logger.warning("No time available, using current time")
            return datetime.now(tz=ZoneInfo('Europe/Berlin'))

    @staticmethod
    def has_visible_time(data_row) -> bool:
        """Check if a datarow has a visible (non-hidden) time cell with content."""
        time_cell = SeleniumUtils.safe_find_element(
            data_row, By.XPATH, './td[1]')
        if time_cell:
            class_attr = SeleniumUtils.safe_get_attribute(
                time_cell, 'class', 'time cell') or ''
            if 'hide' not in class_attr:
                time_text = SeleniumUtils.safe_get_text(
                    time_cell, 'datarow time check')
                return bool(time_text and time_text.strip())
        return False

    @staticmethod
    def _looks_like_time(text: str) -> bool:
        """Check if text looks like a time string."""
        return any(char.isdigit() for char in text) and ('.' in text or ':' in text)

    @staticmethod
    def _parse_time_string(time_text: str) -> datetime:
        """Parse time string into Europe/Berlin aware datetime object using zoneinfo."""
        try:
            naive_dt = datetime.strptime(time_text, '%d.%m.%y %H:%M')
            return naive_dt.replace(tzinfo=ZoneInfo('Europe/Berlin'))
        except ValueError as e:
            logger.warning(f"Could not parse time '{time_text}': {e}")
            return datetime.now(tz=ZoneInfo('Europe/Berlin'))


class TableRowProcessor:
    """Handles processing of table rows and state management."""

    def __init__(self, driver: WebDriver):
        self.driver = driver

    def get_all_table_rows(self):
        """Get all table rows from the tipping table."""
        return SeleniumUtils.safe_find_elements(
            self.driver,
            By.XPATH,
            '//*[@id="tippabgabeSpiele"]/tbody/tr'
        )

    def get_row_safely(self, all_rows, row_index: int):
        """Get a row safely, handling stale element references."""
        try:
            row = all_rows[row_index]
            row_class = SeleniumUtils.safe_get_attribute(
                row, 'class', 'table row') or ''
            return row, row_class
        except Exception as e:
            if 'stale element' in str(e).lower():
                logger.debug(
                    f"Stale element for row {row_index}, re-finding...")
                fresh_rows = self.get_all_table_rows()
                if row_index < len(fresh_rows):
                    row = fresh_rows[row_index]
                    row_class = SeleniumUtils.safe_get_attribute(
                        row, 'class', 'table row') or ''
                    return row, row_class
                else:
                    logger.warning(f"Could not re-find row {row_index}")
                    return None, None
            else:
                raise e


class GameDataExtractor:
    """Handles extraction of game-specific data from table rows."""

    @staticmethod
    def extract_team_name(data_row, column_index: int, team_type: str) -> Optional[str]:
        """Extract team name from a specific column."""
        team_element = SeleniumUtils.safe_find_element(
            data_row, By.XPATH, f'./td[{column_index}]')
        if team_element:
            team_name = SeleniumUtils.safe_get_text(
                team_element, f'{team_type} team')
            if team_name and team_name.strip():
                return team_name.strip()
        return None

    @staticmethod
    def extract_team_names_robust(data_row) -> Optional[tuple]:
        """
        Extract team names using a more robust approach that works with different table structures.
        
        Strategy:
        1. Try to find team names using common class names and attributes
        2. Look for td elements that contain team information
        3. Fall back to positional extraction if needed
        
        Returns:
            Tuple of (home_team, away_team) or None if extraction fails
        """
        try:
            # Strategy 1: Look for td elements with team-related classes
            # Common classes: 'heimteam', 'gastteam', 'team', etc.
            all_cells = SeleniumUtils.safe_find_elements(data_row, By.TAG_NAME, 'td')
            if not all_cells:
                logger.warning("No table cells found in data row")
                return None
            
            # Strategy 2: Find cells that likely contain team names
            # Team names are usually text-heavy cells that are not:
            # - Time cells (contain ":" or ".")
            # - Input cells (contain input elements)
            # - Quote cells (contain links or numbers)
            # - Result cells (contain "-" between numbers)
            potential_team_cells = []
            
            for idx, cell in enumerate(all_cells):
                # Skip cells with input elements (these are tip fields)
                inputs = SeleniumUtils.safe_find_elements(cell, By.TAG_NAME, 'input')
                if inputs:
                    continue
                
                # Get cell text
                cell_text = SeleniumUtils.safe_get_text(cell, f'cell {idx}')
                if not cell_text or not cell_text.strip():
                    continue
                
                text = cell_text.strip()
                
                # Skip time cells (contain ":" or look like dates)
                if ':' in text or (text.count('.') >= 2 and len(text) <= 20):
                    continue
                
                # Skip cells that look like results (e.g., "2 : 1")
                if re.match(r'^\d+\s*[:−-]\s*\d+$', text):
                    continue
                
                # Skip cells that are just numbers or formations (e.g., "1-4-1")
                if re.match(r'^[\d\-]+$', text):
                    continue
                
                # Skip very short text (likely not team names)
                if len(text) < 3:
                    continue
                
                # This looks like a potential team name
                potential_team_cells.append((idx, text))
                logger.debug(f"Potential team cell {idx}: '{text}'")
            
            # We need at least 2 team cells (home and away)
            if len(potential_team_cells) >= 2:
                # Typically home team comes first, then away team
                home_team = potential_team_cells[0][1]
                away_team = potential_team_cells[1][1]
                logger.debug(f"Extracted teams: {home_team} vs {away_team}")
                return (home_team, away_team)
            
            # Strategy 3: Fallback to hardcoded positions (columns 2 and 3)
            logger.debug("Using fallback extraction with hardcoded column indices")
            home_team = GameDataExtractor.extract_team_name(data_row, 2, 'home')
            away_team = GameDataExtractor.extract_team_name(data_row, 3, 'away')
            
            if home_team and away_team:
                return (home_team, away_team)
            
            logger.warning("Could not extract team names using any strategy")
            return None
            
        except Exception as e:
            logger.error(f"Error in robust team name extraction: {e}")
            return None

    @staticmethod
    def get_tip_fields(game_row) -> Optional[tuple]:
        """Get tip input fields directly from a game row element."""
        home_tip_field = SeleniumUtils.safe_find_element(
            game_row, By.XPATH, './/input[contains(@name, "heimTipp")]')
        away_tip_field = SeleniumUtils.safe_find_element(
            game_row, By.XPATH, './/input[contains(@name, "gastTipp")]')

        if home_tip_field and away_tip_field:
            return home_tip_field, away_tip_field
        else:
            result_element = SeleniumUtils.safe_find_element(
                game_row, By.XPATH, './td[4]')
            if result_element:
                result_text = SeleniumUtils.safe_get_text(
                    result_element, 'game result')
                if result_text:
                    logger.debug(
                        f"Game is over or not available: {result_text}")
            return None

    @staticmethod
    def extract_quotes(game_row) -> Optional[list]:
        """
        Extract betting quotes in the order [1, X, 2].
        Supports multiple DOM structures:
        - New DOM with span elements (ad-free accounts): span.quote > span.quote-label + span.quote-text
        - New DOM with anchor elements (accounts with ads): a.quote > span.quote-label + span.quote-text
        - Legacy format: a.quote-link with text content
        
        Returns a list of 3 strings or None if not found.
        """
        # --- New DOM structure ---
        try:
            container = SeleniumUtils.safe_find_element(
                game_row,
                By.XPATH,
                './/div[contains(@class, "tippabgabe-quoten")]'
            )
            if not container:
                # fallback: sometimes quotes are inside td.quoten
                container = SeleniumUtils.safe_find_element(
                    game_row,
                    By.XPATH,
                    './/td[contains(@class, "quoten")]'
                )

            if container:
                # First try: Look for span elements (ad-free accounts)
                # Only select spans that have both quote-label and quote-text children
                quote_elements = SeleniumUtils.safe_find_elements(
                    container,
                    By.XPATH,
                    ".//span[contains(@class, 'quote')][span[contains(@class,'quote-label')] and span[contains(@class,'quote-text')]]"
                )
                
                # Fallback: Look for anchor elements (accounts with ads)
                if not quote_elements or len(quote_elements) < 3:
                    quote_elements = SeleniumUtils.safe_find_elements(
                        container,
                        By.XPATH,
                        './/a[contains(@class, "quote")]'
                    )
                
                logger.debug(f"Found {len(quote_elements)} quote elements in container")
                
                if quote_elements and len(quote_elements) >= 3:
                    pairs = []
                    for idx, a in enumerate(quote_elements):
                        label_el = SeleniumUtils.safe_find_element(
                            a, By.XPATH, './/span[contains(@class, "quote-label")]'
                        )
                        text_el = SeleniumUtils.safe_find_element(
                            a, By.XPATH, './/span[contains(@class, "quote-text")]'
                        )
                        label = SeleniumUtils.safe_get_text(label_el, 'quote label') if label_el else None
                        value = SeleniumUtils.safe_get_text(text_el, 'quote text') if text_el else None
                        
                        logger.debug(f"Quote anchor {idx}: label='{label}', value='{value}'")
                        
                        if label and value:
                            pairs.append((label.strip(), value.strip()))

                    if pairs:
                        mapping = {lbl: val for (lbl, val) in pairs}
                        ordered = [mapping.get('1'), mapping.get('X'), mapping.get('2')]
                        logger.debug(f"Quote mapping: {mapping}, ordered: {ordered}")
                        
                        if all(ordered) and len(ordered) == 3:
                            logger.info(f"Successfully extracted quotes: {ordered}")
                            return ordered
                        else:
                            logger.warning(f"Incomplete quote mapping: {mapping}")
                            logger.warning("This may indicate that quotes are not fully loaded or DNS/firewall is blocking the quote provider")
                else:
                    logger.debug(f"Not enough quote elements found: {len(quote_elements) if quote_elements else 0}")
        except Exception as e:
            logger.warning(f"Error parsing quotes (new DOM): {e}")

        # --- Legacy fallback ---
        try:
            quotes_element = SeleniumUtils.safe_find_element(
                game_row, By.XPATH, './/a[contains(@class, "quote-link")]'
            )
            if quotes_element:
                quotes_raw = SeleniumUtils.safe_get_text(quotes_element, 'quotes element')
                logger.debug(f"Legacy quotes element text: '{quotes_raw}'")
                
                if quotes_raw:
                    txt = quotes_raw.replace("Quote: ", "").strip()
                    if " / " in txt:
                        parts = [p.strip() for p in txt.split(" / ")]
                    elif " | " in txt:
                        parts = [p.strip() for p in txt.split(" | ")]
                    else:
                        parts = None

                    if parts and len(parts) == 3:
                        logger.info(f"Successfully extracted quotes (legacy): {parts}")
                        return parts
                    else:
                        logger.warning(f"Could not parse legacy quotes format: '{txt}'")
                        logger.warning("Expected format: '1.50 / 3.20 / 5.00' or '1.50 | 3.20 | 5.00'")
                else:
                    logger.warning("Legacy quotes element found but has no text content")
                    logger.warning("This may indicate DNS/firewall blocking or quotes not yet loaded")
        except Exception as e:
            logger.warning(f"Error parsing quotes (legacy DOM): {e}")

        # --- Additional debugging: check what's actually in the row ---
        try:
            all_links = SeleniumUtils.safe_find_elements(game_row, By.TAG_NAME, 'a')
            logger.debug(f"Total links found in row: {len(all_links)}")
            for idx, link in enumerate(all_links[:5]):  # Log first 5 links
                link_text = SeleniumUtils.safe_get_text(link, f'link {idx}')
                link_class = SeleniumUtils.safe_get_attribute(link, 'class', f'link {idx}')
                logger.debug(f"Link {idx}: class='{link_class}', text='{link_text}'")
        except Exception as e:
            logger.debug(f"Could not log link debug info: {e}")

        logger.warning("Could not find quotes element in any supported format")
        logger.warning("Possible causes:")
        logger.warning("  - Quotes are not yet loaded (try increasing wait time)")
        logger.warning("  - DNS/Firewall blocking quote provider (check Pi-hole or similar)")
        logger.warning("  - Page structure has changed")
        logger.warning("  - Network connectivity issues")
        return None
