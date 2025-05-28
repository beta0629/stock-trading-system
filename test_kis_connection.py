#!/usr/bin/env python
"""
한국투자증권 API 연결 상태 테스트 스크립트
run_stock_trader.sh에서 API 연결 테스트를 위해 호출됩니다.
"""
import os
import sys
import logging
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('KIS_Connection_Test')

# 상위 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 설정 및 모듈 import
try:
    import config
    from src.trading.kis_api import KISAPI
except ImportError as e:
    logger.error(f"모듈 임포트 실패: {e}")
    sys.exit(1)

def test_api_connection():
    """API 연결 테스트"""
    
    logger.info("=" * 50)
    logger.info("한국투자증권 API 연결 테스트 시작")
    logger.info("=" * 50)
    
    # KIS API 객체 생성
    try:
        api = KISAPI(config)
        logger.info(f"API 모드: {api.get_trading_mode()}")
    except Exception as e:
        logger.error(f"API 객체 생성 실패: {e}")
        return False
    
    # 1. API 연결 테스트
    try:
        if api.connect():
            logger.info("API 연결 성공")
        else:
            logger.error("API 연결 실패")
            return False
    except Exception as e:
        logger.error(f"API 연결 중 오류 발생: {e}")
        return False
    
    # 2. 로그인 테스트 (선택적)
    try:
        if api.login():
            logger.info("로그인 성공")
        else:
            logger.warning("로그인 실패. 일부 기능은 사용할 수 없습니다.")
            # 로그인 실패는 경고로 처리하고 계속 진행
    except Exception as e:
        logger.error(f"로그인 중 오류 발생: {e}")
        # 로그인 오류는 경고로 처리하고 계속 진행
    
    # 3. 기본 API 기능 테스트 (삼성전자 현재가 조회)
    try:
        symbol = "005930"  # 삼성전자
        current_price = api.get_current_price(symbol)
        if current_price > 0:
            logger.info(f"삼성전자(005930) 현재가 조회 성공: {current_price}원")
        else:
            logger.error(f"현재가 조회 실패: {current_price}")
            return False
    except Exception as e:
        logger.error(f"현재가 조회 중 오류 발생: {e}")
        return False
    
    # 4. 계좌 잔고 조회 테스트
    try:
        balance = api.get_balance()
        if balance:
            logger.info(f"계좌 잔고 조회 성공: {balance}")
        else:
            logger.warning("계좌 잔고 조회 실패. 계좌 정보를 확인해주세요.")
            # 잔고 조회 실패는 경고로 처리하고 계속 진행
    except Exception as e:
        logger.error(f"계좌 잔고 조회 중 오류 발생: {e}")
        # 잔고 조회 오류는 경고로 처리하고 계속 진행
    
    # API 연결 종료
    api.disconnect()
    logger.info("API 연결 테스트 완료")
    
    return True

if __name__ == "__main__":
    success = test_api_connection()
    
    if success:
        logger.info("API 연결 테스트 성공")
        sys.exit(0)  # 성공: 종료 코드 0
    else:
        logger.error("API 연결 테스트 실패")
        sys.exit(1)  # 실패: 종료 코드 1