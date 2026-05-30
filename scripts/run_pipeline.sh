#!/bin/bash
# 언어관측시스템 자동 수집·분석 파이프라인
# cron에서 호출: run_pipeline.sh [naver|youtube|morphemes|embed|refresh|eojeol|report|all]
#
# 5/24 개정:
# - morphemes: analyze_morphemes_tf.py 사용 (texts·comments 통합, TF 누적)
# - comments 케이스 제거 (morphemes 안에서 처리)
# - embed: embed_texts_segmented.py 사용 (세그먼트 단위, 매체별 샘플링)
set -e
cd ~/lang-observatory
source venv/bin/activate
export PYTHONPATH=src
LOGDIR=~/lang-observatory/logs
mkdir -p $LOGDIR
TIMESTAMP=$(date '+%Y%m%d_%H%M')
case "$1" in
  naver)
    echo "[$TIMESTAMP] 네이버 뉴스 수집 시작" >> $LOGDIR/naver.log
    python3 src/scrapers/naver_news.py >> $LOGDIR/naver.log 2>&1
    echo "[$TIMESTAMP] 네이버 뉴스 수집 완료" >> $LOGDIR/naver.log
    ;;
  youtube)
    echo "[$TIMESTAMP] 유튜브 댓글 수집 시작" >> $LOGDIR/youtube.log
    python3 src/scrapers/youtube_comments.py >> $LOGDIR/youtube.log 2>&1
    echo "[$TIMESTAMP] 유튜브 댓글 수집 완료" >> $LOGDIR/youtube.log
    ;;
  morphemes)
    echo "[$TIMESTAMP] 형태소 분석 시작 (texts + comments 통합)" >> $LOGDIR/morphemes.log
    python3 -u src/analyze_morphemes_tf.py >> $LOGDIR/morphemes.log 2>&1
    echo "[$TIMESTAMP] 형태소 분석 완료" >> $LOGDIR/morphemes.log
    ;;
  embed)
    echo "[$TIMESTAMP] 임베딩 시작 (세그먼트 단위)" >> $LOGDIR/embed.log
    python3 -u src/analyzers/embed_texts_segmented.py >> $LOGDIR/embed.log 2>&1
    echo "[$TIMESTAMP] 임베딩 완료" >> $LOGDIR/embed.log
    ;;
  segment_map)
    echo "[$TIMESTAMP] 세그먼트 lemma 매핑 시작" >> $LOGDIR/segment_map.log
    python3 -u src/build_segment_lemma_map.py >> $LOGDIR/segment_map.log 2>&1
    echo "[$TIMESTAMP] 세그먼트 lemma 매핑 완료" >> $LOGDIR/segment_map.log
    ;;
  refresh)
    echo "[$TIMESTAMP] vocab/neologism 갱신 시작" >> $LOGDIR/refresh.log
    python3 -u src/analyzers/refresh_vocab_freq.py >> $LOGDIR/refresh.log 2>&1
    echo "[$TIMESTAMP] vocab/neologism 갱신 완료" >> $LOGDIR/refresh.log
    ;;
  eojeol)
    echo "[$TIMESTAMP] 어절 복원 신어 추출 시작" >> $LOGDIR/eojeol.log
    python3 -u src/analyzers/analyze_neologisms_eojeol.py --days 7 --min-count 5 >> $LOGDIR/eojeol.log 2>&1
    echo "[$TIMESTAMP] 어절 복원 신어 추출 완료" >> $LOGDIR/eojeol.log
    ;;
  report)
    echo "[$TIMESTAMP] 주간 보고서 생성 시작" >> $LOGDIR/report.log
    python3 -u src/generate_report.py >> $LOGDIR/report.log 2>&1
    echo "[$TIMESTAMP] 주간 보고서 생성 완료" >> $LOGDIR/report.log
    ;;
  all)
    $0 naver
    $0 youtube
    $0 morphemes
    $0 embed
    $0 refresh
    $0 eojeol
    $0 segment_map
    ;;
  *)
    echo "Usage: $0 {naver|youtube|morphemes|embed|segment_map|refresh|eojeol|report|all}"
    exit 1
    ;;
esac

