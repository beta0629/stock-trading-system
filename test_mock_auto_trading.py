#!/usr/bin/env python3
"""
24시간 모의 자동매매 시스템
한국과 미국 시장 시간에 맞춰 자동으로 운영되는 모의 투자 시스템입니다.
"""
import logging
import sys
import time
import random
import datetime
import os  # os 모듈 추가
import pandas as pd
import numpy as np
import pytz
import schedule
from src.notification.kakao_sender import KakaoSender
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mock_auto_trading.log')
    ]
)
logger = logging.getLogger('MockAutoTrading')

class MockStockData:
    """모의 주식 데이터 생성 클래스"""
    
    def __init__(self):
        """초기화 함수"""
        self.stock_info = {
            # 한국 주식
            "005930": {"name": "삼성전자", "price": 71000, "volatility": 0.02},
            "000660": {"name": "SK하이닉스", "price": 167000, "volatility": 0.025},
            "035420": {"name": "NAVER", "price": 193000, "volatility": 0.03},
            "051910": {"name": "LG화학", "price": 453000, "volatility": 0.035},
            "035720": {"name": "카카오", "price": 51500, "volatility": 0.04},
            "207940": {"name": "삼성바이오로직스", "price": 820000, "volatility": 0.03},
            "006400": {"name": "삼성SDI", "price": 580000, "volatility": 0.035},
            "373220": {"name": "LG에너지솔루션", "price": 400000, "volatility": 0.04},
            "323410": {"name": "카카오뱅크", "price": 26000, "volatility": 0.045},
            "259960": {"name": "크래프톤", "price": 234000, "volatility": 0.05},
            
            # 미국 주식
            "AAPL": {"name": "애플", "price": 174.5, "volatility": 0.02},
            "MSFT": {"name": "마이크로소프트", "price": 337.8, "volatility": 0.022},
            "GOOGL": {"name": "알파벳", "price": 131.2, "volatility": 0.025},
            "AMZN": {"name": "아마존", "price": 129.8, "volatility": 0.03},
            "TSLA": {"name": "테슬라", "price": 193.2, "volatility": 0.05},
            "NVDA": {"name": "엔비디아", "price": 405.7, "volatility": 0.045},
            "META": {"name": "메타", "price": 294.5, "volatility": 0.035},
            "BRK.B": {"name": "버크셔 해서웨이", "price": 346.8, "volatility": 0.015},
            "JPM": {"name": "JP모건", "price": 142.6, "volatility": 0.02},
            "V": {"name": "비자", "price": 236.9, "volatility": 0.018},
        }
        logger.info("모의 주식 데이터 클래스 초기화 완료")
    
    def get_current_price(self, symbol):
        """
        현재 주가 가져오기 (랜덤 변동)
        
        Args:
            symbol: 종목 코드
            
        Returns:
            현재 주가
        """
        if symbol not in self.stock_info:
            return None
            
        # 기준 가격에서 랜덤 변동폭 적용
        base_price = self.stock_info[symbol]["price"]
        volatility = self.stock_info[symbol]["volatility"]
        change_rate = np.random.normal(0, volatility)
        
        # 가격이 음수가 되지 않도록 처리
        current_price = max(100, int(base_price * (1 + change_rate)))
        
        # 변동된 가격을 기준 가격으로 업데이트
        self.stock_info[symbol]["price"] = current_price
        
        return current_price
    
    def get_stock_name(self, symbol):
        """
        종목 이름 가져오기
        
        Args:
            symbol: 종목 코드
            
        Returns:
            종목 이름
        """
        return self.stock_info.get(symbol, {}).get("name", symbol)
    
    def generate_mock_data(self, symbol, days=30):
        """
        모의 주식 데이터 생성 (OHLCV)
        
        Args:
            symbol: 종목 코드
            days: 생성할 일수
            
        Returns:
            DataFrame: 모의 주식 데이터
        """
        if symbol not in self.stock_info:
            return pd.DataFrame()
        
        # 기준 가격과 변동성
        base_price = self.stock_info[symbol]["price"]
        volatility = self.stock_info[symbol]["volatility"]
        
        # 날짜 생성
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days)
        dates = [start_date + datetime.timedelta(days=i) for i in range(days)]
        
        # 랜덤 워크로 가격 생성
        closes = [base_price]
        for i in range(1, days):
            change_rate = np.random.normal(0, volatility)
            new_price = max(100, closes[-1] * (1 + change_rate))
            closes.append(new_price)
        
        # OHLCV 생성
        data = []
        for i, date in enumerate(dates):
            close = closes[i]
            # 변동폭 설정
            price_range = close * volatility
            
            # 시가, 고가, 저가 생성
            open_price = close * (1 + np.random.normal(0, volatility/2))
            high_price = max(open_price, close) * (1 + abs(np.random.normal(0, volatility/2)))
            low_price = min(open_price, close) * (1 - abs(np.random.normal(0, volatility/2)))
            
            # 거래량
            volume = int(np.random.normal(1000000, 500000))
            if volume < 0:
                volume = 100000
            
            data.append({
                'Date': date,
                'Open': round(open_price, 2),
                'High': round(high_price, 2),
                'Low': round(low_price, 2),
                'Close': round(close, 2),
                'Volume': volume
            })
        
        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        return df

