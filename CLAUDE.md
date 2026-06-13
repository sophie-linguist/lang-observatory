# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Korean language neology detection system that automatically discovers new words (신어) and new senses of existing words from Korean text corpora. The system combines corpus linguistics methodology with modern NLP (BGE-M3 embeddings, UMAP+HDBSCAN clustering) and AI analysis (Claude API).

**Core Design Principle**: "Collect without bias, detect within collected data" — data collection is broad and unbiased, while neologism detection happens only within the already-collected corpus.

**Key Components**:
- Automated data collection pipeline (Naver News, YouTube comments, 모두의말뭉치 corpus)
- Morphological analysis with Kiwi + custom post-processing rules
- Distributional semantics analysis (embeddings → clustering → AI validation)
- Streamlit dashboard with conversational agent interface
- PostgreSQL + pgvector database

## Development Setup

**Prerequisites**:
- Python 3.10+ with venv
- Docker + Docker Compose (for PostgreSQL with pgvector)
- Environment variables in `.env` file (DB credentials, API keys for Anthropic, Naver, YouTube)

**Database**:
```bash
# Start PostgreSQL with pgvector
docker compose up -d

# Or use the script
./scripts/start_db.sh
```

The database runs at `localhost:5432` with database name `lang_observatory`.

**Python Environment**:
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements_no_torch.txt  # For analysis/pipeline
pip install -r dashboard/requirements.txt  # For dashboard
```

**Dashboard**:
```bash
cd dashboard
streamlit run app.py
```

Dashboard runs at `http://localhost:8501` by default.

## Running the Pipeline

The main pipeline is controlled by `scripts/run_pipeline.sh`:

```bash
# Run specific stages
./scripts/run_pipeline.sh naver          # Collect Naver news
./scripts/run_pipeline.sh youtube        # Collect YouTube comments
./scripts/run_pipeline.sh morphemes      # Morphological analysis (uses analyze_morphemes_tf.py)
./scripts/run_pipeline.sh embed          # Generate embeddings (uses embed_texts_segmented.py)
./scripts/run_pipeline.sh segment_map    # Build segment-lemma mapping
./scripts/run_pipeline.sh refresh        # Refresh vocab frequency tables
./scripts/run_pipeline.sh eojeol         # Extract neologisms via eojeol restoration
./scripts/run_pipeline.sh report         # Generate weekly report

# Run entire pipeline
./scripts/run_pipeline.sh all
```

Logs are written to `~/lang-observatory/logs/` with timestamps.

## Architecture

### Data Flow Pipeline

```
[1] Collection (scrapers/)
    ↓ texts, comments tables
[2] Morphological Analysis (analyze_morphemes_tf.py)
    ↓ morphemes table
[3] Frequency Aggregation (refresh_vocab_freq.py)
    ↓ vocab_freq table
[4] Neologism Detection
    ↓ neologism_candidates table
[5] Embedding (embed_texts_segmented.py)
    ↓ embeddings table (1024-dim BGE-M3 vectors)
[6] Segment-Lemma Mapping (build_segment_lemma_map.py)
    ↓ segment_lemma_map table
[7] Clustering (analyzers/cluster_usage.py)
    ↓ usage_clusters, usage_cluster_members tables
[8] AI Validation (analyzers/claude_analyzer.py)
    ↓ claude_validations table
[9] Dashboard Presentation
```

### Key Technical Concepts

**Segmented Embedding**: Long texts are split into ~300-character segments, with each segment embedded separately. This captures local context around word usage rather than just document-level topics.

**Media-Separated Clustering**: Clustering is performed separately per media source (Naver News, YouTube, etc.) because writing style differences can dominate semantic differences.

**Distributional Semantics**: Word senses are discovered by clustering usage contexts (not just word co-occurrence). The system uses:
- UMAP for dimensionality reduction (1024 → 10 dimensions)
- HDBSCAN for density-based clustering (auto-determines cluster count)
- Claude API for sense validation and definition drafting

**Cluster ≠ Sense**: Clusters represent usage contexts; Claude determines which clusters represent the same sense vs different senses.

## Directory Structure

