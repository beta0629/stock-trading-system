#!/usr/bin/env python3
"""
GPT를 사용한 주식 분석 결과를 카카오톡으로 전송하는 테스트 스크립트
"""
import sys
import logging
import time
import os
from src.notification.kakao_sender import KakaoSender
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
from src.data.stock_data import StockData
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gpt_stock_analysis.log')
    ]
)
logger = logging.getLogger('GPTStockAnalysis')

class GPTStockAnalysisTester:
    """
    GPT 주식 분석 테스트 클래스
    """
    
    def __init__(self):
        """초기화 함수"""
        self.config = config
        
        # 카카오톡 메시지 전송 초기화
        self.kakao_sender = KakaoSender(config)
        
        # ChatGPT 분석기 초기화
        self.chatgpt_analyzer = ChatGPTAnalyzer(config)
        
        # 주식 데이터 객체 초기화
        self.stock_data = StockData(config)
        
        logger.info("GPT 주식 분석 테스트 시스템 초기화 완료")
    
    def run_analysis_for_stock(self, symbol, market="KR"):
        """
        지정된 종목에 대한 분석 실행 및 결과 전송
        
        Args:
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
        
        Returns:
            bool: 분석 성공 여부
        """
        try:
            # 추가 정보 설정
            additional_info = {
                "market": market,
                "analysis_date": time.strftime("%Y-%m-%d")
            }
            
            # 종목명 가져오기
            stock_name = self.get_stock_name(symbol, market)
            
            # 종목 데이터 가져오기
            logger.info(f"{symbol}({stock_name}) 데이터 가져오기")
            df = self.stock_data.get_korean_stock_data(symbol) if market == "KR" else self.stock_data.get_us_stock_data(symbol)
            
            if df is None or df.empty:
                logger.error(f"{symbol}({stock_name}) 데이터를 가져올 수 없습니다")
                return False
                
            logger.info(f"{symbol}({stock_name}) 데이터 가져오기 성공, 행 수: {len(df)}")
            
            # 종합 분석
            logger.info(f"{symbol}({stock_name}) GPT 종합 분석 시작")
            general_analysis = self.chatgpt_analyzer.analyze_stock(df, symbol, "general", additional_info)
            
            # 추세 분석
            logger.info(f"{symbol}({stock_name}) GPT 추세 분석 시작")
            trend_analysis = self.chatgpt_analyzer.analyze_stock(df, symbol, "trend", additional_info)
            
            # 투자 제안
            logger.info(f"{symbol}({stock_name}) GPT 투자 제안 시작")
            recommendation = self.chatgpt_analyzer.analyze_stock(df, symbol, "recommendation", additional_info)
            
            # 분석 정보 생성
            analysis_summary = f"📊 {stock_name}({symbol}) 주식 분석\n\n"
            analysis_summary += "===== 종합 분석 =====\n"
            analysis_summary += f"{general_analysis.get('analysis', '분석 결과가 없습니다.')}\n\n"
            analysis_summary += "===== 추세 분석 =====\n"
            analysis_summary += f"{trend_analysis.get('analysis', '분석 결과가 없습니다.')}\n\n"
            analysis_summary += "===== 투자 제안 =====\n"
            analysis_summary += f"{recommendation.get('analysis', '분석 결과가 없습니다.')}\n\n"
            analysis_summary += "이 분석은 AI에 의해 자동 생성되었으며, 투자 결정의 참고 자료로만 활용하시기 바랍니다."
            
            # 카카오톡으로 전송
            logger.info(f"{symbol}({stock_name}) 분석 결과를 카카오톡으로 전송")
            self.kakao_sender.send_system_status(analysis_summary)
            
            logger.info(f"{symbol}({stock_name}) 분석 및 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"{symbol} 분석 중 오류 발생: {e}")
            return False
    
    def get_stock_name(self, symbol, market="KR"):
        """
        종목 코드에 해당하는 종목명 가져오기
        
        Args:
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            str: 종목명, 찾지 못할 경우 종목 코드 반환
        """
        # KR_STOCK_INFO가 있으면 해당 목록에서 찾기
        if hasattr(self.config, 'KR_STOCK_INFO') and market == "KR":
            for stock in self.config.KR_STOCK_INFO:
                if stock["code"] == symbol:
                    return stock["name"]
        
        # US_STOCK_INFO가 있으면 해당 목록에서 찾기
        if hasattr(self.config, 'US_STOCK_INFO') and market == "US":
            for stock in self.config.US_STOCK_INFO:
                if stock["code"] == symbol:
                    return stock["name"]
        
        # 기본 종목 목록에서 주석 정보로 찾기
        stocks = self.config.KR_STOCKS if market == "KR" else self.config.US_STOCKS
        for i, code in enumerate(stocks):
            if code == symbol:
                # 하드코딩된 주석 정보 반환 시도 (최선의 추측)
                if market == "KR" and len(self.config.KR_STOCKS) > i:
                    return {
                        "005930": "삼성전자",
                        "000660": "SK하이닉스",
                        "035420": "NAVER",
                        "051910": "LG화학",
                        "035720": "카카오"
                    }.get(symbol, symbol)
                elif market == "US" and len(self.config.US_STOCKS) > i:
                    return {
                        "AAPL": "애플",
                        "MSFT": "마이크로소프트",
                        "GOOGL": "알파벳",
                        "AMZN": "아마존",
                        "TSLA": "테슬라"
                    }.get(symbol, symbol)
        
        # 찾지 못한 경우 코드 그대로 반환
        return symbol
    
    def run_daily_market_analysis(self, market="KR"):
        """
        일일 시장 분석 리포트 생성 및 전송
        
        Args:
            market: 시장 구분 ("KR" 또는 "US")
        
        Returns:
            bool: 분석 성공 여부
        """
        try:
            stocks = self.config.KR_STOCKS if market == "KR" else self.config.US_STOCKS
            stock_data_dict = {}
            
            # 각 종목의 데이터 수집
            for symbol in stocks:
                try:
                    df = self.stock_data.get_korean_stock_data(symbol) if market == "KR" else self.stock_data.get_us_stock_data(symbol)
                    if df is not None and not df.empty:
                        stock_data_dict[symbol] = df
                except Exception as e:
                    logger.warning(f"{symbol} 데이터 수집 중 오류: {e}")
            
            if not stock_data_dict:
                logger.error(f"{market} 시장 분석을 위한 데이터를 수집할 수 없습니다")
                return False
            
            # 일일 시장 리포트 생성
            logger.info(f"{market} 시장 일일 리포트 생성 시작")
            daily_report = self.chatgpt_analyzer.generate_daily_report(stock_data_dict, market)
            
            # 리포트 형식화
            market_name = "한국" if market == "KR" else "미국"
            current_date = time.strftime("%Y년 %m월 %d일")
            
            message = f"📈 {current_date} {market_name} 시장 일일 리포트\n\n"
            message += daily_report
            message += "\n\n이 리포트는 AI에 의해 자동 생성되었으며, 투자 결정의 참고 자료로만 활용하시기 바랍니다."
            
            # 카카오톡으로 전송
            logger.info(f"{market} 시장 일일 리포트를 카카오톡으로 전송")
            
            # 메시지가 길 경우 분할 전송
            if len(message) > 3000:  # 카카오톡 메시지 길이 제한
                chunks = [message[i:i+3000] for i in range(0, len(message), 3000)]
                for i, chunk in enumerate(chunks):
                    chunk_message = f"[{i+1}/{len(chunks)}] " + chunk
                    self.kakao_sender.send_system_status(chunk_message)
                    time.sleep(1)  # API 제한 방지
            else:
                self.kakao_sender.send_system_status(message)
            
            logger.info(f"{market} 시장 일일 리포트 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"{market} 시장 일일 리포트 생성 중 오류 발생: {e}")
            return False

def main():
    """메인 함수"""
    logger.info("GPT 주식 분석 테스트 시작")
    
    tester = GPTStockAnalysisTester()
    
    # 명령행 인자가 있는 경우 해당 종목 분석
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
        market = sys.argv[2] if len(sys.argv) > 2 else "KR"
        tester.run_analysis_for_stock(symbol, market)
    else:
        # 기본 종목 분석
        tester.run_analysis_for_stock("005930", "KR")  # 삼성전자 분석
        # 시장 분석
        tester.run_daily_market_analysis("KR")
    
    logger.info("GPT 주식 분석 테스트 완료")

if __name__ == "__main__":
    main()