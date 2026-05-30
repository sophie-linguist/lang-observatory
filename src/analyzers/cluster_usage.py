"""신어 후보 단어 × 매체 단위 용례 클러스터링.

흐름:
1. segment_lemma_map + embeddings + texts JOIN으로
   (lemma, pos, source_id) 조합의 세그먼트 임베딩 수집
2. 샘플링 (max_samples 초과 시 random)
3. UMAP으로 차원 축소 (1024 → 10)
4. HDBSCAN으로 클러스터링
5. usage_clusters + usage_cluster_members에 저장
6. 클러스터별 대표 용례 출력 (검증용)
"""
import os
import sys
import random

import numpy as np
import umap
import hdbscan

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

MAX_SAMPLES = 1000
MIN_SAMPLES = 30
UMAP_DIMS = 10
RANDOM_SEED = 42


def get_candidate_id(cur, lemma):
    cur.execute("""
        SELECT candidate_id FROM neologism_candidates
        WHERE lemma = %s LIMIT 1
    """, (lemma,))
    row = cur.fetchone()
    return row[0] if row else None


def get_segment_embeddings(cur, lemma, pos, source_id):
    """segment_lemma_map에서 lemma가 등장한 세그먼트의 임베딩 가져오기."""
    pos_list = pos.split("·") if "·" in pos else [pos]

    if source_id == 7:
        cur.execute("""
            SELECT e.embedding_id, e.embedding
            FROM segment_lemma_map m
            JOIN embeddings e ON m.embedding_id = e.embedding_id
            WHERE m.lemma = %s AND m.pos = ANY(%s)
              AND e.comment_id IS NOT NULL
        """, (lemma, pos_list))
    else:
        cur.execute("""
            SELECT e.embedding_id, e.embedding
            FROM segment_lemma_map m
            JOIN embeddings e ON m.embedding_id = e.embedding_id
            JOIN texts t ON e.text_id = t.text_id
            WHERE m.lemma = %s AND m.pos = ANY(%s) AND t.source_id = %s
        """, (lemma, pos_list, source_id))

    rows = cur.fetchall()
    if not rows:
        return [], np.array([])

    embedding_ids = [r[0] for r in rows]
    vectors = np.array([
        eval(r[1]) if isinstance(r[1], str) else list(r[1])
        for r in rows
    ], dtype=np.float32)

    return embedding_ids, vectors


def cluster_vectors(vectors):
    n = len(vectors)
    reducer = umap.UMAP(
        n_components=UMAP_DIMS,
        random_state=RANDOM_SEED,
        n_neighbors=min(15, n - 1),
        metric='cosine'
    )
    reduced = reducer.fit_transform(vectors)

    min_cluster_size = max(5, int(n ** 0.5))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric='euclidean'
    )
    labels = clusterer.fit_predict(reduced)
    return labels, reduced


def save_clusters(cur, candidate_id, lemma, pos, source_id, labels, vectors, embedding_ids):
    saved_cluster_ids = []
    unique_labels = sorted(set(labels))

    for cluster_label in unique_labels:
        if cluster_label == -1:
            continue

        member_idx = np.where(labels == cluster_label)[0]
        member_count = len(member_idx)
        member_vectors = vectors[member_idx]
        centroid = member_vectors.mean(axis=0)

        cur.execute("""
            INSERT INTO usage_clusters
                (candidate_id, lemma, pos, source_id, centroid, member_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING cluster_id
        """, (candidate_id, lemma, pos, source_id, centroid.tolist(), member_count))
        cluster_id = cur.fetchone()[0]
        saved_cluster_ids.append(cluster_id)

        for i in member_idx:
            sim = float(np.dot(vectors[i], centroid) /
                       (np.linalg.norm(vectors[i]) * np.linalg.norm(centroid)))
            cur.execute("""
                INSERT INTO usage_cluster_members
                    (cluster_id, embedding_id, similarity)
                VALUES (%s, %s, %s)
            """, (cluster_id, embedding_ids[i], sim))

    return saved_cluster_ids


