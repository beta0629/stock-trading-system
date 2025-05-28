#!/bin/bash
# 모의투자 자동 주식 매매 시스템 실행 스크립트
# 작성일: 2025년 5월 28일

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# 로그 디렉토리 생성 (없는 경우)
LOG_DIR="./logs"
mkdir -p $LOG_DIR

# 로그 파일 경로 설정
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/mock_trading_log_$TIMESTAMP.log"

echo "===== 모의투자 자동 주식 매매 시스템 시작 - $(date) =====" | tee -a $LOG_FILE

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

# 환경 변수 설정
export SIMULATION_MODE=true
export KIS_REAL_TRADING=false
export FORCE_MARKET_OPEN=true

echo "모의투자 모드 활성화 (SIMULATION_MODE=true, KIS_REAL_TRADING=false)" | tee -a $LOG_FILE
echo "강제 시장 열림 모드 활성화 (FORCE_MARKET_OPEN=true)" | tee -a $LOG_FILE

# 프로세스 관리를 위한 함수
function cleanup {
    echo "프로그램 종료 신호를 받았습니다. 정리 중..." | tee -a $LOG_FILE
    # 자식 프로세스 종료
    if [ ! -z "$PID" ]; then
        kill $PID 2>/dev/null
    fi
    echo "===== 모의투자 자동 주식 매매 시스템 종료 - $(date) =====" | tee -a $LOG_FILE
    exit 0
}

# SIGTERM, SIGINT 신호 처리
trap cleanup SIGTERM SIGINT

# 모의투자 실행
echo "모의투자 실행 중 (test_mock_auto_trading.py)..." | tee -a $LOG_FILE
echo "$(date): 프로그램 시작" | tee -a $LOG_FILE

$PYTHON_CMD -u test_mock_auto_trading.py | tee -a $LOG_FILE

# 프로그램 종료 코드 확인
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "경고: 프로그램이 비정상 종료되었습니다 (종료 코드: $EXIT_CODE)." | tee -a $LOG_FILE
else
    echo "프로그램이 정상 종료되었습니다." | tee -a $LOG_FILE
fi

echo "===== 모의투자 자동 주식 매매 시스템 종료 - $(date) =====" | tee -a $LOG_FILE