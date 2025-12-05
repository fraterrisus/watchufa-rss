from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import requests
from xml.etree import ElementTree as ET

@dataclass
class Article:
    img: str
    title: str
    link: str

base_url = "https://watchufa.com/league/news"

def read_etag() -> str:
    if os.path.isfile(".etag"):
        with open(".etag", 'r') as f:
            etag = f.read()
        return etag
    else:
        return ""

def write_etag(etag: str):
    with open(".etag", "w") as f:
        f.write(etag)

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
        articles.append(Article(img=img, title=title, link=url))
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

    return ET.ElementTree(root)

if __name__ == '__main__':
    etag = read_etag()
    response = requests.head(base_url)
    if response.headers['Etag'] == etag:
        exit(201)
    else:
        write_etag(response.headers['Etag'])

    response = requests.get(base_url)
    last_mod = response.headers['Last-Modified']
    articles = get_links(response.content)
    doc = write_rss(articles, last_mod)
    doc.write("watchufa.rss", encoding="utf-8")
    exit(0)