def print_cluster_samples(cur, cluster_ids, top_k=3):
    for cluster_id in cluster_ids:
        cur.execute("""
            SELECT m.similarity, e.segment_text
            FROM usage_cluster_members m
            JOIN embeddings e ON m.embedding_id = e.embedding_id
            WHERE m.cluster_id = %s
            ORDER BY m.similarity DESC
            LIMIT %s
        """, (cluster_id, top_k))
        rows = cur.fetchall()

        cur.execute("""
            SELECT member_count FROM usage_clusters WHERE cluster_id = %s
        """, (cluster_id,))
        member_count = cur.fetchone()[0]

        print(f"\n  [클러스터 {cluster_id}] {member_count}건")
        for sim, segment_text in rows:
            if segment_text is None:
                continue
            preview = segment_text[:120] + "..." if len(segment_text) > 120 else segment_text
            preview = preview.replace('\n', ' ')
            print(f"    sim={sim:.3f} | {preview}")


def run_cluster(lemma, pos, source_id):
    print(f"\n{'='*60}")
    print(f"클러스터링: {lemma} × source_id={source_id}")
    print('='*60)

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT cluster_id FROM usage_clusters
            WHERE lemma = %s AND pos = %s AND source_id = %s
        """, (lemma, pos, source_id))
        old_cluster_ids = [row[0] for row in cur.fetchall()]
        if old_cluster_ids:
            cur.execute("DELETE FROM usage_cluster_members WHERE cluster_id = ANY(%s)", (old_cluster_ids,))
            cur.execute("DELETE FROM usage_clusters WHERE cluster_id = ANY(%s)", (old_cluster_ids,))
            print(f"  기존 클러스터 {len(old_cluster_ids)}개 삭제")

        candidate_id = get_candidate_id(cur, lemma)
        if candidate_id is None:
            print(f"  '{lemma}'는 신어 후보 아님 — 등재어 클러스터링으로 진행")
        else:
            print(f"  candidate_id: {candidate_id}")

        embedding_ids, vectors = get_segment_embeddings(cur, lemma, pos, source_id)
        print(f"  세그먼트 임베딩: {len(embedding_ids):,}건")

        if len(embedding_ids) < MIN_SAMPLES:
            print(f"  용례 부족 ({len(embedding_ids)} < {MIN_SAMPLES})")
            return {'status': 'skip_too_few', 'n_samples': len(embedding_ids)}

        if len(embedding_ids) > MAX_SAMPLES:
            random.seed(RANDOM_SEED)
            indices = random.sample(range(len(embedding_ids)), MAX_SAMPLES)
            embedding_ids = [embedding_ids[i] for i in indices]
            vectors = vectors[indices]
            print(f"  샘플링: {MAX_SAMPLES}건으로 축소")

        print(f"  UMAP + HDBSCAN 실행 중...")
        labels, reduced = cluster_vectors(vectors)

        unique_labels = set(labels)
        n_noise = (labels == -1).sum()
        n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        print(f"  결과: {n_clusters}개 클러스터, 노이즈 {n_noise}건")

        if n_clusters == 0:
            print(f"  의미 있는 클러스터 없음")
            return {'status': 'no_clusters', 'n_samples': len(embedding_ids), 'n_noise': int(n_noise)}

        cluster_ids = save_clusters(cur, candidate_id, lemma, pos, source_id, labels, vectors, embedding_ids)
        conn.commit()
        print(f"  저장 완료: cluster_id {cluster_ids}")

        print_cluster_samples(cur, cluster_ids, top_k=3)

        return {
            'status': 'success',
            'candidate_id': candidate_id,
            'source_id': source_id,
            'n_samples': len(embedding_ids),
            'n_clusters': n_clusters,
            'n_noise': int(n_noise),
            'cluster_ids': cluster_ids,
        }

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    runs = [
        ('긁히다', 'VV', 6),
        ('긁히다', 'VV', 7),
    ]
    results = []
    for lemma, pos, source_id in runs:
        result = run_cluster(lemma, pos, source_id)
        results.append((lemma, pos, source_id, result))

    print(f"\n\n{'='*60}")
    print("=== 전체 요약 ===")
    print('='*60)
    for lemma, pos, source_id, result in results:
        status = result.get('status')
        if status == 'success':
            print(f"  {lemma}/{pos} x source={source_id}: "
                  f"{result['n_clusters']}개 클러스터 "
                  f"({result['n_samples']}건, 노이즈 {result['n_noise']})")
        else:
            print(f"  {lemma}/{pos} x source={source_id}: {status}")
