"""
Google Gemini API를 활용한 주식 분석 모듈
"""
import os
import logging
import json
import time
import pandas as pd
import numpy as np
import google.generativeai as genai
from dotenv import load_dotenv
from ..utils.time_utils import get_current_time, get_current_time_str, format_timestamp

# 환경 변수 로드 (.env 파일)
load_dotenv()

# 로깅 설정
logger = logging.getLogger('GeminiAnalyzer')

# JSON 변환을 위한 유틸리티 함수
def json_default(obj):
    """
    JSON으로 직렬화할 수 없는 객체 처리 함수
    
    Args:
        obj: 변환할 객체
        
    Returns:
        JSON 직렬화 가능한 형태로 변환된 객체
    """
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return str(obj)

class GeminiAnalyzer:
    """Google Gemini API를 활용한 주식 분석 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        
        # API 키 설정 (환경 변수 또는 config에서 가져옴)
        self.api_key = os.environ.get('GEMINI_API_KEY', getattr(config, 'GEMINI_API_KEY', None))
        
        if not self.api_key:
            logger.warning("Gemini API 키가 설정되지 않았습니다. Gemini 분석 기능을 사용할 수 없습니다.")
            
        # 모델 설정
        self.model = getattr(config, 'GEMINI_MODEL', "gemini-1.5-pro")
        self.max_tokens = getattr(config, 'GEMINI_MAX_TOKENS', 1000)
        self.temperature = getattr(config, 'GEMINI_TEMPERATURE', 0.7)
        
        # Gemini 설정
        if self.api_key:
            genai.configure(api_key=self.api_key)
            logger.info(f"Gemini 분석기 초기화 완료 (모델: {self.model})")
        else:
            logger.warning("Gemini API 키가 없어 API 호출 불가능")
            
        # 요청 제한 관리
        self.last_request_time = 0
        self.request_interval = getattr(config, 'GEMINI_REQUEST_INTERVAL', 0.8)  # 기본 0.8초
        
        # 할당량 초과 및 오류 관련 설정
        self.quota_exceeded = False
        self.last_quota_check = 0
        self.quota_reset_interval = getattr(config, 'GEMINI_QUOTA_RESET_INTERVAL', 3600)  # 기본 1시간
        self.max_retries = getattr(config, 'GEMINI_MAX_RETRIES', 2)
        self.retry_delay = getattr(config, 'GEMINI_RETRY_DELAY', 10)  # 초 단위
        
    def _prepare_data_for_analysis(self, df, symbol, additional_info=None):
        """
        분석을 위한 데이터 준비
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            additional_info: 추가 정보 (dict)
            
        Returns:
            dict: 분석을 위한 데이터
        """
        # 최근 데이터만 사용 (API 토큰 제한 때문에)
        recent_df = df.tail(10).copy()
        
        # 주요 통계 계산
        recent_close = recent_df['Close'].iloc[-1]
        avg_price_20d = df['Close'].tail(20).mean()
        price_change_1d = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
        price_change_5d = (df['Close'].iloc[-1] - df['Close'].iloc[-6]) / df['Close'].iloc[-6] * 100
        price_change_20d = (df['Close'].iloc[-1] - df['Close'].iloc[-21]) / df['Close'].iloc[-21] * 100
        
        # 볼륨 통계
        avg_volume_20d = df['Volume'].tail(20).mean()
        volume_change_ratio = df['Volume'].iloc[-1] / avg_volume_20d
        
        # 기술적 지표
        rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else None
        macd = df['MACD'].iloc[-1] if 'MACD' in df.columns else None
        macd_signal = df['MACD_signal'].iloc[-1] if 'MACD_signal' in df.columns else None
        
        # DataFrame을 records 형식으로 변환하여 Timestamp 인덱스 문제 해결
        recent_data = recent_df[['Open', 'High', 'Low', 'Close', 'Volume']].reset_index().to_dict('records')
        
        # 현재 날짜
        current_date = get_current_time_str("%Y-%m-%d")
        
        analysis_data = {
            "symbol": symbol,
            "current_date": current_date,
            "recent_data": recent_data,
            "statistics": {
                "current_price": float(recent_close),
                "20d_average_price": float(avg_price_20d),
                "price_change_1d": float(price_change_1d),
                "price_change_5d": float(price_change_5d),
                "price_change_20d": float(price_change_20d),
                "volume_vs_avg_ratio": float(volume_change_ratio)
            },
            "indicators": {
                "rsi": float(rsi) if rsi is not None else None,
                "macd": float(macd) if macd is not None else None,
                "macd_signal": float(macd_signal) if macd_signal is not None else None,
                "sma_short": float(df['SMA_short'].iloc[-1]) if 'SMA_short' in df.columns else None,
                "sma_long": float(df['SMA_long'].iloc[-1]) if 'SMA_long' in df.columns else None
            }
        }
        
        # 추가 정보 병합
        if additional_info and isinstance(additional_info, dict):
            analysis_data.update(additional_info)
            
        return analysis_data
        
    def _wait_for_rate_limit(self):
        """API 요청 간격 제한 관리"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self.last_request_time = time.time()
        
    def _check_quota_status(self):
        """
        할당량 초과 상태 확인 및 필요시 초기화
        
        Returns:
            bool: 할당량 초과 상태 여부
        """
        current_time = time.time()
        
        # 할당량 초과 후 일정 시간이 지났으면 초기화
        if self.quota_exceeded and (current_time - self.last_quota_check) > self.quota_reset_interval:
            logger.info("Gemini API 할당량 초과 상태 초기화 시도")
            self.quota_exceeded = False
            
        self.last_quota_check = current_time
        return self.quota_exceeded
    
    def _handle_api_error(self, error, retry_attempt=0):
        """
        API 오류 처리 로직
        
        Args:
            error: 발생한 예외
            retry_attempt: 현재 재시도 횟수
            
        Returns:
            tuple: (재시도 여부, 대기 시간)
        """
        error_str = str(error)
        
        # 할당량 초과 오류 처리
        if "429" in error_str and "quota" in error_str.lower():
            logger.warning(f"Gemini API 할당량 초과 감지! 상세: {error}")
            self.quota_exceeded = True
            self.last_quota_check = time.time()
            
            # 오류 메시지에서 retry_delay 추출 시도
            try:
                import re
                retry_seconds_match = re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_str)
                if retry_seconds_match:
                    retry_seconds = int(retry_seconds_match.group(1))
                    return False, retry_seconds
            except Exception as e:
                logger.debug(f"Retry delay 추출 실패: {e}")
                
            return False, 3600  # 할당량 초과시 1시간 대기 (기본값)
            
        # 네트워크 관련 일시적 오류
        elif any(err in error_str.lower() for err in ["timeout", "connection", "network", "500", "503"]):
            if retry_attempt < self.max_retries:
                wait_time = self.retry_delay * (retry_attempt + 1)  # 지수 백오프
                logger.info(f"일시적인 네트워크 오류 감지. {wait_time}초 후 재시도 ({retry_attempt+1}/{self.max_retries})")
                return True, wait_time
                
        # 기타 오류는 재시도하지 않음
        return False, 0
        
    def analyze_stock(self, df, symbol, analysis_type="general", additional_info=None):
        """
        주식 데이터 분석
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            analysis_type: 분석 유형 ("general", "risk", "trend", "recommendation")
            additional_info: 추가 정보 (dict)
            
        Returns:
            dict: 분석 결과
        """
        # API 키 확인
        if not self.api_key:
            logger.error("Gemini API 키가 설정되지 않아 분석할 수 없습니다.")
            return {"error": "API 키 미설정", "analysis": "Gemini 분석을 사용할 수 없습니다."}
        
        # 할당량 초과 상태 확인
        if self._check_quota_status():
            logger.warning("Gemini API 할당량이 초과되어 분석을 건너뜁니다.")
            return self._fallback_analysis(df, symbol, analysis_type, additional_info, "할당량 초과")
            
        # 최대 재시도 횟수만큼 시도
        for retry_attempt in range(self.max_retries + 1):
            try:
                # 데이터 준비
                data = self._prepare_data_for_analysis(df, symbol, additional_info)
                
                # 분석 유형에 따른 프롬프트 구성
                prompt_template = self._get_prompt_template(analysis_type)
                system_prompt = prompt_template["system"]
                user_prompt = prompt_template["user"].format(data=json.dumps(data, ensure_ascii=False, default=str))
                
                # API 호출 제한 관리
                self._wait_for_rate_limit()
                
                # Gemini 모델 생성
                generation_config = {
                    "max_output_tokens": self.max_tokens,
                    "temperature": self.temperature
                }
                
                model = genai.GenerativeModel(
                    model_name=self.model,
                    generation_config=generation_config
                )
                
                # API 호출
                logger.info(f"Gemini API 호출: {symbol} {analysis_type} 분석")
                chat = model.start_chat(history=[
                    {"role": "user", "parts": [system_prompt]}
                ])
                
                response = chat.send_message(user_prompt)
                
                # 응답 처리
                analysis_text = response.text
                
                result = {
                    "symbol": symbol,
                    "analysis_type": analysis_type,
                    "timestamp": get_current_time_str(),  # 직접 문자열로 변환된 현재 시간 사용
                    "analysis": analysis_text,
                    "data": data
                }
                
                logger.info(f"Gemini 분석 완료: {symbol}")
                return result
                
            except Exception as e:
                retry, wait_time = self._handle_api_error(e, retry_attempt)
                
                if retry and retry_attempt < self.max_retries:
                    logger.warning(f"Gemini API 오류 발생, {wait_time}초 후 재시도: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Gemini 분석 중 오류 발생: {e}")
                    error_reason = "할당량 초과" if self.quota_exceeded else str(e)
                    return self._fallback_analysis(df, symbol, analysis_type, additional_info, error_reason)
        
        # 모든 재시도 실패 시
        logger.error(f"모든 재시도 실패: {symbol} {analysis_type} 분석")
        return self._fallback_analysis(df, symbol, analysis_type, additional_info, "모든 재시도 실패")
    
    def _fallback_analysis(self, df, symbol, analysis_type, additional_info, error_reason):
        """
        Gemini API 실패 시 대체 분석 제공
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            analysis_type: 분석 유형
            additional_info: 추가 정보
            error_reason: 오류 원인
            
        Returns:
            dict: 대체 분석 결과
        """
        logger.info(f"대체 분석 제공: {symbol} - 원인: {error_reason}")
        
        # 간단한 기술적 지표 기반 자체 분석
        try:
            # ChatGPT 분석기 사용 가능 확인
            chatgpt_available = False
            try:
                from .chatgpt_analyzer import ChatGPTAnalyzer
                chatgpt_analyzer = ChatGPTAnalyzer(self.config)
                if chatgpt_analyzer.api_key:
                    chatgpt_available = True
            except ImportError:
                logger.debug("ChatGPTAnalyzer를 불러올 수 없습니다.")
                
            # 기존 분석 대신 ChatGPT 분석기 사용
            if chatgpt_available:
                logger.info(f"Gemini 대신 ChatGPT 분석기로 대체: {symbol}")
                result = chatgpt_analyzer.analyze_stock(df, symbol, analysis_type, additional_info)
                result["note"] = f"Gemini API {error_reason}로 ChatGPT 분석기로 대체되었습니다."
                return result
                
            # ChatGPT도 사용 불가능할 경우 간단한 자체 분석
            data = self._prepare_data_for_analysis(df, symbol, additional_info)
            
            # RSI 기반 단순 분석
            rsi = data['indicators']['rsi']
            price_change_5d = data['statistics']['price_change_5d']
            sma_short = data['indicators']['sma_short']
            sma_long = data['indicators']['sma_long']
            
            analysis_text = f"[자동 생성된 기본 분석 - Gemini API {error_reason}]\n\n"
            analysis_text += f"{symbol} 종목 분석:\n"
            
            # RSI 분석
            if rsi is not None:
                if rsi > 70:
                    analysis_text += f"• RSI({rsi:.2f})가 과매수 구간(70 이상)에 있어 단기 조정 가능성이 있습니다.\n"
                elif rsi < 30:
                    analysis_text += f"• RSI({rsi:.2f})가 과매도 구간(30 이하)에 있어 반등 가능성이 있습니다.\n"
                else:
                    analysis_text += f"• RSI({rsi:.2f})는 중립 구간에 있습니다.\n"
            
            # 5일 가격 변동 분석
            if price_change_5d > 5:
                analysis_text += f"• 최근 5일간 {price_change_5d:.2f}% 상승했습니다. 단기 모멘텀이 긍정적입니다.\n"
            elif price_change_5d < -5:
                analysis_text += f"• 최근 5일간 {price_change_5d:.2f}% 하락했습니다. 단기 모멘텀이 부정적입니다.\n"
            else:
                analysis_text += f"• 최근 5일간 가격 변동({price_change_5d:.2f}%)이 제한적입니다.\n"
            
            # SMA 교차 분석
            if sma_short is not None and sma_long is not None:
                if sma_short > sma_long:
                    analysis_text += "• 단기 이동평균선이 장기 이동평균선 위에 위치해 상승 추세에 있습니다.\n"
                else:
                    analysis_text += "• 단기 이동평균선이 장기 이동평균선 아래에 위치해 하락 추세에 있습니다.\n"
            
            analysis_text += f"\n참고: 이 분석은 Gemini API {error_reason}로 인해 자동 생성된 간단한 분석입니다."
            
            return {
                "symbol": symbol,
                "analysis_type": analysis_type,
                "timestamp": get_current_time_str(),
                "analysis": analysis_text,
                "error": error_reason,
                "data": data,
                "fallback": True
            }
            
        except Exception as e:
            logger.error(f"대체 분석 생성 중 오류 발생: {e}")
            return {
                "symbol": symbol,
                "error": f"{error_reason} 및 대체 분석 생성 실패: {str(e)}",
                "analysis": f"분석 서비스 이용이 일시적으로 불가능합니다. (원인: Gemini API {error_reason})",
                "timestamp": get_current_time_str()
            }
    
    def analyze_signals(self, signal_data):
        """
        매매 신호 분석 (금융 데이터 기반 패턴 분석에 적합)
        
        Args:
            signal_data: 매매 신호 데이터 (dict)
            
        Returns:
            str: 분석 결과
        """
        # API 키 확인
        if not self.api_key:
            logger.error("Gemini API 키가 설정되지 않아 신호 분석을 할 수 없습니다.")
            return "Gemini 분석을 사용할 수 없습니다."
        
        # 할당량 초과 상태 확인
        if self._check_quota_status():
            logger.warning("Gemini API 할당량이 초과되어 신호 분석을 건너뜁니다.")
            return self._fallback_signal_analysis(signal_data, "할당량 초과")
            
        # 최대 재시도 횟수만큼 시도
        for retry_attempt in range(self.max_retries + 1):
            try:
                # 프롬프트 구성
                system_prompt = """당신은 주식 시장 전문 트레이더입니다. 제공된 기술적 지표와 시장 분석 정보를 바탕으로 매매 신호를 분석해주세요.
                명확한 매수/매도/홀드 판단과 그 근거를 제시하세요. 분석은 객관적 사실에 기반해야 합니다.
                최종적으로 종목의 '매수', '매도', '홀드' 중 하나의 결론과 그 신뢰도를 함께 제시하세요."""
                
                # JSON 직렬화
                user_prompt = f"""다음 종목({signal_data.get('symbol', '알 수 없음')})의 매매 신호를 분석해주세요.
                
                【 종목 정보 】
                {json.dumps(signal_data, ensure_ascii=False, indent=2, default=json_default)}
                
                위 데이터를 분석하여 명확한 매매 신호(매수/매도/홀드)와 그 이유를 제시해주세요.
                또한 그 신호의 신뢰도(0.0~1.0)도 함께 알려주세요.
                응답의 마지막에는 결론(매수/매도/홀드)과 신뢰도를 명확하게 표시해주세요.
                """
                
                # API 호출 제한 관리
                self._wait_for_rate_limit()
                
                # Gemini 모델 생성
                generation_config = {
                    "max_output_tokens": self.max_tokens,
                    "temperature": self.temperature
                }
                
                model = genai.GenerativeModel(
                    model_name=self.model,
                    generation_config=generation_config
                )
                
                # API 호출
                logger.info(f"매매 신호 분석 API 호출: {signal_data.get('symbol', '알 수 없음')}")
                chat = model.start_chat(history=[
                    {"role": "user", "parts": [system_prompt]}
                ])
                
                response = chat.send_message(user_prompt)
                
                # 응답 처리
                analysis_text = response.text
                logger.info(f"매매 신호 분석 완료: {signal_data.get('symbol', '알 수 없음')}")
                return analysis_text
                
            except Exception as e:
                retry, wait_time = self._handle_api_error(e, retry_attempt)
                
                if retry and retry_attempt < self.max_retries:
                    logger.warning(f"매매 신호 분석 중 오류, {wait_time}초 후 재시도: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"매매 신호 분석 중 오류 발생: {e}")
                    error_reason = "할당량 초과" if self.quota_exceeded else str(e)
                    return self._fallback_signal_analysis(signal_data, error_reason)
        
        # 모든 재시도 실패 시
        return self._fallback_signal_analysis(signal_data, "모든 재시도 실패")
    
    def _fallback_signal_analysis(self, signal_data, error_reason):
        """
        매매 신호 분석 실패 시 대체 분석 제공
        
        Args:
            signal_data: 매매 신호 데이터
            error_reason: 오류 원인
            
        Returns:
            str: 대체 분석 결과
        """
        symbol = signal_data.get('symbol', '알 수 없음')
        logger.info(f"대체 매매 신호 분석 제공: {symbol} - 원인: {error_reason}")
        
        try:
            # ChatGPT 분석 시도
            try:
                from .chatgpt_analyzer import ChatGPTAnalyzer
                chatgpt_analyzer = ChatGPTAnalyzer(self.config)
                if chatgpt_analyzer.api_key:
                    logger.info(f"Gemini 대신 ChatGPT로 신호 분석 대체: {symbol}")
                    result = chatgpt_analyzer.analyze_signals(signal_data)
                    return f"{result}\n\n[참고: Gemini API {error_reason}로 인해 ChatGPT 분석으로 대체되었습니다.]"
            except ImportError:
                logger.debug("ChatGPTAnalyzer를 불러올 수 없습니다.")
            
            # 간단한 규칙 기반 분석
            analysis = f"[자동 생성된 기본 분석 - Gemini API {error_reason}]\n\n"
            analysis += f"{symbol} 종목 매매 신호 분석:\n\n"
            
            # 기본 지표들이 있는지 확인
            rsi = signal_data.get('rsi', signal_data.get('RSI', None))
            macd = signal_data.get('macd', signal_data.get('MACD', None))
            macd_signal = signal_data.get('macd_signal', signal_data.get('MACD_signal', None))
            price_change = signal_data.get('price_change_1d', signal_data.get('price_change', 0))
            
            signals = []
            
            # RSI 기반 신호
            if rsi is not None:
                if float(rsi) > 70:
                    signals.append({"type": "매도", "reason": f"RSI({rsi:.2f})가 과매수 구간(70 이상)에 있습니다.", "weight": 0.6})
                elif float(rsi) < 30:
                    signals.append({"type": "매수", "reason": f"RSI({rsi:.2f})가 과매도 구간(30 이하)에 있습니다.", "weight": 0.6})
                else:
                    signals.append({"type": "홀드", "reason": f"RSI({rsi:.2f})가 중립 구간에 있습니다.", "weight": 0.4})
            
            # MACD 기반 신호
            if macd is not None and macd_signal is not None:
                if float(macd) > float(macd_signal):
                    signals.append({"type": "매수", "reason": "MACD가 시그널 라인 위에 있어 상승 추세입니다.", "weight": 0.5})
                else:
                    signals.append({"type": "매도", "reason": "MACD가 시그널 라인 아래에 있어 하락 추세입니다.", "weight": 0.5})
            
            # 가격 변동 기반 신호
            if price_change is not None:
                if float(price_change) > 3:
                    signals.append({"type": "매도", "reason": f"오늘 주가가 크게 상승({price_change:.2f}%)했습니다. 단기 이익 실현을 고려해볼 수 있습니다.", "weight": 0.3})
                elif float(price_change) < -3:
                    signals.append({"type": "매수", "reason": f"오늘 주가가 크게 하락({price_change:.2f}%)했습니다. 저점 매수를 고려해볼 수 있습니다.", "weight": 0.3})
                else:
                    signals.append({"type": "홀드", "reason": f"오늘 주가 변동({price_change:.2f}%)이 제한적입니다.", "weight": 0.2})
            
            # 신호가 없으면
            if not signals:
                return f"{analysis}충분한 기술적 지표가 제공되지 않아 정확한 분석이 어렵습니다.\n\n결론: 홀드 (신뢰도: 낮음)\n\n[참고: 이 분석은 Gemini API {error_reason}로 인해 자동 생성된 기본 분석입니다.]"
            
            # 가중치 기반 최종 신호 결정
            buy_weight = sum(s["weight"] for s in signals if s["type"] == "매수")
            sell_weight = sum(s["weight"] for s in signals if s["type"] == "매도")
            hold_weight = sum(s["weight"] for s in signals if s["type"] == "홀드")
            
            total_weight = buy_weight + sell_weight + hold_weight
            if total_weight > 0:
                buy_ratio = buy_weight / total_weight
                sell_ratio = sell_weight / total_weight
                hold_ratio = hold_weight / total_weight
                
                # 각 신호의 근거 추가
                analysis += "분석 근거:\n"
                for signal in signals:
                    analysis += f"• {signal['reason']}\n"
                
                analysis += "\n"
                
                # 최종 결정
                if max(buy_ratio, sell_ratio, hold_ratio) == buy_ratio:
                    confidence = buy_ratio * 0.8  # 최대 0.8 신뢰도
                    analysis += f"결론: 매수 (신뢰도: {confidence:.1f})\n"
                elif max(buy_ratio, sell_ratio, hold_ratio) == sell_ratio:
                    confidence = sell_ratio * 0.8  # 최대 0.8 신뢰도
                    analysis += f"결론: 매도 (신뢰도: {confidence:.1f})\n"
                else:
                    confidence = hold_ratio * 0.7  # 최대 0.7 신뢰도
                    analysis += f"결론: 홀드 (신뢰도: {confidence:.1f})\n"
            else:
                analysis += "결론: 홀드 (신뢰도: 낮음)\n"
                
            analysis += f"\n[참고: 이 분석은 Gemini API {error_reason}로 인해 자동 생성된 기본 분석입니다.]"
            return analysis
            
        except Exception as e:
            logger.error(f"대체 매매 신호 분석 생성 중 오류 발생: {e}")
            return f"죄송합니다. Gemini API {error_reason} 및 대체 분석 생성 실패로 인해 매매 신호 분석을 제공할 수 없습니다."
    
    def _get_prompt_template(self, analysis_type):
        """
        분석 유형에 따른 프롬프트 템플릿 반환
        
        Args:
            analysis_type: 분석 유형
            
        Returns:
            dict: 시스템 및 사용자 프롬프트
        """
        templates = {
            "general": {
                "system": "당신은 주식 시장 분석 전문가입니다. 제공된 기술적 지표와 가격 데이터를 바탕으로 객관적이고 전문적인 분석을 제공합니다. 주관적인 투자 조언보다는 데이터에 기반한 분석에 집중하세요.",
                "user": "다음 주식 데이터를 분석해주세요. 최근 추세, 기술적 지표의 신호, 주요 지지선과 저항선을 포함한 종합적인 분석을 제공해주세요.\n\n{data}"
            },
            "risk": {
                "system": "당신은 주식 시장 위험 분석 전문가입니다. 주어진 데이터에서 위험 요소와 잠재적인 위기 징후를 파악하는 데 특화되어 있습니다. 객관적인 위험 분석만 제공하세요.",
                "user": "다음 주식 데이터의 위험 요소를 분석해주세요. 변동성, 하락 위험, 시장 평균 대비 성과, 그리고 잠재적인 위험 신호를 포함한 분석을 제공해주세요.\n\n{data}"
            },
            "trend": {
                "system": "당신은 주식 시장 추세 분석 전문가입니다. 제공된 데이터에서 단기 및 중장기 추세를 파악하고 미래 방향성을 예측하는 데 전문성이 있습니다. 객관적인 추세 분석만 제공하세요.",
                "user": "다음 주식 데이터의 추세를 분석해주세요. 이동평균선, RSI, MACD 등의 지표를 활용하여 현재 추세와 향후 예상되는 추세 변화에 대한 분석을 제공해주세요.\n\n{data}"
            },
            "recommendation": {
                "system": "당신은 주식 시장 분석 전문가이지만, 특정 주식의 매수/매도 추천을 하지 않습니다. 투자 결정을 직접 조언하는 대신, 데이터에 기반한 객관적인 분석과 여러 시나리오를 제시해주세요.",
                "user": "다음 주식 데이터를 분석하고, 가능한 여러 시나리오를 제시해주세요. 직접적인 매수/매도 추천 대신, 여러 관점에서의 분석과 고려해야 할 팩터들을 설명해주세요.\n\n{data}"
            },
            "trading_signal": {
                "system": "당신은 주식 매매 신호 분석 AI입니다. 제공된 데이터를 바탕으로 매수/매도/홀드 신호와 그 신뢰도를 분석합니다. 기술적 지표, 추세, 리스크 요소를 종합적으로 고려하여 분석 결과를 제공하세요.",
                "user": "다음 주식 데이터를 분석하여 매수/매도/홀드 신호와 그 신뢰도에 대한 분석을 제공해주세요. 기술적 지표, 추세, 위험 요소를 종합적으로 고려하세요. 분석 결과는 명확하게 '매수 신호', '매도 신호', '홀드 신호' 중 하나를 포함해야 하며, 신뢰도(높음/중간/낮음)도 표시해주세요.\n\n{data}"
            }
        }
        
        return templates.get(analysis_type, templates["general"])
        
    def generate_daily_report(self, stock_data_dict, market="KR"):
        """
        일일 종합 리포트 생성 (일반적인 요약 작업에 적합)
        
        Args:
            stock_data_dict: {종목코드: DataFrame} 형태의 데이터
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            str: 종합 리포트
        """
        if not self.api_key or not stock_data_dict:
            return "데이터가 없거나 API가 설정되지 않아 리포트를 생성할 수 없습니다."
            
        # 할당량 초과 상태 확인
        if self._check_quota_status():
            logger.warning("Gemini API 할당량이 초과되어 일일 리포트 생성을 건너뜁니다.")
            return self._fallback_daily_report(stock_data_dict, market, "할당량 초과")
            
        for retry_attempt in range(self.max_retries + 1):
            try:
                # 시장 개요 데이터 준비
                market_summary = {
                    "market": market,
                    "date": get_current_time_str("%Y-%m-%d"),
                    "symbols_analyzed": list(stock_data_dict.keys()),
                    "stocks_data": []
                }
                
                for symbol, df in stock_data_dict.items():
                    if df.empty:
                        continue
                        
                    # 기본 통계 계산
                    recent_df = df.tail(1).iloc[0]
                    close_price = recent_df['Close']
                    
                    stock_info = {
                        "symbol": symbol,
                        "close": close_price,
                        "change_pct": (df['Close'].pct_change().iloc[-1] * 100),
                        "rsi": recent_df['RSI'] if 'RSI' in recent_df else None,
                        "volume": recent_df['Volume']
                    }
                    market_summary["stocks_data"].append(stock_info)
                
                # API 호출 제한 관리
                self._wait_for_rate_limit()
                
                # 일일 리포트 프롬프트
                system_prompt = """당신은 금융 시장 분석 전문가입니다. 
                제공된 여러 종목의 데이터를 분석하여 전체 시장 관점에서의 종합 리포트를 작성하세요. 
                오늘의 주요 트렌드, 특이사항, 각별히 주목할 종목들을 객관적인 관점에서 요약해주세요."""
                
                user_prompt = f"""다음 {market} 시장의 주식 데이터를 분석하여 일일 종합 리포트를 생성해주세요.
                핵심 트렌드, 업종별 흐름, 특히 주목할 만한 종목들을 포함해야 합니다.
                
                {json.dumps(market_summary, ensure_ascii=False, default=str)}"""
                
                # Gemini 모델 생성
                generation_config = {
                    "max_output_tokens": self.max_tokens * 2,  # 일일 리포트는 더 길게
                    "temperature": self.temperature
                }
                
                model = genai.GenerativeModel(
                    model_name=self.model,
                    generation_config=generation_config
                )
                
                # API 호출
                logger.info(f"Gemini API 호출: {market} 일일 종합 리포트 생성")
                chat = model.start_chat(history=[
                    {"role": "user", "parts": [system_prompt]}
                ])
                
                response = chat.send_message(user_prompt)
                
                report = response.text
                logger.info(f"{market} 일일 리포트 생성 완료")
                
                return report
                
            except Exception as e:
                retry, wait_time = self._handle_api_error(e, retry_attempt)
                
                if retry and retry_attempt < self.max_retries:
                    logger.warning(f"일일 리포트 생성 중 오류, {wait_time}초 후 재시도: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"일일 리포트 생성 중 오류 발생: {e}")
                    error_reason = "할당량 초과" if self.quota_exceeded else str(e)
                    return self._fallback_daily_report(stock_data_dict, market, error_reason)
        
        # 모든 재시도 실패 시
        return self._fallback_daily_report(stock_data_dict, market, "모든 재시도 실패")
    
    def _fallback_daily_report(self, stock_data_dict, market, error_reason):
        """
        일일 리포트 생성 실패 시 대체 리포트 제공
        
        Args:
            stock_data_dict: 주가 데이터 딕셔너리
            market: 시장 구분
            error_reason: 오류 원인
            
        Returns:
            str: 대체 일일 리포트
        """
        logger.info(f"대체 일일 리포트 제공: {market} - 원인: {error_reason}")
        
        try:
            # ChatGPT 분석 시도
            try:
                from .chatgpt_analyzer import ChatGPTAnalyzer
                chatgpt_analyzer = ChatGPTAnalyzer(self.config)
                if chatgpt_analyzer.api_key:
                    logger.info(f"Gemini 대신 ChatGPT로 일일 리포트 대체: {market}")
                    result = chatgpt_analyzer.generate_daily_report(stock_data_dict, market)
                    return f"{result}\n\n[참고: Gemini API {error_reason}로 인해 ChatGPT 분석으로 대체되었습니다.]"
            except ImportError:
                logger.debug("ChatGPTAnalyzer를 불러올 수 없습니다.")
            
            # 간단한 요약 리포트 생성
            report = f"[자동 생성된 기본 일일 리포트 - Gemini API {error_reason}]\n\n"
            report += f"{market} 시장 일일 요약 ({get_current_time_str('%Y-%m-%d')})\n\n"
            
            if not stock_data_dict:
                return report + "분석할 데이터가 없습니다."
                
            # 기본 통계 수집
            gainers = []
            losers = []
            neutral = []
            avg_change = 0
            total_count = 0
            
            for symbol, df in stock_data_dict.items():
                if df.empty:
                    continue
                    
                try:
                    last_close = df['Close'].iloc[-1]
                    prev_close = df['Close'].iloc[-2]
                    change_pct = ((last_close - prev_close) / prev_close) * 100
                    avg_change += change_pct
                    total_count += 1
                    
                    stock_info = {
                        "symbol": symbol,
                        "price": last_close,
                        "change_pct": change_pct
                    }
                    
                    if change_pct > 2:
                        gainers.append(stock_info)
                    elif change_pct < -2:
                        losers.append(stock_info)
                    else:
                        neutral.append(stock_info)
                except Exception as e:
                    logger.debug(f"종목 {symbol} 통계 계산 중 오류: {e}")
            
            # 전체 시장 흐름
            if total_count > 0:
                avg_change = avg_change / total_count
                report += f"전체 평균 변동률: {avg_change:.2f}%\n"
                report += f"총 분석 종목 수: {total_count}개\n\n"
                
                if avg_change > 1:
                    report += "시장 전체적으로 강세를 보이고 있습니다.\n"
                elif avg_change < -1:
                    report += "시장 전체적으로 약세를 보이고 있습니다.\n"
                else:
                    report += "시장은 보합세를 유지하고 있습니다.\n"
            
            # 상승 종목
            if gainers:
                report += "\n상승 종목 TOP 5:\n"
                for stock in sorted(gainers, key=lambda x: x['change_pct'], reverse=True)[:5]:
                    report += f"• {stock['symbol']}: {stock['price']:.2f} ({stock['change_pct']:.2f}%)\n"
            
            # 하락 종목
            if losers:
                report += "\n하락 종목 TOP 5:\n"
                for stock in sorted(losers, key=lambda x: x['change_pct'])[:5]:
                    report += f"• {stock['symbol']}: {stock['price']:.2f} ({stock['change_pct']:.2f}%)\n"
            
            report += f"\n[참고: 이 리포트는 Gemini API {error_reason}로 인해 자동 생성된 기본 리포트입니다.]"
            return report
            
        except Exception as e:
            logger.error(f"대체 일일 리포트 생성 중 오류 발생: {e}")
            return f"일일 시장 리포트 생성이 불가능합니다. (원인: Gemini API {error_reason} 및 대체 리포트 생성 실패)"