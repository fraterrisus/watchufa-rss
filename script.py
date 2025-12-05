from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import requests
import sqlite3
from typing import Optional
from xml.etree import ElementTree as ET

@dataclass
class Article:
    img: Optional[str]
    title: str
    link: str
    body: Optional[str]

base_url = "https://watchufa.com/league/news"
dbfile = ".etag.db"

def read_etag() -> dict:
    con = sqlite3.connect(dbfile)
    cur = con.cursor()

    res = cur.execute("SELECT name FROM sqlite_master where name='etag'")
    if res.fetchone() is None:
        cur.execute("CREATE TABLE etag(url TEXT PRIMARY KEY,tag TEXT)")

    res = cur.execute("SELECT url,tag from etag")
    tags = dict(res.fetchall())

    con.close()
    return tags

def write_etag(tags: dict):
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    values = [(url, tags[url]) for url in tags]
    sql = "INSERT INTO etag (url,tag) VALUES(?,?)" \
        "ON CONFLICT DO UPDATE SET tag=excluded.tag"
    cur.executemany(sql, values)
    con.commit()
    con.close()

def get_links(body: bytes) -> list[Article]:
    soup = BeautifulSoup(body, "html.parser")
    articles: list[Article] = []
    for article in soup.select(".view-league-page-general-news .views-row"):
        img = article.select_one(".views-field-field-image img")
        if img is not None:
            img = img["src"]
        link = article.select_one(".views-field-title a")
        title = link.text
        url = f"https://watchufa.com{link['href']}"
        articles.append(Article(img=img, title=title, link=url, body=None))
    return articles

def write_rss(articles: list[Article], last_mod: str) -> ET.ElementTree:
    rfc822 = "%a, %d %b %Y %H:%M:%S %z"
    timestamp = datetime.now(timezone.utc).strftime(rfc822)

    root = ET.Element('rss', {"xmlns:atom": "http://www.w3.org/2005/Atom", "version": "2.0"})
    channel = ET.SubElement(root, 'channel')

    channel_children = {
        'title': 'UFA League News',
        'link': base_url,
        'description': 'The latest news from the Ultimate Frisbee Association',
        'language': 'en-US',
        'pubDate': timestamp,
        'lastBuildDate': last_mod,
        'generator': 'watchufa-rss.py',
    }
    for tag in channel_children:
        child = ET.SubElement(channel, tag)
        child.text = channel_children[tag]

    ET.SubElement(channel, 'atom:link', {
        'href': 'https://stuff.hitchhikerprod.com/watchufa.rss',
        'rel': 'self',
        'type': 'application/rss+xml',
    })

    for article in articles:
        item = ET.SubElement(channel, 'item')

        title_child = ET.SubElement(item, 'title')
        title_child.text = article.title

        link_child = ET.SubElement(item, 'link')
        link_child.text = article.link

        if article.body is not None:
            description_child = ET.SubElement(item, 'description')
            description_child.text = escape(article.body)

    return ET.ElementTree(root)

if __name__ == '__main__':
    etags = read_etag()
    response = requests.head(base_url)
    if base_url in etags and response.headers['Etag'] == etags[base_url]:
        exit(201)
    else:
        etags[base_url] = response.headers['Etag']
        write_etag(etags)

    response = requests.get(base_url)
    last_mod = response.headers['Last-Modified']
    articles = get_links(response.content)
    doc = write_rss(articles, last_mod)
    doc.write("watchufa.rss", encoding="utf-8")
    exit(0)
