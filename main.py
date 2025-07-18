"""
AI 주식 분석 시스템 - 메인 파일
이 스크립트는 클라우드 서버에서 24시간 실행되며, 낮에는 국내 주식, 밤에는 미국 주식을 분석합니다.
"""
import logging
import sys
import time
import json  # json 모듈 추가
import schedule
import datetime  # datetime 모듈 추가
import argparse  # 명령줄 인수 처리를 위한 모듈 추가
import os  # os 모듈 추가
import re  # re 모듈 추가
from src.data.stock_data import StockData
from src.analysis.technical import analyze_signals
from src.notification.telegram_sender import TelegramSender
from src.notification.kakao_sender import KakaoSender
from src.trading.kis_api import KISAPI
from src.trading.auto_trader import AutoTrader
from src.trading.gpt_auto_trader import GPTAutoTrader  # 새로 추가한 GPTAutoTrader 클래스
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
from src.ai_analysis.gemini_analyzer import GeminiAnalyzer  # Gemini 분석기 추가
from src.ai_analysis.hybrid_analysis_strategy import HybridAnalysisStrategy  # 하이브리드 분석 전략 추가
from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy, SignalType
from src.ai_analysis.stock_selector import StockSelector
from src.utils.time_utils import now, format_time, get_korean_datetime_format, is_market_open, get_market_schedule, get_current_time, get_current_time_str, convert_time
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('stock_analysis.log')
    ]
)
logger = logging.getLogger('StockAnalysisSystem')

# 시장 강제 오픈 설정 - 환경 변수에서 읽어오기
force_market_open = os.environ.get("FORCE_MARKET_OPEN", "").lower() == "true"
if force_market_open:
    logger.info("환경 변수 FORCE_MARKET_OPEN=true 설정 감지: 시장 시간 제한 무시")
    # config에 강제 설정
    config.FORCE_MARKET_OPEN = True

# 모의투자 모드 설정 - 환경 변수에서 읽어오기
simulation_mode = os.environ.get("SIMULATION_MODE", "").lower() == "true"
if simulation_mode:
    logger.info("환경 변수 SIMULATION_MODE=true 설정 감지: 모의투자 모드 활성화")
    config.KIS_REAL_TRADING = False
    logger.info("한국투자증권 모의투자 계좌를 사용합니다.")

