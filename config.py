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
        # CI/GitHub Actions 환경에서는 시장을 강제로 열림 상태로 설정 (테스트 용도)
        os.environ["FORCE_MARKET_OPEN"] = "true"
        # GitHub Actions 환경에서는 시뮬레이션 모드를 비활성화하고 실제 거래 수행
        os.environ["SIMULATION_MODE"] = "false"
        logger.info("GitHub Actions 환경에서 실제 거래를 위해 시뮬레이션 모드를 비활성화합니다.")
    else:
        # 로컬 환경에서는 .env 파일 로드
        logger.info("로컬 환경에서 실행 중입니다. .env 파일을 로드합니다.")
        env_path = Path(__file__).parent / '.env'
        load_dotenv(dotenv_path=env_path)
        
        # 로컬 환경에서는 FORCE_MARKET_OPEN을 명시적으로 비활성화
        os.environ["FORCE_MARKET_OPEN"] = "false"
        logger.info("로컬 환경에서 FORCE_MARKET_OPEN을 비활성화합니다.")
        
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
US_STOCK_TRADING_ENABLED = True  # 미국 주식 거래 활성화 여부 (기본값: 활성화)

# 미국 주식 시장 시간 (미국 동부시간 기준)
US_MARKET_OPEN_TIME = "09:30"  # 미국 시장 개장 시간 (EST)
US_MARKET_CLOSE_TIME = "16:00"  # 미국 시장 폐장 시간 (EST)

# 미국 주식 시장 시간 (한국 시간 기준) - 시차 적용
US_MARKET_OPEN_TIME_KST = "22:30"  # 미국 시장 개장 시간 (KST)
US_MARKET_CLOSE_TIME_KST = "05:00"  # 미국 시장 폐장 시간 (KST)

# 미국 시장 애프터마켓/프리마켓 설정
US_AFTER_MARKET_ENABLED = True  # 미국 애프터 마켓 활성화 여부
US_AFTER_MARKET_OPEN_TIME = "16:00"  # 미국 애프터 마켓 시작 시간 (EST)
US_AFTER_MARKET_CLOSE_TIME = "20:00"  # 미국 애프터 마켓 종료 시간 (EST)
US_PRE_MARKET_ENABLED = True  # 미국 프리 마켓 활성화 여부
US_PRE_MARKET_OPEN_TIME = "05:00"  # 미국 프리 마켓 시작 시간 (EST)
US_PRE_MARKET_CLOSE_TIME = "09:30"  # 미국 프리 마켓 종료 시간 (EST)

# 한국 시간 기준 미국 시장 확장 거래 시간
US_AFTER_MARKET_OPEN_TIME_KST = "05:00"  # 미국 애프터 마켓 시작 시간 (KST)
US_AFTER_MARKET_CLOSE_TIME_KST = "09:00"  # 미국 애프터 마켓 종료 시간 (KST)
US_PRE_MARKET_OPEN_TIME_KST = "18:00"  # 미국 프리 마켓 시작 시간 (KST)
US_PRE_MARKET_CLOSE_TIME_KST = "22:30"  # 미국 프리 마켓 종료 시간 (KST)

# 미국 주식 시간외 거래 설정
US_AFTER_MARKET_TRADING = True  # 미국 시간외 거래 활성화 여부

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # 텔레그램 채팅 ID
USE_TELEGRAM = os.environ.get("USE_TELEGRAM", "False").lower() == "true"  # 텔레그램 사용 여부

# 카카오톡 설정
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")  # 카카오 REST API 키
KAKAO_ACCESS_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN")  # 카카오 액세스 토큰
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN")  # 카카오 리프레시 토큰
USE_KAKAO = os.environ.get("USE_KAKAO", "True").lower() == "true"  # 카카오톡 메시지 사용 여부
KAKAO_MSG_ENABLED = USE_KAKAO  # 코드 일관성을 위해 KAKAO_MSG_ENABLED도 동일하게 설정

# 국내 주식 설정
KR_MARKET_OPEN_TIME = "09:00"  # 한국 시장 개장 시간
KR_MARKET_CLOSE_TIME = "15:30"  # 한국 시장 폐장 시간

