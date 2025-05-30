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
        self.use_dynamic_selection = getattr(config, 'GPT_USE_DYNAMIC_SELECTION', False)  # 동적 종목 선정 사용 여부
        
        # 기술적 지표 최적화 설정 로드
        self.optimize_technical_indicators = getattr(config, 'GPT_OPTIMIZE_TECHNICAL_INDICATORS', True)
        self.technical_optimization_interval = getattr(config, 'GPT_TECHNICAL_OPTIMIZATION_INTERVAL', 168)  # 시간 (기본 1주일)
        self.last_technical_optimization_time = None
        
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
        
        logger.info(f"GPT 자동 매매 시스템 초기화 완료 (동적 종목 선별: {'활성화' if self.use_dynamic_selection else '비활성화'}, 기술적 지표 최적화: {'활성화' if self.optimize_technical_indicators else '비활성화'})")
        
    def is_trading_time(self, market="KR"):
        """
        현재 시간이 거래 시간인지 확인
        
        Args:
            market (str): 시장 코드 ('KR' 또는 'US')
            
        Returns:
            bool: 거래 시간이면 True, 아니면 False
        """
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
            
            # 시뮬레이션 모드 알림
            if self.notifier:
                self.notifier.send_message("🔧 GPT 자동 매매가 시뮬레이션 모드로 실행됩니다.")
        
        self.is_running = True
        logger.info("GPT 자동 매매 시스템을 시작합니다.")
        
        # AutoTrader 시작
        if self.auto_trader:
            self.auto_trader.start_trading_session()
            logger.info(f"AutoTrader 시작 상태: {self.auto_trader.is_running}")
        
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
            
            logger.info(f"GPT 종목 선정 완료: 한국 {len(kr_recommendations.get('recommended_stocks', []))}개, "
                      f"미국 {len(us_recommendations.get('recommended_stocks', []))}개")
                      
            # 선정된 종목 저장
            self.gpt_selections['KR'] = kr_recommendations.get('recommended_stocks', [])
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
                selection_mode = "동적" if self.use_dynamic_selection else "고정"
                self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()}) - {selection_mode} 선정 모드\n\n{kr_summary}")
                
                # 미국 주식 거래가 활성화된 경우에만 미국 종목 정보 전송
                if us_stock_trading_enabled and self.gpt_selections['US']:
                    self.notifier.send_message(f"📊 GPT 종목 추천 ({get_current_time_str()}) - {selection_mode} 선정 모드\n\n{us_summary}")
                
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
            suggested_weight = stock_data.get('suggested_weight', 20)  # 기본값 20%로 변경
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
    
    def _update_positions(self):
        """
        보유 종목 현황 업데이트 (계좌 정보 동기화)
        
        Returns:
            bool: 업데이트 성공 여부
        """
        return self._load_current_holdings()
    
    def run_cycle(self):
        """
        트레이딩 사이클 실행 - 시간 기반으로 주식 선정 및 매매 결정
        """
        try:
            logger.info("=== GPT 트레이딩 사이클 시작 ===")
            
            # 현재 시간이 거래 시간인지 확인
            now = get_current_time()
            
            if not self.is_trading_time():  # datetime 매개변수 제거하고 기본 "KR" 시장 사용
                logger.info("현재는 거래 시간이 아닙니다.")
                return
            
            # 기술적 지표 최적화 실행 (필요한 경우)
            if self.optimize_technical_indicators:
                self._optimize_technical_indicators()
            
            # 캐시된 GPT 추천 정보 로드 (GPT 선정 데이터가 없을 경우 대비)
            self._load_cached_recommendations()
                
            # 종목 선정 (필요한 경우)
            self._select_stocks()
            
            # 보유 종목 현황 업데이트
            self._update_positions()
            
            # 계좌 잔고 확인
            balance_info = self.broker.get_balance()
            available_cash = balance_info.get('주문가능금액', balance_info.get('예수금', 0))
            logger.info(f"계좌 잔고: {available_cash:,.0f}원")
            
            # 매매 결정 및 실행 (한국 주식)
            logger.info("=== 한국 주식 매매 시작 ===")
            self._process_kr_stocks(available_cash)
            
            # 미국 주식 매매 (설정이 활성화된 경우에만)
            us_stock_trading_enabled = getattr(self.config, 'US_STOCK_TRADING_ENABLED', False)
            
            if us_stock_trading_enabled:
                logger.info("=== 미국 주식 매매 시작 ===")
                self._process_us_stocks(available_cash)
            else:
                logger.info("미국 주식 거래가 비활성화되어 있습니다. 미국 주식 매매를 건너뜁니다.")
            
            logger.info("=== GPT 트레이딩 사이클 완료 ===")
            
        except Exception as e:
            logger.error(f"GPT 트레이딩 사이클 중 오류 발생: {e}")
            if self.notifier:
                self.notifier.send_message(f"⚠️ GPT 트레이딩 오류: {str(e)}")
                
        return
    
    def _process_kr_stocks(self, available_cash):
        """
        한국 주식 매매 처리
        
        Args:
            available_cash: 주문 가능 현금
            
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 디버그: 캐시된 추천 종목 로그
            logger.info("=== KR 추천 종목 목록 로그 확인 ===")
            for stock in self.gpt_selections.get('KR', []):
                symbol = stock.get('symbol', '')
                # 비중이 없거나 0인 경우 기본값 20%로 설정 (로그용)
                weight = stock.get('suggested_weight', 0)
                if weight == 0:
                    weight = 20
                    # 실제 데이터도 업데이트
                    stock['suggested_weight'] = 20
                name = stock.get('name', symbol)
                logger.info(f"추천 종목: {name}({symbol}), 추천 비중: {weight}%")
            
            # 1. 매도 결정
            sell_candidates = []
            for symbol in list(self.holdings.keys()):
                position = self.holdings[symbol]
                if position.get('market') == 'KR':
                    if self._should_sell(symbol):
                        sell_candidates.append(symbol)
            
            # 매도 실행
            for symbol in sell_candidates:
                logger.info(f"{symbol} 매도 진행")
                self._execute_sell(symbol)
            
            # 2. 매수 결정
            kr_recommendations = self.gpt_selections.get('KR', [])
            buy_candidates = []
            
            # 현재 시장에 있는 종목 코드와 추천 종목 코드가 일치하는지 확인
            # 추천 종목 코드를 정규화 (숫자만 추출)
            normalized_recommendations = []
            for stock in kr_recommendations:
                symbol = stock.get('symbol', '')
                
                # 종목코드에서 숫자만 추출 (예: "005930(삼성전자)" -> "005930")
                if '(' in symbol:
                    symbol = symbol.split('(')[0].strip()
                
                # 원래 데이터 복사 후 정규화된 종목 코드로 교체
                stock_copy = stock.copy()
                stock_copy['symbol'] = symbol
                
                # 비중이 없거나 0인 경우 기본값 20%로 설정
                if not stock_copy.get('suggested_weight') or stock_copy.get('suggested_weight') == 0:
                    stock_copy['suggested_weight'] = 20
                
                normalized_recommendations.append(stock_copy)
                
                # 로그에 기록할 비중 값은 위에서 설정한 값을 사용
                logger.info(f"정규화된 종목코드: {symbol}, 추천 비중: {stock_copy.get('suggested_weight')}%")
            
            # 정규화된 추천 목록으로 교체
            kr_recommendations = normalized_recommendations
            
            for stock_data in kr_recommendations:
                if self._should_buy(stock_data):
                    buy_candidates.append(stock_data)
            
            # 매수 실행 (자금 상황 고려)
            for stock_data in buy_candidates:
                if available_cash < 500000:  # 최소 50만원 이상의 투자 자금 필요
                    logger.info(f"남은 자금({available_cash:,.0f}원)이 부족하여 추가 매수를 중단합니다.")
                    break
                
                symbol = stock_data.get('symbol')
                name = stock_data.get('name', symbol)
                weight = stock_data.get('suggested_weight', 20)  # 기본값 20%
                logger.info(f"{symbol}({name}) 매수 진행 - 추천 비중: {weight}%")
                
                if self._execute_buy(stock_data):
                    # 매수 성공 시 가용 자금 업데이트
                    updated_balance = self.broker.get_balance()
                    available_cash = updated_balance.get('주문가능금액', updated_balance.get('예수금', 0))
            
            return True
            
        except Exception as e:
            logger.error(f"한국 주식 처리 중 오류 발생: {e}")
            return False
            
    def _process_us_stocks(self, available_cash):
        """
        미국 주식 매매 처리
        
        Args:
            available_cash: 주문 가능 현금
            
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 미국 시장 거래 시간인지 확인
            if not self.is_trading_time("US"):
                logger.info("현재는 미국 시장 거래 시간이 아닙니다.")
                return False
                
            # 1. 매도 결정
            sell_candidates = []
            for symbol in list(self.holdings.keys()):
                position = self.holdings[symbol]
                if position.get('market') == 'US':
                    if self._should_sell(symbol):
                        sell_candidates.append(symbol)
            
            # 매도 실행
            for symbol in sell_candidates:
                logger.info(f"{symbol} 매도 진행")
                self._execute_sell(symbol)
            
            # 2. 매수 결정
            us_recommendations = self.gpt_selections.get('US', [])
            buy_candidates = []
            
            for stock_data in us_recommendations:
                if self._should_buy(stock_data):
                    buy_candidates.append(stock_data)
            
            # 매수 실행 (자금 상황 고려)
            for stock_data in buy_candidates:
                if available_cash < 500000:  # 최소 50만원 이상의 투자 자금 필요
                    logger.info(f"남은 자금({available_cash:,.0f}원)이 부족하여 추가 매수를 중단합니다.")
                    break
                
                symbol = stock_data.get('symbol')
                logger.info(f"{symbol} 매수 진행")
                if self._execute_buy(stock_data):
                    # 매수 성공 시 가용 자금 업데이트
                    updated_balance = self.broker.get_balance()
                    available_cash = updated_balance.get('주문가능금액', updated_balance.get('예수금', 0))
            
            return True
            
        except Exception as e:
            logger.error(f"미국 주식 처리 중 오류 발생: {e}")
            return False
    
    def _execute_buy_decision(self, stock_data):
        """
        매수 결정에 따른 매수 실행
        
        Args:
            stock_data: GPT 추천 종목 데이터
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            symbol = stock_data.get('symbol')
            market = stock_data.get('market', 'KR')
            if not market:
                market = "KR" if len(symbol) == 6 and symbol.isdigit() else "US"
                
            name = stock_data.get('name', symbol)
            target_price = stock_data.get('target_price', 0)
            
            # 현재가 확인
            current_price = self.data_provider.get_current_price(symbol, market)
            if not current_price:
                logger.warning(f"{symbol} 현재가를 가져올 수 없습니다.")
                return False
                
            # 계좌 잔고 확인 (매수 전 잔고)
            initial_balance_info = self.broker.get_balance()
            available_cash = initial_balance_info.get('주문가능금액', initial_balance_info.get('예수금', 0))
            
            logger.info(f"사용 가능 현금(주문가능금액): {available_cash:,}원")
            
            if available_cash < 100000:
                logger.warning(f"주문가능금액({available_cash:,}원)이 부족하여 매수할 수 없습니다.")
                return False
                
            # 투자 금액 결정
            investment_ratio = stock_data.get('suggested_weight', 10) / 100
            investment_amount = min(self.max_investment_per_stock, available_cash * investment_ratio)
            
            # 최소 100만원 확인
            if investment_amount < 1000000:
                investment_amount = 1000000
                
            # 투자 금액이 주문가능금액을 초과하는지 확인
            if investment_amount > available_cash:
                investment_amount = available_cash
                
            # 매수 수량 계산
            quantity = int(investment_amount / current_price)
            
            # 최소 1주 확인
            if quantity < 1:
                logger.warning(f"{symbol} 현재가({current_price:,}원)로 최소 1주도 구매할 수 없습니다.")
                return False
                
            # 실제 투자 금액 재계산
            actual_investment = quantity * current_price
            
            # 매수 실행
            logger.info(f"매수 주문 실행: {name} ({symbol}), {quantity}주, 현재가 {current_price:,}원, 총 투자금액: {actual_investment:,}원")
            
            # 알림 데이터 준비
            if self.notifier:
                logger.info(f"알림 데이터 확인: symbol={symbol}, name={name}")
                self.notifier.send_stock_alert(
                    symbol=symbol,
                    stock_name=name,
                    action="BUY",
                    quantity=quantity,
                    price=current_price,
                    reason=f"GPT 추천 종목 ({stock_data.get('suggested_weight', 0)}% 비중)",
                    target_price=target_price
                )
                
            # 시뮬레이션 모드 확인
            if getattr(self.auto_trader, 'simulation_mode', False):
                logger.info(f"시뮬레이션 모드: 실제 매수는 실행되지 않습니다.")
                return True
                
            # 주문 실행
            order_result = self.auto_trader.buy(symbol, quantity, market=market)
            
            if order_result.get('success', False):
                # 주문 성공 로그
                logger.info(f"{symbol} 매수 주문 체결 완료")
                
                # 주문 처리 후 잠시 대기하여 API 서버에 반영될 시간을 줌
                time.sleep(2)
                
                # 주문 후 잔고 강제 리프레시 (최대 3회 시도)
                refreshed = False
                for i in range(3):
                    try:
                        # 잔고 업데이트 강제 시도
                        updated_balance = self.broker.get_balance()
                        updated_cash = updated_balance.get('주문가능금액', updated_balance.get('예수금', 0))
                        
                        logger.info(f"주문 후 잔고 확인 (시도 {i+1}/3): {updated_cash:,}원")
                        
                        # 잔고가 변경되었는지 확인
                        if updated_cash < available_cash:
                            logger.info(f"잔고 업데이트 확인됨: {available_cash:,}원 -> {updated_cash:,}원 (차액: {available_cash - updated_cash:,}원)")
                            refreshed = True
                            break
                        
                        # 잔고가 변경되지 않은 경우 더 긴 대기 후 재시도
                        logger.warning(f"잔고가 업데이트되지 않았습니다. 더 대기 후 재시도합니다.")
                        time.sleep(3 * (i + 1))  # 점진적으로 대기 시간 증가
                    except Exception as e:
                        logger.error(f"잔고 업데이트 확인 중 오류: {e}")
                        time.sleep(1)
                
                # 잔고 업데이트 여부에 따른 처리
                if not refreshed:
                    logger.warning("모의투자 환경에서 잔고 업데이트가 즉시 반영되지 않았습니다. 이는 모의투자 API의 제한사항일 수 있습니다.")
                    
                    # 거래 정보 저장
                    self.trade_history.append({
                        'timestamp': get_current_time().strftime("%Y-%m-%d %H:%M:%S"),
                        'symbol': symbol,
                        'name': name,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': current_price,
                        'amount': actual_investment,
                        'success': True,
                        'order_id': order_result.get('order_no', '')
                    })
                    
                    # 강제로 현재 보유 종목에 추가
                    if symbol not in self.holdings:
                        self.holdings[symbol] = {
                            'symbol': symbol,
                            'name': name,
                            'quantity': quantity,
                            'avg_price': current_price,
                            'current_price': current_price,
                            'market': market,
                            'entry_time': get_current_time().isoformat()
                        }
                        logger.info(f"{symbol} 보유 종목 목록에 수동 추가됨")
                    
                return True
            else:
                logger.error(f"{symbol} 매수 주문 실패: {order_result.get('error', '알 수 없는 오류')}")
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
    
    def _optimize_technical_indicators(self):
        """
        기술적 지표 파라미터 최적화
        
        주식 분석에 사용되는 기술적 지표의 파라미터를 최적화합니다.
        일정 주기마다 시장 상황에 맞게 최적의 파라미터를 찾습니다.
        """
        try:
            now = get_current_time()
            
            # 최적화가 필요한지 확인
            if self.last_technical_optimization_time:
                hours_passed = (now - self.last_technical_optimization_time).total_seconds() / 3600
                if hours_passed < self.technical_optimization_interval:
                    logger.debug(f"기술적 지표 최적화 주기({self.technical_optimization_interval}시간)가 지나지 않았습니다. ({hours_passed:.1f}시간 경과)")
                    return False
            
            logger.info("기술적 지표 파라미터 최적화 시작...")
            
            # 대표 종목들의 최근 데이터를 가져와 분석
            benchmark_symbols = ["005930", "000660", "035420"]  # 삼성전자, SK하이닉스, NAVER
            
            results = {}
            for symbol in benchmark_symbols:
                try:
                    # 과거 데이터 가져오기 (최근 3개월)
                    df = self.data_provider.get_historical_data(symbol, "KR", period="3mo")
                    
                    if df is None or len(df) < 60:  # 최소 60일 데이터 필요
                        logger.warning(f"{symbol} 기술적 지표 최적화를 위한 충분한 데이터가 없습니다.")
                        continue
                    
                    # 1. RSI 파라미터 최적화 (기간)
                    best_rsi_period = self._find_best_rsi_period(df)
                    
                    # 2. 이동평균선 파라미터 최적화
                    best_ma_short = self._find_best_ma_short_period(df)
                    best_ma_long = self._find_best_ma_long_period(df, best_ma_short)
                    
                    # 3. MACD 파라미터 최적화
                    best_macd_params = self._find_best_macd_params(df)
                    
                    # 4. 볼린저 밴드 파라미터 최적화
                    best_bollinger_params = self._find_best_bollinger_params(df)
                    
                    results[symbol] = {
                        "best_rsi_period": best_rsi_period,
                        "best_ma_short": best_ma_short,
                        "best_ma_long": best_ma_long,
                        "best_macd_params": best_macd_params,
                        "best_bollinger_params": best_bollinger_params
                    }
                    
                    logger.info(f"{symbol} 기술적 지표 최적화 결과: RSI 기간={best_rsi_period}, "
                              f"단기이평={best_ma_short}, 장기이평={best_ma_long}")
                    
                except Exception as e:
                    logger.error(f"{symbol} 기술적 지표 최적화 중 오류 발생: {e}")
            
            # 결과가 없으면 종료
            if not results:
                logger.warning("기술적 지표 최적화 결과가 없습니다.")
                return False
            
            # 평균 최적 파라미터 계산
            avg_rsi_period = int(sum(r["best_rsi_period"] for r in results.values()) / len(results))
            avg_ma_short = int(sum(r["best_ma_short"] for r in results.values()) / len(results))
            avg_ma_long = int(sum(r["best_ma_long"] for r in results.values()) / len(results))
            
            # 기본 지표는 대표 종목들의 평균값으로 설정하되, 일반적인 범위 내에 있도록 제한
            rsi_period = max(9, min(21, avg_rsi_period))
            ma_short = max(5, min(20, avg_ma_short))
            ma_long = max(20, min(60, avg_ma_long))
            
            # 기술적 지표 설정 업데이트
            # 여기서는 실제로 설정을 변경하진 않고 로깅만 수행
            logger.info(f"기술적 지표 최적화 완료: RSI 기간={rsi_period}, 단기이평={ma_short}, 장기이평={ma_long}")
            
            # 최적화 시간 업데이트
            self.last_technical_optimization_time = now
            
            # 알림 전송
            if self.notifier:
                self.notifier.send_message(f"📊 기술적 지표 최적화 완료\n\n"
                                         f"• RSI 기간: {rsi_period}\n"
                                         f"• 단기 이동평균: {ma_short}\n"
                                         f"• 장기 이동평균: {ma_long}")
            
            return True
            
        except Exception as e:
            logger.error(f"기술적 지표 최적화 중 오류 발생: {e}")
            return False
    
    def _find_best_rsi_period(self, df, min_period=5, max_period=25):
        """
        최적의 RSI 기간 탐색
        
        Args:
            df: 주가 데이터
            min_period: 최소 RSI 기간
            max_period: 최대 RSI 기간
            
        Returns:
            int: 최적의 RSI 기간
        """
        try:
            # 기본 RSI 기간
            default_period = 14
            
            # 데이터가 충분하지 않으면 기본값 반환
            if len(df) < 50:
                return default_period
                
            # 실험해볼 RSI 기간 목록
            periods = range(min_period, max_period + 1, 2)
            
            # 각 기간별 RSI 계산 및 성과 측정
            best_period = default_period
            best_score = -float('inf')
            
            for period in periods:
                try:
                    # RSI 계산
                    import pandas as pd
                    import numpy as np
                    
                    delta = df['Close'].diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    
                    avg_gain = gain.rolling(window=period).mean()
                    avg_loss = loss.rolling(window=period).mean()
                    
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                    
                    # 과매수/과매도 시그널 생성 (RSI < 30 => 매수, RSI > 70 => 매도)
                    buy_signals = (rsi < 30).astype(int)
                    sell_signals = (rsi > 70).astype(int)
                    
                    # 모의 거래 성과 계산
                    position = 0
                    returns = []
                    
                    for i in range(period, len(df)):
                        if buy_signals.iloc[i] and position == 0:
                            position = 1  # 매수
                            entry_price = df['Close'].iloc[i]
                        elif sell_signals.iloc[i] and position == 1:
                            position = 0  # 매도
                            exit_price = df['Close'].iloc[i]
                            returns.append((exit_price / entry_price) - 1)
                    
                    # 성과 지표 계산
                    if returns:
                        avg_return = np.mean(returns)
                        win_rate = sum(1 for r in returns if r > 0) / len(returns)
                        
                        # 종합 점수 계산 (수익률 + 승률)
                        score = avg_return * 100 + win_rate * 50
                        
                        if score > best_score:
                            best_score = score
                            best_period = period
                except Exception as e:
                    logger.debug(f"RSI 기간 {period} 테스트 중 오류: {e}")
            
            return best_period
            
        except Exception as e:
            logger.error(f"최적 RSI 기간 탐색 중 오류: {e}")
            return 14  # 오류 발생시 기본값
    
    def _find_best_ma_short_period(self, df, min_period=5, max_period=20):
        """
        최적의 단기 이동평균선 기간 탐색
        
        Args:
            df: 주가 데이터
            min_period: 최소 기간
            max_period: 최대 기간
            
        Returns:
            int: 최적의 단기 이동평균선 기간
        """
        try:
            # 기본 단기 이동평균 기간
            default_period = 10
            
            # 데이터가 충분하지 않으면 기본값 반환
            if len(df) < 50:
                return default_period
                
            # 실험해볼 기간 목록
            periods = range(min_period, max_period + 1)
            
            # 각 기간별 이동평균 계산 및 성과 측정
            best_period = default_period
            best_sharpe = -float('inf')
            
            for period in periods:
                try:
                    # 이동평균 계산
                    ma = df['Close'].rolling(window=period).mean()
                    
                    # 매매 시그널 생성 (주가 > MA => 매수 포지션, 주가 < MA => 매도 포지션)
                    position = (df['Close'] > ma).astype(int)
                    
                    # 수익률 계산
                    df['Returns'] = df['Close'].pct_change()
                    strategy_returns = df['Returns'].shift(-1) * position
                    
                    # 샤프 비율 계산
                    sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                    
                    if not np.isnan(sharpe_ratio) and sharpe_ratio > best_sharpe:
                        best_sharpe = sharpe_ratio
                        best_period = period
                except Exception as e:
                    logger.debug(f"MA 기간 {period} 테스트 중 오류: {e}")
            
            return best_period
            
        except Exception as e:
            logger.error(f"최적 단기 이동평균 기간 탐색 중 오류: {e}")
            return 10  # 오류 발생시 기본값
    
    def _find_best_ma_long_period(self, df, short_period, min_period=20, max_period=60):
        """
        최적의 장기 이동평균선 기간 탐색
        
        Args:
            df: 주가 데이터
            short_period: 단기 이동평균선 기간
            min_period: 최소 기간
            max_period: 최대 기간
            
        Returns:
            int: 최적의 장기 이동평균선 기간
        """
        try:
            # 기본 장기 이동평균 기간
            default_period = 30
            
            # 단기 이동평균보다 길어야 함
            min_period = max(min_period, short_period + 5)
            
            # 데이터가 충분하지 않으면 기본값 반환
            if len(df) < max_period * 2:
                return default_period
                
            # 실험해볼 기간 목록
            periods = range(min_period, max_period + 1, 5)  # 5일 단위로 테스트
            
            # 각 기간별 이동평균 골든크로스/데드크로스 전략 테스트
            best_period = default_period
            best_sharpe = -float('inf')
            
            # 단기 이동평균 계산
            short_ma = df['Close'].rolling(window=short_period).mean()
            
            for period in periods:
                try:
                    # 장기 이동평균 계산
                    long_ma = df['Close'].rolling(window=period).mean()
                    
                    # 골든 크로스/데드 크로스 시그널 생성
                    # 골든 크로스 (단기선이 장기선 위로): 매수 시그널
                    # 데드 크로스 (단기선이 장기선 아래로): 매도 시그널
                    position = (short_ma > long_ma).astype(int)
                    
                    # 수익률 계산
                    df['Returns'] = df['Close'].pct_change()
                    strategy_returns = df['Returns'].shift(-1) * position
                    
                    # 전략 성과 측정
                    sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                    
                    if not np.isnan(sharpe_ratio) and sharpe_ratio > best_sharpe:
                        best_sharpe = sharpe_ratio
                        best_period = period
                except Exception as e:
                    logger.debug(f"장기 MA 기간 {period} 테스트 중 오류: {e}")
            
            return best_period
            
        except Exception as e:
            logger.error(f"최적 장기 이동평균 기간 탐색 중 오류: {e}")
            return 30  # 오류 발생시 기본값
    
    def _find_best_macd_params(self, df):
        """
        최적의 MACD 파라미터 탐색
        
        Args:
            df: 주가 데이터
            
        Returns:
            dict: 최적의 MACD 파라미터 (fast, slow, signal)
        """
        # 기본값
        default_params = {"fast": 12, "slow": 26, "signal": 9}
        
        try:
            # 데이터가 충분하지 않으면 기본값 반환
            if len(df) < 100:
                return default_params
                
            # 실험해볼 파라미터 조합
            fast_periods = [8, 10, 12, 14]
            slow_periods = [20, 24, 26, 30]
            signal_periods = [7, 9, 11]
            
            best_params = default_params
            best_sharpe = -float('inf')
            
            for fast in fast_periods:
                for slow in slow_periods:
                    if fast >= slow:  # fast 기간은 slow 기간보다 짧아야 함
                        continue
                        
                    for signal in signal_periods:
                        try:
                            # MACD 계산
                            exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
                            exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
                            macd = exp1 - exp2
                            signal_line = macd.ewm(span=signal, adjust=False).mean()
                            
                            # 매매 시그널 생성 (MACD > Signal Line => 매수, MACD < Signal Line => 매도)
                            position = (macd > signal_line).astype(int)
                            
                            # 수익률 계산
                            df['Returns'] = df['Close'].pct_change()
                            strategy_returns = df['Returns'].shift(-1) * position
                            
                            # 성과 측정
                            sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                            
                            if not np.isnan(sharpe_ratio) and sharpe_ratio > best_sharpe:
                                best_sharpe = sharpe_ratio
                                best_params = {"fast": fast, "slow": slow, "signal": signal}
                        except Exception as e:
                            logger.debug(f"MACD 파라미터 테스트 중 오류: fast={fast}, slow={slow}, signal={signal}, 오류: {e}")
            
            return best_params
            
        except Exception as e:
            logger.error(f"최적 MACD 파라미터 탐색 중 오류: {e}")
            return default_params
    
    def _find_best_bollinger_params(self, df):
        """
        최적의 볼린저 밴드 파라미터 탐색
        
        Args:
            df: 주가 데이터
            
        Returns:
            dict: 최적의 볼린저 밴드 파라미터 (기간, 표준편차 배수)
        """
        # 기본값
        default_params = {"window": 20, "num_std": 2.0}
        
        try:
            # 데이터가 충분하지 않으면 기본값 반환
            if len(df) < 60:
                return default_params
                
            # 실험해볼 파라미터 조합
            windows = [10, 15, 20, 25, 30]
            std_devs = [1.5, 2.0, 2.5, 3.0]
            
            best_params = default_params
            best_sharpe = -float('inf')
            
            for window in windows:
                for num_std in std_devs:
                    try:
                        # 볼린저 밴드 계산
                        rolling_mean = df['Close'].rolling(window=window).mean()
                        rolling_std = df['Close'].rolling(window=window).std()
                        
                        upper_band = rolling_mean + (rolling_std * num_std)
                        lower_band = rolling_mean - (rolling_std * num_std)
                        
                        # 매매 전략: 가격이 하단밴드 아래면 매수, 상단밴드 위면 매도
                        long_signal = (df['Close'] < lower_band).astype(int)
                        short_signal = (df['Close'] > upper_band).astype(int) * -1
                        
                        position = long_signal + short_signal
                        
                        # 수익률 계산
                        df['Returns'] = df['Close'].pct_change()
                        strategy_returns = df['Returns'].shift(-1) * position
                        
                        # 성과 측정
                        sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                        
                        if not np.isnan(sharpe_ratio) and sharpe_ratio > best_sharpe:
                            best_sharpe = sharpe_ratio
                            best_params = {"window": window, "num_std": num_std}
                    except Exception as e:
                        logger.debug(f"볼린저 밴드 파라미터 테스트 중 오류: window={window}, num_std={num_std}, 오류: {e}")
            
            return best_params
            
        except Exception as e:
            logger.error(f"최적 볼린저 밴드 파라미터 탐색 중 오류: {e}")
            return default_params
            
    def _load_cached_recommendations(self):
        """
        캐시된 GPT 추천 종목 정보 로드
        """
        try:
            import os
            import json
            
            # 캐시 디렉토리 확인
            cache_dir = "cache"
            if not os.path.exists(cache_dir):
                logger.info("캐시 디렉토리가 없습니다.")
                return False
                
            # 한국 주식 추천 캐시 로드
            kr_cache_path = os.path.join(cache_dir, "kr_stock_recommendations.json")
            if os.path.exists(kr_cache_path):
                try:
                    with open(kr_cache_path, "r", encoding="utf-8") as f:
                        kr_data = json.load(f)
                        if kr_data and "recommended_stocks" in kr_data:
                            self.gpt_selections['KR'] = kr_data.get("recommended_stocks", [])
                            logger.info(f"한국 주식 추천 캐시 로드 성공: {len(self.gpt_selections['KR'])}개 종목")
                except Exception as e:
                    logger.error(f"한국 주식 추천 캐시 로드 중 오류: {e}")
                    
            # 미국 주식 추천 캐시 로드
            us_cache_path = os.path.join(cache_dir, "us_stock_recommendations.json")
            if os.path.exists(us_cache_path):
                try:
                    with open(us_cache_path, "r", encoding="utf-8") as f:
                        us_data = json.load(f)
                        if us_data and "recommended_stocks" in us_data:
                            self.gpt_selections['US'] = us_data.get("recommended_stocks", [])
                            logger.info(f"미국 주식 추천 캐시 로드 성공: {len(self.gpt_selections['US'])}개 종목")
                except Exception as e:
                    logger.error(f"미국 주식 추천 캐시 로드 중 오류: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"캐시된 추천 정보 로드 중 오류: {e}")
            return False