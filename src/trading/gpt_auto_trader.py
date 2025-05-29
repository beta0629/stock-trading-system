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

from src.ai_analysis.stock_selector import StockSelector
from src.trading.auto_trader import AutoTrader, TradeAction, OrderType
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
        
        # AutoTrader 초기화 (실제 매매 실행용)
        self.auto_trader = AutoTrader(config, broker, data_provider, None, notifier)
        
        # 설정값 로드
        self.gpt_trading_enabled = getattr(config, 'GPT_AUTO_TRADING', True)
        self.selection_interval = getattr(config, 'GPT_STOCK_SELECTION_INTERVAL', 24)  # 시간
        self.max_positions = getattr(config, 'GPT_TRADING_MAX_POSITIONS', 5)
        self.conf_threshold = getattr(config, 'GPT_TRADING_CONF_THRESHOLD', 0.7)
        self.max_investment_per_stock = getattr(config, 'GPT_MAX_INVESTMENT_PER_STOCK', 5000000)
        self.strategy = getattr(config, 'GPT_STRATEGY', 'balanced')
        self.monitoring_interval = getattr(config, 'GPT_TRADING_MONITOR_INTERVAL', 30)  # 분
        
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
        
        logger.info("GPT 자동 매매 시스템 초기화 완료")
        
    def start(self):
        """GPT 기반 자동 매매 시작"""
        logger.info("GPT 자동 매매 시작 시도 중...")
        
        if self.is_running:
            logger.warning("GPT 자동 매매가 이미 실행 중입니다.")
            return
            
        if not self.gpt_trading_enabled:
            logger.warning("GPT 자동 매매 기능이 비활성화되어 있습니다. config.py에서 GPT_AUTO_TRADING을 True로 설정하세요.")
            return
        
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
        
        # 증권사 API 연결 및 기능 테스트
        logger.info("증권사 API 연결 테스트를 시작합니다.")
        
        # 브로커 객체 확인 - 시뮬레이션 모드로 대체 가능하도록 수정
        broker_initialized = True
        simulation_mode = getattr(self.config, 'SIMULATION_MODE', False)
        
        if not self.broker:
            logger.error("증권사 API 객체(broker)가 없습니다.")
            if self.notifier:
                self.notifier.send_message("⚠️ 증권사 API 객체 초기화 실패")
            
            # 시뮬레이션 모드로 전환 가능한지 확인
            if simulation_mode:
                logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                broker_initialized = True
            else:
                logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                return False
        
        try:
            # API 테스트는 시뮬레이션 모드가 아닐 때만 수행
            if self.broker and not simulation_mode:
                # 1. API 연결 테스트
                if not self.broker.connect():
                    logger.error("증권사 API 연결에 실패했습니다.")
                    if self.notifier:
                        self.notifier.send_message("⚠️ 증권사 API 연결 실패")
                    
                    # 시뮬레이션 모드로 전환 가능한지 확인
                    if simulation_mode:
                        logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                    else:
                        logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                logger.info("증권사 API 연결 성공")
                
                # 2. 로그인 테스트
                if not self.broker.login():
                    logger.error("증권사 API 로그인에 실패했습니다.")
                    if self.notifier:
                        self.notifier.send_message("⚠️ 증권사 API 로그인 실패")
                    
                    # 시뮬레이션 모드로 전환 가능한지 확인
                    if simulation_mode:
                        logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                    else:
                        logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                logger.info("증권사 API 로그인 성공")
                
                # 3. 계좌 잔고 조회 테스트
                try:
                    balance = self.broker.get_balance()
                    if balance is None:
                        raise ValueError("계좌 잔고 정보를 얻을 수 없습니다.")
                    logger.info(f"계좌 잔고 조회 성공: 예수금 {balance.get('예수금', 0):,}원")
                except Exception as e:
                    logger.error(f"계좌 잔고 조회 실패: {e}")
                    if self.notifier:
                        self.notifier.send_message("⚠️ 계좌 잔고 조회에 실패했습니다.")
                    
                    # 시뮬레이션 모드로 전환 가능한지 확인
                    if simulation_mode:
                        logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                    else:
                        logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                # 4. 보유종목 조회 테스트
                try:
                    positions = self.broker.get_positions()
                    position_count = len(positions)
                    logger.info(f"보유종목 조회 성공: {position_count}개 종목 보유 중")
                except Exception as e:
                    logger.error(f"보유종목 조회 실패: {e}")
                    if self.notifier:
                        self.notifier.send_message("⚠️ 보유종목 조회에 실패했습니다.")
                    
                    # 시뮬레이션 모드로 전환 가능한지 확인
                    if simulation_mode:
                        logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                    else:
                        logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                # 5. 시장 데이터 조회 테스트 (삼성전자 현재가 조회)
                test_symbol = "005930"  # 삼성전자
                try:
                    current_price = self.data_provider.get_current_price(test_symbol, "KR")
                    if current_price <= 0:
                        raise ValueError("현재가가 0 이하입니다.")
                    logger.info(f"시장 데이터 조회 성공: 삼성전자 현재가 {current_price:,}원")
                except Exception as e:
                    logger.error(f"시장 데이터 조회 실패: {e}")
                    if self.notifier:
                        self.notifier.send_message("⚠️ 시장 데이터 조회에 실패했습니다.")
                    
                    # 시뮬레이션 모드로 전환 가능한지 확인
                    if simulation_mode:
                        logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
                    else:
                        logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                        return False
                
                logger.info("증권사 API 기능 테스트 완료: 모든 테스트 통과")
            else:
                # 시뮬레이션 모드일 경우
                logger.info("시뮬레이션 모드로 실행 중입니다. API 테스트를 건너뜁니다.")
        except Exception as e:
            logger.error(f"증권사 API 테스트 중 예외 발생: {e}")
            if self.notifier:
                self.notifier.send_message(f"⚠️ 증권사 API 테스트 중 오류 발생: {str(e)}")
                
            # 시뮬레이션 모드로 전환 가능한지 확인
            if simulation_mode:
                logger.info("시뮬레이션 모드로 대체하여 실행합니다.")
            else:
                logger.error("시뮬레이션 모드도 비활성화되어 있어 자동 매매를 시작할 수 없습니다.")
                return False
        
        # 테스트 결과 알림 (성공 또는 시뮬레이션 모드)
        if self.notifier:
            if simulation_mode:
                message = f"✅ GPT 자동 매매 시작 (시뮬레이션 모드)\n"
                message += f"• 최대 포지션 수: {self.max_positions}개\n"
                message += f"• 종목당 최대 투자금: {self.max_investment_per_stock:,}원\n"
                self.notifier.send_message(message)
            else:
                balance = self.broker.get_balance() if self.broker else {"예수금": 0}
                positions = self.broker.get_positions() if self.broker else {}
                current_price = self.data_provider.get_current_price("005930", "KR") if self.data_provider else 0
                
                message = f"✅ 증권사 API 테스트 완료 ({self.broker.get_trading_mode() if self.broker else '시뮬레이션'})\n"
                message += f"• 계좌 잔고: {balance.get('예수금', 0):,}원\n"
                message += f"• 보유종목 수: {len(positions)}개\n"
                message += f"• 삼성전자 현재가: {current_price:,}원\n"
                self.notifier.send_message(message)
        
        self.is_running = True
        logger.info("GPT 자동 매매 시스템을 시작합니다.")
        
        # AutoTrader 시작 (자체적으로 시뮬레이션 모드 처리)
        if self.auto_trader:
            # 시뮬레이션 모드 설정
            if simulation_mode:
                self.auto_trader.simulation_mode = True
                logger.info("AutoTrader를 시뮬레이션 모드로 시작합니다.")
            
            self.auto_trader.start_trading_session()
        
        # 초기 종목 선정 실행
        self._select_stocks()
        
        # 포지션 로드
        self._load_current_holdings()
        
        # 알림 전송
        if self.notifier:
            message = f"🤖 GPT 자동 매매 시스템 시작 ({get_current_time_str()})\n\n"
            message += f"• 전략: {self.strategy}\n"
            message += f"• 최대 포지션 수: {self.max_positions}개\n"
            message += f"• 종목당 최대 투자금: {self.max_investment_per_stock:,}원\n"
            message += f"• 종목 선정 주기: {self.selection_interval}시간\n"
            message += f"• 모니터링 간격: {self.monitoring_interval}분\n"
            message += f"• 모드: {'시뮬레이션' if simulation_mode else '실거래'}\n"
            self.notifier.send_message(message)
            
        return True
        
    def stop(self):
        """GPT 기반 자동 매매 중지"""
        if not self.is_running:
            logger.warning("GPT 자동 매매가 실행 중이 아닙니다.")
            return
            
        self.is_running = False
        logger.info("GPT 자동 매매 시스템을 중지합니다.")
        
        # AutoTrader 중지
        self.auto_trader.stop_trading_session()
        
        # 알림 전송
        if self.notifier:
            message = f"🛑 GPT 자동 매매 시스템 중지 ({get_current_time_str()})"
            self.notifier.send_message(message)
            
        return True
        
    def _select_stocks(self):
        """GPT를 사용하여 주식 선정"""
        try:
            now = get_current_time()
            
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
            
            # 한국 주식 추천
            kr_recommendations = self.stock_selector.recommend_stocks(
                market="KR", 
                count=self.max_positions,
                strategy=self.strategy
            )
            
            # 미국 주식 추천
            us_recommendations = self.stock_selector.recommend_stocks(
                market="US", 
                count=self.max_positions,
                strategy=self.strategy
            )
            
            logger.info(f"GPT 종목 선정 완료: 한국 {len(kr_recommendations.get('recommended_stocks', []))}개, "
                      f"미국 {len(us_recommendations.get('recommended_stocks', []))}개")
                      
            # 선정된 종목 저장
            self.gpt_selections['KR'] = kr_recommendations.get('recommended_stocks', [])
            self.gpt_selections['US'] = us_recommendations.get('recommended_stocks', [])
            
            # 설정 업데이트 (config.py에 저장)
            self.stock_selector.update_config_stocks(kr_recommendations, us_recommendations)
            
            # 마지막 선정 시간 업데이트
            self.last_selection_time = now
            
            # 선정 내용 요약
            kr_summary = "🇰🇷 국내 추천 종목:\n"
            for stock in self.gpt_selections['KR']:
                symbol = stock.get('symbol', '')
                name = stock.get('name', symbol)
                risk = stock.get('risk_level', 5)
                target = stock.get('target_price', 0)
                weight = stock.get('suggested_weight', 0)
                
                kr_summary += f"• {name} ({symbol}): 목표가 {target:,.0f}원, 비중 {weight}%, 위험도 {risk}/10\n"
                
            us_summary = "\n🇺🇸 미국 추천 종목:\n"
            for stock in self.gpt_selections['US']:
                symbol = stock.get('symbol', '')
                name = stock.get('name', symbol)
                risk = stock.get('risk_level', 5)
                target = stock.get('target_price', 0)
                weight = stock.get('suggested_weight', 0)
                
                us_summary += f"• {name} ({symbol}): 목표가 ${target:,.0f}, 비중 {weight}%, 위험도 {risk}/10\n"
            
            # 분석 내용 포함
            kr_analysis = kr_recommendations.get('market_analysis', '')
            us_analysis = us_recommendations.get('market_analysis', '')
            investment_strategy = kr_recommendations.get('investment_strategy', '')
            
            # 알림 전송
            if self.notifier:
                # 메시지 길이 제한을 고려하여 나눠서 전송
                self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()})\n\n{kr_summary}")
                self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()})\n\n{us_summary}")
                
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
                
            logger.info(f"보유 종목 로드 완료: {len(self.holdings)}개")
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
            suggested_weight = stock_data.get('suggested_weight', 10)
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
                logger.info(f"{market} 시장이 닫혀 있어 매수하지 않습니다.")
                return False
                
            # 추천 비중이 충분히 높은지 확인
            if suggested_weight < 15:  # 15% 미만은 투자하지 않음
                logger.info(f"{symbol} 추천 비중({suggested_weight}%)이 낮아 매수하지 않습니다.")
                return False
                
            # 위험도 체크
            if risk_level > 8:  # 위험도 8 초과는 투자하지 않음
                logger.info(f"{symbol} 위험도({risk_level}/10)가 높아 매수하지 않습니다.")
                return False
                
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 목표가 대비 현재가 확인 (목표가의 85% 이상이면 매수하지 않음)
            if target_price and current_price >= target_price * 0.85:
                logger.info(f"{symbol} 현재가({current_price:,.0f})가 목표가({target_price:,.0f})의 85% 이상으로 매수하지 않습니다.")
                return False
                
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance()
            available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
            
            if available_cash < 100000:  # 최소 10만원 이상 있어야 함
                logger.warning(f"주문가능금액({available_cash:,.0f}원)이 부족하여 매수하지 않습니다.")
                return False
                
            # 투자 금액 결정 (계좌 잔고 또는 최대 투자 금액 중 작은 것)
            investment_amount = min(self.max_investment_per_stock, available_cash * (suggested_weight / 100))
            
            # 최소 50만원 이상의 투자 금액이 있어야 함
            if investment_amount < 500000:
                logger.info(f"{symbol} 투자 금액({investment_amount:,.0f}원)이 50만원 미만으로 매수하지 않습니다.")
                return False
                
            # 기술적 분석 지표 확인 (선택적)
            df = self.data_provider.get_historical_data(symbol, market)
            if df is not None and len(df) > 30:
                # RSI 확인 (과매수 상태면 매수하지 않음)
                if 'RSI' in df.columns and df['RSI'].iloc[-1] > 70:
                    logger.info(f"{symbol} RSI({df['RSI'].iloc[-1]:.1f})가 과매수 상태로 매수하지 않습니다.")
                    return False
                    
                # 이동평균선 확인 (단기선이 장기선 아래면 매수하지 않음)
                if 'MA20' in df.columns and 'MA60' in df.columns and df['MA20'].iloc[-1] < df['MA60'].iloc[-1]:
                    logger.info(f"{symbol} 단기 이동평균선이 장기선 아래로 약세 신호. 매수하지 않습니다.")
                    return False
                    
            # 모든 조건 통과, 매수 시그널
            logger.info(f"{symbol} 매수 결정: 추천 비중 {suggested_weight}%, 위험도 {risk_level}/10")
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
            suggested_weight = stock_data.get('suggested_weight', 10) / 100
            
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance()
            available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
            
            # 투자 금액 결정 (계좌 잔고 또는 최대 투자 금액 중 작은 것)
            investment_amount = min(self.max_investment_per_stock, available_cash * suggested_weight)
            
            # 매수 수량 계산 (투자 금액 / 현재가)
            quantity = int(investment_amount / current_price)
            
            # 최소 1주 이상
            if quantity < 1:
                logger.warning(f"{symbol} 매수 수량({quantity})이 1보다 작아 매수하지 않습니다.")
                return False
                
            logger.info(f"{symbol} 매수 실행: {quantity}주 × {current_price:,.0f}원 = {quantity * current_price:,.0f}원")
            
            # 매수 실행
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
                    'total': quantity * current_price,
                    'market': market,
                    'source': 'GPT',
                    'order_id': order_result.get('order_id', ''),
                    'suggested_weight': suggested_weight * 100
                }
                self.trade_history.append(trade_record)
                
                # 보유 종목 업데이트
                self._load_current_holdings()
                
                return True
            else:
                logger.warning(f"{symbol} 매수 주문 실패: {order_result.get('message', '알 수 없는 오류')}")
                return False
                
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
    
    def run_cycle(self):
        """GPT 자동 매매 주기 실행"""
        if not self.is_running:
            logger.warning("GPT 자동 매매 시스템이 실행 중이 아닙니다.")
            return
            
        logger.info("----- GPT 자동 매매 사이클 시작 -----")
        
        try:
            # 종목 선정 (필요한 경우)
            now = get_current_time()
            needs_selection = True
            
            if self.last_selection_time:
                hours_passed = (now - self.last_selection_time).total_seconds() / 3600
                if hours_passed < self.selection_interval:
                    needs_selection = False
                    logger.info(f"마지막 종목 선정 후 {hours_passed:.1f}시간 경과 (설정: {self.selection_interval}시간). 추가 선정 필요 없음")
            
            if needs_selection:
                logger.info("GPT 종목 선정 실행")
                self._select_stocks()
            
            # 현재 보유 종목 로드
            self._load_current_holdings()
            
            # 매도 결정 (먼저 처리)
            sell_candidates = []
            for symbol in self.holdings:
                if self._should_sell(symbol):
                    sell_candidates.append(symbol)
            
            # 매도 실행
            sell_results = []
            for symbol in sell_candidates:
                result = self._execute_sell(symbol)
                sell_results.append((symbol, result))
            
            if sell_results:
                logger.info(f"매도 실행 결과: {len([r for s, r in sell_results if r])}/{len(sell_results)}개 성공")
            
            # 매수 후보 찾기
            buy_candidates = []
            
            # 한국 시장이 열려있으면 한국 종목 처리
            if is_market_open("KR"):
                for stock in self.gpt_selections['KR']:
                    if self._should_buy(stock):
                        buy_candidates.append(stock)
                        
                        # 최대 매수 종목 수 제한
                        if len(buy_candidates) >= 2:  # 한 번에 최대 2개 종목만 매수
                            break
            
            # 미국 시장이 열려있으면 미국 종목 처리
            if is_market_open("US") and len(buy_candidates) < 2:  # 아직 매수 가능한 경우
                for stock in self.gpt_selections['US']:
                    if self._should_buy(stock):
                        buy_candidates.append(stock)
                        
                        # 최대 매수 종목 수 제한
                        if len(buy_candidates) >= 2:  # 한 번에 최대 2개 종목만 매수
                            break
            
            # 매수 실행
            buy_results = []
            for stock in buy_candidates:
                result = self._execute_buy(stock)
                buy_results.append((stock.get('symbol'), result))
            
            if buy_results:
                logger.info(f"매수 실행 결과: {len([r for s, r in buy_results if r])}/{len(buy_results)}개 성공")
            
            # 실행 결과 요약
            if sell_results or buy_results:
                summary = f"📊 GPT 자동 매매 실행 결과 ({get_current_time_str()})\n\n"
                
                if sell_results:
                    summary += "🔴 매도:\n"
                    for symbol, result in sell_results:
                        name = self.holdings.get(symbol, {}).get('name', symbol)
                        status = "✅ 성공" if result else "❌ 실패"
                        summary += f"• {name} ({symbol}): {status}\n"
                    summary += "\n"
                
                if buy_results:
                    summary += "🟢 매수:\n"
                    for symbol, result in buy_results:
                        # 매수 종목 찾기
                        name = symbol
                        for market in ['KR', 'US']:
                            for stock in self.gpt_selections[market]:
                                if stock.get('symbol') == symbol:
                                    name = stock.get('name', symbol)
                        status = "✅ 성공" if result else "❌ 실패"
                        summary += f"• {name} ({symbol}): {status}\n"
                
                # 알림 전송
                if self.notifier:
                    self.notifier.send_message(summary)
            
            # 현재 포트폴리오 상태 업데이트
            self._update_portfolio_status()
            
            logger.info("----- GPT 자동 매매 사이클 완료 -----")
            
        except Exception as e:
            logger.error(f"GPT 자동 매매 사이클 실행 중 오류 발생: {e}")
            if self.notifier:
                self.notifier.send_message(f"⚠️ GPT 자동 매매 오류: {str(e)}")
    
    def _update_portfolio_status(self):
        """현재 포트폴리오 상태 업데이트"""
        try:
            # 현재 보유 종목 로드
            self._load_current_holdings()
            
            # 포트폴리오 내 종목들 현재가 업데이트
            total_assets = 0
            total_profit_loss = 0
            
            for symbol, position in self.holdings.items():
                current_price = self.data_provider.get_current_price(symbol, position['market'])
                if current_price:
                    quantity = position['quantity']
                    avg_price = position['avg_price']
                    current_value = current_price * quantity
                    profit_loss = (current_price - avg_price) * quantity
                    profit_loss_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
                    
                    # 포지션 정보 업데이트
                    position['current_price'] = current_price
                    position['current_value'] = current_value
                    position['profit_loss'] = profit_loss
                    position['profit_loss_pct'] = profit_loss_pct
                    
                    total_assets += current_value
                    total_profit_loss += profit_loss
            
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance()
            cash = balance_info.get('예수금', 0)
            total_assets += cash
            
            # 1시간 마다 한번씩 포트폴리오 상태 알림
            now = get_current_time()
            current_hour = now.hour
            
            if hasattr(self, 'last_status_hour') and self.last_status_hour == current_hour:
                return
                
            self.last_status_hour = current_hour
            
            # 매시간 정각에만 전체 포트폴리오 상태 알림
            if now.minute < 10 and (now.hour % 2 == 0):  # 짝수 시간대 정각에만
                # 보유 종목이 없으면 건너뜀
                if not self.holdings:
                    return
                    
                status_message = f"📈 GPT 매매 포트폴리오 상태 ({get_current_time_str()})\n\n"
                status_message += f"💰 총자산: {total_assets:,.0f}원\n"
                status_message += f"💵 현금: {cash:,.0f}원\n"
                status_message += f"📊 평가손익: {total_profit_loss:,.0f}원\n\n"
                
                if self.holdings:
                    status_message += "🧩 보유종목:\n"
                    for symbol, position in self.holdings.items():
                        name = position.get('name', symbol)
                        quantity = position.get('quantity', 0)
                        profit_loss_pct = position.get('profit_loss_pct', 0)
                        emoji = "🔴" if profit_loss_pct < 0 else "🟢"
                        status_message += f"{emoji} {name} ({symbol}): {quantity}주, {profit_loss_pct:.2f}%\n"
                
                # 알림 전송
                if self.notifier:
                    self.notifier.send_message(status_message)
                
        except Exception as e:
            logger.error(f"포트폴리오 상태 업데이트 중 오류 발생: {e}")