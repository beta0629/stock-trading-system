#!/usr/bin/env python
"""
한국투자증권 API와 데이터베이스 통합 테스트 스크립트
API로 주식 정보 조회 후 데이터베이스에 저장하는 기능 테스트
"""
import sys
import os
import logging
import time
from datetime import datetime
import pandas as pd

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('kis_db_integration_test.log')
    ]
)
logger = logging.getLogger('KIS_DB_TEST')

# 상위 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 설정 및 모듈 import
import config
from src.trading.kis_api import KISAPI
from src.database.db_manager import DatabaseManager

# API 요청 간격 (초)
API_REQUEST_INTERVAL = 1.5

def test_kis_db_integration():
    """KIS API와 데이터베이스 통합 테스트"""
    
    logger.info("=" * 50)
    logger.info("한국투자증권 API와 데이터베이스 통합 테스트 시작")
    logger.info("=" * 50)
    
    # 데이터베이스 관리자 인스턴스 생성
    db_manager = DatabaseManager.get_instance(config)
    
    # KIS API 객체 생성 (모의투자로 설정)
    api = KISAPI(config)
    
    # 모의투자 모드인지 확인
    if api.real_trading:
        api.switch_to_virtual()
    
    logger.info(f"API 모드: {api.get_trading_mode()}")
    logger.info(f"계좌번호: {api.account_number}")
    logger.info(f"데이터베이스 타입: {db_manager.db_type}")
    
    # 1. API 연결 및 인증 테스트
    logger.info("\n1. API 연결 테스트")
    if api.connect():
        logger.info("API 연결 성공")
    else:
        logger.error("API 연결 실패")
        return
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 2. 로그인 테스트
    logger.info("\n2. 로그인 테스트")
    if api.login():
        logger.info("로그인 성공")
    else:
        logger.error("로그인 실패")
        return
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 3. 계좌 잔고 조회
    logger.info("\n3. 계좌 잔고 조회")
    balance = api.get_balance()
    logger.info(f"계좌 잔고: {balance}")
    
    # 시스템 이벤트 로그에 계좌 조회 기록
    db_manager.log_system_event("API_CALL", "계좌 잔고 조회", {
        "balance": balance,
        "account": api.account_number,
        "trading_mode": api.get_trading_mode()
    })
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 4. 주식 현재가 조회 (삼성전자)
    logger.info("\n4. 삼성전자 현재가 조회")
    stock_code = "005930"  # 삼성전자
    stock_name = "삼성전자"
    current_price = api.get_current_price(stock_code)
    logger.info(f"삼성전자 현재가: {current_price}원")
    
    if current_price <= 0:
        logger.error("현재가 조회 실패")
        return
    
    # 주가 데이터 캐싱
    today = datetime.now().strftime("%Y-%m-%d")
    db_manager.cache_price_data(stock_code, "KR", today, current_price, current_price, current_price, current_price, 0)
    logger.info("주가 데이터 데이터베이스에 캐싱 완료")
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 5. 가상의 매수 거래 기록 (실제 주문은 제외)
    logger.info("\n5. 가상 매수 거래 기록 테스트")
    quantity = 1  # 1주
    buy_price = current_price
    amount = buy_price * quantity
    
    # 데이터베이스에 거래 기록 저장
    db_manager.record_trade(
        symbol=stock_code,
        market="KR",
        action="buy",
        price=buy_price,
        quantity=quantity,
        amount=amount,
        trade_type="limit",
        strategy="db_test",
        confidence=0.8,
        order_id="test_order_001",
        status="executed",
        broker="KIS"
    )
    logger.info(f"매수 거래 기록 저장 완료: {stock_name} {quantity}주 @ {buy_price}원")
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 6. 포트폴리오 확인
    logger.info("\n6. 데이터베이스 포트폴리오 확인")
    portfolio = db_manager.get_portfolio()
    logger.info(f"포트폴리오 항목 수: {len(portfolio)}")
    if not portfolio.empty:
        logger.info(f"포트폴리오 첫 항목: {portfolio.iloc[0].to_dict()}")
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 7. 가상의 매도 거래 기록 (실제 주문은 제외)
    logger.info("\n7. 가상 매도 거래 기록 테스트")
    sell_price = int(current_price * 1.01)  # 1% 높은 가격에 매도
    amount = sell_price * quantity
    
    # 데이터베이스에 거래 기록 저장
    db_manager.record_trade(
        symbol=stock_code,
        market="KR",
        action="sell",
        price=sell_price,
        quantity=quantity,
        amount=amount,
        trade_type="limit",
        strategy="db_test",
        confidence=0.8,
        order_id="test_order_002",
        status="executed",
        broker="KIS"
    )
    logger.info(f"매도 거래 기록 저장 완료: {stock_name} {quantity}주 @ {sell_price}원")
    
    # API 요청 간격 대기
    time.sleep(API_REQUEST_INTERVAL)
    
    # 8. 거래 이력 조회
    logger.info("\n8. 데이터베이스 거래 이력 조회")
    trade_history = db_manager.get_trade_history(symbol=stock_code, limit=10)
    logger.info(f"거래 이력 항목 수: {len(trade_history)}")
    if not trade_history.empty:
        logger.info(f"최근 거래 이력: {trade_history.iloc[0].to_dict()}")
    
    # 9. 데이터베이스에 GPT 추천 저장 테스트
    logger.info("\n9. GPT 추천 저장 테스트")
    symbols = [
        {"code": "005930", "name": "삼성전자", "confidence": 0.92},
        {"code": "000660", "name": "SK하이닉스", "confidence": 0.89},
        {"code": "051910", "name": "LG화학", "confidence": 0.85}
    ]
    rationale = "반도체 및 배터리 시장의 높은 성장성이 예상되며, 삼성전자와 SK하이닉스는 AI 칩 수요 증가로 수혜가 예상됩니다."
    
    db_manager.save_gpt_recommendations("KR", "growth", symbols, rationale, "gpt-4o")
    logger.info("GPT 추천 저장 완료")
    
    # 10. 최근 GPT 추천 조회
    logger.info("\n10. 최근 GPT 추천 조회")
    recommendations = db_manager.get_recent_recommendations(market="KR", limit=5)
    logger.info(f"GPT 추천 항목 수: {len(recommendations)}")
    if not recommendations.empty:
        logger.info(f"최근 GPT 추천: {recommendations.iloc[0].to_dict()}")
    
    # 11. 시스템 이벤트 로그 조회
    logger.info("\n11. 시스템 이벤트 로그 조회")
    events = db_manager.get_system_events(limit=5)
    logger.info(f"시스템 이벤트 수: {len(events)}")
    if not events.empty:
        logger.info(f"최근 시스템 이벤트: {events.iloc[0].to_dict()}")
    
    # 12. 날짜별 거래 요약
    logger.info("\n12. 오늘자 거래 요약")
    summary = db_manager.get_daily_trading_summary()
    if summary is not None and not summary.empty:
        logger.info(f"오늘 거래 요약: {summary.to_dict('records')}")
    else:
        logger.info("오늘 거래 요약 없음")
    
    # API 연결 종료
    api.disconnect()
    logger.info("\nAPI 연결 종료")
    
    logger.info("=" * 50)
    logger.info("한국투자증권 API와 데이터베이스 통합 테스트 완료")
    logger.info("=" * 50)

if __name__ == "__main__":
    # 테스트 실행
    test_kis_db_integration()