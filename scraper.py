"""
Zagreb Events Scraper
Scrapes events from Croatian event sites and saves to events.json
Runs daily via GitHub Actions
"""

import json
import time
import re
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hr-HR,hr;q=0.9,en;q=0.8",
}

TIMEOUT = 15

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def get(url: str) -> Optional[BeautifulSoup]:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [!] Failed to fetch {url}: {e}")
        return None


def make_id(title: str, date: str) -> str:
    """Create a stable unique ID from title + date."""
    raw = f"{title.lower().strip()}-{date}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def normalize_date(raw: str) -> Optional[str]:
    """
    Try to parse various Croatian/English date formats into YYYY-MM-DD.
    Returns None if parsing fails.
    """
    raw = raw.strip()

    # Already ISO format
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]

    # Croatian month names
    hr_months = {
        "siječnja": 1, "siječanj": 1, "sij": 1,
        "veljače": 2, "veljača": 2, "velj": 2,
        "ožujka": 3, "ožujak": 3, "ožu": 3,
        "travnja": 4, "travanj": 4, "tra": 4,
        "svibnja": 5, "svibanj": 5, "svi": 5,
        "lipnja": 6, "lipanj": 6, "lip": 6,
        "srpnja": 7, "srpanj": 7, "srp": 7,
        "kolovoza": 8, "kolovoz": 8, "kol": 8,
        "rujna": 9, "rujan": 9, "ruj": 9,
        "listopada": 10, "listopad": 10, "lis": 10,
        "studenog": 11, "studenoga": 11, "studeni": 11, "stu": 11,
        "prosinca": 12, "prosinac": 12, "pro": 12,
    }

    raw_lower = raw.lower()
    for name, num in hr_months.items():
        if name in raw_lower:
            # Extract day and optionally year
            day_match = re.search(r"\b(\d{1,2})\.", raw)
            year_match = re.search(r"\b(202\d)\b", raw)
            if day_match:
                day = int(day_match.group(1))
                year = int(year_match.group(1)) if year_match else datetime.now().year
                return f"{year}-{num:02d}-{day:02d}"

    # Try common formats
    for fmt in ("%d.%m.%Y", "%d. %m. %Y", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


# ─────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────

def scrape_entrio() -> list[dict]:
    """
    Scrape events from entrio.hr — major Croatian ticketing platform.
    """
    events = []
    print("Scraping entrio.hr …")
    soup = get("https://www.entrio.hr/events?location=zagreb")
    if not soup:
        return events

    for card in soup.select(".event-card, .event_card, [class*='event-item'], article[class*='event']")[:30]:
        try:
            title_el = card.select_one("h2, h3, .event-title, [class*='title']")
            date_el  = card.select_one(".event-date, [class*='date'], time")
            loc_el   = card.select_one(".event-location, [class*='location'], [class*='venue']")
            link_el  = card.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            date_raw = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date(date_raw) if date_raw else None
            if not date:
                continue

            location = loc_el.get_text(strip=True) if loc_el else "Zagreb"
            url = link_el["href"] if link_el else "https://www.entrio.hr"
            if url.startswith("/"):
                url = "https://www.entrio.hr" + url

            events.append({
                "id": make_id(title, date),
                "title": title,
                "date": date,
                "time": "",
                "location": location,
                "category": categorize(title),
                "description": "",
                "url": url,
                "source": "entrio.hr",
            })
        except Exception as e:
            print(f"  [!] Card parse error: {e}")
            continue

    print(f"  → {len(events)} events from entrio.hr")
    return events


def scrape_infozagreb() -> list[dict]:
    """
    Scrape events from infozagreb.hr — official Zagreb tourism board.
    """
    events = []
    print("Scraping infozagreb.hr …")
    soup = get("https://www.infozagreb.hr/events")
    if not soup:
        return events

    for card in soup.select(".event, .event-item, article, .card")[:30]:
        try:
            title_el = card.select_one("h2, h3, h4, .title")
            date_el  = card.select_one(".date, time, [class*='date']")
            link_el  = card.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if len(title) < 4:
                continue

            date_raw = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date(date_raw) if date_raw else None
            if not date:
                continue

            url = link_el["href"] if link_el else "https://www.infozagreb.hr"
            if url.startswith("/"):
                url = "https://www.infozagreb.hr" + url

            events.append({
                "id": make_id(title, date),
                "title": title,
                "date": date,
                "time": "",
                "location": "Zagreb",
                "category": categorize(title),
                "description": "",
                "url": url,
                "source": "infozagreb.hr",
            })
        except Exception:
            continue

    print(f"  → {len(events)} events from infozagreb.hr")
    return events


def scrape_tvornica() -> list[dict]:
    """
    Scrape concerts from tvornica.hr (Tvornica Kulture).
    """
    events = []
    print("Scraping tvornica.hr …")
    soup = get("https://www.tvornica.hr/program")
    if not soup:
        return events

    for card in soup.select(".event, article, .concert, .show, li[class*='event']")[:20]:
        try:
            title_el = card.select_one("h2, h3, .title, strong")
            date_el  = card.select_one(".date, time, [class*='date']")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 4:
                continue

            date_raw = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date(date_raw) if date_raw else None
            if not date:
                continue

            link_el = card.select_one("a[href]")
            url = link_el["href"] if link_el else "https://www.tvornica.hr"
            if url.startswith("/"):
                url = "https://www.tvornica.hr" + url

            # Try to get time
            time_match = re.search(r"\b(\d{1,2}:\d{2})\b", card.get_text())
            event_time = time_match.group(1) if time_match else ""

            events.append({
                "id": make_id(title, date),
                "title": title,
                "date": date,
                "time": event_time,
                "location": "Tvornica Kulture",
                "category": "Music",
                "description": "",
                "url": url,
                "source": "tvornica.hr",
            })
        except Exception:
            continue

    print(f"  → {len(events)} events from tvornica.hr")
    return events


def scrape_hnk() -> list[dict]:
    """
    Scrape theatre events from hnk.hr (Hrvatsko narodno kazalište).
    """
    events = []
    print("Scraping hnk.hr …")
    soup = get("https://www.hnk.hr/program")
    if not soup:
        return events

    for card in soup.select("article, .event, .performance, li[class*='show']")[:20]:
        try:
            title_el = card.select_one("h2, h3, h4, .title")
            date_el  = card.select_one(".date, time, [class*='date']")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 4:
                continue

            date_raw = date_el.get_text(strip=True) if date_el else ""
            date = normalize_date(date_raw) if date_raw else None
            if not date:
                continue

            link_el = card.select_one("a[href]")
            url = link_el["href"] if link_el else "https://www.hnk.hr"
            if url.startswith("/"):
                url = "https://www.hnk.hr" + url

            time_match = re.search(r"\b(\d{1,2}:\d{2})\b", card.get_text())
            event_time = time_match.group(1) if time_match else ""

            events.append({
                "id": make_id(title, date),
                "title": title,
                "date": date,
                "time": event_time,
                "location": "Hrvatsko narodno kazalište",
                "category": "Theatre",
                "description": "",
                "url": url,
                "source": "hnk.hr",
            })
        except Exception:
            continue

    print(f"  → {len(events)} events from hnk.hr")
    return events


# ─────────────────────────────────────────
# CATEGORIZER
# ─────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "Music":    ["concert", "koncert", "jazz", "rock", "electronic", "dj", "band", "glazba", "festival of music", "hip-hop", "punk", "metal"],
    "Festival": ["festival", "fair", "sajam", "street food", "karneval", "advent"],
    "Art":      ["exhibition", "izložba", "art", "galerija", "gallery", "museum", "muzej", "photo", "foto"],
    "Theatre":  ["theatre", "kazalište", "opera", "ballet", "balet", "drama", "komedija", "comedy"],
    "Sport":    ["marathon", "maraton", "football", "soccer", "basketball", "košarka", "run", "trka", "sport", "tournament"],
    "Other":    [],
}

