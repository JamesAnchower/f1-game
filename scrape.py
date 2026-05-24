import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urljoin
import re
import unicodedata

BASE_URL = "https://www.formula1.com"
RACES_URL = "https://www.formula1.com/en/results/2026/races"
DRIVERS_URL = "https://www.formula1.com/en/results/2026/drivers"
SCHEDULE_URL = "https://www.formula1.com/en/racing/2026"

DRIVER_CODE_MAP = {
    "ALB": "albon",
    "ALO": "alonso",
    "ANT": "antonelli",
    "BEA": "bearman",
    "BOR": "bortoleto",
    "BOT": "bottas",
    "COL": "colapinto",
    "GAS": "gasly",
    "HAD": "hadjar",
    "HAM": "hamilton",
    "HUL": "hulkenberg",
    "LAW": "lawson",
    "LEC": "leclerc",
    "LIN": "lindblad",
    "NOR": "norris",
    "OCO": "ocon",
    "PER": "perez",
    "PIA": "piastri",
    "RUS": "russell",
    "SAI": "sainz",
    "STR": "stroll",
    "VER": "verstappen"
}

RACE_NAME_ALIAS_KEYS = {
    "australiangp": "australia",
    "australian": "australia",
    "chinesegp": "china",
    "chinese": "china",
    "japanesegp": "japan",
    "japanese": "japan"
}


def normalize_race_name_key(name):
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_name = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    ascii_name = ascii_name.replace("grand prix", "")
    ascii_name = re.sub(r"\bgp\b", "", ascii_name)
    ascii_name = re.sub(r"[^a-z0-9]+", "", ascii_name)
    return ascii_name


def canonicalize_race_name(name, official_race_names):
    official_map = {normalize_race_name_key(n): n for n in official_race_names}
    key = normalize_race_name_key(name)
    key = RACE_NAME_ALIAS_KEYS.get(key, key)
    return official_map.get(key, name)


def scrape_race_list(races_url=RACES_URL):
    """Return race rows from F1 race list page in display order."""
    soup = get_soup(races_url)
    race_result_pattern = re.compile(r"/en/results/\d{4}/races/(\d+)/([^/]+)/race-result/?$")

    rows = []
    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        tr_list = tbody.find_all("tr") if tbody else table.find_all("tr")

        for tr in tr_list:
            a = tr.find("a", href=True)
            if not a:
                continue

            full_url = urljoin(BASE_URL, a["href"].strip())
            m = race_result_pattern.search(full_url)
            if not m:
                continue

            race_id = int(m.group(1))
            race_slug = m.group(2)
            race_name = race_slug.replace("-", " ").title()
            rows.append({
                "race_id": race_id,
                "race_name": race_name,
                "race_url": full_url
            })

    # Deduplicate by race_id and keep first appearance (table order)
    deduped = {}
    for row in rows:
        deduped.setdefault(row["race_id"], row)

    race_rows = sorted(deduped.values(), key=lambda x: x["race_id"])
    return race_rows