# 애프터 마켓(시간외 거래) 설정 추가
KR_AFTER_MARKET_ENABLED = True  # 애프터 마켓 활성화 여부
KR_AFTER_MARKET_OPEN_TIME = "08:00"  # 시간외 거래 개장 시간 (오전 8시부터)
KR_AFTER_MARKET_CLOSE_TIME = "18:00"  # 시간외 거래 폐장 시간
KR_AFTER_MARKET_TRADING = True  # 시간외 거래 활성화 여부
USE_EXTENDED_HOURS = True  # 확장 거래 시간 사용 여부

# 미국 주식 설정
US_MARKET_OPEN_TIME = "09:30"  # 미국 시장 개장 시간 (EST)
US_MARKET_CLOSE_TIME = "16:00"  # 미국 시장 폐장 시간 (EST)

# 자동 매매 설정
AUTO_TRADING_ENABLED = True  # 자동 매매 활성화 여부
USE_MARKET_ORDER = False  # 시장가 주문 사용 여부 (False: 지정가 사용)
SIMULATION_MODE = False  # 내부 시뮬레이션 모드 비활성화 (실제 거래 API 호출 발생)

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
KIS_REAL_TRADING = True  # 실전투자 모드로 설정 (False = 모의투자, True = 실전투자)

# 초기 자본금 설정
INITIAL_CAPITAL = 1000000  # 실전투자 초기 자본금 (100만원)

# 하락장 매수 전략 설정
DIP_BUYING_ONLY = False  # 하락장에서만 매수 (True = 하락장만 매수, False = 상관없이 매수)
DIP_THRESHOLD_PCT = -2.0  # 하락 기준 퍼센트 완화 (기존 -3.0%)
DIP_PERIOD = 3  # 하락 측정 기간 단축 (기존 5일)

# 모의투자 시장 제한 설정
VIRTUAL_TRADING_KR_ONLY = os.environ.get("VIRTUAL_TRADING_KR_ONLY", "True").lower() == "true"  # 모의투자에서 국내주식만 거래 가능 여부
ALLOWED_VIRTUAL_MARKETS = os.environ.get("ALLOWED_VIRTUAL_MARKETS", "KR").split(",")  # 모의투자에서 허용된 시장 (KR, US)

# 매매 설정
MAX_QUANTITY_PER_SYMBOL = 100  # 종목당 최대 보유 수량
MAX_AMOUNT_PER_TRADE = 1000000  # 1회 최대 매수 금액 (원)

# 기술적 지표 계산을 위한 설정
RSI_PERIOD = 10
MACD_FAST = 10
MACD_SLOW = 24
MACD_SIGNAL = 8
BOLLINGER_PERIOD = 15
BOLLINGER_STD = 2.5
MA_SHORT = 3
MA_MEDIUM = 15
MA_LONG = 50

# 이전 코드와의 호환성을 위한 별칭
SHORT_TERM_MA = MA_SHORT  # 단기 이동평균 별칭
MEDIUM_TERM_MA = MA_MEDIUM  # 중기 이동평균 별칭
LONG_TERM_MA = MA_LONG  # 장기 이동평균 별칭

# GPT 자동 매매 설정 - 추가
GPT_AUTO_TRADING = True  # GPT 자동 매매 활성화 여부
GPT_TRADING_MAX_POSITIONS = 5  # GPT 동시 보유 종목 수
GPT_TRADING_CONF_THRESHOLD = 0.7  # GPT 매매 신뢰도 임계값
GPT_MAX_INVESTMENT_PER_STOCK = 5000000  # GPT 종목당 최대 투자금액
GPT_STOCK_SELECTION_INTERVAL = 24  # GPT 종목 선정 주기 (시간)
GPT_STRATEGY = "balanced"  # GPT 전략 (aggressive, balanced, conservative 중 선택)
GPT_USE_DYNAMIC_SELECTION = True  # 동적 종목 선정 사용 여부
GPT_TRADING_MONITOR_INTERVAL = 10  # GPT 모니터링 주기 (분)

# GPT 완전 자율 매매 설정 - 추가
GPT_FULLY_AUTONOMOUS_MODE = True  # GPT 완전 자율 매매 모드 활성화
GPT_AUTONOMOUS_TRADING_INTERVAL = 5  # 자율 매매 주기 (분)
GPT_AUTONOMOUS_MAX_POSITIONS = 7  # 자율 매매 최대 포지션 수
GPT_AUTONOMOUS_MAX_TRADE_AMOUNT = 1000000  # 자율 매매 종목당 최대 금액 (원)
GPT_REALTIME_MARKET_SCAN_INTERVAL = 10  # 실시간 시장 스캔 주기 (분)
GPT_AGGRESSIVE_MODE = False  # 공격적 매매 모드 (True: 위험 감수, False: 안전 추구)

