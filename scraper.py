#!/usr/bin/env python3
"""
Génère un flux RSS (podcast) pour l'émission "Évolution minimale" de CFM Radio,
à partir de https://www.cfmradio.fr/emissions/evolution-minimale

Le flux est écrit dans docs/rss.xml pour être servi par GitHub Pages.
"""
import re
import os
import requests
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from bs4 import BeautifulSoup

BASE_URL = "https://www.cfmradio.fr"
LISTING_URL = f"{BASE_URL}/emissions/evolution-minimale"
EMISSION_NAME = "Évolution minimale"
MAX_PAGES = 2          # nombre de pages de la liste à parcourir (pagination=0,1,...)
OUTPUT_PATH = "docs/rss.xml"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PodcastFeedBot/1.0)"}

MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-zéûî]+)\s+(\d{4})")
DURATION_RE = re.compile(r"(\d+\s*h\s*\d*\s*min|\d+\s*min)")


def parse_french_date(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    day, month_name, year = m.groups()
    month = MONTHS_FR.get(month_name.lower())
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def collect_episode_links():
    """Parcourt les pages de la liste d'épisodes et renvoie les URLs uniques."""
    links = []
    seen = set()
    for page in range(MAX_PAGES):
        url = LISTING_URL if page == 0 else f"{LISTING_URL}?pagination={page}"
        try:
            soup = get_soup(url)
        except requests.RequestException:
            break

        found_on_page = 0
        for a in soup.find_all("a", href=True):
            bold = a.find(["strong", "b"])
            if not bold or bold.get_text(strip=True) != EMISSION_NAME:
                continue
            href = a["href"]
            full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
                found_on_page += 1

        if found_on_page == 0:
            break
    return links


def scrape_episode(url):
    """Récupère titre, description, date, durée et lien mp3 d'un épisode."""
    soup = get_soup(url)

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else url

    desc_meta = soup.find("meta", attrs={"property": "og:description"})
    description = desc_meta["content"].strip() if desc_meta and desc_meta.get("content") else ""

    mp3_link = None
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".mp3"):
            href = a["href"]
            mp3_link = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            break
    if not mp3_link:
        return None

    page_text = soup.get_text(" ", strip=True)
    pub_date = parse_french_date(page_text)
    duration_match = DURATION_RE.search(page_text)
    duration = duration_match.group(0) if duration_match else ""

    image_meta = soup.find("meta", attrs={"property": "og:image"})
    image_url = image_meta["content"] if image_meta and image_meta.get("content") else None

    return {
        "title": title,
        "link": url,
        "description": description,
        "mp3": mp3_link,
        "pub_date": pub_date or datetime.now(timezone.utc),
        "duration": duration,
        "image": image_url,
    }


def build_rss(episodes):
    items_xml = []
    for ep in episodes:
        items_xml.append(f"""
    <item>
      <title>{escape(ep['title'])}</title>
      <link>{escape(ep['link'])}</link>
      <guid isPermaLink="true">{escape(ep['link'])}</guid>
      <pubDate>{ep['pub_date'].strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>
      <description>{escape(ep['description'])}</description>
      <enclosure url="{escape(ep['mp3'])}" type="audio/mpeg" />
      <itunes:duration>{escape(ep['duration'])}</itunes:duration>
    </item>""")

    channel_image = episodes[0]["image"] if episodes and episodes[0].get("image") else ""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(EMISSION_NAME)} - CFM Radio (non officiel)</title>
    <link>{escape(LISTING_URL)}</link>
    <description>Flux non officiel généré automatiquement à partir du site cfmradio.fr</description>
    <language>fr-fr</language>
    <itunes:image href="{escape(channel_image)}" />
    <lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>
{"".join(items_xml)}
  </channel>
</rss>
"""
    return rss


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    links = collect_episode_links()
    print(f"{len(links)} épisode(s) trouvé(s).")

    episodes = []
    for link in links:
        try:
            ep = scrape_episode(link)
        except requests.RequestException as e:
            print(f"Erreur sur {link}: {e}")
            continue
        if ep:
            episodes.append(ep)

    episodes.sort(key=lambda e: e["pub_date"], reverse=True)

    rss_content = build_rss(episodes)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(rss_content)

    print(f"Flux RSS écrit dans {OUTPUT_PATH} ({len(episodes)} épisodes).")


if __name__ == "__main__":
    main()