def categorize(title: str) -> str:
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "Other"


# ─────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────

def deduplicate(events: list[dict]) -> list[dict]:
    """Remove duplicate events by ID, keeping first occurrence."""
    seen = set()
    unique = []
    for ev in events:
        if ev["id"] not in seen:
            seen.add(ev["id"])
            unique.append(ev)
    return unique


# ─────────────────────────────────────────
# FILTER BY DATE
# ─────────────────────────────────────────

def filter_future_events(events: list[dict], days_ahead: int = 60) -> list[dict]:
    """Keep only events from today up to `days_ahead` days in the future."""
    today = datetime.now().date()
    cutoff = today + timedelta(days=days_ahead)
    filtered = []
    for ev in events:
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if today <= ev_date <= cutoff:
                filtered.append(ev)
        except Exception:
            pass
    return filtered


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("Zagreb Events Scraper")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    all_events = []

    scrapers = [
        scrape_entrio,
        scrape_infozagreb,
        scrape_tvornica,
        scrape_hnk,
    ]

    for scraper in scrapers:
        try:
            results = scraper()
            all_events.extend(results)
        except Exception as e:
            print(f"  [!] Scraper {scraper.__name__} crashed: {e}")
        time.sleep(1)  # Be polite to servers

    # Deduplicate and filter
    all_events = deduplicate(all_events)
    all_events = filter_future_events(all_events, days_ahead=60)

    # Sort by date
    all_events.sort(key=lambda e: e["date"])

    print(f"\nTotal unique future events: {len(all_events)}")

    # Build output
    output = {
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "events": all_events,
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("events.json saved successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
