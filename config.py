"""
AI 주식 분석 시스템 설정 파일
로컬 및 GitHub Actions에서 모두 사용 가능한 설정
"""
import os
import pytz
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Config')

# 환경 변수 설정
def setup_env():
    """환경 변수 설정 및 로드"""
    # 환경 설정이 CI/CD에서 실행 중인지 확인
    is_ci = os.environ.get('CI') == 'true'
    
    if is_ci:
        logger.info("CI/CD 환경에서 실행 중입니다. 환경 변수를 사용합니다.")
    else:
        # 로컬 환경에서는 .env 파일 로드
        logger.info("로컬 환경에서 실행 중입니다. .env 파일을 로드합니다.")
        env_path = Path(__file__).parent / '.env'
        load_dotenv(dotenv_path=env_path)
        
        # 로컬에서 토큰 파일 확인
        token_path = Path(__file__).parent / 'kakao_token.json'
        if token_path.exists():
            try:
                with open(token_path, 'r') as f:
                    token_data = json.load(f)
                    # 토큰 파일에서 환경 변수로 설정
                    os.environ['KAKAO_ACCESS_TOKEN'] = token_data.get('access_token', '')
                    os.environ['KAKAO_REFRESH_TOKEN'] = token_data.get('refresh_token', '')
                    logger.info("카카오 토큰 파일을 로드했습니다.")
            except Exception as e:
                logger.error(f"카카오 토큰 파일 로드 오류: {e}")

# 환경 변수 설정 실행
setup_env()

# 시간대 설정
KST = pytz.timezone('Asia/Seoul')
EST = pytz.timezone('US/Eastern')

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # 텔레그램 채팅 ID
USE_TELEGRAM = os.environ.get("USE_TELEGRAM", "False").lower() == "true"  # 텔레그램 사용 여부

# 카카오톡 설정
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")  # 카카오 REST API 키
KAKAO_ACCESS_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN")  # 카카오 액세스 토큰
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")  # 카카오 리프레시 토큰
USE_KAKAO = os.environ.get("USE_KAKAO", "True").lower() == "true"  # 카카오톡 메시지 사용 여부

# 토큰이 설정되지 않았을 경우 경고
if USE_KAKAO and (not KAKAO_ACCESS_TOKEN or not KAKAO_REFRESH_TOKEN):
    logger.warning("카카오톡 토큰이 설정되지 않았지만 USE_KAKAO가 활성화되어 있습니다.")

# 국내 주식 설정
KR_MARKET_OPEN_TIME = "09:00"  # 한국 시장 개장 시간
KR_MARKET_CLOSE_TIME = "15:30"  # 한국 시장 폐장 시간
KR_STOCKS = []

# 미국 주식 설정
US_MARKET_OPEN_TIME = "09:30"  # 미국 시장 개장 시간 (EST)
US_MARKET_CLOSE_TIME = "16:00"  # 미국 시장 폐장 시간 (EST)
US_STOCKS = []

# 기술적 분석 파라미터
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
SHORT_TERM_MA = 20
LONG_TERM_MA = 60

# 데이터 수집 설정
DATA_UPDATE_INTERVAL = 30  # 데이터 수집 간격(분)

# 자동 매매 설정
AUTO_TRADING_ENABLED = True  # 자동 매매 활성화 여부
USE_MARKET_ORDER = False  # 시장가 주문 사용 여부 (False: 지정가 사용)

# 증권사 API 설정
BROKER_TYPE = "KIS"  # 사용할 증권사 API (KIS: 한국투자증권)

# 한국투자증권 API 설정
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")  # 한국투자증권 앱키
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")  # 한국투자증권 앱시크릿
KIS_ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO", "50123456789")  # 계좌번호 (앞 8자리)

# 한국투자증권 모의투자 API 설정
KIS_VIRTUAL_APP_KEY = os.environ.get("KIS_VIRTUAL_APP_KEY")  # 모의투자 앱키
KIS_VIRTUAL_APP_SECRET = os.environ.get("KIS_VIRTUAL_APP_SECRET")  # 모의투자 앱시크릿
KIS_VIRTUAL_ACCOUNT_NO = os.environ.get("KIS_VIRTUAL_ACCOUNT_NO", "50123456789")  # 모의투자 계좌번호

# 실전투자/모의투자 설정
KIS_REAL_TRADING = os.environ.get("KIS_REAL_TRADING", "False").lower() == "true"  # 기본값: 모의투자

# 모의투자용 서버 URL (실전과 다름)
KIS_VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"

# 매매 설정
MAX_QUANTITY_PER_SYMBOL = 100  # 종목당 최대 보유 수량
MAX_DAILY_TRADES_PER_SYMBOL = 2  # 종목당 일일 최대 거래 횟수
MIN_TRADE_INTERVAL_SECONDS = 1800  # 종목당 매매 최소 간격 (초)
TRADE_RATIO_PER_SYMBOL = 0.1  # 예수금 대비 종목당 최대 매수 비율 (0.1 = 10%)
MAX_AMOUNT_PER_TRADE = 1000000  # 1회 최대 매수 금액 (원)

