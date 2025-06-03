"""
GPT 기반 자동 매매 모듈

이 모듈은 GPT가 추천한 종목을 증권사 API를 통해 자동으로 매매합니다.
GPT의 종목 분석과 추천을 바탕으로 매수/매도 결정을 내립니다.
"""

import os
import logging
import time
import datetime
from typing import Dict, List, Any, Optional, Union
import pandas as pd
import json
import numpy as np  # numpy 추가
import threading

from src.ai_analysis.stock_selector import StockSelector
from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy
from src.trading.auto_trader import AutoTrader, TradeAction, OrderType
from src.trading.realtime_trader import RealtimeTrader
from src.utils.time_utils import get_current_time, get_current_time_str, is_market_open

# 로깅 설정
logger = logging.getLogger('GPTAutoTrader')

class GPTAutoTrader:
    """GPT 기반 자동 매매 클래스"""
    
    def __init__(self, config, broker, data_provider, notifier=None):
        """
        초기화 함수
        
        Args:
            config: 설정 객체
            broker: 증권사 API 연동 객체
            data_provider: 주가 데이터 제공자
            notifier: 알림 발송 객체 (선택적)
        """
        self.config = config
        self.broker = broker
        self.data_provider = data_provider
        self.notifier = notifier
        
        # GPT 종목 선정기 초기화
        self.stock_selector = StockSelector(config)
        
        # GPT 트레이딩 전략 초기화 (신규 추가)
        self.gpt_strategy = GPTTradingStrategy(config)
        
        # AutoTrader 초기화 (실제 매매 실행용)
        self.auto_trader = AutoTrader(config, broker, data_provider, None, notifier)
        
        # RealtimeTrader 초기화 (실시간 매매용) (신규 추가)
        self.realtime_trader = RealtimeTrader(config, broker, data_provider, notifier)
        
        # 설정값 로드
        self.gpt_trading_enabled = getattr(config, 'GPT_AUTO_TRADING', True)
        self.selection_interval = getattr(config, 'GPT_STOCK_SELECTION_INTERVAL', 24)  # 시간
        self.max_positions = getattr(config, 'GPT_TRADING_MAX_POSITIONS', 5)
        self.conf_threshold = getattr(config, 'GPT_TRADING_CONF_THRESHOLD', 0.7)
        self.max_investment_per_stock = getattr(config, 'GPT_MAX_INVESTMENT_PER_STOCK', 5000000)
        self.strategy = getattr(config, 'GPT_STRATEGY', 'balanced')
        self.monitoring_interval = getattr(config, 'GPT_TRADING_MONITOR_INTERVAL', 30)  # 분
        self.use_dynamic_selection = getattr(config, 'GPT_USE_DYNAMIC_SELECTION', False)  # 동적 종목 선정 사용 여부
        
        # 기술적 지표 최적화 설정 로드
        self.optimize_technical_indicators = getattr(config, 'GPT_OPTIMIZE_TECHNICAL_INDICATORS', True)
        self.technical_optimization_interval = getattr(config, 'GPT_TECHNICAL_OPTIMIZATION_INTERVAL', 168)  # 시간 (기본 1주일)
        self.last_technical_optimization_time = None
        
        # 완전 자동화 모드 설정 (신규 추가)
        self.fully_autonomous_mode = getattr(config, 'GPT_FULLY_AUTONOMOUS_MODE', True)
        self.autonomous_trading_interval = getattr(config, 'GPT_AUTONOMOUS_TRADING_INTERVAL', 5)  # 분 단위
        self.realtime_market_scan_interval = getattr(config, 'GPT_REALTIME_MARKET_SCAN_INTERVAL', 15)  # 분 단위
        self.autonomous_max_positions = getattr(config, 'GPT_AUTONOMOUS_MAX_POSITIONS', 7)
        self.autonomous_max_trade_amount = getattr(config, 'GPT_AUTONOMOUS_MAX_TRADE_AMOUNT', 1000000)  # 자동 매매 최대 금액
        
        # 고급 설정
        self.aggressive_mode = getattr(config, 'GPT_AGGRESSIVE_MODE', False)  # 공격적 매매 모드
        self.auto_restart_enabled = getattr(config, 'GPT_AUTO_RESTART_ENABLED', True)  # 자동 재시작 기능
        self.risk_management_enabled = getattr(config, 'GPT_RISK_MANAGEMENT_ENABLED', True)  # 위험 관리 기능
        
        # 실시간 전용 모드 설정
        self.realtime_only_mode = getattr(config, 'REALTIME_ONLY_MODE', True)  # 실시간 전용 모드
        self.use_database = getattr(config, 'USE_DATABASE', False)  # 데이터베이스 사용 여부
        
        # 상태 변수
        self.is_running = False
        self.last_selection_time = None
        self.gpt_selections = {
            'KR': [],
            'US': []
        }
        
        # 보유 종목 및 매매 기록
        self.holdings = {}  # {symbol: {quantity, avg_price, market, entry_time, ...}}
        self.trade_history = []  # 매매 기록
        
        # 자동 거래 스레드 (신규 추가)
        self.autonomous_thread = None
        self.autonomous_thread_running = False
        self.realtime_scan_thread = None
        self.realtime_scan_thread_running = False
        
        # 자동 매매 실적 통계 (신규 추가)
        self.autonomous_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'total_loss': 0.0,
            'start_time': None,
            'last_updated': None
        }
        
        logger.info(f"GPT 자동 매매 시스템 초기화 완료 (동적 종목 선별: {'활성화' if self.use_dynamic_selection else '비활성화'}, "
                  f"완전자율거래: {'활성화' if self.fully_autonomous_mode else '비활성화'}, "
                  f"공격적모드: {'활성화' if self.aggressive_mode else '비활성화'}, "
                  f"실시간 전용 모드: {'활성화' if self.realtime_only_mode else '비활성화'}, "
                  f"데이터베이스: {'사용' if self.use_database else '미사용'})")
                  
        # RealtimeTrader와 GPTAutoTrader 연결
        self.realtime_trader.set_gpt_auto_trader(self)
        
    def is_trading_time(self, market="KR"):
        """
        현재 시간이 거래 시간인지 확인
        
        Args:
            market (str): 시장 코드 ('KR' 또는 'US')
            
        Returns:
            bool: 거래 시간이면 True, 아니면 False
        """
        # 미국 시장 우선순위 설정 확인
        us_market_priority = getattr(self.config, 'US_MARKET_PRIORITY', True)
        
        # 양쪽 시장 상태 확인
        kr_market_open = is_market_open("KR")
        us_market_open = is_market_open("US")
        
        # 시장 우선순위에 따른 처리
        if us_market_priority:
            # 미국 시장이 열려있는 경우 미국 시장만 활성화
            if us_market_open:
                # 미국 시장이 요청된 경우 참, 한국 시장이 요청된 경우 거짓 반환
                return market == "US"
            else:
                # 미국 시장이 닫혀있는 경우에만 한국 시장 상태 반환
                if market == "KR":
                    return kr_market_open
                else:
                    return False
        else:
            # 미국 시장 우선순위가 아닌 경우 각 시장 상태 그대로 반환
            return is_market_open(market)
    
    def start(self):
        """GPT 기반 자동 매매 시작"""
        logger.info("GPT 자동 매매 시작 시도 중...")
        
        if self.is_running:
            logger.warning("GPT 자동 매매가 이미 실행 중입니다.")
            return True  # 이미 실행 중이면 성공으로 처리
            
        if not self.gpt_trading_enabled:
            logger.warning("GPT 자동 매매 기능이 비활성화되어 있습니다. config.py에서 GPT_AUTO_TRADING을 True로 설정하세요.")
            return False
        
        # 디버그: 설정 상태 확인
        logger.info(f"GPT 자동 매매 설정 상태: enabled={self.gpt_trading_enabled}, max_positions={self.max_positions}, interval={self.monitoring_interval}")
        
        # OpenAI API 키 유효성 확인 - 중요: 실패하더라도 계속 진행
        try:
            is_api_key_valid = self.stock_selector.is_api_key_valid()
            if not is_api_key_valid:
                logger.warning("OpenAI API 키가 유효하지 않습니다. 캐시된 종목 목록을 사용합니다.")
                if self.notifier:
                    self.notifier.send_message("⚠️ OpenAI API 키 오류: GPT 종목 선정에 캐시된 데이터를 사용합니다.")
        except Exception as e:
            logger.error(f"OpenAI API 키 검증 중 오류 발생: {e}. 캐시된 종목 목록을 사용합니다.")
        
        # 시뮬레이션 모드 설정 (명시적으로 읽어온 다음 로그에 기록)
        simulation_mode = getattr(self.config, 'SIMULATION_MODE', False)
        logger.info(f"시뮬레이션 모드 설정: {simulation_mode}")
        
        # 브로커 객체 확인 및 시뮬레이션 모드 활성화
        if not self.broker:
            logger.warning("증권사 API 객체(broker)가 없습니다.")
            if simulation_mode:
                logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
            else:
                logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                return False
                
        try:
            # API 테스트는 시뮬레이션 모드가 아니고 브로커가 있을 때만 수행
            if self.broker and not simulation_mode:
                # 1. API 연결 테스트
                try:
                    connect_result = self.broker.connect()
                    if not connect_result:
                        logger.error("증권사 API 연결에 실패했습니다.")
                        if self.notifier:
                            self.notifier.send_message("⚠️ 증권사 API 연결 실패")
                        
                        if getattr(self.config, 'SIMULATION_MODE', False):
                            logger.info("config.py에 SIMULATION_MODE=True로 설정되어 있어 시뮬레이션 모드로 실행합니다.")
                            simulation_mode = True
                        else:
                            logger.error("시뮬레이션 모드가 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                            return False
                except Exception as e:
                    logger.error(f"증권사 API 연결 중 오류 발생: {e}")
                    if getattr(self.config, 'SIMULATION_MODE', False):
                        logger.info("config.py에 SIMULATION_MODE=True로 설정되어 있어 시뮬레이션 모드로 실행합니다.")
                        simulation_mode = True
                    else:
                        logger.error("시뮬레이션 모드가 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                if not simulation_mode:
                    logger.info("증권사 API 연결 성공")
                    
                    # 2. 로그인 테스트
                    try:
                        login_result = self.broker.login()
                        if not login_result:
                            logger.error("증권사 API 로그인에 실패했습니다.")
                            if self.notifier:
                                self.notifier.send_message("⚠️ 증권사 API 로그인 실패")
                            
                            if getattr(self.config, 'SIMULATION_MODE', False):
                                logger.info("config.py에 SIMULATION_MODE=True로 설정되어 있어 시뮬레이션 모드로 실행합니다.")
                                simulation_mode = True
                            else:
                                logger.error("시뮬레이션 모드가 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                                return False
                    except Exception as e:
                        logger.error(f"증권사 API 로그인 중 오류 발생: {e}")
                        if getattr(self.config, 'SIMULATION_MODE', False):
                            logger.info("config.py에 SIMULATION_MODE=True로 설정되어 있어 시뮬레이션 모드로 실행합니다.")
                            simulation_mode = True
                        else:
                            logger.error("시뮬레이션 모드가 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                            return False
                    
                    if not simulation_mode:
                        logger.info("증권사 API 로그인 성공")
            else:
                # 브로커가 없거나 시뮬레이션 모드인 경우
                if not self.broker:
                    logger.info("브로커 객체가 없어 시뮬레이션 모드로 실행합니다.")
                    simulation_mode = True
                else:
                    logger.info("시뮬레이션 모드로 설정되어 API 테스트를 건너뜁니다.")
        except Exception as e:
            logger.error(f"증권사 API 테스트 중 예외 발생: {e}")
            if self.notifier:
                self.notifier.send_message(f"⚠️ 증권사 API 테스트 중 오류 발생: {str(e)}")
                
            # 시뮬레이션 모드 확인 및 활성화
            if getattr(self.config, 'SIMULATION_MODE', False):
                logger.info("config.py에 SIMULATION_MODE=True로 설정되어 있어 시뮬레이션 모드로 실행합니다.")
                simulation_mode = True
            else:
                logger.error("시뮬레이션 모드가 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                return False
        
        # 테스트 결과 알림
        if self.notifier and not simulation_mode:
            try:
                balance = self.broker.get_balance() if self.broker else {"예수금": 0}
                positions = self.broker.get_positions() if self.broker else {}
                current_price = self.data_provider.get_current_price("005930", "KR") if self.data_provider else 0
                
                message = f"✅ 증권사 API 테스트 완료 ({self.broker.get_trading_mode() if self.broker else '시뮬레이션'})\n"
                message += f"• 계좌 잔고: {balance.get('예수금', 0):,}원\n"
                message += f"• 보유종목 수: {len(positions)}개\n"
                message += f"• 삼성전자 현재가: {current_price:,}원\n"
                self.notifier.send_message(message)
            except Exception as e:
                logger.error(f"API 테스트 결과 알림 생성 중 오류 발생: {e}")
        
        # 시뮬레이션 모드 설정
        if simulation_mode:
            # AutoTrader에 시뮬레이션 모드 설정
            if self.auto_trader:
                self.auto_trader.simulation_mode = True
                logger.info("AutoTrader를 시뮬레이션 모드로 설정했습니다.")
            
            # RealtimeTrader에도 시뮬레이션 모드 설정 (신규 추가)
            if self.realtime_trader:
                self.realtime_trader.simulation_mode = True
                logger.info("RealtimeTrader를 시뮬레이션 모드로 설정했습니다.")
            
            # 시뮬레이션 모드 알림
            if self.notifier:
                self.notifier.send_message("🔧 GPT 자동 매매가 시뮬레이션 모드로 실행됩니다.")
        
        self.is_running = True
        logger.info("GPT 자동 매매 시스템을 시작합니다.")
        
        # AutoTrader 시작
        if self.auto_trader:
            self.auto_trader.start_trading_session()
            logger.info(f"AutoTrader 시작 상태: {self.auto_trader.is_running}")
        
        # RealtimeTrader 시작 (신규 추가)
        if self.realtime_trader:
            self.realtime_trader.start()
            logger.info(f"RealtimeTrader 시작 상태: {self.realtime_trader.is_running}")
        
        # 초기 종목 선정 실행
        try:
            self._select_stocks()
            logger.info("초기 종목 선정 완료")
        except Exception as e:
            logger.error(f"초기 종목 선정 중 오류 발생: {e}")
            # 오류가 발생해도 계속 진행
        
        # 포지션 로드
        try:
            self._load_current_holdings()
        except Exception as e:
            logger.error(f"보유 종목 로드 중 오류 발생: {e}")
            # 오류가 발생해도 계속 진행
            
        # 완전 자율 거래 스레드 시작 (신규 추가)
        if self.fully_autonomous_mode:
            self._start_autonomous_thread()
            self._start_realtime_scan_thread()
            logger.info("GPT 완전 자율 거래 스레드 시작")
        
        # 자동 매매 통계 초기화 (신규 추가)
        self.autonomous_stats['start_time'] = get_current_time()
        self.autonomous_stats['last_updated'] = get_current_time()
        
        # 알림 전송
        if self.notifier:
            message = f"🤖 GPT 자동 매매 시스템 시작 ({get_current_time_str()})\n\n"
            message += f"• 전략: {self.strategy}\n"
            message += f"• 최대 포지션 수: {self.max_positions}개\n"
            message += f"• 종목당 최대 투자금: {self.max_investment_per_stock:,}원\n"
            message += f"• 종목 선정 주기: {self.selection_interval}시간\n"
            message += f"• 모니터링 간격: {self.monitoring_interval}분\n"
            
            # 추가된 설정 정보 알림 (신규 추가)
            if self.fully_autonomous_mode:
                message += f"\n🚀 완전 자율 거래 모드: 활성화\n"
                message += f"• 자율 거래 간격: {self.autonomous_trading_interval}분\n"
                message += f"• 실시간 시장 스캔: {self.realtime_market_scan_interval}분\n"
                message += f"• 자율 최대 종목 수: {self.autonomous_max_positions}개\n"
                message += f"• 자율 거래당 최대 금액: {self.autonomous_max_trade_amount:,}원\n"
                message += f"• 공격적 매매 모드: {'활성화' if self.aggressive_mode else '비활성화'}\n"
            
            message += f"• 모드: {'시뮬레이션' if simulation_mode else '실거래'}\n"
            self.notifier.send_message(message)
            
        logger.info("GPT 자동 매매 시스템이 성공적으로 시작되었습니다.")
        return True
        
    def stop(self):
        """GPT 기반 자동 매매 중지"""
        if not self.is_running:
            logger.warning("GPT 자동 매매가 실행 중이 아닙니다.")
            return
            
        self.is_running = False
        logger.info("GPT 자동 매매 시스템을 중지합니다.")
        
        # AutoTrader 중지
        if self.auto_trader:
            self.auto_trader.stop_trading_session()
            logger.info("AutoTrader 중지됨")
            
        # RealtimeTrader 중지 (신규 추가)
        if self.realtime_trader:
            self.realtime_trader.stop()
            logger.info("RealtimeTrader 중지됨")
            
        # 완전 자율 거래 스레드 중지 (신규 추가)
        self._stop_autonomous_thread()
        self._stop_realtime_scan_thread()
        
        # 자동화 통계 요약 (신규 추가)
        stats_summary = self._get_autonomous_stats_summary()
        logger.info(f"자동화 매매 통계 요약: {stats_summary}")
        
        # 알림 전송
        if self.notifier:
            message = f"🛑 GPT 자동 매매 시스템 중지 ({get_current_time_str()})"
            
            # 완전 자율 모드였다면 통계 추가 (신규 추가)
            if self.fully_autonomous_mode:
                message += f"\n\n📊 자율 매매 통계:\n"
                message += f"• 총 거래 횟수: {self.autonomous_stats['total_trades']}회\n"
                message += f"• 승률: {self._calculate_win_rate():.1f}%\n"
                message += f"• 총 수익: {self.autonomous_stats['total_profit']:,.0f}원\n"
                message += f"• 총 손실: {self.autonomous_stats['total_loss']:,.0f}원\n"
            
            self.notifier.send_message(message)
            
        return True
    
    def _start_autonomous_thread(self):
        """완전 자율 거래 스레드 시작 (신규 추가)"""
        if self.autonomous_thread is not None and self.autonomous_thread_running:
            logger.warning("자율 거래 스레드가 이미 실행 중입니다.")
            return False
            
        self.autonomous_thread_running = True
        self.autonomous_thread = threading.Thread(target=self._autonomous_trading_loop, name="GPT_Autonomous_Trading")
        self.autonomous_thread.daemon = True
        self.autonomous_thread.start()
        logger.info("GPT 자율 거래 스레드 시작됨")
        return True
        
    def _stop_autonomous_thread(self):
        """완전 자율 거래 스레드 중지 (신규 추가)"""
        self.autonomous_thread_running = False
        if self.autonomous_thread is not None:
            try:
                if self.autonomous_thread.is_alive():
                    logger.info("자율 거래 스레드 종료 대기 중...")
                    self.autonomous_thread.join(timeout=5)
                    logger.info("자율 거래 스레드 종료됨")
            except Exception as e:
                logger.error(f"자율 거래 스레드 종료 중 오류: {e}")
                
        self.autonomous_thread = None
        return True
        
    def _start_realtime_scan_thread(self):
        """실시간 시장 스캔 스레드 시작 (신규 추가)"""
        if self.realtime_scan_thread is not None and self.realtime_scan_thread_running:
            logger.warning("실시간 시장 스캔 스레드가 이미 실행 중입니다.")
            return False
            
        self.realtime_scan_thread_running = True
        self.realtime_scan_thread = threading.Thread(target=self._realtime_market_scan_loop, name="GPT_Market_Scanner")
        self.realtime_scan_thread.daemon = True
        self.realtime_scan_thread.start()
        logger.info("GPT 실시간 시장 스캔 스레드 시작됨")
        return True
        
    def _stop_realtime_scan_thread(self):
        """실시간 시장 스캔 스레드 중지 (신규 추가)"""
        self.realtime_scan_thread_running = False
        if self.realtime_scan_thread is not None:
            try:
                if self.realtime_scan_thread.is_alive():
                    logger.info("실시간 시장 스캔 스레드 종료 대기 중...")
                    self.realtime_scan_thread.join(timeout=5)
                    logger.info("실시간 시장 스캔 스레드 종료됨")
            except Exception as e:
                logger.error(f"실시간 시장 스캔 스레드 종료 중 오류: {e}")
                
        self.realtime_scan_thread = None
        return True
        
    def _autonomous_trading_loop(self):
        """GPT 완전 자율 거래 루프 실행 (신규 추가)"""
        logger.info("GPT 자율 거래 루프 시작")
        
        while self.autonomous_thread_running and self.is_running:
            try:
                # 거래 시간인지 확인
                if not is_market_open("KR"):
                    logger.info("현재 거래 시간이 아닙니다. 10분 후에 다시 확인합니다.")
                    for _ in range(10 * 60):  # 10분 대기 (1초 단위로 중단 체크)
                        if not self.autonomous_thread_running:
                            break
                        time.sleep(1)
                    continue
                
                logger.info("자율 거래 사이클 시작")
                
                # 현재 보유 포지션 업데이트
                self._load_current_holdings()
                
                # 계좌 잔고 확인
                balance_info = self.broker.get_balance()
                available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
                logger.info(f"계좌 잔고: {available_cash:,.0f}원")
                
                # 시장 데이터 가져오기 (관심종목 + 현재 보유종목)
                market_data = self._get_market_data()
                
                # GPT 자율적인 매매 결정
                decisions = self.gpt_strategy.fully_autonomous_decision(
                    market_data=market_data,
                    available_cash=available_cash,
                    current_positions=self.holdings
                )
                
                # 매도 결정 실행
                for sell_decision in decisions.get('sell_decisions', []):
                    symbol = sell_decision.get('symbol')
                    reason = sell_decision.get('reason', 'GPT 자율 매도 결정')
                    logger.info(f"자율 매도 결정: {symbol}, 이유: {reason}")
                    
                    try:
                        if self._execute_sell(symbol):
                            # 매도 성공 시 통계 업데이트
                            profit_pct = sell_decision.get('profit_loss_pct', 0)
                            amount = sell_decision.get('quantity', 0) * sell_decision.get('price', 0)
                            
                            if profit_pct > 0:
                                self.autonomous_stats['winning_trades'] += 1
                                self.autonomous_stats['total_profit'] += amount * (profit_pct / 100)
                            else:
                                self.autonomous_stats['losing_trades'] += 1
                                self.autonomous_stats['total_loss'] += abs(amount * (profit_pct / 100))
                                
                            self.autonomous_stats['total_trades'] += 1
                            self.autonomous_stats['last_updated'] = get_current_time()
                    except Exception as e:
                        logger.error(f"{symbol} 자율 매도 실행 중 오류: {e}")
                
                # 매수 결정 실행
                for buy_decision in decisions.get('buy_decisions', []):
                    symbol = buy_decision.get('symbol')
                    reason = buy_decision.get('reason', 'GPT 자율 매수 결정')
                    logger.info(f"자율 매수 결정: {symbol}, 이유: {reason}")
                    
                    try:
                        if self._execute_buy_decision(buy_decision):
                            # 매수 성공 시 통계 업데이트
                            self.autonomous_stats['total_trades'] += 1
                            self.autonomous_stats['last_updated'] = get_current_time()
                    except Exception as e:
                        logger.error(f"{symbol} 자율 매수 실행 중 오류: {e}")
                
                # 다음 사이클까지 대기
                logger.info(f"자율 거래 사이클 완료. {self.autonomous_trading_interval}분 후에 다시 실행합니다.")
                for _ in range(self.autonomous_trading_interval * 60):  # 분 단위를 초 단위로 변환
                    if not self.autonomous_thread_running:
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"자율 거래 루프 중 오류 발생: {e}")
                time.sleep(60)  # 오류 발생 시 1분 대기 후 재시도
    
    def _realtime_market_scan_loop(self):
        """실시간 시장 스캔 루프 실행 (신규 추가)"""
        logger.info("실시간 시장 스캔 루프 시작")
        
        while self.realtime_scan_thread_running and self.is_running:
            try:
                # 거래 시간인지 확인
                if not is_market_open("KR"):
                    logger.info("현재 거래 시간이 아닙니다. 실시간 시장 스캔은 5분 후에 다시 확인합니다.")
                    for _ in range(5 * 60):  # 5분 대기 (1초 단위로 중단 체크)
                        if not self.realtime_scan_thread_running:
                            break
                        time.sleep(1)
                    continue
                
                logger.info("실시간 시장 스캔 시작")
                
                # 시장 데이터 수집
                self._scan_market_opportunities()
                
                # 다음 스캔까지 대기
                logger.info(f"실시간 시장 스캔 완료. {self.realtime_market_scan_interval}분 후에 다시 실행합니다.")
                for _ in range(self.realtime_market_scan_interval * 60):  # 분 단위를 초 단위로 변환
                    if not self.realtime_scan_thread_running:
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"실시간 시장 스캔 루프 중 오류 발생: {e}")
                time.sleep(60)  # 오류 발생 시 1분 대기 후 재시도
    
    def _scan_market_opportunities(self):
        """실시간 시장 기회 스캔 (단타매매 및 급등주 분석을 GPT에게 전적으로 맡김)"""
        try:
            logger.info("GPT 기반 실시간 단타매매 및 급등주 기회 스캔 시작")
            
            # 한국 시장과 미국 시장의 상태 확인
            kr_market_open = is_market_open("KR")
            us_market_open = is_market_open("US")
            
            logger.info(f"시장 상태: 한국 시장 {('개장' if kr_market_open else '폐장')}, 미국 시장 {('개장' if us_market_open else '폐장')}")
            
            # 한국 시장이 열려있는 경우만 한국 종목 분석
            kr_symbols = []
            if kr_market_open:
                kr_symbols = self.gpt_strategy.get_day_trading_candidates('KR', max_count=10)
                logger.info(f"GPT 추천 한국 단타매매 종목: {len(kr_symbols)}개")
            else:
                logger.info("한국 시장이 폐장 중이므로 한국 종목 분석은 건너뜁니다.")
            
            # 미국 시장이 열려있는 경우만 미국 종목 분석
            us_symbols = []
            us_stock_trading_enabled = getattr(self.config, 'US_STOCK_TRADING_ENABLED', False)
            if us_market_open and us_stock_trading_enabled:
                us_symbols = self.gpt_strategy.get_day_trading_candidates('US', max_count=5)
                logger.info(f"GPT 추천 미국 단타매매 종목: {len(us_symbols)}개")
            else:
                if not us_market_open:
                    logger.info("미국 시장이 폐장 중이므로 미국 종목 분석은 건너뜁니다.")
                elif not us_stock_trading_enabled:
                    logger.info("미국 주식 거래가 비활성화되어 있어 미국 종목 분석은 건너뜁니다.")
                
            # 종목 목록 합치기
            all_symbols = [(symbol, 'KR') for symbol in kr_symbols] + [(symbol, 'US') for symbol in us_symbols]
            
            # 모멘텀/급등주 분석 결과 저장용
            momentum_stocks = []
            
            # 종목별로 GPT 분석 요청 (디비/캐시 사용 안함)
            for symbol, market in all_symbols:
                # 해당 시장이 열려있는지 다시 확인
                if (market == 'KR' and not kr_market_open) or (market == 'US' and not us_market_open):
                    logger.info(f"{symbol} ({market}) - 해당 시장이 폐장 중이므로 분석을 건너뜁니다.")
                    continue
                    
                try:
                    # 데이터는 바로 데이터 제공자에게서 가져옴 (캐시/디비 사용 안함)
                    stock_data = self.data_provider.get_stock_data(symbol, days=5)
                    current_price = self.data_provider.get_current_price(symbol, market)
                    
                    if stock_data is None or stock_data.empty or current_price is None:
                        logger.warning(f"{symbol} 데이터 가져오기 실패, 건너뜁니다.")
                        continue
                    
                    # GPT에 직접 분석 요청 (캐시 사용하지 않음)
                    analysis = self.gpt_strategy.analyze_momentum_stock(
                        symbol=symbol, 
                        stock_data=stock_data,
                        current_price=current_price,
                        use_cache=False  # 캐시 사용 안함
                    )
                    
                    # 분석 결과에서 모멘텀 점수와 단타매매 적합도 추출
                    if analysis:
                        momentum_score = analysis.get('momentum_score', 0)
                        day_trading_score = analysis.get('day_trading_score', 0)
                        
                        # 스코어가 충분히 높은 종목만 추가 (모멘텀 또는 단타 스코어가 70점 이상)
                        if momentum_score > 70 or day_trading_score > 70:
                            # 종목명 가져오기
                            stock_info = self.data_provider.get_stock_info(symbol, market)
                            name = stock_info.get('name', symbol) if stock_info else symbol
                            
                            analysis['symbol'] = symbol
                            analysis['name'] = name
                            analysis['price'] = current_price
                            analysis['market'] = market
                            
                            # 모멘텀/단타 점수 중 더 높은 점수 기준으로 정렬하기 위한 최종 점수 계산
                            final_score = max(momentum_score, day_trading_score)
                            momentum_stocks.append((symbol, final_score, analysis))
                            
                            # 로그로 분석 결과 요약 기록
                            logger.info(f"{symbol} 분석 완료: 모멘텀 {momentum_score}, 단타 {day_trading_score}")
                
                except Exception as e:
                    logger.error(f"{symbol} 분석 중 오류: {e}")
                    continue
            
            # 스코어 기준 정렬 및 상위 종목 추출
            momentum_stocks.sort(key=lambda x: x[1], reverse=True)
            top_momentum = momentum_stocks[:5]  # 상위 5개 종목
            
            if not top_momentum:
                logger.info("GPT 분석 결과 현재 급등주/단타 기회가 없습니다.")
                return False
                
            # 결과 처리 및 알림
            logger.info(f"GPT 분석으로 {len(top_momentum)}개의 급등주/단타 기회를 발견했습니다")
            
            # 메시지 구성
            message = f"📈 GPT 실시간 단타/급등주 감지 ({get_current_time_str()})\n\n"
            
            for symbol, score, analysis in top_momentum:
                name = analysis.get('name', symbol)
                price = analysis.get('price', 0)
                target = analysis.get('target_price', price * 1.05)
                stop_loss = analysis.get('stop_loss', price * 0.95)
                momentum_score = analysis.get('momentum_score', 0)
                day_trading_score = analysis.get('day_trading_score', 0)
                strategy = analysis.get('strategy', '분석 없음')
                duration = analysis.get('momentum_duration', '확인 불가')
                market_type = '🇰🇷 한국' if analysis.get('market') == 'KR' else '🇺🇸 미국'
                
                message += f"• [{market_type}] {name} ({symbol})\n"
                message += f"  현재가: {price:,.0f}원 / 목표가: {target:,.0f}원\n"
                message += f"  손절가: {stop_loss:,.0f}원\n"
                message += f"  모멘텀 점수: {momentum_score}/100, 단타 적합도: {day_trading_score}/100\n"
                message += f"  전략: {strategy}\n"
                message += f"  예상 지속 기간: {duration}\n\n"
                
                # 메모리에 기회 저장 (디비/캐시 사용하지 않음)
                self.gpt_strategy.add_momentum_opportunity({
                    'symbol': symbol,
                    'name': name,
                    'price': price,
                    'target_price': target,
                    'stop_loss': stop_loss,
                    'momentum_score': momentum_score,
                    'day_trading_score': day_trading_score,
                    'strategy': strategy,
                    'market': analysis.get('market', 'KR'),
                    'entry_time': get_current_time().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # 알림 발송
            if self.notifier:
                self.notifier.send_message(message)
            
            return True
            
        except Exception as e:
            logger.error(f"실시간 시장 스캔 중 오류 발생: {e}")
            return False
    
    def _get_market_data(self):
        """시장 데이터 가져오기 (신규 추가)"""
        try:
            # 관심 종목 목록 구성
            interest_symbols = []
            
            # 1. 추천 종목 추가
            kr_symbols = [stock.get('symbol') for stock in self.gpt_selections.get('KR', [])]
            interest_symbols.extend(kr_symbols)
            
            # 2. 현재 보유 종목 추가
            holding_symbols = list(self.holdings.keys())
            interest_symbols.extend(holding_symbols)
            
            # 3. 추가 관심 종목 추가
            additional_symbols = getattr(self.config, 'ADDITIONAL_INTEREST_SYMBOLS', [])
            if isinstance(additional_symbols, list):
                interest_symbols.extend(additional_symbols)
                
            # 4. 코스피/코스닥 주요 지수 구성 종목 (실시간 급등주 스캐닝을 위한 추가 데이터)
            index_symbols = getattr(self.config, 'INDEX_COMPONENT_SYMBOLS', [])
            if isinstance(index_symbols, list):
                interest_symbols.extend(index_symbols)
                
            # 중복 제거 및 유효한 종목 코드만 추출
            interest_symbols = list(set([s for s in interest_symbols if s and isinstance(s, str)]))
            
            # 최대 100개 종목으로 제한 (API 부하 고려)
            if len(interest_symbols) > 100:
                logger.info(f"관심 종목이 너무 많아({len(interest_symbols)}개) 100개로 제한합니다")
                interest_symbols = interest_symbols[:100]
            
            # 시장 데이터 딕셔너리 초기화
            market_data = {}
            
            # 종목별 시세 데이터 가져오기
            for symbol in interest_symbols:
                try:
                    # 한국 종목 포맷 검사 (기본 6자리 숫자)
                    market = "KR"
                    
                    # 과거 데이터 가져오기 (20일)
                    df = self.data_provider.get_historical_data(symbol, market, period="1mo")
                    
                    if df is not None and not df.empty:
                        # 기술적 지표 추가
                        # RSI
                        try:
                            delta = df['Close'].diff()
                            gain = delta.where(delta > 0, 0)
                            loss = -delta.where(delta < 0, 0)
                            avg_gain = gain.rolling(window=14).mean()
                            avg_loss = loss.rolling(window=14).mean()
                            rs = avg_gain / avg_loss
                            df['RSI'] = 100 - (100 / (1 + rs))
                        except:
                            pass
                            
                        # 이동평균선
                        try:
                            df['SMA_short'] = df['Close'].rolling(window=10).mean()
                            df['SMA_long'] = df['Close'].rolling(window=30).mean()
                        except:
                            pass
                            
                        # MACD
                        try:
                            exp1 = df['Close'].ewm(span=12, adjust=False).mean()
                            exp2 = df['Close'].ewm(span=26, adjust=False).mean()
                            df['MACD'] = exp1 - exp2
                            df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
                        except:
                            pass
                        
                        market_data[symbol] = df
                except Exception as e:
                    logger.error(f"{symbol} 시장 데이터 가져오기 중 오류: {e}")
            
            logger.info(f"시장 데이터 수집 완료: {len(market_data)}개 종목")
            return market_data
            
        except Exception as e:
            logger.error(f"시장 데이터 수집 중 오류: {e}")
            return {}
    
    def _calculate_win_rate(self):
        """승률 계산 (신규 추가)"""
        total = self.autonomous_stats['winning_trades'] + self.autonomous_stats['losing_trades']
        if total == 0:
            return 0
        return (self.autonomous_stats['winning_trades'] / total) * 100
    
    def _get_autonomous_stats_summary(self):
        """자율 매매 통계 요약 (신규 추가)"""
        if self.autonomous_stats['start_time'] is None:
            return "통계 없음"
            
        # 운영 기간 계산
        now = get_current_time()
        duration = now - self.autonomous_stats['start_time']
        days = duration.days
        hours = duration.seconds // 3600
        
        # 승률 계산
        win_rate = self._calculate_win_rate()
        
        # 순이익 계산
        net_profit = self.autonomous_stats['total_profit'] - self.autonomous_stats['total_loss']
        
        return (f"총 {self.autonomous_stats['total_trades']}회 거래, 승률 {win_rate:.1f}%, "
              f"총수익 {self.autonomous_stats['total_profit']:,.0f}원, 총손실 {self.autonomous_stats['total_loss']:,.0f}원, "
              f"순이익 {net_profit:,.0f}원 (운영기간: {days}일 {hours}시간)")
              
    def _select_stocks(self):
        """GPT를 사용하여 주식 선정"""
        try:
            now = get_current_time()
            
            # 동적 종목 선정이 비활성화되어 있고, 이미 이전에 선정된 종목이 있다면 종목 선정 건너뜀
            if not self.use_dynamic_selection and (self.gpt_selections['KR'] or self.gpt_selections['US']):
                logger.info("동적 종목 선정이 비활성화되어 있고 이미 선정된 종목이 있어 종목 선정 건너뜀")
                return
                
            # 마지막 선정 후 설정된 간격이 지나지 않았으면 건너뜀
            if self.last_selection_time:
                hours_passed = (now - self.last_selection_time).total_seconds() / 3600
                if hours_passed < self.selection_interval:
                    logger.info(f"마지막 종목 선정 후 {hours_passed:.1f}시간 경과 (설정: {self.selection_interval}시간). 선정 건너뜀")
                    return
                    
            # OpenAI API 키 유효성 확인
            if not self.stock_selector.is_api_key_valid():
                logger.warning("유효한 OpenAI API 키가 없어 종목 선정을 건너뜁니다.")
                if self.notifier:
                    self.notifier.send_message("⚠️ OpenAI API 키 오류로 GPT 종목 선정 실패. 이전 선정 종목을 계속 사용합니다.")
                return
            
            logger.info(f"{self.strategy} 전략으로 GPT 종목 선정 시작")
            
            # 설정 확인 - 단타 매매 모드와 급등주 감지 모드 확인
            day_trading_mode = getattr(self.config, 'DAY_TRADING_MODE', False)
            surge_detection_enabled = getattr(self.config, 'SURGE_DETECTION_ENABLED', False)
            
            # 단타 매매 또는 급등주 감지 모드가 활성화된 경우
            if day_trading_mode or surge_detection_enabled:
                kr_recommendations = {"recommended_stocks": []}
                us_recommendations = {"recommended_stocks": []}
                
                logger.info(f"단타 매매 모드: {day_trading_mode}, 급등주 감지 모드: {surge_detection_enabled}")
                
                # 단타 매매 모드가 활성화된 경우
                if day_trading_mode:
                    logger.info("단타 매매 모드로 종목 선정을 시작합니다.")
                    try:
                        # 한국 주식 단타 매매 종목 추천
                        day_trading_symbols = self.gpt_strategy.get_day_trading_candidates(
                            market="KR", 
                            max_count=self.max_positions,
                            min_score=70,
                            use_cache=False  # 캐시 사용 안함
                        )
                        
                        # 단타 매매 종목 정보 구성
                        for symbol in day_trading_symbols:
                            # 종목 정보 가져오기
                            stock_info = self.data_provider.get_stock_info(symbol, "KR")
                            name = stock_info.get('name', symbol) if stock_info else symbol
                            
                            # 현재가 가져오기
                            price = self.data_provider.get_current_price(symbol, "KR") or 0
                            
                            # 단타 매매 종목 데이터 분석
                            analysis = self.gpt_strategy.analyze_momentum_stock(
                                symbol=symbol,
                                use_cache=False
                            )
                            
                            # 단타 점수와 목표가 가져오기
                            day_trading_score = analysis.get('day_trading_score', 75) if analysis else 75
                            target_price = analysis.get('target_price', price * 1.1) if analysis else price * 1.1
                            
                            # 추천 종목에 추가
                            kr_recommendations["recommended_stocks"].append({
                                'symbol': symbol,
                                'name': name,
                                'suggested_weight': min(day_trading_score / 2, 40),  # 최대 40%
                                'target_price': target_price,
                                'risk_level': 10 - int(day_trading_score / 10),  # 변환 (점수가 높을수록 위험도 낮음)
                                'type': 'day_trading',
                                'day_trading_score': day_trading_score
                            })
                        
                        logger.info(f"단타 매매 종목 선정 완료: {len(day_trading_symbols)}개 종목")
                    except Exception as e:
                        logger.error(f"단타 매매 종목 선정 중 오류 발생: {e}")
                
                # 급등주 감지 모드가 활성화된 경우
                if surge_detection_enabled:
                    logger.info("급등주 감지 모드로 종목 선정을 시작합니다.")
                    try:
                        # 현재 메모리에 저장된 모멘텀 기회 활용
                        momentum_opportunities = self.gpt_strategy.get_momentum_opportunities(min_score=80)
                        
                        # 기회가 충분하지 않으면 새로 스캔
                        if len(momentum_opportunities) < 3:
                            self._scan_market_opportunities()
                            momentum_opportunities = self.gpt_strategy.get_momentum_opportunities(min_score=80)
                        
                        # 급등주 정보 구성
                        for opp in momentum_opportunities:
                            symbol = opp.get('symbol')
                            if not symbol:
                                continue
                                
                            # 이미 단타 매매 종목에 있는지 확인
                            already_selected = False
                            for stock in kr_recommendations["recommended_stocks"]:
                                if stock.get('symbol') == symbol:
                                    already_selected = True
                                    break
                            
                            if already_selected:
                                continue
                                
                            # 종목 정보 및 현재가
                            name = opp.get('name') or symbol
                            price = opp.get('price') or self.data_provider.get_current_price(symbol, "KR") or 0
                            
                            # 모멘텀 점수 가져오기
                            momentum_score = opp.get('momentum_score', 0)
                            target_price = opp.get('target_price', price * 1.1)
                            
                            # 추천 종목에 추가
                            kr_recommendations["recommended_stocks"].append({
                                'symbol': symbol,
                                'name': name,
                                'suggested_weight': min(momentum_score / 2, 40),  # 최대 40%
                                'target_price': target_price,
                                'risk_level': 10 - int(momentum_score / 10),  # 변환
                                'type': 'momentum',
                                'momentum_score': momentum_score
                            })
                        
                        logger.info(f"급등주 감지 종목 선정 완료: {len(momentum_opportunities)}개 종목 확인")
                    except Exception as e:
                        logger.error(f"급등주 감지 종목 선정 중 오류 발생: {e}")
                
                # 미국 주식 추천 (단타/급등주 모드에서도 미국 주식 지원)
                us_stock_trading_enabled = getattr(self.config, 'US_STOCK_TRADING_ENABLED', False)
                if us_stock_trading_enabled:
                    logger.info("미국 주식 단타/급등주 종목 선정 시작")
                    try:
                        # 미국 단타 매매 종목 가져오기
                        us_symbols = self.gpt_strategy.get_day_trading_candidates(
                            market="US", 
                            max_count=3,
                            use_cache=False
                        )
                        
                        # 미국 종목 정보 구성
                        for symbol in us_symbols:
                            # 종목 정보 가져오기
                            stock_info = self.data_provider.get_stock_info(symbol, "US")
                            name = stock_info.get('name', symbol) if stock_info else symbol
                            price = self.data_provider.get_current_price(symbol, "US") or 0
                            
                            # 분석 (선택 사항)
                            analysis = None
                            try:
                                analysis = self.gpt_strategy.analyze_momentum_stock(
                                    symbol=symbol,
                                    use_cache=False
                                )
                            except:
                                pass
                            
                            score = analysis.get('day_trading_score', 75) if analysis else 75
                            target_price = analysis.get('target_price', price * 1.1) if analysis else price * 1.1
                            
                            # 추천 종목에 추가
                            us_recommendations["recommended_stocks"].append({
                                'symbol': symbol,
                                'name': name,
                                'suggested_weight': min(score / 2, 30),  # 최대 30%
                                'target_price': target_price,
                                'risk_level': 10 - int(score / 10),
                                'type': 'us_day_trading',
                                'score': score
                            })
                    except Exception as e:
                        logger.error(f"미국 단타/급등주 종목 선정 중 오류 발생: {e}")
                        
                # 시장 분석 추가
                kr_recommendations["market_analysis"] = "단타 매매 및 급등주 감지 모드로 선정된 종목입니다."
                kr_recommendations["investment_strategy"] = "단기간 목표가 도달 시 익절, 손실 발생 시 빠르게 손절하는 단타 전략을 구사하세요."
                
                if us_recommendations["recommended_stocks"]:
                    us_recommendations["market_analysis"] = "미국 시장 단타 매매 종목입니다."
                    us_recommendations["investment_strategy"] = "미국 시장 변동성을 고려하여 적극적인 익절 전략을 사용하세요."
                
            else:
                # 기존 일반 종목 추천 로직 (단타/급등주 모드가 비활성화된 경우)
                # 한국 주식 추천
                kr_recommendations = self.stock_selector.recommend_stocks(
                    market="KR", 
                    count=self.max_positions,
                    strategy=self.strategy
                )
                
                # 미국 주식 추천 (설정이 활성화된 경우에만)
                us_recommendations = {"recommended_stocks": []}
                us_stock_trading_enabled = getattr(self.config, 'US_STOCK_TRADING_ENABLED', False)
                
                if us_stock_trading_enabled:
                    logger.info("미국 주식 거래가 활성화되어 있습니다. 미국 주식 추천을 요청합니다.")
                    us_recommendations = self.stock_selector.recommend_stocks(
                        market="US", 
                        count=self.max_positions,
                        strategy=self.strategy
                    )
                else:
                    logger.info("미국 주식 거래가 비활성화되어 있습니다. 미국 주식 추천을 건너뜁니다.")
            
            # None 체크 추가 (kr_recommendations가 None일 수 있음)
            kr_count = len(kr_recommendations.get('recommended_stocks', [])) if kr_recommendations else 0
            us_count = len(us_recommendations.get('recommended_stocks', [])) if us_recommendations else 0
            
            logger.info(f"GPT 종목 선정 완료: 한국 {kr_count}개, 미국 {us_count}개")
                      
            # None 체크 추가
            if kr_recommendations:
                self.gpt_selections['KR'] = kr_recommendations.get('recommended_stocks', [])
            if us_recommendations:
                self.gpt_selections['US'] = us_recommendations.get('recommended_stocks', [])
            
            # 동적 종목 선정이 활성화된 경우에만 config.py 업데이트
            if self.use_dynamic_selection:
                # 설정 업데이트 (config.py에 저장)
                self.stock_selector.update_config_stocks(kr_recommendations, us_recommendations)
                logger.info("동적 종목 선정 활성화: config.py의 종목 리스트를 업데이트했습니다.")
            else:
                logger.info("동적 종목 선정 비활성화: config.py의 종목 리스트를 유지합니다.")
            
            # 마지막 선정 시간 업데이트
            self.last_selection_time = now
            
            # 선정 내용 요약 - 안전한 포맷팅 추가
            kr_summary = "🇰🇷 국내 추천 종목:\n"
            for stock in self.gpt_selections['KR']:
                symbol = stock.get('symbol', '')
                name = stock.get('name', symbol)
                risk = stock.get('risk_level', 5)
                target = stock.get('target_price', 0)
                weight = stock.get('suggested_weight', 0)
                stock_type = stock.get('type', '일반')
                
                # None 값 안전 처리 추가
                target_str = f"{target:,.0f}원" if target is not None else "가격 정보 없음"
                
                type_emoji = "🔄" if stock_type == 'day_trading' else "📈" if stock_type == 'momentum' else "📊"
                kr_summary += f"{type_emoji} {name} ({symbol}): 목표가 {target_str}, 비중 {weight}%, 위험도 {risk}/10\n"
                
            us_summary = "\n🇺🇸 미국 추천 종목:\n"
            for stock in self.gpt_selections['US']:
                symbol = stock.get('symbol', '')
                name = stock.get('name', symbol)
                risk = stock.get('risk_level', 5)
                target = stock.get('target_price', 0)
                weight = stock.get('suggested_weight', 0)
                stock_type = stock.get('type', '일반')
                
                # None 값 안전 처리 추가
                target_str = f"${target:,.0f}" if target is not None else "가격 정보 없음"
                
                type_emoji = "🔄" if 'day_trading' in stock_type else "📈" if 'momentum' in stock_type else "📊"
                us_summary += f"{type_emoji} {name} ({symbol}): 목표가 {target_str}, 비중 {weight}%, 위험도 {risk}/10\n"
            
            # 분석 내용 포함
            kr_analysis = kr_recommendations.get('market_analysis', '') if kr_recommendations else ''
            us_analysis = us_recommendations.get('market_analysis', '') if us_recommendations else ''
            investment_strategy = kr_recommendations.get('investment_strategy', '') if kr_recommendations else ''
            
            # 모드 정보 추가
            mode_info = ""
            if day_trading_mode:
                mode_info += "단타매매 "
            if surge_detection_enabled:
                mode_info += "급등주감지 "
            if not mode_info:
                mode_info = "일반투자 "
            
            # 알림 전송
            if self.notifier:
                # 메시지 길이 제한을 고려하여 나눠서 전송
                selection_mode = "동적" if self.use_dynamic_selection else "고정"
                self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()}) - {selection_mode} 선정 모드, {mode_info}\n\n{kr_summary}")
                
                # 미국 주식 거래가 활성화된 경우에만 미국 종목 정보 전송
                if us_stock_trading_enabled and self.gpt_selections['US']:
                    self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()}) - {selection_mode} 선정 모드, {mode_info}\n\n{us_summary}")
                
                if kr_analysis:
                    self.notifier.send_message(f"🧠 시장 분석\n\n{kr_analysis[:500]}...")
                    
                if investment_strategy:
                    self.notifier.send_message(f"🔍 투자 전략 ({self.strategy})\n\n{investment_strategy[:500]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"GPT 종목 선정 중 오류 발생: {e}")
            if self.notifier:
                self.notifier.send_message(f"⚠️ GPT 종목 선정 중 오류 발생: {str(e)}")
            return False
            
    def _load_current_holdings(self):
        """현재 보유 중인 종목 정보 로드"""
        try:
            # 증권사 API를 통해 보유 종목 정보 가져오기
            positions = self.broker.get_positions()
            self.holdings = {}
            
            # positions가 dict인 경우 (key-value 형태)
            if isinstance(positions, dict):
                logger.debug("Dict 형태의 positions 처리")
                for symbol, position in positions.items():
                    self.holdings[symbol] = {
                        'symbol': symbol,
                        'name': position.get('name', symbol),
                        'quantity': position.get('quantity', 0),
                        'avg_price': position.get('avg_price', 0),
                        'current_price': position.get('current_price', 0),
                        'market': position.get('market', 'KR'),
                        'entry_time': position.get('entry_time', get_current_time().isoformat())
                    }
            # positions가 list인 경우 (항목 리스트 형태)
            elif isinstance(positions, list):
                logger.debug("List 형태의 positions 처리")
                for position in positions:
                    # KISAPI의 응답 형식 처리 추가
                    if "종목코드" in position:
                        # KISAPI 응답 형식 (한글 키)
                        symbol = position.get("종목코드", "")
                        if symbol:
                            # 종목코드 앞에 'A' 추가 (필요시)
                            if len(symbol) == 6 and symbol.isdigit():
                                symbol_key = symbol  # 원본 종목코드를 키로 사용
                            else:
                                symbol_key = symbol
                                
                            self.holdings[symbol_key] = {
                                'symbol': symbol,
                                'name': position.get("종목명", symbol),
                                'quantity': position.get("보유수량", 0),
                                'avg_price': position.get("평균단가", 0),
                                'current_price': position.get("현재가", 0),
                                'market': 'KR',  # 한국투자증권 API는 국내 주식만 제공
                                'entry_time': get_current_time().isoformat()
                            }
                    elif "pdno" in position or "PDNO" in position:
                        # KISAPI 모의투자 응답 형식 (영문 키)
                        symbol = position.get("pdno", position.get("PDNO", ""))
                        if symbol:
                            self.holdings[symbol] = {
                                'symbol': symbol,
                                'name': position.get("prdt_name", position.get("PRDT_NAME", symbol)),
                                'quantity': int(position.get("hldg_qty", position.get("HLDG_QTY", "0"))),
                                'avg_price': int(float(position.get("pchs_avg_pric", position.get("PCHS_AVG_PRIC", "0")))),
                                'current_price': int(float(position.get("prpr", position.get("PRPR", "0")))),
                                'market': 'KR',
                                'entry_time': get_current_time().isoformat()
                            }
                    else:
                        # 일반 형식
                        symbol = position.get('symbol')
                        if not symbol:  # symbol이 없으면 건너뜀
                            continue
                        
                        self.holdings[symbol] = {
                            'symbol': symbol,
                            'name': position.get('name', symbol),
                            'quantity': position.get('quantity', 0),
                            'avg_price': position.get('avg_price', 0),
                            'current_price': position.get('current_price', 0),
                            'market': position.get('market', 'KR'),
                            'entry_time': position.get('entry_time', get_current_time().isoformat())
                        }
            else:
                # 예상치 않은 형태
                logger.warning(f"예상치 않은 positions 형식: {type(positions)}")
                
            logger.info(f"보유 종목 로드 완료: {len(self.holdings)}개")
            
            # 디버깅: 보유 종목 상세 정보 출력
            if self.holdings:
                for symbol, data in self.holdings.items():
                    logger.debug(f"보유종목 상세: {symbol}, 이름: {data.get('name')}, "
                               f"수량: {data.get('quantity')}, 평단가: {data.get('avg_price'):,}원")
            
            return True
            
        except Exception as e:
            logger.error(f"보유 종목 로드 중 오류 발생: {e}")
            return False
            
    def _should_buy(self, stock_data):
        """
        GPT 추천 종목 매수 여부 결정
        
        Args:
            stock_data: GPT 추천 종목 데이터
            
        Returns:
            bool: 매수 여부
        """
        try:
            symbol = stock_data.get('symbol')
            risk_level = stock_data.get('risk_level', 5)
            suggested_weight = stock_data.get('suggested_weight', 20)  # 기본값 20%로 설정
            target_price = stock_data.get('target_price', 0)
            
            # 기본 검증
            if not symbol:
                return False
                
            # 이미 보유 중인 종목 체크
            if symbol in self.holdings:
                logger.info(f"{symbol} 이미 보유 중")
                return False
                
            # 기존 포지션이 최대치에 도달했는지 확인
            if len(self.holdings) >= self.max_positions:
                logger.info(f"최대 포지션 수({self.max_positions}개)에 도달하여 새로운 종목을 매수하지 않습니다.")
                return False
                
            # 시장이 열려있는지 확인
            market = "KR" if len(symbol) == 6 and symbol.isdigit() else "US"
            if not is_market_open(market):
                logger.info(f"{market} 시장이 닫혀있어 매수하지 않습니다.")
                return False
                
            # 추천 비중이 충분히 높은지 확인 - 적정 수준 유지 (기존 15%에서 조정)
            if suggested_weight < 10:  # 10% 미만은 투자하지 않음
                logger.info(f"{symbol} 추천 비중({suggested_weight}%)이 낮아 매수하지 않습니다.")
                return False
                
            # 위험도 체크 - 안전 기준 유지
            if risk_level > 8:  # 위험도 8 초과는 투자하지 않음
                logger.info(f"{symbol} 위험도({risk_level}/10)가 높아 매수하지 않습니다.")
                return False
                
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 목표가 대비 현재가 확인
            if target_price and current_price >= target_price * 0.85:  # 85% 기준 유지
                logger.info(f"{symbol} 현재가({current_price:,.0f})가 목표가({target_price:,.0f})의 85% 이상으로 매수하지 않습니다.")
                return False
                
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance()
            available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
            
            # 최소 현금 기준
            if available_cash < 100000:  # 최소 10만원 유지
                logger.warning(f"주문가능금액({available_cash:,.0f}원)이 부족하여 매수하지 않습니다.")
                return False
                
            # 투자 금액 결정 (계좌 잔고 또는 최대 투자 금액 중 작은 것)
            investment_amount = min(self.max_investment_per_stock, available_cash * (suggested_weight / 100))
            
            # 최소 투자 금액 기준 (기존 50만원에서 약간 낮춤)
            if investment_amount < 300000:  # 30만원 미만은 투자하지 않음
                logger.info(f"{symbol} 투자 금액({investment_amount:,.0f}원)이 30만원 미만으로 매수하지 않습니다.")
                return False
                
            # 기술적 분석 지표 확인
            df = self.data_provider.get_historical_data(symbol, market)
            if df is not None and len(df) > 30:
                # RSI 확인 (과매수 상태면 매수하지 않음)
                if 'RSI' in df.columns and df['RSI'].iloc[-1] > 75:  # 75로 안전하게 조정
                    logger.info(f"{symbol} RSI({df['RSI'].iloc[-1]:.1f})가 과매수 상태로 매수하지 않습니다.")
                    return False
                
                # 이동평균선 확인 - 약한 조건으로 적용
                if ('MA20' in df.columns and 'MA60' in df.columns and 
                    df['MA20'].iloc[-1] < df['MA60'].iloc[-1] * 0.9):  # 단기선이 장기선의 90% 미만이면 약세
                    logger.info(f"{symbol} 단기 이동평균선이 장기선보다 크게 낮아(10% 이상) 약세 신호. 매수하지 않습니다.")
                    return False
                    
            # 모든 조건 통과, 매수 시그널
            logger.info(f"{symbol} 매수 결정: 추천 비중 {suggested_weight}%, 위험도 {risk_level}/10")
            
            # 추천 비중이 0인 경우 기본값으로 설정하기 전에 한 번 더 확인
            if suggested_weight == 0:
                # 추천 비중이 0%인 경우 매수하지 않음 (안전 장치)
                logger.info(f"{symbol} 추천 비중이 0%이므로 매수하지 않습니다.")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"매수 결정 중 오류 발생: {e}")
            return False
            
    def _should_sell(self, symbol):
        """
        보유 종목 매도 여부 결정
        
        Args:
            symbol: 종목 코드
            
        Returns:
            bool: 매도 여부
        """
        try:
            if symbol not in self.holdings:
                return False
                
            position = self.holdings[symbol]
            market = position.get('market', 'KR')
            avg_price = position.get('avg_price', 0)
            
            # 시장이 열려있는지 확인
            if not is_market_open(market):
                logger.info(f"{market} 시장이 닫혀 있어 매도하지 않습니다.")
                return False
                
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 최근 GPT 추천에서 제외된 종목인지 확인
            is_recommended = False
            selections = self.gpt_selections[market]
            for stock in selections:
                if stock.get('symbol') == symbol:
                    is_recommended = True
                    break
                    
            # GPT 추천에서 제외되었고 수익이 났다면 매도
            if not is_recommended and current_price > avg_price:
                profit_pct = ((current_price / avg_price) - 1) * 100
                logger.info(f"{symbol} GPT 추천에서 제외되었고 수익률({profit_pct:.2f}%)이 플러스라 매도합니다.")
                return True
                
            # 손실 컷 (평균 매수가의 10% 이상 하락 시)
            loss_threshold = -10
            if avg_price > 0:
                profit_pct = ((current_price / avg_price) - 1) * 100
                if profit_pct <= loss_threshold:
                    logger.info(f"{symbol} 손실 컷: 수익률 {profit_pct:.2f}%가 임계치({loss_threshold}%)보다 낮아 매도합니다.")
                    return True
                
            # 보유 기간 체크 (30일 이상 보유하고 수익이 없으면 매도)
            entry_time = position.get('entry_time')
            if entry_time:
                try:
                    entry_date = datetime.datetime.fromisoformat(entry_time)
                    days_held = (get_current_time() - entry_date).days
                    if days_held >= 30 and current_price <= avg_price:
                        logger.info(f"{symbol} {days_held}일 이상 보유했으나 수익이 없어 매도합니다.")
                        return True
                except:
                    pass
                
            # 기술적 분석 지표 확인 (추가 매도 시그널)
            df = self.data_provider.get_historical_data(symbol, market)
            if df is not None and len(df) > 30:
                # RSI가 과매도 상태이고 손실 상태라면 매도 (추가 하락 예상)
                if 'RSI' in df.columns and df['RSI'].iloc[-1] < 30 and current_price < avg_price:
                    logger.info(f"{symbol} RSI({df['RSI'].iloc[-1]:.1f})가 과매도 상태이고 손실 중. 추가 하락 예상으로 매도합니다.")
                    return True
                    
                # 단기/장기 이동평균선 데드크로스 발생 시 매도
                if ('MA20' in df.columns and 'MA60' in df.columns and 
                    df['MA20'].iloc[-2] >= df['MA60'].iloc[-2] and  # 전일: 단기선이 장기선 위
                    df['MA20'].iloc[-1] < df['MA60'].iloc[-1]):      # 금일: 단기선이 장기선 아래
                    logger.info(f"{symbol} 이동평균 데드크로스 발생. 매도합니다.")
                    return True
                    
            # 기본적으로 매도하지 않음
            return False
            
        except Exception as e:
            logger.error(f"매도 결정 중 오류 발생: {e}")
            return False
            
    def _execute_buy(self, stock_data):
        """
        GPT 추천 종목 매수 실행
        
        Args:
            stock_data: GPT 추천 종목 데이터
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            symbol = stock_data.get('symbol')
            name = stock_data.get('name', symbol)
            market = "KR" if len(symbol) == 6 and symbol.isdigit() else "US"
            suggested_weight = stock_data.get('suggested_weight', 20) / 100
            
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 매수 전 계좌 잔고 기록
            pre_balance_info = self.broker.get_balance()
            pre_available_cash = pre_balance_info.get('주문가능금액', pre_balance_info.get('예수금', 0))
            logger.info(f"매수 전 주문가능금액: {pre_available_cash:,.0f}원")
            
            # 투자 금액 결정 (계좌 잔고 또는 최대 투자 금액 중 작은 것)
            investment_amount = min(self.max_investment_per_stock, pre_available_cash * suggested_weight)
            
            # 매수 수량 계산 (투자 금액 / 현재가)
            quantity = int(investment_amount / current_price)
            
            # 최소 1주 이상
            if quantity < 1:
                logger.warning(f"{symbol} 매수 수량({quantity})이 1보다 작아 매수하지 않습니다.")
                return False
                
            expected_total = quantity * current_price
            logger.info(f"{symbol} 매수 실행: {quantity}주 × {current_price:,.0f}원 = {expected_total:,.0f}원 (예상)")
            
            # 시뮬레이션 모드 확인 (명시적으로 config에서 가져옴)
            simulation_mode = getattr(self.config, 'SIMULATION_MODE', False)
            logger.info(f"현재 거래 모드: {'시뮬레이션' if simulation_mode else '실거래'} (SIMULATION_MODE={simulation_mode})")
            
            # auto_trader의 시뮬레이션 모드도 확인
            auto_trader_simulation = getattr(self.auto_trader, 'simulation_mode', False)
            logger.info(f"AutoTrader 시뮬레이션 모드: {auto_trader_simulation}")
            
            # 명시적으로 auto_trader의 시뮬레이션 모드를 config와 일치시킴
            self.auto_trader.simulation_mode = simulation_mode
            
            # 매수 실행 (실거래 모드일 때만 실제 주문 실행)
            if not simulation_mode:
                logger.info("실거래 모드로 주문을 실행합니다.")
                order_result = self.auto_trader._execute_order(
                    symbol=symbol,
                    action=TradeAction.BUY,
                    quantity=quantity,
                    market=market
                )
                
                if order_result.get('status') == 'EXECUTED':
                    logger.info(f"{symbol} 매수 주문 체결 완료 - 실제 거래 실행됨")
                    
                    # 매매 기록에 추가
                    trade_record = {
                        'timestamp': get_current_time().isoformat(),
                        'symbol': symbol,
                        'name': name,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': current_price,
                        'total': quantity * current_price,
                        'market': market,
                        'source': 'GPT',
                        'order_id': order_result.get('order_id', ''),
                        'suggested_weight': suggested_weight * 100
                    }
                    self.trade_history.append(trade_record)
                    
                    # 주문 후 잔고 변화 확인을 위해 지연시간 추가
                    logger.info(f"주문 체결 후 API 반영 대기 시작...")
                    time.sleep(10)  # 10초로 증가 - 모의투자 API 반영 시간 고려
                    
                    # 매수 후 계좌 잔고 확인 - 증권사 API 데이터만 사용
                    post_balance_info = self.broker.get_balance()
                    post_available_cash = post_balance_info.get('주문가능금액', post_balance_info.get('예수금', 0))
                    logger.info(f"매수 후 주문가능금액: {post_available_cash:,.0f}원")
                    
                    # 잔고 변화 확인 및 로깅 (정보 제공 목적으로만 사용)
                    cash_diff = pre_available_cash - post_available_cash
                    logger.info(f"주문가능금액 변화: -{cash_diff:,.0f}원 (예상: -{expected_total:,.0f}원)")
                    
                    # 보유 종목 업데이트 (증권사 API에서 제공하는 데이터만 사용)
                    self._load_current_holdings()
                    
                    # 알림 전송
                    if self.notifier:
                        self.notifier.send_message(f"💰 주식 매수 완료: {name}({symbol})\n"
                                                  f"• 수량: {quantity:,}주\n"
                                                  f"• 단가: {current_price:,}원\n"
                                                  f"• 총액: {expected_total:,}원\n"
                                                  f"• 거래모드: 실거래")
                    
                    return True
                else:
                    logger.warning(f"{symbol} 매수 주문 실패: {order_result.get('message', '알 수 없는 오류')}")
                    return False
            else:
                # 시뮬레이션 모드일 경우 매매 로그만 남기고 성공으로 처리
                logger.info(f"{symbol} 매수 주문 시뮬레이션 완료 - 실제 거래는 발생하지 않음")
                
                # 매매 기록에 추가 (시뮬레이션 표시)
                trade_record = {
                    'timestamp': get_current_time().isoformat(),
                    'symbol': symbol,
                    'name': name,
                    'action': 'BUY (SIM)',  # 시뮬레이션 표시
                    'quantity': quantity,
                    'price': current_price,
                    'total': quantity * current_price,
                    'market': market,
                    'source': 'GPT',
                    'suggested_weight': suggested_weight * 100
                }
                self.trade_history.append(trade_record)
                
                # 시뮬레이션 보유 종목에 추가
                if symbol not in self.holdings:
                    self.holdings[symbol] = {
                        'symbol': symbol,
                        'name': name,
                        'quantity': quantity,
                        'avg_price': current_price,
                        'current_price': current_price,
                        'market': market,
                        'entry_time': get_current_time().isoformat(),
                        'simulation': True  # 시뮬레이션 표시
                    }
                
                # 알림 전송
                if self.notifier:
                    self.notifier.send_message(f"💰 주식 매수 시뮬레이션: {name}({symbol})\n"
                                              f"• 수량: {quantity:,}주\n"
                                              f"• 단가: {current_price:,}원\n"
                                              f"• 총액: {expected_total:,}원\n"
                                              f"• 거래모드: 시뮬레이션 (실제 거래 없음)")
                
                return True
                
        except Exception as e:
            logger.error(f"매수 실행 중 오류 발생: {e}")
            return False
            
    def _execute_sell(self, symbol):
        """
        보유 종목 매도 실행
        
        Args:
            symbol: 종목 코드
            
        Returns:
            bool: 매도 성공 여부
        """
        try:
            if symbol not in self.holdings:
                logger.warning(f"{symbol} 보유하고 있지 않은 종목입니다.")
                return False
                
            position = self.holdings[symbol]
            quantity = position.get('quantity', 0)
            market = position.get('market', 'KR')
            name = position.get('name', symbol)
            
            if quantity <= 0:
                logger.warning(f"{symbol} 매도 가능한 수량이 없습니다.")
                return False
                
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            
            logger.info(f"{symbol} 매도 실행: {quantity}주 × {current_price:,.0f}원 = {quantity * current_price:,.0f}원")
            
            # 매도 실행
            order_result = self.auto_trader._execute_order(
                symbol=symbol,
                action=TradeAction.SELL,
                quantity=quantity,
                market=market
            )
            
            if order_result.get('status') == 'EXECUTED':
                logger.info(f"{symbol} 매도 주문 체결 완료")
                
                # 매매 기록에 추가
                trade_record = {
                    'timestamp': get_current_time().isoformat(),
                    'symbol': symbol,
                    'name': name,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': current_price,
                    'total': quantity * current_price,
                    'market': market,
                    'source': 'GPT',
                    'order_id': order_result.get('order_id', '')
                }
                self.trade_history.append(trade_record)
                
                # 보유 종목 업데이트
                self._load_current_holdings()
                
                return True
            else:
                logger.warning(f"{symbol} 매도 주문 실패: {order_result.get('message', '알 수 없는 오류')}")
                return False
                
        except Exception as e:
            logger.error(f"매도 실행 중 오류 발생: {e}")
            return False
    
    def get_gpt_insights_for_realtime_trading(self, symbol, stock_data, current_price=None, is_holding=False, avg_price=0):
        """
        GPT 모델에서 실시간 트레이딩을 위한 분석 요청
        
        Args:
            symbol (str): 종목 코드
            stock_data (DataFrame): 종목 주가 데이터
            current_price (float, optional): 현재가. None이면 stock_data에서 가져옴
            is_holding (bool): 현재 보유 중인 종목인지 여부
            avg_price (float): 보유 중인 경우 평균 매수가
            
        Returns:
            dict: 분석 결과 및 매매 신호
        """
        try:
            logger.info(f"{symbol} 종목에 대한 실시간 GPT 분석 요청")
            
            # 현재가가 없는 경우 데이터에서 가져옴
            if current_price is None and not stock_data.empty:
                current_price = stock_data['Close'].iloc[-1]
            
            # 종목명 조회 (가능한 경우)
            name = None
            if hasattr(self.broker, 'get_stock_name'):
                try:
                    name = self.broker.get_stock_name(symbol)
                except:
                    name = symbol  # 조회 실패시 코드 사용
            
            # GPT 트레이딩 전략 객체로 분석 요청
            result = self.gpt_strategy.analyze_realtime_trading(
                symbol=symbol,
                stock_data=stock_data,
                current_price=current_price,
                is_holding=is_holding,
                avg_price=avg_price,
                name=name
            )
            
            # 결과 로깅
            action = result.get('action', 'HOLD')
            confidence = result.get('confidence', 0.0)
            
            if action != 'HOLD' and action != 'ERROR':
                logger.info(f"GPT 실시간 분석 결과 - {symbol}: {action} 신호 (신뢰도: {confidence:.2f})")
                
                # 중요 매매 신호는 알림 발송 (높은 신뢰도)
                if self.notifier and confidence > 0.8:
                    summary = result.get('analysis_summary', '분석 없음')
                    if action == 'BUY':
                        self.notifier.send_message(f"🔵 매수 신호 감지: {symbol} ({name})\n신뢰도: {confidence:.2f}\n{summary}")
                    elif action == 'SELL':
                        self.notifier.send_message(f"🔴 매도 신호 감지: {symbol} ({name})\n신뢰도: {confidence:.2f}\n{summary}")
            
            return result
            
        except Exception as e:
            logger.error(f"{symbol} 실시간 GPT 분석 요청 중 오류 발생: {e}")
            return {
                'symbol': symbol,
                'action': 'ERROR',
                'confidence': 0.0,
                'analysis_summary': f'GPT 분석 중 오류: {str(e)}',
                'timestamp': datetime.datetime.now().isoformat()
            }

    def _execute_buy_decision(self, buy_decision):
        """
        GPT가 제안한 매수 결정 실행 (신규 추가)
        
        Args:
            buy_decision (dict): 매수 결정 정보
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            symbol = buy_decision.get('symbol')
            price = buy_decision.get('price', 0)
            amount = buy_decision.get('amount', 0)  # 금액 기준
            quantity = buy_decision.get('quantity', 0)  # 수량 기준
            market = "KR" if len(symbol) == 6 and symbol.isdigit() else "US"
            
            # 종목명 가져오기
            stock_info = self.data_provider.get_stock_info(symbol, market)
            name = stock_info.get('name', symbol) if stock_info else symbol
            
            # 1. 현재 가격 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 2. 금액이 지정되어 있으면 수량 계산
            if amount > 0 and quantity == 0:
                quantity = int(amount / current_price)
                if quantity < 1:
                    logger.warning(f"{symbol} 매수 수량({quantity})이 1보다 작아 매수하지 않습니다.")
                    return False
            
            # 3. 수량이 지정되어 있지 않으면 매수 불가
            if quantity == 0:
                logger.warning(f"{symbol} 매수 수량이 지정되어 있지 않습니다.")
                return False
                
            total_amount = quantity * current_price
            
            # 4. 자율 매매 최대 금액 체크
            if total_amount > self.autonomous_max_trade_amount:
                old_quantity = quantity
                quantity = int(self.autonomous_max_trade_amount / current_price)
                logger.info(f"{symbol} 매수 금액({total_amount:,.0f}원)이 최대 허용 금액({self.autonomous_max_trade_amount:,.0f}원)을 초과하여 수량을 {old_quantity}주에서 {quantity}주로 조정")
                total_amount = quantity * current_price
            
            # 5. 매수 실행
            logger.info(f"{symbol} 매수 실행: {quantity}주 × {current_price:,.0f}원 = {total_amount:,.0f}원")
            
            # 시뮬레이션 모드 확인
            simulation_mode = getattr(self.config, 'SIMULATION_MODE', False)
            
            if not simulation_mode:
                # 실제 매수 실행
                order_result = self.auto_trader._execute_order(
                    symbol=symbol,
                    action=TradeAction.BUY,
                    quantity=quantity,
                    market=market
                )
                
                if order_result.get('status') == 'EXECUTED':
                    logger.info(f"{symbol} 매수 주문 체결 완료")
                    
                    # 매매 기록에 추가
                    trade_record = {
                        'timestamp': get_current_time().isoformat(),
                        'symbol': symbol,
                        'name': name,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': current_price,
                        'total': total_amount,
                        'market': market,
                        'source': 'GPT_AUTONOMOUS',
                        'order_id': order_result.get('order_id', ''),
                        'reason': buy_decision.get('reason', 'GPT 자율 매매')
                    }
                    self.trade_history.append(trade_record)
                    
                    # 주문 후 잔고 변화 확인을 위해 지연시간 추가
                    time.sleep(2)
                    
                    # 보유 종목 업데이트
                    self._load_current_holdings()
                    
                    # 알림 전송
                    if self.notifier:
                        message = f"🤖 GPT 자율 매수: {name}({symbol})\n"
                        message += f"• 수량: {quantity:,}주\n"
                        message += f"• 단가: {current_price:,}원\n"
                        message += f"• 총액: {total_amount:,}원\n"
                        message += f"• 근거: {buy_decision.get('reason', '자율 투자 결정')}"
                        self.notifier.send_message(message)
                    
                    return True
                else:
                    logger.warning(f"{symbol} 매수 주문 실패: {order_result.get('message', '알 수 없는 오류')}")
                    return False
            else:
                # 시뮬레이션 모드일 경우
                logger.info(f"{symbol} 매수 주문 시뮬레이션 완료 - 실제 거래는 발생하지 않음")
                
                # 매매 기록에 추가 (시뮬레이션 표시)
                trade_record = {
                    'timestamp': get_current_time().isoformat(),
                    'symbol': symbol,
                    'name': name,
                    'action': 'BUY (SIM)',  # 시뮬레이션 표시
                    'quantity': quantity,
                    'price': current_price,
                    'total': total_amount,
                    'market': market,
                    'source': 'GPT_AUTONOMOUS',
                    'reason': buy_decision.get('reason', 'GPT 자율 매매 (시뮬레이션)')
                }
                self.trade_history.append(trade_record)
                
                # 시뮬레이션 보유 종목에 추가
                if symbol not in self.holdings:
                    self.holdings[symbol] = {
                        'symbol': symbol,
                        'name': name,
                        'quantity': quantity,
                        'avg_price': current_price,
                        'current_price': current_price,
                        'market': market,
                        'entry_time': get_current_time().isoformat(),
                        'simulation': True  # 시뮬레이션 표시
                    }
                
                # 알림 전송
                if self.notifier:
                    message = f"🤖 GPT 시뮬레이션 매수: {name}({symbol})\n"
                    message += f"• 수량: {quantity:,}주\n"
                    message += f"• 단가: {current_price:,}원\n"
                    message += f"• 총액: {total_amount:,}원\n"
                    message += f"• 근거: {buy_decision.get('reason', '자율 투자 결정')}\n"
                    message += f"• 모드: 시뮬레이션 (실제 거래 없음)"
                    self.notifier.send_message(message)
                
                return True
                
        except Exception as e:
            logger.error(f"매수 결정 실행 중 오류 발생: {e}")
            return False

    def evaluate_autonomous_trade(self, symbol, market_data=None):
        """
        자율 투자 종목의 성과를 평가하여 매도 여부 결정 (신규 추가)
        
        Args:
            symbol (str): 종목 코드
            market_data (dict, optional): 미리 수집된 시장 데이터
            
        Returns:
            dict: 평가 결과 (매도 여부, 이유 등)
        """
        try:
            if symbol not in self.holdings:
                return {'action': 'NO_ACTION', 'reason': '보유 중이 아님'}
                
            # 보유 정보 가져오기
            position = self.holdings[symbol]
            avg_price = position.get('avg_price', 0)
            quantity = position.get('quantity', 0)
            market = position.get('market', 'KR')
            
            # 현재 가격 가져오기
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                return {'action': 'ERROR', 'reason': '현재가 조회 실패'}
                
            # 손익률 계산
            profit_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
            
            # GPT 분석 요청
            insights = self.get_gpt_insights_for_realtime_trading(symbol, market_data)
            
            # 자체 매도 조건 확인 (손절/익절)
            result = {'action': 'NO_ACTION', 'reason': '분석 결과 보유 유지', 'profit_pct': profit_pct}
            
            # 1. 급격한 하락 발생 시 즉시 매도 (손절)
            if profit_pct < -10:  # 10% 이상 손실
                result = {'action': 'SELL', 'reason': f'손절: {profit_pct:.1f}% 손실', 'profit_pct': profit_pct}
            
            # 2. 높은 이익 실현 (익절)
            elif profit_pct > 15:  # 15% 이상 이익
                result = {'action': 'SELL', 'reason': f'익절: {profit_pct:.1f}% 이익', 'profit_pct': profit_pct}
            
            # 3. GPT 분석이 매도 권고할 경우
            elif insights and insights.get('action') == 'SELL' and insights.get('confidence', 0) > 0.7:
                result = {
                    'action': 'SELL', 
                    'reason': f"GPT 매도 권고: {insights.get('analysis_summary', '추가 상승 여력 제한')}",
                    'profit_pct': profit_pct
                }
            
            # 4. 손실 상태에서 더 큰 하락이 예상되는 경우 (신뢰도 높은 경우)
            elif profit_pct < 0 and insights and insights.get('action') == 'SELL' and insights.get('confidence', 0) > 0.8:
                result = {
                    'action': 'SELL',
                    'reason': f"손실 확대 방지: {insights.get('analysis_summary', '추가 하락 예상')}",
                    'profit_pct': profit_pct
                }
                
            # 기타 정보 추가
            result['symbol'] = symbol
            result['current_price'] = current_price
            result['avg_price'] = avg_price
            result['quantity'] = quantity
            result['total_investment'] = avg_price * quantity
            result['current_value'] = current_price * quantity
            result['profit_amount'] = (current_price - avg_price) * quantity
            
            return result
            
        except Exception as e:
            logger.error(f"{symbol} 자율 투자 평가 중 오류: {e}")
            return {'action': 'ERROR', 'reason': f'평가 오류: {str(e)}', 'symbol': symbol}
    
    def run_cycle(self):
        """
        GPT 매매 사이클 실행 - 현재 보유 중인 종목을 확인하고 매수/매도 결정을 내림
        
        Returns:
            dict: 사이클 실행 결과 요약
        """
        logger.info("GPT 매매 사이클 실행 시작")
        
        try:
            # 자동 매매가 실행 중이 아니면 자동으로 시작
            if not self.is_running:
                logger.info("GPT 자동 매매가 실행 중이 아닙니다. 자동으로 시작합니다.")
                start_success = self.start()
                if not start_success:
                    logger.error("GPT 자동 매매 시작 실패")
                    return {"status": "error", "message": "GPT 자동 매매가 실행 중이 아니고 자동 시작에 실패했습니다."}
                logger.info("GPT 자동 매매 자동 시작 성공")
            
            # 현재 시간에 거래가 가능한지 확인
            if not self.is_trading_time("KR"):
                logger.info("현재 거래 시간이 아닙니다.")
                return {"status": "skip", "message": "현재 거래 시간이 아닙니다."}
                
            # 현재 보유 중인 종목 정보 로드
            self._load_current_holdings()
            
            # 1. 매도 결정 처리
            sell_results = []
            for symbol in list(self.holdings.keys()):
                if self._should_sell(symbol):
                    logger.info(f"{symbol} 매도 결정")
                    if self._execute_sell(symbol):
                        sell_results.append({"symbol": symbol, "status": "success"})
                    else:
                        sell_results.append({"symbol": symbol, "status": "fail"})
                        
            # 2. 매수 결정 처리
            buy_results = []
            # 추천 종목이 없으면 종목 선정 먼저 실행
            if not self.gpt_selections['KR'] and not self.gpt_selections['US']:
                self._select_stocks()
                
            for market, selections in self.gpt_selections.items():
                for stock_data in selections:
                    if self._should_buy(stock_data):
                        symbol = stock_data.get('symbol')
                        logger.info(f"{symbol} 매수 결정")
                        if self._execute_buy(stock_data):
                            buy_results.append({"symbol": symbol, "status": "success"})
                        else:
                            buy_results.append({"symbol": symbol, "status": "fail"})
            
            # 3. 기술적 지표 최적화 검사 (필요시 실행)
            if self.optimize_technical_indicators:
                if (self.last_technical_optimization_time is None or 
                    (get_current_time() - self.last_technical_optimization_time).total_seconds() / 3600 > self.technical_optimization_interval):
                    logger.info("기술적 지표 최적화 실행")
                    try:
                        if hasattr(self.gpt_strategy, 'optimize_technical_indicators'):
                            self.gpt_strategy.optimize_technical_indicators()
                        self.last_technical_optimization_time = get_current_time()
                    except Exception as e:
                        logger.error(f"기술적 지표 최적화 중 오류 발생: {e}")
            
            # 결과 요약
            summary = {
                "status": "success",
                "timestamp": get_current_time_str(),
                "holdings_count": len(self.holdings),
                "sell_orders": sell_results,
                "buy_orders": buy_results
            }
            
            logger.info(f"GPT 매매 사이클 완료: {len(sell_results)}개 매도, {len(buy_results)}개 매수")
            return summary
            
        except Exception as e:
            logger.error(f"GPT 매매 사이클 실행 중 오류 발생: {e}")
            return {"status": "error", "message": f"오류 발생: {str(e)}"}