```
lang-observatory/
├── src/
│   ├── db.py                    # Database connection helper
│   ├── analyzers/
│   │   ├── agent_loop.py        # Claude tool-use agent loop
│   │   ├── agent_tools.py       # Agent tool implementations
│   │   ├── claude_analyzer.py   # Sense validation with Claude API
│   │   ├── cluster_usage.py     # UMAP+HDBSCAN clustering
│   │   ├── embed_texts_segmented.py  # BGE-M3 embedding generation
│   │   └── refresh_vocab_freq.py     # Frequency aggregation
│   ├── scrapers/
│   │   ├── naver_news.py        # Naver News API scraper
│   │   └── youtube_comments.py  # YouTube Data API v3 scraper
│   ├── analyze_morphemes_tf.py  # Kiwi morphological analysis + custom merge rules
│   └── build_segment_lemma_map.py  # Map embeddings to lemmas
├── dashboard/
│   ├── app.py                   # Main dashboard entry
│   ├── auth.py                  # Password protection (currently disabled)
│   └── pages/
│       ├── 1_에이전트와_대화.py      # Conversational agent (main entry point)
│       ├── 2_어휘_사용_동향.py       # Vocabulary trends
│       ├── 3_어휘_의미_탐색.py       # Word search and exploration
│       ├── 4_AI_의미_분석.py        # AI sense analysis with clustering
│       └── 5_AI_분석_결과_모아보기.py  # Validation results gallery
├── scripts/
│   ├── run_pipeline.sh          # Main pipeline orchestration
│   ├── backup_db.sh             # Database backup
│   └── start_db.sh              # Start PostgreSQL
├── prompts/
│   └── sense_analysis.txt       # Claude prompt template for sense validation
└── docker-compose.yml           # PostgreSQL + pgvector setup
```

## Dashboard Pages

**Page Order & Purpose**:
1. **에이전트와 대화** (Agent Chat): Natural language interface — ask questions, agent calls appropriate tools
2. **어휘 사용 동향** (Usage Trends): Emerging words, frequency trends by media
3. **어휘 의미 탐색** (Meaning Exploration): Search for words, view frequencies, dictionary entries, cluster counts
4. **AI 의미 분석** (AI Analysis): Run clustering + Claude validation for a word, view results by media
5. **AI 분석 결과 모아보기** (Validation Gallery): Browse all validation results, sorted to show new senses first

**Design Principles for Dashboard Code**:
- Use lazy loading via tabs to improve performance (data loads only when tab is clicked)
- HTML content must be left-aligned in f-strings to avoid indentation in output (which breaks rendering)
- Always escape user-generated content with `html.escape()` before rendering in `st.markdown(..., unsafe_allow_html=True)`
- Sort validation results to show new senses (신의미) first, regardless of media or validation time

## Development Notes

### Database Connection

All modules use `src/db.py:get_conn()` to connect to PostgreSQL. Credentials come from `.env`:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `POSTGRES_PASSWORD`

### Morphological Analysis

The system uses Kiwi with custom post-processing (`merge_tokens` function in `analyze_morphemes_tf.py`):
- Merges adjacent nouns into compounds (e.g., "인공" + "지능" → "인공지능")
- Combines nouns with derivational suffixes (e.g., "공부" + "하" → "공부하다")
- Combines auxiliary verbs with main verbs
- Whitelist approach: only keeps NNG, NNP, VV, VA (content words)

### Clustering Parameters

In `cluster_usage.py`:
- `MAX_SAMPLES = 1000` — downsample if more than 1000 usage examples
- `MIN_SAMPLES = 30` — require at least 30 examples to cluster
- `UMAP_DIMS = 10` — reduce to 10 dimensions
- `min_cluster_size = max(5, int(n ** 0.5))` — HDBSCAN minimum cluster size

### Validation Card Rendering

When rendering validation results (pages 4 and 5), senses are sorted within each card so new senses appear first:
```python
def sort_key(sense):
    dict_matches = sense.get("dict_sense_matches", {})
    is_existing = any(v is not None for v in dict_matches.values()) if dict_matches else False
    return (is_existing, sense.get("sense_no", 999))
sorted_senses = sorted(senses, key=sort_key)
```

Validation groups are also sorted to show words with new senses first in the gallery view.

### API Keys Required

- `ANTHROPIC_API_KEY` — for Claude API (sense validation, agent chat)
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` — for Naver News Search API
- `YOUTUBE_API_KEY` — for YouTube Data API v3

### Data Preservation Principle

"Store broadly, filter later" — prefer to keep noisy data and filter at query/analysis time rather than discarding during collection. Data lost cannot be recovered; data kept can always be filtered.

### Media Sampling

To balance media representation:
- Naver News is heavily downsampled (1/10) during embedding to prevent overwhelming other media
- YouTube comments are capped per channel to avoid single-channel dominance
- 모두의말뭉치 corpus provides balanced baseline

### Running Clustering for a Word

```python
from analyzers.cluster_usage import cluster_word

# Cluster a word for a specific media source
cluster_word(lemma="단어", pos="NNG", source_id=3)  # 3 = Naver News
```

Source IDs: 3=Naver News, 4=YouTube video, 5=모두의말뭉치 dialogue, 6=모두의말뭉치 newspaper, 7=YouTube comments

### Running Claude Validation

```python
from analyzers.claude_analyzer import fetch_word_data, validate_with_claude

# Fetch data for a word
data = fetch_word_data(lemma="단어", pos="NNG", source_id=3)

# Run Claude validation
result = validate_with_claude(data)
```

The validation result follows 우리말샘 (Urimalsaem) dictionary structure with enhancements for cluster IDs and context distribution.
