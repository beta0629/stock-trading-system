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
    
    while max_retries is None or retry_count < max_retries:
        start_time = get_current_time()  # Use time_utils
        logger.info(f"스크립트 실행 시작 (시도 #{retry_count + 1}): {script_path}")
        
        try:
            # 스크립트 실행
            process = subprocess.run([sys.executable, script_path], 
                                    check=True)
            exit_code = process.returncode
            
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
    script_to_run = "test_mock_auto_trading.py"
    
    # 명령행 인자로 다른 스크립트를 지정한 경우
    if len(sys.argv) > 1:
        script_to_run = sys.argv[1]
    
    logger.info(f"모의 자동 매매 시스템 자동 재시작 래퍼 스크립트 시작 (대상: {script_to_run})")
    run_with_retry(script_to_run)
    logger.info("모의 자동 매매 시스템 자동 재시작 래퍼 스크립트 종료")