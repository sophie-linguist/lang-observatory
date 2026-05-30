"""
표준국어대사전 JSONL → urimalsaem_entries 적재 스크립트
(같은 테이블에 dict_source='stdict'로 구분 저장)
"""
import csv
import io
import json
import sys
import time
from pathlib import Path
from db import get_conn

JSONL_PATH = Path.home() / "lang-observatory" / "stdict.jsonl"
BATCH_SIZE = 20000
DICT_SOURCE = "stdict"

COLUMNS = [
    "headword", "pos", "sense_number", "definition", "source_code",
    "word_unit", "word_type", "sense_type", "sense_category",
    "pronunciation", "conjugation", "examples", "relations", "link", "raw",
    "dict_source",
]


def truncate(s, n):
    if s is None:
        return None
    s = str(s)
    return s[:n] if len(s) > n else s


def to_jsonb(obj):
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def row_from_record(rec):
    headword = rec.get("headword")
    pos = rec.get("pos")
    sense_number = rec.get("sense_number")
    
    if not headword:
        return None
    if sense_number is None:
        sense_number = 1
    
    # target_code를 source_code로 매핑 (참조용)
    target_code = rec.get("target_code", "")
    
    return (
        truncate(headword, 100),
        truncate(pos, 20),
        int(sense_number),
        rec.get("definition"),
        truncate(str(target_code) if target_code else "", 50),
        truncate(rec.get("word_unit"), 20),
        truncate(rec.get("word_type"), 20),
        truncate(rec.get("sense_type"), 20),
        truncate(rec.get("sense_category"), 50),
        truncate(rec.get("pronunciation"), 100),
        rec.get("conjugation"),
        to_jsonb(rec.get("examples")),
        to_jsonb(rec.get("relations")),
        truncate(rec.get("link"), 200),
        to_jsonb(rec.get("raw")),
        DICT_SOURCE,  # 'stdict' 명시
    )


def flush_buffer(cur, rows):
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    for r in rows:
        writer.writerow(["" if v is None else v for v in r])
    buf.seek(0)
    cur.copy_expert(
        f"COPY urimalsaem_entries ({','.join(COLUMNS)}) "
        f"FROM STDIN WITH (FORMAT csv, NULL '')",
        buf,
    )


def main():
    if not JSONL_PATH.exists():
        print(f"[ERROR] 파일 없음: {JSONL_PATH}")
        sys.exit(1)
    
    print(f"[INFO] 적재 시작: {JSONL_PATH}")
    print(f"[INFO] dict_source = '{DICT_SOURCE}'")
    
    t0 = time.time()
    conn = get_conn()
    cur = conn.cursor()
    
    # 중복 제거 키: (headword, pos, sense_number, dict_source)
    seen = set()
    rows = []
    total_read = 0
    total_inserted = 0
    skipped_dup = 0
    skipped_bad = 0
    
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            total_read += 1
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped_bad += 1
                continue
            
            row = row_from_record(rec)
            if row is None:
                skipped_bad += 1
                continue
            
            # 키: (headword, pos, sense_number) — dict_source는 동일하니 생략
            key = (row[0], row[1], row[2])
            if key in seen:
                skipped_dup += 1
                continue
            seen.add(key)
            
            rows.append(row)
            
            if len(rows) >= BATCH_SIZE:
                flush_buffer(cur, rows)
                conn.commit()
                total_inserted += len(rows)
                rows = []
                elapsed = time.time() - t0
                rate = total_inserted / elapsed if elapsed else 0
                print(f"  진행: 읽음 {total_read:,} / 적재 {total_inserted:,} "
                      f"({rate:.0f}행/초)")
        
        if rows:
            flush_buffer(cur, rows)
            conn.commit()
            total_inserted += len(rows)
    
    cur.close()
    conn.close()
    
    elapsed = time.time() - t0
    print()
    print("=" * 50)
    print(f"[완료] 소요 시간: {elapsed/60:.1f}분")
    print(f"  읽음:        {total_read:,}")
    print(f"  적재:        {total_inserted:,}")
    print(f"  중복 제외:   {skipped_dup:,}")
    print(f"  손상/누락:   {skipped_bad:,}")


if __name__ == "__main__":
    main()
