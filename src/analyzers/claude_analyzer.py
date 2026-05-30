"""
의미 번호 검증을 위한 Claude API 분석기.
단어 하나 받아서 클러스터 정보를 모으고 Claude에 전달해서 의미를 판정한다.
"""
import sys
import os
import re
import json                    
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv() 

# src 디렉토리를 import 경로에 추가 (db.py 쓰려고)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_conn

def clean_text(text):
    """HTML 태그 제거 + 공백 정리."""
    if not text:
        return ""
    # HTML 태그 전부 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 연속 공백을 하나로
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def fetch_word_data(lemma, pos, source_id=None, examples_per_cluster=10):
    """
    단어 하나에 대한 검증용 데이터를 DB에서 모은다.
    
    돌려주는 것:
    - candidate_id: 신어 후보 테이블 id
    - clusters: [{cluster_id, member_count, examples: [용례 텍스트, ...]}, ...]
    - dict_senses: [(dict_source, sense_number, definition), ...] (세 사전 통합)
    """
    conn = get_conn()
    cur = conn.cursor()
    # 1. neologism_candidates에서 candidate_id 찾기
    pos_list = pos.split("·") if "·" in pos else [pos]
    # NNG·NNP 합쳐진 새 클러스터와 NNG·NNP 따로 박힌 옛 클러스터 모두 매칭
    if "·" in pos:
        pos_list = pos_list + [pos]
    cur.execute(
        "SELECT candidate_id FROM neologism_candidates WHERE lemma = %s AND pos = ANY(%s) LIMIT 1",
        (lemma, pos_list)
    )

    row = cur.fetchone()
    candidate_id = row[0] if row else None
    
    # 2. 클러스터들 가져오기 — lemma + pos + (선택) source_id 기반
    if source_id is None:
        cur.execute("""
            SELECT cluster_id, member_count, source_id
            FROM usage_clusters
            WHERE lemma = %s AND pos = ANY(%s)
            ORDER BY source_id, cluster_id
        """, (lemma, pos_list))

    else:
        cur.execute("""
            SELECT cluster_id, member_count, source_id
            FROM usage_clusters
            WHERE lemma = %s AND pos = ANY(%s) AND source_id = %s
            ORDER BY cluster_id
        """, (lemma, pos_list, source_id))
    cluster_rows = cur.fetchall()
    if not cluster_rows:
        print(f"[!] {lemma}/{pos} (source_id={source_id}) 클러스터 없음")
        return None
    
    # 3. 각 클러스터의 대표 용례 N개씩
    clusters = []
    for cluster_id, member_count, cl_source_id in cluster_rows:
        cur.execute("""
            SELECT COALESCE(t.content, c.content) AS content, m.similarity
            FROM usage_cluster_members m
            JOIN embeddings e ON m.embedding_id = e.embedding_id
            LEFT JOIN texts t ON e.text_id = t.text_id
            LEFT JOIN comments c ON e.comment_id = c.comment_id
            WHERE m.cluster_id = %s
            ORDER BY m.similarity DESC
            LIMIT %s
        """, (cluster_id, examples_per_cluster))
        examples = [clean_text(row[0])[:512] for row in cur.fetchall() if row[0]] 
        clusters.append({
            "cluster_id": cluster_id,
            "member_count": member_count,
            "source_id": cl_source_id,
            "examples": examples
        })
    
    # 4. 세 사전 등재 sense 전체 (다중 사전 비교용)
    cur.execute("""
        SELECT dict_source, sense_number, definition
        FROM urimalsaem_entries
        WHERE headword_norm = %s AND sense_type = '일반어'
        ORDER BY dict_source, sense_number
    """, (lemma,))
    dict_senses_rows = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return {
        "lemma": lemma,
        "candidate_id": candidate_id,
        "clusters": clusters,
        "dict_senses": dict_senses_rows
    }

def format_dict_senses(dict_senses_rows):
    """세 사전 sense 데이터를 프롬프트용 텍스트로 변환."""
    if not dict_senses_rows:
        return "(어느 사전에도 등재되지 않음)"

    by_dict = {}
    for src, sn, definition in dict_senses_rows:
        by_dict.setdefault(src, []).append((sn, definition))

    label = {
        "urimalsaem": "우리말샘",
        "stdict": "표준국어대사전",
        "kbd": "한국어기초사전",
    }

    parts = []
    for src in ["urimalsaem", "stdict", "kbd"]:
        if src not in by_dict:
            continue
        parts.append(f"### {label[src]}")
        for sn, definition in by_dict[src]:
            parts.append(f"[{src}:{sn}] {definition}")
        parts.append("")
    return "\n".join(parts)


