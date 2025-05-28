#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import pandas as pd
import logging
from datetime import datetime
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy
from src.data.stock_data import StockData
from src.analysis.technical import add_technical_indicators

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("gpt_stock_analysis.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GPT_분석")

# 환경 변수 확인 또는 설정 (필요한 경우)
if "OPENAI_API_KEY" not in os.environ:
    try:
        from config import OPENAI_API_KEY
        os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
    except (ImportError, AttributeError):
        logger.error("OpenAI API 키가 환경 변수나 config.py에 설정되어 있지 않습니다.")
        sys.exit(1)

def main():
    logger.info("저평가 주식 및 스윙 트레이딩 종목 분석 시작")
    
    # 데이터 가져오기 (예시: KOSPI 상위 종목들)
    stock_data = StockData()
    
    # 분석할 종목 리스트 (예시)
    kr_symbols = ['005930', '000660', '035420', '005380', '051910', 
                 '035720', '000270', '105560', '006400', '068270']
    
    us_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 
                 'TSLA', 'NVDA', 'JPM', 'V', 'WMT']
    
    try:
        # 한국 주식 데이터 가져오기
        logger.info("한국 주식 데이터 로드 중...")
        kr_df_dict = {}
        for symbol in kr_symbols:
            try:
                df = stock_data.get_stock_history(symbol, market="KR", days=180)
                if not df.empty:
                    # 기술적 지표 추가
                    df = add_technical_indicators(df)
                    kr_df_dict[symbol] = df
                    logger.info(f"{symbol} 데이터 및 기술적 지표 로드 완료")
            except Exception as e:
                logger.error(f"{symbol} 데이터 로드 실패: {e}")
        
        # 미국 주식 데이터 가져오기 (선택적)
        logger.info("미국 주식 데이터 로드 중...")
        us_df_dict = {}
        for symbol in us_symbols:
            try:
                df = stock_data.get_stock_history(symbol, market="US", days=180)
                if not df.empty:
                    # 기술적 지표 추가
                    df = add_technical_indicators(df)
                    us_df_dict[symbol] = df
                    logger.info(f"{symbol} 데이터 및 기술적 지표 로드 완료")
            except Exception as e:
                logger.error(f"{symbol} 데이터 로드 실패: {e}")
        
        # ChatGPT 분석기 초기화
        logger.info("ChatGPT 분석기 초기화 중...")
        gpt_analyzer = ChatGPTAnalyzer()
        
        # GPT 트레이딩 전략 초기화
        trading_strategy = GPTTradingStrategy(gpt_analyzer)
        
        # 저평가 주식 식별
        logger.info("저평가 주식 분석 시작...")
        kr_undervalued = trading_strategy.identify_undervalued_stocks(kr_df_dict, market="KR", top_n=5)
        us_undervalued = trading_strategy.identify_undervalued_stocks(us_df_dict, market="US", top_n=5)
        
        # 스윙 트레이딩 적합 종목 식별
        logger.info("스윙 트레이딩 종목 분석 시작...")
        kr_swing = trading_strategy.identify_swing_trading_candidates(kr_df_dict, market="KR", top_n=5)
        us_swing = trading_strategy.identify_swing_trading_candidates(us_df_dict, market="US", top_n=5)
        
        # 결과 정리 및 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = {
            "analysis_date": timestamp,
            "kr_undervalued_stocks": [{"symbol": s[0], "score": float(s[1]), "explanation": s[2]} for s in kr_undervalued],
            "us_undervalued_stocks": [{"symbol": s[0], "score": float(s[1]), "explanation": s[2]} for s in us_undervalued],
            "kr_swing_candidates": [{"symbol": s[0], "score": float(s[1]), "explanation": s[2]} for s in kr_swing],
            "us_swing_candidates": [{"symbol": s[0], "score": float(s[1]), "explanation": s[2]} for s in us_swing]
        }
        
        # 결과 출력
        print("\n======= 분석 결과 =======")
        
        print("\n[한국 저평가 주식 TOP 5]")
        for stock in kr_undervalued:
            print(f"{stock[0]}: 점수 {stock[1]:.1f} - {stock[2]}")
            
        print("\n[미국 저평가 주식 TOP 5]")
        for stock in us_undervalued:
            print(f"{stock[0]}: 점수 {stock[1]:.1f} - {stock[2]}")
            
        print("\n[한국 스윙 트레이딩 적합 종목 TOP 5]")
        for stock in kr_swing:
            print(f"{stock[0]}: 점수 {stock[1]:.1f} - {stock[2]}")
            
        print("\n[미국 스윙 트레이딩 적합 종목 TOP 5]")
        for stock in us_swing:
            print(f"{stock[0]}: 점수 {stock[1]:.1f} - {stock[2]}")
        
        # 결과 JSON 파일로 저장
        cache_dir = "cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        output_file = os.path.join(cache_dir, f"stock_analysis_{timestamp}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        logger.info(f"분석 결과가 {output_file}에 저장되었습니다.")
        
    except Exception as e:
        logger.error(f"분석 과정에서 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()