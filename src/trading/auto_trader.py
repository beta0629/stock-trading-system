"""
AI 기반 자동 주식 매매 실행 모듈

이 모듈은 AI 분석 결과를 바탕으로 주식 매매를 자동 실행합니다.
증권사 API와 연동하여 실제 주문을 처리합니다.
"""

import logging
import time
import json
import pandas as pd
import datetime  # datetime 모듈 추가
from enum import Enum
import traceback

# 시간 유틸리티 모듈
from src.utils.time_utils import (
    get_current_time, get_current_time_str, is_market_open,
    format_timestamp, get_market_hours, KST, EST, parse_time
)

# 로깅 설정
logger = logging.getLogger('AutoTrader')

class TradeAction(Enum):
    """매매 동작 정의"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class OrderType(Enum):
    """주문 유형 정의"""
    MARKET = "MARKET"      # 시장가
    LIMIT = "LIMIT"        # 지정가
    CONDITIONAL = "CONDITIONAL"  # 조건부 주문

class OrderStatus(Enum):
    """주문 상태 정의"""
    RECEIVED = "RECEIVED"  # 주문 접수
    EXECUTED = "EXECUTED"  # 체결됨
    PARTIALLY = "PARTIALLY_EXECUTED"  # 일부 체결
    CANCELED = "CANCELED"  # 취소됨
    REJECTED = "REJECTED"  # 거부됨
    PENDING = "PENDING"    # 대기 중

class AutoTrader:
    """자동 매매 실행 클래스"""
    
    def __init__(self, config, broker, data_provider, strategy_provider, notifier=None):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
            broker: 증권사 API 객체
            data_provider: 주가 데이터 제공자
            strategy_provider: 트레이딩 전략 제공자
            notifier: 알림 발송 객체 (선택적)
        """
        # 로거 설정
        self.logger = logging.getLogger('AutoTrader')
        
        self.config = config
        self.broker = broker
        self.data_provider = data_provider
        self.strategy = strategy_provider
        self.notifier = notifier
        
        # 설정 값 로드
        self.initial_capital = getattr(config, 'INITIAL_CAPITAL', 10000000)  # 초기 자본금 (기본 1천만원) - 기본값으로 유지
        self.max_position_pct = getattr(config, 'MAX_POSITION_PCT', 20)  # 종목당 최대 포지션 (기본 20%)
        self.stop_loss_pct = getattr(config, 'STOP_LOSS_PCT', 3)  # 손절매 비율 (기본 3%)
        self.take_profit_pct = getattr(config, 'TAKE_PROFIT_PCT', 5)  # 익절 비율 (기본 5%)
        self.trade_interval = getattr(config, 'TRADE_INTERVAL_SECONDS', 3600)  # 매매 간격 (기본 1시간)
        self.market_hours = getattr(config, 'MARKET_HOURS', {})  # 시장 운영 시간
        self.simulation_mode = getattr(config, 'SIMULATION_MODE', False)  # 시뮬레이션 모드 (기본값: 실제 거래)
        
        # 포지션 및 주문 이력 관리
        self.positions = {}  # {종목코드: {수량, 평균단가, 현재가치, ...}}
        self.order_history = []  # 주문 이력
        self.last_check_time = {}  # {종목코드: 마지막 확인 시간}
        self.trade_stats = {  # 매매 통계
            "win_count": 0,
            "loss_count": 0,
            "total_profit": 0,
            "total_loss": 0,
            "max_profit": 0,
            "max_loss": 0
        }
        
        # 모니터링 대상 종목
        self.watchlist = getattr(config, 'WATCHLIST', [])
        
        # 계좌 잔고 초기화 - 모의 투자 계좌에서 실제 잔고를 가져오도록 수정
        self.account_balance = 0
        self.available_cash = 0  # 사용 가능한 현금
        self.max_buy_ratio = 0.5  # 최대 매수 비율 (기본 50%)
        self._load_account_balance()
        
        self.logger.info("자동매매 시스템 초기화 완료")
        if self.simulation_mode:
            self.logger.warning("!! 시뮬레이션 모드로 실행 중. 실제 거래는 발생하지 않습니다 !!")
        else:
            self.logger.info("!! 실제 거래 모드로 실행 중. 실제 자금으로 거래가 발생합니다 !!")
    
    def _load_account_balance(self, force_refresh=False):
        """
        계좌 잔고 정보를 불러와서 현재 상태 업데이트
        
        Args:
            force_refresh (bool): 강제로 잔고 갱신 여부
        
        Returns:
            dict: 계좌 잔고 정보
        """
        # API에서 계좌 잔고 가져오기
        max_attempts = 3 if force_refresh else 1
        delay_seconds = 1
        
        for attempt in range(max_attempts):
            # 타임스탬프 추가하여 캐시 방지
            timestamp = int(time.time() * 1000)
            
            if attempt > 0:
                self.logger.info(f"계좌 잔고 새로고침 시도 {attempt+1}/{max_attempts}")
                time.sleep(delay_seconds)
                # 시도마다 지연시간 증가
                delay_seconds *= 1.5
            
            balance = self.broker.get_balance(force_refresh=force_refresh, timestamp=timestamp)
            
            if "error" not in balance:
                self.balance = balance
                self.available_cash = balance.get("주문가능금액", 0)
                
                # 최신 잔고 정보로 업데이트됐는지 확인
                if "timestamp" in balance and balance["timestamp"] == timestamp:
                    self.logger.info(f"계좌 잔고 갱신 성공: 주문가능금액 {self.available_cash:,}원")
                    return balance
                else:
                    self.logger.info(f"잔고 정보가 최신 상태로 확인됨: {self.available_cash:,}원")
                    return balance
        
        self.logger.warning("계좌 잔고 새로고침 시도 후에도 최신 정보를 가져오지 못했습니다")
        return balance

    def _update_available_cash(self, account_info):
        """
        사용 가능한 현금(매수 가능 금액) 업데이트
        """
        try:
            # 모의 투자 계좌 처리
            if not self.broker.real_trading:
                # 출금가능금액이 있으면 사용
                if "출금가능금액" in account_info and account_info["출금가능금액"] > 0:
                    self.available_cash = account_info["출금가능금액"]
                    logger.info(f"모의 계좌 출금가능금액으로 설정: {self.available_cash:,}원")
                
                # D+2예수금이 있으면 사용
                elif "D+2예수금" in account_info and account_info["D+2예수금"] > 0:
                    self.available_cash = account_info["D+2예수금"]
                    logger.info(f"모의 계좌 D+2예수금으로 설정: {self.available_cash:,}원")
                
                # 예수금 사용
                else:
                    self.available_cash = account_info.get("예수금", 0)
                    logger.info(f"모의 계좌 예수금으로 설정: {self.available_cash:,}원")
            else:
                # 실제 투자 계좌는 기존 방식 유지
                self.available_cash = account_info.get("출금가능금액", 0)
                
            # 매수 금액 제한 적용
            max_available = self.account_balance * self.max_buy_ratio
            if self.available_cash > max_available:
                logger.info(f"매수 금액 제한 적용: {self.available_cash:,}원 -> {max_available:,}원 (총 자산의 {self.max_buy_ratio*100}%)")
                self.available_cash = max_available
                
        except Exception as e:
            logger.error(f"사용 가능 현금 업데이트 실패: {e}")
            logger.error(traceback.format_exc())
            self.available_cash = 0
    
    def _check_market_open(self, market="KR"):
        """
        시장이 열려있는지 확인
        
        Args:
            market: 시장 코드 ("KR" 또는 "US")
            
        Returns:
            bool: 시장 개장 여부
        """
        # 시간 유틸리티 모듈 사용
        return is_market_open(market)
    
    def _load_positions(self):
        """현재 보유 포지션 로드"""
        try:
            # 증권사 API에서 포지션 정보 가져오기
            if not self.simulation_mode:
                positions_list = self.broker.get_positions()
                
                # 포지션 형식 변환 (리스트 -> 딕셔너리)
                positions = {}
                for position in positions_list:
                    # "종목코드" 필드를 찾아서 symbol로 사용
                    if "종목코드" in position:
                        symbol = position["종목코드"]
                        symbol_name = position.get("종목명", symbol)
                        quantity = position.get("보유수량", 0)
                        avg_price = position.get("평균단가", 0)
                        current_price = position.get("현재가", 0)
                        current_value = position.get("평가금액", 0)
                        profit_loss = position.get("손익금액", 0)
                        
                        # 손익률 계산
                        profit_loss_pct = 0
                        if avg_price > 0:
                            profit_loss_pct = ((current_price / avg_price) - 1) * 100
                            
                        # 포지션 데이터 구조 변환
                        positions[symbol] = {
                            'symbol': symbol,
                            'symbol_name': symbol_name,
                            'quantity': quantity,
                            'avg_price': avg_price,
                            'current_price': current_price,
                            'current_value': current_value,
                            'profit_loss': profit_loss,
                            'profit_loss_pct': profit_loss_pct,
                            'market': 'KR'  # 기본값으로 KR 설정
                        }
                
                self.positions = positions
                logger.info(f"포지션 로드 완료: {len(self.positions)}개 종목 보유 중")
            else:
                # 모의 투자 모드에서도 실제 포지션을 불러옵니다
                try:
                    positions_list = self.broker.get_positions()
                    if positions_list:
                        # 포지션 형식 변환 (리스트 -> 딕셔너리)
                        positions = {}
                        for position in positions_list:
                            # "종목코드" 필드를 찾아서 symbol로 사용
                            if "종목코드" in position:
                                symbol = position["종목코드"]
                                symbol_name = position.get("종목명", symbol)
                                quantity = position.get("보유수량", 0)
                                avg_price = position.get("평균단가", 0)
                                current_price = position.get("현재가", 0)
                                current_value = position.get("평가금액", 0)
                                profit_loss = position.get("손익금액", 0)
                                
                                # 손익률 계산
                                profit_loss_pct = 0
                                if avg_price > 0:
                                    profit_loss_pct = ((current_price / avg_price) - 1) * 100
                                    
                                # 포지션 데이터 구조 변환
                                positions[symbol] = {
                                    'symbol': symbol,
                                    'symbol_name': symbol_name,
                                    'quantity': quantity,
                                    'avg_price': avg_price,
                                    'current_price': current_price,
                                    'current_value': current_value,
                                    'profit_loss': profit_loss,
                                    'profit_loss_pct': profit_loss_pct,
                                    'market': 'KR'  # 기본값으로 KR 설정
                                }
                        
                        self.positions = positions
                        logger.info(f"모의 투자 포지션 로드 완료: {len(self.positions)}개 종목 보유 중")
                    else:
                        # 포지션 정보를 불러오지 못한 경우 기존 정보 유지
                        logger.info(f"모의 투자 포지션 정보 없음: {len(self.positions)}개 종목 보유 중으로 유지")
                except Exception as e:
                    logger.warning(f"모의 투자 포지션 로드 실패, 기존 상태 유지: {e}")
            return self.positions
        except Exception as e:
            logger.error(f"포지션 로드 중 오류 발생: {e}")
            return {}
    
    def _update_position_value(self):
        """보유 포지션 가치 업데이트"""
        try:
            # positions이 딕셔너리인지 확인하고, 아닌 경우 적절히 변환
            if isinstance(self.positions, list):
                # 리스트를 딕셔너리로 변환 (symbol을 키로 사용)
                positions_dict = {}
                for position in self.positions:
                    if isinstance(position, dict) and 'symbol' in position:
                        positions_dict[position['symbol']] = position
                self.positions = positions_dict
                logger.info(f"포지션 데이터 구조를 리스트에서 딕셔너리로 변환했습니다. {len(self.positions)}개 항목")

            # 이제 딕셔너리로 처리
            for symbol, position in self.positions.items():
                # 현재가 조회
                current_price = self.data_provider.get_current_price(symbol, position.get('market', 'KR'))
                if current_price:
                    # 포지션 가치 업데이트
                    qty = position.get('quantity', 0)
                    avg_price = position.get('avg_price', 0)
                    position['current_price'] = current_price
                    position['current_value'] = current_price * qty
                    position['profit_loss'] = (current_price - avg_price) * qty
                    position['profit_loss_pct'] = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
            
            logger.debug("포지션 가치 업데이트 완료")
        except Exception as e:
            logger.error(f"포지션 가치 업데이트 중 오류 발생: {e}")
    
    def _get_available_cash(self):
        """사용 가능한 현금 잔고를 반환"""
        try:
            # 모의 투자 계좌에서 실제 잔고 조회
            balance_info = self.broker.get_balance()
            logger.debug(f"사용 가능 현금 조회 결과: {balance_info}")
            
            if balance_info:
                # 주문가능금액이 있으면 해당 값을 우선 사용
                if "주문가능금액" in balance_info and balance_info["주문가능금액"] > 0:
                    available_cash = balance_info["주문가능금액"]
                    logger.info(f"사용 가능 현금(주문가능금액): {available_cash:,}원")
                    return available_cash
                # 다음으로 예수금을 사용
                elif "예수금" in balance_info and balance_info["예수금"] > 0:
                    available_cash = balance_info["예수금"]
                    logger.info(f"사용 가능 현금(예수금): {available_cash:,}원")
                    return available_cash
            
            # 계좌 잔고를 불러오지 못한 경우, 현재 계좌 잔고 사용
            logger.warning("사용 가능 현금을 API에서 불러오지 못했습니다. 계좌 잔고 사용.")
            return self.account_balance
        except Exception as e:
            logger.error(f"사용 가능 현금 조회 실패: {e}")
            logger.error(traceback.format_exc())
            # 오류 발생 시 현재 계좌 잔고 사용
            return self.account_balance
    
    def _calculate_position_size(self, symbol, price, signal_strength):
        """
        매수 포지션 사이즈 계산
        
        Args:
            symbol: 종목 코드
            price: 현재 가격
            signal_strength: 신호 강도 ("STRONG", "MODERATE", "WEAK")
            
        Returns:
            int: 매수 수량
        """
        try:
            # 사용 가능한 현금 조회 (API에서 실제 잔고 조회)
            available_cash = self._get_available_cash()
            
            # 신호 강도에 따른 포지션 크기 조정
            position_pct = self.max_position_pct
            if signal_strength == "STRONG":
                position_pct = self.max_position_pct
            elif signal_strength == "MODERATE":
                position_pct = self.max_position_pct * 0.7
            elif signal_strength == "WEAK":
                position_pct = self.max_position_pct * 0.5
            
            # 최대 투자 금액 계산
            max_investment = available_cash * (position_pct / 100)
            
            # 매수 수량 계산 (1주 단위로 내림)
            quantity = max_investment // price
            
            return int(max(quantity, 1))  # 최소 1주 이상
        except Exception as e:
            logger.error(f"포지션 사이즈 계산 중 오류 발생: {e}")
            return 1
    
    def _execute_order(self, symbol, action, quantity, price=None, order_type=OrderType.MARKET, market="KR"):
        """
        주문 실행
        
        Args:
            symbol: 종목 코드
            action: 매매 동작 (TradeAction)
            quantity: 수량
            price: 가격 (지정가 주문시)
            order_type: 주문 유형 (OrderType)
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            dict: 주문 결과
        """
        try:
            # 종목 이름 설정
            stock_name = symbol
            if hasattr(self.config, 'KR_STOCK_INFO') and market == "KR":
                for stock in self.config.KR_STOCK_INFO:
                    if stock['code'] == symbol:
                        stock_name = stock['name']
                        break
            elif hasattr(self.config, 'US_STOCK_INFO') and market == "US":
                for stock in self.config.US_STOCK_INFO:
                    if stock['code'] == symbol:
                        stock_name = stock['name']
                        break
                
            # 디버그 로깅: 종목명 확인
            logger.info(f"주문 실행: 종목명 확인 - 심볼: {symbol}, 종목명: {stock_name}")
            
            order_info = {
                "symbol": symbol,
                "symbol_name": stock_name,
                "action": action.value,
                "quantity": quantity,
                "price": price,
                "order_type": order_type.value,
                "market": market,
                "timestamp": get_current_time().isoformat(),
                "status": OrderStatus.RECEIVED.value
            }
            
            # 시뮬레이션 모드 체크
            if self.simulation_mode:
                # 시뮬레이션 모드에서는 주문을 실행하지 않고 성공으로 가정
                logger.info(f"[시뮬레이션] {action.value} {stock_name}({symbol}) x {quantity}주")
                
                # 시뮬레이션 포지션 업데이트
                if not price and market == "KR":
                    # 현재가로 시장가 주문 시뮬레이션
                    price = self.data_provider.get_current_price(symbol, market)
                
                # 계좌 잔고 (시뮬레이션)
                balance = self._get_available_cash()
                
                # 매매 처리 전 기존 보유 수량 및 평단가 저장
                prev_quantity = 0
                prev_avg_price = 0
                if symbol in self.positions:
                    prev_quantity = self.positions[symbol].get('quantity', 0)
                    prev_avg_price = self.positions[symbol].get('avg_price', 0)
                
                # 매매 금액
                trade_amount = price * quantity
                
                if action == TradeAction.BUY:
                    if symbol not in self.positions:
                        self.positions[symbol] = {
                            'symbol': symbol,
                            'symbol_name': stock_name,
                            'market': market,
                            'quantity': quantity,
                            'avg_price': price,
                            'current_price': price,
                            'current_value': price * quantity,
                            'profit_loss': 0,
                            'profit_loss_pct': 0,
                            'entry_date': get_current_time().isoformat()
                        }
                    else:
                        # 기존 포지션에 추가
                        pos = self.positions[symbol]
                        total_qty = pos['quantity'] + quantity
                        total_value = (pos['avg_price'] * pos['quantity']) + (price * quantity)
                        pos['quantity'] = total_qty
                        pos['avg_price'] = total_value / total_qty
                        pos['current_price'] = price
                        pos['current_value'] = price * total_qty
                    
                    # 거래 후 잔고 업데이트
                    new_balance = balance - trade_amount
                    total_quantity = prev_quantity + quantity
                    
                    # 거래 정보 추가
                    trade_info = {
                        "quantity": quantity,  # 매매 수량
                        "total_quantity": total_quantity,  # 매매 후 총 보유 수량
                        "avg_price": self.positions[symbol]['avg_price'],  # 평균단가
                        "prev_avg_price": prev_avg_price,  # 매매 전 평균단가
                        "balance": new_balance,  # 계좌 잔고
                        "prev_quantity": prev_quantity,  # 매매 전 보유 수량
                        "trade_amount": trade_amount,  # 매매 금액
                        # 모의 거래를 위한 추가 정보 (실제 API와 동일한 형태로)
                        "order_no": f"SIM{int(time.time())}",  # 모의 주문번호
                        "executed_price": price,  # 체결가격
                        "executed_qty": quantity,  # 체결수량
                        "remain_qty": 0,  # 미체결수량
                        "order_status": "체결완료(모의)",  # 주문상태
                        "fee": int(trade_amount * 0.00015),  # 모의 수수료 (0.015%)
                        "transaction_time": get_current_time().strftime("%Y-%m-%d %H:%M:%S")  # 거래시간
                    }
                
                elif action == TradeAction.SELL:
                    if symbol in self.positions:
                        pos = self.positions[symbol]
                        if quantity >= pos['quantity']:
                            # 전량 매도
                            entry_price = pos['avg_price']
                            profit_loss = (price - entry_price) * pos['quantity']
                            profit_loss_pct = ((price / entry_price) - 1) * 100
                            
                            # 매매 통계 업데이트
                            if profit_loss > 0:
                                self.trade_stats["win_count"] += 1
                                self.trade_stats["total_profit"] += profit_loss
                                self.trade_stats["max_profit"] = max(self.trade_stats["max_profit"], profit_loss)
                            else:
                                self.trade_stats["loss_count"] += 1
                                self.trade_stats["total_loss"] += abs(profit_loss)
                                self.trade_stats["max_loss"] = max(self.trade_stats["max_loss"], abs(profit_loss))
                                
                            logger.info(f"[시뮬레이션] {stock_name}({symbol}) 매도 완료: 손익 {profit_loss:,.0f}원 ({profit_loss_pct:.2f}%)")
                            
                            # 매도 수량 및 평균단가 설정
                            sell_quantity = pos['quantity']
                            remaining_quantity = 0
                            new_avg_price = 0
                            
                            del self.positions[symbol]
                            
                        else:
                            # 일부 매도
                            sell_quantity = quantity
                            remaining_quantity = pos['quantity'] - quantity
                            new_avg_price = pos['avg_price']  # 일부 매도 시 평단가 유지
                            
                            pos['quantity'] = remaining_quantity
                            pos['current_value'] = price * remaining_quantity
                        
                        # 거래 후 잔고 업데이트
                        new_balance = balance + (price * quantity)
                        
                        # 수익률 계산
                        profit_loss = (price - prev_avg_price) * quantity
                        profit_loss_pct = ((price / prev_avg_price) - 1) * 100 if prev_avg_price > 0 else 0
                        
                        # 거래 정보 추가
                        trade_info = {
                            "quantity": quantity,  # 매매 수량
                            "total_quantity": remaining_quantity,  # 매매 후 총 보유 수량
                            "avg_price": new_avg_price,  # 평균단가
                            "prev_avg_price": prev_avg_price,  # 매매 전 평균단가
                            "balance": new_balance,  # 계좌 잔고
                            "prev_quantity": prev_quantity,  # 매매 전 보유 수량
                            "trade_amount": price * quantity,  # 매매 금액
                            "profit_loss": profit_loss,  # 매매에 따른 손익
                            "profit_loss_pct": profit_loss_pct,  # 매매 손익률
                            # 모의 거래를 위한 추가 정보 (실제 API와 동일한 형태로)
                            "order_no": f"SIM{int(time.time())}",  # 모의 주문번호
                            "executed_price": price,  # 체결가격
                            "executed_qty": quantity,  # 체결수량
                            "remain_qty": 0,  # 미체결수량
                            "order_status": "체결완료(모의)",  # 주문상태
                            "fee": int((price * quantity) * 0.00015),  # 모의 수수료 (0.015%)
                            "transaction_time": get_current_time().strftime("%Y-%m-%d %H:%M:%S")  # 거래시간
                        }
                
                order_info["status"] = OrderStatus.EXECUTED.value
                order_info["executed_price"] = price
                order_info["executed_quantity"] = quantity
                order_info["trade_info"] = trade_info  # 거래 정보 추가
                
                # 시뮬레이션 모드에서도 계좌 잔고 강제 갱신
                if action == TradeAction.BUY:
                    # 매수 후 잔고를 즉시 업데이트
                    logger.info(f"[시뮬레이션] 매수 후 계좌 잔고 강제 갱신...")
                    self._load_account_balance(force_refresh=True)
                
            else:
                # 실제 주문 실행
                logger.info(f"주문 실행: {action.value} {stock_name}({symbol}) x {quantity}주")
                
                # 거래 전 보유 정보
                prev_quantity = 0
                prev_avg_price = 0
                
                try:
                    # 현재 포지션 정보 확인
                    positions = self.broker.get_positions()
                    if symbol in positions:
                        prev_quantity = positions[symbol].get('quantity', 0)
                        prev_avg_price = positions[symbol].get('avg_price', 0)
                        logger.info(f"기존 보유: {symbol} {prev_quantity}주, 평균단가: {prev_avg_price:,.0f}원")
                    
                    # 현재 계좌 잔고
                    account_info = self.broker.get_balance()
                    balance_before = account_info.get('예수금', 0)
                    logger.info(f"주문 전 계좌 잔고: {balance_before:,.0f}원")
                except Exception as broker_error:
                    logger.error(f"포지션 정보 조회 중 오류: {broker_error}")
                
                # 주문 실행
                if action == TradeAction.BUY:
                    order_result = self.broker.buy(symbol, quantity, price, order_type.value, market)
                else:
                    order_result = self.broker.sell(symbol, quantity, price, order_type.value, market)
                
                # 주문 결과 업데이트
                order_info.update(order_result)
                
                # 주문 체결 확인 대기 (실시간 체결 정보를 받을 수 있는 경우)
                logger.info(f"주문 체결 확인 대기 중...")
                time.sleep(0.5)  # 체결 확인을 위해 잠시 대기
                
                # 주문 체결 상태 확인
                order_no = order_result.get('order_no', '')
                if order_no:
                    try:
                        order_status = self.broker.get_order_status(order_no)
                        logger.info(f"주문 상태: {order_status}")
                        
                        # 주문 상태 정보를 order_info에 추가
                        order_info.update({
                            "executed_quantity": order_status.get('체결수량', 0),
                            "executed_price": order_status.get('체결단가', price),
                            "remain_qty": order_status.get('미체결수량', 0),
                            "order_status": order_status.get('주문상태', '접수')
                        })
                    except Exception as e:
                        logger.error(f"주문 상태 확인 중 오류: {e}")
                
                # 거래 후 정보 조회
                try:
                    # 최소 5초 이상 대기하여 API 캐싱 이슈 방지
                    logger.info(f"계좌 정보 갱신 대기 중 (5초)...")
                    time.sleep(5)
                    
                    # 거래 후 잔고 정보 강제 갱신 (여러번 시도)
                    account_info = None
                    retry_count = 0
                    max_retries = 3
                    while retry_count < max_retries:
                        try:
                            # 캐시를 회피하기 위한 추가 파라미터 사용 (타임스탬프)
                            account_info = self.broker.get_balance(force_refresh=True, timestamp=int(time.time()))
                            balance_after = account_info.get('예수금', 0)
                            
                            # 잔고 정보가 갱신되었는지 확인 (매수인 경우 감소, 매도인 경우 증가)
                            if action == TradeAction.BUY:
                                if balance_before > balance_after:
                                    logger.info(f"계좌 잔고 변경 확인: {balance_before:,}원 -> {balance_after:,}원 (차이: {balance_before - balance_after:,}원)")
                                    break
                            else:  # SELL
                                if balance_before < balance_after:
                                    logger.info(f"계좌 잔고 변경 확인: {balance_before:,}원 -> {balance_after:,}원 (차이: {balance_after - balance_before:,}원)")
                                    break
                                
                            # 변경이 감지되지 않으면 재시도
                            logger.warning(f"계좌 잔고 변경이 감지되지 않음: {balance_before:,}원 -> {balance_after:,}원")
                            retry_count += 1
                            time.sleep(2)  # 2초 대기 후 재시도
                        except Exception as e:
                            logger.error(f"계좌 잔고 조회 재시도 중 오류: {e}")
                            retry_count += 1
                            time.sleep(2)
                    
                    # 포지션 정보 갱신
                    updated_positions = self.broker.get_positions()
                    
                    total_quantity = 0
                    new_avg_price = 0
                    
                    if symbol in updated_positions:
                        total_quantity = updated_positions[symbol].get('quantity', 0)
                        new_avg_price = updated_positions[symbol].get('avg_price', 0)
                        logger.info(f"거래 후 보유: {symbol} {total_quantity}주, 평균단가: {new_avg_price:,.0f}원")
                    
                    # 거래 금액 및 수수료 계산
                    executed_qty = order_info.get('executed_quantity', 0)
                    executed_price = order_info.get('executed_price', price)
                    
                    # None 값 확인 및 기본값 설정
                    if executed_qty is None:
                        executed_qty = 0
                        logger.warning("체결수량이 None입니다. 기본값 0으로 설정합니다.")
                    
                    if executed_price is None:
                        executed_price = 0
                        logger.warning("체결가격이 None입니다. 기본값 0으로 설정합니다.")
                    
                    # 안전한 곱셈 연산
                    trade_amount = executed_qty * executed_price
                    
                    # 예상 수수료 계산 (실제 수수료는 증권사마다 다를 수 있음)
                    fee_rate = getattr(self.config, 'FEE_RATE', 0.00015)  # 기본 0.015%
                    fee = int(trade_amount * fee_rate)
                    
                    # 거래 정보 추가
                    trade_info = {
                        "quantity": executed_qty,  # 체결 수량
                        "total_quantity": total_quantity,  # 매매 후 총 보유 수량
                        "avg_price": new_avg_price,  # 평균단가
                        "prev_avg_price": prev_avg_price,  # 매매 전 평균단가
                        "balance": balance_after,  # 거래 후 계좌 잔고
                        "prev_quantity": prev_quantity,  # 매매 전 보유 수량
                        "trade_amount": trade_amount,  # 거래 금액
                        "order_no": order_no,  # 주문번호
                        "executed_price": executed_price,  # 체결가격
                        "executed_qty": executed_qty,  # 체결수량
                        "remain_qty": order_info.get('remain_qty', 0),  # 미체결수량
                        "order_status": order_info.get('order_status', ''),  # 주문상태
                        "fee": fee,  # 수수료
                        "transaction_time": get_current_time().strftime("%Y-%m-%d %H:%M:%S")  # 거래시간
                    }
                    
                    # 매도의 경우 손익 정보 추가
                    if action == TradeAction.SELL and prev_avg_price > 0:
                        trade_info["profit_loss"] = (executed_price - prev_avg_price) * executed_qty  # 매매에 따른 손익
                        trade_info["profit_loss_pct"] = ((executed_price / prev_avg_price) - 1) * 100  # 매매 손익률
                    
                    order_info["trade_info"] = trade_info
                    
                except Exception as e:
                    logger.error(f"거래 후 정보 조회 중 오류: {e}")
                    # 오류가 발생하더라도 기본 거래 정보는 설정
                    order_info["trade_info"] = {
                        "quantity": quantity,
                        "order_no": order_no,
                        "transaction_time": get_current_time().strftime("%Y-%m-%d %H:%M:%S")
                    }
                
                # 주문 완료 후 계좌 잔고 강제 갱신 (매수/매도 모두)
                self._load_account_balance(force_refresh=True)
            
            # 주문 이력에 추가
            self.order_history.append(order_info)
            
            # 알림 발송
            if self.notifier:
                # order_info에 trade_info가 있으면 이를 포함하여 알림
                signal_data = {
                    'symbol': symbol,
                    'name': stock_name,  # 종목명 추가
                    'price': price,
                    'market': market,
                    'signals': [{
                        'type': action.value,
                        'strength': 'STRONG',
                        'confidence': 0.9,
                        'date': get_current_time().strftime("%Y-%m-%d")
                    }],
                    'trade_info': order_info.get('trade_info', {})
                }
                
                # 데이터 구조 확인 로그
                logger.info(f"알림 데이터 확인: symbol={signal_data['symbol']}, name={signal_data['name']}")
                
                self.notifier.send_signal_notification(signal_data)
            
            return order_info
            
        except Exception as e:
            logger.error(f"주문 실행 중 오류 발생: {e}")
            logger.debug(traceback.format_exc())
            
            # 실패 정보 업데이트
            order_info["status"] = OrderStatus.REJECTED.value
            order_info["error"] = str(e)
            self.order_history.append(order_info)
            
            return order_info
    
    def _send_order_notification(self, order_info):
        """주문 알림 발송"""
        try:
            if not self.notifier:
                return
                
            action = order_info.get("action")
            symbol = order_info.get("symbol")
            quantity = order_info.get("quantity")
            price = order_info.get("executed_price") or order_info.get("price")
            status = order_info.get("status")
            
            # 알림 메시지 구성
            if status == OrderStatus.EXECUTED.value:
                message = f"🔔 주문 체결: {action} {symbol} x {quantity}주\n"
                message += f"💰 체결가: {price:,.0f}원\n"
                message += f"⏱️ 시간: {get_current_time_str()}"
            else:
                message = f"⚠️ 주문 상태 알림: {symbol} {action}\n"
                message += f"상태: {status}\n"
                if "error" in order_info:
                    message += f"오류: {order_info['error']}\n"
                message += f"⏱️ 시간: {get_current_time_str()}"
            
            # 알림 발송
            self.notifier.send_message(message)
            
        except Exception as e:
            logger.error(f"알림 발송 중 오류 발생: {e}")
    
    def _check_stop_loss_take_profit(self):
        """손절매/익절 조건 확인 및 처리"""
        try:
            # positions이 딕셔너리인지 확인하고, 아닌 경우 적절히 변환
            if isinstance(self.positions, list):
                # 리스트를 딕셔너리로 변환 (symbol을 키로 사용)
                positions_dict = {}
                for position in self.positions:
                    if isinstance(position, dict) and 'symbol' in position:
                        positions_dict[position['symbol']] = position
                self.positions = positions_dict
                logger.info(f"포지션 데이터 구조를 리스트에서 딕셔너리로 변환했습니다. {len(self.positions)}개 항목")

            for symbol, position in list(self.positions.items()):
                # 보유 수량이 0이거나 평균단가가 0인 잘못된 데이터 건너뛰기
                quantity = position.get('quantity', 0)
                avg_price = position.get('avg_price', 0)
                if quantity <= 0 or avg_price <= 0:
                    logger.warning(f"{symbol} 포지션 데이터가 유효하지 않습니다. (수량: {quantity}, 평균단가: {avg_price}) - 손절매/익절 검사 건너뜀")
                    continue
                    
                # 현재가 확인 (0이면 건너뛰기)
                current_price = position.get('current_price', 0)
                if current_price <= 0:
                    logger.warning(f"{symbol} 현재가가 유효하지 않습니다. (현재가: {current_price}) - 손절매/익절 검사 건너뜀")
                    continue
                
                # 손익률 계산 (안전하게)
                try:
                    profit_loss_pct = ((current_price / avg_price) - 1) * 100
                    # 비정상적인 손실률 제한 (-99%까지만 허용)
                    if profit_loss_pct < -99:
                        logger.warning(f"{symbol} 계산된 손실률이 비정상적입니다: {profit_loss_pct:.2f}% (현재가: {current_price}, 평균단가: {avg_price}) - 손실률을 -99%로 제한")
                        profit_loss_pct = -99
                except Exception as e:
                    logger.error(f"{symbol} 손익률 계산 중 오류: {e}")
                    continue
                
                # 손절매 확인
                if profit_loss_pct <= -self.stop_loss_pct:
                    logger.info(f"{symbol} 손절매 조건 도달: {profit_loss_pct:.2f}%")
                    
                    # 매도 실행
                    self._execute_order(
                        symbol=symbol,
                        action=TradeAction.SELL,
                        quantity=position['quantity'],
                        market=position.get('market', 'KR')
                    )
                    
                    # 알림 발송
                    if self.notifier:
                        # 현재가, 평균단가 정보 추가
                        self.notifier.send_message(
                            f"🔴 손절매 실행: {symbol}\n"
                            f"손실: {profit_loss_pct:.2f}%\n"
                            f"현재가: {current_price:,}원, 평단가: {avg_price:,}원\n"
                            f"⏱️ 시간: {get_current_time_str()}"
                        )
                
                # 익절 확인
                elif profit_loss_pct >= self.take_profit_pct:
                    logger.info(f"{symbol} 익절 조건 도달: {profit_loss_pct:.2f}%")
                    
                    # 매도 실행
                    self._execute_order(
                        symbol=symbol,
                        action=TradeAction.SELL,
                        quantity=position['quantity'],
                        market=position.get('market', 'KR')
                    )
                    
                    # 알림 발송
                    if self.notifier:
                        # 현재가, 평균단가 정보 추가
                        self.notifier.send_message(
                            f"🟢 익절 실행: {symbol}\n"
                            f"이익: {profit_loss_pct:.2f}%\n"
                            f"현재가: {current_price:,}원, 평단가: {avg_price:,}원\n"
                            f"⏱️ 시간: {get_current_time_str()}"
                        )
        except Exception as e:
            logger.error(f"손절매/익절 확인 중 오류 발생: {e}")
            logger.error(traceback.format_exc())
    
    def process_trading_signal(self, signal_data):
        """
        트레이딩 신호 처리
        
        Args:
            signal_data: 트레이딩 신호 데이터
            
        Returns:
            dict: 처리 결과
        """
        try:
            symbol = signal_data.get('symbol')
            market = signal_data.get('market', 'KR')
            signal = signal_data.get('signal_data', {}).get('signal')
            strength = signal_data.get('signal_data', {}).get('strength', 'MODERATE')
            
            logger.info(f"{symbol} 신호 처리: {signal} ({strength})")
            
            # 포지션 확인
            has_position = symbol in self.positions
            
            # 시장 개장 여부 확인
            if not self._check_market_open(market):
                logger.warning(f"{market} 시장 개장 시간이 아닙니다. 신호 처리 건너뜁니다.")
                return {"status": "market_closed", "message": f"{market} 시장이 닫혀 있습니다."}
            
            # 매매 간격 확인
            current_time = time.time()
            if symbol in self.last_check_time:
                time_since_last_check = current_time - self.last_check_time[symbol]
                if time_since_last_check < self.trade_interval:
                    logger.debug(f"{symbol} 매매 간격 미달: {time_since_last_check:.0f}초 (필요: {self.trade_interval}초)")
                    return {"status": "interval_not_met", "message": f"매매 간격이 충분하지 않습니다."}
            
            # 매매 신호에 따라 처리
            result = {"status": "processed", "action": "none", "message": "신호 처리 완료"}
            
            if signal == "BUY" and not has_position:
                # 현재가 조회
                current_price = self.data_provider.get_current_price(symbol, market)
                if not current_price:
                    return {"status": "error", "message": f"{symbol} 가격 정보를 가져올 수 없습니다."}
                
                # 매수 수량 계산
                quantity = self._calculate_position_size(symbol, current_price, strength)
                
                if quantity <= 0:
                    return {"status": "insufficient_funds", "message": "매수 가능한 자금이 부족합니다."}
                
                # 매수 주문 실행
                order_result = self._execute_order(
                    symbol=symbol,
                    action=TradeAction.BUY,
                    quantity=quantity,
                    market=market
                )
                
                result["action"] = "buy"
                result["order_result"] = order_result
                
            elif signal == "SELL" and has_position:
                # 매도 주문 실행
                quantity = self.positions[symbol]['quantity']
                
                order_result = self._execute_order(
                    symbol=symbol,
                    action=TradeAction.SELL,
                    quantity=quantity,
                    market=market
                )
                
                result["action"] = "sell"
                result["order_result"] = order_result
                
            else:
                # HOLD 또는 다른 신호는 아무 조치 없음
                result["message"] = f"{symbol}: {signal} 신호, 조치 없음"
                
            # 마지막 확인 시간 업데이트
            self.last_check_time[symbol] = current_time
            
            return result
            
        except Exception as e:
            logger.error(f"트레이딩 신호 처리 중 오류 발생: {e}")
            logger.debug(traceback.format_exc())
            
            return {"status": "error", "message": f"신호 처리 중 오류: {str(e)}"}
    
    def run_trading_cycle(self):
        """전체 매매 사이클 실행"""
        try:
            logger.info("----- 새로운 매매 사이클 시작 -----")
            
            # 보유 포지션 로드 및 가치 업데이트
            self._load_positions()
            self._update_position_value()
            
            # 손절매/익절 확인
            self._check_stop_loss_take_profit()
            
            # 모니터링 종목 확인
            for item in self.watchlist:
                symbol = item.get('symbol')
                market = item.get('market', 'KR')
                
                try:
                    logger.info(f"{symbol} 분석 진행 중...")
                    
                    # 주가 데이터 로드
                    df = self.data_provider.get_historical_data(symbol, market)
                    if df is None or len(df) < 20:
                        logger.warning(f"{symbol} 데이터 불충분. 건너뜁니다.")
                        continue
                    
                    # 트레이딩 신호 요청
                    signal_data = self.strategy.get_trading_signal(df, symbol, market)
                    
                    # 신호 처리
                    result = self.process_trading_signal(signal_data)
                    logger.info(f"{symbol} 신호 처리 결과: {result['status']} - {result.get('message', '')}")
                    
                except Exception as e:
                    logger.error(f"{symbol} 처리 중 오류 발생: {e}")
                    continue
            
            logger.info("----- 매매 사이클 완료 -----")
            
        except Exception as e:
            logger.error(f"매매 사이클 실행 중 오류 발생: {e}")
            logger.debug(traceback.format_exc())
    
    def get_portfolio_summary(self):
        """포트폴리오 요약 정보 반환"""
        try:
            # 포지션 가치 업데이트
            self._update_position_value()
            
            # 총 자산 계산
            cash = self._get_available_cash()
            total_position_value = sum(p.get('current_value', 0) for p in self.positions.values())
            total_assets = cash + total_position_value
            
            # 수익률 계산
            total_profit_loss = sum(p.get('profit_loss', 0) for p in self.positions.values())
            total_profit_loss_pct = (total_profit_loss / (total_assets - total_profit_loss)) * 100 if (total_assets - total_profit_loss) > 0 else 0
            
            # 포트폴리오 요약
            summary = {
                "timestamp": get_current_time().isoformat(),
                "total_assets": total_assets,
                "cash": cash,
                "invested_amount": total_position_value,
                "cash_ratio": (cash / total_assets) * 100 if total_assets > 0 else 0,
                "total_profit_loss": total_profit_loss,
                "total_profit_loss_pct": total_profit_loss_pct,
                "positions": list(self.positions.values()),
                "position_count": len(self.positions),
                "trade_stats": self.trade_stats
            }
            
            return summary
        
        except Exception as e:
            logger.error(f"포트폴리오 요약 생성 중 오류 발생: {e}")
            return {
                "error": str(e),
                "timestamp": get_current_time().isoformat()
            }
            
    def save_trading_state(self, file_path='trading_state.json'):
        """트레이딩 상태 저장"""
        try:
            state = {
                "timestamp": datetime.datetime.now().isoformat(),
                "positions": self.positions,
                "order_history": self.order_history[-50:] if len(self.order_history) > 50 else self.order_history,
                "trade_stats": self.trade_stats,
                "last_check_time": {k: v for k, v in self.last_check_time.items()},
                "simulation_mode": self.simulation_mode
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2, default=str)
                
            logger.info(f"트레이딩 상태 저장 완료: {file_path}")
            
        except Exception as e:
            logger.error(f"트레이딩 상태 저장 중 오류 발생: {e}")
            
    def load_trading_state(self, file_path='trading_state.json'):
        """트레이딩 상태 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
                
            self.positions = state.get('positions', {})
            self.order_history = state.get('order_history', [])
            self.trade_stats = state.get('trade_stats', self.trade_stats)
            self.last_check_time = {k: float(v) for k, v in state.get('last_check_time', {}).items()}
            
            logger.info(f"트레이딩 상태 로드 완료: {file_path}")
            return True
            
        except FileNotFoundError:
            logger.warning(f"트레이딩 상태 파일이 없습니다: {file_path}")
            return False
        except Exception as e:
            logger.error(f"트레이딩 상태 로드 중 오류 발생: {e}")
            return False
    
    def is_trading_allowed(self, symbol, market="KR"):
        """
        특정 종목의 거래 허용 여부 확인
        
        Args:
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            bool: 거래 허용 여부
        """
        try:
            # 모의투자에서의 시장 제한 확인
            if (self.simulation_mode or not self.broker.real_trading):
                # 모의투자에서 국내주식만 거래 가능하도록 제한
                if hasattr(self.config, 'VIRTUAL_TRADING_KR_ONLY') and self.config.VIRTUAL_TRADING_KR_ONLY:
                    if market != "KR":
                        logger.warning(f"{market} 시장은 모의투자에서 거래할 수 없습니다. 실전투자 모드에서만 해외주식 거래가 가능합니다.")
                        return False
                # 허용된 시장 확인 (설정 파일에서 정의)
                elif hasattr(self.config, 'ALLOWED_VIRTUAL_MARKETS') and market not in self.config.ALLOWED_VIRTUAL_MARKETS:
                    logger.warning(f"{market} 시장은 모의투자에서 허용되지 않습니다. 허용된 시장: {self.config.ALLOWED_VIRTUAL_MARKETS}")
                    return False
                
            # 시뮬레이션 모드에서는 거래 허용
            if self.simulation_mode:
                return True
                
            # 기본 상태 - 자동 매매가 실행 중인지 확인
            if not hasattr(self, 'is_running') or not self.is_running:
                logger.warning(f"자동 매매가 활성화되지 않았습니다.")
                return False
                
            # 시장 개장 여부 확인
            if not self._check_market_open(market):
                logger.warning(f"{market} 시장이 개장되지 않아 거래를 허용하지 않습니다. {symbol}")
                return False
                
            # 차단된 종목인지 확인
            if hasattr(self.config, 'BLOCKED_SYMBOLS') and symbol in self.config.BLOCKED_SYMBOLS:
                logger.warning(f"{symbol}은 거래 차단 목록에 있습니다.")
                return False
                
            # 거래 가능 시간대 확인 (설정된 경우)
            if hasattr(self.config, 'TRADING_HOURS'):
                trading_hours = self.config.TRADING_HOURS.get(market)
                if trading_hours:
                    current_time = get_current_time().time()
                    start_time = parse_time(trading_hours.get('start', '09:00')).time()
                    end_time = parse_time(trading_hours.get('end', '15:30')).time()
                    
                    if not (start_time <= current_time <= end_time):
                        logger.warning(f"현재 시간이 거래 가능 시간대를 벗어났습니다. {current_time}")
                        return False
            
            # 거래 횟수 제한 확인
            if hasattr(self.config, 'MAX_DAILY_TRADES'):
                max_daily_trades = self.config.MAX_DAILY_TRADES
                today_trades = len([order for order in self.order_history 
                                    if order.get('symbol') == symbol and
                                    order.get('timestamp', '').startswith(get_current_time().strftime("%Y-%m-%d"))])
                                    
                if today_trades >= max_daily_trades:
                    logger.warning(f"{symbol}에 대한 일일 최대 거래 횟수에 도달했습니다. ({today_trades}/{max_daily_trades})")
                    return False
                    
            # 자본금 제한 확인 (설정된 경우)
            if hasattr(self.config, 'MIN_CAPITAL_REQUIRED'):
                min_capital = self.config.MIN_CAPITAL_REQUIRED
                available_cash = self._get_available_cash()
                
                if available_cash < min_capital:
                    logger.warning(f"사용 가능한 자본금이 최소 요구 금액보다 적습니다. ({available_cash:,.0f} < {min_capital:,.0f})")
                    return False
            
            # 기타 모든 조건 통과
            return True
            
        except Exception as e:
            logger.error(f"거래 허용 여부 확인 중 오류 발생: {e}")
            # 오류 발생 시 안전하게 거래 거부
            return False
    
    def process_signals(self, signals):
        """
        매매 신호 처리
        
        Args:
            signals: 매매 신호 데이터
            
        Returns:
            dict: 처리 결과
        """
        if not signals.get('signals'):
            logger.info("처리할 매매 신호가 없습니다.")
            return None
            
        symbol = signals.get('symbol')
        market = signals.get('market', 'KR')
        
        # 해당 종목의 거래가 허용되는지 확인
        if not self.is_trading_allowed(symbol, market):
            logger.warning(f"{symbol}에 대한 거래가 현재 허용되지 않습니다.")
            return None
        
        results = []
        # 신호 처리 (중요도나 신뢰도 순으로 정렬)
        sorted_signals = sorted(
            signals['signals'], 
            key=lambda x: x.get('confidence', 0), 
            reverse=True
        )
        
        for signal_data in sorted_signals:
            signal_type = signal_data.get('type')
            signal_date = signal_data.get('date')
            signal_price = signal_data.get('price')
            signal_confidence = signal_data.get('confidence', 5.0)  # 기본값 5.0 (중간 신뢰도)
            
            # 신뢰도가 낮은 신호는 무시
            min_confidence = getattr(self.config, 'MIN_SIGNAL_CONFIDENCE', 5.0)
            if signal_confidence < min_confidence:
                logger.info(f"{symbol} {signal_type} 신호 무시: 신뢰도가 낮음 ({signal_confidence} < {min_confidence})")
                continue
                
            try:
                # 신호 유형에 따른 처리
                if signal_type == "BUY":
                    # 이미 포지션을 가지고 있는지 확인
                    has_position = symbol in self.positions
                    
                    if not has_position:
                        # 매수 신호 처리 (TradeAction 열거형 사용)
                        signal_dict = {
                            'symbol': symbol,
                            'signal_data': {
                                'signal': TradeAction.BUY.value,
                                'strength': 'STRONG' if signal_confidence > 7.5 else (
                                    'MODERATE' if signal_confidence > 5.0 else 'WEAK'
                                ),
                                'price': signal_price,
                                'date': signal_date
                            },
                            'market': market,
                            'price': signal_price
                        }
                        
                        result = self.process_trading_signal(signal_dict)
                        if result['status'] == 'processed' and result['action'] == 'buy':
                            logger.info(f"{symbol} 매수 신호 처리 완료")
                        
                        results.append(result)
                    else:
                        logger.info(f"{symbol}에 대한 포지션이 이미 있어 매수 신호를 무시합니다.")
                
                elif signal_type == "SELL":
                    # 포지션을 가지고 있는지 확인
                    has_position = symbol in self.positions
                    
                    if has_position:
                        # 매도 신호 처리
                        signal_dict = {
                            'symbol': symbol,
                            'signal_data': {
                                'signal': TradeAction.SELL.value,
                                'strength': 'STRONG' if signal_confidence > 7.5 else (
                                    'MODERATE' if signal_confidence > 5.0 else 'WEAK'
                                ),
                                'price': signal_price,
                                'date': signal_date
                            },
                            'market': market,
                            'price': signal_price
                        }
                        
                        result = self.process_trading_signal(signal_dict)
                        if result['status'] == 'processed' and result['action'] == 'sell':
                            logger.info(f"{symbol} 매도 신호 처리 완료")
                            
                        results.append(result)
                    else:
                        logger.info(f"{symbol}에 대한 포지션이 없어 매도 신호를 무시합니다.")
                
            except Exception as e:
                logger.error(f"{symbol} {signal_type} 신호 처리 중 오류: {e}")
                results.append({
                    "status": "error",
                    "message": f"{signal_type} 신호 처리 중 오류: {str(e)}"
                })
                
        return results
    
    def start_trading_session(self):
        """자동 매매 세션 시작"""
        logger.info("자동 매매 세션 시작")
        self.is_running = True
        
        # 포지션 로드
        self._load_positions()
        
        return True
        
    def stop_trading_session(self):
        """자동 매매 세션 종료"""
        logger.info("자동 매매 세션 종료")
        self.is_running = False
        
        return True
    
    def get_trading_summary(self):
        """
        거래 요약 정보 반환
        
        Returns:
            dict: 거래 요약 정보
        """
        try:
            # 요약 정보 딕셔리
            summary = {
                "오늘의거래": {},
                "계좌정보": {},
                "보유종목": []
            }
            
            # 오늘 날짜 가져오기
            today = get_current_time().strftime("%Y-%m-%d")
            
            # 오늘의 거래 카운트
            for order in self.order_history:
                if order.get('timestamp', '').startswith(today):
                    symbol = order.get('symbol')
                    action = order.get('action').lower()
                    
                    if symbol not in summary["오늘의거래"]:
                        summary["오늘의거래"][symbol] = {"buy": 0, "sell": 0}
                    
                    if action in summary["오늘의거래"][symbol]:
                        summary["오늘의거래"][symbol][action] += 1
            
            # 계좌 정보 (시뮬레이션 모드에 따라 다름)
            if self.simulation_mode:
                # 총 포지션 가치 계산
                total_position_value = sum(p.get('current_value', 0) for p in self.positions.values())
                
                # 예수금 계산
                cash = self.initial_capital - total_position_value
                
                summary["계좌정보"] = {
                    "예수금": cash,
                    "총자산": self.initial_capital,
                    "평가손익": sum(p.get('profit_loss', 0) for p in self.positions.values()),
                    "손익률": (sum(p.get('profit_loss', 0) for p in self.positions.values()) / self.initial_capital) * 100 if self.initial_capital > 0 else 0
                }
            else:
                # 실제 브로커 API에서 계좌 정보 가져오기
                try:
                    account_info = self.broker.get_account_info()
                    summary["계좌정보"] = account_info
                except:
                    logger.error("계좌 정보 조회 실패")
            
            # 보유 종목 정보
            for symbol, position in self.positions.items():
                # 종목 이름 가져오기 (있는 경우)
                stock_name = symbol
                if hasattr(self.config, 'STOCK_NAMES') and symbol in self.config.STOCK_NAMES:
                    stock_name = self.config.STOCK_NAMES[symbol]
                
                summary["보유종목"].append({
                    "종목코드": symbol,
                    "종목명": stock_name,
                    "보유수량": position.get('quantity', 0),
                    "평균단가": position.get('avg_price', 0),
                    "현재가": position.get('current_price', 0),
                    "평가금액": position.get('current_value', 0),
                    "평가손익": position.get('profit_loss', 0),
                    "손익률": position.get('profit_loss_pct', 0)
                })
                
            return summary
            
        except Exception as e:
            logger.error(f"거래 요약 정보 생성 중 오류: {e}")
            return {
                "오늘의거래": {},
                "계좌정보": {},
                "보유종목": []
            }
    
    def place_order(self, code, order_type, quantity, price, order_type_name=None):
        """
        주식 주문 실행
        
        Args:
            code (str): 종목코드
            order_type (str): 주문유형 (buy, sell)
            quantity (int): 주문수량
            price (float): 주문가격
            order_type_name (str, optional): 주문유형명 (지정가, 시장가 등)
            
        Returns:
            dict: 주문 결과
        """
        logger.info(f"주문 시작: {code} {order_type} {quantity}주 {price}원")
        
        try:
            # 현재 잔고 확인
            pre_balance = self.broker_api.get_balance()
            available_cash = pre_balance.get('주문가능금액', 0)
            
            logger.info(f"주문 전 계좌 잔고: {available_cash:,}원")
            
            # 매수 시 주문가능금액 확인
            if order_type == 'buy':
                required_amount = quantity * price
                if available_cash < required_amount:
                    logger.warning(f"주문가능금액 부족: 필요 {required_amount:,}원, 보유 {available_cash:,}원")
                    return {"success": False, "message": "주문가능금액 부족", "error_code": "INSUFFICIENT_BALANCE"}
            
            # 주문 실행
            order_result = self.broker_api.place_order(code, order_type, quantity, price, order_type_name)
            
            if order_result.get('success', False):
                order_no = order_result.get('order_no', '')
                logger.info(f"주문 성공: {order_no}")
                
                # 주문 성공 후 잔고 갱신을 위한 대기
                time.sleep(2)
                
                # 주문 후 강제로 잔고 갱신 (최대 3회 시도)
                max_attempts = 3
                for attempt in range(1, max_attempts + 1):
                    logger.info(f"주문 후 잔고 갱신 시도 ({attempt}/{max_attempts})")
                    time.sleep(1 * attempt)  # 시도마다 대기 시간 증가
                    
                    # 강제로 최신 잔고 정보 가져오기
                    post_balance = self.broker_api.get_balance(force_refresh=True)
                    updated_cash = post_balance.get('주문가능금액', 0)
                    
                    # 잔고가 변경되었는지 확인
                    if order_type == 'buy' and updated_cash != available_cash:
                        logger.info(f"잔고 갱신 성공: {updated_cash:,}원 (이전: {available_cash:,}원)")
                        break
                    elif attempt == max_attempts:
                        logger.warning(f"잔고 갱신 실패: 여전히 {updated_cash:,}원 (API 지연 또는 캐싱 문제)")
                
                return order_result
            else:
                error_message = order_result.get('message', '알 수 없는 오류')
                error_code = order_result.get('error_code', 'UNKNOWN_ERROR')
                logger.error(f"주문 실패: {error_message} (코드: {error_code})")
                return order_result
                
        except Exception as e:
            logger.error(f"주문 처리 중 오류 발생: {e}")
            logger.error(traceback.format_exc())
            return {"success": False, "message": str(e), "error_code": "EXCEPTION"}