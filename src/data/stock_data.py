"""
주식 데이터 수집 모듈
"""
import pandas as pd
import yfinance as yf
from pykrx import stock
import pytz
from ..analysis.technical import calculate_indicators
from ..utils.time_utils import (
    get_current_time, get_current_time_str, KST,
    get_date_days_ago, format_timestamp
)
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
            # time_utils 함수 사용
            end_date = get_current_time(timezone=KST)  # tz 대신 timezone 사용
            start_date = get_date_days_ago(days, timezone=KST)  # tz 대신 timezone 사용
            
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
    
    def get_us_stock_data(self, symbol, days=90):
        """
        미국 주식 데이터 수집
        
        Args:
            symbol: 주식 티커 (예: 'AAPL')
            days: 데이터를 가져올 기간 (일)
            
        Returns:
            DataFrame: 주가 데이터
        """
        try:
            # time_utils 함수 사용 - 매개변수명 수정
            end_date = get_current_time()  # 기본 UTC 시간
            start_date = get_date_days_ago(days, timezone=KST)  # timezone 매개변수명 사용
            
            ticker = yf.Ticker(symbol)
            # 시작일과 종료일을 직접 지정하여 데이터 가져오기
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d")
            )
            
            # 기술적 지표 계산
            df = calculate_indicators(df, self.config)
            
            self.us_data[symbol] = df
            logger.info(f"미국 주식 {symbol} 데이터 수집 완료. 데이터 크기: {len(df)}, 기간: {start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}")
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
    
    def get_current_price(self, symbol, market="KR"):
        """
        현재 주식 가격 조회
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            
        Returns:
            float: 현재 주가
        """
        try:
            if market == "KR":
                # 국내 주식인 경우
                if symbol not in self.kr_data or self.kr_data[symbol].empty:
                    # 데이터가 없으면 새로 가져오기
                    df = self.get_korean_stock_data(symbol, days=5)  # 최근 5일 데이터만 가져오기
                else:
                    df = self.kr_data[symbol]
                
                # 마지막 가격 반환
                if not df.empty:
                    return df['Close'].iloc[-1]
            else:
                # 미국 주식인 경우
                if symbol not in self.us_data or self.us_data[symbol].empty:
                    # 데이터가 없으면 새로 가져오기
                    df = self.get_us_stock_data(symbol, days=5)  # 최근 5일 데이터만 가져오기
                else:
                    df = self.us_data[symbol]
                
                # 마지막 가격 반환
                if not df.empty:
                    return df['Close'].iloc[-1]
            
            # 데이터를 가져올 수 없는 경우 실시간 API 직접 호출 시도
            logger.warning(f"{symbol} 현재가 조회를 위한 API 직접 호출 시도")
            
            if market == "KR" and hasattr(self.config, 'BROKER_TYPE') and self.config.BROKER_TYPE == "KIS":
                # KIS API를 통한 현재가 조회 시도 (설정되어 있는 경우)
                from ..trading.kis_api import KISAPI
                try:
                    kis_api = KISAPI(self.config)
                    if kis_api.connect():
                        current_price = kis_api.get_current_price(symbol)
                        logger.info(f"KIS API로 {symbol} 현재가 조회 성공: {current_price}")
                        return current_price
                except Exception as api_error:
                    logger.error(f"KIS API 현재가 조회 실패: {api_error}")
            
            # 실시간 API 조회 실패 시 기본값 반환
            logger.error(f"{symbol} 현재가 조회 실패")
            return 0
            
        except Exception as e:
            logger.error(f"{symbol} 현재가 조회 중 오류 발생: {e}")
            return 0
    
    def get_historical_data(self, symbol, market="KR", days=90):
        """
        과거 주식 데이터 조회
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            days: 데이터를 가져올 기간 (일)
            
        Returns:
            DataFrame: 주가 데이터
        """
        if market == "KR":
            return self.get_korean_stock_data(symbol, days)
        else:
            return self.get_us_stock_data(symbol, days)