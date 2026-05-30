"""
NER 분류 도구.

함수:
- classify_word(lemma, pos, n_samples=3)
  단어 하나 NER 분류. 보고서/대시보드/에이전트에서 호출.

- classify_word_list(words)
  여러 단어 한 번에 분류. 보고서가 매주 호출.

CLI:
- python run_ner.py --score 1000
  신어 후보에서 score 이상인 거 일괄 분류 (수동 실행용)
"""

import json
import sys
import time
from collections import Counter
from transformers import pipeline

sys.path.insert(0, '/home/ubuntu/lang-observatory/src')
from db import get_conn


# 모델 lazy loading (필요할 때만 로딩)
_NER_PIPELINE = None

from transformers import AutoConfig, AutoModelForTokenClassification, AutoTokenizer, pipeline

def get_ner_pipeline():
    """NER 파이프라인 (한 번만 로딩 및 한국어 Suffix 태그 버그 패치)."""
    global _NER_PIPELINE
    if _NER_PIPELINE is None:
        print("🚀 [UPGRADE] monologg Base NER 모델 로딩 및 태그 변환 패치 중...")
        model_name = 'monologg/koelectra-base-finetuned-naver-ner'
        
        # 💡 [핵심 패치] 한국어 특유의 Suffix 태그(PER-B)를 글로벌 표준인 Prefix(B-PER)로 강제 변환
        config = AutoConfig.from_pretrained(model_name)
        if hasattr(config, 'id2label'):
            new_id2label = {}
            for idx, label in config.id2label.items():
                if '-' in label:
                    parts = label.split('-')
                    if parts[1] in ['B', 'I']:  # PER-B 구조인 경우
                        new_id2label[idx] = f"{parts[1]}-{parts[0]}"  # B-PER 형태로 뒤집기
                    else:
                        new_id2label[idx] = label
                else:
                    new_id2label[idx] = label
            config.id2label = new_id2label
            config.label2id = {v: k for k, v in new_id2label.items()}
        
        # 변환된 세팅으로 모델과 토크나이저를 안전하게 로드
        model = AutoModelForTokenClassification.from_pretrained(model_name, config=config)
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        _NER_PIPELINE = pipeline(
            'ner',
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy='simple'
        )
        print("✨ 로딩 및 태그 패치 완료")
    return _NER_PIPELINE
def _get_sample_texts(lemma, pos, n=3):
    """그 단어가 들어간 텍스트 N개 가져오기. 내부 함수."""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT t.content
        FROM (
            SELECT DISTINCT text_id
            FROM morphemes
            WHERE lemma = %s AND pos = %s AND text_id IS NOT NULL
            LIMIT %s
        ) m
        JOIN texts t ON m.text_id = t.text_id
        WHERE length(t.content) >= 50
          AND length(t.content) <= 1000
    """, (lemma, pos, n))
    texts = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return texts


def classify_word(lemma, pos, n_samples=3, save=True):
    """
    단어 하나 NER 분류.

    반환: dict with keys 'entity_type', 'entity_score', 'sample_texts', 'sample_count'
    save=True면 ner_results에 저장.
    """
    texts = _get_sample_texts(lemma, pos, n=n_samples)

    if not texts:
        result = {
            'lemma': lemma, 'pos': pos,
            'entity_type': None, 'entity_score': None,
            'sample_count': 0, 'sample_texts': []
        }
    else:
        ner = get_ner_pipeline()
        entity_types = []
        scores = []

        for text in texts:
            try:
                # 단어 주변만 잘라서 NER에 줌 (앞뒤 200자)
                idx = text.find(lemma)
                if idx == -1:
                    continue
                start = max(0, idx - 200)
                end = min(len(text), idx + len(lemma) + 200)
                snippet = text[start:end]
                ner_results = ner(snippet)
                for r in ner_results:
                    if lemma in r['word'] or r['word'] in lemma:
                        entity_types.append(r['entity_group'])
                        scores.append(r['score'])
            except Exception:
                continue

        if not entity_types:
            entity_type, entity_score = None, None
        else:
            most_common = Counter(entity_types).most_common(1)[0]
            entity_type = most_common[0]
            matching = [s for t, s in zip(entity_types, scores) if t == entity_type]
            entity_score = float(sum(matching) / len(matching))

        result = {
            'lemma': lemma, 'pos': pos,
            'entity_type': entity_type,
            'entity_score': entity_score,
            'sample_count': len(texts),
            'sample_texts': [
                t[max(0, t.find(lemma)-100):min(len(t), t.find(lemma)+len(lemma)+100)]
                if t.find(lemma) != -1 else t[:200]
                for t in texts
            ]
        }

    if save:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ner_results
            (lemma, pos, entity_type, entity_score, sample_count, sample_texts)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            result['lemma'], result['pos'],
            result['entity_type'], result['entity_score'],
            result['sample_count'],
            json.dumps(result['sample_texts'], ensure_ascii=False)
        ))
        conn.commit()
        cur.close()
        conn.close()

    return result


def classify_word_list(words, save=True, verbose=True):
    """
    여러 단어 한 번에 분류. 보고서에서 호출.

    words: list of (lemma, pos) tuples
    반환: list of dict (classify_word와 같은 구조)
    """
    results = []
    start = time.time()

    for i, (lemma, pos) in enumerate(words, 1):
        r = classify_word(lemma, pos, save=save)
        results.append(r)

        if verbose and i % 20 == 0:
            elapsed = time.time() - start
            rate = i / elapsed
            eta = (len(words) - i) / rate
            print(f"  {i}/{len(words)} | {rate:.1f}건/초 | 남은: {eta:.0f}초")

    return results


def _cli_bulk(min_score=1000):
    """CLI 일괄 처리. 신어 후보에서 score 이상인 거 다 분류."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT lemma, pos, score
        FROM neologism_candidates
        WHERE detection_type = 'unregistered'
          AND score >= %s
        ORDER BY score DESC
    """, (min_score,))
    candidates = [(row[0], row[1]) for row in cur.fetchall()]
    cur.close()
    conn.close()

    print(f"대상: {len(candidates):,}건 (score >= {min_score})")
    print("-" * 60)

    classify_word_list(candidates, save=True, verbose=True)

    print("=" * 60)
    print(f"완료: {len(candidates):,}건")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--score', type=int, default=1000,
                        help='신어 후보 일괄 처리 시 최소 score')
    parser.add_argument('--word', type=str, default=None,
                        help='단일 단어 시험. 형식: "lemma,pos" (예: "헬스케어,NNG")')
    args = parser.parse_args()

    if args.word:
        lemma, pos = args.word.split(',')
        result = classify_word(lemma.strip(), pos.strip(), save=False)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 잘려 있던 마무리를 정상적으로 연결
        _cli_bulk(args.score)
