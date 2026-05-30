#!/bin/bash
set -e
# 설정
BACKUP_DIR="/home/ssohe/lang-observatory/backups"
CONTAINER="lang-observatory-db"
DB_NAME="lang_observatory"
DB_USER="observatory"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_${DATE}.sql.gz"
KEEP_DAYS=3
# 백업 폴더 생성
mkdir -p $BACKUP_DIR
# DB 덤프 → gzip 압축 (embeddings 제외 - 임베딩은 다시 만들 수 있음)
docker exec $CONTAINER pg_dump -U $DB_USER $DB_NAME --exclude-table-data=embeddings | gzip > $BACKUP_FILE
# 오래된 백업 삭제 (7일 초과)
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +$KEEP_DAYS -delete
echo "$(date): 백업 완료 - $BACKUP_FILE"
