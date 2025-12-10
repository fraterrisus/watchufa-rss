from bs4 import BeautifulSoup
from datetime import datetime, timezone
from html import escape
import requests
from requests.adapters import HTTPAdapter
import sqlite3
from time import sleep
from urllib3.util import Retry
from xml.etree import ElementTree as ET


base_url = "https://watchufa.com/league/news"
dbfile = ".etag.db"
rfc822 = "%a, %d %b %Y %H:%M:%S %z"

retry_strat = Retry(total=5)
adapter = HTTPAdapter(max_retries=retry_strat)
session = requests.Session()
session.mount("http://", adapter)
session.mount("https://", adapter)

def read_etags() -> dict:
    con = sqlite3.connect(dbfile)
    cur = con.cursor()

    res = cur.execute("SELECT name FROM sqlite_master where name='etag'")
    if res.fetchone() is None:
        cur.execute("CREATE TABLE etag(url TEXT PRIMARY KEY,tag TEXT,body TEXT)")

    res = cur.execute("SELECT url,tag,body from etag")
    tags = dict()
    while True:
        r = res.fetchone()
        if r is None:
            break
        tags[r[0]] = (r[1], r[2])

    con.close()
    return tags

def write_etags(values: list[dict]):
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    sql = "INSERT INTO etag (url,tag,body) VALUES(:url,:tag,:body) " \
        "ON CONFLICT DO UPDATE SET tag=excluded.tag,body=excluded.body"
    cur.executemany(sql, values)
    con.commit()
    con.close()

def get_links(body: bytes) -> list[dict]:
    soup = BeautifulSoup(body, "html.parser")
    articles = []
    for article in soup.select(".view-league-page-general-news .views-row"):
        img = article.select_one(".views-field-field-image img")
        link = article.select_one(".views-field-title a")
        a = {
            "title": link.text,
            "link": f"https://watchufa.com{link['href']}"
        }
        if img is not None:
            a['img'] = img['src']
        articles.append(a)

    return articles

def get_body(article: dict):
    print(f"HEAD {article['link']}")
    response = session.head(article['link'])

    if 'etag' in article and 'body' in article and response.headers['Etag'] == article['etag']:
        return

    response = get_with_backoff(article['link'])

    article['etag'] = response.headers['Etag']
    article['date'] = response.headers['Last-Modified']

    soup = BeautifulSoup(response.content, "html.parser")

    body = soup.select_one("meta[property='og:description']")
    if body is not None:
        article['body'] = escape(body['content'])

    date = soup.select_one("meta[property='article:published_time']")
    if date is not None:
        article['date'] = datetime.fromisoformat(date['content']).strftime(rfc822)

def write_rss(articles: list[dict], last_mod: str) -> ET.ElementTree:
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
        title_child.text = article['title']

        link_child = ET.SubElement(item, 'link')
        link_child.text = article['link']

        if article['date'] is not None:
            pub_date_child = ET.SubElement(item, 'pubDate')
            pub_date_child.text = article['date']

        if article['body'] is not None:
            description_child = ET.SubElement(item, 'description')
            description_child.text = article['body']

    return ET.ElementTree(root)

def get_with_backoff(url):
    retries = 0
    while retries < 5:
        print(f"GET {url}")
        response = session.get(url)
        if response.status_code == 200:
            return response
        else:
            sleep(1 + (2 ** retries))
            retries = retries + 1

    raise

if __name__ == '__main__':
    old_etags = read_etags()
    print(f"HEAD {base_url}")
    response = session.head(base_url)
    base_etag = response.headers['Etag']

    if base_url in old_etags and base_etag == old_etags[base_url][0]:
        exit(201)

    response = get_with_backoff(base_url)
    last_mod = response.headers['Last-Modified']
    articles = get_links(response.content)

    for article in articles:
        if article['link'] in old_etags:
            article['etag'] = old_etags[article['link']][0]
            article['body'] = old_etags[article['link']][1]

        get_body(article)

    doc = write_rss(articles, last_mod)
    doc.write("watchufa.rss", encoding="utf-8")

    new_etags = [{'url': base_url, 'tag': base_etag, 'body': ''}]
    for article in articles:
        new_etags.append({'url': article['link'], 'tag': article['etag'], 'body': article['body']})
    write_etags(new_etags)

    exit(0)
