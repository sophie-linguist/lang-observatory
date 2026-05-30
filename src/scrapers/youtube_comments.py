"""YouTube 댓글 수집기 (카테고리별 인기 영상 기반)

4/26 변경:
- videoCategoryId 7개 분산 수집 (10/20/22/23/24/25/26)
- 영상당 댓글 200개 (페이지 2회)
- 일일 API quota 가드 (8000 units 한도)
"""
import os, sys, time
from datetime import datetime
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

load_dotenv()
YOUTUBE_KEY = os.getenv("YOUTUBE_API_KEY")
SOURCE_ID = 4  # 유튜브

VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

# YouTube 카테고리 ID (한국)
# 10: Music, 20: Gaming, 22: People & Blogs, 23: Comedy
# 24: Entertainment, 25: News & Politics, 26: Howto & Style
CATEGORIES = [
    ("10", "Music"),
    ("20", "Gaming"),
    ("22", "People & Blogs"),
    ("23", "Comedy"),
    ("24", "Entertainment"),
    ("25", "News & Politics"),
    ("26", "Howto & Style"),
]

# 일일 API 사용량 가드 (한도 10,000의 80%)
QUOTA_LIMIT = 8000

# 전역 사용량 카운터 (실행 1회 동안 누적)
quota_used = 0


def parse_date(s):
    """ISO 8601 → datetime (Z는 UTC, naive로 변환)"""
    if not s:
        return None
    try:
        return datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def fetch_popular_videos(category_id, max_results=50):
    """카테고리별 한국 인기 영상 목록"""
    global quota_used
    r = requests.get(VIDEOS_URL, params={
        "part": "snippet",
        "chart": "mostPopular",
        "regionCode": "KR",
        "videoCategoryId": category_id,
        "maxResults": max_results,
        "key": YOUTUBE_KEY,
    }, timeout=10)
    quota_used += 1
    r.raise_for_status()
    return r.json().get("items", [])


def fetch_comments(video_id, max_pages=2, per_page=100):
    """영상 댓글 (페이지네이션 지원)
    
    max_pages=2, per_page=100 → 영상당 최대 200개 댓글
    """
    global quota_used
    all_comments = []
    page_token = None
    
    for page in range(max_pages):
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": per_page,
            "order": "relevance",
            "textFormat": "plainText",
            "key": YOUTUBE_KEY,
        }
        if page_token:
            params["pageToken"] = page_token
        
        try:
            r = requests.get(COMMENTS_URL, params=params, timeout=10)
            quota_used += 1
            
            if r.status_code == 403:
                # 댓글 비활성화된 영상
                return all_comments
            r.raise_for_status()
            
            data = r.json()
            all_comments.extend(data.get("items", []))
            
            page_token = data.get("nextPageToken")
            if not page_token:
                break  # 더 이상 페이지 없음
                
        except Exception as e:
            print(f"    댓글 가져오기 실패 ({video_id}, page {page+1}): {e}")
            break
    
    return all_comments


def save_video(cur, video):
    """영상 → texts. 이미 있으면 text_id만 반환."""
    snip = video["snippet"]
    video_id = video["id"]
    cur.execute("""
        INSERT INTO texts
        (source_id, external_id, title, content, author, published_at, collected_at, url, is_processed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id, external_id) DO UPDATE
          SET collected_at = EXCLUDED.collected_at
        RETURNING text_id
    """, (
        SOURCE_ID,
        video_id,
        snip.get("title", "")[:500],
        snip.get("description", "")[:5000],
        snip.get("channelTitle", "")[:100],
        parse_date(snip.get("publishedAt")),
        datetime.now(),
        f"https://youtube.com/watch?v={video_id}",
        False,
    ))
    return cur.fetchone()[0]