def get_soup(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser")


def scrape_f1_races():
    # Scrape all completed races from the race list
    try:
        race_rows = scrape_race_list(RACES_URL)
        if not race_rows:
            return [], [], []

        official_race_names = [r["race_name"] for r in race_rows]
        races = []
        for row in race_rows:
            race_name = row["race_name"]
            race_url = row["race_url"]
            print(f"Scraping {race_name}: {race_url}")

            finishes = scrape_race_finishes(race_url)
            # Future races generally have no result table yet; skip those
            if finishes:
                races.append({"name": race_name, "finishes": finishes})

        return race_rows, races, official_race_names

    except Exception as e:
        print(f"Error scraping races: {e}")
        return [], []


def scrape_current_driver_standings(drivers_url=DRIVERS_URL):
    """Scrape the current drivers standings page and return ordered driver ids by rank."""
    try:
        soup = get_soup(drivers_url)

        def to_driver_id(name):
            normalized = unicodedata.normalize("NFKD", name)
            ascii_name = "".join(ch for ch in normalized if not unicodedata.combining(ch))
            lowered = ascii_name.lower()
            return re.sub(r"[^a-z0-9]", "", lowered)

        candidate_tables = []
        primary = soup.find("table", class_="resultsarchive-table")
        if primary:
            candidate_tables.append(primary)
        candidate_tables.extend([t for t in soup.find_all("table") if t is not primary])

        for table in candidate_tables:
            ranks = []
            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else table.find_all("tr")

            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue

                pos_text = cols[0].get_text(strip=True)
                if not re.match(r"^\d+$", pos_text):
                    continue

                driver_id = None
                # Prefer /drivers/ slug when available
                for a in row.find_all("a", href=True):
                    href = a["href"].strip().lower()
                    if "/drivers/" not in href:
                        continue
                    slug = href.rstrip("/").split("/")[-1]
                    slug_token = slug.split("-")[-1]
                    slug_id = to_driver_id(slug_token)
                    if slug_id:
                        driver_id = slug_id
                        break

                # Fallback from displayed text/code
                if not driver_id:
                    text_candidates = [
                        cols[2].get_text(" ", strip=True) if len(cols) > 2 else "",
                        cols[1].get_text(" ", strip=True) if len(cols) > 1 else ""
                    ]
                    token = ""
                    for txt in text_candidates:
                        if txt:
                            token = txt.split()[-1]
                            if token:
                                break
                    token_upper = token.upper()
                    if token_upper in DRIVER_CODE_MAP:
                        driver_id = DRIVER_CODE_MAP[token_upper]
                    else:
                        driver_id = to_driver_id(token)

                if driver_id:
                    ranks.append(driver_id)

            # 2026 grid can be up to 22; require enough rows to identify standings table
            if len(ranks) >= 15:
                return ranks

        return []
    except Exception as e:
        print(f"Error scraping driver standings: {e}")
        return []


def get_next_race_name(official_race_names, completed_race_names):
    """Return next race name in official schedule after latest completed race."""
    schedule_names = scrape_season_schedule_race_names(SCHEDULE_URL)
    if schedule_names:
        official_race_names = schedule_names

    completed_keys = {normalize_race_name_key(n) for n in completed_race_names}
    for race_name in official_race_names:
        if normalize_race_name_key(race_name) not in completed_keys:
            return race_name
    return None


def scrape_next_race_name_from_races_page(races_url=RACES_URL):
    """Fallback: parse 'Next Race: <Name>' from races page text."""
    try:
        soup = get_soup(races_url)
        page_text = soup.get_text(" ", strip=True)
        m = re.search(r"Next\s+Race\s*:\s*([A-Za-z\u00C0-\u017F'\- ]+?)\s+\d{4}\b", page_text)
        if m:
            raw_name = m.group(1).strip()
            # Normalize spacing/casing and remove leading 'Flag of' if present in text content
            raw_name = re.sub(r"^Flag\s+of\s+", "", raw_name, flags=re.IGNORECASE)
            return raw_name.title()

        # Fallback 2: first race weekend link in event tracker, e.g. /en/racing/2026/miami
        race_weekend_pattern = re.compile(r"/en/racing/2026/([a-z0-9\-]+)/?$")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().lower()
            m2 = race_weekend_pattern.search(href)
            if not m2:
                continue
            slug = m2.group(1)
            # Skip generic year schedule links
            if slug == "2026":
                continue
            return slug.replace("-", " ").title()

        return None
    except Exception as e:
        print(f"Could not parse next race from races page: {e}")
        return None


def scrape_season_schedule_race_names(schedule_url=SCHEDULE_URL):
    """Return season race names in calendar order from schedule page."""
    try:
        soup = get_soup(schedule_url)
        race_weekend_pattern = re.compile(r"/en/racing/2026/([a-z0-9\-]+)/?$")
        names = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().lower()
            m = race_weekend_pattern.search(href)
            if not m:
                continue
            slug = m.group(1)
            if slug == "2026":
                continue
            names.append(slug.replace("-", " ").title())

        deduped = []
        seen = set()
        for name in names:
            key = normalize_race_name_key(name)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(name)
        return deduped
    except Exception as e:
        print(f"Could not parse season schedule: {e}")
        return []


def find_race_row_by_name(target_name):
    """Try to find a race row (race_id, race_name, race_url) for a given race name by scanning known pages."""
    try:
        pattern = re.compile(r"/en/results/2026/races/(\d+)/([^/]+)/")
        # Check results listing page and schedule page
        for url in (RACES_URL, SCHEDULE_URL):
            try:
                soup = get_soup(url)
            except Exception:
                continue
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                m = pattern.search(href.lower())
                if not m:
                    continue
                race_id = int(m.group(1))
                slug = m.group(2)
                name = slug.replace('-', ' ').title()
                if normalize_race_name_key(name) == normalize_race_name_key(target_name):
                    return { 'race_id': race_id, 'race_name': name, 'race_url': urljoin(BASE_URL, href) }
        return None
    except Exception as e:
        print(f"Error finding race row by name: {e}")
        return None


def update_next_race_standings_json(official_race_names, completed_race_names):
    """Keep historical standings; only upsert next-race pre-race ranks from current drivers standings."""
    next_race_name = get_next_race_name(official_race_names, completed_race_names)
    if not next_race_name:
        next_race_name = scrape_next_race_name_from_races_page(RACES_URL)
        if next_race_name and next_race_name not in official_race_names:
            official_race_names = official_race_names + [next_race_name]

    if not next_race_name:
        print("No upcoming race found for standings update")
        return

    current_ranks = scrape_current_driver_standings(DRIVERS_URL)
    if not current_ranks:
        print("Could not scrape current driver standings; standings.json unchanged")
        return

    standings_data = {"standings": []}
    if os.path.exists('standings.json'):
        with open('standings.json', 'r') as f:
            standings_data = json.load(f)

    existing_rows = standings_data.get('standings', [])

    # Normalize names and preserve historical rows
    normalized_rows = []
    seen = set()
    for row in existing_rows:
        standardized_name = canonicalize_race_name(row.get('name', ''), official_race_names)
        key = normalize_race_name_key(standardized_name)
        if key in seen:
            continue
        seen.add(key)
        normalized_rows.append({
            "name": standardized_name,
            "ranks": row.get('ranks', [])
        })

    # Upsert next race entry with freshly scraped standings
    next_key = normalize_race_name_key(next_race_name)
    replaced = False
    for row in normalized_rows:
        if normalize_race_name_key(row['name']) == next_key:
            row['name'] = next_race_name
            row['ranks'] = current_ranks
            replaced = True
            break

    if not replaced:
        normalized_rows.append({
            "name": next_race_name,
            "ranks": current_ranks
        })

    # Order by official race schedule where possible
    by_key = {normalize_race_name_key(r['name']): r for r in normalized_rows}
    ordered = []
    for official_name in official_race_names:
        key = normalize_race_name_key(official_name)
        if key in by_key:
            ordered.append(by_key.pop(key))
    ordered.extend(by_key.values())

    standings_data['standings'] = ordered
    with open('standings.json', 'w') as f:
        json.dump(standings_data, f, indent=2)

    print(f"Updated standings.json for next race: {next_race_name}")

def scrape_race_finishes(race_url):
    try:
        soup = get_soup(race_url)

        def to_driver_id(name):
            normalized = unicodedata.normalize("NFKD", name)
            ascii_name = "".join(ch for ch in normalized if not unicodedata.combining(ch))
            lowered = ascii_name.lower()
            return re.sub(r"[^a-z0-9]", "", lowered)

        # Try old/classic table first, but fall back to scanning all tables
        candidate_tables = []
        primary = soup.find("table", class_="resultsarchive-table")
        if primary:
            candidate_tables.append(primary)
        candidate_tables.extend([t for t in soup.find_all("table") if t is not primary])

        for table in candidate_tables:
            finishes = []
            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else table.find_all("tr")

            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 6:
                    continue

                pos_text = cols[0].get_text(strip=True).upper()
                if not re.match(r"^(\d+|NC|DSQ|DQ|DNS|DNF)$", pos_text):
                    continue

                # Modern table layout is usually: Pos | No | Driver | Car | Laps | Time/Retired | Pts
                # Fallback to older layout if needed
                driver_text = cols[2].get_text(" ", strip=True) if len(cols) > 2 else ""
                if not driver_text and len(cols) > 3:
                    driver_text = cols[3].get_text(" ", strip=True)
                if not driver_text:
                    continue

                # Try to derive driver id from row links first
                driver_id = None
                for a in row.find_all("a", href=True):
                    href = a["href"].strip().lower()
                    if "/drivers/" not in href:
                        continue
                    slug = href.rstrip("/").split("/")[-1]
                    # Handle possible first-last slugs (e.g. kimi-antonelli) by taking surname token
                    slug_token = slug.split("-")[-1]
                    slug_id = to_driver_id(slug_token)
                    if slug_id:
                        driver_id = slug_id
                        break

                if not driver_id:
                    token = driver_text.split()[-1]
                    token_upper = token.upper()
                    if token_upper in DRIVER_CODE_MAP:
                        driver_id = DRIVER_CODE_MAP[token_upper]
                    else:
                        driver_id = to_driver_id(token)

                time_or_status = cols[5].get_text(" ", strip=True).upper() if len(cols) > 5 else ""
                if pos_text in {"NC", "DSQ", "DQ", "DNS", "DNF"} or any(x in time_or_status for x in ["DNF", "DNS", "DSQ", "DQ"]):
                    status = "dnf"
                else:
                    status = "finished"

                finishes.append({"driver": driver_id, "status": status})

            # If we parsed enough rows, this is the race result table
            if len(finishes) >= 10:
                return finishes[:22]

        return []
    
    except Exception as e:
        print(f"Error scraping race: {e}")
        return []

def update_races_json():
    scraped_rows, scraped_races, official_race_names = scrape_f1_races()
    if scraped_races:
        existing_races = []
        if os.path.exists('races.json'):
            with open('races.json', 'r') as f:
                existing_races = json.load(f).get('races', [])

        # Normalize existing race names to official F1 race-list names
        normalized_existing = []
        for race in existing_races:
            normalized_existing.append({
                "name": canonicalize_race_name(race.get("name", ""), official_race_names),
                "finishes": race.get("finishes", [])
            })

        merged = {}
        for race in normalized_existing:
            merged[race["name"]] = race
        # Scraped races overwrite existing entries for the same race name
        for race in scraped_races:
            merged[race["name"]] = race

        # Keep official season order where possible
        ordered = []
        for official_name in official_race_names:
            if official_name in merged:
                ordered.append(merged.pop(official_name))
        # Append anything unmatched
        ordered.extend(merged.values())

        data = {"races": ordered}
        with open('races.json', 'w') as f:
            json.dump(data, f, indent=2)
        completed_race_names = [r['name'] for r in scraped_races]
        update_next_race_standings_json(official_race_names, completed_race_names)

        # Now attempt to scrape the starting grid for the next race (if available)
        try:
            next_race_name = get_next_race_name(official_race_names, completed_race_names)
            if not next_race_name:
                next_race_name = scrape_next_race_name_from_races_page(RACES_URL)
            if next_race_name:
                print(f"Next race determined for starting grid check: {next_race_name}")
            else:
                print("No next race could be determined for starting grid check")

            # find matching row to obtain race_id and slug
            next_row = None
            if next_race_name and scraped_rows:
                print('Available scraped rows:')
                for row in scraped_rows:
                    rn = row.get('race_name')
                    print(f" - id={row.get('race_id')} name='{rn}' url='{row.get('race_url')}' norm='{normalize_race_name_key(rn)}'")

                next_key = normalize_race_name_key(next_race_name)
                print(f"Looking for next race key: '{next_key}' (from '{next_race_name}')")

                for row in scraped_rows:
                    left = canonicalize_race_name(row.get('race_name'), official_race_names)
                    right = canonicalize_race_name(next_race_name, official_race_names)
                    if left == right:
                        next_row = row
                        print(f"Canonical match found: row name='{row.get('race_name')}'")
                        break

                if not next_row:
                    for row in scraped_rows:
                        if normalize_race_name_key(row.get('race_name')) == next_key:
                            next_row = row
                            print(f"Normalized-key match found: row name='{row.get('race_name')}'")
                            break

            def scrape_starting_grid_for_row(row):
                try:
                    # Prefer using the scraped race URL to build the starting-grid URL
                    race_url = row.get('race_url')
                    if race_url:
                        grid_url = race_url.rstrip('/')
                        # race_url typically ends with '/race-result' - replace with '/starting-grid'
                        grid_url = re.sub(r'/race-result/?$', '/starting-grid', grid_url)
                        if not grid_url.endswith('/starting-grid'):
                            grid_url = grid_url + '/starting-grid'
                    else:
                        # fallback: attempt to construct from id and name
                        race_id = row.get('race_id')
                        race_name = row.get('race_name') or ''
                        if not race_id or not race_name:
                            return None
                        slug = re.sub(r"[^a-z0-9]+", '-', race_name.lower()).strip('-')
                        grid_url = f"{BASE_URL}/en/results/2026/races/{race_id}/{slug}/starting-grid"

                    print(f"Attempting to fetch starting grid page: {grid_url}")
                    try:
                        soup = get_soup(grid_url)
                    except Exception as e:
                        print(f"Failed to fetch starting grid URL: {grid_url} -> {e}")
                        return None

                    primary = soup.find("table", class_="resultsarchive-table")
                    candidate_tables = []
                    if primary:
                        candidate_tables.append(primary)
                    candidate_tables.extend([t for t in soup.find_all("table") if t is not primary])

                    def to_driver_id(name):
                        normalized = unicodedata.normalize("NFKD", name)
                        ascii_name = "".join(ch for ch in normalized if not unicodedata.combining(ch))
                        lowered = ascii_name.lower()
                        return re.sub(r"[^a-z0-9]", "", lowered)

                    for table in candidate_tables:
                        grid = []
                        tbody = table.find("tbody")
                        rows = tbody.find_all("tr") if tbody else table.find_all("tr")
                        for row_el in rows:
                            cols = row_el.find_all("td")
                            if len(cols) < 3:
                                continue
                            pos_text = cols[0].get_text(strip=True)
                            if not re.match(r"^\d+$", pos_text):
                                continue
                            pos = int(pos_text)

                            driver_id = None
                            for a in row_el.find_all("a", href=True):
                                href = a["href"].strip().lower()
                                if "/drivers/" not in href:
                                    continue
                                slug = href.rstrip("/").split("/")[-1]
                                slug_token = slug.split("-")[-1]
                                slug_id = to_driver_id(slug_token)
                                if slug_id:
                                    driver_id = slug_id
                                    break

                            if not driver_id:
                                driver_text = cols[2].get_text(" ", strip=True)
                                token = driver_text.split()[-1] if driver_text else ""
                                driver_id = DRIVER_CODE_MAP.get(token.upper()) or to_driver_id(token)

                            if driver_id:
                                grid.append({"driver": driver_id, "position": pos})

                        if len(grid) >= 10:
                            return grid
                except Exception:
                    return None
                return None

            starting_grid = None
            if next_row:
                print(f"Found race row for next race: id={next_row.get('race_id')} url={next_row.get('race_url')}")
                starting_grid = scrape_starting_grid_for_row(next_row)
            else:
                print('No matching scraped row found for next race; attempting to locate by scanning schedule/results pages')
                located = find_race_row_by_name(next_race_name)
                if located:
                    print(f"Located race row via scan: id={located.get('race_id')} url={located.get('race_url')}")
                    starting_grid = scrape_starting_grid_for_row(located)
                else:
                    print('Could not locate race row for next race via scan; cannot fetch starting grid')

            if starting_grid:
                grid_data = {"name": next_race_name, "grid": starting_grid}
                with open('starting_grid.json', 'w') as gf:
                    json.dump(grid_data, gf, indent=2)
                print(f"Saved starting_grid.json for next race: {next_race_name} (entries: {len(starting_grid)})")
            else:
                print('No starting grid parsed for next race')
                if os.path.exists('starting_grid.json'):
                    try:
                        os.remove('starting_grid.json')
                        print('Removed starting_grid.json; starting grid not available for next race')
                    except Exception as e:
                        print(f'Could not remove starting_grid.json: {e}')
        except Exception as e:
            print(f"Error handling starting grid: {e}")

        print("Updated races.json with merged scraped data and standings.json for next race")
    else:
        print("No races scraped")

if __name__ == "__main__":
    update_races_json()