# GPT 위험 관리 설정 - 추가
GPT_RISK_MANAGEMENT_ENABLED = True  # GPT 위험 관리 기능 활성화
GPT_DAILY_LOSS_LIMIT = 5.0  # 일일 최대 손실 허용 비율 (%)
GPT_AUTO_RESTART_ENABLED = True  # 오류 발생 시 자동 재시작 기능 활성화

# GPT 기술적 지표 최적화 설정
GPT_OPTIMIZE_TECHNICAL_INDICATORS = True  # GPT가 기술적 지표 설정 최적화 여부
GPT_TECHNICAL_OPTIMIZATION_INTERVAL = 168  # 기술적 지표 최적화 간격 (시간, 기본값 1주일)
GPT_TECHNICAL_MARKET_SENSITIVITY = "market_sensitive"  # market_sensitive(시장 민감), balanced(균형), conservative(보수적)

# RSI 매수/매도 임계값
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75

# 단타 매매 설정
DAY_TRADING_MODE = True  # 단타 매매 모드 활성화 여부
DAY_TRADING_MAX_POSITIONS = 5  # 단타 매매 시 최대 동시 포지션 수 증가 (기존 3)
DAY_TRADING_PROFIT_THRESHOLD = 3.0  # 단타 매매 이익 실현 기준 상향 (기존 2.0%)
DAY_TRADING_STOP_LOSS = 2.0  # 단타 매매 손절 기준 조정 (기존 1.0%)
DAY_TRADING_MONITOR_INTERVAL = 2  # 단타 매매 모니터링 간격 단축 (기존 3분)
DAY_TRADING_POSITION_HOLD_MAX = 120  # 단타 매매 최대 보유 시간 단축 (기존 180분)
DAY_TRADING_VOLATILITY_THRESHOLD = 2.0  # 단타 매매 대상 종목 변동성 기준 상향 (기존 1.5%)

# 급등주 감지 및 매매 설정 - 중소형주 중심 최적화
SURGE_DETECTION_ENABLED = True  # 급등주 감지 활성화
SURGE_THRESHOLD = 3.0  # 급등 기준 하향 (기존 5.0%)
SURGE_VOLUME_RATIO = 1.5  # 급등주 거래량 증가 비율 기준 하향 (기존 2.0)
SURGE_SCORE_THRESHOLD = 6  # 급등주 매매 점수 기준 하향 (기존 7)
MAX_SURGE_POSITIONS = 3  # 급등주 최대 포지션 수 증가 (기존 2)
SURGE_SCAN_INTERVAL = int(os.environ.get("SURGE_SCAN_INTERVAL", "10"))  # 급등주 스캔 간격(분)
SURGE_PROFIT_MULTIPLE = float(os.environ.get("SURGE_PROFIT_MULTIPLE", "1.5"))  # 급등주 익절 배수
SURGE_GPT_ANALYSIS_ENABLED = os.environ.get("SURGE_GPT_ANALYSIS_ENABLED", "True").lower() == "true"  # GPT를 사용한 급등주 분석 활성화

# GPT와 실시간 트레이딩 연동 설정 - 추가
REALTIME_GPT_INTEGRATION = True  # GPT와 실시간 트레이딩 연동 활성화
REALTIME_GPT_CONFIDENCE_THRESHOLD = 0.8  # 실시간 GPT 매매 신뢰도 임계값 
REALTIME_GPT_ANALYSIS_INTERVAL = 5  # 실시간 GPT 분석 간격 (분)
REALTIME_MOMENTUM_DETECTION = True  # 실시간 모멘텀 감지 활성화
MOMENTUM_SCORE_THRESHOLD = 85  # 모멘텀 점수 임계값 (0-100)
HYBRID_ANALYSIS_MODE = True  # 하이브리드 분석 모드(기술적 지표 + GPT 분석)

# 데이터베이스 설정
USE_DATABASE = False  # 데이터베이스 사용 비활성화 - 실시간 매매만 사용
DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()  # 데이터베이스 타입 (sqlite, mysql)

