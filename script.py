from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, timezone
import requests
from xml.etree import ElementTree as ET

@dataclass
class Article:
    img: str
    title: str
    link: str

base_url = "https://watchufa.com/league/news"

def get_links() -> list[Article]:
    response = requests.get(base_url)
    soup = BeautifulSoup(response.content, "html.parser")
    articles: list[Article] = []
    for article in soup.select(".view-league-page-general-news .views-row"):
        img = article.select_one(".views-field-field-image img")
        if img is not None:
            img = img["src"]
        link = article.select_one(".views-field-title a")
        title = link.text
        url = base_url + link['href']
        articles.append(Article(img=img, title=title, link=url))
    return articles

def write_rss(articles: list[Article]) -> ET.ElementTree:
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
        'lastBuildDate': timestamp,
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
    articles = get_links()
    doc = write_rss(articles)
    doc.write("watchufa.rss", encoding="utf-8")
