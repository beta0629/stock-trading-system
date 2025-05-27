"""
주식 데이터 수집 모듈
"""
import datetime
import pandas as pd
import yfinance as yf
from pykrx import stock
import pytz
from ..analysis.technical import calculate_indicators
import logging
import sys

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('StockData')

class StockData:
    """주식 데이터 수집 및 관리 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        self.kr_data = {}  # 국내 주식 데이터를 저장할 딕셔너리
        self.us_data = {}  # 미국 주식 데이터를 저장할 딕셔너리
        logger.info("StockData 클래스 초기화 완료")
    
    def get_korean_stock_data(self, symbol, days=90):
        """
        국내 주식 데이터 수집
        
        Args:
            symbol: 주식 코드 (예: '005930')
            days: 데이터를 가져올 기간 (일)
            
        Returns:
            DataFrame: 주가 데이터
        """
        try:
            end_date = datetime.datetime.now(self.config.KST)
            start_date = end_date - datetime.timedelta(days=days)
            
            # pykrx 라이브러리로 한국 주식 데이터 가져오기
            df = stock.get_market_ohlcv_by_date(
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d"),
                symbol
            )
            
            # 수정: pykrx 라이브러리 업데이트로 인한 데이터 형식 변경에 대응
            # 실제 컬럼 확인 후 필요한 컬럼만 선택
            required_columns = ['시가', '고가', '저가', '종가', '거래량']
            available_columns = [col for col in required_columns if col in df.columns]
            
            if len(available_columns) == 5:
                # 기존 방식대로 처리
                df = df[available_columns]
                df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            else:
                # 컬럼 구조가 변경된 경우 대응
                logger.info(f"국내 주식 데이터 컬럼 구조 변경 감지: {df.columns}")
                # 가능한 모든 컬럼 이름 경우의 수 처리
                if '종가' in df.columns:
                    close_col = '종가'
                elif '현재가' in df.columns:
                    close_col = '현재가'
                else:
                    close_col = df.columns[3]  # 일반적으로 4번째 컬럼
                
                if '거래량' in df.columns:
                    vol_col = '거래량'
                else:
                    vol_col = df.columns[-1]  # 보통 마지막 컬럼
                
                # 필수 컬럼만 추출하여 새로운 DataFrame 생성
                new_df = pd.DataFrame()
                new_df['Open'] = df.iloc[:, 0]  # 시가
                new_df['High'] = df.iloc[:, 1]  # 고가
                new_df['Low'] = df.iloc[:, 2]   # 저가
                new_df['Close'] = df[close_col]
                new_df['Volume'] = df[vol_col]
                df = new_df
            
            # 기술적 지표 계산
            df = calculate_indicators(df, self.config)
            
            self.kr_data[symbol] = df
            logger.info(f"국내 주식 {symbol} 데이터 수집 완료. 데이터 크기: {len(df)}")
            return df
            
        except Exception as e:
            logger.error(f"국내 주식 {symbol} 데이터 수집 실패: {e}")
            return pd.DataFrame()
    
    def get_us_stock_data(self, symbol, period="3mo"):
        """
        미국 주식 데이터 수집
        
        Args:
            symbol: 주식 티커 (예: 'AAPL')
            period: 데이터를 가져올 기간 ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            
        Returns:
            DataFrame: 주가 데이터
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            
            # 기술적 지표 계산
            df = calculate_indicators(df, self.config)
            
            self.us_data[symbol] = df
            logger.info(f"미국 주식 {symbol} 데이터 수집 완료. 데이터 크기: {len(df)}")
            return df
            
        except Exception as e:
            logger.error(f"미국 주식 {symbol} 데이터 수집 실패: {e}")
            return pd.DataFrame()
    
    def update_all_data(self):
        """모든 주식 데이터 업데이트"""
        logger.info("모든 주식 데이터 업데이트 시작")
        
        # 한국 주식 데이터 업데이트
        for symbol in self.config.KR_STOCKS:
            self.get_korean_stock_data(symbol)
        
        # 미국 주식 데이터 업데이트
        for symbol in self.config.US_STOCKS:
            self.get_us_stock_data(symbol)
            
        logger.info("모든 주식 데이터 업데이트 완료")
        
    def get_latest_data(self, symbol, market="KR"):
        """
        최신 주식 데이터 조회
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            
        Returns:
            Series: 최신 주가 데이터
        """
        if market == "KR":
            if symbol in self.kr_data and not self.kr_data[symbol].empty:
                return self.kr_data[symbol].iloc[-1]
        else:
            if symbol in self.us_data and not self.us_data[symbol].empty:
                return self.us_data[symbol].iloc[-1]
        
        return None