# 실시간 트레이더 설정
REALTIME_TRADING_ENABLED = True  # 실시간 트레이딩 활성화
REALTIME_ONLY_MODE = True  # 실시간 매매 전용 모드로 설정 (추가된 설정)
REALTIME_SCAN_INTERVAL_SECONDS = 30  # 실시간 스캔 간격 (초)
REALTIME_USE_GPT_ANALYSIS = True  # 실시간 트레이딩에서 GPT 분석 사용
REALTIME_GPT_CONFIDENCE_THRESHOLD = 0.8  # 실시간 GPT 신뢰도 임계값
PRICE_SURGE_THRESHOLD_PERCENT = 2.5  # 급등 가격 변화 임계값 (%)
VOLUME_SURGE_THRESHOLD_PERCENT = 200.0  # 급등 거래량 변화 임계값 (%)
REALTIME_MIN_TRADE_AMOUNT = 500000  # 실시간 트레이딩 최소 거래 금액 (원)
REALTIME_MAX_TRADE_AMOUNT = 2000000  # 실시간 트레이딩 최대 거래 금액 (원)
REALTIME_STOP_LOSS_PERCENT = 3.0  # 실시간 트레이딩 손절 기준 (%)
REALTIME_TAKE_PROFIT_PERCENT = 5.0  # 실시간 트레이딩 익절 기준 (%)
REALTIME_MAX_HOLDING_MINUTES = 60  # 실시간 트레이딩 최대 보유 시간 (분)

# GPT에 의해 추천된 한국 종목 정보 (코드와 이름)
# GPT_USE_DYNAMIC_SELECTION = True 설정 시 아래 목록은 GPT가 자동 업데이트합니다
# 주의: KR_STOCK_INFO = [{'code': '005930', 'name': '삼성전자'}, {'code': '035720', 'name': '카카오'}, {'code': '000660', 'name': 'SK하이닉스'}]
# 종목 데이터는 src/database/db_manager.py의 get_kr_stock_info() 함수를 통해 불러옵니다
KR_STOCK_INFO = []  # 빈 리스트로 시작, 실행 시 데이터베이스에서 자동으로 채워짐

# 종목 코드 리스트 생성
KR_STOCKS = []

# 시장 시간 관련 설정
FORCE_MARKET_OPEN = False  # 시장 시간 강제 오픈 여부 - 비활성화로 설정

# 웹 인터페이스 설정
WEB_UI_ENABLED = True  # 웹 인터페이스 활성화 여부
WEB_PORT = int(os.environ.get("WEB_PORT", "3000"))  # 웹 서버 포트
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")  # 웹 서버 호스트
WEB_DEBUG = os.environ.get("WEB_DEBUG", "False").lower() == "true"  # 웹 디버그 모드

# 웹 인터페이스 기능 설정
WEB_AUTO_REFRESH = True  # 웹 페이지 자동 새로고침 활성화
WEB_REFRESH_INTERVAL = 30  # 웹 페이지 새로고침 간격 (초)
WEB_REALTIME_CHART = True  # 실시간 차트 표시 활성화
WEB_SHOW_LOGS = True  # 로그 표시 활성화
WEB_MAX_LOG_ENTRIES = 1000  # 최대 로그 항목 수

# 웹 인터페이스 자동 매매 설정
WEB_AUTO_TRADING_CONTROLS = True  # 웹에서 자동 매매 제어 활성화
WEB_STRATEGY_SELECTION = True  # 웹에서 전략 선택 활성화
WEB_POSITION_LIMITS = 10  # 웹에서 설정 가능한 최대 포지션 수
WEB_MAX_INVESTMENT_AMOUNT = 10000000  # 웹에서 설정 가능한 최대 투자 금액 (원)

# 웹 인터페이스 사용자 설정
MAX_POSITIONS_PER_USER = int(os.environ.get("MAX_POSITIONS_PER_USER", "10"))
MAX_INVESTMENT_PER_TRADE_USER = int(os.environ.get("MAX_INVESTMENT_PER_TRADE_USER", "5000000"))
MAX_DAILY_TRADES_USER = int(os.environ.get("MAX_DAILY_TRADES_USER", "10"))
DEFAULT_STRATEGY_USER = os.environ.get("DEFAULT_STRATEGY_USER", "balanced")

