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
    is_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
    
    if is_ci or is_github_actions:
        logger.info("CI/CD 또는 GitHub Actions 환경에서 실행 중입니다. 환경 변수를 사용합니다.")
        # CI/GitHub Actions 환경에서는 시장을 강제로 열림 상태로 설정
        os.environ["FORCE_MARKET_OPEN"] = "true"
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

# 미국 주식 거래 설정
US_STOCK_TRADING_ENABLED = os.environ.get("US_STOCK_TRADING_ENABLED", "False").lower() == "true"  # 미국 주식 거래 활성화 여부 (기본값: 비활성화)
# 환경 변수로 설정하지 않은 경우 여기서 직접 변경 가능 (True: 활성화, False: 비활성화)
# US_STOCK_TRADING_ENABLED = True  # 주석을 제거하고 True로 설정하면 미국 주식 거래가 활성화됩니다.

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # 텔레그램 채팅 ID
USE_TELEGRAM = os.environ.get("USE_TELEGRAM", "False").lower() == "true"  # 텔레그램 사용 여부

# 카카오톡 설정
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")  # 카카오 REST API 키
KAKAO_ACCESS_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN")  # 카카오 액세스 토큰
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")  # 카카오 리프레시 토큰
USE_KAKAO = os.environ.get("USE_KAKAO", "True").lower() == "true"  # 카카오톡 메시지 사용 여부

# 국내 주식 설정
KR_MARKET_OPEN_TIME = "09:00"  # 한국 시장 개장 시간
KR_MARKET_CLOSE_TIME = "15:30"  # 한국 시장 폐장 시간

# 미국 주식 설정
US_MARKET_OPEN_TIME = "09:30"  # 미국 시장 개장 시간 (EST)
US_MARKET_CLOSE_TIME = "16:00"  # 미국 시장 폐장 시간 (EST)

# 자동 매매 설정
AUTO_TRADING_ENABLED = True  # 자동 매매 활성화 여부
USE_MARKET_ORDER = False  # 시장가 주문 사용 여부 (False: 지정가 사용)
SIMULATION_MODE = True  # 시뮬레이션 모드 활성화 여부 (API 연결 실패시 기본 동작)

# 증권사 API 설정
BROKER_TYPE = "KIS"  # 사용할 증권사 API (KIS: 한국투자증권)

# 한국투자증권 API 설정
KIS_APP_KEY = os.environ.get("KIS_APP_KEY")  # 한국투자증권 앱키
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")  # 한국투자증권 앱시크릿
KIS_ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO")  # 계좌번호

# 모의투자 API 설정 추가
KIS_VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자 API URL
KIS_VIRTUAL_APP_KEY = os.environ.get("KIS_VIRTUAL_APP_KEY", KIS_APP_KEY)  # 모의투자 앱키 (기본값: 실전투자 앱키)
KIS_VIRTUAL_APP_SECRET = os.environ.get("KIS_VIRTUAL_APP_SECRET", KIS_APP_SECRET)  # 모의투자 앱시크릿 (기본값: 실전투자 앱시크릿)
KIS_VIRTUAL_ACCOUNT_NO = os.environ.get("KIS_VIRTUAL_ACCOUNT_NO")  # 모의투자 계좌번호

# 실전투자 설정
KIS_REAL_TRADING = os.environ.get("KIS_REAL_TRADING", "False").lower() == "true"  # 기본값: 모의투자

# 모의투자 시장 제한 설정
VIRTUAL_TRADING_KR_ONLY = os.environ.get("VIRTUAL_TRADING_KR_ONLY", "True").lower() == "true"  # 모의투자에서 국내주식만 거래 가능 여부
ALLOWED_VIRTUAL_MARKETS = os.environ.get("ALLOWED_VIRTUAL_MARKETS", "KR").split(",")  # 모의투자에서 허용된 시장 (KR, US)

# 매매 설정
MAX_QUANTITY_PER_SYMBOL = 100  # 종목당 최대 보유 수량
MAX_AMOUNT_PER_TRADE = 1000000  # 1회 최대 매수 금액 (원)

# 기술적 지표 계산을 위한 설정
RSI_PERIOD = 14  # RSI 계산을 위한 기간
MACD_FAST = 12  # MACD 빠른 이동평균 기간
MACD_SLOW = 26  # MACD 느린 이동평균 기간
MACD_SIGNAL = 9  # MACD 시그널 기간
BOLLINGER_PERIOD = 20  # 볼린저 밴드 계산 기간
BOLLINGER_STD = 2.0  # 볼린저 밴드 표준편차
MA_SHORT = 5  # 단기 이동평균 기간
MA_MEDIUM = 20  # 중기 이동평균 기간
MA_LONG = 60  # 장기 이동평균 기간

