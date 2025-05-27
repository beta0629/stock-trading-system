#!/usr/bin/env python3
"""
주식 자동매매 시스템 상태 확인 스크립트
"""
import os
import sys
import logging
import argparse
import datetime
import pandas as pd
from src.data.stock_data import StockData
from src.trading.kis_api import KISAPI
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('StatusChecker')


def check_api_connection():
    """API 연결 상태 확인"""
    try:
        kis_api = KISAPI(config)
        connected = kis_api.connect()
        mode = "실전투자" if kis_api.real_trading else "모의투자"
        
        if connected:
            print(f"✅ 한국투자증권 API 연결 성공 (모드: {mode})")
            
            # 계좌 잔고 확인
            balance = kis_api.get_balance()
            if balance:
                print(f"💰 계좌 잔고: {balance.get('예수금', 0):,.0f}원")
            
            # 보유 종목 확인
            positions = kis_api.get_positions()
            if positions:
                print(f"\n📊 보유 종목 ({len(positions)}개):")
                for pos in positions:
                    try:
                        # 평균단가가 0인 경우 오류 방지
                        if pos['평균단가'] <= 0:
                            profit_pct = 0.0
                        else:
                            profit_pct = (pos['현재가'] / pos['평균단가'] - 1) * 100
                            
                        print(f"  - {pos['종목명']} ({pos['종목코드']}): {pos['보유수량']}주, 평균단가: {pos['평균단가']:,.0f}원, 현재가: {pos['현재가']:,.0f}원, 손익률: {profit_pct:.2f}%")
                    except Exception as detail_error:
                        print(f"  - {pos.get('종목명', '알 수 없음')} ({pos.get('종목코드', '???')}): 상세 정보 표시 오류")
                        logger.error(f"보유 종목 상세 정보 표시 중 오류: {detail_error}")
            else:
                print("📊 보유 종목 없음")
                
        else:
            print(f"❌ 한국투자증권 API 연결 실패")
        
        # 연결 해제
        kis_api.disconnect()
        
    except Exception as e:
        print(f"❌ API 연결 확인 중 오류 발생: {e}")


def check_stock_data():
    """주식 데이터 확인"""
    try:
        stock_data = StockData(config)
        
        # 국내 주식 데이터 확인
        print("\n🇰🇷 국내 주식 데이터:")
        for code in config.KR_STOCKS[:3]:  # 처음 3개만 확인
            df = stock_data.get_korean_stock_data(code)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                print(f"  - {code}: 최근 가격 {latest['Close']:,.0f}원, 거래량 {latest['Volume']:,.0f}, RSI {latest.get('RSI', 'N/A')}")
            else:
                print(f"  - {code}: 데이터 없음")
        
        # 미국 주식 데이터 확인
        print("\n🇺🇸 미국 주식 데이터:")
        for symbol in config.US_STOCKS[:3]:  # 처음 3개만 확인
            df = stock_data.get_us_stock_data(symbol)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                print(f"  - {symbol}: 최근 가격 ${latest['Close']:.2f}, 거래량 {latest['Volume']:,.0f}, RSI {latest.get('RSI', 'N/A')}")
            else:
                print(f"  - {symbol}: 데이터 없음")
                
    except Exception as e:
        print(f"❌ 주식 데이터 확인 중 오류 발생: {e}")


def check_system_status():
    """시스템 상태 확인"""
    # 프로세스 확인
    try:
        import psutil
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'python' in proc.info['name'].lower() and len(proc.info['cmdline']) > 1:
                cmd = ' '.join(proc.info['cmdline'])
                if 'main.py' in cmd:
                    print(f"✅ 주식 자동매매 시스템 실행 중 (PID: {proc.info['pid']})")
                    return True
                    
        print("❌ 주식 자동매매 시스템이 실행되고 있지 않습니다.")
        return False
    except ImportError:
        print("ℹ️ psutil 패키지가 설치되어 있지 않아 프로세스 확인을 건너뜁니다.")
        return None
    except Exception as e:
        print(f"❌ 시스템 상태 확인 중 오류 발생: {e}")
        return None


def check_log_file():
    """로그 파일 확인"""
    log_file = 'stock_analysis.log'
    
    if os.path.exists(log_file):
        # 마지막 10개 로그 메시지 출력
        print(f"\n📝 최근 로그 메시지 ({log_file}):")
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                for line in lines[-10:]:
                    print(f"  {line.strip()}")
        except Exception as e:
            print(f"❌ 로그 파일 읽기 오류: {e}")
    else:
        print(f"\n❌ 로그 파일이 존재하지 않습니다: {log_file}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='주식 자동매매 시스템 상태 확인')
    parser.add_argument('--api', action='store_true', help='API 연결 상태 확인')
    parser.add_argument('--data', action='store_true', help='주식 데이터 확인')
    parser.add_argument('--system', action='store_true', help='시스템 상태 확인')
    parser.add_argument('--log', action='store_true', help='로그 파일 확인')
    parser.add_argument('--all', action='store_true', help='모든 상태 확인')
    
    args = parser.parse_args()
    
    # 옵션이 지정되지 않았거나 --all 인 경우 모두 실행
    run_all = args.all or not (args.api or args.data or args.system or args.log)
    
    print(f"===== 주식 자동매매 시스템 상태 확인 ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) =====\n")
    
    if args.api or run_all:
        check_api_connection()
    
    if args.data or run_all:
        check_stock_data()
    
    if args.system or run_all:
        check_system_status()
    
    if args.log or run_all:
        check_log_file()
        
    print("\n===== 상태 확인 완료 =====")


if __name__ == "__main__":
    main()