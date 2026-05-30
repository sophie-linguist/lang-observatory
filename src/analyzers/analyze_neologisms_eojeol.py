"""댓글 어절 복원 기반 신어 후보 추출

알고리즘:
1. 댓글을 어절(띄어쓰기) 단위로 분할
2. 각 어절을 Kiwi로 토큰화
3. 어절 끝에서 조사·어미·접미사 제거
4. 명사 어근 추출 (NNG/MAG로 시작, 어간 앞까지)
5. 동사·형용사 어간 추출 (lemma 기반, 명사·부사 앞부분 합성)
6. 우리말샘 미등재 어휘 → neologism_candidates 적재

사용:
    python3 src/analyzers/analyze_neologisms_eojeol.py [--days N] [--min-count N]
    
    --days: 처리할 댓글 기간 (기본: 7일)
    --min-count: 최소 빈도 임계값 (기본: 5)
"""
import os
import sys
import argparse
from datetime import datetime
from collections import Counter
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

from kiwipiepy import Kiwi


# ===== Kiwi 태그 분류 =====

# 조사·어미·접미사·부호·자모 (어근에서 제외)
STRIP_TAGS = {
    'JKS', 'JKC', 'JKG', 'JKO', 'JKB', 'JKV', 'JKQ', 'JX', 'JC',
    'EP', 'EC', 'EF', 'ETM', 'ETN',
    'XSN', 'XSV', 'XSA',
    'SF', 'SP', 'SS', 'SE', 'SO', 'SW', 'SH', 'SN',
    'NNB',
    'VCP', 'VCN',  # 서술격조사 '이다', 부정 '아니다'
    'W_EMOJI', 'W_HASHTAG', 'W_MENTION', 'W_URL', 'W_SERIAL',
}

# 어근 시작 가능 태그 (NNG=일반명사, MAG=일반부사)
ROOT_TAGS = {'NNG', 'MAG'}


def is_strip_tag(tag):
    """STRIP 태그 여부 (변형 태그 prefix 매칭 포함)"""
    if tag in STRIP_TAGS:
        return True
    if tag.startswith('XSA') or tag.startswith('XSV') or tag.startswith('XSN'):
        return True
    return False


def is_stem_tag(tag):
    """동사/형용사 어간 여부 (VV-R, VA-I 등 변형 포함)"""
    if tag in {'VV', 'VA', 'VX'}:
        return True
    return tag.startswith('VV') or tag.startswith('VA') or tag.startswith('VX')


def stem_pos(tag):
    """어간 태그를 NNG/VV/VA로 정규화"""
    if tag.startswith('VV'):
        return 'VV'
    if tag.startswith('VA'):
        return 'VA'
    if tag.startswith('VX'):
        return 'VV'  # 보조용언은 VV로 통일
    return tag


# ===== 어절 분할 =====

def extract_eojeol_tokens(tokens):
    """Kiwi 토큰을 어절(띄어쓰기) 단위로 묶기"""
    eojeols = []
    current = []
    for i, tok in enumerate(tokens):
        if i == 0:
            current.append(tok)
            continue
        prev = tokens[i-1]
        prev_end = prev.start + prev.len
        if tok.start > prev_end:
            if current:
                eojeols.append(current)
            current = [tok]
        else:
            current.append(tok)
    if current:
        eojeols.append(current)
    return eojeols


# ===== 어근·어간 추출 =====

def extract_root_and_stem(eojeol_tokens):
    """어절에서 명사 어근 + 동사·형용사 어간 추출
    
    Returns:
        (root, stem_lemma, stem_pos) 튜플
        - root: 명사 어근 (str | None)
        - stem_lemma: 동사·형용사 어간의 사전형 (str | None)
        - stem_pos: 어간 품사 'VV' | 'VA' | None
    """
    end = len(eojeol_tokens)
    
    # 끝에서 STRIP 토큰 떼기
    while end > 0 and is_strip_tag(eojeol_tokens[end-1].tag):
        end -= 1
    if end == 0:
        return None, None, None
    
    # 어간 위치 찾기
    stem_idx = None
    for i in range(end):
        if is_stem_tag(eojeol_tokens[i].tag):
            stem_idx = i
            break
    
    noun_end = stem_idx if stem_idx is not None else end
    root_tokens = eojeol_tokens[:noun_end]
    
    # 명사 어근
    root = None
    if root_tokens and root_tokens[0].tag in ROOT_TAGS:
        candidate = ''.join(t.form for t in root_tokens if not is_strip_tag(t.tag))
        if re.fullmatch(r'[가-힣]{2,}', candidate):
            root = candidate
    
    # 동사·형용사 어간
    stem_lemma = None
    spos = None
    if stem_idx is not None:
        stem_token = eojeol_tokens[stem_idx]
        base_lemma = stem_token.lemma
        spos = stem_pos(stem_token.tag)
        
        # 명사·부사 앞부분 합성 (열받다, 킹받다, 개귀엽다)
        if root_tokens and root_tokens[0].tag in ROOT_TAGS:
            noun_part = ''.join(t.form for t in root_tokens if not is_strip_tag(t.tag))
            if noun_part and re.fullmatch(r'[가-힣]+', noun_part):
                stem_lemma = noun_part + base_lemma
        
        if not stem_lemma:
            stem_lemma = base_lemma
        
        # 정규식 검증: 한글 2글자 이상, '다'로 끝남
        if not re.fullmatch(r'[가-힣]{2,}다$', stem_lemma):
            stem_lemma = None
            spos = None
    
    return root, stem_lemma, spos


