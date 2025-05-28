"""
AI 주식 분석 시스템 - 메인 파일
이 스크립트는 클라우드 서버에서 24시간 실행되며, 낮에는 국내 주식, 밤에는 미국 주식을 분석합니다.
"""
import logging
import sys
import time
import schedule
import datetime  # datetime 모듈 추가
import argparse  # 명령줄 인수 처리를 위한 모듈 추가
import os  # os 모듈 추가
from src.data.stock_data import StockData
from src.analysis.technical import analyze_signals
from src.notification.telegram_sender import TelegramSender
from src.notification.kakao_sender import KakaoSender
from src.trading.kis_api import KISAPI
from src.trading.auto_trader import AutoTrader
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
from src.ai_analysis.gemini_analyzer import GeminiAnalyzer  # Gemini 분석기 추가
from src.ai_analysis.hybrid_analysis_strategy import HybridAnalysisStrategy  # 하이브리드 분석 전략 추가
from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy, SignalType
from src.ai_analysis.stock_selector import StockSelector
from src.utils.time_utils import now, format_time, get_korean_datetime_format, is_market_open, get_market_schedule, get_current_time
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
        # 텔레그램으로 메시지 전송 시도
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
            # CI 환경에서는 간소화된 초기화
            if os.environ.get('CI') == 'true':
                logger.info("CI 환경에서 실행 중입니다. 자동 매매 시스템을 제한된 모드로 초기화합니다.")
                self.auto_trading_enabled = False
                return False
                
            # 실제 환경에서 정상 초기화
            if self.config.BROKER_TYPE == "KIS":
                self.broker_api = KISAPI(self.config)
                logger.info("한국투자증권 API 초기화 완료")
            else:
                logger.error(f"지원하지 않는 증권사 유형: {self.config.BROKER_TYPE}")
                self.auto_trading_enabled = False
                return False
                
            # 필수 구성요소가 초기화되었는지 확인
            if not hasattr(self, 'stock_data') or not self.stock_data:
                logger.error("stock_data가 초기화되지 않았습니다.")
                self.auto_trading_enabled = False
                return False
                
            if not hasattr(self, 'gpt_trading_strategy') or not self.gpt_trading_strategy:
                logger.error("gpt_trading_strategy가 초기화되지 않았습니다.")
                self.auto_trading_enabled = False
                return False
            
            # AutoTrader 초기화 시 필요한 인자 모두 전달
            self.auto_trader = AutoTrader(
                config=self.config, 
                broker=self.broker_api,
                data_provider=self.stock_data,  # StockData 객체를 data_provider로 전달
                strategy_provider=self.gpt_trading_strategy,  # GPTTradingStrategy 객체를 strategy_provider로 전달
                notifier=self.telegram_sender if not self.use_kakao else self.kakao_sender  # 알림 발송 객체 설정
            )
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
            
            # 미국 시장 종목 추천
            us_result = self.stock_selector.recommend_stocks(
                market="US", 
                count=5, 
                strategy="balanced"
            )
            
            # 미국 종목 분석 추가
            us_analysis = "📊 <b>GPT 추천 미국 종목 분석</b>\n\n"
            if "recommended_stocks" in us_result and us_result["recommended_stocks"]:
                for stock in us_result["recommended_stocks"]:
                    symbol = stock.get("symbol")
                    name = stock.get("name", symbol)
                    reason = stock.get("reason", "")
                    weight = stock.get("suggested_weight", 0)
                    
                    us_analysis += f"- {name} ({symbol}): {reason} (추천 비중: {weight}%)\n"
            
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
            
            # 유망 종목 config에 업데이트
            self.stock_selector.update_config_stocks(
                kr_recommendations={"recommended_stocks": [stock for stock in combined_kr_stocks]},
                us_recommendations=us_result
            )
            
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
            
            logger.info("GPT 종목 선정 및 업데이트 완료")
            
        except Exception as e:
            logger.error(f"GPT 종목 선정 중 오류 발생: {e}")
            self.send_notification('status', f"❌ GPT 종목 선정 중 오류 발생: {str(e)}")

    def analyze_korean_stocks(self):
        """한국 주식 분석"""
        logger.info("한국 주식 분석 시작")
        
        # 시장 개장 여부 확인 (통합 시간 유틸리티 사용)
        if not is_market_open("KR", self.config):
            logger.info("현재 한국 시장이 개장되지 않았습니다. 분석을 건너뜁니다.")
            return
        
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
                    
                    # 자동 매매 처리
                    if self.auto_trading_enabled and self.auto_trader:
                        if self.auto_trader.is_trading_allowed(code, "KR"):
                            logger.info(f"종목 {code}에 대한 자동 매매 처리 시작")
                            self.auto_trader.process_signals(signals)
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
        if not is_market_open("US", self.config):
            logger.info("현재 미국 시장이 개장되지 않았습니다. 분석을 건너뜁니다.")
            return
        
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
                    
                    # 자동 매매 처리
                    if self.auto_trading_enabled and self.auto_trader:
                        if self.auto_trader.is_trading_allowed(symbol, "US"):
                            logger.info(f"종목 {symbol}에 대한 자동 매매 처리 시작")
                            self.auto_trader.process_signals(signals)
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
            # datetime 직접 사용 대신 time_utils 함수 사용
            current_time = get_current_time(tz=self.config.EST).time()
            
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
        if self.auto_trading_enabled and self.auto_trader and self.auto_trader.connected:
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
        
    def start(self):
        """시스템 시작"""
        if self.is_running:
            logger.warning("시스템이 이미 실행 중입니다.")
            return
            
        self.is_running = True
        logger.info("AI 주식 분석 시스템 시작")
        
        # 자동 매매 시스템 시작
        if self.auto_trading_enabled and self.auto_trader:
            self.auto_trader.start_trading_session()
            trade_status = "활성화" if self.auto_trader.is_running else "비활성화"
            logger.info(f"자동 매매 시스템 상태: {trade_status}")
        
        # 시스템 시작 메시지 전송
        start_msg = "AI 주식 분석 시스템이 시작되었습니다."
        if self.auto_trading_enabled:
            start_msg += f"\n자동 매매 기능이 {trade_status} 되었습니다."
        
        # 통합 알림 전송 함수 사용
        self.send_notification('status', start_msg)
        
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
        
        # 메인 루프
        try:
            # 시스템 시작 시 한 번 종목 선정 실행 (테스트용)
            self.select_stocks_with_gpt()
            
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 스케줄 확인
                
        except KeyboardInterrupt:
            logger.info("사용자에 의해 시스템 종료")
            self.stop()
            
        except Exception as e:
            logger.error(f"시스템 실행 중 오류 발생: {e}")
            self.stop()
            
    def stop(self):
        """시스템 종료"""
        if not self.is_running:
            return
            
        self.is_running = False
        logger.info("AI 주식 분석 시스템 종료")
        
        # 자동 매매 세션 종료
        if self.auto_trading_enabled and self.auto_trader:
            self.auto_trader.stop_trading_session()
            logger.info("자동 매매 세션 종료")
        
        # 시스템 종료 메시지 전송
        self.send_notification('status', "AI 주식 분석 시스템이 종료되었습니다.")

