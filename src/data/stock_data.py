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
from ..database.db_manager import DatabaseManager
import datetime
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
        
        # 데이터베이스 매니저 초기화
        self.db_manager = DatabaseManager.get_instance(config)
        
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
    
    def get_stock_data(self, symbol, days=90):
        """
        종목 코드에 따라 한국/미국 주식 데이터 수집
        
        Args:
            symbol: 종목 코드/티커 (예: '005930', 'AAPL')
            days: 데이터를 가져올 기간 (일)
            
        Returns:
            DataFrame: 주가 데이터
        """
        try:
            # 종목 코드 형태로 국내/해외 구분
            if len(symbol) == 6 and symbol.isdigit():
                # 국내 종목 (6자리 숫자)
                logger.info(f"{symbol}: 한국 주식으로 인식")
                return self.get_korean_stock_data(symbol, days)
            elif symbol.isalpha() or (len(symbol) <= 5 and any(c.isalpha() for c in symbol)):
                # 영문자만 있거나 5자 이하의 영숫자 혼합 코드는 미국 주식으로 간주
                # 예: AAPL, NVDA, AMD, TSLA, MS, F 등
                logger.info(f"{symbol}: 미국 주식으로 인식")
                return self.get_us_stock_data(symbol, days)
            else:
                # 판별이 어려운 종목은 기본적으로 한국 주식으로 시도 후 실패 시 미국 주식 시도
                logger.info(f"{symbol}: 형식 판별 불가, 한국 주식으로 먼저 시도")
                try:
                    df = self.get_korean_stock_data(symbol, days)
                    if df is not None and not df.empty:
                        return df
                    
                    # 한국 주식으로 가져오기 실패했으면 미국 주식으로 시도
                    logger.info(f"{symbol}: 한국 주식 데이터 수집 실패, 미국 주식으로 재시도")
                    return self.get_us_stock_data(symbol, days)
                except Exception as e:
                    logger.error(f"{symbol} 한국 주식 처리 중 오류, 미국 주식으로 재시도: {e}")
                    return self.get_us_stock_data(symbol, days)
                
        except Exception as e:
            logger.error(f"주식 데이터 수집 중 오류 발생 ({symbol}): {e}")
            return pd.DataFrame()
    
    def update_all_data(self):
        """모든 주식 데이터 업데이트 및 DB에 저장"""
        logger.info("모든 주식 데이터 업데이트 시작")
        
        # 한국 주식 데이터 업데이트
        for symbol in self.config.KR_STOCKS:
            df = self.get_korean_stock_data(symbol)
            if df is not None and not df.empty:
                self._save_data_to_db(symbol, "KR", df)
        
        # 미국 주식 데이터 업데이트
        for symbol in self.config.US_STOCKS:
            df = self.get_us_stock_data(symbol)
            if df is not None and not df.empty:
                self._save_data_to_db(symbol, "US", df)
            
        logger.info("모든 주식 데이터 업데이트 및 DB 저장 완료")
    
    def get_historical_data(self, symbol, market="KR", days=90, period=None, interval=None):
        """
        기존 주식 데이터 반환 또는 신규 수집
        데이터베이스에서 먼저 검색하고, 없으면 API에서 가져와 DB에 저장
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            days: 데이터를 가져올 기간 (일)
            period: 기간 문자열 (예: "1mo", "3mo", "6mo", "1y") - days 대신 사용 가능
            interval: 데이터 간격 (예: "1d", "5m", "1h") - 일부 API에서만 지원
            
        Returns:
            DataFrame: 주가 데이터
        """
        try:
            # 심볼에 따라 시장 자동 판별 - 잘못된 market 파라미터가 전달된 경우 수정
            correct_market = self._detect_market_from_symbol(symbol)
            
            # market 파라미터가 심볼에 맞지 않으면 수정하고 로그 출력
            if market != correct_market:
                logger.warning(f"심볼 {symbol}에 잘못된 시장 '{market}' 지정됨. 자동으로 '{correct_market}'으로 수정합니다.")
                market = correct_market
            
            # period 문자열이 제공된 경우 days로 변환
            if period:
                if period == "1mo":
                    days = 30
                elif period == "3mo":
                    days = 90
                elif period == "6mo":
                    days = 180
                elif period == "1y":
                    days = 365
                else:
                    logger.warning(f"인식할 수 없는 period 값: {period}, 기본값 90일 사용")
            
            # interval 로깅 (실제로 사용되지 않더라도 기록)
            if interval:
                logger.debug(f"{symbol}({market}) 데이터 요청 간격: {interval}")
            
            # 1. 메모리에 이미 데이터가 있는지 확인
            data_dict = self.kr_data if market == "KR" else self.us_data
            
            if symbol in data_dict and not data_dict[symbol].empty:
                logger.info(f"{symbol}({market}) 메모리에서 데이터 반환. 데이터 크기: {len(data_dict[symbol])}")
                return data_dict[symbol]
            
            # 2. 데이터베이스에서 데이터 조회
            end_date = get_current_time(timezone=KST if market == "KR" else None)
            start_date = get_date_days_ago(days, timezone=KST if market == "KR" else None)
            
            cache_df = self.db_manager.get_cached_price_data(
                symbol, 
                market, 
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            
            # 데이터베이스에서 가져온 데이터가 있고 충분하면 사용
            if cache_df is not None and len(cache_df) > days * 0.7:  # 요청 기간의 70% 이상 데이터가 있으면 사용
                logger.info(f"{symbol}({market}) DB에서 데이터 반환. 데이터 크기: {len(cache_df)}")
                
                # 데이터 형식 변환
                df = pd.DataFrame()
                df['Open'] = cache_df['open_price']
                df['High'] = cache_df['high_price']
                df['Low'] = cache_df['low_price']
                df['Close'] = cache_df['close_price']
                df['Volume'] = cache_df['volume']
                df.index = pd.to_datetime(cache_df['date'])
                
                # 기술적 지표 계산
                df = calculate_indicators(df, self.config)
                
                # 메모리에 저장
                if market == "KR":
                    self.kr_data[symbol] = df
                else:
                    self.us_data[symbol] = df
                    
                return df
            
            # 3. API를 통해 데이터 가져오기
            logger.info(f"{symbol}({market}) API를 통해 데이터 가져오기 시작")
            if market == "KR":
                df = self.get_korean_stock_data(symbol, days)
            else:
                df = self.get_us_stock_data(symbol, days)
            
            # 4. 가져온 데이터를 DB에 저장
            if df is not None and not df.empty:
                self._save_data_to_db(symbol, market, df)
                
            return df
                
        except Exception as e:
            logger.error(f"{symbol}({market}) 기록 데이터 조회 중 오류 발생: {e}")
            return None
    
    def _save_data_to_db(self, symbol, market, df):
        """
        데이터프레임을 DB에 저장
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            df: 저장할 데이터프레임
        """
        try:
            for date, row in df.iterrows():
                date_str = date.strftime('%Y-%m-%d')
                self.db_manager.cache_price_data(
                    symbol=symbol,
                    market=market,
                    date=date_str,
                    open_price=float(row['Open']),
                    high_price=float(row['High']),
                    low_price=float(row['Low']),
                    close_price=float(row['Close']),
                    volume=int(row['Volume'])
                )
            logger.info(f"{symbol}({market}) 데이터 {len(df)}개 DB 저장 완료")
        except Exception as e:
            logger.error(f"{symbol}({market}) 데이터 DB 저장 중 오류 발생: {e}")
    
    def get_latest_data(self, symbol, market="KR"):
        """
        최신 주식 데이터 조회
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            
        Returns:
            Series: 최신 주가 데이터
        """
        # 심볼에 따라 시장 자동 판별
        correct_market = self._detect_market_from_symbol(symbol)
        
        # market 파라미터가 심볼에 맞지 않으면 수정
        if market != correct_market:
            logger.warning(f"심볼 {symbol}에 잘못된 시장 '{market}' 지정됨. 자동으로 '{correct_market}'으로 수정합니다.")
            market = correct_market
            
        if market == "KR":
            if symbol in self.kr_data and not self.kr_data[symbol].empty:
                return self.kr_data[symbol].iloc[-1]
        else:
            if symbol in self.us_data and not self.us_data[symbol].empty:
                return self.us_data[symbol].iloc[-1]
        
        # 데이터가 없는 경우 데이터 로드 시도
        try:
            df = self.get_historical_data(symbol, market, days=30)
            if df is not None and not df.empty:
                return df.iloc[-1]
        except Exception as e:
            logger.error(f"{symbol}({market}) 최신 데이터 로드 실패: {e}")
            
        return None
    
    def get_current_price(self, symbol, market="KR"):
        """
        현재 주식 가격 조회
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            
        Returns:
            float: 현재 주가 (종가)
        """
        try:
            # 심볼에 따라 시장 자동 판별
            correct_market = self._detect_market_from_symbol(symbol)
            
            # market 파라미터가 심볼에 맞지 않으면 수정
            if market != correct_market:
                logger.warning(f"심볼 {symbol}에 잘못된 시장 '{market}' 지정됨. 자동으로 '{correct_market}'으로 수정합니다.")
                market = correct_market
                
            latest_data = self.get_latest_data(symbol, market)
            if latest_data is not None and 'Close' in latest_data:
                return latest_data['Close']
            
            # 데이터가 없는 경우 필요에 따라 데이터 가져오기
            if market == "KR":
                df = self.get_korean_stock_data(symbol)
                if not df.empty:
                    return df['Close'].iloc[-1]
            else:
                df = self.get_us_stock_data(symbol)
                if not df.empty:
                    return df['Close'].iloc[-1]
            
            logger.warning(f"{market} 시장의 {symbol} 종목의 현재 가격을 가져올 수 없습니다.")
            return 0
            
        except Exception as e:
            logger.error(f"현재 주가 조회 중 오류 발생: {e}")
            return 0
            
    def get_stock_info(self, symbol, market="KR"):
        """
        종목 기본 정보 조회 (신규 추가)
        
        Args:
            symbol: 주식 코드/티커
            market: 시장 구분 ('KR' 또는 'US')
            
        Returns:
            dict: 종목 정보
        """
        try:
            # 기본 정보 구성
            info = {'symbol': symbol, 'market': market}
            
            # 종목명 조회 시도
            name = symbol  # 기본값으로 심볼 사용
            
            # 한국 주식인 경우 pykrx 라이브러리 활용
            if market == "KR":
                try:
                    # 현재 날짜 기준으로 시장 정보 가져오기
                    today = get_current_time(timezone=KST).strftime("%Y%m%d")
                    stock_info = stock.get_market_ticker_name(symbol)
                    if stock_info:
                        name = stock_info
                except:
                    # pykrx에서 정보를 가져오지 못하면 DB에서 조회
                    if self.db_manager:
                        db_info = self.db_manager.get_stock_info(symbol, market)
                        if db_info and 'name' in db_info:
                            name = db_info['name']
            
            # 미국 주식인 경우 yfinance 활용
            else:
                try:
                    ticker = yf.Ticker(symbol)
                    ticker_info = ticker.info
                    if ticker_info and 'shortName' in ticker_info:
                        name = ticker_info['shortName']
                        
                        # 추가 정보
                        if 'sector' in ticker_info:
                            info['sector'] = ticker_info['sector']
                        if 'industry' in ticker_info:
                            info['industry'] = ticker_info['industry']
                        if 'website' in ticker_info:
                            info['website'] = ticker_info['website']
                except:
                    # yfinance에서 정보를 가져오지 못하면 DB에서 조회
                    if self.db_manager:
                        db_info = self.db_manager.get_stock_info(symbol, market)
                        if db_info and 'name' in db_info:
                            name = db_info['name']
            
            # 종목명 설정
            info['name'] = name
            
            return info
            
        except Exception as e:
            logger.error(f"종목 정보 조회 중 오류 발생: {e}")
            return {'symbol': symbol, 'name': symbol, 'market': market}
    
    def _detect_market_from_symbol(self, symbol):
        """
        심볼에 따라 시장을 자동으로 판별
        
        Args:
            symbol: 주식 코드/티커
            
        Returns:
            str: 시장 구분 ('KR' 또는 'US')
        """
        try:
            if len(symbol) == 6 and symbol.isdigit():
                return "KR"  # 6자리 숫자는 한국 주식으로 간주
            elif symbol.isalpha() or (len(symbol) <= 5 and any(c.isalpha() for c in symbol)):
                return "US"  # 영문자만 있거나 5자 이하의 영숫자 혼합 코드는 미국 주식으로 간주
            else:
                return "KR"  # 기본값은 한국 주식으로 설정
        except Exception as e:
            logger.error(f"심볼 {symbol}에 대한 시장 판별 중 오류 발생: {e}")
            return "KR"  # 오류 발생 시 기본값으로 한국 주식 설정