# 매도 비율 설정 (보유량 대비)
SELL_RATIO_STRONG = 0.5  # 강한 매도 신호 시 매도 비율 (50%)
SELL_RATIO_MEDIUM = 0.3  # 중간 매도 신호 시 매도 비율 (30%)
SELL_RATIO_WEAK = 0.1  # 약한 매도 신호 시 매도 비율 (10%)

# 모의투자 기본 설정
MOCK_INITIAL_CAPITAL = 50000000  # 모의투자 초기 자본금 (5천만원)
MAX_RUNTIME_MINUTES = 180  # 모의 자동매매 최대 실행 시간 (분) - 기본 3시간

# 손절/익절 설정
STOP_LOSS_PCT = 5  # 손절매 비율 (기본 5%)
TAKE_PROFIT_PCT = 10  # 익절 비율 (기본 10%)
USE_TRAILING_STOP = True  # 트레일링 스탑 사용 여부
TRAILING_STOP_DISTANCE = 3  # 트레일링 스탑 거리(%) - 최고가 대비 3% 하락시 매도

# 시장 시간 강제 설정 (CI 환경에서 사용)
FORCE_MARKET_OPEN = os.environ.get("FORCE_MARKET_OPEN", "False").lower() == "true"  # 강제로 시장을 열림 상태로 간주

# OpenAI ChatGPT API 설정
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # OpenAI API 키
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")  # 사용할 모델
OPENAI_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "1000"))  # 최대 토큰 수
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.7"))  # 응답 다양성
OPENAI_REQUEST_INTERVAL = float(os.environ.get("OPENAI_REQUEST_INTERVAL", "1.0"))  # API 요청 간격 (초)

# Google Gemini API 설정
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # Gemini API 키
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")  # 모델을 1.5로 변경
GEMINI_MAX_TOKENS = int(os.environ.get("GEMINI_MAX_TOKENS", "1000"))  # 최대 토큰 수
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.7"))  # 응답 다양성
GEMINI_REQUEST_INTERVAL = float(os.environ.get("GEMINI_REQUEST_INTERVAL", "1.2"))  # API 요청 간격 (1.2초로 증가)

# GPT 분석 사용 여부
USE_GPT_ANALYSIS = os.environ.get("USE_GPT_ANALYSIS", "False").lower() == "true"

# GPT에 의해 추천된 한국 종목 정보 (코드와 이름)
KR_STOCK_INFO = [
    {'code': '005930', 'name': '삼성전자'}, 
    {'code': '000660', 'name': 'SK하이닉스'}, 
    {'code': '051910', 'name': 'LG화학'}, 
    {'code': '035420', 'name': 'NAVER'}, 
    {'code': '096770', 'name': 'SK이노베이션'}, 
    {'code': '005380', 'name': '현대차'}
]

# GPT에 의해 추천된 미국 종목 정보 (코드와 이름)
US_STOCK_INFO = [
    {'code': 'AAPL', 'name': 'Apple Inc.'}, 
    {'code': 'MSFT', 'name': 'Microsoft Corporation'}, 
    {'code': 'JNJ', 'name': 'Johnson & Johnson'}, 
    {'code': 'XOM', 'name': 'Exxon Mobil Corporation'}, 
    {'code': 'GOOGL', 'name': 'Alphabet Inc.'}
]

# 종목 코드 리스트 생성
KR_STOCKS = [stock['code'] for stock in KR_STOCK_INFO]
US_STOCKS = [stock['code'] for stock in US_STOCK_INFO]

# 실행 환경 확인
IS_CI_ENV = os.environ.get('CI') == 'true'
logger.info(f"실행 환경: {'CI/CD' if IS_CI_ENV else '로컬'}")
logger.info(f"카카오톡 메시지 사용: {USE_KAKAO}")
logger.info(f"텔레그램 메시지 사용: {USE_TELEGRAM}")
logger.info(f"GPT 분석 사용: {USE_GPT_ANALYSIS}")
logger.info(f"자동 손절/익절 기능: 활성화 (손절: {STOP_LOSS_PCT}%, 익절: {TAKE_PROFIT_PCT}%, 트레일링 스탑: {'사용' if USE_TRAILING_STOP else '미사용'})")

# 환경 설정 요약
if USE_KAKAO and KAKAO_API_KEY and KAKAO_ACCESS_TOKEN and KAKAO_REFRESH_TOKEN:
    logger.info("카카오톡 토큰이 설정되었습니다.")
else:
    logger.warning("카카오톡 토큰이 완전히 설정되지 않았습니다.")
