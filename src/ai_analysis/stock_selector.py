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
7. 투자 위험도(risk_level) - 1(매우 낮음)부터 10(매우 높음)

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