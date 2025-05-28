"""
하이브리드 AI 분석 전략 - Gemini와 GPT 모델을 조합하여 사용하는 전략 클래스
"""
import logging
from enum import Enum
import json

# 로깅 설정
logger = logging.getLogger('HybridAIStrategy')

class AIModelType(Enum):
    """AI 모델 타입 열거형"""
    GPT = "gpt"
    GEMINI = "gemini"

class AnalysisType(Enum):
    """분석 유형 열거형"""
    GENERAL = "general"           # 일반적인 주식 분석
    RISK = "risk"                 # 위험 분석
    TREND = "trend"               # 추세 분석
    RECOMMENDATION = "recommendation"  # 추천/시나리오 분석
    TRADING_SIGNAL = "trading_signal" # 매매 신호 분석
    DAILY_REPORT = "daily_report"     # 일일 종합 리포트

class HybridAnalysisStrategy:
    """
    Gemini와 GPT 모델을 조합하여 사용하는 하이브리드 AI 분석 전략 클래스
    """
    
    def __init__(self, gpt_analyzer, gemini_analyzer, config):
        """
        초기화 함수
        
        Args:
            gpt_analyzer: ChatGPT 분석기 인스턴스
            gemini_analyzer: Gemini 분석기 인스턴스
            config: 설정 모듈
        """
        self.gpt_analyzer = gpt_analyzer
        self.gemini_analyzer = gemini_analyzer
        self.config = config
        
        # 분석 유형별 기본 모델 설정
        self.default_models = {
            AnalysisType.GENERAL: AIModelType.GPT,             # 일반 분석은 GPT 사용 (Gemini 할당량 문제로 변경)
            AnalysisType.RISK: AIModelType.GPT,               # 위험 분석은 GPT 사용 (정확도 우선)
            AnalysisType.TREND: AIModelType.GPT,              # 추세 분석은 GPT 사용 (Gemini 할당량 문제로 변경)
            AnalysisType.RECOMMENDATION: AIModelType.GPT,     # 추천은 GPT 사용 (정확도 우선)
            AnalysisType.TRADING_SIGNAL: AIModelType.GPT,     # 매매 신호는 GPT 사용 (정확도 우선)
            AnalysisType.DAILY_REPORT: AIModelType.GPT        # 일일 리포트는 GPT 사용 (Gemini 할당량 문제로 변경)
        }
        
        # 카테고리별 모델 결정 우선순위 설정
        self.model_priority_rules = {
            "critical_decisions": AIModelType.GPT,    # 중요한 의사결정은 GPT 우선
            "high_stakes": AIModelType.GPT,           # 높은 리스크의 분석은 GPT 우선
            "routine_analysis": AIModelType.GPT,      # 일상적인 분석은 GPT 우선 (Gemini 할당량 문제로 변경)
            "background_info": AIModelType.GPT        # 배경 정보는 GPT 우선 (Gemini 할당량 문제로 변경)
        }
        
        # API 키 상태 확인
        self.gpt_available = hasattr(self.gpt_analyzer, 'api_key') and self.gpt_analyzer.api_key is not None
        self.gemini_available = hasattr(self.gemini_analyzer, 'api_key') and self.gemini_analyzer.api_key is not None
        
        logger.info(f"하이브리드 AI 전략 초기화 - GPT 사용 가능: {self.gpt_available}, Gemini 사용 가능: {self.gemini_available}")
        
    def select_model(self, analysis_type, importance=None, budget_priority=False):
        """
        분석 유형에 따라 적절한 AI 모델을 선택
        
        Args:
            analysis_type: 분석 유형 (AnalysisType 열거형)
            importance: 중요도 (None, 'low', 'medium', 'high', 'critical')
            budget_priority: 예산 제약 우선 여부 (True/False)
            
        Returns:
            AIModelType: 선택된 AI 모델 타입
        """
        # API 키 상태에 따른 기본 선택
        if not self.gpt_available and not self.gemini_available:
            logger.warning("두 API 모두 사용 불가능합니다.")
            return None
        elif not self.gpt_available:
            logger.info("GPT API 키가 없어 Gemini를 사용합니다.")
            return AIModelType.GEMINI
        elif not self.gemini_available:
            logger.info("Gemini API 키가 없어 GPT를 사용합니다.")
            return AIModelType.GPT
            
        # 문자열로 전달된 경우 열거형으로 변환
        if isinstance(analysis_type, str):
            try:
                analysis_type = AnalysisType(analysis_type)
            except ValueError:
                # 일치하는 값이 없으면 기본값으로 설정
                analysis_type = AnalysisType.GENERAL
                
        # 예산 우선 설정이면 Gemini 사용
        if budget_priority:
            logger.info(f"예산 우선 정책에 따라 {analysis_type.value} 분석에 Gemini 사용")
            return AIModelType.GEMINI
            
        # 중요도에 따른 결정
        if importance == 'critical':
            logger.info(f"중요도 'critical'에 따라 {analysis_type.value} 분석에 GPT 사용")
            return AIModelType.GPT
        elif importance == 'high':
            logger.info(f"중요도 'high'에 따라 {analysis_type.value} 분석에 GPT 사용")
            return AIModelType.GPT
            
        # 기본 설정값 반환
        selected_model = self.default_models.get(analysis_type, AIModelType.GEMINI)
        logger.info(f"{analysis_type.value} 분석에 기본 설정에 따라 {selected_model.value} 사용")
        return selected_model
        
    def analyze_stock(self, df, symbol, analysis_type, additional_info=None, importance=None, budget_priority=False):
        """
        주식 데이터 분석 하이브리드 전략
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            analysis_type: 분석 유형 (문자열 또는 AnalysisType)
            additional_info: 추가 정보 (dict)
            importance: 중요도 (None, 'low', 'medium', 'high', 'critical')
            budget_priority: 예산 제약 우선 여부 (True/False)
            
        Returns:
            dict: 분석 결과
        """
        # 문자열로 전달된 경우 열거형으로 변환 시도
        if isinstance(analysis_type, str):
            try:
                analysis_enum = AnalysisType(analysis_type)
            except ValueError:
                analysis_enum = AnalysisType.GENERAL
        else:
            analysis_enum = analysis_type
            
        # 적절한 모델 선택
        model_type = self.select_model(analysis_enum, importance, budget_priority)
        
        if model_type is None:
            return {"error": "사용 가능한 AI 모델이 없습니다.", "analysis": "API 키 설정을 확인해주세요."}
            
        try:
            # 선택된 모델에 따라 분석 실행
            if model_type == AIModelType.GPT:
                logger.info(f"{symbol} {analysis_enum.value} 분석에 GPT 사용")
                if isinstance(analysis_enum, AnalysisType):
                    analysis_str = analysis_enum.value
                else:
                    analysis_str = str(analysis_enum)
                    
                result = self.gpt_analyzer.analyze_stock(df, symbol, analysis_str, additional_info)
            else:  # GEMINI
                logger.info(f"{symbol} {analysis_enum.value} 분석에 Gemini 사용")
                if isinstance(analysis_enum, AnalysisType):
                    analysis_str = analysis_enum.value
                else:
                    analysis_str = str(analysis_enum)
                    
                result = self.gemini_analyzer.analyze_stock(df, symbol, analysis_str, additional_info)
                
            # 모델 종류 정보 추가
            result['model_used'] = model_type.value
            return result
            
        except Exception as e:
            logger.error(f"하이브리드 분석 중 오류 발생: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "analysis": "분석 중 오류가 발생했습니다.",
                "model_used": model_type.value if model_type else "unknown"
            }
            
    def analyze_signals(self, signal_data, importance=None, budget_priority=False):
        """
        매매 신호 분석 하이브리드 전략 (중요 결정에는 GPT 사용)
        
        Args:
            signal_data: 매매 신호 데이터 (dict)
            importance: 중요도 (None, 'low', 'medium', 'high', 'critical')
            budget_priority: 예산 제약 우선 여부 (True/False)
            
        Returns:
            str: 분석 결과
        """
        # 매매 신호는 기본적으로 중요하므로 GPT를 우선적으로 사용
        default_importance = 'high' if importance is None else importance
        
        # 중요도와 예산 제약을 고려하여 모델 선택
        model_type = self.select_model(AnalysisType.TRADING_SIGNAL, default_importance, budget_priority)
        
        if model_type is None:
            return "사용 가능한 AI 모델이 없습니다. API 키 설정을 확인해주세요."
            
        try:
            # 선택된 모델에 따라 분석 실행
            if model_type == AIModelType.GPT:
                logger.info(f"{signal_data.get('symbol', '알 수 없음')}의 매매 신호를 GPT로 분석")
                analysis = self.gpt_analyzer.analyze_signals(signal_data)
            else:  # GEMINI
                logger.info(f"{signal_data.get('symbol', '알 수 없음')}의 매매 신호를 Gemini로 분석")
                analysis = self.gemini_analyzer.analyze_signals(signal_data)
                
            return analysis
            
        except Exception as e:
            logger.error(f"매매 신호 분석 중 오류 발생: {e}")
            return f"분석 중 오류가 발생했습니다: {str(e)}"
            
    def generate_daily_report(self, stock_data_dict, market="KR", importance=None, budget_priority=False):
        """
        일일 종합 리포트 생성 하이브리드 전략
        
        Args:
            stock_data_dict: {종목코드: DataFrame} 형태의 데이터
            market: 시장 구분 ("KR" 또는 "US")
            importance: 중요도 (None, 'low', 'medium', 'high', 'critical')
            budget_priority: 예산 제약 우선 여부 (True/False)
            
        Returns:
            str: 종합 리포트
        """
        # 종합 리포트는 비용 효율성이 중요하므로 기본적으로 Gemini 사용
        model_type = self.select_model(AnalysisType.DAILY_REPORT, importance, budget_priority)
        
        if model_type is None:
            return "사용 가능한 AI 모델이 없습니다. API 키 설정을 확인해주세요."
            
        try:
            # 선택된 모델에 따라 분석 실행
            if model_type == AIModelType.GPT:
                logger.info(f"{market} 일일 리포트를 GPT로 생성")
                report = self.gpt_analyzer.generate_daily_report(stock_data_dict, market)
            else:  # GEMINI
                logger.info(f"{market} 일일 리포트를 Gemini로 생성")
                report = self.gemini_analyzer.generate_daily_report(stock_data_dict, market)
                
            return report
            
        except Exception as e:
            logger.error(f"일일 리포트 생성 중 오류 발생: {e}")
            return f"일일 리포트 생성 중 오류가 발생했습니다: {str(e)}"
            
    def compare_analyses(self, df, symbol, analysis_type, additional_info=None):
        """
        두 AI 모델의 분석 결과를 비교 (중요 결정에 활용)
        
        Args:
            df: 주가 데이터 (DataFrame)
            symbol: 종목 코드
            analysis_type: 분석 유형
            additional_info: 추가 정보 (dict)
            
        Returns:
            dict: GPT와 Gemini 분석 결과 비교
        """
        if not self.gpt_available or not self.gemini_available:
            logger.warning("두 모델을 모두 사용할 수 없어 비교를 수행할 수 없습니다.")
            return {"error": "비교를 위해서는 두 API 키가 모두 필요합니다."}
            
        try:
            # 두 모델로 분석 수행
            if isinstance(analysis_type, AnalysisType):
                analysis_str = analysis_type.value
            else:
                analysis_str = str(analysis_type)
                
            gpt_result = self.gpt_analyzer.analyze_stock(df, symbol, analysis_str, additional_info)
            gemini_result = self.gemini_analyzer.analyze_stock(df, symbol, analysis_str, additional_info)
            
            comparison = {
                "symbol": symbol,
                "analysis_type": analysis_str,
                "gpt_analysis": gpt_result.get("analysis", "분석 없음"),
                "gemini_analysis": gemini_result.get("analysis", "분석 없음"),
                "models_agree": self._check_agreement(gpt_result.get("analysis", ""), 
                                                   gemini_result.get("analysis", ""))
            }
            
            logger.info(f"{symbol} 분석 비교 완료 - 일치도: {comparison['models_agree']}")
            
            return comparison
            
        except Exception as e:
            logger.error(f"분석 비교 중 오류 발생: {e}")
            return {"error": str(e)}
            
    def _check_agreement(self, gpt_analysis, gemini_analysis):
        """
        두 분석 결과의 일치도 계산 (간단한 구현)
        
        Args:
            gpt_analysis: GPT 분석 결과 문자열
            gemini_analysis: Gemini 분석 결과 문자열
            
        Returns:
            str: 일치도 평가 ("높음", "중간", "낮음")
        """
        # 간단한 키워드 기반 일치도 확인 (실제로는 더 복잡한 NLP 기법 사용 가능)
        positive_keywords = ["상승", "매수", "긍정", "성장", "강세", "매집", "호재"]
        negative_keywords = ["하락", "매도", "부정", "하락", "약세", "매도", "악재"]
        neutral_keywords = ["관망", "홀드", "보합", "중립", "혼조", "횡보"]
        
        # GPT 분석의 키워드 확인
        gpt_positive = sum(1 for word in positive_keywords if word in gpt_analysis)
        gpt_negative = sum(1 for word in negative_keywords if word in gpt_analysis)
        gpt_neutral = sum(1 for word in neutral_keywords if word in gpt_analysis)
        
        # Gemini 분석의 키워드 확인
        gemini_positive = sum(1 for word in positive_keywords if word in gemini_analysis)
        gemini_negative = sum(1 for word in negative_keywords if word in gemini_analysis)
        gemini_neutral = sum(1 for word in neutral_keywords if word in gemini_analysis)
        
        # 방향성 결정
        gpt_direction = "positive" if gpt_positive > gpt_negative else ("negative" if gpt_negative > gpt_positive else "neutral")
        gemini_direction = "positive" if gemini_positive > gemini_negative else ("negative" if gemini_negative > gemini_positive else "neutral")
        
        # 일치도 평가
        if gpt_direction == gemini_direction:
            return "높음"
        elif (gpt_direction == "neutral" or gemini_direction == "neutral"):
            return "중간"
        else:
            return "낮음"