def format_clusters(clusters):
    """클러스터 데이터를 프롬프트에 들어갈 텍스트로 변환."""
    parts = []
    for c in clusters:
        parts.append(f"[클러스터 {c['cluster_id']}] ({c['member_count']}개 용례)")
        for i, ex in enumerate(c['examples'], 1):
            parts.append(f"{i}. {ex}")
        parts.append("")  # 클러스터 사이 빈 줄
    return "\n".join(parts)


def build_prompt(data, source_name="전체"):
    """프롬프트 파일을 읽어서 빈칸을 채운다."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "prompts",
        "sense_analysis.txt"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    return (template
        .replace("{lemma}", data["lemma"])
        .replace("{source_name}", source_name)
        .replace("{dict_senses}", format_dict_senses(data["dict_senses"]))
        .replace("{clusters}", format_clusters(data["clusters"]))
    )

def call_claude(prompt, model="claude-opus-4-7", max_tokens=4096):
    """
    Claude API 호출하고 JSON 응답을 파싱해서 돌려준다.
    실패하면 None.
    """
    client = Anthropic()  # API 키는 환경변수에서 자동으로 읽음
    
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"[!] API 호출 실패: {e}")
        return None
    
    # 응답 텍스트 추출
    text = response.content[0].text
    
    # JSON 추출 (```json ... ``` 블록이 있으면 그 안만, 없으면 전체)
    json_match = re.search(r'```json\s*(.+?)\s*```', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 첫 { 부터 마지막 } 까지
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            print(f"[!] JSON을 찾을 수 없음. 응답: {text[:200]}...")
            return None
        json_str = text[start:end+1]
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[!] JSON 파싱 실패: {e}")
        print(f"파싱 시도한 텍스트: {json_str[:500]}...")
        return None

def save_to_db(lemma, data, result):
    """sense_validation 테이블에 결과 저장."""
    conn = get_conn()
    cur = conn.cursor()
    
    n_clusters = len(data["clusters"])
    n_examples = sum(len(c["examples"]) for c in data["clusters"])
    judgment = result.get("judgment", "")
    pos = result.get("pos", "")
    
    cur.execute("""
        INSERT INTO sense_validation 
        (headword, pos, n_clusters, n_examples, claude_result, judgment)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING validation_id
    """, (
        lemma,
        pos,
        n_clusters,
        n_examples,
        json.dumps(result, ensure_ascii=False),
        judgment
    ))
    
    validation_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return validation_id

if __name__ == "__main__":
    # 사용법: python3 claude_analyzer.py <lemma> <pos> [source_id]
    # 예: python3 claude_analyzer.py 긁다 VV 6  (긁다 동사, 신문 매체)
    # 예: python3 claude_analyzer.py 헬스케어 NNG  (헬스케어, 모든 매체)
    if len(sys.argv) < 3:
        print("사용법: python3 claude_analyzer.py <lemma> <pos> [source_id]")
        print("예: python3 claude_analyzer.py 긁다 VV 6")
        sys.exit(1)
    lemma = sys.argv[1]
    pos = sys.argv[2]
    source_id = int(sys.argv[3]) if len(sys.argv) > 3 else None

    print(f"[1/3] DB에서 데이터 가져오는 중... ({lemma}/{pos}, source_id={source_id})")
    data = fetch_word_data(lemma, pos, source_id=source_id)
    if data is None:
        sys.exit(1)
    print(f"  → 클러스터 {len(data['clusters'])}개, 세 사전 sense {len(data['dict_senses'])}개")

    print(f"[2/3] 프롬프트 만드는 중...")
    prompt = build_prompt(data)
    print(f"  → {len(prompt):,}자")
    
    print(f"[3/3] Claude 호출 중... (1~2분 걸림)")
    result = call_claude(prompt)
    if result is None:
        sys.exit(1)
    
    # 결과 미리보기
    print("\n=== Claude 응답 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print(f"\n[저장] DB에 결과 저장 중...")
    validation_id = save_to_db(lemma, data, result)
    print(f"  → validation_id={validation_id} 저장 완료")
