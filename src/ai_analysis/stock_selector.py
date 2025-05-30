"""
GPT 기반 종목 선정 모듈

이 모듈은 GPT를 활용하여 주식 시장에서 유망 종목을 선정하기 위한 기능을 제공합니다.
다양한 전략(성장형, 배당형, 밸류, 모멘텀 등)을 기반으로 종목을 추천할 수 있습니다.
"""
import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional, Union
# 시간 유틸리티 추가
from src.utils.time_utils import get_current_time, get_current_time_str

logger = logging.getLogger('StockAnalysisSystem')

class StockSelector:
    """GPT를 활용한 종목 선정기 클래스"""
    
    def __init__(self, config):
        """
        GPT 종목 선정기 초기화
        
        Args:
            config: 설정 객체 (OpenAI API 키 등이 포함되어야 함)
        """
        self.config = config
        self.api_key = getattr(config, 'OPENAI_API_KEY', None)
        self.api_base = getattr(config, 'OPENAI_API_BASE', 'https://api.openai.com/v1')
        self.model = getattr(config, 'OPENAI_MODEL', 'gpt-4-turbo')
        self.max_tokens = getattr(config, 'OPENAI_MAX_TOKENS', 4000)
        
        # API 키가 없으면 환경 변수에서 가져오기 시도
        if not self.api_key:
            self.api_key = os.environ.get('OPENAI_API_KEY')
            
        if not self.api_key:
            logger.warning("OpenAI API 키가 설정되지 않았습니다. GPT 기반 종목 선정 기능이 제한됩니다.")
            
        # 캐시 파일 경로
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.kr_cache_file = os.path.join(self.cache_dir, 'kr_stock_recommendations.json')
        self.us_cache_file = os.path.join(self.cache_dir, 'us_stock_recommendations.json')
        
    def is_api_key_valid(self):
        """
        OpenAI API 키의 유효성을 검사합니다.
        
        Returns:
            bool: API 키가 유효한 경우 True, 그렇지 않으면 False
        """
        if not self.api_key:
            logger.warning("API 키가 설정되지 않았습니다.")
            return False
            
        try:
            # 간단한 요청으로 API 키 유효성 확인
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "간단한 API 키 유효성 확인입니다."},
                    {"role": "user", "content": "API 키가 유효한지 확인해주세요."}
                ],
                "max_tokens": 10
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=10  # 타임아웃 설정
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"API 키 유효성 확인 실패: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"API 키 유효성 확인 중 오류 발생: {e}")
            return False
            
    def _load_cached_recommendations(self, market):
        """
        캐시된 종목 추천 목록을 로드합니다.
        
        Args:
            market: 시장 코드 ("KR" 또는 "US")
            
        Returns:
            dict: 캐시된 추천 종목 목록. 파일이 없을 경우 기본 종목 목록 반환.
        """
        cache_file = self.kr_cache_file if market == "KR" else self.us_cache_file
        
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    logger.info(f"캐시된 {market} 시장 종목 목록을 로드했습니다.")
                    return cached_data
        except Exception as e:
            logger.error(f"캐시된 종목 목록 로드 중 오류 발생: {e}")
            
        # 캐시 파일이 없을 경우 기본 종목 목록 반환
        if market == "KR":
            return {
                "recommended_stocks": [
                    {"symbol": "005930", "name": "삼성전자", "sector": "반도체"},
                    {"symbol": "000660", "name": "SK하이닉스", "sector": "반도체"},
                    {"symbol": "051910", "name": "LG화학", "sector": "화학"},
                    {"symbol": "035420", "name": "NAVER", "sector": "인터넷 서비스"},
                    {"symbol": "096770", "name": "SK이노베이션", "sector": "에너지"},
                    {"symbol": "005380", "name": "현대차", "sector": "자동차"}
                ]
            }
        else:  # US
            return {
                "recommended_stocks": [
                    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
                    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
                    {"symbol": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology"},
                    {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "E-commerce"},
                    {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Social Media"}
                ]
            }
            
    def _cache_recommendations(self, market, recommendations):
        """
        종목 추천 목록을 캐시 파일에 저장합니다.
        
        Args:
            market: 시장 코드 ("KR" 또는 "US")
            recommendations: 저장할 추천 종목 목록 딕셔너리
            
        Returns:
            bool: 저장 성공 시 True, 실패 시 False
        """
        cache_file = self.kr_cache_file if market == "KR" else self.us_cache_file
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(recommendations, f, ensure_ascii=False, indent=2)
            logger.info(f"{market} 시장 종목 추천 목록을 캐시 파일에 저장했습니다.")
            return True
        except Exception as e:
            logger.error(f"종목 추천 목록 캐싱 중 오류 발생: {e}")
            return False
            
    def recommend_stocks(self, market: str = "KR", count: int = 5, strategy: str = "balanced") -> Dict[str, Any]:
        """
        GPT를 사용하여 시장 상황에 맞는 종목 추천
        
        Args:
            market: 시장 코드 ("KR": 한국, "US": 미국)
            count: 추천할 종목 수
            strategy: 투자 전략 ("balanced", "growth", "value", "dividend", "momentum")
            
        Returns:
            추천 종목 목록 및 분석 내용이 포함된 딕셔너리
        """
        logger.info(f"{market} 시장에 대한 {strategy} 전략 기반 종목 추천 시작")
        
        # API 키 유효성 확인
        if not self.is_api_key_valid():
            logger.warning("유효하지 않은 OpenAI API 키로 인해 캐시된 종목 목록을 사용합니다.")
            return self._load_cached_recommendations(market)
        
        # 현재 날짜/시간 정보 가져오기
        now = get_current_time()
        current_date = get_current_time_str("%Y년 %m월 %d일")
        current_year = now.year
        
        # 시장에 따라 다른 프롬프트 사용
        market_info = {
            "KR": {
                "name": "한국",
                "index": "KOSPI",
                "currency": "원",
                "symbols_example": "005930(삼성전자), 000660(SK하이닉스)"
            },
            "US": {
                "name": "미국",
                "index": "S&P 500",
                "currency": "달러",
                "symbols_example": "AAPL(Apple), MSFT(Microsoft)"
            }
        }.get(market, {})
        
        if not market_info:
            logger.error(f"지원하지 않는 시장 코드: {market}")
            return {"error": "지원하지 않는 시장 코드입니다."}
            
        # 전략별 프롬프트 수정
        strategy_description = {
            "balanced": "균형 잡힌 위험과 수익률의 안정적인 성장형 포트폴리오",
            "growth": "높은 성장성과 혁신성을 갖춘 성장주 중심 포트폴리오",
            "value": "저평가된 내재가치가 높은 가치주 중심 포트폴리오",
            "dividend": "안정적인 배당수익을 제공하는 배당주 중심 포트폴리오",
            "momentum": "최근 상승 추세가 강한 모멘텀 중심 포트폴리오"
        }.get(strategy, "균형 잡힌 포트폴리오")
        
        # GPT 프롬프트 구성
        prompt = f"""당신은 최고의 투자 전문가입니다. 오늘 날짜는 {current_date}입니다.
현재 {market_info['name']} 주식 시장 상황과 글로벌 경제 환경을 종합적으로 고려하여,
{strategy_description}에 적합한 {market_info['name']} 주식 {count}개를 추천해주세요.

각 종목에 대해 다음 정보를 포함하여 JSON 형식으로 응답해주세요:
1. 종목코드(symbol)
2. 종목명(name)
3. 주요 업종/섹터(sector)
4. 추천 이유(reason) - 간결하게 2-3문장
5. 주요 재무지표(key_metrics) - 예상 PER, ROE, 부채비율 등 중요 지표
6. 향후 12개월 목표가(target_price)
7. 투자 위험도(risk_level) - 1(매우 낮음)부터 10(매우 높음)
8. 포트폴리오 내 권장 비중(suggested_weight) - 퍼센트(%)

{market_info['name']} 시장의 종목코드는 {market_info['symbols_example']} 형식으로 정확히 표기해주세요.

마지막으로 전체 시장에 대한 간략한 전망과 선택한 종목들이 현재 경제 상황에서 왜 유망한지 설명해주세요.

응답은 다음과 같은 JSON 형식으로 제공해주세요:
{{
  "market_analysis": "현재 시장 상황 분석...",
  "investment_strategy": "{strategy} 전략 설명...",
  "recommended_stocks": [
    {{
      "symbol": "종목코드",
      "name": "종목명",
      "sector": "섹터",
      "reason": "추천 이유",
      "key_metrics": {{
        "per": 15.2,
        "roe": 12.5,
        "debt_ratio": 45.3
      }},
      "target_price": 50000,
      "risk_level": 7,
      "suggested_weight": 25
    }},
    ...
  ],
  "outlook": "향후 시장 전망 및 투자 제안"
}}"""

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 최고의 투자 전문가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=30  # 타임아웃 설정 증가
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                # API 호출 실패 시 캐시된 추천 목록 반환
                return self._load_cached_recommendations(market)
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            recommendations = json.loads(content)
            logger.info(f"{market} 시장 종목 추천 완료: {len(recommendations.get('recommended_stocks', []))}개")
            
            # 추천 결과 캐싱
            self._cache_recommendations(market, recommendations)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"종목 추천 중 오류 발생: {e}")
            # 오류 발생 시 캐시된 추천 목록 반환
            return self._load_cached_recommendations(market)
            
    def advanced_sector_selection(self, market: str = "KR", sectors_count: int = 3) -> Dict[str, Any]:
        """
        GPT를 사용하여 유망 산업 섹터 선정
        
        Args:
            market: 시장 코드 ("KR": 한국, "US": 미국)
            sectors_count: 추천할 섹터 수
            
        Returns:
            유망 섹터 목록 및 분석 내용이 포함된 딕셔너리
        """
        logger.info(f"{market} 시장에 대한 유망 산업 섹터 선정 시작")
        
        # 현재 날짜/시간 정보 가져오기
        now = get_current_time()
        current_date = get_current_time_str("%Y년 %m월 %d일")
        
        # 시장에 따라 다른 프롬프트 사용
        market_info = {
            "KR": {
                "name": "한국",
                "sectors_example": "반도체, 2차전지, 바이오, 인공지능, 로봇, 친환경 에너지"
            },
            "US": {
                "name": "미국",
                "sectors_example": "Technology, Healthcare, AI, Clean Energy, Cybersecurity"
            }
        }.get(market, {})
        
        if not market_info:
            logger.error(f"지원하지 않는 시장 코드: {market}")
            return {"error": "지원하지 않는 시장 코드입니다."}
        
        # GPT 프롬프트 구성
        prompt = f"""당신은 최고의 투자 전문가입니다. 오늘 날짜는 {current_date}입니다.
현재 {market_info['name']} 경제 상황과 글로벌 트렌드를 종합적으로 분석하여,
향후 1-2년간 성장 가능성이 가장 높은 {market_info['name']} 산업 섹터 {sectors_count}개를 선정해주세요.

예시로 {market_info['sectors_example']} 등의 섹터가 있습니다.

각 섹터에 대해 다음 정보를 포함하여 JSON 형식으로 응답해주세요:
1. 섹터 이름(name)
2. 성장 잠재력 점수(growth_potential) - 1(낮음)부터 10(매우 높음)
3. 핵심 성장 동력(key_drivers) - 이 섹터가 성장하는 주요 원인들 (최소 3개)
4. 주요 위험 요소(risk_factors) - 이 섹터 성장을 저해할 수 있는 요소들 (최소 2개)
5. 대표 기업들(leading_companies) - 이 섹터의 대표적인 {market_info['name']} 기업들 (최소 3개)
6. 중장기 전망(outlook) - 향후 1-2년 전망을 간결하게 2-3문장으로

마지막으로 전체 {market_info['name']} 경제에 대한 간략한 전망과 선정된 섹터들이 향후 경제에서 어떤 역할을 할지 설명해주세요.

응답은 다음과 같은 JSON 형식으로 제공해주세요:
{{
  "economic_analysis": "현재 {market_info['name']} 경제 상황 분석...",
  "promising_sectors": [
    {{
      "name": "섹터명",
      "growth_potential": 8,
      "key_drivers": ["성장 동력 1", "성장 동력 2", "성장 동력 3"],
      "risk_factors": ["위험 요소 1", "위험 요소 2"],
      "leading_companies": ["기업명 1", "기업명 2", "기업명 3"],
      "outlook": "이 섹터의 중장기 전망 설명..."
    }},
    ...
  ],
  "overall_outlook": "전체 경제 전망 및 선정된 섹터들의 중요성"
}}"""

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 최고의 투자 전문가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                return {"error": f"API 호출 실패: {response.status_code}", "detail": response.text}
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            sector_analysis = json.loads(content)
            logger.info(f"{market} 시장 유망 섹터 선정 완료: {len(sector_analysis.get('promising_sectors', []))}개")
            
            return sector_analysis
            
        except Exception as e:
            logger.error(f"유망 섹터 선정 중 오류 발생: {e}")
            return {"error": f"유망 섹터 선정 중 오류 발생: {str(e)}"}
            
    def recommend_sector_stocks(self, sector_name: str, market: str = "KR", count: int = 3) -> Dict[str, Any]:
        """
        특정 산업 섹터 내에서 추천 종목 선정
        
        Args:
            sector_name: 산업 섹터 이름
            market: 시장 코드 ("KR": 한국, "US": 미국)
            count: 추천할 종목 수
            
        Returns:
            해당 섹터 내 추천 종목 목록
        """
        logger.info(f"{market} 시장의 {sector_name} 섹터 내 종목 추천 시작")
        
        # 현재 날짜 정보
        current_date = get_current_time_str("%Y년 %m월 %d일")
        
        # 시장 정보
        market_info = {
            "KR": {
                "name": "한국",
                "currency": "원",
                "symbols_example": "005930(삼성전자), 000660(SK하이닉스)"
            },
            "US": {
                "name": "미국",
                "currency": "달러",
                "symbols_example": "AAPL(Apple), MSFT(Microsoft)"
            }
        }.get(market, {})
        
        if not market_info:
            logger.error(f"지원하지 않는 시장 코드: {market}")
            return {"error": "지원하지 않는 시장 코드입니다."}
        
        # GPT 프롬프트 구성
        prompt = f"""당신은 최고의 투자 전문가입니다. 오늘 날짜는 {current_date}입니다.
{market_info['name']}의 {sector_name} 산업 섹터에서 향후 성장 가능성이 높은 주식 {count}개를 추천해주세요.

각 종목에 대해 다음 정보를 포함하여 JSON 형식으로 응답해주세요:
1. 종목코드(symbol)
2. 종목명(name)
3. 해당 섹터 내 포지션/역할(position)
4. 추천 이유(reason) - 간결하게 2-3문장
5. 주요 경쟁 우위 요소(competitive_advantages) - 최소 2가지
6. 향후 12개월 목표가(target_price)
7. 투자 위험도(risk_level) - 1(매우 낮음)부터 10(매우 높음)까지의 점수

{market_info['name']} 시장의 종목코드는 {market_info['symbols_example']} 형식으로 정확히 표기해주세요.

응답은 다음과 같은 JSON 형식으로 제공해주세요:
{{
  "sector_analysis": "{sector_name} 섹터 현황 및 전망...",
  "recommended_stocks": [
    {{
      "symbol": "종목코드",
      "name": "종목명",
      "position": "섹터 내 포지션/역할",
      "reason": "추천 이유",
      "competitive_advantages": ["경쟁 우위 1", "경쟁 우위 2"],
      "target_price": 50000,
      "risk_level": 7
    }},
    ...
  ]
}}"""

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 최고의 투자 전문가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                return {"error": f"API 호출 실패: {response.status_code}", "detail": response.text}
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            sector_stocks = json.loads(content)
            logger.info(f"{sector_name} 섹터 내 종목 추천 완료: {len(sector_stocks.get('recommended_stocks', []))}개")
            
            return sector_stocks
            
        except Exception as e:
            logger.error(f"{sector_name} 섹터 내 종목 추천 중 오류 발생: {e}")
            return {"error": f"종목 추천 중 오류 발생: {str(e)}"}
    
    def update_config_stocks(self, kr_recommendations: Dict[str, Any], us_recommendations: Dict[str, Any]) -> bool:
        """
        추천된 종목 목록을 config 파일에 업데이트
        
        Args:
            kr_recommendations: 국내 추천 종목 목록
            us_recommendations: 미국 추천 종목 목록
            
        Returns:
            업데이트 성공 여부
        """
        try:
            logger.info("config에 추천 종목 업데이트 시작")
            
            # 한국 종목 업데이트
            if "recommended_stocks" in kr_recommendations and kr_recommendations["recommended_stocks"]:
                kr_stock_info = []
                for stock in kr_recommendations["recommended_stocks"]:
                    if "symbol" in stock and stock["symbol"]:
                        # 종목코드와 종목명 추출
                        symbol = stock["symbol"]
                        name = stock.get("name", "")
                        
                        # 종목코드에서 숫자만 추출 (예: "005930(삼성전자)" -> "005930")
                        if '(' in symbol:
                            symbol = symbol.split('(')[0]
                        
                        # 종목코드와 종목명을 딕셔너리로 저장
                        kr_stock_info.append({"code": symbol, "name": name})
                
                if kr_stock_info:
                    # 기존 설정에 없으면 빈 리스트로 초기화
                    if not hasattr(self.config, 'KR_STOCKS'):
                        self.config.KR_STOCKS = []
                    
                    # 중복 제거를 위해 종목 코드만 먼저 추출
                    kr_codes = [stock["code"] for stock in kr_stock_info]
                    kr_codes = list(set(kr_codes))  # 중복 제거
                    
                    # 종목 코드 리스트 업데이트 (기존 호환성 유지)
                    self.config.KR_STOCKS = kr_codes
                    
                    # 종목 코드와 이름 정보를 담은 딕셔너리 리스트 생성
                    self.config.KR_STOCK_INFO = []
                    for stock in kr_stock_info:
                        if stock["code"] in kr_codes:  # 중복 제거된 코드에 있는 경우만
                            self.config.KR_STOCK_INFO.append({
                                "code": stock["code"],
                                "name": stock["name"]
                            })
                            # 중복 코드 제거 (첫 번째 항목만 유지)
                            kr_codes.remove(stock["code"])
                    
                    logger.info(f"한국 추천 종목 {len(self.config.KR_STOCK_INFO)}개 업데이트됨")
            
            # 미국 종목 업데이트
            if "recommended_stocks" in us_recommendations and us_recommendations["recommended_stocks"]:
                us_stock_info = []
                for stock in us_recommendations["recommended_stocks"]:
                    if "symbol" in stock and stock["symbol"]:
                        # 종목코드와 종목명 추출
                        symbol = stock["symbol"]
                        name = stock.get("name", "")
                        
                        # 종목코드에서 심볼만 추출 (예: "AAPL(Apple)" -> "AAPL")
                        if '(' in symbol:
                            symbol = symbol.split('(')[0]
                        
                        # 종목코드와 종목명을 딕셔너리로 저장
                        us_stock_info.append({"code": symbol, "name": name})
                
                if us_stock_info:
                    # 기존 설정에 없으면 빈 리스트로 초기화
                    if not hasattr(self.config, 'US_STOCKS'):
                        self.config.US_STOCKS = []
                    
                    # 중복 제거를 위해 종목 코드만 먼저 추출
                    us_codes = [stock["code"] for stock in us_stock_info]
                    us_codes = list(set(us_codes))  # 중복 제거
                    
                    # 종목 코드 리스트 업데이트 (기존 호환성 유지)
                    self.config.US_STOCKS = us_codes
                    
                    # 종목 코드와 이름 정보를 담은 딕셔너리 리스트 생성
                    self.config.US_STOCK_INFO = []
                    for stock in us_stock_info:
                        if stock["code"] in us_codes:  # 중복 제거된 코드에 있는 경우만
                            self.config.US_STOCK_INFO.append({
                                "code": stock["code"],
                                "name": stock["name"]
                            })
                            # 중복 코드 제거 (첫 번째 항목만 유지)
                            us_codes.remove(stock["code"])
                    
                    logger.info(f"미국 추천 종목 {len(self.config.US_STOCK_INFO)}개 업데이트됨")
            
            # config 파일 경로 설정
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.py')
            
            # 파일 내용 읽기
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file:
                    config_content = file.read()
                
                # KR_STOCKS 업데이트 (기존 호환성 유지)
                if hasattr(self.config, 'KR_STOCKS'):
                    kr_stocks_str = repr(self.config.KR_STOCKS)
                    
                    if "KR_STOCKS" in config_content:
                        # 정규식 패턴 대신 간단한 문자열 치환 사용
                        start_idx = config_content.find("KR_STOCKS")
                        if start_idx != -1:
                            line_end = config_content.find("\n", start_idx)
                            config_content = (
                                config_content[:start_idx] + 
                                f"KR_STOCKS = {kr_stocks_str}" + 
                                config_content[line_end:]
                            )
                    else:
                        # 없으면 파일 끝에 추가
                        config_content += f"\n\n# GPT에 의해 추천된 한국 종목 목록\nKR_STOCKS = {kr_stocks_str}\n"
                
                # KR_STOCK_INFO 추가 (종목 코드와 이름 정보)
                if hasattr(self.config, 'KR_STOCK_INFO'):
                    kr_stock_info_str = repr(self.config.KR_STOCK_INFO)
                    
                    if "KR_STOCK_INFO" in config_content:
                        # 정규식 패턴 대신 간단한 문자열 치환 사용
                        start_idx = config_content.find("KR_STOCK_INFO")
                        if start_idx != -1:
                            line_end = config_content.find("\n", start_idx)
                            config_content = (
                                config_content[:start_idx] + 
                                f"KR_STOCK_INFO = {kr_stock_info_str}" + 
                                config_content[line_end:]
                            )
                    else:
                        # 없으면 파일 끝에 추가
                        config_content += f"\n\n# GPT에 의해 추천된 한국 종목 정보 (코드와 이름)\nKR_STOCK_INFO = {kr_stock_info_str}\n"
                
                # US_STOCKS 업데이트 (기존 호환성 유지)
                if hasattr(self.config, 'US_STOCKS'):
                    us_stocks_str = repr(self.config.US_STOCKS)
                    
                    if "US_STOCKS" in config_content:
                        # 정규식 패턴 대신 간단한 문자열 치환 사용
                        start_idx = config_content.find("US_STOCKS")
                        if start_idx != -1:
                            line_end = config_content.find("\n", start_idx)
                            config_content = (
                                config_content[:start_idx] + 
                                f"US_STOCKS = {us_stocks_str}" + 
                                config_content[line_end:]
                            )
                    else:
                        # 없으면 파일 끝에 추가
                        config_content += f"\n\n# GPT에 의해 추천된 미국 종목 목록\nUS_STOCKS = {us_stocks_str}\n"
                
                # US_STOCK_INFO 추가 (종목 코드와 이름 정보)
                if hasattr(self.config, 'US_STOCK_INFO'):
                    us_stock_info_str = repr(self.config.US_STOCK_INFO)
                    
                    if "US_STOCK_INFO" in config_content:
                        # 정규식 패턴 대신 간단한 문자열 치환 사용
                        start_idx = config_content.find("US_STOCK_INFO")
                        if start_idx != -1:
                            line_end = config_content.find("\n", start_idx)
                            config_content = (
                                config_content[:start_idx] + 
                                f"US_STOCK_INFO = {us_stock_info_str}" + 
                                config_content[line_end:]
                            )
                    else:
                        # 없으면 파일 끝에 추가
                        config_content += f"\n\n# GPT에 의해 추천된 미국 종목 정보 (코드와 이름)\nUS_STOCK_INFO = {us_stock_info_str}\n"
                
                # 파일 쓰기
                with open(config_path, 'w', encoding='utf-8') as file:
                    file.write(config_content)
                
                logger.info(f"설정 파일({config_path})에 추천 종목이 성공적으로 업데이트되었습니다.")
                return True
            else:
                logger.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
                return False
                
        except Exception as e:
            logger.error(f"설정 업데이트 중 오류 발생: {e}")
            return False
    
    def optimize_technical_indicators(self, market: str = "KR") -> Dict[str, Any]:
        """
        GPT를 사용하여 기술적 지표 설정 최적화
        
        Args:
            market: 시장 코드 ("KR": 한국, "US": 미국)
            
        Returns:
            최적화된 기술적 지표 설정값이 포함된 딕셔너리
        """
        logger.info(f"{market} 시장에 대한 기술적 지표 최적화 시작")
        
        # API 키 유효성 확인
        if not self.is_api_key_valid():
            logger.warning("유효하지 않은 OpenAI API 키로 인해 기본 기술적 지표 설정을 사용합니다.")
            return self._get_default_technical_indicators()
        
        # 현재 날짜/시간 정보 가져오기
        now = get_current_time()
        current_date = get_current_time_str("%Y년 %m월 %d일")
        
        # 시장에 따라 다른 프롬프트 사용
        market_info = {
            "KR": {
                "name": "한국",
                "index": "KOSPI",
                "currency": "원"
            },
            "US": {
                "name": "미국",
                "index": "S&P 500",
                "currency": "달러"
            }
        }.get(market, {})
        
        if not market_info:
            logger.error(f"지원하지 않는 시장 코드: {market}")
            return {"error": "지원하지 않는 시장 코드입니다."}
            
        # 시장 민감도 설정 가져오기
        market_sensitivity = getattr(self.config, 'GPT_TECHNICAL_MARKET_SENSITIVITY', 'balanced')
        
        sensitivity_description = {
            "market_sensitive": "시장 변화에 민감하게 반응하는 적극적인 매매 전략",
            "balanced": "안정적인 성과를 내면서도 시장 기회를 활용하는 균형 잡힌 매매 전략",
            "conservative": "리스크를 최소화하고 안정적인 수익을 추구하는 보수적인 매매 전략"
        }.get(market_sensitivity, "균형 잡힌 매매 전략")
        
        # 현재 사용 중인 기술적 지표 설정 가져오기
        current_settings = {
            "RSI_PERIOD": getattr(self.config, 'RSI_PERIOD', 14),
            "RSI_OVERSOLD": getattr(self.config, 'RSI_OVERSOLD', 30),
            "RSI_OVERBOUGHT": getattr(self.config, 'RSI_OVERBOUGHT', 70),
            "MACD_FAST": getattr(self.config, 'MACD_FAST', 12),
            "MACD_SLOW": getattr(self.config, 'MACD_SLOW', 26),
            "MACD_SIGNAL": getattr(self.config, 'MACD_SIGNAL', 9),
            "BOLLINGER_PERIOD": getattr(self.config, 'BOLLINGER_PERIOD', 20),
            "BOLLINGER_STD": getattr(self.config, 'BOLLINGER_STD', 2.0),
            "MA_SHORT": getattr(self.config, 'MA_SHORT', 5),
            "MA_MEDIUM": getattr(self.config, 'MA_MEDIUM', 20),
            "MA_LONG": getattr(self.config, 'MA_LONG', 60)
        }
        
        # GPT 프롬프트 구성
        prompt = f"""당신은 주식 기술적 분석 전문가입니다. 오늘 날짜는 {current_date}입니다.
현재 {market_info['name']} 주식 시장 상황과 글로벌 경제 환경을 고려하여, {sensitivity_description}에 최적화된 기술적 지표 설정값을 제안해주세요.

현재 사용 중인 기술적 지표 설정은 다음과 같습니다:
- RSI 기간: {current_settings['RSI_PERIOD']} (일반적으로 9-25 사이)
- RSI 과매도 기준: {current_settings['RSI_OVERSOLD']} (일반적으로 20-40 사이)
- RSI 과매수 기준: {current_settings['RSI_OVERBOUGHT']} (일반적으로 60-80 사이)
- MACD 빠른 이동평균: {current_settings['MACD_FAST']} (일반적으로 8-13 사이)
- MACD 느린 이동평균: {current_settings['MACD_SLOW']} (일반적으로 21-30 사이)
- MACD 시그널: {current_settings['MACD_SIGNAL']} (일반적으로 5-12 사이)
- 볼린저밴드 기간: {current_settings['BOLLINGER_PERIOD']} (일반적으로 10-30 사이)
- 볼린저밴드 표준편차: {current_settings['BOLLINGER_STD']} (일반적으로 1.5-3.0 사이)
- 단기 이동평균: {current_settings['MA_SHORT']} (일반적으로 3-10 사이)
- 중기 이동평균: {current_settings['MA_MEDIUM']} (일반적으로 15-30 사이)
- 장기 이동평균: {current_settings['MA_LONG']} (일반적으로 50-200 사이)

현재 {market_info['name']} 시장의 특성과 경제 환경을 고려하여, 각 기술적 지표의 최적 설정값을 제안해주세요.
또한 각 설정값을 변경한 이유와 그에 따른 매매 전략에 대한 조언도 제공해주세요.

응답은 다음과 같은 JSON 형식으로 제공해주세요:
{{
  "market_analysis": "현재 {market_info['name']} 시장 상황 분석...",
  "recommended_settings": {{
    "RSI_PERIOD": 14,
    "RSI_OVERSOLD": 30,
    "RSI_OVERBOUGHT": 70,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
    "BOLLINGER_PERIOD": 20,
    "BOLLINGER_STD": 2.0,
    "MA_SHORT": 5,
    "MA_MEDIUM": 20,
    "MA_LONG": 60
  }},
  "explanation": {{
    "RSI": "RSI 설정값 변경 이유 설명...",
    "MACD": "MACD 설정값 변경 이유 설명...",
    "BOLLINGER": "볼린저밴드 설정값 변경 이유 설명...",
    "MA": "이동평균 설정값 변경 이유 설명..."
  }},
  "trading_strategy": "제안된 설정값을 사용할 때의 매매 전략 조언..."
}}"""

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 주식 기술적 분석 전문가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=30  # 타임아웃 설정
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                # API 호출 실패 시 기본 설정값 반환
                return self._get_default_technical_indicators()
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            technical_settings = json.loads(content)
            logger.info("기술적 지표 설정 최적화 완료")
            
            # 최적화 결과 캐싱
            cache_file = os.path.join(self.cache_dir, f'{market.lower()}_technical_indicators.json')
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(technical_settings, f, ensure_ascii=False, indent=2)
                logger.info(f"최적화된 기술적 지표 설정이 캐시 파일({cache_file})에 저장되었습니다.")
            except Exception as e:
                logger.error(f"기술적 지표 설정 캐싱 중 오류 발생: {e}")
            
            return technical_settings
            
        except Exception as e:
            logger.error(f"기술적 지표 최적화 중 오류 발생: {e}")
            # 오류 발생 시 기본 설정값 반환
            return self._get_default_technical_indicators()
    
    def _get_default_technical_indicators(self) -> Dict[str, Any]:
        """기본 기술적 지표 설정을 반환합니다."""
        return {
            "market_analysis": "API 호출 실패로 인해 기본 설정을 사용합니다.",
            "recommended_settings": {
                "RSI_PERIOD": getattr(self.config, 'RSI_PERIOD', 14),
                "RSI_OVERSOLD": getattr(self.config, 'RSI_OVERSOLD', 30),
                "RSI_OVERBOUGHT": getattr(self.config, 'RSI_OVERBOUGHT', 70),
                "MACD_FAST": getattr(self.config, 'MACD_FAST', 12),
                "MACD_SLOW": getattr(self.config, 'MACD_SLOW', 26),
                "MACD_SIGNAL": getattr(self.config, 'MACD_SIGNAL', 9),
                "BOLLINGER_PERIOD": getattr(self.config, 'BOLLINGER_PERIOD', 20),
                "BOLLINGER_STD": getattr(self.config, 'BOLLINGER_STD', 2.0),
                "MA_SHORT": getattr(self.config, 'MA_SHORT', 5),
                "MA_MEDIUM": getattr(self.config, 'MA_MEDIUM', 20),
                "MA_LONG": getattr(self.config, 'MA_LONG', 60)
            },
            "explanation": {
                "default": "기본 설정값을 사용합니다."
            },
            "trading_strategy": "기본 설정을 사용한 표준 매매 전략을 적용합니다."
        }
    
    def update_config_technical_indicators(self, technical_settings: Dict[str, Any]) -> bool:
        """
        최적화된 기술적 지표 설정을 config 파일에 업데이트
        
        Args:
            technical_settings: 최적화된 기술적 지표 설정
            
        Returns:
            업데이트 성공 여부
        """
        try:
            logger.info("config에 기술적 지표 설정 업데이트 시작")
            
            if not technical_settings or "recommended_settings" not in technical_settings:
                logger.error("유효하지 않은 기술적 지표 설정 형식")
                return False
                
            settings = technical_settings["recommended_settings"]
            
            # 기술적 지표 설정 업데이트
            for key, value in settings.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.info(f"{key} = {value} 설정 업데이트됨")
            
            # config 파일 경로 설정
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.py')
            
            # 파일 내용 읽기
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file:
                    config_content = file.read()
                
                # 각 설정값 업데이트
                for key, value in settings.items():
                    value_str = str(value)
                    
                    if key in config_content:
                        # 정규식 대신 간단한 문자열 치환 사용
                        start_idx = config_content.find(key + " = ")
                        if start_idx != -1:
                            line_end = config_content.find("\n", start_idx)
                            old_line = config_content[start_idx:line_end]
                            new_line = f"{key} = {value_str}"
                            config_content = config_content.replace(old_line, new_line)
                    else:
                        # 없으면 기술적 지표 섹션에 추가
                        if "# 기술적 지표 계산을 위한 설정" in config_content:
                            insert_idx = config_content.find("# 기술적 지표 계산을 위한 설정")
                            line_end = config_content.find("\n", insert_idx)
                            next_line = config_content.find("\n", line_end + 1)
                            
                            # 코멘트 아래 라인에 삽입
                            config_content = (
                                config_content[:next_line + 1] + 
                                f"{key} = {value_str}  # GPT에 의해 최적화된 설정\n" + 
                                config_content[next_line + 1:]
                            )
                        else:
                            # 기술적 지표 섹션이 없으면 파일 끝에 추가
                            config_content += f"\n\n# GPT에 의해 최적화된 기술적 지표 설정\n{key} = {value_str}\n"
                
                # 파일 쓰기
                with open(config_path, 'w', encoding='utf-8') as file:
                    file.write(config_content)
                
                logger.info(f"설정 파일({config_path})에 기술적 지표 설정이 성공적으로 업데이트되었습니다.")
                return True
            else:
                logger.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
                return False
                
        except Exception as e:
            logger.error(f"기술적 지표 설정 업데이트 중 오류 발생: {e}")
            return False
    
    def analyze_for_day_trading(self, symbols: List[str]) -> Dict[str, Any]:
        """
        단타 매매를 위한 종목 분석 수행
        
        Args:
            symbols: 분석할 종목코드 목록
            
        Returns:
            dict: 각 종목에 대한 분석 결과
        """
        logger.info(f"단타 매매를 위한 종목 분석 시작: {symbols}")
        
        # API 키 유효성 확인
        if not self.is_api_key_valid():
            logger.warning("유효하지 않은 OpenAI API 키로 인해 분석을 수행할 수 없습니다.")
            return {"error": "유효하지 않은 API 키"}
        
        # 현재 날짜/시간 정보 가져오기
        current_date = get_current_time_str("%Y년 %m월 %d일")
        
        # 종목 코드 문자열 생성
        symbols_str = ", ".join([f"{s}" for s in symbols])
        
        # JSON 형식 예제 분리
        json_example = '''
{
  "market_condition": "현재 시장 상황 분석",
  "stock_analysis": {
    "종목코드1": {
      "price_trend": "상승",
      "momentum_score": 8,
      "day_trading_score": 7,
      "trading_strategy": {
        "entry_point": "매수 포인트 설명",
        "exit_point": "매도 포인트 설명",
        "key_signals": ["주요 시그널 1", "주요 시그널 2"]
      },
      "price_targets": {
        "target": 52000,
        "stop_loss": 49500
      },
      "summary": "이 종목에 대한 간략한 요약"
    },
    "종목코드2": {
      "...":"..."
    }
  },
  "day_trading_tips": "오늘의 단타 매매 전략에 대한 조언"
}
'''
        
        # GPT 프롬프트 구성 (f-string 중첩 방지)
        prompt = f"당신은 단타 매매 전문 투자 분석가입니다. 오늘 날짜는 {current_date}입니다.\n"
        prompt += f"다음 한국 종목들에 대한 단타 매매 관점에서의 분석을 해주세요: {symbols_str}\n\n"
        prompt += """각 종목에 대해 다음 정보를 포함하여 JSON 형식으로 응답해주세요:
1. 현재 가격 동향(price_trend) - "상승", "하락", "횡보" 중 하나
2. 단기 모멘텀 점수(momentum_score) - 1(매우 약함)부터 10(매우 강함)까지의 점수
3. 단타 매매 적합성 점수(day_trading_score) - 1(매우 낮음)부터 10(매우 높음)까지의 점수
4. 오늘의 매매 전략(trading_strategy) - 매수/매도 시점, 익절 및 손절 전략 등
5. 가격 타겟(price_targets) - 목표가 및 손절가

응답은 다음과 같은 JSON 형식으로 제공해주세요:"""
        prompt += "\n" + json_example

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 단타 매매 전문 투자 분석가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=30  # 타임아웃 설정
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                return {"error": f"API 호출 실패: {response.status_code}", "detail": response.text}
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            analysis = json.loads(content)
            logger.info(f"단타 매매 분석 완료: {len(analysis.get('stock_analysis', {}))}개 종목")
            
            return analysis
            
        except Exception as e:
            logger.error(f"단타 매매 분석 중 오류 발생: {e}")
            return {"error": f"분석 오류: {str(e)}"}

    def analyze_sudden_price_surge(self, limit=10) -> Dict[str, Any]:
        """
        급등주 감지 및 분석
        
        Args:
            limit: 분석할 급등주 최대 개수
            
        Returns:
            dict: 급등주 분석 결과
        """
        logger.info(f"급등주 감지 및 분석 시작 (최대 {limit}개)")
        
        # API 키 유효성 확인
        if not self.is_api_key_valid():
            logger.warning("유효하지 않은 OpenAI API 키로 인해 분석을 수행할 수 없습니다.")
            return {"error": "유효하지 않은 API 키"}
        
        # 현재 날짜/시간 정보 가져오기
        current_date = get_current_time_str("%Y년 %m월 %d일")
        
        # JSON 형식 예시를 완전히 분리
        json_example = '''
{
  "market_trend": "현재 시장 급등 트렌드 분석",
  "surge_stocks": [
    {
      "symbol": "종목코드",
      "name": "종목명",
      "expected_surge_rate": 8.5,
      "surge_reason": ["사유1", "사유2", "사유3"],
      "day_trading_score": 8,
      "trading_strategy": {
        "entry_point": "매수 전략",
        "target_price": 55000,
        "stop_loss": 51000,
        "exit_strategy": "매도 전략"
      },
      "momentum_sustainability": "중간",
      "trading_signals": ["매수신호1", "매수신호2"],
      "risk_factors": ["위험요소1", "위험요소2"]
    }
  ],
  "day_trading_advice": "오늘의 급등주 단타 매매 조언"
}
'''
        
        # 급등주 감지 기준 및 설명 (f-string 없이)
        criteria_text = """급등주 감지 기준:
1. 전일 대비 5% 이상 상승하는 종목
2. 거래량이 평소보다 2배 이상 급증한 종목
3. 특별한 뉴스나 이벤트가 있는 종목

각 급등주에 대해 다음 정보를 포함하여 JSON 형식으로 응답해주세요:
1. 종목코드(symbol)와 종목명(name)
2. 예상 상승률(expected_surge_rate) - 퍼센트(%)
3. 급등 원인(surge_reason) - 최대 3가지
4. 단타 매매 적합성 점수(day_trading_score) - 1(매우 낮음)부터 10(매우 높음)까지의 점수
5. 매매 전략(trading_strategy) - 진입 포인트, 목표가, 손절가 포함
6. 모멘텀 지속성(momentum_sustainability) - "매우 짧음", "짧음", "중간", "길음" 중 하나"""

        # GPT 프롬프트 구성 (f-string 최소화)
        prompt = f"당신은 한국 주식 시장의 급등주 분석 전문가입니다. 오늘 날짜는 {current_date}입니다.\n"
        prompt += "현재 한국 주식 시장에서 급등하는 종목을 찾고, 단타 매매 관점에서 분석해주세요.\n\n"
        prompt += criteria_text + "\n\n"
        prompt += f"금일 가장 매력적인 급등주 {limit}개에 대해 분석해주세요.\n\n"
        prompt += "응답은 다음과 같은 JSON 형식으로 제공해주세요:\n"
        prompt += json_example

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 한국 주식 시장의 급등주 분석 전문가입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=30  # 타임아웃 설정
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                return {"error": f"API 호출 실패: {response.status_code}", "detail": response.text}
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            surge_analysis = json.loads(content)
            logger.info(f"급등주 분석 완료: {len(surge_analysis.get('surge_stocks', []))}개 종목")
            
            # 결과 캐싱
            cache_file = os.path.join(self.cache_dir, 'surge_stocks_analysis.json')
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(surge_analysis, f, ensure_ascii=False, indent=2)
                logger.info(f"급등주 분석 결과가 캐시 파일({cache_file})에 저장되었습니다.")
            except Exception as e:
                logger.warning(f"급등주 분석 결과 캐싱 중 오류 발생: {e}")
            
            return surge_analysis
            
        except Exception as e:
            logger.error(f"급등주 분석 중 오류 발생: {e}")
            return {"error": f"분석 오류: {str(e)}"}

    def get_intraday_trading_signals(self, symbol: str) -> Dict[str, Any]:
        """
        특정 종목에 대한 장중 실시간 매매 시그널 생성
        
        Args:
            symbol: 종목 코드
            
        Returns:
            dict: 매매 시그널 정보
        """
        logger.info(f"{symbol} 종목에 대한 장중 매매 시그널 생성 시작")
        
        # API 키 유효성 확인
        if not self.is_api_key_valid():
            logger.warning("유효하지 않은 OpenAI API 키로 인해 시그널을 생성할 수 없습니다.")
            return {"error": "유효하지 않은 API 키"}
        
        # 현재 날짜/시간 정보 가져오기
        current_date = get_current_time_str("%Y년 %m월 %d일")
        current_time = get_current_time_str("%H:%M")
        
        # JSON 응답 예시 분리
        json_example = '''
{
  "symbol": "SYMBOL",
  "current_signal": "매수",
  "signal_strength": 8,
  "signal_type": "reversal", 
  "timeframe": "단타(5분봉)",
  "price_targets": {
    "entry_min": 50000,
    "entry_max": 51000,
    "target": 54000,
    "stop_loss": 49000
  },
  "exit_strategy": {
    "price_based": "목표가 도달 시 또는 손절가 도달 시",
    "time_based": "15:00까지 청산"
  },
  "momentum_indicators": {
    "rsi": "과매도 상태에서 반등",
    "macd": "골든크로스 형성 중",
    "volume": "평균보다 1.5배 증가"
  },
  "key_levels": {
    "support": 49500,
    "resistance": 53000
  },
  "special_notes": "오후장 추가 상승 가능성 있음",
  "confidence_score": 75
}
'''
        
        # GPT 프롬프트 구성 (f-string 중첩 방지)
        prompt = f"당신은 단타 매매 전문 트레이더입니다. 오늘 날짜는 {current_date}, 현재 시간은 {current_time}입니다.\n"
        prompt += f"현재 한국 주식시장에서 거래되는 종목 {symbol}에 대한 장중 실시간 매매 시그널을 생성해주세요.\n\n"
        prompt += """매매 시그널은 다음과 같은 정보를 포함해야 합니다:
1. 현재 거래 신호(current_signal) - "강력 매수", "매수", "중립", "매도", "강력 매도" 중 하나
2. 신호 강도(signal_strength) - 1(매우 약함)부터 10(매우 강함)까지의 점수
3. 시그널 발생 타임프레임(timeframe) - "초단타(1분봉)", "단타(5분봉)", "스윙(30분-1시간봉)" 중 하나
4. 목표가(target_price)와 손절가(stop_loss)
5. 청산 시점(exit_point) - "가격 기준", "시간 기준" 등 청산 조건
6. 진입 가격대(entry_price_range) - 매수/매도 진입 가격대
7. 해당 종목 관련 특이사항(특별히 주의해야 할 이벤트나 뉴스)

응답은 다음과 같은 JSON 형식으로 제공해주세요:"""
        prompt += "\n" + json_example.replace("SYMBOL", symbol)

        try:
            # OpenAI API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "당신은 단타 매매 전문 트레이더입니다. 항상 JSON 형식으로 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1500,
                "temperature": 0.5,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=data,
                timeout=20  # 타임아웃 설정
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API 호출 실패: {response.status_code} {response.text}")
                return {"error": f"API 호출 실패: {response.status_code}", "detail": response.text}
                
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # JSON 파싱
            trading_signal = json.loads(content)
            logger.info(f"{symbol} 종목 매매 시그널 생성 완료: {trading_signal.get('current_signal')}")
            
            return trading_signal
            
        except Exception as e:
            logger.error(f"매매 시그널 생성 중 오류 발생: {e}")
            return {"error": f"시그널 생성 오류: {str(e)}"}