# 실행 환경 확인
IS_CI_ENV = os.environ.get('CI') == 'true'
logger.info(f"실행 환경: {'CI/CD' if IS_CI_ENV else '로컬'}")
logger.info(f"카카오톡 메시지 사용: {USE_KAKAO}")
logger.info(f"텔레그램 메시지 사용: {USE_TELEGRAM}")
logger.info(f"자동 매매 기능: {AUTO_TRADING_ENABLED}")
logger.info(f"강제 시장 열림: {FORCE_MARKET_OPEN}")
logger.info(f"데이터베이스 사용: {USE_DATABASE} (타입: {DB_TYPE})")
logger.info(f"증권사 API 모드: {'실전투자' if KIS_REAL_TRADING else '모의투자'}")
logger.info(f"GPT 자동 매매 기능: {GPT_AUTO_TRADING} (완전자율모드: {GPT_FULLY_AUTONOMOUS_MODE})")
logger.info(f"실시간 GPT 연동: {REALTIME_GPT_INTEGRATION} (모멘텀 감지: {REALTIME_MOMENTUM_DETECTION})")
logger.info(f"웹 인터페이스: {WEB_UI_ENABLED} (포트: {WEB_PORT})")

# 스윙매매 설정
SWING_TRADING_MODE = os.environ.get("SWING_TRADING_MODE", "False").lower() == "true"  # 스윙 매매 모드 활성화 여부
SWING_TRADING_MAX_POSITIONS = int(os.environ.get("SWING_TRADING_MAX_POSITIONS", "5"))  # 스윙 매매 최대 포지션 수
SWING_TRADING_PROFIT_THRESHOLD = float(os.environ.get("SWING_TRADING_PROFIT_THRESHOLD", "10.0"))  # 스윙 매매 이익 실현 기준 (%)
SWING_TRADING_STOP_LOSS = float(os.environ.get("SWING_TRADING_STOP_LOSS", "5.0"))  # 스윙 매매 손절 기준 (%)
SWING_TRADING_MIN_HOLDING_DAYS = int(os.environ.get("SWING_TRADING_MIN_HOLDING_DAYS", "2"))  # 스윙 매매 최소 보유 일수
SWING_TRADING_MAX_HOLDING_DAYS = int(os.environ.get("SWING_TRADING_MAX_HOLDING_DAYS", "15"))  # 스윙 매매 최대 보유 일수
SWING_TRADING_MONITOR_INTERVAL = int(os.environ.get("SWING_TRADING_MONITOR_INTERVAL", "60"))  # 스윙 매매 모니터링 간격 (분)
SWING_SCORE_THRESHOLD = int(os.environ.get("SWING_SCORE_THRESHOLD", "75"))  # 스윙 매매 점수 임계값 (0-100)

# 시장 우선순위 설정 (추가)
US_MARKET_PRIORITY = True  # 미국 시장 우선 설정 (양쪽 시장이 열려있을 경우 미국 시장 우선)
MARKET_PRIORITY_TIME_CHECK_INTERVAL = 10  # 시장 우선순위 체크 간격 (분)
US_MARKET_ALLOCATION = 0.7  # 미국 시장 자본 배분 비율 (70%)
KR_MARKET_ALLOCATION = 0.3  # 한국 시장 자본 배분 비율 (30%)

# 초보자 실전투자 설정 (단타매매 중심 전략으로 변경)
GPT_STRATEGY_TYPE = "day_trading"  # 단타매매 중심 전략으로 설정
GPT_AGGRESSIVE_MODE = True  # 공격적 전략 사용
DAY_TRADING_MODE = True  # 단타 매매 모드 활성화
SWING_TRADING_MODE = False  # 스윙 매매 모드 비활성화
SWING_TRADING_ALLOCATION = 0.2  # 자본금의 20%를 스윙매매에 할당
DAY_TRADING_ALLOCATION = 0.8  # 자본금의 80%를 단타매매에 할당

# 웹 인터페이스 전략 설정
WEB_STRATEGY_BALANCED = {
    "name": "균형 (Balanced)",
    "day_trading_allocation": 0.5,
    "swing_trading_allocation": 0.5,
    "max_positions": 5,
    "stop_loss_percent": 5.0,
    "take_profit_percent": 10.0,
    "risk_level": "moderate"
}

