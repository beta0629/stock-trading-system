#!/usr/bin/env python3
"""
모의 자동 매매 시스템 자동 재시작 래퍼 스크립트
타임아웃이나 오류로 인해 종료되는 경우 다시 시작합니다.
"""
import subprocess
import time
import sys
import logging
import os
import signal
import threading
from datetime import timedelta  # Keep for timedelta functionality
from src.utils.time_utils import get_current_time  # Use our time utility

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('auto_restart.log')
    ]
)
logger = logging.getLogger('AutoRestart')

# GitHub Actions 환경 감지 및 환경 변수 설정
is_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
if is_github_actions:
    logger.info("GitHub Actions 환경이 감지되었습니다.")
    # GitHub Actions에서는 기본적으로 MAX_RUNTIME_MINUTES를 55분으로 설정
    # (GitHub Actions의 일반적인 작업 제한 시간은 60분)
    if 'MAX_RUNTIME_MINUTES' not in os.environ:
        os.environ['MAX_RUNTIME_MINUTES'] = '55'
        logger.info("GitHub Actions 환경에서 MAX_RUNTIME_MINUTES=55로 설정했습니다.")
    else:
        logger.info(f"GitHub Actions 환경에서 MAX_RUNTIME_MINUTES={os.environ['MAX_RUNTIME_MINUTES']}로 설정되어 있습니다.")
else:
    # 로컬 환경에서는 MAX_RUNTIME_MINUTES 환경 변수를 무제한으로 설정
    os.environ['MAX_RUNTIME_MINUTES'] = '0'  # 0으로 설정하면 무제한
    logger.info("로컬 환경에서 MAX_RUNTIME_MINUTES=0(무제한)으로 설정했습니다.")

# GitHub Actions에서 연결 유지를 위한 활동 로그 출력 간격 (초)
HEARTBEAT_INTERVAL = 60 if is_github_actions else None

def heartbeat_thread():
    """GitHub Actions에서 연결이 끊어지지 않도록 주기적으로 로그 출력"""
    heartbeat_count = 0
    while True:
        heartbeat_count += 1
        logger.info(f"GitHub Actions 연결 유지 신호 #{heartbeat_count} - 활성 상태 확인")
        time.sleep(HEARTBEAT_INTERVAL)

def run_with_retry(script_path, max_retries=None):
    """
    오류나 타임아웃으로 종료될 경우 지정된 스크립트를 재실행
    
    Args:
        script_path: 실행할 스크립트 경로
        max_retries: 최대 재시도 횟수 (None이면 무제한)
    """
    retry_count = 0
    
    def handle_signal(sig, frame):
        logger.info("사용자에 의한 중단 신호 감지. 프로세스를 종료합니다.")
        sys.exit(0)
    
    # CTRL+C 신호 처리
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # GitHub Actions 환경에서 하트비트 스레드 시작
    if is_github_actions and HEARTBEAT_INTERVAL:
        heartbeat = threading.Thread(target=heartbeat_thread, daemon=True)
        heartbeat.start()
        logger.info(f"GitHub Actions 연결 유지 스레드가 시작되었습니다 (간격: {HEARTBEAT_INTERVAL}초)")
    
    while max_retries is None or retry_count < max_retries:
        start_time = get_current_time()  # Use time_utils
        logger.info(f"스크립트 실행 시작 (시도 #{retry_count + 1}): {script_path}")
        
        try:
            # 스크립트 실행 (환경 변수 현재 프로세스에서 상속)
            # 출력을 캡처하지 않고 그대로 콘솔에 표시하여 장시간 무응답을 방지
            process = subprocess.Popen(
                [sys.executable, script_path],
                env=os.environ,  # 환경 변수 전달
                stdout=None,     # 표준 출력을 그대로 표시
                stderr=None      # 표준 에러를 그대로 표시
            )
            
            # 프로세스가 끝날 때까지 대기
            exit_code = process.wait()
            
            # 정상 종료된 경우 (반환 코드 0)
            if exit_code == 0:
                logger.info(f"스크립트가 정상 종료되었습니다 (반환 코드: {exit_code})")
                break
            else:
                logger.warning(f"스크립트가 오류 코드와 함께 종료되었습니다 (반환 코드: {exit_code})")
        
        except subprocess.CalledProcessError as e:
            logger.error(f"스크립트 실행 중 오류 발생: {e}")
        except KeyboardInterrupt:
            logger.info("사용자에 의한 중단. 프로세스를 종료합니다.")
            break
        except Exception as e:
            logger.error(f"예상치 못한 오류 발생: {e}")
        
        # 재시작 전 대기 시간
        retry_count += 1
        end_time = get_current_time()  # Use time_utils
        elapsed_seconds = (end_time - start_time).total_seconds()
        
        # 실행 시간이 짧을 경우 (10초 미만) 재시작 전에 대기 시간을 좀더 길게
        if elapsed_seconds < 10:
            wait_time = 30  # 오류가 계속 발생한다면 30초 대기
        else:
            wait_time = 5   # 정상 실행되다 종료된 경우 5초 후 재시작
        
        logger.info(f"스크립트가 {elapsed_seconds:.1f}초 동안 실행되었습니다. {wait_time}초 후 재시작합니다...")
        time.sleep(wait_time)
    
    if max_retries is not None and retry_count >= max_retries:
        logger.warning(f"최대 재시도 횟수({max_retries}회)에 도달했습니다. 프로세스를 종료합니다.")

if __name__ == "__main__":
    script_to_run = "main.py"
    
    # 명령행 인자로 다른 스크립트를 지정한 경우
    if len(sys.argv) > 1:
        script_to_run = sys.argv[1]
    
    logger.info(f"자동 매매 시스템 자동 재시작 래퍼 스크립트 시작 (대상: {script_to_run})")
    # GitHub Actions 환경에서만 제한된 재시도 횟수를 설정, 로컬에서는 무제한 재시도
    max_retries = 5 if is_github_actions else None
    run_with_retry(script_to_run, max_retries)
    logger.info("자동 매매 시스템 자동 재시작 래퍼 스크립트 종료")