# ===== 메인 처리 =====

def process_comments(days=7, min_count=5):
    """최근 N일 댓글 어절 복원 → 신어 후보 적재"""
    
    print(f"[설정] 기간: 최근 {days}일, 최소 빈도: {min_count}+")
    
    conn = get_conn()
    cur = conn.cursor()
    
    # 댓글 가져오기
    print("[1/4] 댓글 가져오는 중...")
    cur.execute(f"""
        SELECT content FROM comments 
        WHERE collected_at >= NOW() - INTERVAL '{days} days'
          AND char_length(content) >= 10
    """)
    comments = [row[0] for row in cur.fetchall()]
    print(f"  → {len(comments):,}개")
    
    if not comments:
        print("  처리할 댓글 없음, 종료")
        cur.close()
        conn.close()
        return
    
    # 형태소 분석 + 어절 복원
    print("[2/4] 형태소 분석 + 어절 복원...")
    kiwi = Kiwi()
    
    # (lemma, pos) → count
    counter = Counter()
    
    for idx, comment in enumerate(comments):
        if idx % 5000 == 0 and idx > 0:
            print(f"  {idx:,}/{len(comments):,}")
        try:
            tokens = kiwi.tokenize(comment)
            eojeols = extract_eojeol_tokens(tokens)
            for eojeol in eojeols:
                root, stem, spos = extract_root_and_stem(eojeol)
                if root:
                    counter[(root, 'NNG')] += 1
                if stem and spos:
                    counter[(stem, spos)] += 1
        except Exception as e:
            # 개별 댓글 분석 실패는 무시하고 진행
            continue
    
    print(f"  → 총 {len(counter):,}개 후보 (lemma+pos 단위)")
    
    # 임계값 필터
    candidates = [
        (lemma, pos, cnt) 
        for (lemma, pos), cnt in counter.items() 
        if cnt >= min_count
    ]
    print(f"  → 빈도 {min_count}+ 후보: {len(candidates):,}개")
    
    if not candidates:
        print("  적재할 후보 없음, 종료")
        cur.close()
        conn.close()
        return
    
    # 우리말샘 매칭
    print("[3/4] 우리말샘 매칭...")
    candidate_lemmas = list({lemma for lemma, _, _ in candidates})
    cur.execute("""
        SELECT DISTINCT headword_norm FROM urimalsaem_entries 
        WHERE headword_norm = ANY(%s) AND sense_type = '일반어'
    """, (candidate_lemmas,))
    registered = {row[0] for row in cur.fetchall()}
    
    unregistered = [
        (lemma, pos, cnt) 
        for lemma, pos, cnt in candidates 
        if lemma not in registered
    ]
    print(f"  → 미등재 신어 후보: {len(unregistered):,}개")
    
    # neologism_candidates 적재
    print("[4/4] DB 적재...")
    inserted = 0
    updated = 0
    for lemma, pos, cnt in unregistered:
        try:
            cur.execute("""
                INSERT INTO neologism_candidates 
                (lemma, pos, detection_type, score, status)
                VALUES (%s, %s, 'comment_eojeol', %s, 'pending')
                ON CONFLICT (lemma, pos, detection_type)
                DO UPDATE SET 
                    score = EXCLUDED.score,
                    detected_at = CURRENT_DATE
                RETURNING (xmax = 0) AS inserted
            """, (lemma, pos, float(cnt)))
            if cur.fetchone()[0]:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  적재 실패: {lemma}({pos}) - {e}")
            conn.rollback()
            continue
    
    conn.commit()
    
    print(f"\n[완료] 신규 {inserted}건 / 업데이트 {updated}건")
    
    # 상위 20개 미리보기
    print("\n=== 상위 20 신어 후보 ===")
    for lemma, pos, cnt in sorted(unregistered, key=lambda x: -x[2])[:20]:
        print(f"  {cnt:5.0f}  {pos:4s}  {lemma}")
    
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=7,
                        help='처리할 댓글 기간 (일 단위, 기본 7)')
    parser.add_argument('--min-count', type=int, default=5,
                        help='최소 빈도 임계값 (기본 5)')
    args = parser.parse_args()
    
    start = datetime.now()
    process_comments(days=args.days, min_count=args.min_count)
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n총 소요 시간: {elapsed:.1f}초")


if __name__ == '__main__':
    main()
