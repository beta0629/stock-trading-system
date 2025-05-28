"""
GPT 모델을 활용한 고급 트레이딩 전략 구현
"""
import logging
import pandas as pd
import numpy as np
import datetime
from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
# 시간 유틸리티 추가
from src.utils.time_utils import get_current_time, get_current_time_str, format_timestamp
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
        
        logger.info("GPT 트레이딩 전략 초기화 완료")
    
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
                    score += 10  # 적정 상승 추세
                    confidence_factors.append(('SMA', 0.6, 'BUY', '이동평균선 상승 추세 지속'))
            
            elif short_ma < long_ma:  # 하락 추세
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
            # analyze_stock 메서드를 통해 기본 분석 수행
            analysis_result = self.analyze_stock(df, symbol)
            
            signals = []
            
            # 신호가 BUY 또는 SELL이고 신뢰도가 임계값보다 높은 경우에만 신호 생성
            signal_type = analysis_result.get('signal')
            confidence = analysis_result.get('confidence', 0.0)
            
            if signal_type == 'BUY' and confidence >= self.buy_confidence_threshold:
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