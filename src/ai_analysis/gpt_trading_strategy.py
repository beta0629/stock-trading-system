"""
GPT 모델을 활용한 고급 트레이딩 전략 구현
"""
import logging
import pandas as pd
import numpy as np
import datetime
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
# 시간 유틸리티 추가
from src.utils.time_utils import get_current_time, get_current_time_str, format_timestamp, is_market_open
from enum import Enum

# 로깅 설정
logger = logging.getLogger('GPTTradingStrategy')

# 매매 신호 타입 열거형 추가
class SignalType(Enum):
    """매매 신호 타입 열거형"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NONE = "NONE"
    ERROR = "ERROR"

# 트레이딩 신호 클래스 추가
class TradingSignal:
    """매매 신호 클래스"""
    def __init__(self, signal_type, price, date=None, confidence=0.0, analysis=None):
        self.signal_type = signal_type if isinstance(signal_type, SignalType) else SignalType(signal_type)
        self.price = price
        self.date = date or datetime.datetime.now()
        self.confidence = confidence
        self.analysis = analysis
        self.generated_at = datetime.datetime.now()

    def __str__(self):
        return f"Signal: {self.signal_type.value}, Price: {self.price}, Confidence: {self.confidence:.2f}, Date: {self.date}"

class GPTTradingStrategy:
    """GPT 모델을 활용한 고급 트레이딩 전략 클래스"""
    
    def __init__(self, config, analyzer=None):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
            analyzer: ChatGPT 분석기 (없으면 새로 생성)
        """
        self.config = config
        
        # ChatGPT 분석기 설정
        self.analyzer = analyzer if analyzer else ChatGPTAnalyzer(config)
        
        # 매매 신호 신뢰도 임계값
        self.buy_confidence_threshold = getattr(config, 'GPT_BUY_CONFIDENCE_THRESHOLD', 0.7)
        self.sell_confidence_threshold = getattr(config, 'GPT_SELL_CONFIDENCE_THRESHOLD', 0.6)
        
        # 기술적 지표와 GPT 분석의 가중치
        self.technical_weight = getattr(config, 'TECHNICAL_WEIGHT', 0.6)
        self.gpt_weight = getattr(config, 'GPT_WEIGHT', 0.4)

        # 완전 자동화 모드 설정
        self.fully_autonomous = getattr(config, 'GPT_FULLY_AUTONOMOUS', True)
        self.autonomous_confidence_threshold = getattr(config, 'GPT_AUTONOMOUS_CONFIDENCE_THRESHOLD', 0.75)
        self.autonomous_max_trade_amount = getattr(config, 'GPT_AUTONOMOUS_MAX_TRADE', 1000000)  # 자동 매매 최대 금액
        self.aggressive_mode = getattr(config, 'GPT_AGGRESSIVE_MODE', False)  # 공격적 매매 모드
        
        # 하락장에서만 매수하는 설정 추가
        self.dip_buying_only = getattr(config, 'DIP_BUYING_ONLY', True)  # 하락장에서만 매수
        self.dip_threshold_pct = getattr(config, 'DIP_THRESHOLD_PCT', -3.0)  # 하락 기준 퍼센트
        self.dip_period = getattr(config, 'DIP_PERIOD', 5)  # 하락 측정 기간 (일)
        
        # 초기 자본금 설정
        self.initial_capital = getattr(config, 'INITIAL_CAPITAL', 1000000)  # 초기 자본금

        # 모멘텀 기회 메모리 저장소 (디비/캐시 대신)
        self.momentum_opportunities = []
        
        logger.info(f"GPT 트레이딩 전략 초기화 완료 (완전자율모드: {self.fully_autonomous}, 공격적모드: {self.aggressive_mode}, 하락장매수: {self.dip_buying_only})")
    
    def analyze_stock(self, df, symbol, market_context=None):
        """
        종목 분석 및 매매 신호 생성
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            market_context: 시장 맥락 정보 (선택 사항)
            
        Returns:
            dict: 분석 결과 및 매매 신호
        """
        if df.empty:
            logger.warning(f"{symbol}: 분석할 데이터가 없습니다.")
            return {
                "symbol": symbol,
                "signal": "NONE",
                "confidence": 0.0,
                "reason": "분석할 데이터가 없습니다."
            }
        
        try:
            # 기본 기술적 신호 계산
            tech_signal, tech_confidence = self._calculate_technical_signals(df)
            
            # GPT 분석 수행 (추세 및 리스크 분석)
            gpt_analysis = self._perform_gpt_analysis(df, symbol, market_context)
            gpt_signal, gpt_confidence = self._extract_gpt_signals(gpt_analysis)
            
            # 최종 신호 결정 (가중 평균)
            final_signal, final_confidence = self._combine_signals(
                tech_signal, tech_confidence, 
                gpt_signal, gpt_confidence
            )
            
            # 매매 수량 결정
            quantity = self._calculate_position_size(df, final_confidence, symbol)
            
            result = {
                "symbol": symbol,
                "signal": final_signal,
                "confidence": final_confidence,
                "quantity": quantity,
                "technical_signal": tech_signal,
                "technical_confidence": tech_confidence,
                "gpt_signal": gpt_signal,
                "gpt_confidence": gpt_confidence,
                "analysis_summary": gpt_analysis.get("analysis", "")[:200] + "...",  # 요약 정보만
                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            logger.info(f"{symbol} 분석 완료: {final_signal} 신호 (신뢰도: {final_confidence:.2f})")
            return result
            
        except Exception as e:
            logger.error(f"{symbol} 분석 중 오류 발생: {e}")
            return {
                "symbol": symbol,
                "signal": "ERROR",
                "confidence": 0.0,
                "reason": f"분석 중 오류: {str(e)}"
            }
    
    def _calculate_technical_signals(self, df):
        """
        기술적 지표 기반 매매 신호 계산
        
        Args:
            df: 주가 데이터
            
        Returns:
            tuple: (신호, 신뢰도)
        """
        # 필요한 기술적 지표가 있는지 확인
        required_indicators = ['RSI', 'MACD', 'MACD_signal', 'SMA_short', 'SMA_long']
        missing = [ind for ind in required_indicators if ind not in df.columns]
        
        if missing:
            logger.warning(f"일부 기술적 지표가 없습니다: {missing}")
            # 기본 지표만 사용해서 계속 진행
        
        # 최근 데이터
        recent = df.iloc[-1]
        
        # 매매 신호 점수 계산 (0~100)
        score = 50  # 중립 시작점
        confidence_factors = []
        
        # 1. RSI 지표 분석
        if 'RSI' in df.columns:
            rsi = recent['RSI']
            if rsi < 30:  # 과매도
                score += 15
                confidence_factors.append(('RSI', 0.7, 'BUY', f'RSI가 {rsi:.2f}로 과매도 상태'))
            elif rsi > 70:  # 과매수
                score -= 15
                confidence_factors.append(('RSI', 0.7, 'SELL', f'RSI가 {rsi:.2f}로 과매수 상태'))
            elif rsi < 45:
                score += 5
                confidence_factors.append(('RSI', 0.5, 'BUY', f'RSI가 {rsi:.2f}로 저점 구간에 접근'))
            elif rsi > 55:
                score -= 5
                confidence_factors.append(('RSI', 0.5, 'SELL', f'RSI가 {rsi:.2f}로 고점 구간에 접근'))
        
        # 2. 이동평균선 분석
        if 'SMA_short' in df.columns and 'SMA_long' in df.columns:
            short_ma = df['SMA_short'].iloc[-1]
            long_ma = df['SMA_long'].iloc[-1]
            prev_short_ma = df['SMA_short'].iloc[-2]
            prev_long_ma = df['SMA_long'].iloc[-2]
            
            # 골든 크로스 (단기선이 장기선을 상향 돌파)
            if prev_short_ma < prev_long_ma and short_ma > long_ma:
                score += 20
                confidence_factors.append(('SMA', 0.8, 'BUY', '골든 크로스 발생'))
            
            # 데드 크로스 (단기선이 장기선을 하향 돌파)
            elif prev_short_ma > prev_long_ma and short_ma < long_ma:
                score -= 20
                confidence_factors.append(('SMA', 0.8, 'SELL', '데드 크로스 발생'))
            
            # 추세 확인
            elif short_ma > long_ma:  # 상승 추세
                # 얼마나 크게 이격되어 있는지 확인
                gap_percent = (short_ma / long_ma - 1) * 100
                
                if gap_percent > 5:
                    score -= 10  # 과도한 이격은 조정 가능성
                    confidence_factors.append(('SMA', 0.6, 'SELL', f'이동평균선 과도 이격 ({gap_percent:.2f}%)'))
                else:
                    score += 10  # 적정 상승 추trend
                    confidence_factors.append(('SMA', 0.6, 'BUY', '이동평균선 상승 추세 지속'))
            
            elif short_ma < long_ma:  # 하락 추Trend
                # 얼마나 크게 이격되어 있는지 확인
                gap_percent = (long_ma / short_ma - 1) * 100
                
                if gap_percent > 5:
                    score += 10  # 과도한 이격은 반등 가능성
                    confidence_factors.append(('SMA', 0.6, 'BUY', f'이동평균선 과도 이격 ({gap_percent:.2f}%)'))
                else:
                    score -= 10  # 적정 하락 추세
                    confidence_factors.append(('SMA', 0.6, 'SELL', '이동평균선 하락 추세 지속'))
        
        # 3. MACD 분석
        if 'MACD' in df.columns and 'MACD_signal' in df.columns:
            macd = recent['MACD']
            signal = recent['MACD_signal']
            prev_macd = df['MACD'].iloc[-2]
            prev_signal = df['MACD_signal'].iloc[-2]
            
            # MACD가 시그널 라인을 상향 돌파 (강한 매수 신호)
            if prev_macd < prev_signal and macd > signal:
                score += 15
                confidence_factors.append(('MACD', 0.7, 'BUY', 'MACD 상향 돌파'))
            
            # MACD가 시그널 라인을 하향 돌파 (강한 매도 신호)
            elif prev_macd > prev_signal and macd < signal:
                score -= 15
                confidence_factors.append(('MACD', 0.7, 'SELL', 'MACD 하향 돌파'))
            
            # MACD와 시그널 모두 상승 중 (상승 추세 지속)
            elif macd > prev_macd and signal > prev_signal:
                score += 5
                confidence_factors.append(('MACD', 0.5, 'BUY', 'MACD 상승 추세'))
            
            # MACD와 시그널 모두 하락 중 (하락 추세 지속)
            elif macd < prev_macd and signal < prev_signal:
                score -= 5
                confidence_factors.append(('MACD', 0.5, 'SELL', 'MACD 하락 추세'))
        
        # 4. 주가 움직임 분석 (최근 3일)
        recent_changes = df['Close'].pct_change().iloc[-3:].values
        
        # 3일 연속 상승
        if all(change > 0 for change in recent_changes):
            # 상승폭이 크면 추가적인 매도 가능성
            total_change = (df['Close'].iloc[-1] / df['Close'].iloc[-4] - 1) * 100
            if total_change > 10:
                score -= 10  # 단기 과열 조정 가능성
                confidence_factors.append(('Price', 0.6, 'SELL', f'3일 연속 급등 (총 {total_change:.2f}%)'))
            else:
                score += 5  # 적정 상승 추세 지속
                confidence_factors.append(('Price', 0.5, 'BUY', '상승 모멘텀 지속'))
        
        # 3일 연속 하락
        elif all(change < 0 for change in recent_changes):
            # 하락폭이 크면 추가적인 매수 가능성
            total_change = (df['Close'].iloc[-1] / df['Close'].iloc[-4] - 1) * 100
            if total_change < -10:
                score += 10  # 과매도 반등 가능성
                confidence_factors.append(('Price', 0.6, 'BUY', f'3일 연속 급락 (총 {total_change:.2f}%)'))
            else:
                score -= 5  # 하락 추세 지속
                confidence_factors.append(('Price', 0.5, 'SELL', '하락 추세 지속'))
        
        # 점수를 신호와 신뢰도로 변환
        if score > 70:
            signal = "BUY"
            confidence = min((score - 50) / 50, 0.9)  # 최대 0.9
        elif score < 30:
            signal = "SELL"
            confidence = min((50 - score) / 50, 0.9)  # 최대 0.9
        else:
            signal = "HOLD"
            # 중립에 가까울수록 신뢰도가 낮아짐
            confidence = 1.0 - abs(50 - score) / 20
            confidence = max(0.3, min(confidence, 0.7))  # 0.3 ~ 0.7 사이 값
        
        logger.info(f"기술적 분석 결과 - 점수: {score}, 신호: {signal}, 신뢰도: {confidence:.2f}")
        
        return signal, confidence
    
    def _perform_gpt_analysis(self, df, symbol, market_context=None):
        """
        GPT 모델을 사용한 분석 수행
        
        Args:
            df: 주가 데이터
            symbol: 종목 코드
            market_context: 시장 맥락 정보 (선택 사항)
            
        Returns:
            dict: 분석 결과
        """
        # 분석에 사용할 추가 정보
        additional_info = {
            "market_context": market_context or {},
            "analysis_purpose": "trading_signal",
            "analysis_timestamp": get_current_time_str(format_str="%Y-%m-%dT%H:%M:%S%z")  # ISO 형식으로 변환
        }
        
        # 여러 분석 유형 결과 조합
        trend_analysis = self.analyzer.analyze_stock(df, symbol, "trend", additional_info)
        risk_analysis = self.analyzer.analyze_stock(df, symbol, "risk", additional_info)
        
        # 분석 결과 조합
        combined_analysis = {
            "symbol": symbol,
            "trend_analysis": trend_analysis.get("analysis", "분석 없음"),
            "risk_analysis": risk_analysis.get("analysis", "분석 없음"),
            "timestamp": get_current_time_str(format_str="%Y-%m-%dT%H:%M:%S%z")  # ISO 형식으로 변환
        }
        
        # 매매 신호 추출을 위한 특별 분석 요청
        signal_data = {
            "symbol": symbol,
            "trend_summary": trend_analysis.get("analysis", "")[:300],
            "risk_summary": risk_analysis.get("analysis", "")[:300],
            # DataFrame을 records 형식으로 변환하여 JSON 직렬화 문제 방지
            "recent_price_data": df[['Close', 'Volume']].tail(5).reset_index().to_dict('records'),
            "technical_indicators": {
                "rsi": float(df['RSI'].iloc[-1]) if 'RSI' in df.columns else None,
                "macd": float(df['MACD'].iloc[-1]) if 'MACD' in df.columns else None,
                "macd_signal": float(df['MACD_signal'].iloc[-1]) if 'MACD_signal' in df.columns else None
            }
        }
        
        signal_analysis = self.analyzer.analyze_signals(signal_data)
        combined_analysis["signal_analysis"] = signal_analysis
        combined_analysis["analysis"] = signal_analysis  # 호환성을 위해
        
        return combined_analysis
    
    def _extract_gpt_signals(self, gpt_analysis):
        """
        GPT 분석 결과에서 매매 신호 추출
        
        Args:
            gpt_analysis: GPT 분석 결과
            
        Returns:
            tuple: (신호, 신뢰도)
        """
        analysis_text = gpt_analysis.get("signal_analysis", "")
        if not analysis_text or isinstance(analysis_text, dict):
            return "HOLD", 0.5
            
        analysis_text = analysis_text.lower()
        
        # 매수 관련 키워드
        buy_keywords = ["매수", "상승", "강세", "bullish", "buy", "positive", "상향", "매집", "저평가"]
        sell_keywords = ["매도", "하락", "약세", "bearish", "sell", "negative", "하향", "매도세", "고평가"]
        
        # 키워드 등장 횟수
        buy_count = sum(analysis_text.count(keyword) for keyword in buy_keywords)
        sell_count = sum(analysis_text.count(keyword) for keyword in sell_keywords)
        
        # 신뢰도 관련 단어
        high_confidence = ["매우", "확실", "strongly", "clearly", "significant", "뚜렷", "명확"]
        low_confidence = ["약간", "조금", "slight", "mild", "weak", "미약", "불확실"]
        
        # 신뢰도 조정
        confidence_base = 0.7  # 기본 신뢰도
        
        # 높은 신뢰도 증거가 있으면 +0.2
        if any(word in analysis_text for word in high_confidence):
            confidence_base = 0.9
        # 낮은 신뢰도 증거가 있으면 -0.2
        elif any(word in analysis_text for word in low_confidence):
            confidence_base = 0.5
            
        # 신호 결정
        if buy_count > sell_count * 1.5:  # 매수 신호가 매도 신호보다 1.5배 이상
            return "BUY", confidence_base
        elif sell_count > buy_count * 1.5:  # 매도 신호가 매수 신호보다 1.5배 이상
            return "SELL", confidence_base
        else:  # 보류 또는 중립
            return "HOLD", max(0.4, confidence_base - 0.3)  # 보류는 신뢰도 낮춤
    
    def _combine_signals(self, tech_signal, tech_confidence, gpt_signal, gpt_confidence):
        """
        기술적 신호와 GPT 신호 조합
        
        Args:
            tech_signal: 기술적 지표 기반 신호
            tech_confidence: 기술적 신호 신뢰도
            gpt_signal: GPT 기반 신호
            gpt_confidence: GPT 신호 신뢰도
            
        Returns:
            tuple: (최종 신호, 최종 신뢰도)
        """
        # 신호 일치 여부
        signals_match = tech_signal == gpt_signal
        
        # 신호 가중 평균 계산
        signal_scores = {
            "BUY": 1.0,
            "HOLD": 0.0,
            "SELL": -1.0
        }
        
        tech_score = signal_scores.get(tech_signal, 0.0) * tech_confidence * self.technical_weight
        gpt_score = signal_scores.get(gpt_signal, 0.0) * gpt_confidence * self.gpt_weight
        
        combined_score = tech_score + gpt_score
        
        # 최종 신호 및 신뢰도 결정
        if combined_score > 0.3:
            signal = "BUY"
            confidence = min(abs(combined_score) + (0.1 if signals_match else 0), 1.0)
        elif combined_score < -0.3:
            signal = "SELL"
            confidence = min(abs(combined_score) + (0.1 if signals_match else 0), 1.0)
        else:
            signal = "HOLD"
            confidence = max(0.4, abs(combined_score) * 2)  # HOLD 신호는 신뢰도 낮춤
            
        return signal, confidence
    
    def _calculate_position_size(self, df, confidence, symbol):
        """
        매매 수량 결정
        
        Args:
            df: 주가 데이터
            confidence: 신호 신뢰도
            symbol: 종목 코드
            
        Returns:
            int: 매매 수량
        """
        # 기본 볼륨 (신뢰도에 따라 조정)
        base_quantity = max(1, int(confidence * 5))
        
        # 변동성 체크
        if 'Close' in df.columns and len(df) > 20:
            # 20일 변동성
            volatility = df['Close'].pct_change().rolling(window=20).std().iloc[-1]
            
            # 변동성이 높으면 수량 감소
            if volatility > 0.03:  # 3% 이상 변동성
                base_quantity = max(1, int(base_quantity * 0.7))
            # 변동성이 매우 낮으면 수량 증가
            elif volatility < 0.01:  # 1% 미만 변동성
                base_quantity = int(base_quantity * 1.2)
        
        # 최대 매매 수량 제한
        max_quantity = 10
        quantity = min(base_quantity, max_quantity)
        
        return quantity

    def analyze_stop_levels(self, df, symbol, market_context=None):
        """
        종목별 적절한 손절매/익절 수준 분석
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            market_context: 시장 맥락 정보 (선택 사항)
            
        Returns:
            dict: 손절매/익절 설정 값
        """
        if df.empty:
            logger.warning(f"{symbol}: 손절/익절 수준을 분석할 데이터가 없습니다.")
            return {
                "stop_loss_pct": 5.0,  # 기본값
                "take_profit_pct": 10.0,  # 기본값
                "use_trailing_stop": True,
                "trailing_stop_distance": 3.0,  # 기본값
                "confidence": 0.0
            }
            
        try:
            # 1. 기술적 지표 기반 변동성 분석
            volatility = self._calculate_volatility(df)
            
            # 2. 종목 특성 분석을 위한 GPT 요청
            gpt_analysis = self._analyze_risk_profile(df, symbol, market_context, volatility)
            
            # 3. 손절매/익절 수준 설정
            stop_levels = self._determine_stop_levels(volatility, gpt_analysis)
            
            logger.info(f"{symbol} 손절/익절 수준 분석 완료: 손절 {stop_levels['stop_loss_pct']:.1f}%, "
                       f"익절 {stop_levels['take_profit_pct']:.1f}%, "
                       f"트레일링스탑 거리 {stop_levels['trailing_stop_distance']:.1f}%")
            
            return stop_levels
            
        except Exception as e:
            logger.error(f"{symbol} 손절/익절 수준 분석 중 오류 발생: {e}")
            return {
                "stop_loss_pct": 5.0,  # 기본값
                "take_profit_pct": 10.0,  # 기본값
                "use_trailing_stop": True,
                "trailing_stop_distance": 3.0,  # 기본값
                "confidence": 0.0
            }
    
    def _calculate_volatility(self, df):
        """
        주가 데이터의 변동성 계산
        
        Args:
            df: 주가 데이터
            
        Returns:
            dict: 변동성 관련 지표
        """
        # 일일 변동률 계산
        daily_returns = df['Close'].pct_change().dropna()
        
        # 표준 변동성 (20일)
        std_20d = daily_returns.rolling(window=20).std().iloc[-1]
        
        # ATR (Average True Range) - 20일
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_20d = true_range.rolling(window=20).mean().iloc[-1] / df['Close'].iloc[-1]
        
        # 최근 20일 내 최대 하락폭
        rolling_max = df['Close'].rolling(window=20).max()
        max_drawdown = ((df['Close'] - rolling_max) / rolling_max).rolling(window=20).min().iloc[-1]
        
        # 일일 변동폭 평균 (%) - 고가와 저가의 차이
        avg_daily_range_pct = ((df['High'] - df['Low']) / df['Close']).rolling(window=20).mean().iloc[-1] * 100
        
        return {
            "std_20d": std_20d,
            "atr_20d": atr_20d,
            "max_drawdown_20d": max_drawdown,
            "avg_daily_range_pct": avg_daily_range_pct
        }
    
    def _analyze_risk_profile(self, df, symbol, market_context, volatility):
        """
        종목의 리스크 프로필 분석을 위한 GPT 요청
        
        Args:
            df: 주가 데이터
            symbol: 종목 코드
            market_context: 시장 맥락 정보
            volatility: 변동성 지표
            
        Returns:
            dict: GPT 분석 결과
        """
        # 분석에 필요한 데이터 준비 - records 형식으로 변환하여 Timestamp 인덱스 문제 해결
        recent_data = df.tail(5)[['Close', 'Volume']].reset_index().to_dict('records')
        
        # 변동성 데이터 추가
        analysis_data = {
            "symbol": symbol,
            "market_context": market_context or {},
            "recent_data": recent_data,
            "volatility": volatility,
            "analysis_purpose": "stop_loss_take_profit",
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        # GPT에 분석 요청 - 손절/익절 최적화를 위한 특별한 프롬프트 사용
        risk_analysis = self.analyzer.analyze_stop_levels(analysis_data)
        
        return risk_analysis
    
    def _determine_stop_levels(self, volatility, gpt_analysis):
        """
        최종 손절매/익절 수준 결정
        
        Args:
            volatility: 변동성 지표
            gpt_analysis: GPT 분석 결과
            
        Returns:
            dict: 손절매/익절 설정 값
        """
        # 기본 설정값
        default_stop_loss = 5.0
        default_take_profit = 10.0
        default_trailing_stop = 3.0
        
        # GPT 추천 값 (없으면 기본값 사용)
        gpt_results = gpt_analysis.get("recommendations", {})
        gpt_stop_loss = gpt_results.get("stop_loss_pct", default_stop_loss)
        gpt_take_profit = gpt_results.get("take_profit_pct", default_take_profit)
        gpt_trailing_stop = gpt_results.get("trailing_stop_distance", default_trailing_stop)
        
        # 변동성 기반 조정 - 변동성이 높을수록 손절/익절 폭을 넓게 설정
        volatility_factor = max(0.8, min(1.5, 1 + volatility["std_20d"] * 10))
        avg_daily_range = volatility["avg_daily_range_pct"]
        
        # 평균 일일 변동폭이 큰 종목은 더 넓은 손절/익절폭 필요
        if avg_daily_range > 3.0:  # 일 3% 이상 변동이면
            volatility_factor *= 1.2
        
        # 최종 손절/익절 수준 결정 (GPT와 변동성 고려)
        stop_loss = max(2.0, min(15.0, gpt_stop_loss * volatility_factor))
        take_profit = max(5.0, min(30.0, gpt_take_profit * volatility_factor))
        trailing_stop = max(1.0, min(10.0, gpt_trailing_stop * volatility_factor))
        
        # 손절폭이 익절폭보다 크지 않도록 조정
        if stop_loss > take_profit * 0.8:
            stop_loss = take_profit * 0.7
            
        return {
            "stop_loss_pct": round(stop_loss, 1),
            "take_profit_pct": round(take_profit, 1),
            "use_trailing_stop": True,
            "trailing_stop_distance": round(trailing_stop, 1),
            "confidence": 0.8
        }
    
    def generate_trading_signals(self, df, symbol):
        """
        주식 데이터로부터 매매 신호 생성
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            
        Returns:
            list: TradingSignal 객체 리스트
        """
        logger.info(f"종목 {symbol}에 대한 매매 신호 생성 시작")
        
        if df.empty:
            logger.warning(f"{symbol}: 분석할 데이터가 없습니다.")
            return []
        
        try:
            # 하락장 매수 로직 적용: 최근 가격 하락이 있는지 확인
            if self.dip_buying_only:
                # 설정된 기간 동안의 가격 변화율 계산
                if len(df) > self.dip_period:
                    price_change_pct = (df['Close'].iloc[-1] / df['Close'].iloc[-self.dip_period] - 1) * 100
                    if price_change_pct > self.dip_threshold_pct:  # 가격이 상승했다면
                        logger.info(f"{symbol}: 최근 {self.dip_period}일 동안 {price_change_pct:.2f}% 상승하여 매수 신호를 억제합니다.")
                        return []  # 매수 신호 억제
            
            # analyze_stock 메서드를 통해 기본 분석 수행
            analysis_result = self.analyze_stock(df, symbol)
            
            signals = []
            
            # 신호가 BUY 또는 SELL이고 신뢰도가 임계값보다 높은 경우에만 신호 생성
            signal_type = analysis_result.get('signal')
            confidence = analysis_result.get('confidence', 0.0)
            
            if signal_type == 'BUY' and confidence >= self.buy_confidence_threshold:
                # 하락장 매수 조건 체크 (매수 신호일 때만)
                if self.dip_buying_only:
                    # 기간 내 최고가 대비 현재가의 하락 정도 확인
                    recent_high = df['High'].iloc[-self.dip_period:].max()
                    current_price = df['Close'].iloc[-1]
                    dip_from_high_pct = (current_price / recent_high - 1) * 100
                    
                    # 최근 고점 대비 현재 가격이 충분히 떨어졌는지 확인
                    if dip_from_high_pct > self.dip_threshold_pct:  # 하락폭이 충분하지 않은 경우
                        logger.info(f"{symbol}: 최근 고점 대비 {dip_from_high_pct:.2f}% 변동으로 하락폭이 충분하지 않아 매수 신호를 억제합니다.")
                        return []  # 매수 신호 억제
                
                # 현재가 기준 매수 신호 생성
                current_price = df['Close'].iloc[-1]
                signals.append(TradingSignal(
                    signal_type=SignalType.BUY,
                    price=current_price,
                    date=pd.to_datetime(df.index[-1]) if isinstance(df.index[-1], (str, pd.Timestamp)) else datetime.datetime.now(),
                    confidence=confidence,
                    analysis=analysis_result.get('analysis_summary', '')
                ))
                logger.info(f"{symbol} 매수 신호 생성: 가격 {current_price}, 신뢰도 {confidence:.2f}")
                
            elif signal_type == 'SELL' and confidence >= self.sell_confidence_threshold:
                # 현재가 기준 매도 신호 생성
                current_price = df['Close'].iloc[-1]
                signals.append(TradingSignal(
                    signal_type=SignalType.SELL,
                    price=current_price,
                    date=pd.to_datetime(df.index[-1]) if isinstance(df.index[-1], (str, pd.Timestamp)) else datetime.datetime.now(),
                    confidence=confidence,
                    analysis=analysis_result.get('analysis_summary', '')
                ))
                logger.info(f"{symbol} 매도 신호 생성: 가격 {current_price}, 신뢰도 {confidence:.2f}")
                
            # 손절매/익절 수준 분석 및 추가 신호 생성 (향후 확장)
            if signals and hasattr(self, 'analyze_stop_levels'):
                try:
                    stop_levels = self.analyze_stop_levels(df, symbol)
                    # 기존 신호에 손절매/익절 정보 추가
                    for signal in signals:
                        if signal.signal_type == SignalType.BUY:
                            stop_price = signal.price * (1 - stop_levels['stop_loss_pct'] / 100)
                            target_price = signal.price * (1 + stop_levels['take_profit_pct'] / 100)
                            logger.info(f"{symbol} 매수 후 손절가: {stop_price:.2f}, 목표가: {target_price:.2f}")
                except Exception as e:
                    logger.warning(f"{symbol} 손절매/익절 수준 분석 중 오류: {e}")
            
            return signals
            
        except Exception as e:
            logger.error(f"{symbol} 매매 신호 생성 중 오류 발생: {e}")
            return []
    
    def identify_undervalued_stocks(self, df_dict, market="KR", top_n=5):
        """
        여러 종목 중에서 저평가된 종목을 식별

        Args:
            df_dict: {종목코드: DataFrame} 형태의 데이터
            market: 시장 구분 ("KR" 또는 "US")
            top_n: 반환할 상위 종목 수

        Returns:
            list: (종목코드, 점수, 설명) 형태의 저평가 종목 리스트
        """
        logger.info(f"{market} 시장에서 저평가 종목 식별 시작")
        
        if not df_dict:
            logger.warning("분석할 데이터가 없습니다.")
            return []
        
        undervalued_stocks = []
        
        for symbol, df in df_dict.items():
            if df.empty:
                continue
                
            try:
                # 저평가 분석을 위한 특별 프롬프트 구성
                additional_info = {
                    "analysis_purpose": "valuation",
                    "market": market
                }
                
                # GPT 분석 수행 (밸류에이션 분석)
                analysis = self.analyzer.analyze_stock(df, symbol, "trend", additional_info)
                
                # 저평가 관련 키워드 검색
                analysis_text = analysis.get("analysis", "").lower()
                
                # 저평가 점수 계산
                undervalued_score = 0
                
                # 저평가 관련 키워드
                undervalued_keywords = ["저평가", "undervalued", "할인", "discount", "저렴", "매력적 가치", "buying opportunity"]
                overvalued_keywords = ["고평가", "overvalued", "프리미엄", "premium", "비싼", "과열"]
                
                # 저평가 키워드 발견 시 점수 증가
                for keyword in undervalued_keywords:
                    if keyword in analysis_text:
                        undervalued_score += 10
                        
                # 고평가 키워드 발견 시 점수 감소
                for keyword in overvalued_keywords:
                    if keyword in analysis_text:
                        undervalued_score -= 10
                
                # 기술적 지표 분석
                if 'RSI' in df.columns:
                    rsi = df['RSI'].iloc[-1]
                    # RSI가 낮을수록 저평가 가능성 높음
                    if rsi < 30:
                        undervalued_score += 15
                    elif rsi < 40:
                        undervalued_score += 10
                    elif rsi > 70:
                        undervalued_score -= 15
                
                # PER, PBR 정보가 있는 경우 (추가 정보를 통해 제공됨)
                if 'fundamental_data' in analysis and isinstance(analysis['fundamental_data'], dict):
                    fundamental = analysis['fundamental_data']
                    
                    # PER이 낮으면 저평가 가능성 (업종 평균 대비)
                    if 'PER' in fundamental and 'industry_avg_PER' in fundamental:
                        per_ratio = fundamental['PER'] / fundamental['industry_avg_PER']
                        if per_ratio < 0.7:  # 업종 평균보다 30% 이상 낮음
                            undervalued_score += 20
                        elif per_ratio < 0.9:  # 업종 평균보다 10% 이상 낮음
                            undervalued_score += 10
                    
                    # PBR이 낮으면 저평가 가능성
                    if 'PBR' in fundamental and fundamental['PBR'] < 1:
                        undervalued_score += 10
                
                # 추가 분석을 위해 GPT에 직접 저평가 여부 질문
                valuation_prompt = f"이 {symbol} 종목이 얼마나 저평가되어 있는지 1-10 척도로 평가해주세요. 1은 매우 고평가, 10은 매우 저평가입니다. 숫자로만 답변하세요."
                valuation_response = self.analyzer.client.chat.completions.create(
                    model=self.analyzer.model,
                    messages=[
                        {"role": "system", "content": "당신은 주식 밸류에이션 전문가입니다. 1-10 척도로 저평가 정도를 평가합니다."},
                        {"role": "user", "content": valuation_prompt}
                    ],
                    max_tokens=10,
                    temperature=0.3
                )
                
                # 응답에서 숫자 추출 시도
                valuation_text = valuation_response.choices[0].message.content.strip()
                
                try:
                    # 숫자만 추출 (1-10 사이 값인지 확인)
                    valuation_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', valuation_text)))
                    if 1 <= valuation_num <= 10:
                        # 1-10 척도를 -50 ~ +50 점수로 변환 (5.5가 중간점)
                        gpt_score = (valuation_num - 5.5) * 10
                        undervalued_score += gpt_score
                except:
                    # 숫자 추출에 실패하면 기본 점수 사용
                    pass
                
                # 최종 저평가 점수 정규화 (0-100)
                normalized_score = max(0, min(100, undervalued_score + 50))
                
                # 분석 요약 생성
                explanation = f"저평가 점수: {normalized_score:.1f}/100"
                if normalized_score > 70:
                    explanation += " (매우 저평가 상태)"
                elif normalized_score > 60:
                    explanation += " (다소 저평가 상태)"
                elif normalized_score < 30:
                    explanation += " (고평가 상태)"
                    
                # 결과 추가
                undervalued_stocks.append((symbol, normalized_score, explanation))
                logger.info(f"{symbol} 저평가 분석 완료: 점수 {normalized_score:.1f}")
                
            except Exception as e:
                logger.error(f"{symbol} 저평가 분석 중 오류 발생: {e}")
        
        # 점수 기준 정렬 (내림차순) 및 상위 n개 반환
        return sorted(undervalued_stocks, key=lambda x: x[1], reverse=True)[:top_n]
    
    def identify_swing_trading_candidates(self, df_dict, market="KR", top_n=5):
        """
        여러 종목 중에서 스윙 트레이딩에 적합한 종목 식별

        Args:
            df_dict: {종목코드: DataFrame} 형태의 데이터
            market: 시장 구분 ("KR" 또는 "US")
            top_n: 반환할 상위 종목 수

        Returns:
            list: (종목코드, 점수, 설명) 형태의 스윙 트레이딩 적합 종목 리스트
        """
        logger.info(f"{market} 시장에서 스윙 트레이딩 적합 종목 식별 시작")
        
        if not df_dict:
            logger.warning("분석할 데이터가 없습니다.")
            return []
        
        swing_candidates = []
        
        for symbol, df in df_dict.items():
            if df.empty:
                continue
                
            try:
                # 스윙 트레이딩 적합성 점수 계산
                swing_score = 0
                explanation_parts = []
                
                # 1. 변동성 분석 (적당한 변동성이 있어야 함)
                volatility = self._calculate_volatility(df)
                daily_range = volatility["avg_daily_range_pct"]
                
                # 일일 변동폭이 적당한 경우 (너무 작지도, 너무 크지도 않음)
                if 1.0 <= daily_range <= 3.0:
                    swing_score += 20
                    explanation_parts.append(f"적정 변동성({daily_range:.1f}%)")
                elif daily_range < 1.0:
                    swing_score -= 10
                    explanation_parts.append(f"변동성 부족({daily_range:.1f}%)")
                elif daily_range > 5.0:
                    swing_score -= 15
                    explanation_parts.append(f"과도한 변동성({daily_range:.1f}%)")
                elif 3.0 < daily_range <= 5.0:
                    swing_score += 10
                    explanation_parts.append(f"다소 높은 변동성({daily_range:.1f}%)")
                
                # 2. 거래량 안정성 (거래량이 너무 불안정하면 스윙에 부적합)
                volume = df['Volume'].tail(20)
                volume_std = volume.std() / volume.mean()  # 거래량의 변동계수
                
                if volume_std < 0.5:
                    swing_score += 15
                    explanation_parts.append("안정적인 거래량")
                elif volume_std > 1.0:
                    swing_score -= 10
                    explanation_parts.append("불안정한 거래량")
                
                # 3. 추세의 명확성 (추세가 명확할수록 스윙에 유리)
                # 단기/장기 이동평균선의 방향성
                if 'SMA_short' in df.columns and 'SMA_long' in df.columns:
                    short_ma = df['SMA_short'].tail(10)
                    long_ma = df['SMA_long'].tail(10)
                    
                    # 단기 이동평균선의 기울기
                    short_slope = (short_ma.iloc[-1] - short_ma.iloc[0]) / short_ma.iloc[0] * 100
                    
                    if abs(short_slope) > 3.0:  # 뚜렷한 방향성 (3% 이상 변화)
                        swing_score += 15
                        explanation_parts.append(f"뚜렷한 추세({short_slope:.1f}%)")
                    elif abs(short_slope) < 1.0:  # 횡보 시장
                        swing_score -= 5
                        explanation_parts.append("횡보 시장")
                
                # 4. RSI 중간 구간 (과매수/과매도 구간이 아닌, 추세 전환 가능성)
                if 'RSI' in df.columns:
                    rsi = df['RSI'].iloc[-1]
                    
                    if 35 <= rsi <= 65:  # 중간 구간 (스윙에 적합)
                        swing_score += 10
                        explanation_parts.append(f"중간 RSI({rsi:.1f})")
                    elif rsi < 30 or rsi > 70:  # 과매수/과매도 (급격한 변화 가능성)
                        swing_score -= 5
                        explanation_parts.append(f"극단 RSI({rsi:.1f})")
                
                # 5. 주기적 패턴 확인 (스윙에 유리)
                # 최근 데이터의 자기상관계수 계산 (주기적 패턴 확인)
                close_pct_change = df['Close'].pct_change().tail(30).dropna()
                if len(close_pct_change) >= 10:  # 충분한 데이터가 있는 경우
                    # 자기상관계수가 클수록 주기적 패턴이 있을 가능성
                    autocorr = close_pct_change.autocorr(lag=5)  # 5일 지연 자기상관
                    
                    if abs(autocorr) > 0.2:  # 약한 주기성 존재
                        swing_score += 10
                        explanation_parts.append("주기적 패턴 감지")
                
                # 6. GPT 분석 (추세 및 스윙 적합성)
                additional_info = {
                    "analysis_purpose": "swing_trading",
                    "market": market,
                    "volatility_data": volatility
                }
                
                # GPT 분석 수행
                analysis = self.analyzer.analyze_stock(df, symbol, "trend", additional_info)
                analysis_text = analysis.get("analysis", "").lower()
                
                # 스윙 트레이딩 관련 키워드 확인
                swing_keywords = ["스윙", "swing", "oscillation", "상승하락 반복", "지지", "저항", "반등", "조정"]
                if any(keyword in analysis_text for keyword in swing_keywords):
                    swing_score += 15
                    explanation_parts.append("GPT 스윙 패턴 확인")
                
                # 스윙에 불리한 키워드 확인
                negative_keywords = ["단방향", "지속 상승", "지속 하락", "폭락", "급등", "급변동"]
                if any(keyword in analysis_text for keyword in negative_keywords):
                    swing_score -= 15
                    explanation_parts.append("불안정한 패턴")
                
                # 7. 추가 분석을 위해 GPT에 직접 스윙 적합성 질문
                swing_prompt = f"이 {symbol} 종목이 스윙 트레이딩에 얼마나 적합한지 1-10 척도로 평가해주세요. 1은 매우 부적합, 10은 매우 적합합니다. 숫자로만 답변하세요."
                swing_response = self.analyzer.client.chat.completions.create(
                    model=self.analyzer.model,
                    messages=[
                        {"role": "system", "content": "당신은 스윙 트레이딩 전문가입니다. 1-10 척도로 스윙 트레이딩 적합도를 평가합니다."},
                        {"role": "user", "content": swing_prompt}
                    ],
                    max_tokens=10,
                    temperature=0.3
                )
                
                # 응답에서 숫자 추출 시도
                swing_text = swing_response.choices[0].message.content.strip()
                
                try:
                    # 숫자만 추출 (1-10 사이 값인지 확인)
                    swing_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', swing_text)))
                    if 1 <= swing_num <= 10:
                        # 1-10 척도를 -50 ~ +50 점수로 변환 (5.5가 중간점)
                        gpt_score = (swing_num - 5.5) * 10
                        swing_score += gpt_score
                except:
                    # 숫자 추출에 실패하면 기본 점수 사용
                    pass
                
                # 최종 스윙 적합성 점수 정규화 (0-100)
                normalized_score = max(0, min(100, swing_score + 50))
                
                # 설명 생성
                if explanation_parts:
                    explanation = f"스윙 적합도: {normalized_score:.1f}/100 - {', '.join(explanation_parts)}"
                else:
                    explanation = f"스윙 적합도: {normalized_score:.1f}/100"
                
                # 손절매/익절 수준 분석 추가
                try:
                    stop_levels = self.analyze_stop_levels(df, symbol)
                    explanation += f" (손절: {stop_levels['stop_loss_pct']}%, 익절: {stop_levels['take_profit_pct']}%)"
                except Exception as e:
                    logger.warning(f"{symbol} 손절/익절 수준 분석 중 오류: {e}")
                
                # 결과 추가
                swing_candidates.append((symbol, normalized_score, explanation))
                logger.info(f"{symbol} 스윙 트레이딩 적합성 분석 완료: 점수 {normalized_score:.1f}")
                
            except Exception as e:
                logger.error(f"{symbol} 스윙 트레이딩 적합성 분석 중 오류 발생: {e}")
        
        # 점수 기준 정렬 (내림차순) 및 상위 n개 반환
        return sorted(swing_candidates, key=lambda x: x[1], reverse=True)[:top_n]
    
    def analyze_realtime_opportunity(self, symbol, price_data, current_price, market_context=None):
        """
        GPT와 기술적 지표를 활용하여 실시간 트레이딩 기회를 분석합니다.
        
        Args:
            symbol: 종목 코드
            price_data: 실시간 주가 데이터 (DataFrame)
            current_price: 현재가
            market_context: 시장 상황에 대한 추가 컨텍스트 (옵션)
            
        Returns:
            dict: 트레이딩 기회 분석 결과
        """
        try:
            # 1. 기술적 신호 계산
            technical_signals = self._calculate_realtime_signals(price_data, symbol, current_price)
            
            # 기술적 신호만으로 충분히 강한 경우, GPT 분석 스킵
            if technical_signals["signal"] != "NEUTRAL" and technical_signals["signal_strength"] > 0.8:
                logger.info(f"{symbol}: 강한 기술적 신호 감지됨 ({technical_signals['signal']}, 강도: {technical_signals['signal_strength']:.2f})")
                return {
                    "action": technical_signals["signal"],
                    "confidence": technical_signals["signal_strength"],
                    "reasoning": f"강한 기술적 신호에 기반함: {technical_signals['indicators']}",
                    "model": "technical_only",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "price": current_price
                }
            
            # 2. GPT 분석 준비
            # 효율성을 위해 데이터를 요약
            recent_data = price_data.tail(20).copy() if len(price_data) > 20 else price_data.copy()
            price_summary = {
                "current_price": current_price,
                "day_change_pct": (current_price / price_data['close'].iloc[-2] - 1) * 100 if len(price_data) > 1 else 0,
                "week_change_pct": (current_price / price_data['close'].iloc[-6] - 1) * 100 if len(price_data) > 5 else 0,
                "volatility": price_data['close'].pct_change().std() * 100,
                "volume_change": (price_data['volume'].iloc[-1] / price_data['volume'].iloc[-6:].mean()) if len(price_data) > 5 else 1
            }
            
            # 3. GPT로 기술적 신호 해석 및 강화
            gpt_analysis = self._get_gpt_realtime_insight(symbol, technical_signals, price_summary, market_context)
            
            # 4. 기술적 신호와 GPT 분석 결과 통합
            final_action = gpt_analysis.get("action", technical_signals["signal"])
            
            # 기본 신뢰도는 기술적 신호의 강도에서 시작
            base_confidence = technical_signals["signal_strength"]
            
            # GPT의 신뢰도 가중치 (0.3~0.7)
            gpt_weight = min(max(gpt_analysis.get("confidence", 0.5), 0.3), 0.7)
            
            # 최종 신뢰도 계산 (기술적 신호 50%, GPT 분석 50% 가중치)
            final_confidence = (base_confidence * 0.5) + (gpt_weight * 0.5)
            
            # GPT와 기술적 신호가 일치하면 신뢰도 상승
            if gpt_analysis.get("action") == technical_signals["signal"]:
                final_confidence = min(final_confidence + 0.1, 0.95)
            
            return {
                "action": final_action,
                "confidence": final_confidence,
                "technical_signals": technical_signals,
                "gpt_analysis": gpt_analysis.get("reasoning", "GPT 분석 없음"),
                "model": gpt_analysis.get("model", "hybrid"),
                "timestamp": datetime.datetime.now().isoformat(),
                "price": current_price
            }
            
        except Exception as e:
            logger.error(f"{symbol} 실시간 거래 기회 분석 중 오류: {str(e)}")
            return {
                "action": "ERROR",
                "confidence": 0,
                "reasoning": f"분석 중 오류 발생: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat(),
                "price": current_price
            }
    
    def _calculate_realtime_signals(self, data, symbol, current_price):
        """
        실시간 기술적 신호를 계산하는 헬퍼 메서드
        
        Args:
            data: 실시간 주가 데이터
            symbol: 종목 코드
            current_price: 현재가
            
        Returns:
            dict: 기술적 신호 지표 모음
        """
        try:
            # 충분한 데이터가 있는지 확인
            if len(data) < 30:
                logger.warning(f"{symbol}: 실시간 신호 계산을 위한 충분한 데이터가 없음 (필요: 30, 제공: {len(data)})")
                return {
                    "signal": "NEUTRAL",
                    "signal_strength": 0.5,
                    "indicators": {},
                    "price": current_price
                }
            
            # 볼린저 밴드 계산
            data['MA20'] = data['close'].rolling(window=20).mean()
            data['stddev'] = data['close'].rolling(window=20).std()
            data['upper_band'] = data['MA20'] + (data['stddev'] * 2)
            data['lower_band'] = data['MA20'] - (data['stddev'] * 2)
            
            # RSI 계산 (14일) - 0으로 나누기 오류 방지 개선
            delta = data['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
            
            # 0으로 나누기 방지를 위한 강화된 안전장치
            epsilon = 1e-10  # 아주 작은 값으로 대체
            
            # loss가 0에 가까우면 RSI는 100에 가까워짐 (모든 변화가 긍정적인 경우)
            rs = gain / (loss + epsilon)
            data['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD 계산
            data['ema12'] = data['close'].ewm(span=12, adjust=False).mean()
            data['ema26'] = data['close'].ewm(span=26, adjust=False).mean()
            data['macd'] = data['ema12'] - data['ema26']
            data['signal_line'] = data['macd'].ewm(span=9, adjust=False).mean()
            
            # 최신 데이터 포인트 가져오기
            latest = data.iloc[-1]
            
            # 신호 계산
            signals = {}
            signal_strength = 0.5  # 기본값: 중립
            buy_signals = 0
            sell_signals = 0
            
            # 볼린저 밴드 신호
            if current_price < latest['lower_band']:
                signals['bollinger'] = 'BUY'
                buy_signals += 1
            elif current_price > latest['upper_band']:
                signals['bollinger'] = 'SELL'
                sell_signals += 1
            else:
                signals['bollinger'] = 'NEUTRAL'
            
            # RSI 신호
            if latest['RSI'] < 30:
                signals['rsi'] = 'BUY'
                buy_signals += 1
            elif latest['RSI'] > 70:
                signals['rsi'] = 'SELL'
                sell_signals += 1
            else:
                signals['rsi'] = 'NEUTRAL'
            
            # MACD 신호
            if latest['macd'] > latest['signal_line']:
                signals['macd'] = 'BUY'
                buy_signals += 1
            elif latest['macd'] < latest['signal_line']:
                signals['macd'] = 'SELL'
                sell_signals += 1
            else:
                signals['macd'] = 'NEUTRAL'
            
            # 이동평균선 트렌드
            data['ma50'] = data['close'].rolling(window=50).mean()
            data['ma200'] = data['close'].rolling(window=200).mean()
            
            if len(data) >= 200 and not data['ma200'].isna().iloc[-1]:
                if latest['ma50'] > latest['ma200']:
                    signals['ma_trend'] = 'BULLISH'
                    buy_signals += 0.5
                elif latest['ma50'] < latest['ma200']:
                    signals['ma_trend'] = 'BEARISH'
                    sell_signals += 0.5
                else:
                    signals['ma_trend'] = 'NEUTRAL'
            
            # 모멘텀 지표 (ROC - Rate of Change)
            data['roc'] = data['close'].pct_change(periods=10) * 100
            if latest['roc'] > 2:
                signals['momentum'] = 'BULLISH'
                buy_signals += 0.5
            elif latest['roc'] < -2:
                signals['momentum'] = 'BEARISH'
                sell_signals += 0.5
            else:
                signals['momentum'] = 'NEUTRAL'
            
            # 최종 신호 계산
            total_indicators = 5  # 볼린저, RSI, MACD, MA 트렌드, 모멘텀
            
            if buy_signals > sell_signals and buy_signals >= 2:
                signal = "BUY"
                signal_strength = 0.5 + (buy_signals / total_indicators * 0.5)
            elif sell_signals > buy_signals and sell_signals >= 2:
                signal = "SELL"
                signal_strength = 0.5 + (sell_signals / total_indicators * 0.5)
            else:
                signal = "NEUTRAL"
                signal_strength = 0.5
            
            # 캡핑
            signal_strength = min(signal_strength, 0.95)
            
            return {
                "signal": signal,
                "signal_strength": signal_strength,
                "indicators": {
                    "bollinger": {
                        "signal": signals['bollinger'],
                        "upper": float(latest['upper_band']),
                        "lower": float(latest['lower_band']),
                        "ma20": float(latest['MA20'])
                    },
                    "rsi": {
                        "signal": signals['rsi'],
                        "value": float(latest['RSI'])
                    },
                    "macd": {
                        "signal": signals['macd'],
                        "macd_line": float(latest['macd']),
                        "signal_line": float(latest['signal_line'])
                    },
                    "ma_trend": signals.get('ma_trend', 'NEUTRAL'),
                    "momentum": signals.get('momentum', 'NEUTRAL'),
                },
                "price": current_price
            }
            
        except Exception as e:
            logger.error(f"{symbol} 실시간 기술 신호 계산 중 오류: {e}")
            return {
                "signal": "ERROR",
                "signal_strength": 0.5,
                "indicators": {},
                "price": current_price
            }
    
    def analyze_realtime_trading(self, symbol, stock_data, current_price=None, is_holding=False, avg_price=0, name=None):
        """
        실시간 트레이딩을 위한 종목 분석 (디비/캐시 사용 안함)
        
        Args:
            symbol (str): 종목 코드
            stock_data (DataFrame): 종목 가격 데이터
            current_price (float): 현재가
            is_holding (bool): 보유 여부
            avg_price (float): 평균 매수가 (보유 중인 경우)
            name (str): 종목명 (선택사항)
            
        Returns:
            dict: 분석 결과 및 매매 신호
        """
        try:
            logger.info(f"{symbol} 실시간 트레이딩 분석 시작")
            
            # 직접 분석에 필요한 데이터 준비
            data_summary = {}
            
            if stock_data is not None and not stock_data.empty:
                # 최근 데이터 요약
                recent_data = stock_data.tail(5)
                price_changes = recent_data['Close'].pct_change() * 100
                
                # 기술적 지표 추가
                if 'RSI' in stock_data.columns:
                    rsi_values = stock_data['RSI'].tail(5).tolist()
                    data_summary['RSI'] = [round(val, 2) for val in rsi_values if not pd.isna(val)]
                    data_summary['current_RSI'] = round(stock_data['RSI'].iloc[-1], 2) if not pd.isna(stock_data['RSI'].iloc[-1]) else None
                    
                if 'MACD' in stock_data.columns and 'MACD_signal' in stock_data.columns:
                    data_summary['MACD'] = round(stock_data['MACD'].iloc[-1], 4) if not pd.isna(stock_data['MACD'].iloc[-1]) else None
                    data_summary['MACD_signal'] = round(stock_data['MACD_signal'].iloc[-1], 4) if not pd.isna(stock_data['MACD_signal'].iloc[-1]) else None
                    data_summary['MACD_hist'] = round(stock_data['MACD'].iloc[-1] - stock_data['MACD_signal'].iloc[-1], 4)
                    
                if 'SMA_short' in stock_data.columns and 'SMA_long' in stock_data.columns:
                    data_summary['SMA_short'] = round(stock_data['SMA_short'].iloc[-1], 2) if not pd.isna(stock_data['SMA_short'].iloc[-1]) else None
                    data_summary['SMA_long'] = round(stock_data['SMA_long'].iloc[-1], 2) if not pd.isna(stock_data['SMA_long'].iloc[-1]) else None
                    
                # 거래량 분석
                if 'Volume' in stock_data.columns:
                    avg_volume = stock_data['Volume'].tail(20).mean()
                    latest_volume = stock_data['Volume'].iloc[-1]
                    data_summary['volume_ratio'] = round(latest_volume / avg_volume, 2) if avg_volume > 0 else 0
            
            # 보유 상태 정보
            holding_info = ""
            if is_holding and avg_price > 0:
                profit_loss_pct = ((current_price / avg_price) - 1) * 100
                holding_info = f"""
현재 보유 중: 예
평균 매수가: {avg_price:,.0f}원
현재 손익률: {profit_loss_pct:.2f}%
"""
            
            # GPT 프롬프트 구성
            prompt = f"""당신은 실시간 주식 트레이딩 전문가입니다. 다음 종목에 대한 실시간 매매 신호를 분석해주세요:

종목: {name or symbol} ({symbol})
현재가: {current_price:,.0f}원
{holding_info}

기술적 지표 및 시장 데이터:
{data_summary}

다음 요청사항에 따라 분석을 진행하고 JSON 형식으로 응답해 주세요:

1. 현재 주가와 기술적 지표를 분석하여 매수/매도/홀딩 추천
2. 매매 추천의 신뢰도 점수 (0.0~1.0)
3. 추천 이유를 명확하고 간결하게 설명
4. 목표가와 손절가 제시
5. 예상 보유기간

결과는 반드시 다음 키를 포함한 JSON 형식으로 제공해주세요:
{{"action": "BUY", "SELL", 또는 "HOLD" 중 하나,
"confidence": 0.0~1.0 사이의 신뢰도,
"analysis_summary": "분석 요약 (200자 이내)",
"target_price": 목표가,
"stop_loss": 손절가,
"expected_holding_period": "예상 보유 기간"}}

반드시 올바른 JSON 형식으로 응답해주세요. 모든 문자열은 쌍따옴표로 감싸주세요."""

            # GPT에 직접 요청
            response = self.analyzer.openai_client.chat.completions.create(
                model="gpt-4o",
                temperature=0.7,
                messages=[
                    {"role": "system", "content": "당신은 실시간 주식 트레이딩 신호 분석 전문가입니다. 응답은 항상 올바른 JSON 형식으로 제공해주세요."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_content = response.choices[0].message.content
            
            # JSON 추출 시도
            import re
            import json
            
            # 응답에서 JSON 부분만 추출
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```|(\{[\s\S]*\})', response_content)
            
            if json_match:
                # JSON 문자열 추출 및 전처리
                json_str = json_match.group(1) or json_match.group(2)
                
                # JSON 문법 오류 수정을 위한 전처리
                # 1. 작은따옴표를 큰따옴표로 변경
                json_str = re.sub(r"'([^']*)':", r'"\1":', json_str)
                json_str = re.sub(r':\s*\'([^\']*)\'', r': "\1"', json_str)
                
                # 2. 후행 쉼표 제거
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                
                # 3. 키와 문자열 값이 큰따옴표로 감싸져 있는지 확인
                json_str = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', json_str)
                
                try:
                    # 전처리된 JSON 문자열 파싱
                    result = json.loads(json_str)
                    
                    # 필요한 필드 추가
                    if 'symbol' not in result:
                        result['symbol'] = symbol
                    if 'current_price' not in result:
                        result['current_price'] = current_price
                    if 'timestamp' not in result:
                        result['timestamp'] = datetime.datetime.now().isoformat()
                    
                    logger.info(f"{symbol} JSON 파싱 성공")
                    return result
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 오류 (전처리 후): {e}, JSON 문자열: {json_str[:100]}...")
                    
                    # 파싱 실패 시 더 강력한 정규식으로 재시도
                    try:
                        # 모든 키-값 쌍을 개별적으로 추출
                        action_match = re.search(r'"action"\s*:\s*"([^"]*)"', json_str)
                        confidence_match = re.search(r'"confidence"\s*:\s*([\d\.]+)', json_str)
                        summary_match = re.search(r'"analysis_summary"\s*:\s*"([^"]*)"', json_str)
                        target_match = re.search(r'"target_price"\s*:\s*([\d\.]+)', json_str)
                        stop_match = re.search(r'"stop_loss"\s*:\s*([\d\.]+)', json_str)
                        period_match = re.search(r'"expected_holding_period"\s*:\s*"([^"]*)"', json_str)
                        
                        # 수동으로 결과 딕셔너리 구성
                        manual_result = {
                            'symbol': symbol,
                            'current_price': current_price,
                            'timestamp': datetime.datetime.now().isoformat()
                        }
                        
                        if action_match:
                            manual_result['action'] = action_match.group(1)
                        if confidence_match:
                            manual_result['confidence'] = float(confidence_match.group(1))
                        if summary_match:
                            manual_result['analysis_summary'] = summary_match.group(1)
                        if target_match:
                            manual_result['target_price'] = float(target_match.group(1))
                        if stop_match:
                            manual_result['stop_loss'] = float(stop_match.group(1))
                        if period_match:
                            manual_result['expected_holding_period'] = period_match.group(1)
                            
                        logger.info(f"{symbol} 수동 파싱 성공")
                        return manual_result
                        
                    except Exception as e2:
                        logger.error(f"수동 파싱 시도 중 오류: {e2}")
            
            # JSON 파싱 실패 시 기본 결과 반환
            logger.warning(f"{symbol} JSON 파싱 실패, 기본 결과 반환")
            from datetime import datetime
            
            # 텍스트 분석으로 action 결정 시도
            action = "HOLD"  # 기본값
            if "매수" in response_content or "BUY" in response_content.upper():
                action = "BUY"
            elif "매도" in response_content or "SELL" in response_content.upper():
                action = "SELL"
            
            fallback_result = {
                'symbol': symbol,
                'action': action,
                'confidence': 0.6,  # 중간 신뢰도
                'analysis_summary': response_content[:200] + "...",
                'target_price': current_price * 1.05 if action == "BUY" else (current_price * 0.95 if action == "SELL" else current_price),
                'stop_loss': current_price * 0.95 if action == "BUY" else (current_price * 1.05 if action == "SELL" else current_price),
                'expected_holding_period': "1-3일",
                'timestamp': datetime.now().isoformat(),
                'raw_response': response_content[:500]
            }
            
            return fallback_result
            
        except Exception as e:
            logger.error(f"{symbol} 실시간 트레이딩 분석 중 오류: {e}")
            return {
                'symbol': symbol,
                'action': "ERROR",
                'confidence': 0.0,
                'analysis_summary': f"분석 중 오류 발생: {str(e)}",
                'timestamp': datetime.datetime.now().isoformat()
            }
    
    def fully_autonomous_decision(self, market_data, available_cash, current_positions):
        """
        GPT 모델 기반 완전 자율 매매 결정 (디비/캐시 사용 안함)
        
        Args:
            market_data (dict): 시장 데이터 (종목별 DataFrame)
            available_cash (float): 주문 가능 현금
            current_positions (dict): 현재 보유 포지션 정보
            
        Returns:
            dict: 매수/매도 결정 목록
        """
        try:
            logger.info(f"GPT 완전 자율 매매 결정 시작 (가용 현금: {available_cash:,.0f}원, 보유 종목: {len(current_positions)}개)")
            
            # 결과 초기화
            decisions = {
                'buy_decisions': [],
                'sell_decisions': [],
                'hold_decisions': [],
                'timestamp': get_current_time().isoformat()
            }
            
            # 1. 매도 결정 - 보유 종목 분석
            for symbol, position in current_positions.items():
                try:
                    # 종목 데이터 가져오기
                    stock_df = market_data.get(symbol)
                    if stock_df is None or stock_df.empty:
                        logger.warning(f"{symbol} 데이터가 없어 분석을 건너뜁니다")
                        continue
                        
                    qty = position.get('quantity', 0)
                    avg_price = position.get('avg_price', 0)
                    current_price = position.get('current_price', 0)
                    
                    # 최신 현재가 확인
                    if not pd.isna(stock_df['Close'].iloc[-1]):
                        current_price = stock_df['Close'].iloc[-1]
                    
                    # GPT 분석 요청 (디비/캐시 사용 안함)
                    analysis = self.analyze_realtime_trading(
                        symbol=symbol,
                        stock_data=stock_df,
                        current_price=current_price,
                        is_holding=True,
                        avg_price=avg_price,
                        name=position.get('name', symbol)
                    )
                    
                    action = analysis.get('action')
                    confidence = analysis.get('confidence', 0.0)
                    
                    # 매도 결정
                    if action == 'SELL' and confidence >= self.sell_confidence_threshold:
                        # 매도 결정에 필요한 정보 추가
                        # 0으로 나누기 방지 로직 추가
                        profit_loss_pct = 0.0
                        if avg_price > 0:
                            profit_loss_pct = ((current_price / avg_price) - 1) * 100
                        
                        sell_decision = {
                            'symbol': symbol,
                            'name': position.get('name', symbol),
                            'quantity': qty,
                            'price': current_price,
                            'avg_price': avg_price,
                            'profit_loss_pct': profit_loss_pct,
                            'confidence': confidence,
                            'reason': analysis.get('analysis_summary', '매도 신호')
                        }
                        
                        decisions['sell_decisions'].append(sell_decision)
                        logger.info(f"매도 결정: {symbol}, 수량: {qty}, 손익: {profit_loss_pct:.2f}%, 신뢰도: {confidence:.2f}")
                    else:
                        # 홀딩 결정
                        decisions['hold_decisions'].append({
                            'symbol': symbol,
                            'name': position.get('name', symbol),
                            'reason': analysis.get('analysis_summary', '홀딩 유지')
                        })
                        
                except Exception as e:
                    logger.error(f"{symbol} 매도 결정 분석 중 오류: {e}")
            
            # 2. 매수 결정 - 시장 기회 분석
            
            # 매수할 수 있는 여력이 있는지 확인
            if available_cash < 1000000:  # 최소 100만원 필요
                logger.info(f"가용 현금({available_cash:,.0f}원)이 부족하여 매수 분석 건너뜀")
                return decisions
                
            # 이미 최대 보유 종목 수에 도달했는지 확인
            max_positions = getattr(self.config, 'GPT_AUTONOMOUS_MAX_POSITIONS', 7)
            if len(current_positions) >= max_positions:
                logger.info(f"최대 보유 종목 수({max_positions}개)에 도달하여 매수 분석 건너뜀")
                return decisions
            
            # 가장 최근 단타매매/급등주 기회 중 점수가 높은 종목 가져오기
            opportunities = self.get_momentum_opportunities(min_score=80)
            
            # 기회가 없는 경우 새로운 종목 추천 요청 (최대 5개)
            if len(opportunities) < 3:
                new_symbols = self.get_day_trading_candidates('KR', max_count=5, use_cache=False)
                
                # 새로운 종목 중 이미 보유 중인 것 제외
                new_symbols = [s for s in new_symbols if s not in current_positions]
                
                for symbol in new_symbols:
                    try:
                        # 종목 데이터 가져오기
                        stock_df = market_data.get(symbol)
                        if stock_df is None or stock_df.empty:
                            continue
                            
                        current_price = stock_df['Close'].iloc[-1]
                        
                        # 모멘텀/급등주 분석 요청
                        analysis = self.analyzer.analyze_momentum_stock(
                            symbol=symbol,
                            stock_data=stock_df,
                            current_price=current_price,
                            use_cache=False
                        )
                        
                        # 기회에 추가
                        if analysis and (analysis.get('momentum_score', 0) > 70 or analysis.get('day_trading_score', 0) > 70):
                            opportunity = {
                                'symbol': symbol,
                                'momentum_score': analysis.get('momentum_score', 0),
                                'day_trading_score': analysis.get('day_trading_score', 0),
                                'current_price': current_price,
                                'target_price': analysis.get('target_price', current_price * 1.05),
                                'stop_loss': analysis.get('stop_loss', current_price * 0.95),
                                'strategy': analysis.get('strategy', '단타매매'),
                                'market': 'KR'
                            }
                            self.add_momentum_opportunity(opportunity)
                            opportunities.append(opportunity)
                            
                    except Exception as e:
                        logger.error(f"{symbol} 기회 분석 중 오류: {e}")
            
            # 매수 가능한 종목 선정 (최대 2개)
            buy_candidates = opportunities[:3]
            
            # 각 매수 후보에 대해 매수 여부 결정
            for candidate in buy_candidates:
                symbol = candidate.get('symbol')
                
                # 이미 보유 중인 종목 제외
                if symbol in current_positions:
                    continue
                    
                try:
                    momentum_score = candidate.get('momentum_score', 0)
                    day_trading_score = candidate.get('day_trading_score', 0)
                    price = candidate.get('current_price', 0)
                    
                    # 가격이 0이거나 None인 경우 처리
                    if price is None or price <= 0:
                        logger.warning(f"{symbol} 가격이 유효하지 않습니다: {price}")
                        continue
                    
                    # 점수가 충분히 높은 경우만 매수 고려
                    if momentum_score >= 80 or day_trading_score >= 80:
                        # 단타 매매에 적합한 금액 결정 (가용 현금의 10-20%)
                        allocation_pct = 0.1  # 기본 10%
                        if momentum_score > 90 or day_trading_score > 90:
                            allocation_pct = 0.2  # 점수가 매우 높으면 20%
                            
                        # 공격적 모드면 비중 증가
                        if self.aggressive_mode:
                            allocation_pct *= 1.5  # 50% 증가
                            
                        # 최대 주문 금액 제한
                        max_amount = min(
                            available_cash * allocation_pct, 
                            self.autonomous_max_trade_amount
                        )
                        
                        # 수량 계산 (0으로 나누기 방지)
                        quantity = 0
                        if price > 0:
                            quantity = int(max_amount / price)
                            
                        if quantity < 1:
                            continue
                            
                        # 매수 결정 추가
                        buy_reason = f"모멘텀 점수: {momentum_score}/100, 단타 점수: {day_trading_score}/100"
                        if candidate.get('strategy'):
                            buy_reason += f", 전략: {candidate.get('strategy')}"
                            
                        buy_decision = {
                            'symbol': symbol,
                            'name': candidate.get('name', symbol),
                            'price': price,
                            'quantity': quantity,
                            'amount': price * quantity,
                            'target_price': candidate.get('target_price', price * 1.05),
                            'stop_loss': candidate.get('stop_loss', price * 0.95),
                            'reason': buy_reason
                        }
                        
                        decisions['buy_decisions'].append(buy_decision)
                        logger.info(f"매수 결정: {symbol}, 수량: {quantity}, 금액: {price * quantity:,.0f}원, 이유: {buy_reason}")
                        
                except Exception as e:
                    logger.error(f"{symbol} 매수 결정 중 오류: {e}")
            
            return decisions
            
        except Exception as e:
            logger.error(f"GPT 완전 자율 매매 결정 중 오류: {e}")
            return {
                'buy_decisions': [],
                'sell_decisions': [],
                'hold_decisions': [],
                'error': str(e),
                'timestamp': get_current_time().isoformat()
            }
    
    def send_momentum_stocks_to_kakao(self, min_score=70, max_count=10):
        """
        급등주 및 단타매매 적합 종목 리스트를 카카오톡으로 전송
        
        Args:
            min_score (int): 최소 점수 기준 (0-100)
            max_count (int): 최대 종목 수
            
        Returns:
            bool: 전송 성공 여부
        """
        try:
            # 모멘텀 기회 가져오기
            opportunities = self.get_momentum_opportunities(min_score=min_score)
            
            if not opportunities:
                logger.info(f"카카오톡 전송할 급등/단타 종목이 없습니다 (최소 점수: {min_score})")
                return False
                
            # 최대 종목 수 제한
            opportunities = opportunities[:max_count]
            
            # 메시지 생성
            now = get_current_time_str(format_str="%Y-%m-%d %H:%M")
            message = f"🔥 추천 급등/단타 종목 ({now})\n\n"
            
            # 급등주 섹션 (모멘텀 점수 기준)
            momentum_stocks = [opp for opp in opportunities if opp.get('momentum_score', 0) >= min_score]
            if momentum_stocks:
                message += "📈 급등주 TOP 리스트\n"
                message += "┌────────────────────\n"
                
                for i, stock in enumerate(momentum_stocks[:5]):
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', symbol)
                    momentum_score = stock.get('momentum_score', 0)
                    current_price = stock.get('current_price', 0)
                    
                    # 종목명 (코드)
                    message += f"│ {i+1}. {name} ({symbol})\n"
                    # 모멘텀 점수
                    message += f"│   모멘텀 점수: {momentum_score:.1f}/100\n"
                    # 현재가 (있는 경우만)
                    if current_price > 0:
                        message += f"│   현재가: {int(current_price):,}원\n"
                    # 매매 전략 (있는 경우만)
                    strategy = stock.get('strategy', '')
                    if strategy:
                        message += f"│   추천 전략: {strategy}\n"
                    
                    # 마지막 항목이 아니면 구분선 추가
                    if i < len(momentum_stocks[:5]) - 1:
                        message += "│ ----------------------\n"
                        
                message += "└────────────────────\n\n"
            
            # 단타매매 섹션 (단타 점수 기준)
            day_trading_stocks = [opp for opp in opportunities if opp.get('day_trading_score', 0) >= min_score]
            if day_trading_stocks:
                message += "💰 단타매매 추천 종목\n"
                message += "┌────────────────────\n"
                
                for i, stock in enumerate(day_trading_stocks[:5]):
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', symbol)
                    day_score = stock.get('day_trading_score', 0)
                    current_price = stock.get('current_price', 0)
                    
                    # 종목명 (코드)
                    message += f"│ {i+1}. {name} ({symbol})\n"
                    # 단타 점수
                    message += f"│   단타 점수: {day_score:.1f}/100\n"
                    # 현재가 (있는 경우만)
                    if current_price > 0:
                        message += f"│   현재가: {int(current_price):,}원\n"
                    
                    # 매매 전략 (있는 경우만)
                    strategy = stock.get('strategy', '')
                    if strategy:
                        message += f"│   추천 전략: {strategy}\n"
                        
                    # 목표가/손절가 (있는 경우만)
                    target_price = stock.get('target_price', 0)
                    stop_loss = stock.get('stop_loss', 0)
                    if target_price > 0 and stop_loss > 0:
                        message += f"│   목표가: {int(target_price):,}원 / 손절가: {int(stop_loss):,}원\n"
                    
                    # 마지막 항목이 아니면 구분선 추가
                    if i < len(day_trading_stocks[:5]) - 1:
                        message += "│ ----------------------\n"
                        
                message += "└────────────────────\n\n"
            
            # 메시지 끝 마무리
            message += f"⏱️ {now} 기준\n"
            message += f"(최소 점수 기준: {min_score}점)"
            
            # 메시지 전송을 위한 KakaoSender 인스턴스 생성
            # (kakao_sender.py 모듈이 있다고 가정)
            try:
                from src.notification.kakao_sender import KakaoSender
                kakao = KakaoSender(self.config)
                logger.info(f"카카오톡으로 급등/단타 종목 리스트 ({len(opportunities)}개) 전송 시도")
                return kakao.send_message(message)
            except ImportError:
                logger.error("KakaoSender 모듈을 가져올 수 없습니다.")
                return False
                
        except Exception as e:
            logger.error(f"급등/단타 종목 카카오톡 전송 중 오류: {e}")
            return False