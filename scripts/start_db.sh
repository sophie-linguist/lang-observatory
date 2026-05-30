#!/bin/bash
# PC 부팅 후 DB 컨테이너를 안전하게 시작
# initdb 타이밍 문제 방지: pgdata 확인 후 restart
PGDATA="/home/ssohe/lang-observatory/pgdata"
LOG="/home/ssohe/lang-observatory/logs/start_db.log"

echo "$(date) DB 시작 스크립트 실행" >> $LOG

# pgdata가 보일 때까지 대기
for i in $(seq 1 60); do
    if [ -f "$PGDATA/PG_VERSION" ]; then
        echo "$(date) pgdata 확인 완료" >> $LOG
        break
    fi
    sleep 2
done

# 컨테이너가 이미 떠 있으면 restart로 bind mount 재연결
docker restart lang-observatory-db >> $LOG 2>&1
echo "$(date) DB 컨테이너 restart 완료" >> $LOG
