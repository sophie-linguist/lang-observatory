"""신어 후보 단어 × 매체 단위 용례 클러스터링.

흐름:
1. word_text_map에서 (lemma, source_id) 조합의 text_id 수집
2. 샘플링 (max_samples 초과 시 random)
3. embeddings에서 sentence 벡터 가져오기
4. UMAP으로 차원 축소 (1024 → 10)
5. HDBSCAN으로 클러스터링
6. usage_clusters + usage_cluster_members에 저장
7. 클러스터별 대표 용례 출력 (검증용)
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np
import umap
import hdbscan

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

# === 클러스터링 파라미터 ===
MAX_SAMPLES = 1000        # 단어×매체당 최대 샘플 수
MIN_SAMPLES = 30          # 미만이면 클러스터링 스킵
UMAP_DIMS = 10            # UMAP 축소 후 차원
RANDOM_SEED = 42          # 재현성 위해 고정

# === source_id 매핑 (참고용) ===
# 1: 에펨코리아 (미사용)
# 2: 더쿠 (미사용)
# 3: 네이버뉴스
# 4: 유튜브
# 5: 모두의말뭉치_일상대화
# 6: 모두의말뭉치_신문

def get_candidate_id(cur, lemma):
    """neologism_candidates에서 lemma의 candidate_id 조회.
    
    Returns:
        candidate_id (int) 또는 None
    """
    cur.execute("""
        SELECT candidate_id FROM neologism_candidates
        WHERE lemma = %s
        LIMIT 1
    """, (lemma,))
    row = cur.fetchone()
    return row[0] if row else None

def get_text_ids(cur, lemma, pos, source_id):
    """morphemes에서 (lemma, pos, source_id) 조합의 text_id 목록 가져오기.
    pos가 'NNG·NNP'면 NNG와 NNP 둘 다 매칭.
    Returns:
        list of text_id (int)
    """
    pos_list = pos.split("·") if "·" in pos else [pos]
    cur.execute("""
        SELECT DISTINCT m.text_id
        FROM morphemes m
        JOIN texts t ON m.text_id = t.text_id
        WHERE m.lemma = %s AND m.pos = ANY(%s) AND t.source_id = %s
          AND m.text_id IS NOT NULL
    """, (lemma, pos_list, source_id))
    return [row[0] for row in cur.fetchall()]


def get_comment_ids(cur, lemma, pos):
    """morphemes에서 (lemma, pos) 조합의 comment_id 목록 가져오기.
    pos가 'NNG·NNP'면 NNG와 NNP 둘 다 매칭.
    댓글은 source_id=7 (유튜브 댓글)뿐이라 source_id 필터 없음.
    Returns:
        list of comment_id (int)
    """
    pos_list = pos.split("·") if "·" in pos else [pos]
    cur.execute("""
        SELECT DISTINCT comment_id
        FROM morphemes
        WHERE lemma = %s AND pos = ANY(%s)
          AND comment_id IS NOT NULL
    """, (lemma, pos_list))
    return [row[0] for row in cur.fetchall()]

def get_embeddings(cur, text_ids):
    """text_id 목록에 대응하는 sentence 임베딩 가져오기.
    
    Returns:
        embedding_ids (list of int)
        text_ids_found (list of int) - 실제 임베딩 있는 text_id만
        vectors (numpy.ndarray, shape=(N, 1024))
    """
    cur.execute("""
        SELECT e.embedding_id, e.text_id, e.embedding
        FROM embeddings e
        WHERE e.text_id = ANY(%s)
          AND e.embedding_type = 'sentence'
    """, (text_ids,))
    rows = cur.fetchall()
    
    if not rows:
        return [], [], np.array([])
    
    embedding_ids = [r[0] for r in rows]
    text_ids_found = [r[1] for r in rows]
    # pgvector는 문자열로 반환됨 ('[0.1, 0.2, ...]')
    # 또는 list 형태일 수 있어 두 경우 다 처리
    vectors = np.array([
        eval(r[2]) if isinstance(r[2], str) else list(r[2])
        for r in rows
    ], dtype=np.float32)
    
    return embedding_ids, text_ids_found, vectors

def get_embeddings_for_comments(cur, comment_ids):
    """comment_id 목록에 대응하는 sentence 임베딩 가져오기.
    Returns:
        embedding_ids (list of int)
        comment_ids_found (list of int) - 실제 임베딩 있는 comment_id만
        vectors (numpy.ndarray, shape=(N, 1024))
    """
    cur.execute("""
        SELECT e.embedding_id, e.comment_id, e.embedding
        FROM embeddings e
        WHERE e.comment_id = ANY(%s)
          AND e.embedding_type = 'sentence'
    """, (comment_ids,))
    rows = cur.fetchall()
    if not rows:
        return [], [], np.array([])
    embedding_ids = [r[0] for r in rows]
    comment_ids_found = [r[1] for r in rows]
    # pgvector는 문자열로 반환됨 ('[0.1, 0.2, ...]')
    # 또는 list 형태일 수 있어 두 경우 다 처리
    vectors = np.array([
        eval(r[2]) if isinstance(r[2], str) else list(r[2])
        for r in rows
    ], dtype=np.float32)
    return embedding_ids, comment_ids_found, vectors


def cluster_vectors(vectors):
    """UMAP으로 차원 축소 후 HDBSCAN으로 클러스터링.
    
    Args:
        vectors: numpy.ndarray, shape=(N, 1024)
    
    Returns:
        labels: numpy.ndarray, shape=(N,) - 클러스터 라벨 (-1=노이즈)
        reduced: numpy.ndarray, shape=(N, UMAP_DIMS) - 축소된 벡터
    """
    n = len(vectors)
    
    # UMAP: 1024 → 10차원
    reducer = umap.UMAP(
        n_components=UMAP_DIMS,
        random_state=RANDOM_SEED,
        n_neighbors=min(15, n - 1),  # n이 작을 때 안전 장치
        metric='cosine'
    )
    reduced = reducer.fit_transform(vectors)
    
    # HDBSCAN: min_cluster_size = sqrt(N), 최소 5
    min_cluster_size = max(5, int(n ** 0.5))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric='euclidean'
    )
    labels = clusterer.fit_predict(reduced)
    
    return labels, reduced


def save_clusters(cur, candidate_id, lemma, pos, source_id, labels, vectors, embedding_ids):
    """클러스터링 결과를 usage_clusters + usage_cluster_members에 저장.
    
    Args:
        candidate_id: 신어 후보 ID
        source_id: 매체 ID
        labels: numpy.ndarray, 각 점의 클러스터 라벨 (-1=노이즈)
        vectors: numpy.ndarray, shape=(N, 1024), 원본 1024차원 벡터
        embedding_ids: list of int, 각 점의 embedding_id
    
    Returns:
        list of cluster_id (int) - 저장된 클러스터들의 ID
    """
    saved_cluster_ids = []
    
    # 노이즈(-1)는 제외하고 실제 클러스터만 처리
    unique_labels = sorted(set(labels))
    
    for cluster_label in unique_labels:
        if cluster_label == -1:
            continue  # 노이즈 스킵
        
        # 이 클러스터에 속한 점들의 인덱스
        member_idx = np.where(labels == cluster_label)[0]
        member_count = len(member_idx)
        
        # 클러스터 centroid (멤버들의 평균)
        member_vectors = vectors[member_idx]
        centroid = member_vectors.mean(axis=0)
        
        # usage_clusters에 저장
        cur.execute("""
            INSERT INTO usage_clusters
                (candidate_id, lemma, pos, source_id, centroid, member_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING cluster_id
        """, (candidate_id, lemma, pos, source_id, centroid.tolist(), member_count))
        cluster_id = cur.fetchone()[0]
        saved_cluster_ids.append(cluster_id)
        
        # usage_cluster_members에 저장
        # similarity = centroid와의 코사인 유사도
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
    """클러스터별 대표 용례 출력 (centroid에 가까운 순으로 top_k개).
    
    Args:
        cluster_ids: list of cluster_id
        top_k: 클러스터당 출력할 용례 수
    """
    for cluster_id in cluster_ids:
        cur.execute("""
            SELECT m.similarity, COALESCE(t.content, c.content) AS content
            FROM usage_cluster_members m
            JOIN embeddings e ON m.embedding_id = e.embedding_id
            LEFT JOIN texts t ON e.text_id = t.text_id
            LEFT JOIN comments c ON e.comment_id = c.comment_id
            WHERE m.cluster_id = %s
            ORDER BY m.similarity DESC
            LIMIT %s
        """, (cluster_id, top_k))

        rows = cur.fetchall()
        
        # 클러스터 정보
        cur.execute("""
            SELECT member_count FROM usage_clusters WHERE cluster_id = %s
        """, (cluster_id,))
        member_count = cur.fetchone()[0]
        
        print(f"\n  [클러스터 {cluster_id}] {member_count}건")
        for sim, content in rows:
            if content is None:
                continue
            # 용례 너무 길면 자르기
            preview = content[:120] + "..." if len(content) > 120 else content
            preview = preview.replace('\n', ' ')
            print(f"    sim={sim:.3f} | {preview}")

def run_cluster(lemma, pos, source_id):
    """단어 × 매체 단위 클러스터링 한 번 실행.
    
    Returns:
        dict with status and stats
    """
    print(f"\n{'='*60}")
    print(f"클러스터링: {lemma} × source_id={source_id}")
    print('='*60)
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 0. 기존 (lemma, pos, source_id) 클러스터 + 멤버 삭제 (재호출 시 중복 방지)
        cur.execute("""
            SELECT cluster_id FROM usage_clusters
            WHERE lemma = %s AND pos = %s AND source_id = %s
        """, (lemma, pos, source_id))
        old_cluster_ids = [row[0] for row in cur.fetchall()]
        if old_cluster_ids:
            cur.execute("""
                DELETE FROM usage_cluster_members
                WHERE cluster_id = ANY(%s)
            """, (old_cluster_ids,))
            cur.execute("""
                DELETE FROM usage_clusters
                WHERE cluster_id = ANY(%s)
            """, (old_cluster_ids,))
            print(f"  ⚠ 기존 클러스터 {len(old_cluster_ids)}개 삭제 (재호출)")

        # 1. candidate_id 조회
        candidate_id = get_candidate_id(cur, lemma)
        if candidate_id is None:
            print(f"  ℹ '{lemma}'는 신어 후보 아님 — 등재어 클러스터링으로 진행")
        else:
            print(f"  candidate_id: {candidate_id}")
        
        # 2. 용례 ID 수집 (텍스트 or 댓글 분기)

        if source_id == 7:  # 유튜브 댓글
            text_ids = get_comment_ids(cur, lemma, pos)
            print(f"  word_comment_map 용례: {len(text_ids):,}건")
        else:
            text_ids = get_text_ids(cur, lemma, pos,source_id)
            print(f"  word_text_map 용례: {len(text_ids):,}건")
        
        if len(text_ids) < MIN_SAMPLES:
            print(f"  ⚠ 용례 부족 ({len(text_ids)} < {MIN_SAMPLES})")
            return {'status': 'skip_too_few', 'n_samples': len(text_ids)}
        
        # 3. 샘플링
        if len(text_ids) > MAX_SAMPLES:
            random.seed(RANDOM_SEED)
            text_ids = random.sample(text_ids, MAX_SAMPLES)
            print(f"  샘플링: {MAX_SAMPLES}건으로 축소")
        
        # 4. 임베딩 가져오기 (텍스트 or 댓글 분기)
        if source_id == 7:  # 유튜브 댓글
            embedding_ids, _, vectors = get_embeddings_for_comments(cur, text_ids)
        else:
            embedding_ids, _, vectors = get_embeddings(cur, text_ids)
        print(f"  임베딩 있음: {len(embedding_ids):,}건 / {len(text_ids):,}건")        
        

        if len(embedding_ids) < MIN_SAMPLES:
            print(f"  ⚠ 임베딩 부족 ({len(embedding_ids)} < {MIN_SAMPLES})")
            return {'status': 'skip_no_embedding', 
                    'n_samples': len(embedding_ids)}
        
        # 5. 클러스터링
        print(f"  UMAP + HDBSCAN 실행 중...")
        labels, reduced = cluster_vectors(vectors)
        
        unique_labels = set(labels)
        n_noise = (labels == -1).sum()
        n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        print(f"  결과: {n_clusters}개 클러스터, 노이즈 {n_noise}건")
        
        if n_clusters == 0:
            print(f"  ⚠ 의미 있는 클러스터 없음")
            return {'status': 'no_clusters', 
                    'n_samples': len(embedding_ids),
                    'n_noise': int(n_noise)}
        
        # 6. DB 저장
        cluster_ids = save_clusters(cur, candidate_id, lemma, pos, source_id,
                                     labels, vectors, embedding_ids)
        conn.commit()
        print(f"  저장 완료: cluster_id {cluster_ids}")
        
        # 7. 검증 출력
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
    # 5/16: 긁히다 매체별 클러스터링 (5/15 메모 12번 "즉시 작업")
    runs = [
        # (lemma, pos, source_id)
        ('긁히다', 'VV', 6),   # 모두의말뭉치_신문 1,101건 (5/15 메모 기준)
        ('긁히다', 'VV', 7),   # 유튜브 댓글 128건 — cluster_usage 댓글 분기 실전 시험
    ]
    results = []
    for lemma, pos, source_id in runs:
        result = run_cluster(lemma, pos, source_id)
        results.append((lemma, pos, source_id, result))
    
    # 전체 요약
    print(f"\n\n{'='*60}")
    print("=== 전체 요약 ===")
    print('='*60)
    for lemma, pos, source_id, result in results:
        status = result.get('status')
        if status == 'success':
            print(f"  ✓ {lemma}/{pos} × source={source_id}: "
                  f"{result['n_clusters']}개 클러스터 "
                  f"({result['n_samples']}건, 노이즈 {result['n_noise']})")
        else:
            print(f"  ✗ {lemma}/{pos} × source={source_id}: {status}")
