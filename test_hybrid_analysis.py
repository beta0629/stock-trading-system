"""
하이브리드 AI 분석 시스템 테스트 스크립트
- GPT와 Gemini를 함께 활용한 주식 분석 시스템 테스트
"""
import os
import sys
import logging
import pandas as pd
import numpy as np
import time
import traceback
import datetime
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("hybrid_analysis_test.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('HybridAnalysisTest')

# 필요한 모듈 임포트
try:
    logger.info("모듈 임포트를 시작합니다.")
    import config
    from src.ai_analysis.chatgpt_analyzer import ChatGPTAnalyzer
    from src.ai_analysis.gemini_analyzer import GeminiAnalyzer
    from src.ai_analysis.hybrid_analysis_strategy import HybridAnalysisStrategy, AnalysisType
    from src.data.stock_data import StockData  # StockDataFetcher를 StockData로 수정
    logger.info("모듈 임포트가 완료되었습니다.")
except ImportError as e:
    logger.error(f"모듈 임포트 중 오류 발생: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

def create_test_dataframe():
    """
    테스트용 주가 데이터 생성
    
    Returns:
        DataFrame: 테스트용 주가 데이터
    """
    # 날짜 인덱스 생성
    dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
    
    # 시작가
    start_price = 50000
    
    # 기본 데이터 생성
    np.random.seed(42)  # 재현 가능성을 위한 시드 설정
    
    # 상승 추세 시뮬레이션
    price_trend = np.linspace(0, 0.3, len(dates))  # 0%에서 30%까지 선형 증가
    daily_changes = np.random.normal(0.001, 0.02, len(dates))  # 평균 0.1%, 표준편차 2%의 일별 변화
    cumulative_changes = np.cumprod(1 + daily_changes + price_trend / len(dates))
    
    # 가격 시리즈 생성
    closes = start_price * cumulative_changes
    opens = closes * np.random.normal(1, 0.01, len(dates))  # 종가 대비 ±1% 내외의 시가
    highs = np.maximum(opens, closes) * np.random.uniform(1.001, 1.03, len(dates))  # 고가는 시가/종가 중 높은 값보다 0.1~3% 높게
    lows = np.minimum(opens, closes) * np.random.uniform(0.97, 0.999, len(dates))   # 저가는 시가/종가 중 낮은 값보다 0.1~3% 낮게
    
    # 거래량 생성 (가격 변화가 클수록 거래량 증가)
    volumes = np.abs(np.diff(np.append([0], closes))) * np.random.uniform(5000, 15000, len(dates))
    volumes = volumes.astype(int)
    
    # DataFrame 생성
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes
    }, index=dates)
    
    # 기술적 지표 추가
    df = add_technical_indicators(df)
    
    return df

def add_technical_indicators(df):
    """
    주가 데이터에 기술적 지표 추가
    
    Args:
        df: 주가 데이터
        
    Returns:
        DataFrame: 기술적 지표가 추가된 데이터
    """
    # 단기/장기 이동평균선
    df['SMA_short'] = df['Close'].rolling(window=5).mean()
    df['SMA_long'] = df['Close'].rolling(window=20).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    return df

