"""
실시간 주식 매매 처리 모듈

이 모듈은 실시간 데이터를 기반으로 빠른 단타 매매와 급등주 매매를 수행합니다.
디비나 캐시 파일에 의존하지 않고 실시간 시장 데이터를 분석하여 거래 결정을 내립니다.
"""

import logging
import time
import json
import threading
import datetime
import pandas as pd
import numpy as np
from src.utils.time_utils import get_current_time, get_current_time_str, is_market_open

# 로거 설정
logger = logging.getLogger(__name__)

class RealtimeTrader:
    """실시간 트레이딩을 위한 클래스"""
    
    def __init__(self, config, broker, data_provider, notifier=None):
        """
        RealtimeTrader 클래스 초기화
        
        Args:
            config: 설정값을 담고 있는 객체
            broker: 주문 실행을 위한 브로커 객체
            data_provider: 주가 데이터 제공자
            notifier: 알림 발송 객체 (선택사항)
        """
        self.config = config
        self.broker = broker
        self.data_provider = data_provider
        self.notifier = notifier
        
        # 실시간 거래 관련 설정
        self.realtime_trading_enabled = getattr(config, 'REALTIME_TRADING_ENABLED', True)
        self.realtime_only_mode = getattr(config, 'REALTIME_ONLY_MODE', True)  # 실시간 전용 모드 사용 여부
        self.simulation_mode = getattr(config, 'SIMULATION_MODE', False)
        self.scan_interval_seconds = getattr(config, 'REALTIME_SCAN_INTERVAL_SECONDS', 30)
        self.price_surge_threshold = getattr(config, 'PRICE_SURGE_THRESHOLD_PERCENT', 3.0)
        self.volume_surge_threshold = getattr(config, 'VOLUME_SURGE_THRESHOLD_PERCENT', 200.0)
        self.min_trade_amount = getattr(config, 'REALTIME_MIN_TRADE_AMOUNT', 500000)
        self.max_trade_amount = getattr(config, 'REALTIME_MAX_TRADE_AMOUNT', 2000000)
        self.stop_loss_percent = getattr(config, 'REALTIME_STOP_LOSS_PERCENT', 3.0)
        self.take_profit_percent = getattr(config, 'REALTIME_TAKE_PROFIT_PERCENT', 5.0)
        self.max_holding_time_minutes = getattr(config, 'REALTIME_MAX_HOLDING_MINUTES', 60)
        
        # GPT 분석 사용 여부
        self.use_gpt_analysis = getattr(config, 'REALTIME_USE_GPT_ANALYSIS', True)
        self.gpt_confidence_threshold = getattr(config, 'REALTIME_GPT_CONFIDENCE_THRESHOLD', 0.8)
        
        # 내부 상태 변수
        self.is_running = False
        self.thread = None
        self.realtime_targets = {}  # {symbol: {price, volume, first_detected, last_updated, ...}}
        self.current_positions = {}  # {symbol: {entry_price, quantity, entry_time, ...}}
        self.surge_history = []  # 급등 감지 히스토리
        self.trade_history = []  # 매매 히스토리
        
        # 연결된 GPTAutoTrader 객체 (나중에 설정됨)
        self.gpt_auto_trader = None
        
        logger.info(f"RealtimeTrader 초기화 완료 (시뮬레이션 모드: {'활성화' if self.simulation_mode else '비활성화'}, "
                  f"GPT 분석: {'사용' if self.use_gpt_analysis else '미사용'}, "
                  f"실시간 전용 모드: {'활성화' if self.realtime_only_mode else '비활성화'})")
                  
    def set_gpt_auto_trader(self, gpt_auto_trader):
        """GPTAutoTrader 객체 연결"""
        self.gpt_auto_trader = gpt_auto_trader
        logger.info("GPTAutoTrader 객체가 RealtimeTrader에 연결되었습니다.")
    
    def start(self):
        """실시간 트레이딩 시작"""
        if not self.realtime_trading_enabled:
            logger.warning("실시간 트레이딩 기능이 비활성화되어 있습니다.")
            return False
            
        if self.is_running:
            logger.warning("실시간 트레이딩이 이미 실행 중입니다.")
            return True
            
        self.is_running = True
        self.thread = threading.Thread(target=self._trading_loop, name="RealtimeTrader")
        self.thread.daemon = True
        self.thread.start()
        
        msg = "실시간 트레이딩 시스템이 시작되었습니다."
        if self.realtime_only_mode:
            msg += " (실시간 전용 모드)"
        logger.info(msg)
        
        if self.notifier:
            self.notifier.send_message(f"✅ {msg}")
        
        return True
    
    def stop(self):
        """실시간 트레이딩 중지"""
        if not self.is_running:
            logger.warning("실시간 트레이딩이 실행 중이 아닙니다.")
            return False
            
        self.is_running = False
        if self.thread and self.thread.is_alive():
            logger.info("실시간 트레이딩 스레드 종료를 기다립니다...")
            self.thread.join(timeout=5)
            
        logger.info("실시간 트레이딩 시스템이 중지되었습니다.")
        if self.notifier:
            self.notifier.send_message("🛑 실시간 트레이딩 시스템이 중지되었습니다.")
            
        return True
    
    def add_realtime_target(self, symbol, data):
        """
        실시간 감시 대상 종목 추가
        
        Args:
            symbol (str): 종목코드
            data (dict): 종목 관련 데이터 (price, volume, strategy 등)
        """
        if symbol in self.realtime_targets:
            # 이미 존재하는 경우 업데이트
            self.realtime_targets[symbol].update(data)
            self.realtime_targets[symbol]['last_updated'] = get_current_time()
            logger.info(f"실시간 감시 종목 업데이트: {symbol}")
        else:
            # 새로운 종목 추가
            data['first_detected'] = get_current_time()
            data['last_updated'] = get_current_time()
            self.realtime_targets[symbol] = data
            logger.info(f"실시간 감시 종목 추가: {symbol}")
    
    def _trading_loop(self):
        """실시간 트레이딩 메인 루프"""
        logger.info("실시간 트레이딩 루프 시작")
        
        while self.is_running:
            try:
                # 거래 시간인지 확인
                if not is_market_open("KR"):
                    logger.info("현재 거래 시간이 아닙니다. 5분 후에 다시 확인합니다.")
                    for _ in range(5 * 60):  # 5분 대기 (1초 단위로 중단 체크)
                        if not self.is_running:
                            break
                        time.sleep(1)
                    continue
                
                # 1. 현재 포지션 업데이트
                self._update_positions()
                
                # 2. 기존 포지션 관리 (손절, 익절 등)
                self._manage_existing_positions()
                
                # 3. 실시간 시장 스캔으로 급등주 감지
                self._scan_market_for_surges()
                
                # 4. 감지된 종목 분석 및 거래 실행
                self._analyze_and_trade_surges()
                
                # 다음 스캔까지 대기
                logger.debug(f"실시간 트레이딩 사이클 완료. {self.scan_interval_seconds}초 후에 다시 스캔합니다.")
                for _ in range(self.scan_interval_seconds):
                    if not self.is_running:
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"실시간 트레이딩 루프 중 오류 발생: {e}")
                time.sleep(60)  # 오류 발생 시 1분 대기
    
    def _update_positions(self):
        """현재 보유 중인 포지션 정보 업데이트"""
        try:
            positions = self.broker.get_positions() if self.broker else {}
            
            # 포지션 정보 형식 변환 및 저장
            current_positions = {}
            
            # 리스트 형식 처리
            if isinstance(positions, list):
                for position in positions:
                    # 종목코드 확인
                    symbol = position.get("종목코드", position.get("symbol", ""))
                    if not symbol:
                        continue
                        
                    # 수량 및 평균단가 추출
                    quantity = int(position.get("보유수량", position.get("quantity", 0)))
                    avg_price = float(position.get("평균단가", position.get("avg_price", 0)))
                    
                    if quantity > 0:
                        current_positions[symbol] = {
                            'symbol': symbol,
                            'name': position.get("종목명", position.get("name", symbol)),
                            'quantity': quantity,
                            'avg_price': avg_price,
                            'current_price': float(position.get("현재가", position.get("current_price", 0))),
                            'entry_time': position.get("entry_time", self.current_positions.get(symbol, {}).get("entry_time", get_current_time().isoformat()))
                        }
            
            # 딕셔너리 형식 처리
            elif isinstance(positions, dict) and "positions" in positions:
                for symbol, position in positions["positions"].items():
                    quantity = int(position.get("quantity", 0))
                    if quantity > 0:
                        current_positions[symbol] = {
                            'symbol': symbol,
                            'name': position.get("name", symbol),
                            'quantity': quantity,
                            'avg_price': float(position.get("avg_price", 0)),
                            'current_price': float(position.get("current_price", 0)),
                            'entry_time': position.get("entry_time", self.current_positions.get(symbol, {}).get("entry_time", get_current_time().isoformat()))
                        }
            
            self.current_positions = current_positions
            logger.debug(f"현재 포지션 업데이트 완료: {len(self.current_positions)}개")
            return True
            
        except Exception as e:
            logger.error(f"포지션 업데이트 중 오류 발생: {e}")
            return False
    
    def _manage_existing_positions(self):
        """기존 포지션 관리 (손절, 익절, 보유 시간 초과 등)"""
        if not self.current_positions:
            return
            
        positions_to_sell = []
        now = get_current_time()
        
        for symbol, position in self.current_positions.items():
            try:
                # 현재 가격 조회
                current_price = self.data_provider.get_current_price(symbol, "KR")
                if not current_price:
                    logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                    continue
                
                avg_price = position.get('avg_price', 0)
                if avg_price <= 0:
                    continue
                
                # 손익률 계산
                profit_pct = ((current_price / avg_price) - 1) * 100
                
                # 손절 조건 확인 (손실이 설정된 비율보다 큰 경우)
                if profit_pct <= -self.stop_loss_percent:
                    logger.info(f"{symbol} 손절 조건 충족: 손실률 {profit_pct:.2f}% (기준: {-self.stop_loss_percent}%)")
                    positions_to_sell.append((symbol, "손절", profit_pct))
                    continue
                
                # 익절 조건 확인 (이익이 설정된 비율보다 큰 경우)
                if profit_pct >= self.take_profit_percent:
                    logger.info(f"{symbol} 익절 조건 충족: 이익률 {profit_pct:.2f}% (기준: {self.take_profit_percent}%)")
                    positions_to_sell.append((symbol, "익절", profit_pct))
                    continue
                
                # 보유 시간 초과 확인
                entry_time = None
                if position.get('entry_time'):
                    try:
                        entry_time = datetime.datetime.fromisoformat(position['entry_time'])
                    except (ValueError, TypeError):
                        pass
                
                if entry_time:
                    holding_minutes = (now - entry_time).total_seconds() / 60
                    if holding_minutes >= self.max_holding_time_minutes:
                        logger.info(f"{symbol} 최대 보유 시간 초과: {holding_minutes:.1f}분 (기준: {self.max_holding_time_minutes}분)")
                        positions_to_sell.append((symbol, "시간초과", profit_pct))
                
            except Exception as e:
                logger.error(f"{symbol} 포지션 관리 중 오류: {e}")
        
        # 매도 조건에 해당하는 종목 처리
        for symbol, reason, profit_pct in positions_to_sell:
            self._execute_sell(symbol, reason, profit_pct)
    
    def _scan_market_for_surges(self):
        """시장 스캔을 통해 급등주 감지"""
        try:
            # 관심 종목 목록 (코스피, 코스닥 상위 종목, 관심 종목 등)
            # 실제로는 관심 종목 목록을 DB나 설정에서 가져와야 함
            target_symbols = self._get_watchlist_symbols()
            if not target_symbols:
                logger.warning("감시할 종목 목록이 비어 있습니다.")
                return
                
            logger.debug(f"급등주 스캔 시작: {len(target_symbols)}개 종목")
            
            # 급등 종목 감지
            for symbol in target_symbols:
                # 이미 보유 중인 종목은 건너뜀
                if symbol in self.current_positions:
                    continue
                
                # 이미 감시 중인 종목은 업데이트만 수행
                if symbol in self.realtime_targets:
                    self._update_target_info(symbol)
                    continue
                
                # 급등 조건 확인
                if self._check_surge_conditions(symbol):
                    name = self._get_stock_name(symbol)
                    current_price = self.data_provider.get_current_price(symbol, "KR")
                    volume = self._get_current_volume(symbol)
                    
                    # 신규 감시 대상 추가
                    self.add_realtime_target(symbol, {
                        'name': name,
                        'price': current_price,
                        'volume': volume,
                        'strategy': 'surge_detection',
                        'target_price': current_price * (1 + self.take_profit_percent / 100),
                        'stop_loss': current_price * (1 - self.stop_loss_percent / 100),
                        'surge_detected': True,
                        'analysis': '급등 감지'
                    })
                    
                    # 히스토리에 기록
                    self.surge_history.append({
                        'timestamp': get_current_time().isoformat(),
                        'symbol': symbol,
                        'name': name,
                        'price': current_price,
                        'volume': volume,
                        'strategy': 'surge_detection'
                    })
                    
                    logger.info(f"새로운 급등주 감지: {name}({symbol}), 가격: {current_price:,.0f}원, 거래량: {volume:,}")
            
            return True
            
        except Exception as e:
            logger.error(f"급등주 스캔 중 오류 발생: {e}")
            return False
    
    def _get_watchlist_symbols(self):
        """감시할 종목 목록 가져오기"""
        # 실제로는 DB나 설정에서 가져와야 함
        # 예시로 몇 개의 종목 코드를 반환
        return ['005930', '000660', '035420', '035720', '051910', '207940']
    
    def _get_stock_name(self, symbol):
        """종목 코드로 종목명 조회"""
        try:
            if hasattr(self.broker, 'get_stock_name'):
                return self.broker.get_stock_name(symbol) or symbol
        except:
            pass
        return symbol
    
    def _get_current_volume(self, symbol):
        """현재 거래량 조회"""
        try:
            # 일중 거래량 조회 (데이터 제공자에 따라 구현 방식이 다를 수 있음)
            if hasattr(self.data_provider, 'get_current_volume'):
                return self.data_provider.get_current_volume(symbol, "KR")
        except:
            pass
        return 0
    
    def _check_surge_conditions(self, symbol):
        """
        급등 조건 확인
        - 가격이 기준 대비 일정 비율 이상 상승
        - 거래량이 기준 대비 일정 배수 이상 증가
        """
        try:
            # 현재 가격 조회
            current_price = self.data_provider.get_current_price(symbol, "KR")
            if not current_price:
                return False
                
            # 최근 데이터 조회
            df = self.data_provider.get_historical_data(symbol, "KR", period="1d", interval="5m")
            if df is None or len(df) < 3:
                return False
                
            # 가격 변화율 계산 (최근 5분 vs 이전 5분)
            recent_price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2]
            price_change = ((recent_price / prev_price) - 1) * 100
            
            # 거래량 변화 계산
            recent_volume = df['Volume'].iloc[-1]
            avg_volume = df['Volume'].iloc[:-1].mean()
            volume_ratio = (recent_volume / avg_volume if avg_volume > 0 else 0) * 100
            
            # 급등 조건 확인
            is_price_surge = price_change > self.price_surge_threshold
            is_volume_surge = volume_ratio > self.volume_surge_threshold
            
            # 디버깅 로그
            logger.debug(f"{symbol} 급등 검사: 가격변화 {price_change:.2f}%, 거래량변화 {volume_ratio:.2f}%")
            
            # 둘 다 충족해야 급등으로 판단
            return is_price_surge and is_volume_surge
            
        except Exception as e:
            logger.error(f"{symbol} 급등 확인 중 오류: {e}")
            return False
    
    def _update_target_info(self, symbol):
        """감시 중인 종목 정보 업데이트"""
        try:
            if symbol not in self.realtime_targets:
                return
                
            current_price = self.data_provider.get_current_price(symbol, "KR")
            if not current_price:
                return
                
            self.realtime_targets[symbol].update({
                'price': current_price,
                'last_updated': get_current_time()
            })
            
            # 현재 거래량 업데이트 (가능한 경우)
            volume = self._get_current_volume(symbol)
            if volume > 0:
                self.realtime_targets[symbol]['volume'] = volume
                
        except Exception as e:
            logger.error(f"{symbol} 타겟 정보 업데이트 중 오류: {e}")
    
    def _analyze_and_trade_surges(self):
        """감지된 급등주 분석 및 거래 실행"""
        if not self.realtime_targets:
            return
            
        now = get_current_time()
        targets_to_remove = []
        
        for symbol, data in self.realtime_targets.items():
            try:
                # 이미 보유 중인 종목은 건너뜀
                if symbol in self.current_positions:
                    continue
                    
                # 최초 감지 후 일정 시간이 지났는지 확인
                first_detected = data.get('first_detected')
                if not first_detected:
                    continue
                    
                # 감지 후 너무 오래 지난 종목은 제외 (30분 이상)
                minutes_since_detection = (now - first_detected).total_seconds() / 60
                if minutes_since_detection > 30:
                    targets_to_remove.append(symbol)
                    logger.info(f"{symbol} 감시 목록에서 제거: 감지 후 {minutes_since_detection:.1f}분 경과")
                    continue
                
                # 현재 가격 확인
                current_price = self.data_provider.get_current_price(symbol, "KR")
                if not current_price:
                    logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                    continue
                
                # GPT 분석 요청 (설정된 경우)
                gpt_insights = None
                if self.use_gpt_analysis and self.gpt_auto_trader:
                    # 히스토리 데이터 조회
                    stock_data = self.data_provider.get_historical_data(symbol, "KR", period="1d", interval="5m")
                    if stock_data is not None and len(stock_data) > 0:
                        # GPT 분석 요청
                        gpt_insights = self.gpt_auto_trader.get_gpt_insights_for_realtime_trading(
                            symbol, stock_data, current_price
                        )
                
                # 매매 결정
                should_buy = self._should_buy_surge(symbol, data, gpt_insights)
                
                if should_buy:
                    # 매수 주문 실행
                    success = self._execute_buy(symbol, data, gpt_insights)
                    if success:
                        # 매수 성공 시 감시 목록에서 제거
                        targets_to_remove.append(symbol)
                
            except Exception as e:
                logger.error(f"{symbol} 분석 및 거래 중 오류: {e}")
        
        # 처리 완료된 종목은 감시 목록에서 제거
        for symbol in targets_to_remove:
            if symbol in self.realtime_targets:
                del self.realtime_targets[symbol]
    
    def _should_buy_surge(self, symbol, data, gpt_insights=None):
        """
        급등주 매수 여부 결정
        
        Args:
            symbol: 종목 코드
            data: 종목 관련 데이터
            gpt_insights: GPT 분석 결과 (있는 경우)
            
        Returns:
            bool: 매수 여부
        """
        # 기본 검증
        if not self.is_running or symbol in self.current_positions:
            return False
            
        # 계좌 잔고 확인
        balance_info = self.broker.get_balance() if self.broker else {"주문가능금액": 0}
        available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
        
        if available_cash < self.min_trade_amount:
            logger.info(f"주문가능금액({available_cash:,.0f}원)이 최소 거래 금액보다 적습니다.")
            return False
        
        # 현재가 확인
        current_price = data.get('price') or self.data_provider.get_current_price(symbol, "KR")
        if not current_price or current_price <= 0:
            return False
            
        # 기술적 매매 신호 확인
        technical_buy_signal = True  # 기본적으로 매수 신호로 가정
        
        # GPT 분석 결과가 있으면 확인
        if gpt_insights:
            action = gpt_insights.get('action', 'HOLD')
            confidence = gpt_insights.get('confidence', 0)
            
            logger.info(f"{symbol} GPT 분석 결과: 행동={action}, 신뢰도={confidence:.2f}")
            
            # GPT가 매수를 추천하고 신뢰도가 높은 경우에만 매수
            if self.use_gpt_analysis:
                if action != 'BUY' or confidence < self.gpt_confidence_threshold:
                    logger.info(f"{symbol} GPT 분석 결과로 인해 매수하지 않음 (행동={action}, 신뢰도={confidence:.2f})")
                    return False
        
        # 모든 조건 통과 시 매수 결정
        return True
    
    def _execute_buy(self, symbol, data, gpt_insights=None):
        """
        급등주 매수 주문 실행
        
        Args:
            symbol: 종목 코드
            data: 종목 관련 데이터
            gpt_insights: GPT 분석 결과 (있는 경우)
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance() if self.broker else {"주문가능금액": 0}
            available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
            
            # 현재가 가져오기
            current_price = data.get('price') or self.data_provider.get_current_price(symbol, "KR")
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 종목명 가져오기
            name = data.get('name') or self._get_stock_name(symbol)
            
            # 투자금액 결정 (최대 투자 금액 이내에서)
            investment_amount = min(self.max_trade_amount, available_cash)
            
            # 매수 수량 계산
            quantity = int(investment_amount / current_price)
            
            # 1주 이상인 경우만 거래
            if quantity < 1:
                logger.warning(f"{symbol} 매수 수량이 1보다 작아 주문하지 않습니다.")
                return False
                
            # 예상 주문 금액
            expected_total = quantity * current_price
            
            # 매수 이유 구성
            reason = data.get('analysis') or "급등 감지"
            if gpt_insights:
                gpt_reason = gpt_insights.get('analysis_summary')
                if gpt_reason:
                    reason += f" + GPT 분석: {gpt_reason}"
            
            logger.info(f"{symbol} 매수 실행: {quantity}주 × {current_price:,.0f}원 = {expected_total:,.0f}원 (예상)")
            
            # 시뮬레이션 모드 확인
            if self.simulation_mode:
                logger.info(f"{symbol} 매수 주문 시뮬레이션 완료")
                
                # 매매 기록에 추가
                trade_record = {
                    'timestamp': get_current_time().isoformat(),
                    'symbol': symbol,
                    'name': name,
                    'action': 'BUY',
                    'quantity': quantity,
                    'price': current_price,
                    'total_amount': expected_total,
                    'reason': reason,
                    'simulation': True
                }
                self.trade_history.append(trade_record)
                
                # 알림 전송
                if self.notifier:
                    self.notifier.send_message(f"🚀 급등주 매수 시뮬레이션: {name}({symbol})\n"
                                              f"• 수량: {quantity:,}주\n"
                                              f"• 단가: {current_price:,}원\n"
                                              f"• 총액: {expected_total:,}원\n"
                                              f"• 사유: {reason}\n"
                                              f"• 모드: 시뮬레이션 (실제 거래 없음)")
                
                return True
            else:
                # 실제 매수 주문
                order_result = self.broker.place_order(
                    symbol=symbol,
                    order_type="buy",
                    quantity=quantity,
                    price=current_price
                )
                
                if order_result and order_result.get('success'):
                    logger.info(f"{symbol} 실제 매수 주문 완료: 주문번호 {order_result.get('order_id', 'N/A')}")
                    
                    # 매매 기록에 추가
                    trade_record = {
                        'timestamp': get_current_time().isoformat(),
                        'symbol': symbol,
                        'name': name,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': current_price,
                        'total_amount': expected_total,
                        'reason': reason,
                        'order_id': order_result.get('order_id', ''),
                        'simulation': False
                    }
                    self.trade_history.append(trade_record)
                    
                    # API 반영 대기
                    logger.info("주문 체결 후 API 반영 대기 중...")
                    time.sleep(5)
                    
                    # 포지션 업데이트
                    self._update_positions()
                    
                    # 알림 전송
                    if self.notifier:
                        self.notifier.send_message(f"🚀 급등주 매수 완료: {name}({symbol})\n"
                                                  f"• 수량: {quantity:,}주\n"
                                                  f"• 단가: {current_price:,}원\n"
                                                  f"• 총액: {expected_total:,}원\n"
                                                  f"• 사유: {reason}")
                    
                    return True
                else:
                    error = order_result.get('error', '알 수 없는 오류') if order_result else '주문 실패'
                    logger.error(f"{symbol} 매수 주문 실패: {error}")
                    return False
        
        except Exception as e:
            logger.error(f"{symbol} 매수 실행 중 오류 발생: {e}")
            return False
    
    def _execute_sell(self, symbol, reason, profit_pct=None):
        """
        보유 종목 매도 주문 실행
        
        Args:
            symbol: 종목 코드
            reason: 매도 사유 (손절, 익절 등)
            profit_pct: 손익률 (있는 경우)
        """
        try:
            if symbol not in self.current_positions:
                logger.warning(f"{symbol} 매도 시도 중 오류: 보유하고 있지 않은 종목")
                return False
                
            position = self.current_positions[symbol]
            quantity = position.get('quantity', 0)
            avg_price = position.get('avg_price', 0)
            name = position.get('name', symbol)
            
            if quantity <= 0:
                logger.warning(f"{symbol} 매도할 수량이 없습니다.")
                return False
                
            # 현재가 조회
            current_price = self.data_provider.get_current_price(symbol, "KR")
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 손익 계산 (정보 제공용)
            if profit_pct is None and avg_price > 0:
                profit_pct = ((current_price / avg_price) - 1) * 100
                
            logger.info(f"{symbol} 매도 실행: {quantity}주 × {current_price:,.0f}원 = {quantity * current_price:,.0f}원, 손익률: {profit_pct:.2f}%")
            
            # 시뮬레이션 모드 확인
            if self.simulation_mode:
                logger.info(f"{symbol} 매도 주문 시뮬레이션 완료 (사유: {reason})")
                
                # 매매 기록에 추가
                trade_record = {
                    'timestamp': get_current_time().isoformat(),
                    'symbol': symbol,
                    'name': name,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': current_price,
                    'total_amount': quantity * current_price,
                    'profit_pct': profit_pct,
                    'reason': reason,
                    'simulation': True
                }
                self.trade_history.append(trade_record)
                
                # 알림 전송
                if self.notifier:
                    emoji = '🔴' if profit_pct < 0 else '🔵' if profit_pct > 0 else '⚪'
                    self.notifier.send_message(f"{emoji} 매도 시뮬레이션: {name}({symbol})\n"
                                              f"• 수량: {quantity:,}주\n"
                                              f"• 단가: {current_price:,}원\n"
                                              f"• 총액: {quantity * current_price:,}원\n"
                                              f"• 손익률: {profit_pct:.2f}%\n"
                                              f"• 사유: {reason}\n"
                                              f"• 모드: 시뮬레이션 (실제 거래 없음)")
                
                # 시뮬레이션에서도 포지션 정보 업데이트
                del self.current_positions[symbol]
                return True
            else:
                # 실제 매도 주문
                order_result = self.broker.place_order(
                    symbol=symbol,
                    order_type="sell",
                    quantity=quantity,
                    price=current_price
                )
                
                if order_result and order_result.get('success'):
                    logger.info(f"{symbol} 실제 매도 주문 완료: 주문번호 {order_result.get('order_id', 'N/A')}")
                    
                    # 매매 기록에 추가
                    trade_record = {
                        'timestamp': get_current_time().isoformat(),
                        'symbol': symbol,
                        'name': name,
                        'action': 'SELL',
                        'quantity': quantity,
                        'price': current_price,
                        'total_amount': quantity * current_price,
                        'profit_pct': profit_pct,
                        'reason': reason,
                        'order_id': order_result.get('order_id', ''),
                        'simulation': False
                    }
                    self.trade_history.append(trade_record)
                    
                    # API 반영 대기
                    logger.info("매도 주문 체결 후 API 반영 대기 중...")
                    time.sleep(5)
                    
                    # 포지션 업데이트
                    self._update_positions()
                    
                    # 알림 전송
                    if self.notifier:
                        emoji = '🔴' if profit_pct < 0 else '🔵' if profit_pct > 0 else '⚪'
                        self.notifier.send_message(f"{emoji} 매도 완료: {name}({symbol})\n"
                                                  f"• 수량: {quantity:,}주\n"
                                                  f"• 단가: {current_price:,}원\n"
                                                  f"• 총액: {quantity * current_price:,}원\n"
                                                  f"• 손익률: {profit_pct:.2f}%\n"
                                                  f"• 사유: {reason}")
                    
                    return True
                else:
                    error = order_result.get('error', '알 수 없는 오류') if order_result else '주문 실패'
                    logger.error(f"{symbol} 매도 주문 실패: {error}")
                    return False
        
        except Exception as e:
            logger.error(f"{symbol} 매도 실행 중 오류 발생: {e}")
            return False