"""
GPT-4 기반 트레이딩 전략 모듈

이 모듈은 GPT-4 API를 활용하여 주식 매매 신호를 생성합니다.
투자 결정을 내리기 위해 기술적 지표, 가격 데이터, 뉴스 정보 등을 종합적으로 분석합니다.
"""

import json
import logging
import datetime
import time
from enum import Enum
import pandas as pd
import requests
from openai import OpenAI

# 로깅 설정
logger = logging.getLogger('GPT_Trading')

class SignalType(Enum):
    """매매 신호 유형"""
    BUY = "BUY"          # 매수 신호
    SELL = "SELL"        # 매도 신호
    HOLD = "HOLD"        # 관망 신호
    UNKNOWN = "UNKNOWN"  # 불명확한 신호

class StrengthLevel(Enum):
    """신호 강도"""
    STRONG = "STRONG"    # 강한 신호
    MODERATE = "MODERATE"  # 중간 신호
    WEAK = "WEAK"        # 약한 신호

class GPTTradingStrategy:
    """GPT-4 기반 트레이딩 전략 클래스"""
    
    def __init__(self, config, news_api=None):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
            news_api: 뉴스 API 객체 (선택적)
        """
        self.config = config
        self.news_api = news_api
        
        # OpenAI API 설정
        self.api_key = config.OPENAI_API_KEY
        self.model = getattr(config, 'OPENAI_MODEL', "gpt-4o")
        self.client = OpenAI(api_key=self.api_key)
        
        # 요청 관리 설정
        self.last_request_time = 0
        self.request_interval = getattr(config, 'OPENAI_REQUEST_INTERVAL', 1.0)
        
        # 모델 프롬프트 설정
        self.system_prompt = self._get_system_prompt()
        
        # 캐싱 설정
        self.signal_cache = {}  # {종목코드: (타임스탬프, 신호)}
        self.signal_cache_ttl = 1800  # 30분 캐시 유효시간
        
        logger.info(f"GPT-4 트레이딩 전략 초기화 완료 (모델: {self.model})")
        
    def _get_system_prompt(self):
        """시스템 프롬프트 생성"""
        return """당신은 주식 트레이딩 전략 전문가입니다. 
        제공된 기술적 지표, 가격 데이터, 뉴스 및 시장 정보를 분석하여 명확한 매매 신호(BUY/SELL/HOLD)를 생성해야 합니다.
        
        매 답변은 다음 형식의 JSON으로 시작해야 합니다:
        {
          "signal": "BUY/SELL/HOLD",
          "strength": "STRONG/MODERATE/WEAK",
          "time_horizon": "SHORT/MEDIUM/LONG",
          "risk_level": "LOW/MEDIUM/HIGH",
          "confidence": 0-100,
          "reasoning": "간략한 이유",
          "key_factors": ["요인1", "요인2", "요인3"]
        }
        
        그 후에 상세 분석을 추가로 제공하세요. 수익 목표와 손절 수준도 제안해주세요.
        
        매매 신호는 다음과 같이 해석됩니다:
        - BUY: 현재 이 종목을 매수하는 것이 유리하다는 신호
        - SELL: 현재 이 종목을 매도하는 것이 유리하다는 신호
        - HOLD: 현재 이 종목에 대해 포지션을 유지하거나 신규 진입을 하지 않는 것이 좋다는 신호
        
        신호의 강도는 다음과 같이 해석됩니다:
        - STRONG: 매우 확실한 신호로, 즉각적인 조치가 권장됨
        - MODERATE: 중간 정도의 신호로, 다른 요소들도 함께 고려해야 함
        - WEAK: 약한 신호로, 추가 확인이 필요함

        시간 범위는 다음과 같습니다:
        - SHORT: 수일 내의 단기 관점
        - MEDIUM: 수주에서 수개월의 중기 관점
        - LONG: 6개월 이상의 장기 관점
        
        모든 분석은 데이터에 기반해야 하며, 주관적 의견이나 추측은 피하고, 
        도표상 명확한 패턴, 기술적 지표의 신호, 최근 뉴스의 영향 등 객관적 요소를 중심으로 분석하세요."""
        
    def _wait_for_rate_limit(self):
        """API 요청 간격 제한 관리"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self.last_request_time = time.time()
        
    def _prepare_trading_data(self, df, symbol, market):
        """
        트레이딩 분석을 위한 데이터 준비
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            dict: 분석을 위한 데이터
        """
        # 최근 데이터 선택 (너무 많은 데이터는 토큰 제한 초과 가능성)
        recent_df = df.tail(20).copy()
        earlier_df = df.iloc[-40:-20].copy() if len(df) >= 40 else None
        
        # 주요 기술적 지표 추출
        latest_row = recent_df.iloc[-1]
        prev_row = recent_df.iloc[-2] if len(recent_df) > 1 else None
        
        # 추세 정보 계산
        price_trend = "상승" if len(recent_df) > 1 and latest_row['Close'] > recent_df.iloc[-2]['Close'] else "하락"
        
        # 이동평균선 정보
        ma_data = {}
        sma_columns = [col for col in df.columns if 'SMA' in col or 'EMA' in col]
        for col in sma_columns:
            ma_data[col] = latest_row[col]
        
        # 볼륨 추세
        volume_avg = recent_df['Volume'].mean()
        volume_trend = "증가" if latest_row['Volume'] > volume_avg else "감소"
        
        # 뉴스 데이터 추가
        news_data = []
        if self.news_api:
            try:
                news = self.news_api.get_recent_news(symbol, market, limit=5)
                if news:
                    news_data = news
            except Exception as e:
                logger.warning(f"뉴스 데이터 가져오기 실패: {e}")
        
        # OHLCV 데이터
        ohlcv_data = recent_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict('records')
        
        # 기술적 지표 데이터
        indicators = {}
        tech_columns = [col for col in df.columns if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        for col in tech_columns:
            if col in latest_row:
                indicators[col] = latest_row[col]
        
        # 시장 정보
        market_info = {
            "KR": {
                "name": "한국 주식시장",
                "currency": "원",
                "timezone": "Asia/Seoul"
            },
            "US": {
                "name": "미국 주식시장",
                "currency": "USD",
                "timezone": "US/Eastern"
            }
        }.get(market, {"name": "기타", "currency": "Unknown", "timezone": "UTC"})
        
        # 최종 데이터 구성
        trading_data = {
            "symbol": symbol,
            "market": market,
            "market_info": market_info,
            "current_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "latest_price": latest_row['Close'],
            "price_change": (latest_row['Close'] - prev_row['Close']) / prev_row['Close'] * 100 if prev_row is not None else 0,
            "price_trend": price_trend,
            "volume_trend": volume_trend,
            "recent_data": ohlcv_data,
            "moving_averages": ma_data,
            "indicators": indicators,
            "news": news_data
        }
        
        return trading_data

    def get_trading_signal(self, df, symbol, market="KR"):
        """
        주식 매매 신호 생성
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            dict: 매매 신호 및 분석 결과
        """
        # 캐시 확인
        current_time = time.time()
        if symbol in self.signal_cache:
            cache_time, cache_data = self.signal_cache[symbol]
            if current_time - cache_time < self.signal_cache_ttl:
                logger.info(f"{symbol} 캐시된 신호 반환 (생성시간: {datetime.datetime.fromtimestamp(cache_time).strftime('%Y-%m-%d %H:%M:%S')})")
                return cache_data
        
        try:
            # 데이터 준비
            trading_data = self._prepare_trading_data(df, symbol, market)
            
            # 사용자 프롬프트 구성
            user_prompt = f"""다음 주식 데이터를 분석하여 BUY/SELL/HOLD 신호와 신호 강도를 결정해주세요.
            
            종목: {symbol}
            시장: {market}
            최근 종가: {trading_data['latest_price']}
            가격 변동(%): {trading_data['price_change']:.2f}%
            
            OHLCV 데이터 (최근 5일):
            {pd.DataFrame(trading_data['recent_data']).tail(5).to_string()}
            
            기술적 지표:
            {json.dumps(trading_data['indicators'], indent=2)}
            
            이동평균선:
            {json.dumps(trading_data['moving_averages'], indent=2)}
            
            뉴스 정보:
            {json.dumps(trading_data['news'], indent=2) if trading_data['news'] else "뉴스 정보 없음"}
            
            매매 신호(BUY/SELL/HOLD)와 강도(STRONG/MODERATE/WEAK), 그리고 상세 분석을 제공해주세요.
            반드시 요청한 JSON 형식으로 응답을 시작해주세요.
            """
            
            # API 요청 제한 관리
            self._wait_for_rate_limit()
            
            # API 호출
            logger.info(f"GPT API 호출: {symbol} 매매 신호 요청")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.3,  # 결정적 응답을 위해 낮은 온도 설정
                response_format={"type": "text"}  # 일반 텍스트 응답
            )
            
            # 응답 파싱
            response_text = response.choices[0].message.content
            logger.debug(f"GPT 응답: {response_text[:200]}...")
            
            # JSON 응답 추출
            try:
                # JSON 부분 찾기
                json_start = response_text.find('{')
                json_end = response_text.find('}', json_start) + 1
                
                if json_start >= 0 and json_end > json_start:
                    signal_json = json.loads(response_text[json_start:json_end])
                    
                    # 필수 필드 확인 및 기본값 설정
                    signal = signal_json.get('signal', 'HOLD').upper()
                    strength = signal_json.get('strength', 'MODERATE').upper()
                    
                    # 유효한 값인지 확인
                    if signal not in [s.value for s in SignalType]:
                        signal = SignalType.HOLD.value
                    if strength not in [s.value for s in StrengthLevel]:
                        strength = StrengthLevel.MODERATE.value
                        
                    # 최종 신호 데이터 구성
                    signal_data = {
                        "signal": signal,
                        "strength": strength,
                        "time_horizon": signal_json.get('time_horizon', 'SHORT'),
                        "risk_level": signal_json.get('risk_level', 'MEDIUM'),
                        "confidence": signal_json.get('confidence', 50),
                        "reasoning": signal_json.get('reasoning', '분석 정보 없음'),
                        "key_factors": signal_json.get('key_factors', [])
                    }
                    
                    # 분석 텍스트 추출 (JSON 이후 부분)
                    analysis_text = response_text[json_end:].strip()
                    
                else:
                    # JSON 파싱 실패 시 기본값 사용
                    logger.warning(f"{symbol} JSON 파싱 실패, 기본값 사용")
                    signal_data = {
                        "signal": SignalType.HOLD.value,
                        "strength": StrengthLevel.WEAK.value,
                        "time_horizon": "SHORT",
                        "risk_level": "MEDIUM",
                        "confidence": 0,
                        "reasoning": "분석 정보를 추출할 수 없습니다.",
                        "key_factors": []
                    }
                    analysis_text = response_text
                    
            except Exception as e:
                # JSON 파싱 오류 처리
                logger.error(f"{symbol} JSON 파싱 오류: {e}")
                signal_data = {
                    "signal": SignalType.HOLD.value,
                    "strength": StrengthLevel.WEAK.value,
                    "time_horizon": "SHORT",
                    "risk_level": "MEDIUM",
                    "confidence": 0,
                    "reasoning": f"분석 오류: {str(e)}",
                    "key_factors": []
                }
                analysis_text = response_text
            
            # 결과 데이터 구성
            result = {
                "symbol": symbol,
                "market": market,
                "timestamp": datetime.datetime.now().isoformat(),
                "signal_data": signal_data,
                "analysis_text": analysis_text,
                "data_used": trading_data
            }
            
            # 캐시에 저장
            self.signal_cache[symbol] = (current_time, result)
            
            logger.info(f"{symbol} 신호 생성 완료: {signal_data['signal']} ({signal_data['strength']})")
            return result
            
        except Exception as e:
            logger.error(f"매매 신호 생성 중 오류 발생: {e}")
            
            # 오류 발생 시 기본 응답
            return {
                "symbol": symbol,
                "market": market,
                "timestamp": datetime.datetime.now().isoformat(),
                "signal_data": {
                    "signal": SignalType.UNKNOWN.value,
                    "strength": StrengthLevel.WEAK.value,
                    "time_horizon": "SHORT",
                    "risk_level": "HIGH",
                    "confidence": 0,
                    "reasoning": f"오류 발생: {str(e)}",
                    "key_factors": []
                },
                "analysis_text": f"매매 신호를 생성하는 중 오류가 발생했습니다: {str(e)}",
                "error": str(e)
            }
    
    def get_signals_for_watchlist(self, watchlist, data_provider):
        """
        관심종목 리스트에 대한 매매 신호 일괄 생성
        
        Args:
            watchlist: 관심종목 리스트 [{symbol, market}]
            data_provider: 데이터 제공자 객체
            
        Returns:
            dict: {종목코드: 매매 신호} 형태의 결과
        """
        results = {}
        
        for item in watchlist:
            symbol = item.get('symbol')
            market = item.get('market', 'KR')
            
            try:
                # 데이터 가져오기
                df = data_provider.get_historical_data(symbol, market)
                
                if df is None or len(df) < 20:
                    logger.warning(f"{symbol} 데이터 불충분. 건너뜁니다.")
                    continue
                    
                # 매매 신호 생성
                signal = self.get_trading_signal(df, symbol, market)
                results[symbol] = signal
                
                # API 호출 간격 관리
                time.sleep(0.5)  # 추가 요청을 위한 짧은 대기
                
            except Exception as e:
                logger.error(f"{symbol} 신호 생성 중 오류 발생: {e}")
                results[symbol] = {
                    "symbol": symbol,
                    "error": str(e),
                    "signal_data": {
                        "signal": SignalType.UNKNOWN.value,
                        "strength": StrengthLevel.WEAK.value
                    }
                }
                
        return results
    
    def filter_strong_signals(self, signals_dict, signal_type=None, min_confidence=70):
        """
        강한 신호만 필터링
        
        Args:
            signals_dict: {종목코드: 신호} 형태의 딕셔너리
            signal_type: 필터링할 신호 유형 (None=모든 유형)
            min_confidence: 최소 신뢰도 (기본 70%)
            
        Returns:
            dict: 필터링된 신호 딕셔너리
        """
        filtered = {}
        
        for symbol, data in signals_dict.items():
            signal_data = data.get('signal_data', {})
            signal = signal_data.get('signal')
            strength = signal_data.get('strength')
            confidence = signal_data.get('confidence', 0)
            
            # 신호 유형 및 강도, 신뢰도 필터링
            if (signal_type is None or signal == signal_type) and \
               strength == StrengthLevel.STRONG.value and \
               confidence >= min_confidence:
                filtered[symbol] = data
                
        return filtered
    
    def evaluate_portfolio(self, portfolio_data):
        """
        포트폴리오 전체 평가 및 재조정 추천
        
        Args:
            portfolio_data: 포트폴리오 데이터 (종목별 데이터 포함)
            
        Returns:
            dict: 포트폴리오 평가 및 추천 사항
        """
        try:
            # API 요청 간격 관리
            self._wait_for_rate_limit()
            
            # 포트폴리오 분석 프롬프트
            system_prompt = """당신은 포트폴리오 관리 전문가입니다.
            제공된 포트폴리오 데이터와 시장 상황을 분석하여 포트폴리오 평가 및 조정 방안을 제안하세요.
            
            답변은 다음 형식의 JSON으로 시작해야 합니다:
            {
              "portfolio_health": "HEALTHY/CAUTION/WARNING",
              "risk_assessment": "LOW/MEDIUM/HIGH",
              "diversification": "GOOD/MODERATE/POOR",
              "suggestions": [
                {"action": "ADD/REDUCE/HOLD", "symbol": "종목코드", "reasoning": "이유"},
                ...
              ],
              "market_outlook": "BULLISH/NEUTRAL/BEARISH"
            }
            
            그 후 상세 분석과 전략적 제안을 제공하세요."""
            
            user_prompt = f"""다음 포트폴리오 데이터를 분석하고 평가해주세요. 현재 시장 상황에 적합한 조정 방안과 함께 상세한 분석을 제공해주세요.
            
{json.dumps(portfolio_data, ensure_ascii=False, default=str)}

다음 측면에서 포트폴리오를 평가해주세요:
1. 전반적인 건전성과 리스크 수준
2. 다각화 정도와 분산 투자 상태
3. 시장 상황에 맞는 자산 배분 적절성
4. 종목별 유지/증가/감소 추천
5. 단기 및 중장기 전망

현재 시장 상황을 고려한 구체적인 조정 방안을 제안해주세요."""

            # API 호출
            logger.info("GPT-4 API 호출: 포트폴리오 평가 및 추천")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            # 응답 텍스트 파싱
            response_text = response.choices[0].message.content
            
            # JSON 추출 시도
            portfolio_assessment = self._extract_json_from_response(response_text)
            
            # 결과 구성
            result = {
                "timestamp": datetime.datetime.now().isoformat(),
                "portfolio_assessment": portfolio_assessment if portfolio_assessment else {"error": "평가 데이터를 추출할 수 없습니다."},
                "detailed_analysis": self._clean_response_text(response_text)
            }
            
            logger.info("포트폴리오 평가 완료")
            return result
            
        except Exception as e:
            logger.error(f"포트폴리오 평가 중 오류 발생: {e}")
            return {
                "timestamp": datetime.datetime.now().isoformat(),
                "error": str(e),
                "portfolio_assessment": {"error": f"분석 중 오류: {str(e)}"}
            }
    
    def backtest_strategy(self, strategy_description, historical_data, initial_capital=10000000):
        """
        전략 백테스팅 (아직 구현되지 않음)
        
        Args:
            strategy_description: 전략 설명
            historical_data: 과거 가격 데이터
            initial_capital: 초기 자본금
            
        Returns:
            dict: 백테스팅 결과
        """
        # TODO: 백테스팅 로직 구현
        return {
            "status": "not_implemented",
            "message": "백테스팅 기능이 아직 구현되지 않았습니다."
        }