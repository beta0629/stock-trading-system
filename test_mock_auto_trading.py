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
import pandas as pd
import numpy as np
import pytz
import schedule
from src.notification.kakao_sender import KakaoSender
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
    """모의 자동매매 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 객체
        """
        self.config = config
        self.mock_stock_data = MockStockData()
        self.kakao_sender = KakaoSender(config)
        self.account_balance = 50000000  # 5천만원 초기 자본금
        
        # 거래 이력
        self.trading_history = []
        # 보유 종목
        self.holdings = {}
        
        # 시장별 종목 목록 (한국/미국)
        self.kr_symbols = []
        self.us_symbols = []
        
        # GPT가 선정한 종목이 있으면 사용, 없으면 기본 종목 사용
        if hasattr(self.config, 'KR_STOCKS') and self.config.KR_STOCKS:
            self.kr_symbols = self.config.KR_STOCKS
        else:
            self.kr_symbols = [
                "005930",  # 삼성전자
                "000660",  # SK하이닉스
                "035420",  # NAVER
                "051910",  # LG화학
                "035720",  # 카카오
            ]
            
        if hasattr(self.config, 'US_STOCKS') and self.config.US_STOCKS:
            self.us_symbols = self.config.US_STOCKS
        else:
            self.us_symbols = [
                "AAPL",    # 애플
                "MSFT",    # 마이크로소프트
                "GOOGL",   # 알파벳
                "AMZN",    # 아마존
                "TSLA",    # 테슬라
            ]
        
        # 시스템 실행 상태
        self.is_running = False
        
        logger.info("모의 자동매매 클래스 초기화 완료")
        logger.info(f"시작 계좌 잔고: {self.account_balance:,}원")
        logger.info(f"한국 종목 목록: {', '.join(self.kr_symbols)}")
        logger.info(f"미국 종목 목록: {', '.join(self.us_symbols)}")
    
    def generate_trading_signal(self, symbol, market="KR"):
        """
        랜덤 매매 신호 생성
        
        Args:
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            dict: 매매 신호 데이터
        """
        # 매수/매도 신호 랜덤 생성
        signal_type = random.choice(["BUY", "SELL"])
        
        # 현재가 가져오기
        current_price = self.mock_stock_data.get_current_price(symbol)
        if current_price is None:
            return None
        
        # 종목명 가져오기
        stock_name = self.mock_stock_data.get_stock_name(symbol)
        
        # 시장에 따라 통화 설정
        currency = "원" if market == "KR" else "달러"
        
        # 신호 강도 랜덤 생성
        strength = random.choice(["WEAK", "MEDIUM", "STRONG"])
        
        # 신호 이유 생성
        reasons_by_type = {
            "BUY": [
                f"{stock_name}의 기술적 지표가 매수 신호를 보입니다",
                f"{stock_name}의 상대강도지수(RSI)가 과매도 구간에서 반등했습니다",
                f"{stock_name}의 이동평균선이 골든크로스를 형성했습니다",
                f"{stock_name}의 볼린저밴드 하단에 접근했습니다",
                f"{stock_name}의 MACD가 시그널 라인을 상향 돌파했습니다"
            ],
            "SELL": [
                f"{stock_name}의 기술적 지표가 매도 신호를 보입니다",
                f"{stock_name}의 상대강도지수(RSI)가 과매수 구간에 진입했습니다",
                f"{stock_name}의 이동평균선이 데드크로스를 형성했습니다",
                f"{stock_name}의 볼린저밴드 상단에 접근했습니다",
                f"{stock_name}의 MACD가 시그널 라인을 하향 돌파했습니다"
            ]
        }
        
        reason = random.choice(reasons_by_type[signal_type])
        
        # 지금 시간
        timestamp = datetime.datetime.now()
        
        signal = {
            'symbol': symbol,
            'name': stock_name,
            'price': current_price,
            'market': market,
            'currency': currency,
            'timestamp': timestamp,
            'signals': [{
                'type': signal_type,
                'strength': strength,
                'reason': reason,
                'date': timestamp.strftime('%Y-%m-%d')
            }]
        }
        
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
        
        # 매매 수량 결정
        trade_amount = 0
        
        if signal_type == "BUY":
            # 매수할 금액 결정 (강도에 따라)
            strength_factor = {"WEAK": 0.1, "MEDIUM": 0.2, "STRONG": 0.3}
            max_amount = min(self.account_balance, self.config.MAX_AMOUNT_PER_TRADE)
            trade_amount = max_amount * strength_factor[strength]
            
            # 최대 매수 수량 계산
            buy_quantity = int(trade_amount / price)
            
            if buy_quantity <= 0:
                logger.info(f"{symbol} 매수 신호가 있으나 수량이 0보다 작거나 같습니다")
                return False
                
            # 계좌 잔고 확인
            if self.account_balance < buy_quantity * price:
                logger.info(f"{symbol} 매수 신호가 있으나 계좌 잔고가 부족합니다")
                return False
                
            # 매수 실행
            self.account_balance -= buy_quantity * price
            
            # 보유종목 업데이트
            total_quantity = holding_quantity + buy_quantity
            total_amount = (holding_quantity * current_holdings['avg_price']) + (buy_quantity * price)
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
                'amount': buy_quantity * price
            })
            
            currency = "원" if market == "KR" else "달러"
            logger.info(f"{symbol}({stock_name}) {buy_quantity}주 매수 완료 - 단가: {price:,}{currency}, 총액: {buy_quantity * price:,}{currency}")
            return True
            
        elif signal_type == "SELL":
            # 보유 종목이 있는지 확인
            if holding_quantity <= 0:
                logger.info(f"{symbol} 매도 신호가 있으나 보유수량이 없습니다")
                return False
                
            # 매도할 수량 결정 (강도에 따라)
            strength_factor = {"WEAK": 0.2, "MEDIUM": 0.5, "STRONG": 0.8}
            sell_quantity = int(holding_quantity * strength_factor[strength])
            
            if sell_quantity <= 0:
                logger.info(f"{symbol} 매도 신호가 있으나 매도 수량이 0보다 작거나 같습니다")
                return False
                
            # 매도 실행
            self.account_balance += sell_quantity * price
            
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
                'amount': sell_quantity * price
            })
            
            currency = "원" if market == "KR" else "달러"
            logger.info(f"{symbol}({stock_name}) {sell_quantity}주 매도 완료 - 단가: {price:,}{currency}, 총액: {sell_quantity * price:,}{currency}")
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
                total_holdings_value = sum(holding['quantity'] * self.mock_stock_data.get_current_price(symbol) 
                                         for symbol, holding in self.holdings.items() if holding['quantity'] > 0 and holding.get('market') == 'KR')
                
                # 미국 주식 가치 원화 환산
                exchange_rate = 1300  # 가정 환율
                us_holdings_value_krw = sum(holding['quantity'] * self.mock_stock_data.get_current_price(symbol) * exchange_rate
                                          for symbol, holding in self.holdings.items() if holding['quantity'] > 0 and holding.get('market') == 'US')
                
                total_assets = self.account_balance + total_holdings_value + us_holdings_value_krw
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
        # 현재 한국 시간
        now_kr = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
        current_weekday = now_kr.weekday()  # 0=월요일, 1=화요일, ..., 6=일요일
        
        # 주말이면 시장 닫힘
        if current_weekday >= 5:  # 토요일(5) 또는 일요일(6)
            return False
        
        if market == "KR":
            # 한국 시장 시간 (9:00 ~ 15:30)
            market_open = datetime.time(hour=9, minute=0)
            market_close = datetime.time(hour=15, minute=30)
            
            current_time = now_kr.time()
            return market_open <= current_time <= market_close
            
        elif market == "US":
            # 미국 동부 시간 (EST)
            now_us = datetime.datetime.now(pytz.timezone('US/Eastern'))
            
            # 미국 시장 시간 (9:30 ~ 16:00 EST)
            market_open = datetime.time(hour=9, minute=30)
            market_close = datetime.time(hour=16, minute=0)
            
            current_time = now_us.time()
            return market_open <= current_time <= market_close
        
        return False
    
    def check_market_status(self):
        """
        시장 상태 확인 및 필요한 작업 수행
        """
        kr_open = self.is_market_open("KR")
        us_open = self.is_market_open("US")
        
        current_time_kr = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"시장 상태 확인 ({current_time_kr}) - 한국: {'열림' if kr_open else '닫힘'}, 미국: {'열림' if us_open else '닫힘'}")
        
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
            start_message = "🚀 24시간 모의 자동매매 시스템이 시작되었습니다.\n"
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