def test_hybrid_analysis():
    """
    하이브리드 AI 분석 시스템 테스트
    """
    logger.info("하이브리드 AI 분석 시스템 테스트 시작")
    
    try:
        # 분석 모듈 초기화
        logger.info("분석 모듈 초기화 중...")
        gpt_analyzer = ChatGPTAnalyzer(config)
        gemini_analyzer = GeminiAnalyzer(config)
        
        # API 키 확인
        logger.info("API 키 확인 중...")
        if not os.environ.get('OPENAI_API_KEY'):
            logger.error("OpenAI API 키가 설정되지 않았습니다.")
            return
        if not os.environ.get('GEMINI_API_KEY'):
            logger.error("Gemini API 키가 설정되지 않았습니다.")
            return
        
        logger.info("GPT API 키: 설정됨")
        logger.info("Gemini API 키: 설정됨")
        
        # 하이브리드 분석 전략 초기화
        logger.info("하이브리드 분석 전략 초기화 중...")
        hybrid_strategy = HybridAnalysisStrategy(gpt_analyzer, gemini_analyzer, config)
        
        # 테스트 데이터 생성
        logger.info("테스트 데이터 생성 중...")
        df = create_test_dataframe()
        logger.info(f"테스트 데이터 생성 완료: {len(df)} 행, 컬럼: {list(df.columns)}")
        
        # 샘플 심볼
        symbol = "005930"  # 삼성전자
        
        # 1. 기본 일반 분석 테스트 (Gemini 사용)
        logger.info("1. 일반 분석 테스트 (Gemini 기본)")
        try:
            result = hybrid_strategy.analyze_stock(df, symbol, AnalysisType.GENERAL)
            logger.info(f"일반 분석 결과 - 모델: {result.get('model_used')}")
            logger.info(f"분석 요약: {result.get('analysis')[:150]}...")
        except Exception as e:
            logger.error(f"일반 분석 오류: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(1)  # API 호출 간격 조정
        
        # 2. 위험 분석 테스트 (GPT 사용)
        logger.info("2. 위험 분석 테스트 (GPT 기본)")
        try:
            result = hybrid_strategy.analyze_stock(df, symbol, AnalysisType.RISK)
            logger.info(f"위험 분석 결과 - 모델: {result.get('model_used')}")
            logger.info(f"분석 요약: {result.get('analysis')[:150]}...")
        except Exception as e:
            logger.error(f"위험 분석 오류: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(1)  # API 호출 간격 조정
        
        # 3. 중요도 우선 테스트 (GPT 강제 사용)
        logger.info("3. 중요도 우선 테스트 (GPT 강제)")
        try:
            result = hybrid_strategy.analyze_stock(df, symbol, AnalysisType.GENERAL, importance="critical")
            logger.info(f"중요도 우선 분석 결과 - 모델: {result.get('model_used')}")
            logger.info(f"분석 요약: {result.get('analysis')[:150]}...")
        except Exception as e:
            logger.error(f"중요도 우선 분석 오류: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(1)  # API 호출 간격 조정
        
        # 4. 예산 우선 테스트 (Gemini 강제 사용)
        logger.info("4. 예산 우선 테스트 (Gemini 강제)")
        try:
            result = hybrid_strategy.analyze_stock(df, symbol, AnalysisType.RISK, budget_priority=True)
            logger.info(f"예산 우선 분석 결과 - 모델: {result.get('model_used')}")
            logger.info(f"분석 요약: {result.get('analysis')[:150]}...")
        except Exception as e:
            logger.error(f"예산 우선 분석 오류: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(1)  # API 호출 간격 조정
        
        # 5. 매매 신호 분석 테스트
        logger.info("5. 매매 신호 분석 테스트")
        try:
            signal_data = {
                "symbol": symbol,
                "price": df['Close'].iloc[-1],
                "technical_indicators": {
                    "rsi": df['RSI'].iloc[-1],
                    "macd": df['MACD'].iloc[-1],
                    "macd_signal": df['MACD_signal'].iloc[-1],
                    "sma_short": df['SMA_short'].iloc[-1],
                    "sma_long": df['SMA_long'].iloc[-1]
                },
                "price_changes": {
                    "1d": (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) * 100,
                    "5d": (df['Close'].iloc[-1] / df['Close'].iloc[-6] - 1) * 100,
                    "20d": (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) * 100
                }
            }
            result = hybrid_strategy.analyze_signals(signal_data)
            logger.info(f"매매 신호 분석 결과: {result[:150]}...")
        except Exception as e:
            logger.error(f"매매 신호 분석 오류: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(1)  # API 호출 간격 조정
        
        # 6. 두 AI 모델 비교 테스트
        logger.info("6. 두 AI 모델 비교 테스트")
        try:
            comparison = hybrid_strategy.compare_analyses(df, symbol, AnalysisType.RECOMMENDATION)
            logger.info(f"모델 비교 결과 - 일치도: {comparison.get('models_agree', '알 수 없음')}")
            logger.info(f"GPT 분석: {comparison.get('gpt_analysis', '')[:100]}...")
            logger.info(f"Gemini 분석: {comparison.get('gemini_analysis', '')[:100]}...")
        except Exception as e:
            logger.error(f"모델 비교 테스트 오류: {e}")
            logger.error(traceback.format_exc())
    
    except Exception as e:
        logger.error(f"하이브리드 분석 테스트 중 예상치 못한 오류 발생: {e}")
        logger.error(traceback.format_exc())
    
    logger.info("하이브리드 AI 분석 시스템 테스트 완료")

def test_real_stock_data():
    """
    실제 주식 데이터를 사용한 테스트
    """
    logger.info("실제 주식 데이터 테스트 시작")
    
    try:
        # 데이터 가져오기
        fetcher = StockData()
        symbols = ["005930", "000660", "035420"]  # 삼성전자, SK하이닉스, NAVER
        
        # 분석 모듈 초기화
        gpt_analyzer = ChatGPTAnalyzer(config)
        gemini_analyzer = GeminiAnalyzer(config)
        hybrid_strategy = HybridAnalysisStrategy(gpt_analyzer, gemini_analyzer, config)
        
        for symbol in symbols:
            try:
                # 주가 데이터 가져오기
                df = fetcher.fetch_stock_data(symbol, days=60)
                
                if df is None or df.empty:
                    logger.warning(f"{symbol}: 데이터를 불러올 수 없습니다.")
                    continue
                    
                # 기술적 지표 추가
                df = add_technical_indicators(df)
                logger.info(f"{symbol} 데이터 준비 완료, 최근 종가: {df['Close'].iloc[-1]:.2f}")
                
                # 다양한 분석 유형 테스트
                for analysis_type in [AnalysisType.GENERAL, AnalysisType.RISK, AnalysisType.TREND]:
                    logger.info(f"{symbol} {analysis_type.value} 분석 시작")
                    result = hybrid_strategy.analyze_stock(df, symbol, analysis_type)
                    logger.info(f"분석 완료 - 모델: {result.get('model_used')}")
                    logger.info(f"분석 내용: {result.get('analysis')[:150]}...")
                    time.sleep(1)  # API 호출 간격 조정
                    
            except Exception as e:
                logger.error(f"{symbol} 분석 중 오류 발생: {e}")
                logger.error(traceback.format_exc())
                
    except Exception as e:
        logger.error(f"실제 주식 데이터 테스트 오류: {e}")
        logger.error(traceback.format_exc())
        
    logger.info("실제 주식 데이터 테스트 완료")

if __name__ == "__main__":
    try:
        logger.info("테스트 스크립트 실행 시작")
        load_dotenv()  # .env 파일 로드
        logger.info(".env 파일 로드 완료")
        
        # 인공 데이터로 테스트
        test_hybrid_analysis()
        
        # 실제 주식 데이터로 테스트 (필요한 경우 주석 해제)
        # test_real_stock_data()
    except Exception as e:
        logger.error(f"테스트 스크립트 실행 중 오류 발생: {e}")
        logger.error(traceback.format_exc())