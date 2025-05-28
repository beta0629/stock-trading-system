"""
주식 매매 시스템 데이터베이스 초기화 및 관리 스크립트
"""
import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('DB_INIT')

# 데이터베이스 관리자 클래스 가져오기
try:
    import os
    import sys
    # 상위 디렉토리를 시스템 경로에 추가
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)
    
    # 환경 변수에서 직접 설정 가져오기
    USE_DATABASE = os.environ.get("USE_DATABASE", "True").lower() == "true"
    DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(parent_dir, "data", "stock_trading.db"))
    
    # config 모듈과 필요한 클래스 가져오기
    import config
    from src.database.db_manager import DatabaseManager
except ImportError:
    logger.error("모듈 가져오기 오류. 실행 경로를 확인하세요.")
    sys.exit(1)

def initialize_database():
    """데이터베이스 초기화"""
    logger.info("데이터베이스 초기화 시작")
    
    # 환경 변수 정보 로그 출력
    logger.info(f"데이터베이스 사용 여부 환경 변수: {os.environ.get('USE_DATABASE', 'Not Set')}")
    
    # 데이터베이스 관리자 인스턴스 생성
    db_manager = DatabaseManager.get_instance()
    
    logger.info(f"데이터베이스 타입: {db_manager.db_type}")
    if db_manager.db_type == 'sqlite':
        logger.info(f"데이터베이스 경로: {db_manager.db_path}")
    else:
        logger.info(f"데이터베이스 서버: {db_manager.mysql_host}")
    
    # 데이터베이스 초기화 여부 확인
    if db_manager.use_db:
        logger.info("데이터베이스 초기화 완료")
    else:
        logger.warning("데이터베이스 사용이 비활성화되어 있습니다.")
    
    return db_manager

def add_sample_data(db_manager):
    """샘플 데이터 추가"""
    logger.info("샘플 데이터 추가 시작")
    
    # 샘플 거래 내역 추가
    sample_trades = [
        {"symbol": "005930", "market": "KR", "action": "buy", "price": 67000, "quantity": 10, "amount": 670000},
        {"symbol": "000660", "market": "KR", "action": "buy", "price": 98000, "quantity": 5, "amount": 490000},
        {"symbol": "AAPL", "market": "US", "action": "buy", "price": 156.5, "quantity": 10, "amount": 1565.0},
        {"symbol": "005930", "market": "KR", "action": "sell", "price": 69000, "quantity": 5, "amount": 345000},
    ]
    
    for trade in sample_trades:
        db_manager.record_trade(
            trade["symbol"], trade["market"], trade["action"], trade["price"], 
            trade["quantity"], trade["amount"], strategy="sample"
        )
    
    # 샘플 포트폴리오 추가
    sample_portfolio = [
        {"symbol": "005930", "market": "KR", "quantity": 5, "avg_price": 67000, "current_price": 69000},
        {"symbol": "000660", "market": "KR", "quantity": 5, "avg_price": 98000, "current_price": 99000},
        {"symbol": "AAPL", "market": "US", "quantity": 10, "avg_price": 156.5, "current_price": 162.7},
    ]
    
    for item in sample_portfolio:
        db_manager.update_portfolio(
            item["symbol"], item["market"], item["quantity"], 
            item["avg_price"], item["current_price"]
        )
    
    # 샘플 GPT 추천 종목 추가
    sample_recommendations = [
        {
            "market": "KR", 
            "strategy": "balanced", 
            "symbols": [
                {"code": "005930", "name": "삼성전자", "reasons": "반도체 호황 예상", "confidence": 0.85},
                {"code": "000660", "name": "SK하이닉스", "reasons": "메모리 시장 성장", "confidence": 0.82},
                {"code": "035420", "name": "NAVER", "reasons": "AI 기술 투자", "confidence": 0.78},
            ],
            "rationale": "국내 대형주 기반으로 테크 섹터 집중 투자 전략"
        },
        {
            "market": "US", 
            "strategy": "growth", 
            "symbols": [
                {"code": "AAPL", "name": "Apple Inc.", "reasons": "신규 기기 출시 예정", "confidence": 0.88},
                {"code": "MSFT", "name": "Microsoft", "reasons": "클라우드 성장", "confidence": 0.87},
                {"code": "NVDA", "name": "NVIDIA", "reasons": "AI 칩셋 수요 증가", "confidence": 0.92},
            ],
            "rationale": "AI 관련 기술주 중심 성장 전략"
        }
    ]
    
    for rec in sample_recommendations:
        db_manager.save_gpt_recommendations(
            rec["market"], rec["strategy"], rec["symbols"], rec["rationale"]
        )
    
    # 샘플 시스템 이벤트 로그
    sample_events = [
        {"event_type": "system_start", "description": "시스템 시작", "details": {"version": "1.0.0"}},
        {"event_type": "api_error", "description": "API 요청 오류", "details": {"error": "timeout", "retry": 3}},
        {"event_type": "trade_success", "description": "거래 성공", "details": {"symbol": "005930", "action": "buy"}},
    ]
    
    for event in sample_events:
        db_manager.log_system_event(
            event["event_type"], event["description"], event["details"]
        )
    
    # 샘플 주가 데이터
    today = datetime.now().date()
    sample_prices = []
    
    for i in range(1, 11):  # 10일간의 데이터
        date = today - timedelta(days=i)
        sample_prices.append({
            "symbol": "005930", "market": "KR", "date": date.strftime("%Y-%m-%d"),
            "open_price": 67000 + i * 100, "high_price": 67500 + i * 100,
            "low_price": 66500 + i * 100, "close_price": 67200 + i * 100, 
            "volume": 10000000 + i * 100000
        })
    
    for price in sample_prices:
        db_manager.cache_price_data(
            price["symbol"], price["market"], price["date"], price["open_price"], 
            price["high_price"], price["low_price"], price["close_price"], price["volume"]
        )
    
    logger.info("샘플 데이터 추가 완료")

