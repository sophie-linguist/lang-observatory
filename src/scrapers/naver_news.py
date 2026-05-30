"""네이버 뉴스 검색 API 수집기"""
import os, re, sys, html, time
from datetime import datetime
from email.utils import parsedate_to_datetime
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

load_dotenv()
NAVER_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_SECRET = os.getenv("NAVER_CLIENT_SECRET")
SOURCE_ID = 3

API_URL = "https://openapi.naver.com/v1/search/news.json"
HEADERS = {
    "X-Naver-Client-Id": NAVER_ID,
    "X-Naver-Client-Secret": NAVER_SECRET,
    "User-Agent": "lang-observatory/0.1; research",
}
TAG_RE = re.compile(r'<[^>]+>')


def clean(s):
    if not s: return ""
    return html.unescape(TAG_RE.sub('', s)).strip()


def parse_date(s):
    try: return parsedate_to_datetime(s).replace(tzinfo=None)
    except: return None


def search_news(query, display=100, start=1):
    params = {"query": query, "display": display, "start": start, "sort": "date"}
    r = requests.get(API_URL, headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def save_items(cur, items):
    saved = 0
    dedup_skipped = 0
    for it in items:
        url = it.get("originallink") or it.get("link")
        if not url: continue
        content = clean(it.get("description"))
        # dedup: 같은 LEFT(content, 80)가 이미 있으면 skip
        if content:
            prefix = content[:80]
            cur.execute(
                "SELECT 1 FROM texts WHERE source_id=%s AND LEFT(content, 80)=%s LIMIT 1",
                (SOURCE_ID, prefix)
            )
            if cur.fetchone():
                dedup_skipped += 1
                continue
        cur.execute("""
            INSERT INTO texts
            (source_id, external_id, title, content, author, published_at, collected_at, url, is_processed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            SOURCE_ID, url[:500],
            clean(it.get("title"))[:500],
            content,
            None,
            parse_date(it.get("pubDate")),
            datetime.now(),
            url,
            False,
        ))
        saved += cur.rowcount
    return saved, dedup_skipped

def collect(keywords, per_keyword=100):
    conn = get_conn()
    cur = conn.cursor()
    total = 0
    total_dedup = 0
    for kw in keywords:
        try:
            data = search_news(kw, display=per_keyword)
            items = data.get("items", [])
            new, dedup = save_items(cur, items)
            conn.commit()
            print(f"  {kw}: 수신 {len(items)} / 신규 {new} / dedup skip {dedup}")
            total += new
            total_dedup += dedup
            time.sleep(0.2)
        except Exception as e:
            print(f"  {kw}: 실패 - {e}")
            conn.rollback()
    cur.close()
    conn.close()
    print(f"\n[완료] 총 신규 {total}건 / dedup skip {total_dedup}건")

if __name__ == "__main__":
    keywords = [
        "오늘", "어제", "발표", "공개",
        "정치", "경제", "사회", "문화", "스포츠", "국제",
        "정부", "한국",
    ]
    collect(keywords, per_keyword=100)