WEB_STRATEGY_AGGRESSIVE = {
    "name": "공격적 (Aggressive)",
    "day_trading_allocation": 0.8,
    "swing_trading_allocation": 0.2,
    "max_positions": 7,
    "stop_loss_percent": 7.0,
    "take_profit_percent": 15.0,
    "risk_level": "high"
}

WEB_STRATEGY_CONSERVATIVE = {
    "name": "보수적 (Conservative)",
    "day_trading_allocation": 0.3,
    "swing_trading_allocation": 0.7,
    "max_positions": 3,
    "stop_loss_percent": 3.0,
    "take_profit_percent": 7.0,
    "risk_level": "low"
}

WEB_STRATEGY_DAY_TRADING = {
    "name": "단타매매 (Day Trading)",
    "day_trading_allocation": 1.0,
    "swing_trading_allocation": 0.0,
    "max_positions": 5,
    "stop_loss_percent": 2.0,
    "take_profit_percent": 5.0,
    "risk_level": "high",
    "position_hold_max_minutes": 120
}

WEB_STRATEGY_SWING_TRADING = {
    "name": "스윙매매 (Swing Trading)",
    "day_trading_allocation": 0.0,
    "swing_trading_allocation": 1.0,
    "max_positions": 5,
    "stop_loss_percent": 5.0,
    "take_profit_percent": 10.0,
    "risk_level": "moderate",
    "min_holding_days": 2,
    "max_holding_days": 14
}

# 현재 활성화된 웹 전략
CURRENT_WEB_STRATEGY = WEB_STRATEGY_DAY_TRADING  # 기본값으로 단타매매 전략 사용


# GPT에 의해 추천된 미국 종목 목록
US_STOCKS = []

# GPT에 의해 추천된 미국 종목 정보 (코드와 이름)
# 데이터베이스에서 동적으로 불러옴
US_STOCK_INFO = []

# 시스템 시작 시 데이터베이스에서 종목 정보 로드 함수
def load_stock_info():
    """
    데이터베이스에서 종목 정보를 로드하는 함수
    """
    try:
        from src.database.db_manager import DatabaseManager
        
        # 데이터베이스 매니저 인스턴스 가져오기
        db_manager = DatabaseManager.get_instance()
        
        # 미국 주식 종목 정보 로드
        global US_STOCK_INFO
        us_stocks = db_manager.get_us_stock_info()
        if us_stocks:
            US_STOCK_INFO = us_stocks
            logger.info(f"{len(us_stocks)}개의 미국 주식 종목 정보를 데이터베이스에서 로드했습니다.")
        else:
            # 기본 데이터로 초기화
            logger.warning("데이터베이스에서 미국 주식 정보를 로드할 수 없습니다. 기본 데이터를 사용합니다.")
            default_us_stocks = [
                {'code': 'AAPL', 'name': 'Apple Inc.'},
                {'code': 'MSFT', 'name': 'Microsoft Corporation'},
                {'code': 'GOOGL', 'name': 'Alphabet Inc.'},
                {'code': 'AMZN', 'name': 'Amazon.com Inc.'},
                {'code': 'META', 'name': 'Meta Platforms Inc.'},
                {'code': 'TSLA', 'name': 'Tesla Inc.'},
                {'code': 'NVDA', 'name': 'NVIDIA Corporation'}
            ]
            US_STOCK_INFO = default_us_stocks
            
            # 기본 데이터를 데이터베이스에 저장
            if db_manager.use_db:
                db_manager.save_us_stock_info(default_us_stocks)
        
        # 한국 주식 종목 정보 로드
        global KR_STOCK_INFO
        kr_stocks = db_manager.get_kr_stock_info()
        if kr_stocks:
            KR_STOCK_INFO = kr_stocks
            logger.info(f"{len(kr_stocks)}개의 한국 주식 종목 정보를 데이터베이스에서 로드했습니다.")
            
            # 코드 리스트 업데이트
            global KR_STOCKS
            KR_STOCKS = [stock['code'] for stock in KR_STOCK_INFO]
    
    except Exception as e:
        logger.error(f"종목 정보 로드 중 오류 발생: {e}")
        # 기본값 유지

# 초기 로드 실행
try:
    load_stock_info()
except Exception as e:
    logger.error(f"초기 종목 정보 로드 실패: {e}")
