#!/bin/bash
# 자동 주식 매매 시스템을 24시간 동안 실행하기 위한 스크립트
# 작성일: 2025년 5월 28일

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# 로그 디렉토리 생성 (없는 경우)
LOG_DIR="./logs"
mkdir -p $LOG_DIR

# 데이터베이스 디렉토리 생성 (없는 경우)
DATA_DIR="./data"
DB_BACKUP_DIR="$DATA_DIR/backup"
mkdir -p $DATA_DIR
mkdir -p $DB_BACKUP_DIR

# 로그 파일 경로 설정
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/trading_log_$TIMESTAMP.log"

echo "===== 자동 주식 매매 시스템 시작 - $(date) =====" | tee -a $LOG_FILE

# 필요한 환경 설정 확인
if [ ! -f "config.py" ]; then
    echo "오류: config.py 파일이 없습니다. 설정 파일을 확인해주세요." | tee -a $LOG_FILE
    exit 1
fi

# Python 버전 확인
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_CMD="python"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo "오류: Python이 설치되어 있지 않습니다." | tee -a $LOG_FILE
        exit 1
    fi
fi

# Python 버전 출력
echo "Python 버전 정보:" | tee -a $LOG_FILE
$PYTHON_CMD --version | tee -a $LOG_FILE

# 필요한 패키지 설치 확인
echo "필요한 패키지 설치 확인 중..." | tee -a $LOG_FILE
$PYTHON_CMD -m pip install -r requirements.txt | tee -a $LOG_FILE

# config.py 설정 확인
echo "설정 파일 내용 확인:" | tee -a $LOG_FILE
echo "AUTO_TRADING_ENABLED 설정:" | tee -a $LOG_FILE
grep "AUTO_TRADING_ENABLED" config.py | tee -a $LOG_FILE
echo "GPT_AUTO_TRADING 설정:" | tee -a $LOG_FILE
grep "GPT_AUTO_TRADING" config.py | tee -a $LOG_FILE
echo "USE_DATABASE 설정:" | tee -a $LOG_FILE
grep "USE_DATABASE" config.py | tee -a $LOG_FILE

# 강제 시장 열림 설정
# 이 부분이 추가됨: 시장 시간에 상관없이 거래 실행
export FORCE_MARKET_OPEN=true
echo "강제 시장 열림 모드 활성화 (FORCE_MARKET_OPEN=true)" | tee -a $LOG_FILE

# 데이터베이스 사용 설정
export USE_DATABASE=true
export DB_TYPE="sqlite"
export SQLITE_DB_PATH="$DATA_DIR/stock_trading.db"
echo "데이터베이스 설정: USE_DATABASE=$USE_DATABASE, DB_TYPE=$DB_TYPE" | tee -a $LOG_FILE
echo "SQLite DB 경로: $SQLITE_DB_PATH" | tee -a $LOG_FILE

# DB 파일이 있는지 확인 (SQLite 경우)
if [ "$DB_TYPE" == "sqlite" ]; then
    if [ -f "$SQLITE_DB_PATH" ]; then
        echo "기존 SQLite DB 파일이 존재합니다: $SQLITE_DB_PATH" | tee -a $LOG_FILE
        
        # DB 백업 생성 (하루에 한 번)
        DB_BACKUP_FILE="$DB_BACKUP_DIR/stock_trading_backup_$(date +"%Y%m%d").db"
        if [ ! -f "$DB_BACKUP_FILE" ]; then
            echo "DB 백업 생성 중: $DB_BACKUP_FILE" | tee -a $LOG_FILE
            cp "$SQLITE_DB_PATH" "$DB_BACKUP_FILE"
        else
            echo "오늘자 DB 백업이 이미 존재합니다: $DB_BACKUP_FILE" | tee -a $LOG_FILE
        fi
    else
        echo "SQLite DB 파일이 존재하지 않습니다. 프로그램 실행 시 자동 생성됩니다." | tee -a $LOG_FILE
    fi
fi

# API 테스트 실행
echo "한국투자증권 API 테스트 중..." | tee -a $LOG_FILE
$PYTHON_CMD -u test_kis_connection.py | tee -a $LOG_FILE

# API 테스트 결과 확인
API_TEST_EXIT=$?
if [ $API_TEST_EXIT -ne 0 ]; then
    echo "경고: API 연결 테스트에 실패했습니다. 프로그램이 계속 실행됩니다만, 거래가 실패할 수 있습니다." | tee -a $LOG_FILE
else
    echo "API 연결 테스트 성공!" | tee -a $LOG_FILE
fi

# 프로세스 관리를 위한 함수
function cleanup {
    echo "프로그램 종료 신호를 받았습니다. 정리 중..." | tee -a $LOG_FILE
    # 자식 프로세스 종료
    if [ ! -z "$PID" ]; then
        kill $PID 2>/dev/null
    fi
    echo "===== 자동 주식 매매 시스템 종료 - $(date) =====" | tee -a $LOG_FILE
    exit 0
}

# SIGTERM, SIGINT 신호 처리
trap cleanup SIGTERM SIGINT

# 주식 매매 프로그램 실행
echo "main.py 실행 중 (강제 시장 열림 모드)..." | tee -a $LOG_FILE

# 디버깅을 위해 main.py가 직접 출력하도록 변경
echo "$(date): 프로그램 시작" | tee -a $LOG_FILE
$PYTHON_CMD -u main.py --force-market-open | tee -a $LOG_FILE

# 프로그램 종료 코드 확인
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "경고: 프로그램이 비정상 종료되었습니다 (종료 코드: $EXIT_CODE)." | tee -a $LOG_FILE
else
    echo "프로그램이 정상 종료되었습니다." | tee -a $LOG_FILE
fi

echo "===== 자동 주식 매매 시스템 종료 - $(date) =====" | tee -a $LOG_FILE