class StockAnalysisSystem:
    """주식 분석 시스템 메인 클래스"""
    
    def __init__(self):
        """초기화 함수"""
        self.config = config
        self.stock_data = StockData(config)
        self.telegram_sender = TelegramSender(config)
        
        # 카카오톡 메시지 전송 초기화
        self.use_kakao = self.config.USE_KAKAO
        self.kakao_sender = KakaoSender(config) if self.use_kakao else None
        
        self.is_running = False
        
        # 자동 매매 기능 초기화
        self.auto_trading_enabled = self.config.AUTO_TRADING_ENABLED
        self.broker_api = None
        self.auto_trader = None
        self.gpt_auto_trader = None  # GPT 자동 매매 객체
        
        if self.auto_trading_enabled:
            self.init_trading_system()
        
        # ChatGPT 분석기 초기화
        self.chatgpt_analyzer = ChatGPTAnalyzer(config)
        
        # Gemini 분석기 초기화
        self.gemini_analyzer = GeminiAnalyzer(config)
        
        # 하이브리드 분석 전략 초기화 (필요한 모든 인자 전달)
        self.hybrid_analysis_strategy = HybridAnalysisStrategy(self.chatgpt_analyzer, self.gemini_analyzer, config)
        
        # GPT 기반 트레이딩 전략 초기화
        self.gpt_trading_strategy = GPTTradingStrategy(config)
        
        # GPT 기반 종목 선정기 초기화
        self.stock_selector = StockSelector(config)
        
        logger.info("AI 주식 분석 시스템 초기화 완료")
    
    # 메시지 전송 함수 (텔레그램, 카카오 통합)
    def send_notification(self, message_type, data):
        """
        알림 메시지 전송 (텔레그램, 카카오톡)
        
        Args:
            message_type: 메시지 유형 ('signal', 'status')
            data: 알림 데이터
        """
        # 텔레그램으로 메시지 전송 시도 (텔레그램 활성화된 경우에만)
        if getattr(self.config, 'USE_TELEGRAM', False) and self.telegram_sender and self.telegram_sender.enabled:
            try:
                if message_type == 'signal':
                    self.telegram_sender.send_signal_notification(data)
                elif message_type == 'status':
                    self.telegram_sender.send_system_status(data)
                logger.info("텔레그램 메시지 전송 시도")
            except Exception as e:
                logger.error(f"텔레그램 메시지 전송 실패: {e}")
        
        # 카카오톡으로 메시지 전송 (활성화된 경우)
        if self.use_kakao and self.kakao_sender:
            try:
                if message_type == 'signal':
                    self.kakao_sender.send_signal_notification(data)
                elif message_type == 'status':
                    self.kakao_sender.send_system_status(data)
                logger.info("카카오톡 메시지 전송 시도")
            except Exception as e:
                logger.error(f"카카오톡 메시지 전송 실패: {e}")
    
    def init_trading_system(self):
        """자동 매매 시스템 초기화"""
        try:
            # CI 환경에서는 특별한 설정으로 초기화
            is_ci = os.environ.get('CI') == 'true'
            if is_ci:
                logger.info("CI 환경에서 실행 중입니다. 자동 매매 시스템을 특수 모드로 초기화합니다.")
                # CI 환경에서도 자동 매매 기능 유지
                self.auto_trading_enabled = True
                
            # 증권사 API 초기화
            try:
                if self.config.BROKER_TYPE == "KIS":
                    self.broker_api = KISAPI(self.config)
                    logger.info("한국투자증권 API 초기화 완료")
                else:
                    logger.error(f"지원하지 않는 증권사 유형: {self.config.BROKER_TYPE}")
                    self.auto_trading_enabled = False
                    return False
            except Exception as broker_error:
                logger.error(f"브로커 API 초기화 실패: {broker_error}")
                # CI 환경에서는 브로커 API 초기화 실패를 허용하고 진행
                if is_ci:
                    logger.info("CI 환경에서는 브로커 API 오류를 무시하고 계속 진행합니다.")
                    self.broker_api = None  # 더미 브로커 객체
                else:
                    self.auto_trading_enabled = False
                    return False
                
            # 필수 구성요소 초기화 확인
            if not hasattr(self, 'stock_data') or not self.stock_data:
                # 필요한 객체 재생성
                logger.info("stock_data 객체 초기화")
                self.stock_data = StockData(self.config)
                
            if not hasattr(self, 'gpt_trading_strategy') or not self.gpt_trading_strategy:
                # 필요한 객체 재생성
                logger.info("gpt_trading_strategy 객체 초기화")
                self.gpt_trading_strategy = GPTTradingStrategy(self.config)
            
            # 알림 발송 객체 확인
            notifier = self.telegram_sender
            if self.use_kakao and self.kakao_sender:
                notifier = self.kakao_sender
            
            # AutoTrader 초기화
            self.auto_trader = AutoTrader(
                config=self.config, 
                broker=self.broker_api,
                data_provider=self.stock_data,
                strategy_provider=self.gpt_trading_strategy,
                notifier=notifier
            )
            
            # GPT 자동 매매 기능 초기화
            gpt_auto_trading = getattr(self.config, 'GPT_AUTO_TRADING', True)
            logger.info(f"GPT 자동 매매 설정: {gpt_auto_trading}")
            
            if gpt_auto_trading:
                # OpenAI API 키 검증
                openai_api_key = getattr(self.config, 'OPENAI_API_KEY', None)
                if not openai_api_key or len(openai_api_key) < 10:  # 기본적인 길이 체크
                    logger.warning("OpenAI API 키가 설정되지 않았거나 유효하지 않습니다.")
                    if notifier:
                        notifier.send_message("⚠️ OpenAI API 키가 설정되지 않아 GPT 자동 매매 기능이 제한됩니다.")
                
                # GPT 자동 매매 객체 초기화
                self.gpt_auto_trader = GPTAutoTrader(
                    config=self.config,
                    broker=self.broker_api,
                    data_provider=self.stock_data,
                    notifier=notifier
                )
                logger.info("GPT 기반 자동 매매 시스템 초기화 완료")
            else:
                logger.info("GPT 자동 매매 기능이 비활성화되어 있습니다.")
                self.gpt_auto_trader = None
            
            # 시뮬레이션 모드 설정이 활성화 되었는지 확인
            if hasattr(self.config, 'SIMULATION_MODE') and self.config.SIMULATION_MODE:
                if self.auto_trader:
                    self.auto_trader.simulation_mode = True
                    logger.info("자동 매매 시스템이 시뮬레이션 모드로 설정되었습니다.")
                if self.gpt_auto_trader and hasattr(self.gpt_auto_trader, 'auto_trader'):
                    self.gpt_auto_trader.auto_trader.simulation_mode = True
                    logger.info("GPT 자동 매매 시스템이 시뮬레이션 모드로 설정되었습니다.")
            
            # CI 환경에서 시뮬레이션 모드로 강제 설정
            if is_ci:
                self.auto_trader.simulation_mode = True
                if self.gpt_auto_trader:
                    self.gpt_auto_trader.auto_trader.simulation_mode = True
                logger.info("CI 환경에서는 시뮬레이션 모드로 자동매매 시스템이 작동합니다.")
                
            logger.info("자동 매매 시스템 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"자동 매매 시스템 초기화 실패: {e}")
            self.auto_trading_enabled = False
            return False
        
    def select_stocks_with_gpt(self):
        """GPT를 활용한 종목 선정"""
        logger.info("GPT 종목 선정 프로세스 시작")
        try:
            # 현재 요일 확인 (월요일 = 0)
            current_weekday = now().weekday()
            
            # 주말에는 실행하지 않음
            if current_weekday >= 5:  # 토(5), 일(6)
                logger.info("주말이므로 종목 선정을 건너뜁니다.")
                return
                
            # 한국 시장 종목 추천 (균형, 성장, 배당 전략 모두 적용)
            strategies = ["balanced", "growth", "dividend"]
            kr_recommendations = {}
            
            for strategy in strategies:
                kr_result = self.stock_selector.recommend_stocks(
                    market="KR", 
                    count=3, 
                    strategy=strategy
                )
                kr_recommendations[strategy] = kr_result
                logger.info(f"KR {strategy} 전략 종목 추천 완료: {len(kr_result.get('recommended_stocks', []))}개")
                
            # 추천 종목 통합
            combined_kr_stocks = []
            kr_analysis = "📊 <b>GPT 추천 국내 종목 분석</b>\n\n"
            
            for strategy, result in kr_recommendations.items():
                if "recommended_stocks" in result and result["recommended_stocks"]:
                    kr_analysis += f"<b>· {strategy.capitalize()} 전략:</b>\n"
                    
                    for stock in result["recommended_stocks"]:
                        symbol = stock.get("symbol")
                        name = stock.get("name", symbol)
                        reason = stock.get("reason", "")
                        weight = stock.get("suggested_weight", 0)
                        
                        combined_kr_stocks.append({
                            "symbol": symbol,
                            "name": name,
                            "strategy": strategy
                        })
                        
                        kr_analysis += f"- {name} ({symbol}): {reason} (추천 비중: {weight}%)\n"
                    
                    kr_analysis += "\n"
            
            # 미국 시장 종목 추천 (다양한 전략 적용)
            us_recommendations = {}
            
            # 미국 시장도 한국 시장과 동일하게 균형, 성장, 배당 전략 모두 적용
            for strategy in strategies:
                us_result = self.stock_selector.recommend_stocks(
                    market="US", 
                    count=3, 
                    strategy=strategy
                )
                us_recommendations[strategy] = us_result
                logger.info(f"US {strategy} 전략 종목 추천 완료: {len(us_result.get('recommended_stocks', []))}개")
            
            # 미국 추천 종목 통합
            combined_us_stocks = []
            us_analysis = "📊 <b>GPT 추천 미국 종목 분석</b>\n\n"
            
            for strategy, result in us_recommendations.items():
                if "recommended_stocks" in result and result["recommended_stocks"]:
                    us_analysis += f"<b>· {strategy.capitalize()} 전략:</b>\n"
                    
                    for stock in result["recommended_stocks"]:
                        symbol = stock.get("symbol")
                        name = stock.get("name", symbol)
                        reason = stock.get("reason", "")
                        weight = stock.get("suggested_weight", 0)
                        
                        combined_us_stocks.append({
                            "symbol": symbol,
                            "name": name,
                            "strategy": strategy
                        })
                        
                        us_analysis += f"- {name} ({symbol}): {reason} (추천 비중: {weight}%)\n"
                    
                    us_analysis += "\n"
            
            # 섹터 분석 추가
            sector_analysis = self.stock_selector.advanced_sector_selection(market="KR", sectors_count=3)
            
            # 섹터 분석 요약
            sector_summary = "📊 <b>GPT 추천 유망 산업 분석</b>\n\n"
            if "promising_sectors" in sector_analysis and sector_analysis["promising_sectors"]:
                for sector in sector_analysis["promising_sectors"]:
                    sector_name = sector.get("name")
                    growth = sector.get("growth_potential", 0)
                    key_drivers = sector.get("key_drivers", [])
                    
                    sector_summary += f"<b>· {sector_name} (성장 잠재력: {growth}/10)</b>\n"
                    sector_summary += f"  주요 성장 동력: {', '.join(key_drivers[:3])}\n\n"
                    
                    # 유망 섹터 내 종목 추천
                    sector_stocks = self.stock_selector.recommend_sector_stocks(
                        sector_name=sector_name,
                        market="KR",
                        count=2
                    )
                    
                    if "recommended_stocks" in sector_stocks and sector_stocks["recommended_stocks"]:
                        sector_summary += "  추천 종목:\n"
                        for stock in sector_stocks["recommended_stocks"]:
                            stock_symbol = stock.get("symbol")
                            stock_name = stock.get("name", stock_symbol)
                            reason = stock.get("reason", "")
                            
                            sector_summary += f"  - {stock_name} ({stock_symbol}): {reason[:50]}...\n"
                        
                        sector_summary += "\n"
            
            # 미국 섹터 분석 추가
            us_sector_analysis = self.stock_selector.advanced_sector_selection(market="US", sectors_count=3)
            
            # 미국 섹터 분석 요약
            us_sector_summary = "📊 <b>GPT 추천 유망 미국 산업 분석</b>\n\n"
            if "promising_sectors" in us_sector_analysis and us_sector_analysis["promising_sectors"]:
                for sector in us_sector_analysis["promising_sectors"]:
                    sector_name = sector.get("name")
                    growth = sector.get("growth_potential", 0)
                    key_drivers = sector.get("key_drivers", [])
                    
                    us_sector_summary += f"<b>· {sector_name} (성장 잠재력: {growth}/10)</b>\n"
                    us_sector_summary += f"  주요 성장 동력: {', '.join(key_drivers[:3])}\n\n"
                    
                    # 유망 섹터 내 종목 추천
                    sector_stocks = self.stock_selector.recommend_sector_stocks(
                        sector_name=sector_name,
                        market="US",
                        count=2
                    )
                    
                    if "recommended_stocks" in sector_stocks and sector_stocks["recommended_stocks"]:
                        us_sector_summary += "  추천 종목:\n"
                        for stock in sector_stocks["recommended_stocks"]:
                            stock_symbol = stock.get("symbol")
                            stock_name = stock.get("name", stock_symbol)
                            reason = stock.get("reason", "")
                            
                            us_sector_summary += f"  - {stock_name} ({stock_symbol}): {reason[:50]}...\n"
                        
                        us_sector_summary += "\n"
            
            # 유망 종목 config에 업데이트
            self.stock_selector.update_config_stocks(
                kr_recommendations={"recommended_stocks": combined_kr_stocks},
                us_recommendations={"recommended_stocks": combined_us_stocks}
            )
            
            # GPT 자동 매매 시스템이 있으면 종목 선정 이벤트 알림
            if self.gpt_auto_trader:
                # 종목 선정 이후 자동으로 매매 사이클 실행
                logger.info("GPT 종목 선정 완료 후 자동 매매 사이클 실행")
                self.gpt_auto_trader._select_stocks()
            
            # 종목 리스트 업데이트 확인
            updated_kr_stocks = getattr(self.config, 'KR_STOCKS', [])
            updated_us_stocks = getattr(self.config, 'US_STOCKS', [])
            
            # 종목 업데이트 요약
            update_summary = "🔄 <b>종목 리스트 업데이트</b>\n\n"
            update_summary += f"- 국내 종목: {len(updated_kr_stocks)}개\n"
            update_summary += f"- 미국 종목: {len(updated_us_stocks)}개\n\n"
            update_summary += "<i>종목 리스트가 GPT의 추천에 따라 업데이트되었습니다.</i>"
            
            # 분석 결과 전송 (길이에 따라 분할)
            self.send_notification('status', update_summary)
            self.send_notification('status', kr_analysis)
            self.send_notification('status', us_analysis)
            self.send_notification('status', sector_summary)
            self.send_notification('status', us_sector_summary)
            
            logger.info("GPT 종목 선정 및 업데이트 완료")
            
        except Exception as e:
            logger.error(f"GPT 종목 선정 중 오류 발생: {e}")
            self.send_notification('status', f"❌ GPT 종목 선정 중 오류 발생: {str(e)}")
    
    # GPT 자동 매매 실행 메서드 추가
    def run_gpt_trading_cycle(self):
        """GPT 기반 자동 매매 사이클 실행"""
        logger.info("GPT 기반 자동 매매 사이클 실행")
        
        try:
            # GPT 자동 매매 시스템이 초기화되었는지 확인
            if not self.gpt_auto_trader:
                logger.warning("GPT 자동 매매 시스템이 초기화되지 않았습니다.")
                return False
                
            # 거래 가능한 시간인지 확인 (한국 시장 또는 미국 시장 중 하나라도 열려있으면 실행)
            kr_market_status = get_market_schedule(date=None, market="KR", config=self.config)
            us_market_status = get_market_schedule(date=None, market="US", config=self.config)
            
            current_time_str = get_current_time_str(format_str='%H:%M')
            
            # 어떤 시장이라도 열려있으면 거래 실행
            if not kr_market_status['is_open'] and not us_market_status['is_open']:
                logger.info(f"현재 ({current_time_str}) 한국/미국 시장 모두 개장되지 않았습니다. GPT 매매 사이클을 건너뜁니다.")
                return False
                
            # 한국장 여부 확인
            if kr_market_status['is_open']:
                kr_open_time = kr_market_status['open_time'].strftime('%H:%M')
                kr_close_time = kr_market_status['close_time'].strftime('%H:%M')
                logger.info(f"현재 한국 시장 거래 시간: {kr_open_time}-{kr_close_time}")
                
            # 미국장 여부 확인
            if us_market_status['is_open']:
                us_open_time = convert_time(us_market_status['open_time'], from_timezone=self.config.EST, to_timezone=self.config.KST).strftime('%H:%M')
                us_close_time = convert_time(us_market_status['close_time'], from_timezone=self.config.EST, to_timezone=self.config.KST).strftime('%H:%M')
                logger.info(f"현재 미국 시장 거래 시간 (한국시간): {us_open_time}-{us_close_time}")
                
            # GPT 자동 매매 사이클 실행
            self.gpt_auto_trader.run_cycle()
            logger.info("GPT 자동 매매 사이클 완료")
            return True
            
        except Exception as e:
            logger.error(f"GPT 자동 매매 사이클 실행 중 오류 발생: {e}")
            self.send_notification('status', f"⚠️ GPT 자동 매매 오류: {str(e)}")
            return False

    def analyze_korean_stocks(self):
        """한국 주식 분석"""
        logger.info("한국 주식 분석 시작")
        
        # 시장 개장 여부 확인 (통합 시간 유틸리티 사용)
        market_status = get_market_schedule(date=None, market="KR", config=self.config)
        if not market_status['is_open']:
            current_time_str = get_current_time_str(format_str='%H:%M')
            logger.info(f"현재 한국 시장이 개장되지 않았습니다 (현재 시간: {current_time_str}). 분석을 건너뜁니다.")
            return
        else:
            open_time_str = market_status['open_time'].strftime('%H:%M')
            close_time_str = market_status['close_time'].strftime('%H:%M')
            logger.info(f"한국 시장 거래 시간: {open_time_str}-{close_time_str}")
        
        # 데이터 수집을 위한 딕셔너리 (ChatGPT 일일 리포트용)
        collected_data = {}
        
        # 데이터 업데이트
        for code in self.config.KR_STOCKS:
            try:
                # 주식 데이터 가져오기
                df = self.stock_data.get_korean_stock_data(code)
                
                if df.empty:
                    logger.warning(f"종목 {code}에 대한 데이터가 없습니다.")
                    continue
                
                # 수집된 데이터 저장 (일일 리포트용)
                collected_data[code] = df
                
                # 기술적 지표 기반 매매 시그널 분석
                signals = analyze_signals(df, code, self.config)
                
                # GPT 기반 트레이딩 전략 적용 (시장 시간에만)
                if is_market_open("KR", self.config):
                    try:
                        # GPT 기반 매매 신호 생성
                        gpt_signals = self.gpt_trading_strategy.generate_trading_signals(df, code)
                        
                        # 기존 시그널에 GPT 시그널 통합
                        if gpt_signals:
                            if not signals.get('signals'):
                                signals['signals'] = []
                                
                            for signal in gpt_signals:
                                # 중복 방지를 위해 기존 시그널과 비교
                                signal_exists = False
                                for existing_signal in signals['signals']:
                                    if (existing_signal['type'] == signal.signal_type.value and 
                                        existing_signal['date'] == signal.date.strftime("%Y-%m-%d")):
                                        signal_exists = True
                                        break
                                        
                                if not signal_exists:
                                    signals['signals'].append({
                                        'type': signal.signal_type.value,
                                        'date': signal.date.strftime("%Y-%m-%d"),
                                        'price': signal.price,
                                        'confidence': signal.confidence,
                                        'source': 'GPT-Trading-Strategy'
                                    })
                                    
                            # GPT 분석 결과가 있으면 추가
                            if any(signal.analysis for signal in gpt_signals):
                                # 가장 높은 신뢰도의 분석 내용 사용
                                best_signal = max(gpt_signals, key=lambda x: x.confidence)
                                if not signals.get('gpt_analysis') and best_signal.analysis:
                                    signals['gpt_analysis'] = best_signal.analysis
                    
                        logger.info(f"종목 {code}에 대한 GPT 매매 신호 생성 완료")
                    except Exception as e:
                        logger.error(f"종목 {code}에 대한 GPT 매매 신호 생성 중 오류 발생: {e}")
                
                # 시그널이 있으면 알림 보내기
                if signals['signals']:
                    # ChatGPT를 통한 시그널 분석
                    ai_analysis = self.chatgpt_analyzer.analyze_signals(signals)
                    signals['ai_analysis'] = ai_analysis
                    
                    # 통합 알림 전송 함수 사용
                    self.send_notification('signal', signals)
                    logger.info(f"종목 {code}에 대한 매매 시그널 감지: {len(signals['signals'])}개")
                    
                    # 자동 매매 처리 - 거래 시간 확인 후 실행
                    if self.auto_trading_enabled and self.auto_trader:
                        current_time = get_current_time(timezone=self.config.KST).time()
                        market_open = market_status['open_time'].time()
                        market_close = market_status['close_time'].time()
                        
                        # 장 마감 10분 전까지만 매매 실행 (마감 임박 매매 방지)
                        closing_time_buffer_minutes = 10
                        closing_time_buffer = market_close.replace(
                            minute=market_close.minute - closing_time_buffer_minutes if market_close.minute >= closing_time_buffer_minutes else market_close.minute,
                            hour=market_close.hour - 1 if market_close.minute < closing_time_buffer_minutes else market_close.hour
                        )
                        
                        # 거래 시간 체크 (개장 후 10분 ~ 마감 10분 전까지)
                        opening_time_buffer_minutes = 10
                        opening_time_buffer = market_open.replace(
                            minute=market_open.minute + opening_time_buffer_minutes,
                            hour=market_open.hour + 1 if market_open.minute + opening_time_buffer_minutes >= 60 else market_open.hour
                        )
                        
                        is_trading_time = (opening_time_buffer <= current_time <= closing_time_buffer)
                        
                        if is_trading_time and self.auto_trader.is_trading_allowed(code, "KR"):
                            logger.info(f"종목 {code}에 대한 자동 매매 처리 시작 (거래 시간: {current_time.strftime('%H:%M')})")
                            self.auto_trader.process_signals(signals)
                        else:
                            if not is_trading_time:
                                logger.info(f"종목 {code}에 대한 자동 매매가 최적 거래 시간({opening_time_buffer.strftime('%H:%M')}-{closing_time_buffer.strftime('%H:%M')})이 아니어서 보류됩니다.")
                            else:
                                logger.info(f"종목 {code}에 대한 자동 매매가 현재 허용되지 않습니다.")
                
                # 주기적으로 ChatGPT 상세 분석 실행 (하루에 한 번)
                # 현재 시각이 오전 10시에서 10시 30분 사이일 경우에만 실행
                current_time = now()
                if is_market_open("KR", self.config) and \
                   10 <= current_time.hour < 11 and current_time.minute < 30:
                    self._run_detailed_analysis(df, code, "KR")
                
            except Exception as e:
                logger.error(f"종목 {code} 분석 중 오류 발생: {e}")
                
        # 일일 리포트 생성 (장 마감 30분 전)
        market_schedule = get_market_schedule(date=None, market="KR", config=self.config)
        if market_schedule['is_open'] and market_schedule['close_time'] is not None:
            closing_time = market_schedule['close_time'].time()
            # datetime 직접 사용 대신 time_utils 함수 사용
            current_time = get_current_time().time()
            
            # 마감 30분 전인지 확인
            closing_time_hour = closing_time.hour
            closing_time_minute = closing_time.minute - 30
            if closing_time_minute < 0:
                closing_time_hour -= 1
                closing_time_minute += 60
            
            # 현재 시간이 마감 30분 전과 마감 시간 사이인지 확인
            is_before_close = (
                current_time.hour > closing_time_hour or 
                (current_time.hour == closing_time_hour and current_time.minute >= closing_time_minute)
            )
            is_not_closed = (
                current_time.hour < closing_time.hour or
                (current_time.hour == closing_time.hour and current_time.minute <= closing_time.minute)
            )
            
            if is_before_close and is_not_closed and collected_data:
                self._generate_market_report(collected_data, "KR")
                
        logger.info("한국 주식 분석 완료")
        
    def analyze_us_stocks(self):
        """미국 주식 분석"""
        logger.info("미국 주식 분석 시작")
        
        # 시장 개장 여부 확인 (통합 시간 유틸리티 사용)
        market_status = get_market_schedule(date=None, market="US", config=self.config)
        if not market_status['is_open']:
            current_time_str = get_current_time_str(timezone=self.config.EST, format_str='%H:%M')
            current_time_kst_str = get_current_time_str(format_str='%H:%M')
            logger.info(f"현재 미국 시장이 개장되지 않았습니다 (현재 시간 EST: {current_time_str}, KST: {current_time_kst_str}). 분석을 건너뜁니다.")
            return
        else:
            open_time_str = market_status['open_time'].strftime('%H:%M')
            close_time_str = market_status['close_time'].strftime('%H:%M')
            open_time_kst = convert_time(market_status['open_time'], from_timezone=self.config.EST, to_timezone=self.config.KST).strftime('%H:%M')
            close_time_kst = convert_time(market_status['close_time'], from_timezone=self.config.EST, to_timezone=self.config.KST).strftime('%H:%M')
            logger.info(f"미국 시장 거래 시간: {open_time_str}-{close_time_str} (EST) / {open_time_kst}-{close_time_kst} (KST)")
        
        # 데이터 수집을 위한 딕셔너리 (ChatGPT 일일 리포트용)
        collected_data = {}
        
        # 데이터 업데이트
        for symbol in self.config.US_STOCKS:
            try:
                # 주식 데이터 가져오기
                df = self.stock_data.get_us_stock_data(symbol)
                
                if df.empty:
                    logger.warning(f"종목 {symbol}에 대한 데이터가 없습니다.")
                    continue
                
                # 수집된 데이터 저장 (일일 리포트용)
                collected_data[symbol] = df
                
                # 기술적 지표 기반 매매 시그널 분석
                signals = analyze_signals(df, symbol, self.config)
                
                # GPT 기반 트레이딩 전략 적용 (시장 시간에만)
                if is_market_open("US", self.config):
                    try:
                        # GPT 기반 매매 신호 생성
                        gpt_signals = self.gpt_trading_strategy.generate_trading_signals(df, symbol)
                        
                        # 기존 시그널에 GPT 시그널 통합
                        if gpt_signals:
                            if not signals.get('signals'):
                                signals['signals'] = []
                                
                            for signal in gpt_signals:
                                # 중복 방지를 위해 기존 시그널과 비교
                                signal_exists = False
                                for existing_signal in signals['signals']:
                                    if (existing_signal['type'] == signal.signal_type.value and 
                                        existing_signal['date'] == signal.date.strftime("%Y-%m-%d")):
                                        signal_exists = True
                                        break
                                        
                                if not signal_exists:
                                    signals['signals'].append({
                                        'type': signal.signal_type.value,
                                        'date': signal.date.strftime("%Y-%m-%d"),
                                        'price': signal.price,
                                        'confidence': signal.confidence,
                                        'source': 'GPT-Trading-Strategy'
                                    })
                                    
                            # GPT 분석 결과가 있으면 추가
                            if any(signal.analysis for signal in gpt_signals):
                                # 가장 높은 신뢰도의 분석 내용 사용
                                best_signal = max(gpt_signals, key=lambda x: x.confidence)
                                if not signals.get('gpt_analysis') and best_signal.analysis:
                                    signals['gpt_analysis'] = best_signal.analysis
                    
                        logger.info(f"종목 {symbol}에 대한 GPT 매매 신호 생성 완료")
                    except Exception as e:
                        logger.error(f"종목 {symbol}에 대한 GPT 매매 신호 생성 중 오류 발생: {e}")
                
                # 시그널이 있으면 알림 보내기
                if signals['signals']:
                    # ChatGPT를 통한 시그널 분석
                    ai_analysis = self.chatgpt_analyzer.analyze_signals(signals)
                    signals['ai_analysis'] = ai_analysis
                    
                    # 통합 알림 전송 함수 사용
                    self.send_notification('signal', signals)
                    logger.info(f"종목 {symbol}에 대한 매매 시그널 감지: {len(signals['signals'])}개")
                    
                    # 자동 매매 처리 - 거래 시간 확인 후 실행
                    if self.auto_trading_enabled and self.auto_trader:
                        current_time = get_current_time(timezone=self.config.EST).time()
                        market_open = market_status['open_time'].time()
                        market_close = market_status['close_time'].time()
                        
                        # 장 마감 15분 전까지만 매매 실행 (마감 임박 매매 방지)
                        closing_time_buffer_minutes = 15  # 미국 시장은 변동성이 클 수 있어 더 보수적으로 설정
                        closing_time_buffer = market_close.replace(
                            minute=market_close.minute - closing_time_buffer_minutes if market_close.minute >= closing_time_buffer_minutes else market_close.minute,
                            hour=market_close.hour - 1 if market_close.minute < closing_time_buffer_minutes else market_close.hour
                        )
                        
                        # 거래 시간 체크 (개장 후 15분 ~ 마감 15분 전까지)
                        opening_time_buffer_minutes = 15  # 미국 시장은 개장 초기 변동성이 클 수 있어 더 보수적으로 설정
                        opening_time_buffer = market_open.replace(
                            minute=market_open.minute + opening_time_buffer_minutes,
                            hour=market_open.hour + 1 if market_open.minute + opening_time_buffer_minutes >= 60 else market_open.hour
                        )
                        
                        is_trading_time = (opening_time_buffer <= current_time <= closing_time_buffer)
                        
                        if is_trading_time and self.auto_trader.is_trading_allowed(symbol, "US"):
                            logger.info(f"종목 {symbol}에 대한 자동 매매 처리 시작 (거래 시간 EST: {current_time.strftime('%H:%M')})")
                            self.auto_trader.process_signals(signals)
                        else:
                            if not is_trading_time:
                                logger.info(f"종목 {symbol}에 대한 자동 매매가 최적 거래 시간({opening_time_buffer.strftime('%H:%M')}-{closing_time_buffer.strftime('%H:%M')}) EST가 아니어서 보류됩니다.")
                            else:
                                logger.info(f"종목 {symbol}에 대한 자동 매매가 현재 허용되지 않습니다.")
                
                # 주기적으로 ChatGPT 상세 분석 실행 (하루에 한 번)
                # 현재 시각이 오후 2시에서 2시 30분 사이일 경우에만 실행
                current_time = now()
                if is_market_open("US", self.config) and \
                   14 <= current_time.hour < 15 and current_time.minute < 30:
                    self._run_detailed_analysis(df, symbol, "US")
                
            except Exception as e:
                logger.error(f"종목 {symbol} 분석 중 오류 발생: {e}")
                
        # 일일 리포트 생성 (장 마감 30분 전)
        us_market_schedule = get_market_schedule(date=None, market="US", config=self.config)
        if us_market_schedule['is_open'] and us_market_schedule['close_time'] is not None:
            closing_time = us_market_schedule['close_time'].time()
            # 시간대 설정 - 호환성을 위해 timezone 매개변수 사용
            current_time = get_current_time(timezone=self.config.EST).time()
            
            # 마감 30분 전인지 확인
            closing_time_hour = closing_time.hour
            closing_time_minute = closing_time.minute - 30
            if closing_time_minute < 0:
                closing_time_hour -= 1
                closing_time_minute += 60
            
            # 현재 시간이 마감 30분 전과 마감 시간 사이인지 확인
            is_before_close = (
                current_time.hour > closing_time_hour or 
                (current_time.hour == closing_time_hour and current_time.minute >= closing_time_minute)
            )
            is_not_closed = (
                current_time.hour < closing_time.hour or
                (current_time.hour == closing_time.hour and current_time.minute <= closing_time.minute)
            )
            
            if is_before_close and is_not_closed and collected_data:
                self._generate_market_report(collected_data, "US")
                
        logger.info("미국 주식 분석 완료")
    
    def _run_detailed_analysis(self, df, symbol, market):
        """
        ChatGPT를 통한 상세 분석 실행
        
        Args:
            df: 주가 데이터
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
        """
        try:
            # 추가 정보 설정 (시장 정보 등)
            additional_info = {
                "market": market,
                "analysis_date": format_time(format_string="%Y-%m-%d")
            }
            
            # 종합 분석
            general_analysis = self.chatgpt_analyzer.analyze_stock(
                df, symbol, "general", additional_info
            )
            
            # 리스크 분석
            risk_analysis = self.chatgpt_analyzer.analyze_stock(
                df, symbol, "risk", additional_info
            )
            
            # 추세 분석
            trend_analysis = self.chatgpt_analyzer.analyze_stock(
                df, symbol, "trend", additional_info
            )
            
            # 전략적 제안
            recommendation = self.chatgpt_analyzer.analyze_stock(
                df, symbol, "recommendation", additional_info
            )
            
            # 결과 조합
            full_analysis = {
                "symbol": symbol,
                "market": market,
                "analysis_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "general_analysis": general_analysis["analysis"],
                "risk_analysis": risk_analysis["analysis"],
                "trend_analysis": trend_analysis["analysis"],
                "recommendation": recommendation["analysis"]
            }
            
            # 상세 분석 결과 전송
            self._send_detailed_analysis(full_analysis)
            logger.info(f"{symbol} 상세 분석 완료 및 전송")
            
        except Exception as e:
            logger.error(f"{symbol} 상세 분석 중 오류 발생: {e}")
            
    def _send_detailed_analysis(self, analysis_data):
        """
        상세 분석 결과를 텔레그램과 카카오톡으로 전송
        
        Args:
            analysis_data: 분석 결과 데이터
        """
        symbol = analysis_data["symbol"]
        market = analysis_data["market"]
        date = analysis_data["analysis_date"]
        
        # 분석 내용 형식화
        message = f"<b>📊 {symbol} 상세 분석 ({date})</b>\n\n"
        message += "<b>📈 종합 분석</b>\n"
        message += f"{analysis_data['general_analysis']}\n\n"
        
        message += "<b>⚠️ 리스크 분석</b>\n"
        message += f"{analysis_data['risk_analysis']}\n\n"
        
        message += "<b>🔍 추세 분석</b>\n"
        message += f"{analysis_data['trend_analysis']}\n\n"
        
        message += "<b>💡 전략적 제안</b>\n"
        message += f"{analysis_data['recommendation']}\n\n"
        
        message += f"<i>이 분석은 AI에 의해 자동 생성되었으며, 투자 결정의 참고 자료로만 활용하시기 바랍니다.</i>"
        
        # 메시지가 길 경우 분할 전송 (텔레그램 메시지 길이 제한 4096자)
        if len(message) > 4000:
            parts = [
                message[:message.find("\n\n<b>⚠️ 리스크 분석</b>")],
                message[message.find("<b>⚠️ 리스크 분석</b>"):message.find("\n\n<b>🔍 추세 분석</b>")],
                message[message.find("<b>🔍 추세 분석</b>"):message.find("\n\n<b>💡 전략적 제안</b>")],
                message[message.find("<b>💡 전략적 제안</b>"):]
            ]
            
            for part in parts:
                # 통합 알림 전송 함수 사용
                self.send_notification('status', part)
                time.sleep(1)  # API 제한 방지
        else:
            # 통합 알림 전송 함수 사용
            self.send_notification('status', message)
    
    def _generate_market_report(self, collected_data, market):
        """
        시장 일일 리포트 생성 및 전송
        
        Args:
            collected_data: 수집된 주가 데이터
            market: 시장 구분 ("KR" 또는 "US")
        """
        try:
            # ChatGPT 일일 리포트 생성
            daily_report = self.chatgpt_analyzer.generate_daily_report(
                market=market,
                stocks_data=collected_data
            )
            
            # 리포트 내용 전송
            self.send_notification('status', daily_report)
            logger.info(f"{market} 시장 일일 리포트 생성 및 전송 완료")
            
        except Exception as e:
            logger.error(f"{market} 시장 일일 리포트 생성 중 오류 발생: {e}")
        
    def send_daily_summary(self):
        """일일 요약 보내기"""
        logger.info("일일 요약 작성 시작")
        
        current_date = get_korean_datetime_format(include_seconds=False)
        message = f"<b>📅 {current_date} 일일 요약</b>\n\n"
        
        # 국내 주식 요약
        message += "<b>국내 종목 현황:</b>\n"
        
        for symbol in self.config.KR_STOCKS:
            data = self.stock_data.get_latest_data(symbol, market="KR")
            if data is not None:
                message += f"• {symbol}: {data['Close']:,.2f} (RSI: {data['RSI']:.2f})\n"
        
        message += "\n<b>미국 종목 현황:</b>\n"
        
        for symbol in self.config.US_STOCKS:
            data = self.stock_data.get_latest_data(symbol, market="US")
            if data is not None:
                message += f"• {symbol}: ${data['Close']:,.2f} (RSI: {data['RSI']:.2f})\n"
        
        # 자동 매매 정보 추가
        if self.auto_trading_enabled and self.auto_trader and hasattr(self.auto_trader, 'is_running') and self.auto_trader.is_running:
            message += "\n<b>자동 매매 상태:</b>\n"
            
            # 거래 요약 정보 가져오기
            trading_summary = self.auto_trader.get_trading_summary()
            
            # 오늘의 거래 정보
            if trading_summary["오늘의거래"]:
                message += "<b>오늘의 거래:</b>\n"
                for symbol, counts in trading_summary["오늘의거래"].items():
                    message += f"• {symbol}: 매수 {counts['buy']}건, 매도 {counts['sell']}건\n"
            else:
                message += "• 오늘의 거래 없음\n"
                
            # 계좌 정보
            if trading_summary["계좌정보"]:
                message += f"\n<b>계좌 잔고:</b> {trading_summary['계좌정보'].get('예수금', 0):,.0f}원\n"
                
            # 보유 종목 정보
            if trading_summary["보유종목"]:
                message += "\n<b>보유 종목:</b>\n"
                for position in trading_summary["보유종목"]:
                    profit_percentage = (position['현재가'] / position['평균단가'] - 1) * 100
                    message += f"• {position['종목명']} ({position['종목코드']}): {position['보유수량']}주, {profit_percentage:.2f}%\n"
                
        # 통합 알림 전송 함수 사용
        self.send_notification('status', message)
        logger.info("일일 요약 전송 완료")
        
    def send_investment_report(self):
        """투자 내역 종합 리포트 생성 및 전송"""
        logger.info("투자 내역 종합 리포트 생성 시작")
        
        try:
            # 자동 매매 활성화 여부 확인
            if not self.auto_trading_enabled or not self.auto_trader:
                logger.warning("자동 매매 시스템이 비활성화되어 있어 투자 리포트를 생성할 수 없습니다.")
                return
            
            # 투자 내역 종합 리포트 생성
            report = self.auto_trader.generate_investment_report()
            
            # 리포트 생성 실패 시
            if not report or "error" in report.get("account_summary", {}):
                error_msg = report.get("account_summary", {}).get("error", "알 수 없는 오류")
                logger.error(f"투자 리포트 생성 실패: {error_msg}")
                
                # 오류 알림 발송
                self.send_notification('status', f"⚠️ 투자 리포트 생성 실패: {error_msg}")
                return
            
            # 계좌 요약 정보 메시지 생성
            account_msg = "📊 <b>투자 내역 종합 리포트</b>\n\n"
            account_msg += f"<i>{report.get('formatted_date')} 기준</i>\n\n"
            account_msg += "<b>🏦 계좌 요약 정보</b>\n"
            
            account_data = report.get("account_summary", {})
            account_msg += f"• 총평가금액: {account_data.get('총평가금액', 0):,.0f}원\n"
            account_msg += f"• 주식평가금액: {account_data.get('주식평가금액', 0):,.0f}원\n"
            account_msg += f"• 예수금: {account_data.get('예수금', 0):,.0f}원\n"
            account_msg += f"• 주문가능금액: {account_data.get('주문가능금액', 0):,.0f}원\n"
            account_msg += f"• D+2예수금: {account_data.get('D+2예수금', 0):,.0f}원\n"
            account_msg += f"• 투자원금: {account_data.get('투자원금', 0):,.0f}원\n"
            account_msg += f"• 총손익: {account_data.get('총손익', 0):,.0f}원\n"
            account_msg += f"• 수익률: {account_data.get('수익률', 0):.2f}%\n"
            account_msg += f"• 보유종목수: {account_data.get('보유종목수', 0)}개\n"
            
            # 보유 종목 정보 메시지 생성
            positions_msg = "<b>📈 보유 종목 정보</b>\n"
            
            positions = report.get("positions", [])
            if positions:
                # 손익률 기준으로 내림차순 정렬 (이미 sorted)
                for position in positions:
                    positions_msg += f"• {position.get('종목명')} ({position.get('종목코드')})\n"
                    positions_msg += f"  - 보유수량: {position.get('보유수량', 0):,.0f}주\n"
                    positions_msg += f"  - 평균단가: {position.get('평균단가', 0):,.0f}원\n"
                    positions_msg += f"  - 현재가: {position.get('현재가', 0):,.0f}원\n"
                    positions_msg += f"  - 평가금액: {position.get('평가금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익금액: {position.get('손익금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익률: {position.get('손익률', 0):.2f}%\n"
                    positions_msg += f"  - 비중: {position.get('비중', 0):.2f}%\n\n"
            else:
                positions_msg += "• 보유 종목이 없습니다.\n\n"
            
            # 최근 거래 내역 메시지 생성
            trades_msg = "<b>🔄 최근 거래 내역</b>\n"
            
            recent_trades = report.get("recent_trades", [])
            if recent_trades:
                # 최근 5개 거래만 표시
                for trade in recent_trades[:5]:
                    trades_msg += f"• {trade.get('종목명')} ({trade.get('종목코드')})\n"
                    trades_msg += f"  - {trade.get('거래유형')}: {trade.get('거래수량', 0):,.0f}주\n"
                    trades_msg += f"  - 거래가격: {trade.get('거래가격', 0):,.0f}원\n"
                    trades_msg += f"  - 거래금액: {trade.get('거래금액', 0):,.0f}원\n"
                    
                    # 매도인 경우에만 손익 정보 표시
                    if trade.get('거래유형') == "매도":
                        trades_msg += f"  - 손익금액: {trade.get('손익금액', 0):,.0f}원\n"
                        trades_msg += f"  - 손익률: {trade.get('손익률', 0):.2f}%\n"
                        
                    trades_msg += f"  - 거래시간: {trade.get('거래시간')}\n\n"
            else:
                trades_msg += "• 최근 거래 내역이 없습니다.\n\n"
            
            # 월별 성과 분석 메시지 생성
            monthly_msg = "<b>📅 월별 성과 분석</b>\n"
            
            monthly_performance = report.get("monthly_performance", [])
            if monthly_performance:
                # 최근 3개월만 표시
                for month_data in monthly_performance[-3:]:
                    monthly_msg += f"• {month_data.get('연월')}\n"
                    monthly_msg += f"  - 매수금액: {month_data.get('매수금액', 0):,.0f}원\n"
                    monthly_msg += f"  - 매도금액: {month_data.get('매도금액', 0):,.0f}원\n"
                    monthly_msg += f"  - 순매수금액: {month_data.get('순매수금액', 0):,.0f}원\n"
                    monthly_msg += f"  - 손익금액: {month_data.get('손익금액', 0):,.0f}원\n"
                    monthly_msg += f"  - 거래횟수: {month_data.get('거래횟수', 0)}회\n\n"
            else:
                monthly_msg += "• 월별 성과 데이터가 없습니다.\n\n"
            
            # 섹터 분석 메시지 생성
            sector_msg = "<b>🏭 섹터 분석</b>\n"
            
            sector_analysis = report.get("sector_analysis", [])
            if sector_analysis:
                for sector in sector_analysis:
                    sector_msg += f"• {sector.get('섹터명')}\n"
                    sector_msg += f"  - 종목수: {sector.get('종목수', 0)}개\n"
                    sector_msg += f"  - 평가금액: {sector.get('평가금액', 0):,.0f}원\n"
                    sector_msg += f"  - 손익금액: {sector.get('손익금액', 0):,.0f}원\n"
                    sector_msg += f"  - 비중: {sector.get('비중', 0):.2f}%\n"
                    sector_msg += f"  - 수익률: {sector.get('수익률', 0):.2f}%\n\n"
            else:
                sector_msg += "• 섹터 분석 데이터가 없습니다.\n\n"
            
            # 투자 추천 메시지 생성
            recommendations_msg = "<b>💡 투자 추천</b>\n"
            
            recommendations = report.get("recommendations", [])
            if recommendations:
                for rec in recommendations:
                    recommendations_msg += f"• {rec.get('종목명')} ({rec.get('종목코드')})\n"
                    recommendations_msg += f"  - 추천: {rec.get('추천')}\n"
                    recommendations_msg += f"  - 사유: {rec.get('사유')}\n\n"
            else:
                recommendations_msg += "• 현재 투자 추천이 없습니다.\n\n"
            
            # 면책조항 추가
            disclaimer_msg = "<i>※ 이 리포트는 자동으로 생성된 정보로, 투자 결정에 참고자료로만 활용하시길 권장드립니다. 투자는 본인의 판단과 책임하에 진행하시기 바랍니다.</i>"
            
            # 메시지를 나눠서 전송 (텔레그램 메시지 길이 제한 때문)
            self.send_notification('status', account_msg)
            time.sleep(1)  # API 제한 방지
            self.send_notification('status', positions_msg)
            time.sleep(1)
            self.send_notification('status', trades_msg)
            time.sleep(1)
            self.send_notification('status', monthly_msg)
            time.sleep(1)
            self.send_notification('status', sector_msg)
            time.sleep(1)
            self.send_notification('status', recommendations_msg + disclaimer_msg)
            
            logger.info("투자 내역 종합 리포트 전송 완료")
            
        except Exception as e:
            logger.error(f"투자 내역 종합 리포트 전송 중 오류 발생: {e}")
            self.send_notification('status', f"⚠️ 투자 리포트 전송 중 오류 발생: {str(e)}")
    
    def send_investment_report_kr(self):
        """한국 시장 투자 내역 종합 리포트 생성 및 전송"""
        logger.info("한국 시장 투자 내역 종합 리포트 생성 시작")
        
        try:
            # 자동 매매 활성화 여부 확인
            if not self.auto_trading_enabled or not self.auto_trader:
                logger.warning("자동 매매 시스템이 비활성화되어 있어 투자 리포트를 생성할 수 없습니다.")
                return
            
            # 투자 내역 종합 리포트 생성
            report = self.auto_trader.generate_investment_report()
            
            # 리포트 생성 실패 시
            if not report or "error" in report.get("account_summary", {}):
                error_msg = report.get("account_summary", {}).get("error", "알 수 없는 오류")
                logger.error(f"한국 시장 투자 리포트 생성 실패: {error_msg}")
                self.send_notification('status', f"⚠️ 한국 시장 투자 리포트 생성 실패: {error_msg}")
                return
            
            # 계좌 요약 정보 메시지 생성
            account_msg = "📊 <b>한국 시장 투자 내역 종합 리포트</b>\n\n"
            account_msg += f"<i>{report.get('formatted_date')} 기준</i>\n\n"
            account_msg += "<b>🏦 계좌 요약 정보</b>\n"
            
            account_data = report.get("account_summary", {})
            account_msg += f"• 총평가금액: {account_data.get('총평가금액', 0):,.0f}원\n"
            account_msg += f"• 주식평가금액: {account_data.get('주식평가금액', 0):,.0f}원\n"
            account_msg += f"• 예수금: {account_data.get('예수금', 0):,.0f}원\n"
            account_msg += f"• 주문가능금액: {account_data.get('주문가능금액', 0):,.0f}원\n"
            account_msg += f"• D+2예수금: {account_data.get('D+2예수금', 0):,.0f}원\n"
            account_msg += f"• 투자원금: {account_data.get('투자원금', 0):,.0f}원\n"
            account_msg += f"• 총손익: {account_data.get('총손익', 0):,.0f}원\n"
            account_msg += f"• 수익률: {account_data.get('수익률', 0):.2f}%\n"
            account_msg += f"• 보유종목수: {account_data.get('보유종목수', 0)}개\n"
            
            # 보유 종목 정보 메시지 생성 (한국 시장 종목만)
            positions_msg = "<b>📈 한국 보유 종목 정보</b>\n"
            
            positions = []
            for pos in report.get("positions", []):
                symbol = pos.get('종목코드', '')
                # 한국 주식 코드는 보통 6자리 숫자 (정규식으로 필터링)
                if re.match(r'^\d{6}$', symbol):
                    positions.append(pos)
            
            if positions:
                # 손익률 기준으로 내림차순 정렬
                positions.sort(key=lambda x: x.get('손익률', 0), reverse=True)
                
                for position in positions:
                    positions_msg += f"• {position.get('종목명')} ({position.get('종목코드')})\n"
                    positions_msg += f"  - 보유수량: {position.get('보유수량', 0):,.0f}주\n"
                    positions_msg += f"  - 평균단가: {position.get('평균단가', 0):,.0f}원\n"
                    positions_msg += f"  - 현재가: {position.get('현재가', 0):,.0f}원\n"
                    positions_msg += f"  - 평가금액: {position.get('평가금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익금액: {position.get('손익금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익률: {position.get('손익률', 0):.2f}%\n"
                    positions_msg += f"  - 비중: {position.get('비중', 0):.2f}%\n\n"
            else:
                positions_msg += "• 한국 보유 종목이 없습니다.\n\n"
            
            # 최근 거래 내역 메시지 생성 (한국 시장 거래만)
            trades_msg = "<b>🔄 최근 한국 시장 거래 내역</b>\n"
            
            recent_trades = []
            for trade in report.get("recent_trades", []):
                symbol = trade.get('종목코드', '')
                # 한국 주식 코드는 보통 6자리 숫자
                if re.match(r'^\d{6}$', symbol):
                    recent_trades.append(trade)
                    
            if recent_trades:
                # 최근 5개 거래만 표시
                for trade in recent_trades[:5]:
                    trades_msg += f"• {trade.get('종목명')} ({trade.get('종목코드')})\n"
                    trades_msg += f"  - {trade.get('거래유형')}: {trade.get('거래수량', 0):,.0f}주\n"
                    trades_msg += f"  - 거래가격: {trade.get('거래가격', 0):,.0f}원\n"
                    trades_msg += f"  - 거래금액: {trade.get('거래금액', 0):,.0f}원\n"
                    
                    # 매도인 경우에만 손익 정보 표시
                    if trade.get('거래유형') == "매도":
                        trades_msg += f"  - 손익금액: {trade.get('손익금액', 0):,.0f}원\n"
                        trades_msg += f"  - 손익률: {trade.get('손익률', 0):.2f}%\n"
                        
                    trades_msg += f"  - 거래시간: {trade.get('거래시간')}\n\n"
            else:
                trades_msg += "• 최근 한국 시장 거래 내역이 없습니다.\n\n"
            
            # 섹터 분석 메시지 생성 (한국 시장 종목에 대해서만)
            sector_msg = "<b>🏭 한국 시장 섹터 분석</b>\n"
            
            sector_analysis = report.get("sector_analysis", [])
            if sector_analysis:
                for sector in sector_analysis:
                    sector_msg += f"• {sector.get('섹터명')}\n"
                    sector_msg += f"  - 종목수: {sector.get('종목수', 0)}개\n"
                    sector_msg += f"  - 평가금액: {sector.get('평가금액', 0):,.0f}원\n"
                    sector_msg += f"  - 손익금액: {sector.get('손익금액', 0):,.0f}원\n"
                    sector_msg += f"  - 비중: {sector.get('비중', 0):.2f}%\n"
                    sector_msg += f"  - 수익률: {sector.get('수익률', 0):.2f}%\n\n"
            else:
                sector_msg += "• 섹터 분석 데이터가 없습니다.\n\n"
            
            # 한국 시장 종목에 대한 투자 추천 필터링
            kr_recommendations = []
            for rec in report.get("recommendations", []):
                symbol = rec.get('종목코드', '')
                if re.match(r'^\d{6}$', symbol):
                    kr_recommendations.append(rec)
            
            # 투자 추천 메시지 생성
            recommendations_msg = "<b>💡 한국 종목 투자 추천</b>\n"
            
            if kr_recommendations:
                for rec in kr_recommendations:
                    recommendations_msg += f"• {rec.get('종목명')} ({rec.get('종목코드')})\n"
                    recommendations_msg += f"  - 추천: {rec.get('추천')}\n"
                    recommendations_msg += f"  - 사유: {rec.get('사유')}\n\n"
            else:
                recommendations_msg += "• 현재 한국 종목 투자 추천이 없습니다.\n\n"
            
            # 면책조항 추가
            disclaimer_msg = "<i>※ 이 리포트는 자동으로 생성된 정보로, 투자 결정에 참고자료로만 활용하시길 권장드립니다. 투자는 본인의 판단과 책임하에 진행하시기 바랍니다.</i>"
            
            # 메시지를 나눠서 전송 (텔레그램 메시지 길이 제한 때문)
            self.send_notification('status', account_msg)
            time.sleep(1)  # API 제한 방지
            self.send_notification('status', positions_msg)
            time.sleep(1)
            self.send_notification('status', trades_msg)
            time.sleep(1)
            self.send_notification('status', sector_msg)
            time.sleep(1)
            self.send_notification('status', recommendations_msg + disclaimer_msg)
            
            logger.info("한국 시장 투자 내역 종합 리포트 전송 완료")
            
        except Exception as e:
            logger.error(f"한국 시장 투자 내역 종합 리포트 전송 중 오류 발생: {e}")
            self.send_notification('status', f"⚠️ 한국 시장 투자 리포트 전송 중 오류 발생: {str(e)}")

    def send_investment_report_us(self):
        """미국 시장 투자 내역 종합 리포트 생성 및 전송"""
        logger.info("미국 시장 투자 내역 종합 리포트 생성 시작")
        
        try:
            # 자동 매매 활성화 여부 확인
            if not self.auto_trading_enabled or not self.auto_trader:
                logger.warning("자동 매매 시스템이 비활성화되어 있어 투자 리포트를 생성할 수 없습니다.")
                return
            
            # 투자 내역 종합 리포트 생성
            report = self.auto_trader.generate_investment_report()
            
            # 리포트 생성 실패 시
            if not report or "error" in report.get("account_summary", {}):
                error_msg = report.get("account_summary", {}).get("error", "알 수 없는 오류")
                logger.error(f"미국 시장 투자 리포트 생성 실패: {error_msg}")
                self.send_notification('status', f"⚠️ 미국 시장 투자 리포트 생성 실패: {error_msg}")
                return
            
            # 계좌 요약 정보 메시지 생성
            account_msg = "📊 <b>미국 시장 투자 내역 종합 리포트</b>\n\n"
            account_msg += f"<i>{report.get('formatted_date')} 기준</i>\n\n"
            account_msg += "<b>🏦 계좌 요약 정보</b>\n"
            
            account_data = report.get("account_summary", {})
            account_msg += f"• 총평가금액: {account_data.get('총평가금액', 0):,.0f}원\n"
            account_msg += f"• 주식평가금액: {account_data.get('주식평가금액', 0):,.0f}원\n"
            account_msg += f"• 예수금: {account_data.get('예수금', 0):,.0f}원\n"
            account_msg += f"• 주문가능금액: {account_data.get('주문가능금액', 0):,.0f}원\n"
            account_msg += f"• 투자원금: {account_data.get('투자원금', 0):,.0f}원\n"
            account_msg += f"• 총손익: {account_data.get('총손익', 0):,.0f}원\n"
            account_msg += f"• 수익률: {account_data.get('수익률', 0):.2f}%\n"
            account_msg += f"• 보유종목수: {account_data.get('보유종목수', 0)}개\n"
            
            # 보유 종목 정보 메시지 생성 (미국 시장 종목만)
            positions_msg = "<b>📈 미국 보유 종목 정보</b>\n"
            
            positions = []
            for pos in report.get("positions", []):
                symbol = pos.get('종목코드', '')
                # 미국 주식 코드는 보통 알파벳으로만 이루어짐
                if not re.match(r'^\d{6}$', symbol) and symbol:  # 6자리 숫자가 아니면 미국 종목으로 간주
                    positions.append(pos)
            
            if positions:
                # 손익률 기준으로 내림차순 정렬
                positions.sort(key=lambda x: x.get('손익률', 0), reverse=True)
                
                for position in positions:
                    positions_msg += f"• {position.get('종목명')} ({position.get('종목코드')})\n"
                    positions_msg += f"  - 보유수량: {position.get('보유수량', 0):,.0f}주\n"
                    positions_msg += f"  - 평균단가: ${position.get('평균단가', 0)/100:,.2f}\n"
                    positions_msg += f"  - 현재가: ${position.get('현재가', 0)/100:,.2f}\n"
                    positions_msg += f"  - 평가금액: {position.get('평가금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익금액: {position.get('손익금액', 0):,.0f}원\n"
                    positions_msg += f"  - 손익률: {position.get('손익률', 0):.2f}%\n"
                    positions_msg += f"  - 비중: {position.get('비중', 0):.2f}%\n\n"
            else:
                positions_msg += "• 미국 보유 종목이 없습니다.\n\n"
            
            # 최근 거래 내역 메시지 생성 (미국 시장 거래만)
            trades_msg = "<b>🔄 최근 미국 시장 거래 내역</b>\n"
            
            recent_trades = []
            for trade in report.get("recent_trades", []):
                symbol = trade.get('종목코드', '')
                # 미국 주식 코드는 보통 알파벳으로만 이루어짐
                if not re.match(r'^\d{6}$', symbol) and symbol:
                    recent_trades.append(trade)
                    
            if recent_trades:
                # 최근 5개 거래만 표시
                for trade in recent_trades[:5]:
                    trades_msg += f"• {trade.get('종목명')} ({trade.get('종목코드')})\n"
                    trades_msg += f"  - {trade.get('거래유형')}: {trade.get('거래수량', 0):,.0f}주\n"
                    trades_msg += f"  - 거래가격: ${trade.get('거래가격', 0)/100:,.2f}\n"
                    trades_msg += f"  - 거래금액: {trade.get('거래금액', 0):,.0f}원\n"
                    
                    # 매도인 경우에만 손익 정보 표시
                    if trade.get('거래유형') == "매도":
                        trades_msg += f"  - 손익금액: {trade.get('손익금액', 0):,.0f}원\n"
                        trades_msg += f"  - 손익률: {trade.get('손익률', 0):.2f}%\n"
                        
                    trades_msg += f"  - 거래시간: {trade.get('거래시간')}\n\n"
            else:
                trades_msg += "• 최근 미국 시장 거래 내역이 없습니다.\n\n"
            
            # 미국 시장 종목에 대한 투자 추천 필터링
            us_recommendations = []
            for rec in report.get("recommendations", []):
                symbol = rec.get('종목코드', '')
                if not re.match(r'^\d{6}$', symbol) and symbol:
                    us_recommendations.append(rec)
            
            # 투자 추천 메시지 생성
            recommendations_msg = "<b>💡 미국 종목 투자 추천</b>\n"
            
            if us_recommendations:
                for rec in us_recommendations:
                    recommendations_msg += f"• {rec.get('종목명')} ({rec.get('종목코드')})\n"
                    recommendations_msg += f"  - 추천: {rec.get('추천')}\n"
                    recommendations_msg += f"  - 사유: {rec.get('사유')}\n\n"
            else:
                recommendations_msg += "• 현재 미국 종목 투자 추천이 없습니다.\n\n"
            
            # 면책조항 추가
            disclaimer_msg = "<i>※ 이 리포트는 자동으로 생성된 정보로, 투자 결정에 참고자료로만 활용하시길 권장드립니다. 투자는 본인의 판단과 책임하에 진행하시기 바랍니다.</i>"
            
            # 메시지를 나눠서 전송 (텔레그램 메시지 길이 제한 때문)
            self.send_notification('status', account_msg)
            time.sleep(1)  # API 제한 방지
            self.send_notification('status', positions_msg)
            time.sleep(1)
            self.send_notification('status', trades_msg)
            time.sleep(1)
            self.send_notification('status', recommendations_msg + disclaimer_msg)
            
            logger.info("미국 시장 투자 내역 종합 리포트 전송 완료")
            
        except Exception as e:
            logger.error(f"미국 시장 투자 내역 종합 리포트 전송 중 오류 발생: {e}")
            self.send_notification('status', f"⚠️ 미국 시장 투자 리포트 전송 중 오류 발생: {str(e)}")
    
    def start(self):
        """시스템 시작"""
        if self.is_running:
            logger.warning("시스템이 이미 실행 중입니다.")
            return
            
        self.is_running = True
        logger.info("AI 주식 분석 시스템 시작")
        
        # 종목 리스트 체크 및 초기화
        self._initialize_stock_lists()
        
        # 자동 매매 시스템 시작
        trade_status = "비활성화"
        gpt_trade_status = "비활성화"
        
        if self.auto_trading_enabled and self.auto_trader:
            self.auto_trader.start_trading_session()
            trade_status = "활성화" if self.auto_trader.is_running else "비활성화"
            logger.info(f"자동 매매 시스템 상태: {trade_status}")
            
            # GPT 자동 매매 시스템 시작
            if self.gpt_auto_trader:
                self.gpt_auto_trader.start()
                gpt_trade_status = "활성화" if self.gpt_auto_trader.is_running else "비활성화"
                logger.info(f"GPT 기반 자동 매매 시스템 상태: {gpt_trade_status}")
            
            # 강제 시장 열림 설정이 활성화되어 있으면, 매매 사이클 즉시 실행
            if hasattr(self.config, 'FORCE_MARKET_OPEN') and self.config.FORCE_MARKET_OPEN:
                logger.info("강제 시장 열림 설정이 활성화되어 있습니다. 즉시 매매 사이클을 실행합니다.")
                try:
                    # 즉시 매매 사이클 실행
                    self.auto_trader.run_trading_cycle()
                    logger.info("초기 매매 사이클 실행 완료")
                    
                    # GPT 기반 매매 사이클도 실행
                    if self.gpt_auto_trader:
                        self.gpt_auto_trader.run_cycle()
                        logger.info("초기 GPT 매매 사이클 실행 완료")
                except Exception as e:
                    logger.error(f"초기 매매 사이클 실행 중 오류 발생: {e}")
        
        # 카카오톡 초기화 상태 확인
        kakao_status = "활성화" if self.use_kakao and self.kakao_sender and self.kakao_sender.initialized else "비활성화"
        logger.info(f"카카오톡 알림 상태: {kakao_status}")
        
        # 시스템 시작 메시지 작성
        start_time = get_current_time_str(format_str='%Y-%m-%d %H:%M:%S')
        start_msg = f"🚀 AI 주식 분석 시스템 시작 ({start_time})\n\n"
        start_msg += f"• 자동 매매 기능: {trade_status}\n"
        start_msg += f"• GPT 자동 매매: {gpt_trade_status}\n"
        start_msg += f"• 카카오톡 알림: {kakao_status}\n"
        start_msg += f"• 분석 주기: 30분\n"
        start_msg += f"• 모니터링 종목 수: 국내 {len(self.config.KR_STOCKS)}개, 미국 {len(self.config.US_STOCKS)}개\n"
        
        # GitHut Actions 환경인지 확인
        is_github_actions = 'GITHUB_ACTIONS' in os.environ
        if is_github_actions:
            start_msg += "• GitHub Actions 환경에서 실행 중\n"
            # GitHub 런타임/워크플로우 정보 추가
            if 'GITHUB_WORKFLOW' in os.environ:
                start_msg += f"• 워크플로우: {os.environ.get('GITHUB_WORKFLOW')}\n"
            if 'GITHUB_RUN_ID' in os.environ:
                start_msg += f"• 실행 ID: {os.environ.get('GITHUB_RUN_ID')}\n"
            if 'GITHUB_REPOSITORY' in os.environ:
                start_msg += f"• 저장소: {os.environ.get('GITHUB_REPOSITORY')}\n"
            
            logger.info("GitHub Actions 환경에서 실행 중입니다.")
            
            # 서버 IP 정보 추가 시도
            try:
                import socket
                hostname = socket.gethostname()
                ip_address = socket.gethostbyname(hostname)
                start_msg += f"• 서버 정보: {hostname} ({ip_address})\n"
            except Exception as e:
                logger.error(f"IP 정보 조회 실패: {e}")
                
            # 시스템 리소스 정보 추가
            try:
                import psutil
                memory = psutil.virtual_memory()
                cpu_usage = psutil.cpu_percent(interval=1)
                disk = psutil.disk_usage('/')
                start_msg += f"• CPU 사용률: {cpu_usage}%\n"
                start_msg += f"• 메모리: {memory.percent}% (사용 중: {memory.used/1024/1024/1024:.1f}GB)\n"
                start_msg += f"• 디스크: {disk.percent}% (여유: {disk.free/1024/1024/1024:.1f}GB)\n"
            except ImportError:
                logger.warning("psutil 패키지가 설치되어 있지 않아 시스템 정보를 가져올 수 없습니다.")
            except Exception as e:
                logger.error(f"시스템 정보 조회 실패: {e}")
        
        # 카카오톡이 초기화되지 않았다면 강제 재초기화 시도
        if self.use_kakao and self.kakao_sender and not self.kakao_sender.initialized:
            logger.info("카카오톡 알림 서비스 재초기화 시도")
            try:
                reinit_success = self.kakao_sender.initialize()
                if reinit_success:
                    logger.info("카카오톡 재초기화 성공")
                    kakao_status = "활성화"
                    start_msg += "• 카카오톡 재연결 성공\n"
                else:
                    logger.warning("카카오톡 재초기화 실패")
                    start_msg += "• 카카오톡 재연결 실패\n"
            except Exception as e:
                logger.error(f"카카오톡 재초기화 중 오류: {e}")
                start_msg += "• 카카오톡 재연결 오류\n"
        
        # OpenAI API 키 유효성 체크
        if hasattr(self.config, 'OPENAI_API_KEY') and self.stock_selector.is_api_key_valid():
            start_msg += "• OpenAI API 키: 유효함\n"
            logger.info("OpenAI API 키가 유효합니다.")
        else:
            start_msg += "• OpenAI API 키: 유효하지 않음 (캐시된 종목 목록 사용)\n"
            logger.warning("OpenAI API 키가 유효하지 않습니다. 캐시된 종목 목록을 사용합니다.")
        
        # 텔레그램으로 우선 시스템 시작 알림 전송
        try:
            self.telegram_sender.send_system_status(start_msg)
            logger.info("텔레그램 시작 메시지 전송 성공")
        except Exception as e:
            logger.error(f"텔레그램 시작 메시지 전송 실패: {e}")
        
        # 카카오톡으로 별도 전송 시도 (조건이 충족될 경우)
        if self.use_kakao and self.kakao_sender:
            try:
                # 환경 변수 설정 확인 (디버깅용)
                if is_github_actions:
                    logger.info(f"GitHub Actions: KAKAO_API_KEY={os.environ.get('KAKAO_API_KEY') is not None}, KAKAO_ACCESS_TOKEN={os.environ.get('KAKAO_ACCESS_TOKEN') is not None}")
                    
                # 직접 메시지 전송 시도 (HTML 태그 제거)
                clean_message = start_msg
                if '<' in start_msg and '>' in start_msg:
                    clean_message = re.sub(r'<[^>]*>', '', start_msg)
                
                # 서버 시작 알림에 대한 특별한 메시지 포맷 (아이콘 추가)
                server_start_message = f"🖥️ 서버 시작 알림\n\n{clean_message}"
                self.kakao_sender.send_message(server_start_message)
                logger.info("카카오톡 시작 메시지 전송 성공")
            except Exception as e:
                logger.error(f"카카오톡 시작 메시지 전송 실패: {e}")
                # 필요에 따라 추가 정보 로깅
                if hasattr(self.kakao_sender, 'access_token') and self.kakao_sender.access_token:
                    token_preview = f"{self.kakao_sender.access_token[:5]}...{self.kakao_sender.access_token[-5:]}"
                    logger.debug(f"액세스 토큰 미리보기: {token_preview}")
        
        # 초기 데이터 수집
        self.stock_data.update_all_data()
        
        # 스케줄 설정
        # 국내 주식: 30분 간격으로 분석 (장 중에만)
        schedule.every(30).minutes.do(self.analyze_korean_stocks)
        
        # 미국 주식: 30분 간격으로 분석 (장 중에만)
        schedule.every(30).minutes.do(self.analyze_us_stocks)
        
        # 일일 요약: 매일 저녁 6시
        schedule.every().day.at("18:00").do(self.send_daily_summary)
        
        # GPT 종목 선정: 매일 오전 8시 30분 (한국 시장 오픈 전)
        schedule.every().day.at("08:30").do(self.select_stocks_with_gpt)
        
        # GPT 자동 매매: 30분 간격으로 실행
        gpt_trading_interval = getattr(self.config, 'GPT_TRADING_MONITOR_INTERVAL', 30)
        schedule.every(gpt_trading_interval).minutes.do(self.run_gpt_trading_cycle)
        
        # 투자 내역 종합 리포트: 국내장 마감 직후 (15:40)와 미국장 마감 직후 (06:10) 전송
        schedule.every().day.at("15:40").do(self.send_investment_report_kr)  # 한국장 마감 직후
        schedule.every().day.at("06:10").do(self.send_investment_report_us)  # 미국장 마감 직후 (한국시간)
        
        # 메인 루프
        try:
            # 시스템 시작 시 한 번 종목 선정 실행 (API 키가 유효한 경우)
            if hasattr(self.config, 'OPENAI_API_KEY') and self.stock_selector.is_api_key_valid():
                logger.info("시스템 시작 시 종목 선정 시작")
                self.select_stocks_with_gpt()
            else:
                logger.warning("OpenAI API 키가 유효하지 않아 시작 시 종목 선정을 건너뜁니다.")
            
            # 무한 루프 - 프로그램이 종료되지 않도록 유지
            logger.info("매매 시스템 메인 루프 시작 (Ctrl+C로 종료)")
            while self.is_running:
                schedule.run_pending()
                
                # 강제 시장 열림 설정이 활성화되어 있으면, 주기적으로 매매 사이클 실행
                if hasattr(self.config, 'FORCE_MARKET_OPEN') and self.config.FORCE_MARKET_OPEN and self.auto_trading_enabled:
                    try:
                        # 일반 매매 사이클 실행
                        if self.auto_trader:
                            self.auto_trader.run_trading_cycle()
                            logger.info("매매 사이클 실행 완료 (강제 실행 모드)")
                        
                        # GPT 자동 매매 사이클 실행
                        if self.gpt_auto_trader:
                            self.gpt_auto_trader.run_cycle()
                            logger.info("GPT 매매 사이클 실행 완료 (강제 실행 모드)")
                    except Exception as e:
                        logger.error(f"매매 사이클 실행 중 오류 발생: {e}")
                
                # 60초 대기
                time.sleep(60)
                logger.info("매매 시스템 실행 중... (1분 간격 체크)")
                
        except KeyboardInterrupt:
            logger.info("사용자에 의해 시스템 종료")
            self.stop()
            
        except Exception as e:
            logger.error(f"시스템 실행 중 오류 발생: {e}")
            self.stop()
    
    def _initialize_stock_lists(self):
        """종목 리스트 초기화 및 확인"""
        # 데이터베이스에서 종목 정보를 불러오기
        from src.database.db_manager import DatabaseManager
        db_manager = DatabaseManager.get_instance(self.config)
        
        # DB 초기화 및 기본 종목 정보 설정 (첫 실행 시에만)
        db_manager.init_kr_stock_info()
        
        # 데이터베이스에서 종목 정보 불러오기
        kr_stock_info = db_manager.get_kr_stock_info()
        
        if kr_stock_info:
            # 데이터베이스에서 불러온 종목 정보로 설정
            self.config.KR_STOCK_INFO = kr_stock_info
            self.config.KR_STOCKS = [stock["code"] for stock in kr_stock_info]
            logger.info(f"데이터베이스에서 한국 종목 정보 {len(kr_stock_info)}개를 불러왔습니다.")
            return
            
        # 데이터베이스에 정보가 없으면 기존 로직 실행
        kr_stocks = getattr(self.config, 'KR_STOCKS', [])
        us_stocks = getattr(self.config, 'US_STOCKS', [])
        
        logger.info(f"현재 종목 리스트 상태: KR={len(kr_stocks)}개, US={len(us_stocks)}개")
        
        if not kr_stocks or not us_stocks:
            logger.warning("종목 리스트가 비어 있습니다. 캐시된 종목 목록을 로드합니다.")
            
            # 캐시 디렉토리 생성
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            
            # 한국 종목 로드
            if not kr_stocks:
                kr_cache_file = os.path.join(cache_dir, 'kr_stock_recommendations.json')
                if os.path.exists(kr_cache_file):
                    try:
                        with open(kr_cache_file, 'r', encoding='utf-8') as f:
                            kr_data = json.load(f)
                        
                        if "recommended_stocks" in kr_data:
                            kr_stock_info = []
                            kr_stock_codes = []
                            
                            for stock in kr_data["recommended_stocks"]:
                                symbol = stock.get("symbol", "")
                                name = stock.get("name", symbol)
                                
                                # 종목코드 정리 (숫자만 추출)
                                if '(' in symbol:
                                    symbol = symbol.split('(')[0]
                                
                                kr_stock_codes.append(symbol)
                                kr_stock_info.append({"code": symbol, "name": name})
                            
                            # 설정 업데이트
                            if kr_stock_codes:
                                self.config.KR_STOCKS = kr_stock_codes
                                self.config.KR_STOCK_INFO = kr_stock_info
                                logger.info(f"캐시에서 한국 종목 {len(kr_stock_codes)}개를 로드했습니다.")
                                
                                # 데이터베이스에 저장
                                db_manager.save_kr_stock_info(kr_stock_info)
                                logger.info(f"한국 종목 정보 {len(kr_stock_info)}개를 데이터베이스에 저장했습니다.")
                    except Exception as e:
                        logger.error(f"한국 종목 캐시 로드 실패: {e}")
                
                # 캐시 파일도 없으면 기본값 설정
                if not getattr(self.config, 'KR_STOCKS', []):
                    default_kr_stocks = [
                        {"code": "005930", "name": "삼성전자"},
                        {"code": "000660", "name": "SK하이닉스"},
                        {"code": "051910", "name": "LG화학"},
                        {"code": "035420", "name": "NAVER"},
                        {"code": "096770", "name": "SK이노베이션"},
                        {"code": "005380", "name": "현대차"}
                    ]
                    
                    self.config.KR_STOCK_INFO = default_kr_stocks
                    self.config.KR_STOCKS = [stock["code"] for stock in default_kr_stocks]
                    logger.info(f"기본 한국 종목 {len(self.config.KR_STOCKS)}개를 설정했습니다.")
                    
                    # 데이터베이스에 저장
                    db_manager.save_kr_stock_info(default_kr_stocks)
                    logger.info(f"기본 한국 종목 정보 {len(default_kr_stocks)}개를 데이터베이스에 저장했습니다.")
            
            # 미국 종목 로드
            if not us_stocks:
                us_cache_file = os.path.join(cache_dir, 'us_stock_recommendations.json')
                if os.path.exists(us_cache_file):
                    try:
                        with open(us_cache_file, 'r', encoding='utf-8') as f:
                            us_data = json.load(f)
                        
                        if "recommended_stocks" in us_data:
                            us_stock_info = []
                            us_stock_codes = []
                            
                            for stock in us_data["recommended_stocks"]:
                                symbol = stock.get("symbol", "")
                                name = stock.get("name", symbol)
                                
                                # 종목코드 정리 (괄호 제거)
                                if '(' in symbol:
                                    symbol = symbol.split('(')[0]
                                
                                us_stock_codes.append(symbol)
                                us_stock_info.append({"code": symbol, "name": name})
                            
                            # 설정 업데이트
                            if us_stock_codes:
                                self.config.US_STOCKS = us_stock_codes
                                self.config.US_STOCK_INFO = us_stock_info
                                logger.info(f"캐시에서 미국 종목 {len(us_stock_codes)}개를 로드했습니다.")
                    except Exception as e:
                        logger.error(f"미국 종목 캐시 로드 실패: {e}")
                
                # 캐시 파일도 없으면 기본값 설정
                if not getattr(self.config, 'US_STOCKS', []):
                    default_us_stocks = [
                        {"code": "AAPL", "name": "Apple Inc."},
                        {"code": "MSFT", "name": "Microsoft Corporation"},
                        {"code": "GOOGL", "name": "Alphabet Inc."},
                        {"code": "AMZN", "name": "Amazon.com Inc."},
                        {"code": "META", "name": "Meta Platforms Inc."}
                    ]
                    
                    self.config.US_STOCK_INFO = default_us_stocks
                    self.config.US_STOCKS = [stock["code"] for stock in default_us_stocks]
                    logger.info(f"기본 미국 종목 {len(self.config.US_STOCKS)}개를 설정했습니다.")
    
    def stop(self):
        """시스템 종료"""
        if not self.is_running:
            logger.warning("시스템이 이미 종료되었습니다.")
            return
            
        self.is_running = False
        
        # 자동 매매 시스템 종료
        if self.auto_trading_enabled and self.auto_trader and hasattr(self.auto_trader, 'stop_trading_session'):
            self.auto_trader.stop_trading_session()
            
        # GPT 자동 매매 시스템 종료
        if self.gpt_auto_trader and hasattr(self.gpt_auto_trader, 'stop'):
            self.gpt_auto_trader.stop()
            
        logger.info("AI 주식 분석 시스템 종료")
        
        # 종료 메시지 전송 시도
        try:
            # 종료 시간과 활성 세션 시간 계산
            end_time = get_current_time_str(format_str='%Y-%m-%d %H:%M:%S')
            message = f"🛑 AI 주식 분석 시스템 종료 ({end_time})"
            self.send_notification('status', message)
        except Exception as e:
            logger.error(f"종료 메시지 전송 실패: {e}")
    
    def force_select_stocks(self):
        """단타매매와 급등주 감지 모드를 위한 종목 강제 재선정"""
        logger.info("단타매매/급등주 감지 모드를 위한 종목 강제 재선정 시작")
        
        # GPT 자동 매매 시스템이 초기화되었는지 확인
        if not self.gpt_auto_trader:
            logger.warning("GPT 자동 매매 시스템이 초기화되지 않았습니다.")
            return False
        
        # GPT 트레이딩 전략이 초기화되었는지 확인
        if not self.gpt_trading_strategy:
            logger.warning("GPT 트레이딩 전략이 초기화되지 않았습니다.")
            return False
        
        try:
            # 마지막 종목 선정 시간 강제 초기화
            if hasattr(self.gpt_auto_trader, 'last_selection_time'):
                self.gpt_auto_trader.last_selection_time = None
                logger.info("마지막 종목 선정 시간 초기화 완료")
            
            # 종목 선정 강제 실행
            self.gpt_auto_trader._select_stocks()
            logger.info("강제 종목 선정 실행 완료")
            
            # 알림 전송
            self.send_notification('status', "🔄 단타매매/급등주 감지를 위한 종목 강제 재선정이 완료되었습니다.")
            
            return True
        except Exception as e:
            logger.error(f"종목 강제 재선정 중 오류 발생: {e}")
            self.send_notification('status', f"⚠️ 종목 재선정 중 오류 발생: {str(e)}")
            return False
    
    def send_momentum_stocks_kakao(self):
        """단타매매와 급등 종목 리스트를 카카오톡으로 전송"""
        logger.info("단타매매 및 급등 종목 리스트 카카오톡 전송 시작")
        
        try:
            # GPT 트레이딩 전략 객체가 초기화되었는지 확인
            if not self.gpt_trading_strategy:
                logger.warning("GPT 트레이딩 전략이 초기화되지 않았습니다.")
                return False
                
            # 카카오톡 발송 모듈이 활성화되어 있는지 확인
            if not self.use_kakao or not self.kakao_sender:
                logger.warning("카카오톡 알림 서비스가 비활성화되어 있습니다.")
                return False
                
            # 카카오톡이 초기화되지 않았다면 강제 재초기화 시도
            if not self.kakao_sender.initialized:
                logger.info("카카오톡 알림 서비스 재초기화 시도")
                try:
                    reinit_success = self.kakao_sender.initialize()
                    if not reinit_success:
                        logger.warning("카카오톡 재초기화 실패")
                        return False
                except Exception as e:
                    logger.error(f"카카오톡 재초기화 중 오류: {e}")
                    return False
            
            # 기본 설정: 최소 점수 70점, 최대 10개 표시
            min_score = getattr(self.config, 'MOMENTUM_MIN_SCORE', 70)
            max_count = getattr(self.config, 'MOMENTUM_MAX_COUNT', 10)
            
            # 단타/급등 종목 전송 실행
            result = self.gpt_trading_strategy.send_momentum_stocks_to_kakao(min_score, max_count)
            
            if result:
                logger.info("단타매매 및 급등 종목 리스트 카카오톡 전송 성공")
                return True
            else:
                logger.warning("단타매매 및 급등 종목 리스트 카카오톡 전송 실패")
                return False
                
        except Exception as e:
            logger.error(f"단타매매 및 급등 종목 리스트 카카오톡 전송 중 오류 발생: {e}")
            return False


# 명령줄 인자 처리
def parse_args():
    parser = argparse.ArgumentParser(description='AI 주식 분석 시스템')
    parser.add_argument('--debug', action='store_true', help='디버그 모드 활성화')
    parser.add_argument('--skip-stock-select', action='store_true', help='종목 선정 과정 건너뛰기')
    parser.add_argument('--force-market-open', action='store_true', help='시장 시간 제한을 무시하고 강제로 열림 상태로 간주')
    parser.add_argument('--simulation-mode', action='store_true', help='자동 매매 시스템을 시뮬레이션 모드로 실행')
    parser.add_argument('--send-momentum-stocks', action='store_true', help='단타매매 및 급등 종목 목록을 카카오톡으로 전송')
    return parser.parse_args()


# 메인 진입점
if __name__ == "__main__":
    args = parse_args()
    
    # 로깅 레벨 설정
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("디버그 모드 활성화")
    
    # 강제 시장 열림 설정
    if args.force_market_open:
        logger.info("강제 시장 열림 모드 활성화")
        config.FORCE_MARKET_OPEN = True
    
    # 시뮬레이션 모드 설정
    if args.simulation_mode:
        logger.info("시뮬레이션 모드 활성화")
        config.KIS_REAL_TRADING = False
        logger.info("한국투자증권 모의투자 계좌를 사용합니다.")
    
    # 시스템 인스턴스 생성
    system = StockAnalysisSystem()
    
    # 단타매매 및 급등 종목 목록 카카오톡 전송 명령 처리
    if args.send_momentum_stocks:
        logger.info("단타매매 및 급등 종목 목록 카카오톡 전송 명령 실행")
        result = system.send_momentum_stocks_kakao()
        if result:
            print("✅ 단타매매 및 급등 종목 목록 카카오톡 전송 완료")
        else:
            print("❌ 단타매매 및 급등 종목 목록 카카오톡 전송 실패")
        sys.exit(0)  # 전송 후 프로그램 종료
    
    try:
        # 시스템 시작 (이 메서드는 내부에서 무한 루프를 실행)
        system.start()
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램 종료")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {e}", exc_info=True)
    finally:
        system.stop()