if __name__ == "__main__":
    # 명령줄 인수 처리
    parser = argparse.ArgumentParser(description="AI 주식 분석 시스템")
    parser.add_argument("--ci", action="store_true", help="CI/CD 환경에서 실행 여부")
    parser.add_argument("--mode", choices=["analysis", "trading", "full"], default="full",
                      help="실행 모드 (analysis: 분석만, trading: 거래만, full: 전체 기능)")
    parser.add_argument("--market", choices=["KR", "US", "all"], default="all",
                      help="분석할 시장 (KR: 한국, US: 미국, all: 모두)")
    args = parser.parse_args()
    
    # CI/CD 환경 여부 설정
    if args.ci:
        logger.info("CI/CD 환경에서 실행합니다.")
        os.environ["CI"] = "true"
        os.environ["FORCE_MARKET_OPEN"] = "true"
    
    # 시스템 초기화
    system = StockAnalysisSystem()
    
    # 모드에 따른 실행
    if args.mode == "analysis":
        logger.info("분석 모드로 실행합니다.")
        # 시장 선택에 따른 실행
        if args.market in ["KR", "all"]:
            system.analyze_korean_stocks()
        if args.market in ["US", "all"]:
            system.analyze_us_stocks()
        # 종목 선정
        system.select_stocks_with_gpt()
        # 일일 요약
        system.send_daily_summary()
    elif args.mode == "trading":
        logger.info("거래 모드로 실행합니다.")
        if system.auto_trading_enabled and system.auto_trader:
            system.auto_trader.start_trading_session()
            logger.info("자동 매매 세션을 시작했습니다.")
    else:
        # 전체 기능 실행
        logger.info("전체 기능 모드로 실행합니다.")
        system.start()