class MockAutoTrader:
    """모의 자동 매매 실행 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        
        # 로거 설정
        self.logger = self._setup_logger()
        
        # 모의 주식 데이터 생성기
        self.mock_stock_data = MockStockData()
        
        # 텔레그램 메시지 발송 (선택 사항)
        self.use_telegram = getattr(config, 'USE_TELEGRAM', False)
        self.telegram = None
        if self.use_telegram:
            try:
                from src.notification.telegram_sender import TelegramSender
                self.telegram = TelegramSender(config)
            except ImportError:
                logger.warning("텔레그램 모듈을 불러올 수 없습니다.")
        
        # 카카오톡 메시지 발송 (선택 사항)
        self.use_kakao = getattr(config, 'USE_KAKAO', False)
        self.kakao = None
        if self.use_kakao:
            try:
                from src.notification.kakao_sender import KakaoSender
                self.kakao = KakaoSender(config)
                logger.info("카카오톡 알림 기능 활성화")
                self.kakao_sender = self.kakao
            except ImportError:
                logger.warning("카카오톡 모듈을 불러올 수 없습니다.")
        
        # GPT 분석 사용 여부
        self.use_gpt_analysis = getattr(config, 'USE_GPT_ANALYSIS', False)
        
        # GPT 트레이딩 전략 설정
        if self.use_gpt_analysis:
            try:
                from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
                from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy
                
                # ChatGPT 분석기 초기화
                self.gpt_analyzer = ChatGPTAnalyzer(config)
                
                # GPT 트레이딩 전략 초기화
                self.gpt_strategy = GPTTradingStrategy(config, self.gpt_analyzer)
                
                logger.info("GPT 분석 및 트레이딩 전략이 활성화되었습니다.")
            except ImportError as e:
                logger.error(f"GPT 모듈을 불러올 수 없습니다: {e}")
                self.use_gpt_analysis = False
            except Exception as e:
                logger.error(f"GPT 초기화 중 오류 발생: {e}")
                self.use_gpt_analysis = False
        
        # 최근 매매 신호 저장 딕셔너리
        self.recent_signals = {}
        
        # 거래 내역
        self.trading_history = []
        
        # 보유 종목 정보 (종목코드: {수량, 평균단가, 시장})
        self.holdings = {}
        
        # 한국/미국 종목 리스트
        self.kr_symbols = getattr(config, 'KR_STOCKS', [])
        self.us_symbols = getattr(config, 'US_STOCKS', [])
        
        # 모의 자본금
        self.initial_capital = getattr(config, 'MOCK_INITIAL_CAPITAL', 10000000)  # 기본 1000만원
        self.account_balance = self.initial_capital
        
        # 실행 상태
        self.is_running = False
        
        # 손절매/익절 설정
        self.stop_loss_pct = getattr(config, 'STOP_LOSS_PCT', 5)  # 기본 손절매 비율 5%
        self.take_profit_pct = getattr(config, 'TAKE_PROFIT_PCT', 10)  # 기본 익절 비율 10%
        self.use_trailing_stop = getattr(config, 'USE_TRAILING_STOP', False)  # 트레일링 스탑 사용 여부
        self.trailing_stop_distance = getattr(config, 'TRAILING_STOP_DISTANCE', 3)  # 트레일링 스탑 거리(%)
        
        # 트레일링 스탑 기록용 딕셔너리
        self.trailing_stops = {}  # {symbol: {'highest_price': 가격, 'stop_price': 가격}}
        
        # 성과 기록
        self.performance = {
            'start_date': datetime.datetime.now(),
            'start_capital': self.initial_capital,
            'current_capital': self.account_balance,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0,
            'total_loss': 0
        }
        
        logger.info(f"모의 자동매매 시스템 초기화 완료 (시작 자본금: {self.initial_capital:,}원)")
    
    def _setup_logger(self):
        """로거 설정"""
        return logging.getLogger('MockAutoTrader')

    def generate_trading_signal(self, symbol, market="KR"):
        """
        GPT 분석 기반 매매 신호 생성
        
        Args:
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            dict: 매매 신호 데이터
        """
        # 현재가 가져오기
        current_price = self.mock_stock_data.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"{symbol}: 가격 데이터를 가져올 수 없습니다.")
            return None
        
        # 종목명 가져오기
        stock_name = self.mock_stock_data.get_stock_name(symbol)
        
        # 시장에 따라 통화 설정
        currency = "원" if market == "KR" else "달러"
        
        # 모의 주식 데이터 생성 (30일치)
        stock_df = self.mock_stock_data.generate_mock_data(symbol, days=30)
        
        if stock_df.empty:
            logger.warning(f"{symbol}: 주가 데이터를 생성할 수 없습니다.")
            return None
            
        # 기술적 지표 계산
        try:
            # RSI 계산 (14일)
            delta = stock_df['Close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss.replace(0, 0.001)  # 0으로 나누기 방지
            stock_df['RSI'] = 100 - (100 / (1 + rs))
            
            # 이동평균 계산
            stock_df['SMA_short'] = stock_df['Close'].rolling(window=5).mean()  # 5일 이동평균
            stock_df['SMA_long'] = stock_df['Close'].rolling(window=20).mean()  # 20일 이동평균
            
            # MACD 계산
            stock_df['EMA_12'] = stock_df['Close'].ewm(span=12, adjust=False).mean()
            stock_df['EMA_26'] = stock_df['Close'].ewm(span=26, adjust=False).mean()
            stock_df['MACD'] = stock_df['EMA_12'] - stock_df['EMA_26']
            stock_df['MACD_signal'] = stock_df['MACD'].ewm(span=9, adjust=False).mean()
            
        except Exception as e:
            logger.error(f"{symbol} 기술적 지표 계산 중 오류: {e}")
            # 기본 지표라도 있는 상태로 계속 진행
        
        # GPT 분석 사용 여부에 따라 신호 생성 방식 변경
        if self.use_gpt_analysis:
            try:
                # 시장 맥락 정보 (현재 시간, 시장 정보 등)
                market_context = {
                    "market": market,
                    "current_time": datetime.datetime.now().isoformat(),
                    "is_market_open": self.is_market_open(market),
                    "current_price": current_price,
                    "currency": currency
                }
                
                logger.info(f"{symbol}({stock_name}): GPT 트레이딩 전략 분석 시작")
                
                # GPT 트레이딩 전략 분석
                analysis_result = self.gpt_strategy.analyze_stock(stock_df, symbol, market_context)
                
                # 분석 결과에서 신호 추출
                signal_type = analysis_result.get("signal", "NONE")
                confidence = analysis_result.get("confidence", 0.0)
                quantity = analysis_result.get("quantity", 0)
                
                # 매매 신호 강도 결정
                if confidence >= 0.8:
                    strength = "STRONG"
                elif confidence >= 0.6:
                    strength = "MEDIUM"
                else:
                    strength = "WEAK"
                
                # 매매 이유 생성
                technical_signal = analysis_result.get("technical_signal", "NONE")
                gpt_signal = analysis_result.get("gpt_signal", "NONE")
                analysis_summary = analysis_result.get("analysis_summary", "")
                
                # 이유 요약 생성
                if len(analysis_summary) > 200:
                    analysis_summary = analysis_summary[:197] + "..."
                
                reason = f"[기술적 신호: {technical_signal}, GPT 신호: {gpt_signal}, 신뢰도: {confidence:.2f}] {analysis_summary}"
                
                logger.info(f"{symbol}({stock_name}): GPT 분석 결과 - {signal_type} 신호, 신뢰도: {confidence:.2f}")
                
                # "NONE" 또는 "HOLD" 신호는 처리하지 않음
                if signal_type in ["NONE", "HOLD", "ERROR"]:
                    logger.info(f"{symbol}({stock_name}): 매매 신호 없음 (NONE/HOLD/ERROR)")
                    return None
                
                # 매매 신호 데이터 생성
                signal = {
                    'symbol': symbol,
                    'name': stock_name,
                    'price': current_price,
                    'market': market,
                    'currency': currency,
                    'timestamp': datetime.datetime.now(),
                    'signals': [{
                        'type': signal_type,
                        'strength': strength,
                        'reason': reason,
                        'confidence': confidence,
                        'date': datetime.datetime.now().strftime('%Y-%m-%d')
                    }]
                }
                
                return signal
                
            except Exception as e:
                logger.error(f"{symbol} GPT 분석 중 오류 발생: {e}")
                # GPT 분석 실패 시 기존 방식으로 계속 진행
        
        # GPT 분석 사용하지 않거나, 오류 발생시 기존 랜덤 방식으로 생성
        # 랜덤 신호 생성 (백업 방식)
        signal_type = random.choice(["BUY", "SELL", "HOLD", "HOLD", "HOLD"])  # HOLD에 가중치 부여
        strength = random.choice(["STRONG", "MEDIUM", "WEAK"])
        
        # 랜덤 신뢰도 (0.1 ~ 0.9, 소수점 둘째자리까지)
        confidence = round(random.uniform(0.2, 0.8), 2)
        
        # 신호 강도에 따라 신뢰도 조정
        if strength == "STRONG":
            confidence = min(0.9, confidence + 0.15)
        elif strength == "WEAK":
            confidence = max(0.1, confidence - 0.15)
            
        # 랜덤 이유 생성
        reasons = {
            "BUY": [
                f"RSI(14) = {random.randint(10, 40)}로 과매도 상태",
                f"20일 이동평균선 상향 돌파 확인",
                f"MACD 골든크로스 신호",
                f"최근 {random.randint(2, 5)}일 연속 상승 추세",
                f"거래량 {random.randint(150, 300)}% 급증"
            ],
            "SELL": [
                f"RSI(14) = {random.randint(60, 90)}로 과매수 상태",
                f"20일 이동평균선 하향 돌파",
                f"MACD 데드크로스 신호",
                f"최근 {random.randint(2, 5)}일 연속 하락 추세",
                f"거래량 {random.randint(40, 80)}% 감소"
            ],
            "HOLD": [
                "뚜렷한 추세가 보이지 않음",
                "기술적 지표 혼조세",
                "추가 확인 필요",
                f"RSI(14) = {random.randint(40, 60)}로 중립 구간",
                "시장 관망 필요"
            ]
        }
        
        reason = random.choice(reasons.get(signal_type, ["추가 분석 필요"]))
        
        # "HOLD" 신호는 처리하지 않음 (신호 없음으로 취급)
        if signal_type == "HOLD":
            logger.info(f"{symbol}({stock_name}): 랜덤 분석 결과 - 매매 신호 없음 (HOLD)")
            return None
        
        # 매매 신호 데이터 생성
        signal = {
            'symbol': symbol,
            'name': stock_name,
            'price': current_price,
            'market': market,
            'currency': currency,
            'timestamp': datetime.datetime.now(),
            'signals': [{
                'type': signal_type,
                'strength': strength,
                'reason': reason,
                'confidence': confidence,
                'date': datetime.datetime.now().strftime('%Y-%m-%d')
            }]
        }
        
        logger.info(f"{symbol}({stock_name}): 랜덤 분석 결과 - {signal_type} 신호, 신뢰도: {confidence:.2f}")
        return signal
    
    def execute_trade(self, signal):
        """
        매매 신호에 따라 모의 거래 실행
        
        Args:
            signal: 매매 신호 데이터
            
        Returns:
            bool: 거래 성공 여부
        """
        if not signal or 'signals' not in signal or not signal['signals']:
            return False
        
        symbol = signal['symbol']
        price = signal['price']
        stock_name = signal['name']
        market = signal.get('market', 'KR')
        
        # 첫 번째 신호만 처리
        trade_signal = signal['signals'][0]
        signal_type = trade_signal['type']
        strength = trade_signal['strength']
        
        # 현재 보유량 확인
        current_holdings = self.holdings.get(symbol, {'quantity': 0, 'avg_price': 0, 'market': market})
        holding_quantity = current_holdings['quantity']
        
        # 매도 신호일 경우, 보유 수량이 없으면 처리하지 않음
        if signal_type == "SELL" and holding_quantity <= 0:
            logger.info(f"{symbol}({stock_name}) 매도 신호가 있으나 보유수량이 없습니다. 처리를 건너뜁니다.")
            return False
        
        # 매매 수량 결정
        trade_amount = 0
        
        if signal_type == "BUY":
            # 매수할 금액 결정 (강도에 따라)
            strength_factor = {"WEAK": 0.1, "MEDIUM": 0.2, "STRONG": 0.3}
            max_amount = min(self.account_balance, self.config.MAX_AMOUNT_PER_TRADE)
            trade_amount = max_amount * strength_factor[strength]
            
            # 최대 매수 수량 계산
            buy_quantity = int(trade_amount / price)
            
            # 매수 수량 검증 - 0 이하인 경우 처리 안함
            if buy_quantity <= 0:
                logger.info(f"{symbol}({stock_name}) 매수 신호가 있으나 계산된 수량이 0보다 작거나 같습니다. 처리를 건너뜁니다.")
                return False
                
            # 계좌 잔고 확인
            required_amount = buy_quantity * price
            if self.account_balance < required_amount:
                logger.info(f"{symbol}({stock_name}) 매수 신호가 있으나 필요금액({required_amount:,}원)이 계좌 잔고({self.account_balance:,}원)보다 많습니다.")
                
                # 가능한 최대 수량으로 조정
                adjusted_quantity = int(self.account_balance / price)
                if adjusted_quantity > 0:
                    logger.info(f"{symbol}({stock_name}) 매수 수량을 {buy_quantity}주에서 {adjusted_quantity}주로 조정합니다.")
                    buy_quantity = adjusted_quantity
                else:
                    logger.info(f"{symbol}({stock_name}) 매수 가능한 수량이 없습니다. 처리를 건너뜁니다.")
                    return False
                
            # 매수 실행
            purchase_amount = buy_quantity * price
            self.account_balance -= purchase_amount
            
            # 보유종목 업데이트
            total_quantity = holding_quantity + buy_quantity
            total_amount = (holding_quantity * current_holdings['avg_price']) + purchase_amount
            new_avg_price = total_amount / total_quantity if total_quantity > 0 else 0
            
            self.holdings[symbol] = {
                'quantity': total_quantity,
                'avg_price': new_avg_price,
                'market': market
            }
            
            # 거래 이력 추가
            self.trading_history.append({
                'timestamp': datetime.datetime.now(),
                'symbol': symbol,
                'name': stock_name,
                'market': market,
                'type': 'BUY',
                'price': price,
                'quantity': buy_quantity,
                'amount': purchase_amount
            })
            
            currency = "원" if market == "KR" else "달러"
            logger.info(f"{symbol}({stock_name}) {buy_quantity}주 매수 완료 - 단가: {price:,}{currency}, 총액: {purchase_amount:,}{currency}")
            return True
            
        elif signal_type == "SELL":
            # 이미 보유 종목이 있는지 확인은 위에서 했음
            
            # 매도할 수량 결정 (강도에 따라)
            strength_factor = {"WEAK": 0.2, "MEDIUM": 0.5, "STRONG": 0.8}
            sell_quantity = int(holding_quantity * strength_factor[strength])
            
            # 매도 수량 검증 - 최소 1주 이상
            if sell_quantity <= 0:
                # 최소 1주는 매도하도록 조정
                if holding_quantity > 0:
                    sell_quantity = 1
                    logger.info(f"{symbol}({stock_name}) 매도 수량이 0이하로 계산되어 최소 1주로 조정합니다.")
                else:
                    logger.info(f"{symbol}({stock_name}) 매도 신호가 있으나 매도 수량이 0보다 작거나 같습니다.")
                    return False
                
            # 보유량보다 많이 매도하지 않도록 조정
            if sell_quantity > holding_quantity:
                sell_quantity = holding_quantity
                logger.info(f"{symbol}({stock_name}) 매도 수량이 보유 수량보다 많아 {holding_quantity}주로 조정합니다.")
                
            # 매도 실행
            sell_amount = sell_quantity * price
            self.account_balance += sell_amount
            
            # 보유종목 업데이트
            new_quantity = holding_quantity - sell_quantity
            self.holdings[symbol]['quantity'] = new_quantity
            
            # 전량 매도시 평균단가 초기화
            if new_quantity <= 0:
                self.holdings[symbol]['avg_price'] = 0
            
            # 거래 이력 추가
            self.trading_history.append({
                'timestamp': datetime.datetime.now(),
                'symbol': symbol,
                'name': stock_name,
                'market': market,
                'type': 'SELL',
                'price': price,
                'quantity': sell_quantity,
                'amount': sell_amount
            })
            
            currency = "원" if market == "KR" else "달러"
            logger.info(f"{symbol}({stock_name}) {sell_quantity}주 매도 완료 - 단가: {price:,}{currency}, 총액: {sell_amount:,}{currency}")
            return True
            
        return False
    
    def send_trade_notification(self, signal, trade_result):
        """
        매매 실행 후 알림 전송
        
        Args:
            signal: 매매 신호 데이터
            trade_result: 매매 실행 결과 여부
            
        Returns:
            bool: 알림 전송 성공 여부
        """
        if not signal or 'signals' not in signal or not signal['signals']:
            return False
            
        try:
            symbol = signal['symbol']
            price = signal['price']
            stock_name = signal['name']
            market = signal.get('market', 'KR')
            currency = signal.get('currency', '원')
            
            # 첫 번째 신호로 거래 종류 확인
            trade_signal = signal['signals'][0]
            signal_type = trade_signal['type']
            reason = trade_signal['reason']
            strength = trade_signal['strength']
            
            # 현재 보유량 및 평균단가
            holding_info = self.holdings.get(symbol, {'quantity': 0, 'avg_price': 0, 'market': market})
            quantity = holding_info['quantity']
            avg_price = holding_info['avg_price']
            
            # 수익률 계산
            profit_percent = ((price / avg_price) - 1) * 100 if avg_price > 0 else 0
            
            # 거래 이력에서 이번 거래 정보 가져오기
            latest_trade = next((trade for trade in reversed(self.trading_history) 
                               if trade['symbol'] == symbol), None)
            
            trade_quantity = latest_trade['quantity'] if latest_trade else 0
            
            # 메시지 생성
            emoji = "🟢" if signal_type == "BUY" else "🔴"
            title = "매수 완료" if signal_type == "BUY" else "매도 완료"
            
            message = f"{emoji} {title}: {stock_name}({symbol}) - {market} 시장\n\n"
            message += f"• 거래 종류: {signal_type}\n"
            message += f"• 거래 가격: {price:,}{currency}\n"
            message += f"• 거래 수량: {trade_quantity}주\n"
            message += f"• 거래 금액: {price * trade_quantity:,}{currency}\n"
            message += f"• 현재 보유량: {quantity}주\n"
            message += f"• 평균 단가: {avg_price:,.0f}{currency}\n"
            
            if quantity > 0 and avg_price > 0:
                message += f"• 현재 수익률: {profit_percent:.2f}%\n"
            
            message += f"• 신호 강도: {strength}\n"
            message += f"• 신호 이유: {reason}\n"
            message += f"• 거래 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 계좌 정보 추가
            message += f"💰 계좌 잔고: {self.account_balance:,}원\n"
            
            # 카카오톡으로 전송
            logger.info(f"{symbol}({stock_name}) 거래 알림 전송")
            self.kakao_sender.send_system_status(message)
            return True
            
        except Exception as e:
            logger.error(f"알림 전송 중 오류 발생: {e}")
            return False
    
    def run_trading_session(self, market, iterations=5):
        """
        지정된 시장에 대해 모의 매매 세션 실행
        
        Args:
            market: 시장 구분 ("KR" 또는 "US")
            iterations: 반복 횟수
            
        Returns:
            bool: 세션 완료 여부
        """
        market_name = "한국" if market == "KR" else "미국"
        logger.info(f"{market_name} 시장 모의 매매 세션 시작 - {iterations}회 반복")
        
        symbols = self.kr_symbols if market == "KR" else self.us_symbols
        
        if not symbols:
            logger.warning(f"{market_name} 시장 종목 목록이 없습니다")
            return False
        
        try:
            # 모의 매매 반복
            for i in range(iterations):
                logger.info(f"{market_name} 시장 모의 매매 반복 {i+1}/{iterations}")
                
                # 랜덤하게 종목 선택
                symbol = random.choice(symbols)
                
                # 매매 신호 생성
                signal = self.generate_trading_signal(symbol, market)
                
                if signal:
                    # 거래 실행
                    trade_result = self.execute_trade(signal)
                    
                    # 거래가 성공한 경우 알림 전송
                    if trade_result:
                        self.send_trade_notification(signal, trade_result)
                
                # 대기
                if i < iterations - 1:  # 마지막 반복이 아닌 경우에만 대기
                    time.sleep(2)  # 2초 대기 (반복 간격)
            
            logger.info(f"{market_name} 시장 모의 매매 세션 완료")
            return True
            
        except Exception as e:
            logger.error(f"{market_name} 시장 모의 매매 세션 중 오류 발생: {e}")
            
            # 오류 알림
            error_message = f"❌ {market_name} 시장 모의 자동매매 중 오류가 발생했습니다.\n오류 내용: {str(e)}"
            self.kakao_sender.send_system_status(error_message)
            
            return False
    
    def send_trading_summary(self):
        """
        거래 요약 알림 전송
        
        Returns:
            bool: 알림 전송 성공 여부
        """
        try:
            # 한국 시간 기준
            now = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
            current_date = now.strftime("%Y년 %m월 %d일")
            current_time = now.strftime("%H:%M")
            
            summary = f"📊 {current_date} {current_time} 모의 자동매매 현황 보고\n\n"
            
            # 거래 이력 요약
            # 오늘의 거래만 필터링
            today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_trades = [t for t in self.trading_history if t['timestamp'] >= today]
            
            buy_count = len([t for t in today_trades if t['type'] == 'BUY'])
            sell_count = len([t for t in today_trades if t['type'] == 'SELL'])
            
            summary += f"• 오늘의 거래: 총 {len(today_trades)}회 (매수: {buy_count}회, 매도: {sell_count}회)\n"
            
            # 시장별 거래 횟수
            kr_trades = len([t for t in today_trades if t.get('market') == 'KR'])
            us_trades = len([t for t in today_trades if t.get('market') == 'US'])
            summary += f"  - 한국 시장: {kr_trades}회, 미국 시장: {us_trades}회\n\n"
            
            # 잔고 정보
            initial_balance = 50000000  # 초기 잔고
            balance_change = self.account_balance - initial_balance
            balance_percent = (balance_change / initial_balance) * 100
            
            summary += f"• 계좌 잔고: {self.account_balance:,}원\n"
            summary += f"• 잔고 변화: {balance_change:,}원 ({balance_percent:+.2f}%)\n\n"
            
            # 보유 종목 정보
            if any(holding['quantity'] > 0 for holding in self.holdings.values()):
                summary += "🔶 현재 보유 종목\n"
                
                # 한국 종목
                kr_holdings = {symbol: holding for symbol, holding in self.holdings.items() 
                              if holding['quantity'] > 0 and holding.get('market') == 'KR'}
                
                if kr_holdings:
                    summary += "【 한국 시장 】\n"
                    total_kr_value = 0
                    
                    for symbol, holding in kr_holdings.items():
                        quantity = holding['quantity']
                        avg_price = holding['avg_price']
                        if quantity <= 0:
                            continue
                            
                        stock_name = self.mock_stock_data.get_stock_name(symbol)
                        current_price = self.mock_stock_data.get_current_price(symbol)
                        
                        # 수익률 계산
                        profit_percent = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
                        profit_amount = (current_price - avg_price) * quantity
                        
                        # 종목별 보유금액
                        holding_value = current_price * quantity
                        total_kr_value += holding_value
                        
                        summary += f"• {stock_name}({symbol}): {quantity}주, 평균단가 {avg_price:,.0f}원\n"
                        summary += f"  현재가 {current_price:,}원, 수익률 {profit_percent:+.2f}% ({profit_amount:+,}원)\n"
                    
                    summary += f"  【 한국 시장 총 보유가치: {total_kr_value:,}원 】\n\n"
                
                # 미국 종목
                us_holdings = {symbol: holding for symbol, holding in self.holdings.items() 
                              if holding['quantity'] > 0 and holding.get('market') == 'US'}
                
                if us_holdings:
                    summary += "【 미국 시장 】\n"
                    total_us_value = 0
                    
                    for symbol, holding in us_holdings.items():
                        quantity = holding['quantity']
                        avg_price = holding['avg_price']
                        if quantity <= 0:
                            continue
                            
                        stock_name = self.mock_stock_data.get_stock_name(symbol)
                        current_price = self.mock_stock_data.get_current_price(symbol)
                        
                        # 수익률 계산
                        profit_percent = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
                        profit_amount = (current_price - avg_price) * quantity
                        
                        # 종목별 보유금액 (달러)
                        holding_value = current_price * quantity
                        total_us_value += holding_value
                        
                        summary += f"• {stock_name}({symbol}): {quantity}주, 평균단가 ${avg_price:,.2f}\n"
                        summary += f"  현재가 ${current_price:,.2f}, 수익률 {profit_percent:+.2f}% (${profit_amount:+,.2f})\n"
                    
                    # 달러 원화 환산 (가정 환율 1300원)
                    exchange_rate = 1300
                    total_us_value_krw = total_us_value * exchange_rate
                    summary += f"  【 미국 시장 총 보유가치: ${total_us_value:,.2f} (약 {total_us_value_krw:,}원) 】\n\n"
                
                # 총 보유자산
                total_assets = self.account_balance + sum(holding['quantity'] * self.mock_stock_data.get_current_price(symbol) 
                                         for symbol, holding in self.holdings.items() if holding['quantity'] > 0 and holding.get('market') == 'KR')
                
                # 미국 주식 가치 원화 환산
                exchange_rate = 1300  # 가정 환율
                us_holdings_value_krw = sum(holding['quantity'] * self.mock_stock_data.get_current_price(symbol) * exchange_rate
                                          for symbol, holding in self.holdings.items() if holding['quantity'] > 0 and holding.get('market') == 'US')
                
                total_profit = total_assets - initial_balance
                total_profit_percent = (total_profit / initial_balance) * 100
                
                summary += f"💰 총 보유 자산: {total_assets:,}원 ({total_profit_percent:+.2f}%)\n"
                
            else:
                summary += "🔶 현재 보유 종목이 없습니다.\n"
            
            # 카카오톡으로 전송
            logger.info("거래 요약 알림 전송")
            self.kakao_sender.send_system_status(summary)
            return True
            
        except Exception as e:
            logger.error(f"거래 요약 알림 전송 중 오류 발생: {e}")
            return False
    
    def is_market_open(self, market="KR"):
        """
        현재 시장이 열려있는지 확인
        
        Args:
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            bool: 시장 오픈 여부
        """
        # 강제 오픈 모드 설정 (환경 변수나 설정으로 제어 가능)
        force_open = getattr(self.config, 'FORCE_MARKET_OPEN', False)
        if force_open:
            logger.info(f"강제 시장 오픈 모드 활성화: {market} 시장")
            return True
            
        # GitHub Actions 환경에서는 강제로 시장을 열림 처리
        is_ci_env = os.environ.get('CI') == 'true'
        if is_ci_env:
            logger.info(f"CI 환경 감지: {market} 시장 열림 상태로 간주합니다.")
            return True
        
        # 한국 시간 (KST) 기준으로 계산
        now_kst = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
        current_weekday = now_kst.weekday()  # 0=월요일, 1=화요일, ..., 6=일요일
        
        # 주말 체크 (토/일)
        if current_weekday >= 5:  # 토요일(5) 또는 일요일(6)
            logger.info(f"주말({['월', '화', '수', '목', '금', '토', '일'][current_weekday]}요일)이므로 {market} 시장 닫힘")
            return False
        
        # 공휴일 체크 (간단한 구현, 실제로는 공휴일 목록을 참조해야 함)
        # TODO: 공휴일 목록을 별도로 관리하여 체크하는 로직 추가
            
        # 시장별 시간 체크
        if market == "KR":
            # 설정에서 시장 시간 가져오기
            market_open_str = getattr(self.config, 'KR_MARKET_OPEN_TIME', "09:00")
            market_close_str = getattr(self.config, 'KR_MARKET_CLOSE_TIME', "15:30")
            
            # 한국 시장 시간 (9:00 ~ 15:30)
            open_hour, open_minute = map(int, market_open_str.split(':'))
            close_hour, close_minute = map(int, market_close_str.split(':'))
            
            market_open = datetime.time(hour=open_hour, minute=open_minute)
            market_close = datetime.time(hour=close_hour, minute=close_minute)
            
            current_time = now_kst.time()
            is_open = market_open <= current_time <= market_close
            
            logger.info(f"한국 시장 시간 확인: 현재 {current_time.strftime('%H:%M')}, 개장 {market_open_str}~{market_close_str}, 결과: {'열림' if is_open else '닫힘'}")
            return is_open
            
        elif market == "US":
            # 설정에서 시장 시간 가져오기
            market_open_str = getattr(self.config, 'US_MARKET_OPEN_TIME', "09:30")
            market_close_str = getattr(self.config, 'US_MARKET_CLOSE_TIME', "16:00")
            
            # 미국 동부 시간 (EST/EDT) 계산
            now_us_eastern = datetime.datetime.now(pytz.timezone('US/Eastern'))
            
            # 미국 시장 시간 (9:30 ~ 16:00 EST)
            open_hour, open_minute = map(int, market_open_str.split(':'))
            close_hour, close_minute = map(int, market_close_str.split(':'))
            
            market_open = datetime.time(hour=open_hour, minute=open_minute)
            market_close = datetime.time(hour=close_hour, minute=close_minute)
            
            current_time = now_us_eastern.time()
            is_open = market_open <= current_time <= market_close
            
            logger.info(f"미국 시장 시간 확인: 현재(ET) {current_time.strftime('%H:%M')}, 개장 {market_open_str}~{market_close_str}, 결과: {'열림' if is_open else '닫힘'}")
            return is_open
        
        return False
    
    def check_stop_loss_take_profit(self):
        """
        보유 종목에 대한 손절매/익절 조건 확인 및 처리
        GPT 분석 기반으로 종목별 맞춤 손절/익절 수준 적용
        """
        if not self.holdings:
            return
            
        logger.info("손절매/익절 조건 확인 시작")
        
        for symbol, holding in list(self.holdings.items()):
            if holding['quantity'] <= 0:
                continue
                
            market = holding.get('market', 'KR')
            avg_price = holding.get('avg_price', 0)
            quantity = holding.get('quantity', 0)
            
            # 현재 가격 조회
            current_price = self.mock_stock_data.get_current_price(symbol)
            if current_price is None:
                logger.warning(f"{symbol}: 현재 가격을 조회할 수 없습니다.")
                continue
                
            # 수익률 계산
            profit_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
            profit_amount = (current_price - avg_price) * quantity
            
            stock_name = self.mock_stock_data.get_stock_name(symbol)
            currency = "원" if market == "KR" else "달러"
            
            # 모의 주식 데이터 생성 (GPT 분석용)
            stock_df = self.mock_stock_data.generate_mock_data(symbol, days=30)
            if stock_df.empty:
                logger.warning(f"{symbol}의 데이터를 생성할 수 없어 기본 손절/익절 값을 사용합니다.")
                stop_loss = self.stop_loss_pct
                take_profit = self.take_profit_pct
                trailing_stop_distance = self.trailing_stop_distance
            else:
                # 시장 맥락 정보
                market_context = {
                    "market": market,
                    "current_time": datetime.datetime.now().isoformat(),
                    "is_market_open": self.is_market_open(market),
                    "current_price": current_price,
                    "currency": currency,
                    "profit_pct": profit_pct
                }
                
                # 이 종목에 대한 맞춤형 손절/익절 전략이 필요한 경우 (보유 종목)
                if self.use_gpt_analysis and hasattr(self, 'gpt_strategy'):
                    try:
                        # GPT 기반 손절/익절 수준 분석
                        logger.info(f"{symbol}({stock_name}): GPT 기반 손절/익절 수준 분석 시작")
                        stop_levels = self.gpt_strategy.analyze_stop_levels(stock_df, symbol, market_context)
                        
                        # 분석 결과에서 값 추출
                        stop_loss = stop_levels.get("stop_loss_pct", self.stop_loss_pct)
                        take_profit = stop_levels.get("take_profit_pct", self.take_profit_pct)
                        trailing_stop_distance = stop_levels.get("trailing_stop_distance", self.trailing_stop_distance)
                        
                        # 설정값 로그 출력
                        logger.info(f"{symbol}({stock_name}) 맞춤 손절/익절: 손절 {stop_loss:.1f}%, 익절 {take_profit:.1f}%, "
                                   f"트레일링스탑 {trailing_stop_distance:.1f}%")
                    except Exception as e:
                        # GPT 분석 실패 시 기본값 사용
                        logger.error(f"{symbol}({stock_name}) GPT 손절/익절 분석 실패: {e}")
                        stop_loss = self.stop_loss_pct
                        take_profit = self.take_profit_pct
                        trailing_stop_distance = self.trailing_stop_distance
                else:
                    # GPT 분석을 사용하지 않을 경우 기본값 사용
                    stop_loss = self.stop_loss_pct
                    take_profit = self.take_profit_pct
                    trailing_stop_distance = self.trailing_stop_distance
            
            # 트레일링 스탑 업데이트 (가격이 상승한 경우)
            if self.use_trailing_stop:
                if symbol not in self.trailing_stops:
                    # 처음 기록하는 경우 초기 설정
                    self.trailing_stops[symbol] = {
                        'highest_price': current_price,
                        'stop_price': current_price * (1 - trailing_stop_distance / 100)
                    }
                else:
                    # 가격이 이전 최고가보다 상승한 경우 트레일링 스탑 업데이트
                    if current_price > self.trailing_stops[symbol]['highest_price']:
                        self.trailing_stops[symbol]['highest_price'] = current_price
                        self.trailing_stops[symbol]['stop_price'] = current_price * (1 - trailing_stop_distance / 100)
                        logger.info(f"{symbol}({stock_name}): 트레일링 스탑 갱신 - 최고가: {current_price:,.0f}{currency}, "
                                   f"스탑가: {self.trailing_stops[symbol]['stop_price']:,.0f}{currency}")
            
            # 손절매 조건 확인
            stop_triggered = False
            if profit_pct <= -stop_loss:
                reason = f"손절매 조건 충족 (수익률: {profit_pct:.2f}%, 기준: -{stop_loss:.1f}%)"
                stop_triggered = True
                
            elif self.use_trailing_stop and symbol in self.trailing_stops and current_price <= self.trailing_stops[symbol]['stop_price']:
                highest_price = self.trailing_stops[symbol]['highest_price']
                drop_pct = ((current_price / highest_price) - 1) * 100
                reason = f"트레일링 스탑 조건 충족 (최고가: {highest_price:,.0f}{currency} 대비 {drop_pct:.2f}%, 기준: -{trailing_stop_distance:.1f}%)"
                stop_triggered = True
                
            if stop_triggered:
                logger.info(f"{symbol}({stock_name}) {reason} - 매도 실행")
                
                # 모든 보유 수량 매도 신호 생성
                sell_signal = {
                    'symbol': symbol,
                    'name': stock_name,
                    'price': current_price,
                    'market': market,
                    'currency': currency,
                    'timestamp': datetime.datetime.now(),
                    'signals': [{
                        'type': 'SELL',
                        'strength': 'STRONG',
                        'reason': reason,
                        'confidence': 0.9,
                        'date': datetime.datetime.now().strftime('%Y-%m-%d')
                    }]
                }
                
                # 매도 실행
                if self.execute_trade(sell_signal):
                    self.send_trade_notification(sell_signal, True)
                    
                    # 트레일링 스탑 정보 삭제
                    if self.use_trailing_stop and symbol in self.trailing_stops:
                        del self.trailing_stops[symbol]
                        
                    continue
            
            # 익절 조건 확인
            if profit_pct >= take_profit:
                reason = f"익절 조건 충족 (수익률: +{profit_pct:.2f}%, 기준: +{take_profit:.1f}%)"
                logger.info(f"{symbol}({stock_name}) {reason} - 매도 실행")
                
                # 모든 보유 수량 매도 신호 생성
                sell_signal = {
                    'symbol': symbol,
                    'name': stock_name,
                    'price': current_price,
                    'market': market,
                    'currency': currency,
                    'timestamp': datetime.datetime.now(),
                    'signals': [{
                        'type': 'SELL',
                        'strength': 'STRONG',
                        'reason': reason,
                        'confidence': 0.9,
                        'date': datetime.datetime.now().strftime('%Y-%m-%d')
                    }]
                }
                
                # 매도 실행
                if self.execute_trade(sell_signal):
                    self.send_trade_notification(sell_signal, True)
                    
                    # 트레일링 스탑 정보 삭제
                    if self.use_trailing_stop and symbol in self.trailing_stops:
                        del self.trailing_stops[symbol]
        
        logger.info("손절매/익절 조건 확인 완료")

    def check_market_status(self):
        """
        시장 상태 확인 및 필요한 작업 수행
        """
        kr_open = self.is_market_open("KR")
        us_open = self.is_market_open("US")
        
        current_time_kr = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"시장 상태 확인 ({current_time_kr}) - 한국: {'열림' if kr_open else '닫힘'}, 미국: {'열림' if us_open else '닫힘'}")
        
        # 손절매/익절 확인 (시장이 열렸을 때만)
        if kr_open or us_open:
            self.check_stop_loss_take_profit()
        
        # 한국 시장이 열려있으면 한국 종목 거래
        if kr_open:
            logger.info("한국 시장 거래 세션 실행")
            self.run_trading_session("KR", iterations=3)
        
        # 미국 시장이 열려있으면 미국 종목 거래
        if us_open:
            logger.info("미국 시장 거래 세션 실행")
            self.run_trading_session("US", iterations=3)
    
    def run(self):
        """
        모의 자동매매 시스템 실행
        """
        if self.is_running:
            logger.warning("모의 자동매매 시스템이 이미 실행 중입니다")
            return
            
        self.is_running = True
        
        try:
            # 시스템 시작 메시지
            start_message = "🚀 24시간 모의자동매매 시스템이 시작되었습니다.\n"
            start_message += f"• 시작 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            start_message += f"• 초기 계좌 잔고: {self.account_balance:,}원\n"
            start_message += f"• 한국 종목: {', '.join([f'{symbol}({self.mock_stock_data.get_stock_name(symbol)})' for symbol in self.kr_symbols])}\n"
            start_message += f"• 미국 종목: {', '.join([f'{symbol}({self.mock_stock_data.get_stock_name(symbol)})' for symbol in self.us_symbols])}\n"
            
            self.kakao_sender.send_system_status(start_message)
            logger.info("모의 자동매매 시스템 시작")
            
            # 스케줄 설정
            # 주기적으로 시장 상태 확인 및 거래 실행 (5분 간격)
            schedule.every(5).minutes.do(self.check_market_status)
            
            # 매일 아침 9시 거래 요약
            schedule.every().day.at("09:00").do(self.send_trading_summary)
            
            # 매일 저녁 6시 거래 요약
            schedule.every().day.at("18:00").do(self.send_trading_summary)
            
            # 첫 번째 시장 상태 확인 및 거래 실행
            self.check_market_status()
            
            # 메인 루프
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # 1분 간격으로 스케줄 확인
                
        except KeyboardInterrupt:
            logger.info("사용자에 의해 시스템 종료")
            self.stop()
            
        except Exception as e:
            logger.error(f"시스템 실행 중 오류 발생: {e}")
            self.stop()
            
    def stop(self):
        """
        모의 자동매매 시스템 종료
        """
        if not self.is_running:
            return
            
        self.is_running = False
        
        # 거래 요약 알림 전송
        self.send_trading_summary()
        
        # 시스템 종료 메시지
        stop_message = "⛔️ 24시간 모의 자동매매 시스템이 종료되었습니다.\n"
        stop_message += f"• 종료 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        stop_message += f"• 최종 계좌 잔고: {self.account_balance:,}원\n"
        
        self.kakao_sender.send_system_status(stop_message)
        logger.info("모의 자동매매 시스템 종료")

def main():
    """메인 함수"""
    logger.info("24시간 모의 자동매매 시스템 시작")
    
    try:
        # 모의 자동매매 객체 생성
        mock_trader = MockAutoTrader(config)
        
        # 모의 자동매매 시스템 실행
        mock_trader.run()
        
    except KeyboardInterrupt:
        logger.info("사용자에 의해 시스템이 중단되었습니다.")
    except Exception as e:
        logger.error(f"시스템 중 오류 발생: {e}")
    finally:
        logger.info("24시간 모의 자동매매 시스템 종료")

if __name__ == "__main__":
    main()