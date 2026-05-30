"""문장 임베딩 → pgvector 저장 파이프라인"""
import os, sys, time
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

MODEL_NAME = "BAAI/bge-m3"
BATCH_SIZE = 64  # GPU 없으면 작게
EMBEDDING_TYPE = "sentence"

def get_unembedded_texts(cur):
    """아직 임베딩 안 된 texts 가져오기 (최근 30일 + NOT EXISTS 안티조인)"""
    cur.execute("""
        SELECT t.text_id, t.content
        FROM texts t
        WHERE t.content IS NOT NULL
          AND t.content != ''
          AND t.published_at > NOW() - INTERVAL '30 days'
          AND NOT EXISTS (
              SELECT 1 FROM embeddings e 
              WHERE e.text_id = t.text_id 
                AND e.embedding_type = %s
          )
        ORDER BY t.text_id DESC
    """, (EMBEDDING_TYPE,))
    return cur.fetchall()


def save_embeddings(cur, text_ids, vectors):
    """벡터 배열 → embeddings 테이블"""
    for tid, vec in zip(text_ids, vectors):
        cur.execute("""
            INSERT INTO embeddings (text_id, embedding_type, embedding)
            VALUES (%s, %s, %s)
        """, (tid, EMBEDDING_TYPE, vec.tolist()))


def main():
    print(f"모델 로딩: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("모델 로딩 완료")

    conn = get_conn()
    cur = conn.cursor()

    # 처리 대상 확인
    rows = get_unembedded_texts(cur)
    total = len(rows)
    print(f"임베딩 대상: {total}건")

    if total == 0:
        print("처리할 데이터 없음")
        cur.close(); conn.close()
        return

    t0 = time.time()
    processed = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        text_ids = [r[0] for r in batch]
        contents = [r[1][:512] for r in batch]  # 너무 긴 텍스트 잘라서 임베딩

        vectors = model.encode(contents, show_progress_bar=False)
        save_embeddings(cur, text_ids, vectors)
        conn.commit()

        processed += len(batch)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(f"  {processed}/{total} ({rate:.1f}건/초)")

    elapsed = time.time() - t0
    print(f"\n[완료] {processed}건, {elapsed:.1f}초 소요 ({processed/elapsed:.1f}건/초)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
