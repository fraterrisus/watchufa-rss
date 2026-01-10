from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dateutil import parser
from html import escape
import logging.handlers
import requests
from requests.adapters import HTTPAdapter
from requests.models import Response
import sqlite3
from time import sleep
from typing import Optional
from urllib3.util import Retry
from xml.etree import ElementTree as ET


base_url = "https://watchufa.com/league/news"
dbfile = ".etag.db"
rfc822 = "%a, %d %b %Y %H:%M:%S %z"

logger = logging.getLogger("watchufa")
logger.setLevel(logging.DEBUG)
log_handler = logging.handlers.RotatingFileHandler(
    "watchufa.log",
    maxBytes=1024 * 1024,
    backupCount=5
)
log_formatter = logging.Formatter('{asctime} {name} {levelname:8s} {message}', style='{')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)

retry_strat = Retry(total=5)
adapter = HTTPAdapter(max_retries=retry_strat)
session = requests.Session()
session.mount("http://", adapter)
session.mount("https://", adapter)

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

def read_etags() -> dict:
    con = sqlite3.connect(dbfile)
    con.row_factory = dict_factory
    cur = con.cursor()

    res = cur.execute("SELECT name FROM sqlite_master where name='etag'")
    if res.fetchone() is None:
        cur.execute("CREATE TABLE etag(link TEXT PRIMARY KEY,etag TEXT,date INTEGER,body TEXT)")

    res = cur.execute("SELECT link,etag,date,body from etag")
    tags = dict()
    while (r := res.fetchone()) is not None:
        if r['date'] != '':
            r['date'] = datetime.fromtimestamp(r['date'], timezone.utc).strftime(rfc822)
        tags[r['link']] = r

    con.close()
    return tags

def write_etags(values: list[dict]):
    con = sqlite3.connect(dbfile)
    cur = con.cursor()

    for val in values:
        if 'date' in val:
            val['date'] = int(parser.parse(val['date']).timestamp())

    sql = "INSERT INTO etag (link,etag,date,body) VALUES(:link,:etag,:date,:body) " \
        "ON CONFLICT DO UPDATE SET etag=excluded.etag,date=excluded.date,body=excluded.body"
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
            "link": f"https://watchufa.com{link['href']}",
            "body": "",
        }
        if img is not None:
            a['img'] = img['src']
        articles.append(a)

    return articles

def get_body(article: dict) -> None:
    """
    Makes a web request to pull the body of an article. If `article['body']` and `article['etag']` are both present,
    it will pass the ETag along in the headers, and if the response is 304 NOT MODIFIED, takes no action and makes
    no further changes. If the response is 200 OK, the 'etag', 'date', and 'body' fields will be updated with the
    newly-downloaded data.

    :param article: A dict containing (at least) 'link'
    """

    etag = None
    if 'body' in article and article['body'] is not None and 'etag' in article:
        etag = article['etag']

    response = get_with_backoff(article['link'], etag)
    if response is None:
        return

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

        if 'date' in article and article['date'] is not None:
            pub_date_child = ET.SubElement(item, 'pubDate')
            pub_date_child.text = article['date']

        if 'body' in article and article['body'] is not None:
            description_child = ET.SubElement(item, 'description')
            description_child.text = article['body']

    return ET.ElementTree(root)

def get_with_backoff(url:str, etag:Optional[str]=None) -> Optional[Response]:
    headers = {}
    msg = f"GET ({url}"
    if etag is not None and etag != '':
        headers['If-None-Match'] = etag
        msg += f", {etag}"
    msg += ")"

    retries = 0
    while retries < 5:
        try:
            response = session.get(url, headers=headers)
            logger.info(f"{msg} -> {response.status_code}")
            if response.status_code == 304: # Not Modified
                return None
            elif response.status_code == 200: # OK
                return response
            else:
                sleep(1 + (2 ** retries))
                retries = retries + 1
        except ConnectionError:
            logger.warning(f"{msg} -> connection error")
            sleep(1 + (2 ** retries))
            retries = retries + 1

    raise

if __name__ == '__main__':
    logger.info("Starting up...")
    old_etags = read_etags()

    etag = None
    if base_url in old_etags:
        etag = old_etags[base_url]['etag']

    response = get_with_backoff(base_url, etag)
    if response is None:
        exit()

    base_etag = response.headers['Etag']
    last_mod = response.headers['Last-Modified']

    articles = get_links(response.content)

    for article in articles:
        if article['link'] in old_etags:
            for key in old_etags[article['link']]:
                article[key] = old_etags[article['link']][key]

        get_body(article)

    doc = write_rss(articles, last_mod)
    doc.write("watchufa.rss", encoding="utf-8")

    new_etags = [{'link': base_url, 'etag': base_etag, 'date': last_mod, 'body': ''}]
    for article in articles:
        new_etags.append(article)
    write_etags(new_etags)
