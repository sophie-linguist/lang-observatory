FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 (matplotlib 한글 폰트, psycopg2 빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드는 docker-compose volume으로 마운트할 거라 COPY 안 함

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