def save_comments(cur, text_id, comment_items):
    """댓글들 → comments"""
    saved = 0
    for it in comment_items:
        try:
            top = it["snippet"]["topLevelComment"]
            snip = top["snippet"]
            cur.execute("""
                INSERT INTO comments
                (text_id, external_id, content, author, published_at, collected_at, is_processed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (text_id, external_id) DO NOTHING
            """, (
                text_id,
                top["id"][:255],
                snip.get("textOriginal", ""),
                snip.get("authorDisplayName", "")[:100],
                parse_date(snip.get("publishedAt")),
                datetime.now(),
                False,
            ))
            saved += cur.rowcount
        except Exception as e:
            print(f"    댓글 저장 실패: {e}")
    return saved


def collect(videos_per_category=50, comment_pages=2):
    """카테고리별 인기 영상 수집 + 댓글 수집"""
    global quota_used
    
    conn = get_conn()
    cur = conn.cursor()
    
    total_videos_seen = 0
    total_videos_new = 0
    total_comments_new = 0
    seen_video_ids = set()
    
    for cat_idx, (cat_id, cat_name) in enumerate(CATEGORIES, 1):
        # Quota 가드
        if quota_used >= QUOTA_LIMIT:
            print(f"\n⚠️  API quota 한도 도달 ({quota_used}/{QUOTA_LIMIT}), 중단")
            break
        
        print(f"\n[{cat_idx}/{len(CATEGORIES)}] 카테고리 {cat_name} (id={cat_id})")
        
        try:
            videos = fetch_popular_videos(cat_id, videos_per_category)
        except Exception as e:
            print(f"  영상 목록 가져오기 실패: {e}")
            continue
        
        print(f"  → 영상 {len(videos)}개")
        total_videos_seen += len(videos)
        cat_comments = 0
        cat_new_videos = 0
        cat_channel_count = {}    # 채널별 카운트 (이번 카테고리)
        MAX_PER_CHANNEL = 3       # 채널당 영상 상한
        cat_channel_skipped = 0

        for i, video in enumerate(videos, 1):
            video_id = video["id"]
            channel = video["snippet"].get("channelTitle", "")

            # 카테고리 간 중복 영상 스킵 (이미 이번 실행에서 처리한 거)
            if video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)

            # 채널별 상한 검사
            if cat_channel_count.get(channel, 0) >= MAX_PER_CHANNEL:
                cat_channel_skipped += 1
                continue
            cat_channel_count[channel] = cat_channel_count.get(channel, 0) + 1
            
            # Quota 가드 (영상별로도 체크)
            if quota_used >= QUOTA_LIMIT:
                print(f"  ⚠️  API quota 한도 도달, 카테고리 중단")
                break
            
            title = video["snippet"]["title"][:40]
            
            try:
                text_id = save_video(cur, video)
                comments = fetch_comments(video_id, max_pages=comment_pages)
                new = save_comments(cur, text_id, comments)
                conn.commit()
                
                cat_new_videos += 1
                cat_comments += new
                
                # 매 10번째만 출력 (로그 너무 길어지지 않게)
                if i % 10 == 0 or new > 0:
                    print(f"  [{i:3d}/{len(videos)}] {title} | 댓글 {new}건 (quota {quota_used})")
                
                time.sleep(0.2)
                
            except Exception as e:
                print(f"  [{i:3d}/{len(videos)}] {title} | 실패 - {e}")
                conn.rollback()
        print(f"  카테고리 합계: 신규 영상 {cat_new_videos}개, 댓글 {cat_comments}건, 채널 상한 skip {cat_channel_skipped}건")
        print(f"  → 채널 수: {len(cat_channel_count)}개")

        total_videos_new += cat_new_videos
        total_comments_new += cat_comments
    
    cur.close()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"[완료] 카테고리 {len(CATEGORIES)}개 처리")
    print(f"  영상 조회: {total_videos_seen}개 (중복 포함)")
    print(f"  영상 신규: {total_videos_new}개")
    print(f"  댓글 신규: {total_comments_new}건")
    print(f"  API quota 사용: {quota_used} units")
    print(f"{'='*60}")


if __name__ == "__main__":
    collect(videos_per_category=50, comment_pages=2)
