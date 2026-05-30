import json, glob, os, sys
from db import get_conn

def load_file(filepath, conn, source_id):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)

    cur = conn.cursor()

    for doc in data.get('document', []):
        doc_id = doc['id']
        meta = doc.get('metadata', {})
        title = meta.get('title', '')
        author = meta.get('author', '')
        publisher = meta.get('publisher', '')
        date_str = meta.get('date', '')
        published = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 else None

        # 문단을 합쳐서 기사 본문으로
        paragraphs = doc.get('paragraph', [])
        content = '\n'.join(p['form'] for p in paragraphs)

        if not content.strip():
            continue

        try:
            cur.execute("""
                INSERT INTO texts (source_id, external_id, title, content, author, published_at, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, external_id) DO NOTHING
            """, (source_id, doc_id, title, content, f"{author}({publisher})", published, None))
        except Exception as e:
            print(f"  에러: {doc_id} - {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()

def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT source_id FROM sources WHERE name = '모두의말뭉치_신문'")
    source_id = cur.fetchone()[0]
    cur.close()

    files = sorted(glob.glob('data/corpus/NIKL_NEWSPAPER_*/**/*.json', recursive=True))
    print(f"신문 파일 {len(files)}개 발견")

    for i, f in enumerate(files):
        load_file(f, conn, source_id)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(files)} 완료")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM texts WHERE source_id = %s", (source_id,))
    count = cur.fetchone()[0]
    print(f"\n완료! texts 테이블에 {count}건 적재됨")
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
