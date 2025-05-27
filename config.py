"""
AI 주식 분석 시스템 설정 파일
"""
import os
import pytz
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 시간대 설정
KST = pytz.timezone('Asia/Seoul')
EST = pytz.timezone('US/Eastern')

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # 텔레그램 채팅 ID

# 카카오톡 설정 추가
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")  # 카카오 REST API 키
KAKAO_ACCESS_TOKEN = os.getenv("KAKAO_ACCESS_TOKEN")  # 카카오 액세스 토큰
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN")  # 카카오 리프레시 토큰
USE_KAKAO = os.getenv("USE_KAKAO", "False").lower() == "true"  # 카카오톡 메시지 사용 여부

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
AUTO_TRADING_ENABLED = True  # 자동 매매 활성화 여부 (초기값: 비활성화)
USE_MARKET_ORDER = False  # 시장가 주문 사용 여부 (False: 지정가 사용)

# 증권사 API 설정
BROKER_TYPE = "KIS"  # 사용할 증권사 API (KIS: 한국투자증권)

# 한국투자증권 API 설정
KIS_APP_KEY = os.getenv("KIS_APP_KEY")  # 한국투자증권 앱키
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")  # 한국투자증권 앱시크릿
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "50123456789")  # 계좌번호 (앞 8자리)
KIS_PERSONALSECKEY = os.getenv("KIS_PERSONALSECKEY", "")  # 개인식별키 (모의투자 시에는 필요 없음)

# 한국투자증권 모의투자 API 설정
KIS_VIRTUAL_APP_KEY = os.getenv("KIS_VIRTUAL_APP_KEY")  # 모의투자 앱키
KIS_VIRTUAL_APP_SECRET = os.getenv("KIS_VIRTUAL_APP_SECRET")  # 모의투자 앱시크릿
KIS_VIRTUAL_ACCOUNT_NO = os.getenv("KIS_VIRTUAL_ACCOUNT_NO", "50123456789")  # 모의투자 계좌번호

# 실전투자/모의투자 설정
KIS_REAL_TRADING = os.getenv("KIS_REAL_TRADING", "False").lower() == "true"  # 기본값: 모의투자

# 모의투자용 서버 URL (실전과 다름)
KIS_VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"

# 키움증권 API 설정 (사용하지 않음)
# KIWOOM_USER_ID = os.getenv("KIWOOM_USER_ID", "")  # 키움증권 아이디
# KIWOOM_USER_PW = os.getenv("KIWOOM_USER_PW", "")  # 키움증권 비밀번호
# KIWOOM_CERT_PW = os.getenv("KIWOOM_CERT_PW", "")  # 키움증권 공인인증서 비밀번호

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

# OpenAI ChatGPT API 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API 키
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # 사용할 모델
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))  # 최대 토큰 수
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))  # 응답 다양성
OPENAI_REQUEST_INTERVAL = float(os.getenv("OPENAI_REQUEST_INTERVAL", "1.0"))  # API 요청 간격 (초)

# GPT에 의해 추천된 한국 종목 정보 (코드와 이름)
KR_STOCK_INFO = [{'code': '005930', 'name': '삼성전자'}, {'code': '000660', 'name': 'SK하이닉스'}, {'code': '051910', 'name': 'LG화학'}, {'code': '035420', 'name': 'NAVER'}, {'code': '096770', 'name': 'SK이노베이션'}, {'code': '005380', 'name': '현대차'}]


# GPT에 의해 추천된 미국 종목 정보 (코드와 이름)
US_STOCK_INFO = [{'code': 'AAPL', 'name': 'Apple Inc.'}, {'code': 'MSFT', 'name': 'Microsoft Corporation'}, {'code': 'JNJ', 'name': 'Johnson & Johnson'}, {'code': 'XOM', 'name': 'Exxon Mobil Corporation'}, {'code': 'GOOGL', 'name': 'Alphabet Inc.'}]
