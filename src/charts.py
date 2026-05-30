"""시계열 차트 함수. 보고서/대시보드/에이전트 공용."""
import os
import sys
from datetime import datetime, timedelta

import matplotlib
matplotlib.use('Agg')  # 화면 없는 서버 환경용
import matplotlib.pyplot as plt
from matplotlib import font_manager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_conn


# 한글 폰트 설정 (NanumGothic 우선, 없으면 시스템 기본)
def setup_korean_font():
    candidates = ['NanumGothic', 'Noto Sans CJK KR', 'Malgun Gothic']
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams['font.family'] = name
            plt.rcParams['axes.unicode_minus'] = False
            return name
    return None


def plot_freq_trend(lemma, days=90, save_path=None):
    """
    단어 하나의 시간 추이를 일별로 그림.
    
    돌려주는 것: matplotlib Figure
    save_path 주면 PNG로 저장도 함.
    """
    conn = get_conn()
    cur = conn.cursor()
    
    if days is not None:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        cur.execute("""
            SELECT freq_date, SUM(count) AS cnt
            FROM vocab_freq
            WHERE lemma = %s
              AND freq_date >= %s
              AND freq_date <= %s
            GROUP BY freq_date
            ORDER BY freq_date
        """, (lemma, start_date, end_date))
    else:
        cur.execute("""
            SELECT freq_date, SUM(count) AS cnt
            FROM vocab_freq
            WHERE lemma = %s
            GROUP BY freq_date
            ORDER BY freq_date
        """, (lemma,))    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        print(f"[!] {lemma}: 데이터 없음")
        return None
    
    dates = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    
    setup_korean_font()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(dates, counts, marker='o', markersize=3, linewidth=1)
    title = f'"{lemma}" 빈도 추이'
    if days is not None:
        title += f' (최근 {days}일)'
    else:
        title += ' (전체 기간)'
    ax.set_title(title)
    ax.set_xlabel('날짜')
    ax.set_ylabel('일별 빈도')
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    
    if save_path:
        fig.savefig(save_path, dpi=100, bbox_inches='tight')
        print(f"저장: {save_path}")
    
    return fig


# 시험용
if __name__ == "__main__":
    lemma = sys.argv[1] if len(sys.argv) > 1 else "헬스케어"
    save_path = f"/home/ubuntu/lang-observatory/reports/charts/test_{lemma}.png"
    plot_freq_trend(lemma, days=None, save_path=save_path)
