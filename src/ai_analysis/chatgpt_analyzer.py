"""
OpenAI ChatGPT API를 활용한 주식 분석 모듈
"""
import os
import logging
import json
import time
import pandas as pd
import numpy as np
import openai
from dotenv import load_dotenv
# datetime 모듈 대신 time_utils 사용
from ..utils.time_utils import get_current_time, get_current_time_str, format_timestamp

# 환경 변수 로드 (.env 파일)
load_dotenv()

# 로깅 설정
logger = logging.getLogger('ChatGPTAnalyzer')

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

class ChatGPTAnalyzer:
    """OpenAI ChatGPT API를 활용한 주식 분석 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        
        # API 키 설정 (환경 변수 또는 config에서 가져옴)
        self.api_key = os.environ.get('OPENAI_API_KEY', getattr(config, 'OPENAI_API_KEY', None))
        
        if not self.api_key:
            logger.warning("OpenAI API 키가 설정되지 않았습니다. ChatGPT 분석 기능을 사용할 수 없습니다.")
            
        # 모델 설정
        self.model = getattr(config, 'OPENAI_MODEL', "gpt-4o")
        self.max_tokens = getattr(config, 'OPENAI_MAX_TOKENS', 1000)
        self.temperature = getattr(config, 'OPENAI_TEMPERATURE', 0.7)
        
        # OpenAI 클라이언트 설정
        if self.api_key:
            openai.api_key = self.api_key
            self.client = openai.OpenAI(api_key=self.api_key)
            self.openai_client = self.client  # openai_client 속성 추가
            logger.info(f"ChatGPT 분석기 초기화 완료 (모델: {self.model})")
        else:
            self.client = None
            self.openai_client = None
            
        # 요청 제한 관리
        self.last_request_time = 0
        self.request_interval = getattr(config, 'OPENAI_REQUEST_INTERVAL', 1.0)  # 기본 1초
        
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
        
        # datetime.now() 대신 time_utils의 함수 사용
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
        if not self.client:
            logger.error("OpenAI API 키가 설정되지 않아 분석할 수 없습니다.")
            return {"error": "API 키 미설정", "analysis": "ChatGPT 분석을 사용할 수 없습니다."}
            
        try:
            # 데이터 준비
            data = self._prepare_data_for_analysis(df, symbol, additional_info)
            
            # 분석 유형에 따른 프롬프트 구성
            prompt_template = self._get_prompt_template(analysis_type)
            system_prompt = prompt_template["system"]
            user_prompt = prompt_template["user"].format(data=json.dumps(data, ensure_ascii=False, default=str))
            
            # API 호출 제한 관리
            self._wait_for_rate_limit()
            
            # API 호출
            logger.info(f"ChatGPT API 호출: {symbol} {analysis_type} 분석")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # 응답 처리
            analysis_text = response.choices[0].message.content
            
            result = {
                "symbol": symbol,
                "analysis_type": analysis_type,
                "timestamp": get_current_time_str(),  # format_timestamp 대신 get_current_time_str 직접 사용
                "analysis": analysis_text,
                "data": data
            }
            
            logger.info(f"ChatGPT 분석 완료: {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"ChatGPT 분석 중 오류 발생: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "analysis": "분석 중 오류가 발생했습니다."
            }
    
    def analyze_signals(self, signal_data):
        """
        매매 신호 분석
        
        Args:
            signal_data: 매매 신호 데이터 (dict)
            
        Returns:
            str: 분석 결과
        """
        if not self.client:
            logger.error("OpenAI API 키가 설정되지 않아 신호 분석을 할 수 없습니다.")
            return "ChatGPT 분석을 사용할 수 없습니다."
            
        try:
            # 프롬프트 구성
            system_prompt = """당신은 주식 시장 전문 트레이더입니다. 제공된 기술적 지표와 시장 분석 정보를 바탕으로 매매 신호를 분석해주세요.
            명확한 매수/매도/홀드 판단과 그 근거를 제시하세요. 분석은 객관적 사실에 기반해야 합니다.
            최종적으로 종목의 '매수', '매도', '홀드' 중 하나의 결론과 그 신뢰도를 함께 제시하세요."""
            
            # JSON 직렬화 수정 - json_default 함수 사용
            user_prompt = f"""다음 종목({signal_data.get('symbol', '알 수 없음')})의 매매 신호를 분석해주세요.
            
            【 종목 정보 】
            {json.dumps(signal_data, ensure_ascii=False, indent=2, default=json_default)}
            
            위 데이터를 분석하여 명확한 매매 신호(매수/매도/홀드)와 그 이유를 제시해주세요.
            또한 그 신호의 신뢰도(0.0~1.0)도 함께 알려주세요.
            응답의 마지막에는 결론(매수/매도/홀드)과 신뢰도를 명확하게 표시해주세요.
            """
            
            # API 호출 제한 관리
            self._wait_for_rate_limit()
            
            # API 호출
            logger.info(f"매매 신호 분석 API 호출: {signal_data.get('symbol', '알 수 없음')}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # 응답 처리
            analysis_text = response.choices[0].message.content
            logger.info(f"매매 신호 분석 완료: {signal_data.get('symbol', '알 수 없음')}")
            return analysis_text
            
        except Exception as e:
            logger.error(f"매매 신호 분석 중 오류 발생: {e}")
            return f"분석 중 오류가 발생했습니다: {str(e)}"
    
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
                "system": "당신은 주식 매매 신호 분석 AI입니다. 제공된 데이터를 바탕으로 매수/매도/홀드 신호와 그 신뢰도를 분석합니다. 기술적 지표, 추세, 리스크 요소를 종합적으로 고려하여 분석 결과를 제공하세요. JSON 형태가 아닌 텍스트 형태로 분석 결과를 제공하세요.",
                "user": "다음 주식 데이터를 분석하여 매수/매도/홀드 신호와 그 신뢰도에 대한 분석을 제공해주세요. 기술적 지표, 추세, 위험 요소를 종합적으로 고려하세요. 분석 결과는 명확하게 '매수 신호', '매도 신호', '홀드 신호' 중 하나를 포함해야 하며, 신뢰도(높음/중간/낮음)도 표시해주세요.\n\n{data}"
            }
        }
        
        return templates.get(analysis_type, templates["general"])
        
    def generate_daily_report(self, stock_data_dict, market="KR"):
        """
        일일 종합 리포트 생성
        
        Args:
            stock_data_dict: {종목코드: DataFrame} 형태의 데이터
            market: 시장 구분 ("KR" 또는 "US")
            
        Returns:
            str: 종합 리포트
        """
        if not self.client or not stock_data_dict:
            return "데이터가 없거나 API가 설정되지 않아 리포트를 생성할 수 없습니다."
            
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
            
            # API 호출
            logger.info(f"ChatGPT API 호출: {market} 일일 종합 리포트 생성")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens * 2,  # 일일 리포트는 더 길게
                temperature=self.temperature
            )
            
            report = response.choices[0].message.content
            logger.info(f"{market} 일일 리포트 생성 완료")
            
            return report
            
        except Exception as e:
            logger.error(f"일일 리포트 생성 중 오류 발생: {e}")
            return f"일일 리포트 생성 중 오류가 발생했습니다: {str(e)}"
        
    def analyze_stop_levels(self, analysis_data):
        """
        개별 종목에 적합한 손절매/익절 수준 분석
        
        Args:
            analysis_data: 분석 데이터 (dict)
            
        Returns:
            dict: 손절매/익절 분석 결과
        """
        if not self.client:
            logger.error("OpenAI API 키가 설정되지 않아 손절/익절 수준을 분석할 수 없습니다.")
            return {
                "recommendations": {
                    "stop_loss_pct": 5.0,  # 기본값
                    "take_profit_pct": 10.0,  # 기본값
                    "trailing_stop_distance": 3.0,  # 기본값
                }
            }
            
        try:
            # 프롬프트 구성
            system_prompt = """당신은 주식 트레이딩 리스크 관리 전문가입니다. 
            주어진 종목 데이터를 바탕으로 최적의 손절매(Stop-Loss), 익절(Take-Profit) 및 트레일링 스탑 수준을 분석하고 제안해야 합니다.
            각 종목의 변동성, 일일 변동폭, 추세 강도 등을 고려하여 적절한 비율을 제시하세요.
            응답은 반드시 정해진 JSON 포맷으로만 제공하세요."""
            
            # JSON 직렬화 수정 - json_default 함수 사용
            user_prompt = f"""다음 종목({analysis_data.get('symbol', '알 수 없음')})의 최적 손절매/익절 수준을 분석해주세요.
            
            【 종목 및 시장 정보 】
            {json.dumps(analysis_data, ensure_ascii=False, default=json_default)}
            
            위 데이터를 분석하여, 이 종목의 특성에 맞는 최적의 손절매/익절/트레일링스탑 비율을 제안해주세요.

            다음과 같은 JSON 포맷으로 응답해주세요. 주관적인 설명은 제외하고 JSON 데이터만 반환하세요:
            
            ```json
            {{
                "recommendations": {{
                    "stop_loss_pct": 5.0,
                    "take_profit_pct": 10.0,
                    "trailing_stop_distance": 3.0,
                    "explanation": "이 종목에 대한 설정값 설명"
                }},
                "volatility_analysis": "변동성 분석 요약"
            }}
            ```

            종목의 특성에 따라 값을 조정해주세요. 일반적으로:
            - 변동성이 큰 종목: 손절폭 넓게(5-15%), 익절폭 넓게(10-30%), 트레일링 스탑 거리 넓게(3-8%)
            - 변동성이 작은 종목: 손절폭 좁게(2-5%), 익절폭 좁게(5-10%), 트레일링 스탑 거리 좁게(1-3%)
            
            오직 JSON 데이터만 반환해주세요.
            """
            
            # API 호출 제한 관리
            self._wait_for_rate_limit()
            
            # API 호출
            logger.info(f"손절/익절 수준 분석 API 호출: {analysis_data.get('symbol', '알 수 없음')}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=0.3  # 낮은 temperature로 일관된 결과 유도
            )
            
            # 응답 처리
            response_text = response.choices[0].message.content
            
            # JSON 부분만 추출
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                try:
                    result = json.loads(json_str)
                    logger.info(f"손절/익절 수준 분석 완료: {analysis_data.get('symbol', '알 수 없음')}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 오류: {e}")
            
            # JSON 파싱 실패 시 기본값 반환
            logger.warning(f"JSON 파싱 실패, 기본값 반환: {response_text[:100]}...")
            return {
                "recommendations": {
                    "stop_loss_pct": 5.0,  # 기본값
                    "take_profit_pct": 10.0,  # 기본값
                    "trailing_stop_distance": 3.0,  # 기본값
                    "explanation": "기본값 사용 (JSON 파싱 오류)"
                },
                "volatility_analysis": "분석 실패"
            }
            
        except Exception as e:
            logger.error(f"손절/익절 수준 분석 중 오류 발생: {e}")
            return {
                "recommendations": {
                    "stop_loss_pct": 5.0,  # 기본값
                    "take_profit_pct": 10.0,  # 기본값
                    "trailing_stop_distance": 3.0,  # 기본값
                    "explanation": f"오류 발생: {str(e)}"
                },
                "volatility_analysis": "분석 오류"
            }