def view_database(db_manager):
    """데이터베이스 내용 조회"""
    logger.info("데이터베이스 조회 시작")
    
    # 거래 내역 조회
    trade_history = db_manager.get_trade_history(limit=10)
    print("\n===== 거래 내역 (최근 10건) =====")
    if not trade_history.empty:
        print(trade_history[['timestamp', 'symbol', 'market', 'action', 'price', 'quantity', 'amount']])
    else:
        print("거래 내역이 없습니다.")
    
    # 포트폴리오 조회
    portfolio = db_manager.get_portfolio()
    print("\n===== 현재 포트폴리오 =====")
    if not portfolio.empty:
        print(portfolio[['symbol', 'market', 'quantity', 'avg_price', 'current_price', 'profit_loss', 'profit_loss_pct']])
    else:
        print("포트폴리오가 비어있습니다.")
    
    # GPT 추천 종목
    recommendations = db_manager.get_recent_recommendations()
    print("\n===== GPT 추천 종목 (최근) =====")
    if not recommendations.empty:
        for _, rec in recommendations.iterrows():
            print(f"{rec['timestamp']} {rec['market']} ({rec['strategy']} 전략):")
            symbols = rec['symbols']
            if isinstance(symbols, list):
                for sym in symbols:
                    if isinstance(sym, dict) and 'code' in sym and 'name' in sym:
                        print(f"  - {sym['code']} ({sym['name']})")
                    else:
                        print(f"  - {sym}")
            else:
                print(f"  {symbols}")
    else:
        print("추천 종목이 없습니다.")
    
    logger.info("데이터베이스 조회 완료")

def backup_database(db_manager):
    """데이터베이스 백업"""
    if db_manager.db_type != 'sqlite':
        logger.warning("현재 SQLite 데이터베이스만 백업을 지원합니다.")
        return
    
    logger.info("데이터베이스 백업 시작")
    backup_path = db_manager.backup_database()
    
    if backup_path:
        logger.info(f"백업 완료: {backup_path}")
    else:
        logger.error("백업 실패")

def optimize_database(db_manager):
    """SQLite 데이터베이스 최적화"""
    if db_manager.db_type != 'sqlite':
        logger.warning("현재 SQLite 데이터베이스만 최적화를 지원합니다.")
        return
    
    logger.info("데이터베이스 최적화 시작 (VACUUM)")
    result = db_manager.vacuum_database()
    
    if result:
        logger.info("최적화 완료")
    else:
        logger.error("최적화 실패")

def main():
    parser = argparse.ArgumentParser(description='주식 매매 시스템 데이터베이스 관리 도구')
    
    # 명령어 그룹 설정
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--init', action='store_true', help='데이터베이스 초기화')
    group.add_argument('--sample', action='store_true', help='샘플 데이터 추가')
    group.add_argument('--view', action='store_true', help='데이터베이스 내용 조회')
    group.add_argument('--backup', action='store_true', help='데이터베이스 백업')
    group.add_argument('--optimize', action='store_true', help='데이터베이스 최적화')
    
    args = parser.parse_args()
    
    # 데이터베이스 관리자 초기화
    db_manager = initialize_database()
    
    # 명령에 따른 작업 수행
    if args.init:
        logger.info("데이터베이스가 이미 초기화되었습니다.")
    elif args.sample:
        add_sample_data(db_manager)
    elif args.view:
        view_database(db_manager)
    elif args.backup:
        backup_database(db_manager)
    elif args.optimize:
        optimize_database(db_manager)

if __name__ == "__main__":
    main()