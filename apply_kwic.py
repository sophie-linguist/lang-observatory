"""KWIC 적용 패치 스크립트 — 2번, 4번 페이지 수정"""
import re

# === 2번 페이지 ===
path2 = "/home/ssohe/lang-observatory/dashboard/pages/2_어휘_의미_탐색.py"
with open(path2, "r") as f:
    code = f.read()

# 1. import 추가
if "from kwic import make_kwic" not in code:
    code = code.replace(
        "from db import get_conn",
        "from db import get_conn\nfrom kwic import make_kwic"
    )

# 2. render_cluster_example 교체
old_render = '''def render_cluster_example(ex, lemma: str):
    similarity, text_id, comment_id, content, published_at, title, url = ex
    if not content:
        return

    display_content = content.replace(lemma, f"**{lemma}**")

    if len(display_content) > 200:
        preview = display_content[:200] + "..."
        with st.expander(preview, expanded=False):
            st.markdown(display_content)
            meta = []
            if published_at: meta.append(str(published_at)[:10])
            if title: meta.append(f"제목: {title}")
            if url: meta.append(f"[원문 링크]({url})")
            if similarity is not None: meta.append(f"유사도 {similarity:.3f}")
            if meta: st.caption(" · ".join(meta))
    else:
        st.markdown(f"- {display_content}")
        meta_parts = []
        if published_at: meta_parts.append(str(published_at)[:10])
        if similarity is not None: meta_parts.append(f"유사도 {similarity:.3f}")
        if meta_parts: st.caption("  " + " · ".join(meta_parts))'''

new_render = '''def render_cluster_example(ex, lemma: str):
    similarity, text_id, comment_id, content, published_at, title, url = ex
    if not content:
        return

    kwic = make_kwic(content, lemma)
    if not kwic:
        return

    st.markdown(f"- {kwic}")
    meta_parts = []
    if published_at:
        meta_parts.append(str(published_at)[:10])
    if similarity is not None:
        meta_parts.append(f"유사도 {similarity:.3f}")
    if meta_parts:
        st.caption("  " + " · ".join(meta_parts))'''

code = code.replace(old_render, new_render)

# 3. render_point_example — display를 KWIC로
code = code.replace(
    "display = bold_lemma_in_text(content, lemma, pos)",
    "display = make_kwic(content, lemma)"
)
code = code.replace(
    "preview = display[:200] + (\"...\" if len(display) > 200 else \"\")",
    "preview = display"
)

with open(path2, "w") as f:
    f.write(code)
print("2번 페이지 완료")

# === 4번 페이지 ===
path4 = "/home/ssohe/lang-observatory/dashboard/pages/4_어휘_의미_검증_결과.py"
with open(path4, "r") as f:
    code = f.read()

# 1. import 추가
if "from kwic import make_kwic" not in code:
    code = code.replace(
        "from db import get_conn",
        "from db import get_conn\nfrom kwic import make_kwic"
    )

with open(path4, "w") as f:
    f.write(code)
print("4번 페이지 완료")