# 이전 코드와의 호환성을 위한 별칭
SHORT_TERM_MA = MA_SHORT  # 단기 이동평균 별칭
MEDIUM_TERM_MA = MA_MEDIUM  # 중기 이동평균 별칭
LONG_TERM_MA = MA_LONG  # 장기 이동평균 별칭

# RSI 매수/매도 임계값
RSI_OVERSOLD = 30  # RSI 과매도 기준
RSI_OVERBOUGHT = 70  # RSI 과매수 기준

# GPT 자동 매매 설정
GPT_AUTO_TRADING = True  # GPT 자동 매매 활성화 여부
GPT_STOCK_SELECTION_INTERVAL = 24  # 종목 선정 간격 (시간)
GPT_TRADING_MAX_POSITIONS = 10  # 최대 포지션 수 (5에서 10으로 증가)
GPT_TRADING_CONF_THRESHOLD = 0.7  # 매매 신뢰도 임계값
GPT_MAX_INVESTMENT_PER_STOCK = 1000000  # 종목당 최대 투자금액 (원)
GPT_STRATEGY = "balanced"  # 기본 전략 (balanced, growth, value, dividend)
GPT_TRADING_MONITOR_INTERVAL = 30  # 모니터링 간격 (분)
GPT_USE_DYNAMIC_SELECTION = True  # 하드코딩 대신 GPT가 동적으로 종목 선정 (추가된 옵션)

# 미국 주식 종목 설정
US_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN"]

# 데이터베이스 설정
USE_DATABASE = os.environ.get("USE_DATABASE", "True").lower() == "true"  # 데이터베이스 사용 여부
DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()  # 데이터베이스 타입 (sqlite, mysql)

# 데이터베이스 자동 백업 설정 추가
DB_AUTO_BACKUP = os.environ.get("DB_AUTO_BACKUP", "True").lower() == "true"  # 자동 백업 여부
DB_BACKUP_INTERVAL = int(os.environ.get("DB_BACKUP_INTERVAL", "24"))  # 백업 간격 (시간)

# SQLite 설정
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", str(Path(__file__).parent / "data" / "stock_trading.db"))

# MySQL 설정
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DB", "stock_trading")

# 시장 강제 설정 (CI 환경에서 사용)
FORCE_MARKET_OPEN = os.environ.get("FORCE_MARKET_OPEN", "True").lower() == "true"  # 강제로 시장을 열림 상태로 간주

# GPT에 의해 추천된 한국 종목 정보 (코드와 이름)
# GPT_USE_DYNAMIC_SELECTION = True 설정 시 아래 목록은 GPT가 자동 업데이트합니다
KR_STOCK_INFO = [
    {'code': '005930', 'name': '삼성전자'}, 
    {'code': '000660', 'name': 'SK하이닉스'}, 
    {'code': '051910', 'name': 'LG화학'}, 
    {'code': '035420', 'name': 'NAVER'}, 
    {'code': '096770', 'name': 'SK이노베이션'}, 
    {'code': '005380', 'name': '현대차'},
    {'code': '035720', 'name': '카카오'},
    {'code': '068270', 'name': '셀트리온'}, 
    {'code': '207940', 'name': '삼성바이오로직스'},
    {'code': '006400', 'name': '삼성SDI'},
    {'code': '018260', 'name': '삼성에스디에스'},
    {'code': '000270', 'name': '기아'},
    {'code': '005490', 'name': 'POSCO홀딩스'},
    {'code': '036570', 'name': 'NCsoft'},
    {'code': '055550', 'name': '신한지주'}
]

# 종목 코드 리스트 생성
KR_STOCKS = [stock['code'] for stock in KR_STOCK_INFO]

# 실행 환경 확인
IS_CI_ENV = os.environ.get('CI') == 'true'
logger.info(f"실행 환경: {'CI/CD' if IS_CI_ENV else '로컬'}")
logger.info(f"카카오톡 메시지 사용: {USE_KAKAO}")
logger.info(f"텔레그램 메시지 사용: {USE_TELEGRAM}")
logger.info(f"자동 매매 기능: {AUTO_TRADING_ENABLED}")
logger.info(f"강제 시장 열림: {FORCE_MARKET_OPEN}")
logger.info(f"데이터베이스 사용: {USE_DATABASE} (타입: {DB_TYPE})")
logger.info(f"증권사 API 모드: {'실전투자' if KIS_REAL_TRADING else '모의투자'}")
