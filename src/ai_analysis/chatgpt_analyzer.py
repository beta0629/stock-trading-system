"""
OpenAI ChatGPT API를 활용한 주식 분석 모듈
"""
import os
import logging
import json
import time
import datetime
import pandas as pd
import openai
from dotenv import load_dotenv

# 환경 변수 로드 (.env 파일)
load_dotenv()

# 로깅 설정
logger = logging.getLogger('ChatGPTAnalyzer')

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
            logger.info(f"ChatGPT 분석기 초기화 완료 (모델: {self.model})")
        else:
            self.client = None
            
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
        
        analysis_data = {
            "symbol": symbol,
            "current_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "recent_data": recent_df[['Open', 'High', 'Low', 'Close', 'Volume']].to_dict('records'),
            "statistics": {
                "current_price": recent_close,
                "20d_average_price": avg_price_20d,
                "price_change_1d": price_change_1d,
                "price_change_5d": price_change_5d,
                "price_change_20d": price_change_20d,
                "volume_vs_avg_ratio": volume_change_ratio
            },
            "indicators": {
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "sma_short": df['SMA_short'].iloc[-1] if 'SMA_short' in df.columns else None,
                "sma_long": df['SMA_long'].iloc[-1] if 'SMA_long' in df.columns else None
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
                "timestamp": datetime.datetime.now().isoformat(),
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
                "system": "당신은 리스크 분석 전문가입니다. 제공된 데이터를 바탕으로 현재 주가의 위험 요소와 잠재적인 하락 가능성을 분석합니다. 보수적인 관점에서 리스크를 평가하세요.",
                "user": "다음 주식 데이터의 리스크를 분석해주세요. 현재 가격 수준의 위험도, 변동성 분석, 손실 가능성 및 리스크 대비 수익 잠재력을 평가해주세요.\n\n{data}"
            },
            "trend": {
                "system": "당신은 추세 분석 전문가입니다. 제공된 데이터를 바탕으로 주가의 현재 추세와 향후 추세 전환 가능성을 분석합니다. 모멘텀과 추세 강도에 집중하세요.",
                "user": "다음 주식 데이터의 추세를 분석해주세요. 현재 추세의 강도, 지속 가능성, 잠재적인 추세 전환 신호를 포함한 분석을 제공해주세요.\n\n{data}"
            },
            "recommendation": {
                "system": "당신은 투자 전략 컨설턴트입니다. 제공된 데이터를 바탕으로 투자자 관점에서의 전략적 제안을 제공합니다. 단, 직접적인 매수/매도 추천은 하지 말고, 투자자가 고려해야 할 요소들을 설명하세요.",
                "user": "다음 주식 데이터를 바탕으로 투자자가 고려해야 할 전략적 관점을 제공해주세요. 단기 및 중장기 관점에서의 접근 방법, 주의해야 할 요소, 기술적 지표의 함의를 분석해주세요.\n\n{data}"
            }
        }
        
        # 기본값은 general
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
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
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
    
    def analyze_signals(self, signals_data):
        """
        매매 신호 분석
        
        Args:
            signals_data: 매매 신호 데이터
            
        Returns:
            str: 분석 결과
        """
        if not self.client:
            return "API가 설정되지 않아 분석할 수 없습니다."
        
        try:
            # API 호출 제한 관리
            self._wait_for_rate_limit()
            
            # 신호 분석 프롬프트
            system_prompt = """당신은 알고리즘 트레이딩 전문가입니다. 
            제공된 매매 신호를 분석하여 전략적 함의와 고려해야 할 사항을 설명해주세요.
            기술적 지표의 의미와 함께 신호의 신뢰성을 평가하세요."""
            
            user_prompt = f"""다음 매매 신호를 분석하여 그 의미와 신뢰성을 평가해주세요.
            추가적으로 고려해야 할 요소들을 설명하고, 이 신호가 전체 시장 맥락에서 갖는 의미를 평가해주세요.
            
            {json.dumps(signals_data, ensure_ascii=False, default=str)}"""
            
            # API 호출
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            analysis = response.choices[0].message.content
            logger.info(f"신호 분석 완료: {signals_data['symbol']}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"신호 분석 중 오류 발생: {e}")
            return f"신호 분석 중 오류가 발생했습니다: {str(e)}"