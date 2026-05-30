"""클러스터링 대상 단어의 용례 텍스트만 부분 임베딩.

흐름:
1. 단어 × 매체 조합별로 word_text_map에서 text_id 수집
2. MAX_SAMPLES만큼 랜덤 샘플
3. 이미 임베딩된 건 스킵
4. 나머지만 bge-m3로 임베딩 후 embeddings 테이블에 저장
"""
import os
import sys
import time
import random

from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_TYPE = "sentence"
BATCH_SIZE = 64
MAX_SAMPLES = 1000
RANDOM_SEED = 42

# 대상: (lemma, source_id)
TARGETS = [
    ('헬스케어', 6),
    ('확산세', 6),
    ('조성사업', 6),
]


def get_text_ids_to_embed(cur, lemma, source_id, max_samples):
    """word_text_map에서 (lemma, source_id) 조합의 text_id 수집 + 샘플링.
    
    이미 sentence 임베딩 있는 것은 제외.
    """
    # 전체 후보 가져오기
    cur.execute("""
        SELECT DISTINCT w.text_id
        FROM word_text_map w
        JOIN texts t ON w.text_id = t.text_id
        WHERE w.lemma = %s AND t.source_id = %s
    """, (lemma, source_id))
    all_ids = [r[0] for r in cur.fetchall()]
    
    # 샘플링
    if len(all_ids) > max_samples:
        random.seed(RANDOM_SEED)
        all_ids = random.sample(all_ids, max_samples)
    
    # 이미 임베딩된 것 제외
    cur.execute("""
        SELECT text_id FROM embeddings
        WHERE text_id = ANY(%s) AND embedding_type = %s
    """, (all_ids, EMBEDDING_TYPE))
    already_embedded = {r[0] for r in cur.fetchall()}
    
    to_embed = [tid for tid in all_ids if tid not in already_embedded]
    return to_embed, len(all_ids), len(already_embedded)


def fetch_contents(cur, text_ids):
    """text_id 리스트에 대응하는 content 가져오기."""
    cur.execute("""
        SELECT text_id, content FROM texts
        WHERE text_id = ANY(%s)
          AND content IS NOT NULL AND content != ''
    """, (text_ids,))
    return cur.fetchall()


def save_embeddings(cur, text_ids, vectors):
    for tid, vec in zip(text_ids, vectors):
        cur.execute("""
            INSERT INTO embeddings (text_id, embedding_type, embedding)
            VALUES (%s, %s, %s)
        """, (tid, EMBEDDING_TYPE, vec.tolist()))


def main():
    print(f"모델 로딩: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("모델 로딩 완료\n")
    
    conn = get_conn()
    cur = conn.cursor()
    
    # 모든 타깃의 임베딩 대상 수집
    all_to_embed = set()
    for lemma, source_id in TARGETS:
        to_embed, total, already = get_text_ids_to_embed(
            cur, lemma, source_id, MAX_SAMPLES
        )
        print(f"{lemma} × {source_id}: 샘플 {total}건, "
              f"이미 임베딩 {already}건, 신규 {len(to_embed)}건")
        all_to_embed.update(to_embed)
    
    all_to_embed = list(all_to_embed)
    total = len(all_to_embed)
    print(f"\n총 임베딩 대상: {total}건 (중복 제거 후)\n")
    
    if total == 0:
        print("처리할 데이터 없음")
        cur.close(); conn.close()
        return
    
    # 컨텐츠 가져오기
    rows = fetch_contents(cur, all_to_embed)
    print(f"content 조회됨: {len(rows)}건\n")
    
    # 배치 임베딩
    t0 = time.time()
    processed = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        text_ids = [r[0] for r in batch]
        contents = [r[1][:512] for r in batch]
        
        vectors = model.encode(contents, show_progress_bar=False)
        save_embeddings(cur, text_ids, vectors)
        conn.commit()
        
        processed += len(batch)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(f"  {processed}/{len(rows)} ({rate:.1f}건/초)", flush=True)
    
    elapsed = time.time() - t0
    print(f"\n[완료] {processed}건, {elapsed:.1f}초 소요")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
