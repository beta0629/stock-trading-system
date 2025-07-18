"""
한국투자증권 API 연동 모듈
"""
import logging
import time
import requests
import json
import traceback  # traceback 모듈 추가
from datetime import datetime, timedelta
import hashlib
import jwt  # PyJWT 라이브러리 필요
import uuid  # uuid 모듈 추가
from urllib.parse import urljoin, unquote
import pandas as pd
from pathlib import Path  # Path 추가
from enum import Enum  # Enum 추가

from .broker_base import BrokerBase
from ..utils.time_utils import get_current_time, get_adjusted_time, KST

# 주문 타입 및 매매 구분 열거형 정의
class OrderType(Enum):
    MARKET = "MARKET"  # 시장가
    LIMIT = "LIMIT"    # 지정가

class TradeAction(Enum):
    BUY = "BUY"        # 매수
    SELL = "SELL"      # 매도

# 로깅 설정
logger = logging.getLogger('KISAPI')

# API 호출 관련 상수
API_RATE_LIMIT_DELAY = 3.0  # 초당 API 호출 최대 횟수를 고려한 딜레이 (초) - 1초에서 3초로 증가
LAST_API_CALL_TIMES = {}  # API 종류별 마지막 호출 시간 기록

def ensure_api_rate_limit(api_name, is_real_trading=False):
    """
    API 호출 속도 제한 준수를 위한 딜레이 함수
    
    Args:
        api_name: API 종류 식별자
        is_real_trading: 실전투자 여부 (True: 실전투자, False: 모의투자)
    """
    # 실전투자일 경우 딜레이 없이 바로 반환
    if is_real_trading:
        # logger.debug(f"실전투자 모드 - {api_name} API 딜레이 건너뜀")
        LAST_API_CALL_TIMES[api_name] = time.time()  # 호출 시간은 기록
        return
    
    # 모의투자일 경우에만 API 호출 속도 제한 적용
    current_time = time.time()
    last_call_time = LAST_API_CALL_TIMES.get(api_name, 0)
    elapsed = current_time - last_call_time
    
    # 마지막 호출 이후 최소 딜레이 시간이 지나지 않았으면 대기
    if elapsed < API_RATE_LIMIT_DELAY:
        wait_time = API_RATE_LIMIT_DELAY - elapsed
        logger.debug(f"모의투자 모드 - {api_name} API 호출 제한을 위해 {wait_time:.2f}초 대기")
        time.sleep(wait_time)
    
    # 마지막 호출 시간 갱신
    LAST_API_CALL_TIMES[api_name] = time.time()

class KISAPI(BrokerBase):
    """한국투자증권 API 연동 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        super().__init__(config)
        # 로거 설정 - 클래스 인스턴스에 할당
        self.logger = logger
        
        # 실전투자 여부 확인
        self.real_trading = config.KIS_REAL_TRADING
        
        # 실전/모의투자에 따른 설정
        if self.real_trading:
            self.base_url = "https://openapi.koreainvestment.com:9443"
            self.app_key = config.KIS_APP_KEY
            self.app_secret = config.KIS_APP_SECRET
            self.account_no = config.KIS_ACCOUNT_NO
            self.logger.info("실전투자 모드로 설정되었습니다.")
        else:
            # 모의투자 URL 하드코딩 (KIS_VIRTUAL_URL이 config에 없는 경우 대비)
            self.base_url = getattr(config, 'KIS_VIRTUAL_URL', "https://openapivts.koreainvestment.com:29443")
            self.app_key = config.KIS_VIRTUAL_APP_KEY
            self.app_secret = config.KIS_VIRTUAL_APP_SECRET
            self.account_no = config.KIS_VIRTUAL_ACCOUNT_NO
            self.logger.info(f"모의투자 모드로 설정되었습니다. URL: {self.base_url}")
        
        # 계좌번호 통합 처리 - account_no를 기본 속성으로 사용
        self.account_number = self.account_no
        self.cano = self.account_no
        
        # 상품 코드 설정 (주식: 01)
        self.product_code = "01"
        
        # 계좌번호 로깅
        logger.info(f"계좌번호 설정 완료 - account_no: {self.account_no}, cano: {self.cano}")
        
        self.approval_key = None
        self.access_token = None
        self.token_expired_at = None
        self.hashkey = None
        
        # API 요청 관련 설정
        self.max_api_retries = 3  # API 재시도 최대 횟수
        self.api_retry_delay = 60  # 모의투자 API 장애 시 대기 시간(초)
        
        # 주문 로깅을 위한 설정
        self.enable_detailed_logging = True  # 상세 로깅 활성화 여부
        self.log_directory = getattr(config, 'LOG_DIRECTORY', 'logs')  # 로그 디렉토리
        
        # TR ID 매핑 (실전투자/모의투자)
        self.tr_id_map = {
            "balance": {
                "real": "TTTC8434R",  # 실전투자 잔고 조회
                "virtual": "VTTC8434R"  # 모의투자 잔고 조회
            },
            "buy": {
                "real": "TTTC0802U",  # 실전투자 매수 주문
                "virtual": "VTTC0802U"  # 모의투자 매수 주문
            },
            "sell": {
                "real": "TTTC0801U",  # 실전투자 매도 주문
                "virtual": "VTTC0801U"  # 모의투자 매도 주문
            },
            "cancel": {
                "real": "TTTC0803U",  # 실전투자 정정취소 주문
                "virtual": "VTTC0803U"  # 모의투자 정정취소 주문
            },
            "order_status": {
                "real": "TTTC8036R",  # 실전투자 정정취소가능주문 조회
                "virtual": "VTTC8036R"  # 모의투자 정정취소가능주문 조회
            }
        }
        
    def _log_order_detail(self, order_type, order_data, response_data=None, success=False, error=None):
        """
        주문 세부 정보 로깅
        
        Args:
            order_type: 주문 유형 (매수/매도/취소)
            order_data: 주문 데이터
            response_data: 응답 데이터
            success: 성공 여부
            error: 오류 메시지
        """
        if not self.enable_detailed_logging:
            return
            
        try:
            # 현재 시간
            now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            
            # 주문 정보
            code = order_data.get('PDNO', '코드 없음')
            quantity = order_data.get('ORD_QTY', '0')
            price_str = order_data.get('ORD_UNPR', '0')
            order_div = "시장가" if order_data.get('ORD_DVSN', '') == "01" else "지정가"
            
            # 실제 주문 가격 처리
            price = 0
            try:
                price = int(price_str)
            except (ValueError, TypeError):
                price = 0
                
            # 시장가 주문인 경우 현재가 조회
            if order_div == "시장가" and price == 0:
                try:
                    current_price = self.get_current_price(code)
                    if current_price > 0:
                        price = current_price
                        self.logger.debug(f"시장가 주문의 표시 가격을 현재가({price:,}원)로 설정합니다.")
                except Exception as e:
                    self.logger.warning(f"시장가 주문의 현재가 조회 실패: {e}")
                    
            # 주문 체결 정보에서 가격 확인 (응답 데이터에 체결 가격이 있는 경우)
            if success and response_data:
                try:
                    # output 필드에서 체결 가격 정보 확인
                    output = response_data.get('output', {})
                    if isinstance(output, dict) and 'ODNO' in output:
                        # 체결 가격 정보가 있는지 확인 (필드명이 다를 수 있음)
                        for price_field in ['EXECPRC', 'EXEC_PRC', 'CTTR_PRPR', 'PRPR']:
                            if price_field in output and output.get(price_field):
                                try:
                                    exec_price = int(output.get(price_field))
                                    if exec_price > 0:
                                        price = exec_price
                                        self.logger.debug(f"응답 데이터에서 체결 가격({price:,}원)을 확인했습니다.")
                                        break
                                except (ValueError, TypeError):
                                    continue
                except Exception as e:
                    self.logger.warning(f"응답 데이터 처리 중 오류 발생: {e}")
                        
            # 응답 정보
            order_no = ""
            msg = ""
            if response_data:
                if isinstance(response_data, dict):
                    order_no = response_data.get('output', {}).get('ODNO', '')
                    rt_cd = response_data.get('rt_cd', '')
                    msg = response_data.get('msg1', '')
            
            # 로그 내용 구성
            trading_mode = "실전투자" if self.real_trading else "모의투자"
            log_msg = f"[{now}] [{trading_mode}] [{order_type}] "
            
            # 숫자 형식으로 가격 포맷팅 (천 단위 콤마 추가)
            try:
                price_formatted = f"{price:,}원"
            except (ValueError, TypeError):
                price_formatted = f"{price}원"
            
            if success:
                log_msg += f"성공 - 종목코드: {code}, 수량: {quantity}, 가격: {price_formatted}, 주문유형: {order_div}"
                if order_no:
                    log_msg += f", 주문번호: {order_no}"
            else:
                log_msg += f"실패 - 종목코드: {code}, 수량: {quantity}, 가격: {price_formatted}, 주문유형: {order_div}"
                if error:
                    log_msg += f", 오류: {error}"
                if msg:
                    log_msg += f", 메시지: {msg}"
            
            # 로그 기록 (콘솔과 파일에 동시 출력)
            logger.info(log_msg)
            
            # 로그 파일에 기록
            try:
                log_dir = Path(self.log_directory)
                log_dir.mkdir(exist_ok=True)
                
                # 로그 파일명 (날짜별)
                log_file = log_dir / f"order_log_{datetime.now(KST).strftime('%Y%m%d')}.log"
                
                # 로그 파일에 추가 모드로 기록
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(log_msg + "\n")
                    
                    # 응답 데이터 상세 기록
                    if response_data:
                        f.write(f"응답 데이터: {json.dumps(response_data, ensure_ascii=False, indent=2)}\n")
                    
                    # 구분선 추가
                    f.write("-" * 80 + "\n")
            except Exception as e:
                logger.error(f"로그 파일 기록 실패: {e}")
        
        except Exception as e:
            logger.error(f"주문 로깅 실패: {e}")

    def _get_tr_id(self, tr_type):
        """
        거래 유형에 따른 TR ID 반환
        
        Args:
            tr_type: 거래 유형 ('balance', 'buy', 'sell', 'cancel', 'order_status')
            
        Returns:
            str: TR ID
        """
        trading_mode = "real" if self.real_trading else "virtual"
        return self.tr_id_map.get(tr_type, {}).get(trading_mode, "")
        
    def connect(self):
        """
        한국투자증권 API 연결 (토큰 발급)
        """
        try:
            # 토큰 발급 URL
            url = urljoin(self.base_url, "oauth2/tokenP")
            
            # 요청 헤더
            headers = {
                "content-type": "application/json"
            }
            
            # 요청 바디
            body = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }
            
            # API 요청 전 로그
            logger.info(f"한국투자증권 API 토큰 발급 요청 - URL: {url}")

            # 재시도 로직 추가
            max_retries = 3
            retry_count = 0
            retry_delay = 5  # 초 단위 대기 시간
            
            while retry_count < max_retries:
                try:
                    # 토큰 발급 요청
                    response = requests.post(url, headers=headers, data=json.dumps(body))
                    response_data = response.json()
                    
                    if response.status_code == 200:
                        self.access_token = response_data.get('access_token')
                        expires_in = response_data.get('expires_in', 86400)  # 기본 유효기간: 1일
                        
                        # datetime 직접 사용 대신 time_utils 사용
                        current_time = get_current_time()
                        self.token_expired_at = current_time + timedelta(seconds=expires_in)
                        
                        self.connected = True
                        logger.info(f"한국투자증권 API 연결 성공. 토큰 만료시간: {self.token_expired_at}")
                        return True
                    else:
                        err_msg = response_data.get('error_description', '')
                        # 1분에 1회 요청 제한 오류인 경우
                        if "접근토큰 발급 잠시 후 다시 시도하세요" in err_msg:
                            retry_count += 1
                            wait_time = retry_delay * (2 ** retry_count)  # 지수 백오프
                            logger.warning(f"API 요청 제한 오류. {wait_time}초 후 재시도 ({retry_count}/{max_retries})... 오류: {err_msg}")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"한국투자증권 API 연결 실패: {err_msg}")
                            return False
                except Exception as req_err:
                    retry_count += 1
                    wait_time = retry_delay * (2 ** retry_count)
                    logger.error(f"API 요청 중 오류 발생: {req_err}. {wait_time}초 후 재시도 ({retry_count}/{max_retries})...")
                    time.sleep(wait_time)
            
            # 최대 재시도 횟수 초과
            logger.error(f"최대 재시도 횟수({max_retries})를 초과하여 API 연결에 실패했습니다.")
            return False
                
        except Exception as e:
            logger.error(f"한국투자증권 API 연결 실패: {e}")
            return False
            
    def disconnect(self):
        """
        API 연결 종료 (토큰 폐기)
        """
        self.connected = False
        self.access_token = None
        self.token_expired_at = None
        logger.info("한국투자증권 API 연결 종료")
        return True
        
    def _check_token(self):
        """토큰 유효성 검사 및 재발급"""
        if not self.access_token or not self.token_expired_at:
            return self.connect()
            
        # datetime 직접 사용 대신 time_utils 사용
        current_time = get_current_time()
        
        # 토큰 만료 10분 전에 재발급
        if current_time > self.token_expired_at - timedelta(minutes=10):
            logger.info("토큰 유효기간이 10분 이내로 남아 재발급합니다.")
            return self.connect()
            
        return True
        
    def _get_hashkey(self, data):
        """
        해시키 발급
        
        Args:
            data: 해시키를 발급받을 데이터
            
        Returns:
            str: 해시키
        """
        url = urljoin(self.base_url, "uapi/hashkey")
        
        headers = {
            "content-type": "application/json",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(data))
        
        if response.status_code == 200:
            return response.json()["HASH"]
        else:
            logger.error(f"해시키 발급 실패: {response.text}")
            return None
        
    def login(self, user_id=None, password=None, cert_password=None):
        """
        한국투자증권 로그인 (API 키로 로그인하므로 별도 로그인 불필요)
        
        Returns:
            bool: 연결 상태
        """
        # 토큰이 이미 발급되어 있는지 확인
        if not self._check_token():
            return False
            
        self.user_id = "API" # API 로그인은 ID가 없으므로 임의로 설정
        
        # 계좌 목록 가져와서 연결 확인
        accounts = self.get_account_list()
        
        if accounts:
            logger.info(f"한국투자증권 API 로그인 성공")
            return True
        else:
            logger.error("한국투자증권 API 로그인 실패")
            return False
    
    def get_account_list(self):
        """
        연결된 계좌 목록 조회
        
        Returns:
            list: 계좌 목록
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return []
            
        try:
            # 계좌 목록 조회 불가능한 경우 config에서 설정한 계좌 사용
            accounts = []
            
            if self.account_no:
                accounts = [self.account_no]
                
                # 기본 계좌 설정
                if accounts and not self.account_number:
                    self.account_number = accounts[0]
                    logger.info(f"기본 계좌 설정: {self.account_number}")
                    
            logger.info(f"계좌 목록: {accounts}")
            return accounts
            
        except Exception as e:
            logger.error(f"계좌 목록 조회 실패: {e}")
            return []
    
    def get_balance(self, force_refresh=False, timestamp=None):
        """
        계좌 잔고 조회
        
        Args:
            force_refresh (bool): 캐시된 데이터 무시하고 강제 새로고침
            timestamp (int): API 캐시 무효화를 위한 타임스탬프
            
        Returns:
            dict: 계좌 잔고 정보
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return {"예수금": 0, "출금가능금액": 0, "총평가금액": 0}
            
        try:
            # API 호출 속도 제한 준수
            ensure_api_rate_limit("get_balance", self.real_trading)
            
            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
            
            # 하드코딩된 TR ID를 대신 _get_tr_id 사용해 모드에 맞는 TR ID 가져오기
            tr_id = self._get_tr_id("balance")
            headers = self._get_headers(tr_id)
            
            # 캐시 무효화를 위한 타임스탬프 파라미터
            if timestamp is None:
                timestamp = int(time.time() * 1000)
            
            # API 요청 파라미터
            params = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "N",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "_ts": timestamp  # 캐시 무효화용 타임스탬프
            }
            
            # 강제 새로고침이 필요한 경우 추가 처리
            if force_refresh:
                # 헤더에 캐시 제어 관련 값 추가
                headers["Cache-Control"] = "no-cache, no-store"
                headers["Pragma"] = "no-cache"
                
                # 요청 파라미터에 임의 값 추가하여 캐시된 응답을 방지
                params["_nonce"] = str(uuid.uuid4())
                
                self.logger.debug("계좌 잔고 강제 새로고침 요청")
            
            response = requests.get(url, headers=headers, params=params)
            
            # API 응답 처리
            if response.status_code == 200:
                data = response.json()
                
                # API 응답 전체 로그에 출력 - INFO 레벨로 변경하여 항상 출력되게 함
                self.logger.info(f"계좌 잔고 API 응답 전체: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                # output2 필드 확인 - 있는 경우 별도로 출력
                if 'output2' in data:
                    self.logger.info(f"output2 데이터: {json.dumps(data['output2'], indent=2, ensure_ascii=False)}")
                else:
                    self.logger.info("output2 필드가 응답에 없습니다")
                
                # 오류 응답인 경우
                if data.get("rt_cd") != "0":
                    error_msg = data.get("msg_cd", "") + " " + data.get("msg1", "")
                    self.logger.error(f"잔고 조회 오류: {error_msg}")
                    
                    # 초당 거래건수 초과 에러인 경우 (EGW00201) 재시도
                    if data.get("msg_cd") == "EGW00201":
                        self.logger.warning("초당 거래건수 초과로 딜레이 후 재시도합니다.")
                        time.sleep(1.0)  # 1초 대기
                        return self.get_balance(force_refresh, timestamp)
                        
                    return {"error": error_msg}
                
                # 초기 account_info 설정
                account_info = {
                    "예수금": 0,
                    "D+2예수금": 0,
                    "출금가능금액": 0,
                    "주문가능금액": 0,
                    "총평가금액": 0,
                    "timestamp": timestamp
                }
                
                # 응답 데이터에서 잔고 정보 추출
                if data.get("output1") and len(data.get("output1")) > 0:
                    # 실전투자 또는 기존 구조
                    balance_output1 = data.get("output1", [])[0] if data.get("output1") else {}
                    
                    # 기존 파싱 로직
                    account_info["예수금"] = int(balance_output1.get("dnca_tot_amt", 0))
                    account_info["D+2예수금"] = int(balance_output1.get("d2_auto_rdpt_amt", 0))
                    account_info["출금가능금액"] = int(balance_output1.get("nxdy_excc_amt", 0))
                    account_info["주문가능금액"] = int(balance_output1.get("prvs_rcdl_excc_amt", 0))
                    account_info["총평가금액"] = int(balance_output1.get("tot_evlu_amt", 0))
                    
                # output2에서 추가 정보 파싱 (중요)
                if data.get("output2") and len(data.get("output2")) > 0:
                    balance_output2 = data.get("output2", [])[0]
                    
                    # output1에서 파싱된 데이터가 없거나 중요 필드가 0인 경우, output2에서 데이터 가져옴
                    if account_info["예수금"] == 0:
                        account_info["예수금"] = int(balance_output2.get("dnca_tot_amt", 0))
                    
                    if account_info["출금가능금액"] == 0:
                        account_info["출금가능금액"] = int(balance_output2.get("nxdy_excc_amt", 0))
                    
                    if account_info["주문가능금액"] == 0:
                        # 주문가능금액은 prvs_rcdl_excc_amt 필드에 있음
                        account_info["주문가능금액"] = int(balance_output2.get("prvs_rcdl_excc_amt", 0))
                    
                    if account_info["총평가금액"] == 0:
                        account_info["총평가금액"] = int(balance_output2.get("tot_evlu_amt", 0))
                    
                    # D+2예수금이 없으면 출금가능금액으로 대체
                    if account_info["D+2예수금"] == 0:
                        account_info["D+2예수금"] = account_info["출금가능금액"]
                
                # 잔고 상세 정보 로깅
                self.logger.info(f"계좌 잔고 조회 성공: 예수금 {account_info['예수금']:,}원, "
                               f"주문가능금액 {account_info['주문가능금액']:,}원, "
                               f"총평가금액 {account_info['총평가금액']:,}원")
                
                # 보유 종목 정보 처리
                stocks = []
                # 모의투자는 output2에 계좌 정보만 있고, 종목 정보는 별도 API를 통해 가져와야 할 수 있음
                # 따라서 보유 종목 정보는 별도로 처리하지 않고 빈 배열 반환
                
                account_info["stocks"] = stocks
                return account_info
            else:
                self.logger.error(f"잔고 조회 실패: HTTP {response.status_code} - {response.text}")
                return {"error": f"HTTP {response.status_code} - {response.text}"}
        
        except Exception as e:
            self.logger.exception(f"계좌 잔고 조회 중 예외 발생: {e}")
            return {"error": str(e)}
    
    def get_positions(self, account_number=None, force_refresh=False):
        """
        보유 종목 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            force_refresh: 강제 갱신 여부
            
        Returns:
            list: 보유 종목 목록
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return []
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return []
            
        try:
            # 주식 잔고 조회
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/inquire-balance")
            
            # TR ID 가져오기
            tr_id = self._get_tr_id("balance")
            
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": tr_id
            }
            
            # 모의투자 계좌번호는 8자리이므로 형식을 적절히 처리
            cano = account_number
            acnt_prdt_cd = "01"
            
            logger.info(f"보유 종목 조회 요청: {cano}-{acnt_prdt_cd}, force_refresh={force_refresh}")
            
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            
            # 강제 갱신 요청 시 타임스탬프 추가로 캐싱 방지
            if force_refresh:
                params["_ts"] = int(time.time() * 1000)
                headers["Cache-Control"] = "no-cache, no-store"
                headers["Pragma"] = "no-cache"
                logger.debug("강제 갱신 요청으로 캐시 무효화 헤더 추가")
            
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()
            
            # API 응답 저장
            self.store_api_response(response_data)
            
            logger.debug(f"보유 종목 API 응답 데이터: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                positions = []
                
                if 'output2' in response_data and response_data['output2']:
                    # 보유종목 데이터 처리
                    for item in response_data['output2']:
                        # 필요한 모든 가능한 필드명 미리 정의
                        position_info = {}
                        
                        # 1. 종목 식별 정보
                        for code_field in ['pdno', 'stock_code', 'stck_csmn', 'prdt_code', 'code', 'issue_code']:
                            if code_field in item and not position_info.get('종목코드'):
                                position_info['종목코드'] = item.get(code_field, '')
                                break
                        
                        for name_field in ['prdt_name', 'stock_name', 'hldg_stck_nmix', 'issue_name', 'name']:
                            if name_field in item and not position_info.get('종목명'):
                                position_info['종목명'] = item.get(name_field, '')
                                break
                        
                        # 2. 수량 및 단가 정보
                        for qty_field in ['hldg_qty', 'stck_qty', 'qty', 'nccs_qty']:
                            if qty_field in item and 'quantity' not in position_info:
                                try:
                                    position_info['quantity'] = int(float(item.get(qty_field, '0')))
                                    # 중요: 보유수량 필드를 명시적으로 추가
                                    position_info['보유수량'] = position_info['quantity']
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        for avg_price_field in ['pchs_avg_pric', 'avg_pric', 'pchs_prc', 'avg_urmoney']:
                            if avg_price_field in item and 'avg_price' not in position_info:
                                try:
                                    position_info['avg_price'] = int(float(item.get(avg_price_field, '0')))
                                    # 중요: 평균단가 필드를 명시적으로 추가
                                    position_info['평균단가'] = position_info['avg_price']
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        for curr_price_field in ['prpr', 'stck_prpr', 'now_pric', 'current_price']:
                            if curr_price_field in item and 'current_price' not in position_info:
                                try:
                                    position_info['current_price'] = int(float(item.get(curr_price_field, '0')))
                                    # 중요: 현재가 필드를 명시적으로 추가
                                    position_info['현재가'] = position_info['current_price']
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        # 3. 손익 정보
                        for eval_amt_field in ['evlu_amt', 'stck_evlu_amt', 'thdt_buy_amt', 'evalvalue']:
                            if eval_amt_field in item and 'eval_amount' not in position_info:
                                try:
                                    position_info['eval_amount'] = int(float(item.get(eval_amt_field, '0')))
                                    # 중요: 평가금액 필드를 명시적으로 추가
                                    position_info['평가금액'] = position_info['eval_amount']
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        for pnl_field in ['evlu_pfls_amt', 'evlu_pfls_rt', 'pft_rt', 'appre_rt']:
                            if pnl_field in item and 'pnl_amount' not in position_info:
                                try:
                                    position_info['pnl_amount'] = int(float(item.get(pnl_field, '0')))
                                    # 중요: 손익금액 필드를 명시적으로 추가
                                    position_info['손익금액'] = position_info['pnl_amount']
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        for pnl_rate_field in ['evlu_pfls_rt', 'pft_rt', 'appre_rt', 'return_rt']:
                            if pnl_rate_field in item and 'pnl_rate' not in position_info:
                                try:
                                    # 퍼센트(%) 값인 경우가 많으므로 그대로 저장
                                    position_info['pnl_rate'] = float(item.get(pnl_rate_field, '0').replace('%', '').strip())
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        # 4. 매수/매도 가능 수량
                        for sell_qty_field in ['sll_psbl_qty', 'sell_qty', 'ord_psbl_qty']:
                            if sell_qty_field in item and 'sellable_quantity' not in position_info:
                                try:
                                    position_info['sellable_quantity'] = int(float(item.get(sell_qty_field, '0')))
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        # 계산된 값들로 보정
                        if 'quantity' in position_info and 'current_price' in position_info and 'eval_amount' not in position_info:
                            position_info['eval_amount'] = position_info['quantity'] * position_info['current_price']
                            position_info['평가금액'] = position_info['eval_amount']
                        
                        if 'quantity' in position_info and 'avg_price' in position_info and 'current_price' in position_info:
                            if 'pnl_amount' not in position_info:
                                position_info['pnl_amount'] = (position_info['current_price'] - position_info['avg_price']) * position_info['quantity']
                                position_info['손익금액'] = position_info['pnl_amount']
                            
                            if 'pnl_rate' not in position_info and position_info['avg_price'] > 0:
                                position_info['pnl_rate'] = ((position_info['current_price'] - position_info['avg_price']) / position_info['avg_price']) * 100
                                position_info['손익률'] = position_info['pnl_rate']
                        
                        # 매도 가능 수량이 없으면 수량과 동일하게 설정
                        if 'quantity' in position_info and 'sellable_quantity' not in position_info:
                            position_info['sellable_quantity'] = position_info['quantity']
                        
                        # 모든 원본 데이터도 함께 저장 (향후 참조를 위해)
                        for key, value in item.items():
                            if key not in position_info:
                                position_info[key] = value
                        
                        # 필수 필드가 있는 경우에만 결과에 추가
                        if ('종목코드' in position_info or 'pdno' in position_info) and \
                           ('quantity' in position_info or '보유수량' in position_info or 'hldg_qty' in position_info) and \
                           position_info.get('quantity', 0) > 0:
                            
                            # 수량이 있으면 보유종목으로 간주하고 목록에 추가
                            positions.append(position_info)
                            logger.info(f"보유종목: {position_info['종목명']} ({position_info['종목코드']}), "
                                        f"수량: {position_info.get('quantity', 0):,}주, "
                                        f"평균단가: {position_info.get('avg_price', 0):,}원, "
                                        f"현재가: {position_info.get('current_price', 0):,}원, "
                                        f"평가금액: {position_info.get('eval_amount', 0):,}원, "
                                        f"손익률: {position_info.get('pnl_rate', 0):.2f}%")
                
                return positions
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"보유종목 조회 실패: [{err_code}] {err_msg}")
                return []
                
        except Exception as e:
            logger.error(f"보유종목 조회 실패: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def buy_stock(self, code, quantity, price=0, order_type='market', account_number=None):
        """
        주식 매수 주문
        
        Args:
            code: 종목 코드
            quantity: 수량
            price: 매수 가격
            order_type: 주문 유형 (market: 시장가, limit: 지정가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 매수 주문번호 (실패시 "")
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return ""
        
        # API 호출 속도 제한 준수
        ensure_api_rate_limit("buy_stock", self.real_trading)
        
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-cash")
            
            # 계좌번호 형식 처리 - 전달된 account_number 사용
            # 01: 상품코드 (01: 주식)
            cano = account_number
            acnt_prdt_cd = "01"
            
            logger.info(f"매수 주문 계좌번호: {cano}-{acnt_prdt_cd}")
            
            # 주문 유형 처리
            if order_type == 'market':
                # 시장가 주문
                order_division = "01"  # 시장가
            else:
                # 지정가 주문
                order_division = "00"  # 지정가
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 매수 주문 데이터
            body = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": order_division,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": str(int(price)) if price > 0 else "0"
            }
            
            # 해시키 생성
            hashkey = self._get_hashkey(body)
            if not hashkey:
                logger.error("해시키 생성 실패")
                return ""
            
            # TR ID 가져오기
            tr_id = self._get_tr_id("buy")
            
            # API 헤더
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "hashkey": hashkey
            }
            
            # API 요청 지연/실패에 대비한 재시도 로직
            retry_count = 0
            max_retries = self.max_api_retries
            
            while retry_count < max_retries:
                try:
                    # 주문 요청
                    start_time = time.time()
                    response = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
                    response_time = time.time() - start_time
                    
                    response_data = response.json()
                    
                    # 응답 시간 기록 (모의투자 API 지연 모니터링용)
                    logger.info(f"매수 주문 API 응답 시간: {response_time:.2f}초 (모의투자: {not self.real_trading})")
                    
                    if response.status_code == 200 and response_data.get('rt_cd') == '0':
                        order_number = response_data.get('output', {}).get('ODNO', '')
                        
                        # 상세 로그 기록
                        self._log_order_detail("매수", body, response_data, success=True)
                        
                        logger.info(f"매수 주문 전송 성공: {code}, {quantity}주, {price}원, 주문번호: {order_number}")
                        return order_number
                    else:
                        err_code = response_data.get('rt_cd')
                        err_msg = response_data.get('msg1')
                        
                        # 특정 오류 코드에 따른 재시도 여부 결정
                        if err_code in ['38', '111', '885', 'APBK1021'] and retry_count < max_retries - 1:
                            # 트래픽 제한, 일시적인 서비스 장애 등의 오류는 재시도
                            logger.warning(f"매수 주문 일시적 오류 발생 [{err_code}]: {err_msg}, 재시도 중...")
                            if not self._handle_api_delay(retry_count):
                                break
                            retry_count += 1
                            continue
                        
                        # 재시도해도 실패하는 경우 또는 재시도 불필요한 오류
                        self._log_order_detail("매수", body, response_data, success=False, error=f"[{err_code}] {err_msg}")
                        logger.error(f"매수 주문 전송 실패: [{err_code}] {err_msg}")
                        return ""
                        
                except requests.RequestException as e:
                    # 네트워크 오류, 타임아웃 등의 예외 처리
                    logger.error(f"매수 주문 요청 중 네트워크 오류: {e}")
                    
                    # 모의투자 환경에서만 더 긴 대기 시간 적용
                    if not self.real_trading and retry_count < max_retries - 1:
                        if not self._handle_api_delay(retry_count):
                            break
                        retry_count += 1
                        continue
                    else:
                        # 실전 투자에서는 짧은 대기 후 재시도
                        time.sleep(3)
                        retry_count += 1
                        continue
                        
                except Exception as e:
                    # 기타 예외 처리
                    logger.error(f"매수 주문 처리 중 예외 발생: {e}")
                    self._log_order_detail("매수", body, None, success=False, error=str(e))
                    return ""
            
            # 최대 재시도 횟수 초과
            logger.error(f"매수 주문 최대 재시도 횟수({max_retries}회) 초과로 실패")
            return ""
                
        except Exception as e:
            logger.error(f"매수 주문 실패: {e}")
            return ""
    
    def sell_stock(self, code, quantity, price=0, order_type='market', account_number=None):
        """
        주식 매도 주문
        
        Args:
            code: 종목 코드
            quantity: 수량
            price: 매도 가격
            order_type: 주문 유형 (market: 시장가, limit: 지정가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 매도 주문번호 (실패시 "")
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return ""
        
        # API 호출 속도 제한 준수
        ensure_api_rate_limit("sell_stock", self.real_trading)
        
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-cash")
            
            # 계좌번호 형식 처리 - 전달된 account_number 사용
            # 01: 상품코드 (01: 주식)
            cano = account_number
            acnt_prdt_cd = "01"
            
            logger.info(f"매도 주문 계좌번호: {cano}-{acnt_prdt_cd}")
            
            # 주문 유형 처리
            if order_type == 'market':
                # 시장가 주문
                order_division = "01"  # 시장가
            else:
                # 지정가 주문
                order_division = "00"  # 지정가
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 매도 주문 데이터
            body = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": order_division,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": str(int(price)) if price > 0 else "0"
            }
            
            # 해시키 생성
            hashkey = self._get_hashkey(body)
            if not hashkey:
                logger.error("해시키 생성 실패")
                return ""
            
            # TR ID 가져오기
            tr_id = self._get_tr_id("sell")
            
            # API 헤더
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "hashkey": hashkey
            }
            
            # API 요청 지연/실패에 대비한 재시도 로직
            retry_count = 0
            max_retries = self.max_api_retries
            
            while retry_count < max_retries:
                try:
                    # 주문 요청
                    start_time = time.time()
                    response = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
                    response_time = time.time() - start_time
                    
                    response_data = response.json()
                    
                    # 응답 시간 기록 (모의투자 API 지연 모니터링용)
                    logger.info(f"매도 주문 API 응답 시간: {response_time:.2f}초 (모의투자: {not self.real_trading})")
                    
                    if response.status_code == 200 and response_data.get('rt_cd') == '0':
                        order_number = response_data.get('output', {}).get('ODNO', '')
                        
                        # 상세 로그 기록
                        self._log_order_detail("매도", body, response_data, success=True)
                        
                        logger.info(f"매도 주문 전송 성공: {code}, {quantity}주, {price}원, 주문번호: {order_number}")
                        return order_number
                    else:
                        err_code = response_data.get('rt_cd')
                        err_msg = response_data.get('msg1')
                        
                        # 특정 오류 코드에 따른 재시도 여부 결정
                        if err_code in ['38', '111', '885', 'APBK1021'] and retry_count < max_retries - 1:
                            # 트래픽 제한, 일시적인 서비스 장애 등의 오류는 재시도
                            logger.warning(f"매도 주문 일시적 오류 발생 [{err_code}]: {err_msg}, 재시도 중...")
                            if not self._handle_api_delay(retry_count):
                                break
                            retry_count += 1
                            continue
                        
                        # 재시도해도 실패하는 경우 또는 재시도 불필요한 오류
                        self._log_order_detail("매도", body, response_data, success=False, error=f"[{err_code}] {err_msg}")
                        logger.error(f"매도 주문 전송 실패: [{err_code}] {err_msg}")
                        return ""
                        
                except requests.RequestException as e:
                    # 네트워크 오류, 타임아웃 등의 예외 처리
                    logger.error(f"매도 주문 요청 중 네트워크 오류: {e}")
                    
                    # 모의투자 환경에서만 더 긴 대기 시간 적용
                    if not self.real_trading and retry_count < max_retries - 1:
                        if not self._handle_api_delay(retry_count):
                            break
                        retry_count += 1
                        continue
                    else:
                        # 실전 투자에서는 짧은 대기 후 재시도
                        time.sleep(3)
                        retry_count += 1
                        continue
                        
                except Exception as e:
                    # 기타 예외 처리
                    logger.error(f"매도 주문 처리 중 예외 발생: {e}")
                    self._log_order_detail("매도", body, None, success=False, error=str(e))
                    return ""
            
            # 최대 재시도 횟수 초과
            logger.error(f"매도 주문 최대 재시도 횟수({max_retries}회) 초과로 실패")
            return ""
                
        except Exception as e:
            logger.error(f"매도 주문 실패: {e}")
            return ""
    
    def cancel_order(self, order_number, code, quantity=0, price=0, order_type='market', account_number=None):
        """
        주문 취소
        
        Args:
            order_number: 주문번호
            code: 종목코드
            quantity: 취소수량 (0이면 전체 취소)
            price: 가격 (시장가 주문인 경우 무시)
            order_type: 주문 유형 (market: 시장가, limit: 지정가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            bool: 취소 성공 여부
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return False
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return False
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-rvsecncl")
            
            # 계좌번호 형식 처리 (수정)
            cano = self.cano  # 계좌번호 앞부분
            acnt_prdt_cd = "01"  # 상품코드 (01: 주식)
            
            # 주문 유형 처리
            if order_type == 'market':
                # 시장가 주문
                order_division = "01"  # 시장가
            else:
                # 지정가 주문
                order_division = "00"  # 지정가
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 주문 취소 데이터
            body = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "KRX_FWDG_ORD_ORGNO": "",  # 한국거래소 전송 주문조직번호
                "ORGN_ODNO": order_number,  # 원주문번호
                "ORD_DVSN": order_division,
                "RVSE_CNCL_DVSN_CD": "02",  # 정정취소구분코드 (02: 취소)
                "ORD_QTY": str(quantity),
                "ORD_UNPR": str(int(price)) if price > 0 else "0",
                "QTY_ALL_ORD_YN": "Y" if quantity == 0 else "N"  # 잔량전부주문여부
            }
            
            # 해시키 생성
            hashkey = self._get_hashkey(body)
            if not hashkey:
                logger.error("해시키 생성 실패")
                return False
            
            # TR ID 가져오기
            tr_id = self._get_tr_id("cancel")
            
            # API 헤더
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "hashkey": hashkey
            }
            
            # 취소 요청
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                logger.info(f"주문 취소 요청 성공: 원주문번호 {order_number}")
                return True
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"주문 취소 요청 실패: [{err_code}] {err_msg}")
                return False
                
        except Exception as e:
            logger.error(f"주문 취소 요청 실패: {e}")
            return False
    
    def get_current_price(self, code):
        """
        현재가 조회
        
        Args:
            code: 종목 코드
            
        Returns:
            int: 현재가
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return 0
            
        try:
            # 현재가 조회 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/quotations/inquire-price")
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # API 헤더
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": "FHKST01010100"
            }
            
            # 요청 파라미터
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 시장분류코드(J: 주식)
                "FID_INPUT_ISCD": code  # 종목코드
            }
            
            # 요청 보내기
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                current_price = int(response_data.get('output', {}).get('stck_prpr', '0'))
                logger.info(f"현재가 조회 성공: {code}, {current_price}원")
                return current_price
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"현재가 조회 실패: [{err_code}] {err_msg}")
                return 0
                
        except Exception as e:
            logger.error(f"현재가 조회 실패: {e}")
            return 0
    
    def get_order_status(self, order_number, account_number=None):
        """
        주문 상태 조회
        
        Args:
            order_number: 주문번호
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            dict: 주문 상태 정보
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return {}
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return {}
            
        try:
            # API 호출 속도 제한 준수
            ensure_api_rate_limit("get_order_status", self.real_trading)
            
            # 주문 조회 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl")
            
            # TR ID 가져오기
            tr_id = self._get_tr_id("order_status")
            
            # API 헤더
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": tr_id
            }
            
            # 계좌번호와 상품코드를 분리
            # 예: 계좌번호가 "5015123456" 인 경우
            # CANO: "50151234" (앞 8자리)
            # ACNT_PRDT_CD: "01" (상품코드 - 주식은 01)
            
            # 먼저 계좌번호에 상품코드가 포함되어 있는지 확인
            if len(account_number) >= 10:
                cano = account_number[:-2]  # 계좌번호 앞 부분
                acnt_prdt_cd = account_number[-2:]  # 상품코드 (마지막 2자리)
            else:
                # 10자리 미만이면 상품코드는 기본 "01"로 설정
                cano = account_number
                acnt_prdt_cd = self.product_code
                
            # 로깅을 통해 계좌번호 처리 확인
            logger.debug(f"주문 상태 조회 - 계좌번호 분리: CANO={cano}, ACNT_PRDT_CD={acnt_prdt_cd}")
            
            # 요청 파라미터
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "INQR_DVSN_1": "0",
                "INQR_DVSN_2": "0"
            }
            
            # API 호출 전 전체 파라미터 로깅
            logger.debug(f"주문 상태 조회 요청 파라미터: {params}")
            
            # 요청 보내기
            response = requests.get(url, headers=headers, params=params)
            
            # 응답 상태 코드와 내용 로깅
            logger.debug(f"주문 상태 조회 응답 상태: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.debug(f"주문 상태 조회 응답 데이터: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
                
                if response_data.get('rt_cd') == '0':
                    order_info = {}
                    orders = response_data.get('output', [])
                    
                    # 주문번호로 일치하는 주문 찾기
                    for order in orders:
                        if order.get('odno') == order_number:
                            code = order.get('pdno', '')
                            name = order.get('prdt_name', '')
                            order_status = "접수완료" if order.get('rmn_qty', '0') == order.get('ord_qty', '0') else "일부체결"
                            order_quantity = int(order.get('ord_qty', '0'))
                            executed_quantity = order_quantity - int(order.get('rmn_qty', '0'))
                            remaining_quantity = int(order.get('rmn_qty', '0'))
                            order_price = int(order.get('ord_unpr', '0'))
                            
                            order_info = {
                                "주문번호": order_number,
                                "종목코드": code,
                                "종목명": name,
                                "주문상태": order_status,
                                "주문수량": order_quantity,
                                "체결수량": executed_quantity,
                                "미체결수량": remaining_quantity,
                                "주문가격": order_price
                            }
                            
                            logger.info(f"주문 상태 조회 성공: {order_info}")
                            return order_info
                    
                    logger.warning(f"해당 주문번호({order_number})의 주문 정보를 찾을 수 없습니다.")
                    return {}
                else:
                    err_code = response_data.get('rt_cd')
                    err_msg = response_data.get('msg1')
                    logger.error(f"주문 상태 조회 실패: [{err_code}] {err_msg}")
                    return {}
            else:
                logger.error(f"주문 상태 조회 실패: HTTP {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"주문 상태 조회 실패: {e}")
            logger.error(traceback.format_exc())  # 상세 에러 스택트레이스 출력
            return {}
            
    def switch_to_real(self):
        """실전투자로 전환"""
        if self.real_trading:
            logger.info("이미 실전투자 모드입니다.")
            return True
            
        logger.info("실전투자 모드로 전환합니다.")
        self.real_trading = True
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = self.config.KIS_APP_KEY
        self.app_secret = self.config.KIS_APP_SECRET
        self.account_no = self.config.KIS_ACCOUNT_NO
        self.account_number = self.account_no
        
        # 토큰 재발급
        self.disconnect()
        return self.connect()
        
    def switch_to_virtual(self):
        """모의투자로 전환"""
        if not self.real_trading:
            logger.info("이미 모의투자 모드입니다.")
            return True
            
        logger.info("모의투자 모드로 전환합니다.")
        self.real_trading = False
        self.base_url = self.config.KIS_VIRTUAL_URL
        self.app_key = self.config.KIS_VIRTUAL_APP_KEY
        self.app_secret = self.config.KIS_VIRTUAL_APP_SECRET
        self.account_no = self.config.KIS_VIRTUAL_ACCOUNT_NO
        self.account_number = self.account_no
        
        # 토큰 재발급
        self.disconnect()
        return self.connect()
        
    def get_trading_mode(self):
        """현재 거래 모드 반환"""
        return "실전투자" if self.real_trading else "모의투자"
    
    def buy(self, symbol, quantity, price=0, order_type='MARKET', market='KR'):
        """
        매수 주문 실행
        
        Args:
            symbol: 종목 코드
            quantity: 매수 수량
            price: 매수 희망 가격 (시장가 주문시 0)
            order_type: 주문 유형 ('MARKET': 시장가, 'LIMIT': 지정가)
            market: 시장 구분 ('KR': 국내, 'US': 미국)
            
        Returns:
            dict: 매수 주문 결과
        """
        try:
            # price가 None인 경우를 처리 - 시장가 주문이면 0으로, 지정가 주문이면 현재가 조회
            if price is None:
                if order_type.upper() == 'MARKET':
                    price = 0
                    logger.info("시장가 주문으로 price를 0으로 설정합니다.")
                else:
                    # 지정가 주문인데 가격이 없으면 현재가로 조회하여 설정
                    try:
                        price = self.get_current_price(symbol) or 0
                        logger.info(f"지정가 주문의 가격을 현재가 {price:,}원으로 설정합니다.")
                    except Exception as price_error:
                        logger.error(f"현재가 조회 실패, price를 0으로 설정: {price_error}")
                        price = 0
            
            # price가 정수형이 아닌 경우 정수로 변환
            if not isinstance(price, int) and price is not None:
                try:
                    price = int(price)
                except (ValueError, TypeError):
                    logger.error(f"유효하지 않은 가격 형식: {price}, 0으로 설정합니다.")
                    price = 0

            # 모의투자에서의 시장 제한 확인
            if not self.real_trading:
                # 미국 주식 거래 시도 시 명확한 오류 메시지 제공
                if market == 'US':
                    error_msg = "모의투자에서는 미국 주식 거래가 지원되지 않습니다. 실전투자 계좌에서만 미국 주식 거래가 가능합니다."
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
                
                # 모의투자에서 국내주식만 거래 가능하도록 제한 설정 확인
                if hasattr(self.config, 'VIRTUAL_TRADING_KR_ONLY') and self.config.VIRTUAL_TRADING_KR_ONLY and market != 'KR':
                    error_msg = "모의투자에서는 국내주식만 거래 가능합니다. 해외주식은 실전투자에서만 거래할 수 있습니다."
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
                
                # 허용된 시장 확인
                if hasattr(self.config, 'ALLOWED_VIRTUAL_MARKETS') and market not in self.config.ALLOWED_VIRTUAL_MARKETS:
                    error_msg = f"모의투자에서는 {market} 시장 거래가 허용되지 않습니다. 허용된 시장: {self.config.ALLOWED_VIRTUAL_MARKETS}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
            
            order_type_str = order_type.lower()
            
            # 종목코드 처리
            if market == 'KR':
                if not symbol.startswith('A'):
                    trade_symbol = 'A' + symbol
                else:
                    trade_symbol = symbol
            else:  # 미국 주식인 경우
                trade_symbol = symbol

            # 매수 전 보유 상태 확인
            old_positions = self.get_positions()
            old_quantity = 0
            old_avg_price = 0

            # 기존 보유 여부 및 수량/평단가 확인
            for pos in old_positions:
                if pos.get('종목코드', '').strip() == symbol.strip() or pos.get('종목코드', '').strip() == trade_symbol.strip():
                    old_quantity = pos.get('quantity', 0)
                    old_avg_price = pos.get('avg_price', 0)
                    logger.info(f"매수 전 보유 상태: {symbol}, 수량: {old_quantity}주, 평단가: {old_avg_price:,}원")
                    break

            # 매수 주문 실행
            order_number = self.buy_stock(
                trade_symbol, quantity, price, 
                'market' if order_type_str == 'market' else 'limit'
            )
            
            if order_number:
                logger.info(f"매수 주문 성공: {symbol}, {quantity}주, 주문번호: {order_number}")
                
                # 주문 결과 생성
                result = {
                    "success": True,
                    "order_no": order_number,
                    "message": f"매수 주문이 접수되었습니다. (주문번호: {order_number})"
                }
                
                # 계좌 잔고 업데이트
                account_balance = self.get_balance(force_refresh=True)
                deposit = account_balance.get('예수금', 0)
                total_eval = account_balance.get('총평가금액', 0)
                
                # 매수 후 보유 상태 확인 - 시간을 두고 API 호출
                time.sleep(1)
                new_positions = self.get_positions()
                new_quantity = 0
                new_avg_price = 0
                
                # 매수 후 보유량과 평단가 확인
                for pos in new_positions:
                    if pos.get('종목코드', '').strip() == symbol.strip() or pos.get('종목코드', '').strip() == trade_symbol.strip():
                        new_quantity = pos.get('quantity', 0)
                        new_avg_price = pos.get('avg_price', 0)
                        logger.info(f"매수 후 보유 상태: {symbol}, 수량: {new_quantity}주, 평단가: {new_avg_price:,}원")
                        break
                
                # 카카오톡 메시지 전송
                try:
                    from src.notification.kakao_sender import KakaoSender
                    
                    # config가 있으면 카카오톡 메시지 전송
                    if hasattr(self, 'config') and self.config:
                        # 카카오톡 메시지 전송 활성화 여부 확인
                        kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                        if kakao_enabled:
                            kakao_sender = KakaoSender(self.config)
                            
                            # 현재가 확인
                            current_price = 0
                            try:
                                current_price = self.get_current_price(symbol)
                            except:
                                # 현재가 조회 실패 시 price 값 사용
                                current_price = price if price > 0 else 0
                            
                            # 종목명 확인
                            stock_name = ""
                            if hasattr(self, 'get_stock_name'):
                                try:
                                    stock_name = self.get_stock_name(symbol)
                                except:
                                    pass
                            
                            # 카카오톡 메시지 내용 구성
                            message = f"💰 매수 주문 완료\n\n"
                            message += f"• 종목: {stock_name or symbol}\n"
                            message += f"• 수량: {quantity}주\n"
                            if current_price > 0:
                                message += f"• 가격: {current_price:,}원\n"
                            if price > 0 and order_type_str == 'limit':
                                message += f"• 지정가: {price:,}원\n"
                            message += f"• 주문번호: {order_number}\n"
                            message += f"• 시장: {'국내' if market == 'KR' else '미국'}\n"
                            message += f"• 모드: {'모의투자' if not self.real_trading else '실전투자'}\n"
                            # 계좌 잔고 정보 추가
                            message += f"• 계좌잔고: {deposit:,}원\n"
                            message += f"• 총평가금액: {total_eval:,}원"
                            
                            # 메시지 전송
                            kakao_sender.send_message(message)
                            logger.info("매수 주문 카카오톡 알림 전송 완료")
                except Exception as e:
                    logger.warning(f"카카오톡 알림 전송 중 오류 발생: {e}")
                
                # 매매 후 로직 처리 (예: 잔고 업데이트, 포지션 기록 등)
                try:
                    # 1. 강제 대기 - API 서버에서 주문 처리 시간 확보
                    time.sleep(1)
                    
                    # 2. 잔고 업데이트 확인
                    updated_balance = self.get_balance(force_refresh=True)
                    logger.info(f"매수 후 계좌 잔고: {updated_balance.get('예수금', 0):,}원")
                    
                    # 3. ChatGPT 분석기에게 매매 실행 결과 전달 (향후 확장을 위한 자리)
                    if hasattr(self.config, 'NOTIFY_CHATGPT') and self.config.NOTIFY_CHATGPT:
                        logger.info(f"ChatGPT에게 매매 실행 결과를 전달합니다: {symbol} 매수 완료")
                    
                except Exception as e:
                    logger.warning(f"매수 후 추가 로직 처리 중 오류 발생: {e}")
                
                return result
            else:
                logger.error(f"매수 주문 실패: {symbol}")
                result = {
                    "success": False,
                    "order_no": "",
                    "error": "매수 주문 처리 실패",
                    "message": "매수 주문을 처리할 수 없습니다."
                }
                
                # 카카오톡 오류 메시지 전송
                try:
                    from src.notification.kakao_sender import KakaoSender
                    
                    # config가 있으면 카카오톡 메시지 전송
                    if hasattr(self, 'config') and self.config:
                        # 카카오톡 메시지 전송 활성화 여부 확인
                        kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                        if kakao_enabled:
                            kakao_sender = KakaoSender(self.config)
                            kakao_sender.send_message(f"⚠️ 매수 주문 실패: {symbol}, {quantity}주\n\n실패 사유: 주문 처리 중 오류 발생")
                except Exception as e:
                    logger.warning(f"카카오톡 오류 알림 전송 중 오류 발생: {e}")
                
                return result
                
        except Exception as e:
            logger.error(f"매수 주문 중 예외 발생: {e}")
            result = {
                "success": False,
                "order_no": "",
                "error": str(e),
                "message": f"매수 주문 중 오류가 발생했습니다: {str(e)}"
            }
            
            # 카카오톡 오류 메시지 전송
            try:
                from src.notification.kakao_sender import KakaoSender
                
                # config가 있으면 카카오톡 메시지 전송
                if hasattr(self, 'config') and self.config:
                    # 카카오톡 메시지 전송 활성화 여부 확인
                    kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                    if kakao_enabled:
                        kakao_sender = KakaoSender(self.config)
                        kakao_sender.send_message(f"⚠️ 매수 주문 중 오류: {symbol}, {quantity}주\n\n오류 내용: {str(e)}")
            except Exception as notify_err:
                logger.warning(f"카카오톡 오류 알림 전송 중 오류 발생: {notify_err}")
            
            return result
    
    def sell(self, symbol, quantity, price=0, order_type='MARKET', market='KR'):
        """
        매도 주문 실행
        
        Args:
            symbol: 종목 코드
            quantity: 매도 수량
            price: 매도 희망 가격 (시장가 주문시 0)
            order_type: 주문 유형 ('MARKET': 시장가, 'LIMIT': 지정가)
            market: 시장 구분 ('KR': 국내, 'US': 미국)
            
        Returns:
            dict: 매도 주문 결과
        """
        try:
            # 모의투자에서의 시장 제한 확인
            if not self.real_trading:
                # 미국 주식 거래 시도 시 명확한 오류 메시지 제공
                if market == 'US':
                    error_msg = "모의투자에서는 미국 주식 거래가 지원되지 않습니다. 실전투자 계좌에서만 미국 주식 거래가 가능합니다."
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
                
                # 모의투자에서 국내주식만 거래 가능하도록 제한 설정 확인
                if hasattr(self.config, 'VIRTUAL_TRADING_KR_ONLY') and self.config.VIRTUAL_TRADING_KR_ONLY and market != 'KR':
                    error_msg = "모의투자에서는 국내주식만 거래 가능합니다. 해외주식은 실전투자에서만 거래할 수 있습니다."
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
                
                # 허용된 시장 확인
                if hasattr(self.config, 'ALLOWED_VIRTUAL_MARKETS') and market not in self.config.ALLOWED_VIRTUAL_MARKETS:
                    error_msg = f"모의투자에서는 {market} 시장 거래가 허용되지 않습니다. 허용된 시장: {self.config.ALLOWED_VIRTUAL_MARKETS}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "order_no": "",
                        "error": error_msg,
                        "message": error_msg
                    }
            
            order_type_str = order_type.lower()
            
            # 종목코드 처리
            if market == 'KR':
                if not symbol.startswith('A'):
                    trade_symbol = 'A' + symbol
                else:
                    trade_symbol = symbol
            else:  # 미국 주식인 경우
                trade_symbol = symbol

            # 매도 주문 실행
            order_number = self.sell_stock(
                trade_symbol, quantity, price, 
                'market' if order_type_str == 'market' else 'limit'
            )
            
            if order_number:
                logger.info(f"매도 주문 성공: {symbol}, {quantity}주, 주문번호: {order_number}")
                
                # 주문 결과 생성
                result = {
                    "success": True,
                    "order_no": order_number,
                    "message": f"매도 주문이 접수되었습니다. (주문번호: {order_number})"
                }
                
                # 카카오톡 메시지 전송
                try:
                    from src.notification.kakao_sender import KakaoSender
                    
                    # config가 있으면 카카오톡 메시지 전송
                    if hasattr(self, 'config') and self.config:
                        # 카카오톡 메시지 전송 활성화 여부 확인
                        kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                        if kakao_enabled:
                            kakao_sender = KakaoSender(self.config)
                            
                            # 현재가 확인
                            current_price = 0
                            try:
                                current_price = self.get_current_price(symbol)
                            except:
                                # 현재가 조회 실패 시 price 값 사용
                                current_price = price if price > 0 else 0
                            
                            # 종목명 확인
                            stock_name = ""
                            if hasattr(self, 'get_stock_name'):
                                try:
                                    stock_name = self.get_stock_name(symbol)
                                except:
                                    pass
                            
                            # 카카오톡 메시지 내용 구성
                            message = f"💸 매도 주문 완료\n\n"
                            message += f"• 종목: {stock_name or symbol}\n"
                            message += f"• 수량: {quantity}주\n"
                            if current_price > 0:
                                message += f"• 가격: {current_price:,}원\n"
                            if price > 0 and order_type_str == 'limit':
                                message += f"• 지정가: {price:,}원\n"
                            message += f"• 주문번호: {order_number}\n"
                            message += f"• 시장: {'국내' if market == 'KR' else '미국'}\n"
                            message += f"• 모드: {'모의투자' if not self.real_trading else '실전투자'}"
                            
                            # 메시지 전송
                            kakao_sender.send_message(message)
                            logger.info("매도 주문 카카오톡 알림 전송 완료")
                except Exception as e:
                    logger.warning(f"카카오톡 알림 전송 중 오류 발생: {e}")
                
                # 매매 후 로직 처리 (예: 잔고 업데이트, 포지션 기록 등)
                try:
                    # 1. 강제 대기 - API 서버에서 주문 처리 시간 확보
                    time.sleep(1)
                    
                    # 2. 잔고 업데이트 확인
                    updated_balance = self.get_balance(force_refresh=True)
                    logger.info(f"매도 후 계좌 잔고: {updated_balance.get('예수금', 0):,}원")
                    
                    # 3. 보유 종목 업데이트 확인
                    positions = self.get_positions()
                    has_position = False
                    for pos in positions:
                        if pos.get('종목코드', '').strip() == symbol.strip():
                            has_position = True
                            remaining_qty = pos.get('quantity', 0)
                            logger.info(f"매도 후 보유 수량: {remaining_qty}주 ({symbol})")
                            break
                    
                    if not has_position:
                        logger.info(f"매도 완료: {symbol} 종목을 모두 매도했습니다.")
                    
                    # 4. ChatGPT 분석기에게 매매 실행 결과 전달 (향후 확장을 위한 자리)
                    if hasattr(self.config, 'NOTIFY_CHATGPT') and self.config.NOTIFY_CHATGPT:
                        logger.info(f"ChatGPT에게 매매 실행 결과를 전달합니다: {symbol} 매도 완료")
                    
                except Exception as e:
                    logger.warning(f"매도 후 추가 로직 처리 중 오류 발생: {e}")
                
                return result
            else:
                logger.error(f"매도 주문 실패: {symbol}")
                result = {
                    "success": False,
                    "order_no": "",
                    "error": "매도 주문 처리 실패",
                    "message": "매도 주문을 처리할 수 없습니다."
                }
                
                # 카카오톡 오류 메시지 전송
                try:
                    from src.notification.kakao_sender import KakaoSender
                    
                    # config가 있으면 카카오톡 메시지 전송
                    if hasattr(self, 'config') and self.config:
                        # 카카오톡 메시지 전송 활성화 여부 확인
                        kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                        if kakao_enabled:
                            kakao_sender = KakaoSender(self.config)
                            kakao_sender.send_message(f"⚠️ 매도 주문 실패: {symbol}, {quantity}주\n\n실패 사유: 주문 처리 중 오류 발생")
                except Exception as e:
                    logger.warning(f"카카오톡 오류 알림 전송 중 오류 발생: {e}")
                
                return result
                
        except Exception as e:
            logger.error(f"매도 주문 중 예외 발생: {e}")
            result = {
                "success": False,
                "order_no": "",
                "error": str(e),
                "message": f"매도 주문 중 오류가 발생했습니다: {str(e)}"
            }
            
            # 카카오톡 오류 메시지 전송
            try:
                from src.notification.kakao_sender import KakaoSender
                
                # config가 있으면 카카오톡 메시지 전송
                if hasattr(self, 'config') and self.config:
                    # 카카오톡 메시지 전송 활성화 여부 확인
                    kakao_enabled = getattr(self.config, 'KAKAO_MSG_ENABLED', False)
                    if kakao_enabled:
                        kakao_sender = KakaoSender(self.config)
                        kakao_sender.send_message(f"⚠️ 매도 주문 중 오류: {symbol}, {quantity}주\n\n오류 내용: {str(e)}")
            except Exception as notify_err:
                logger.warning(f"카카오톡 오류 알림 전송 중 오류 발생: {notify_err}")
            
            return result
    
    def _get_headers(self, tr_id, content_type="application/json"):
        """
        API 요청용 헤더 생성
        
        Args:
            tr_id: 거래 ID
            content_type: 콘텐츠 타입 (기본값: "application/json")
            
        Returns:
            dict: 헤더 딕셔너리
        """
        headers = {
            "content-type": content_type,
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        return headers
        
    def _handle_api_delay(self, retry_count):
        """
        API 지연/실패에 대한 대기 처리
        
        Args:
            retry_count: 현재 재시도 횟수
            
        Returns:
            bool: 계속 재시도할지 여부
        """
        # 모의투자일 때만 더 긴 대기 시간 적용
        if not self.real_trading:
            # 재시도 횟수에 따라 대기 시간 증가
            wait_time = self.api_retry_delay * (retry_count + 1)
            logger.warning(f"모의투자 API 지연 발생, {wait_time}초 대기 후 재시도합니다...")
            time.sleep(wait_time)
            return True
        else:
            # 실전투자는 짧은 대기 후 재시도
            time.sleep(3)
            return True
    
    def execute_order(self, symbol, action, quantity, price=None, order_type=OrderType.LIMIT):
        """
        주식 매매 주문 실행
        
        Args:
            symbol: 종목 코드
            action: 매매 구분 (매수/매도)
            quantity: 주문 수량
            price: 주문 가격 (지정가 주문 시)
            order_type: 주문 유형 (시장가/지정가)
            
        Returns:
            dict: 주문 결과
        """
        # 실전투자 여부 확인
        is_real_trading = self.is_real_trading()
        
        # API 호출 속도 제한 적용 (실전투자는 딜레이 없음)
        ensure_api_rate_limit('order', is_real_trading)
        
        # 주문 유형에 따라 필요한 파라미터 설정
        if order_type == OrderType.MARKET:
            # 시장가 주문
            price_type = "01"  # 시장가
            price = 0  # 시장가는 가격 설정 불필요
        else:
            # 지정가 주문
            price_type = "00"  # 지정가
            if price is None:
                # 지정가 주문인데 가격이 없으면 현재가로 설정
                current_price = self.get_current_price(symbol)
                price = current_price
    
        # 헤더에 토큰 추가
        authorization = self._build_auth_header()
        
        # 주문 유형 설정 (매수/매도)
        if action == TradeAction.BUY:
            trade_type = "01"  # 매수
            self.logger.info(f"매수 주문 시작: {symbol}, 수량: {quantity}, 가격: {price:,}원, 주문유형: {'시장가' if order_type == OrderType.MARKET else '지정가'}")
        else:  # TradeAction.SELL
            trade_type = "02"  # 매도
            self.logger.info(f"매도 주문 시작: {symbol}, 수량: {quantity}, 가격: {price:,}원, 주문유형: {'시장가' if order_type == OrderType.MARKET else '지정가'}")

        # 주문 요청 데이터
        request_data = {
            "CANO": self.account_no[:8],  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": self.account_no[8:],  # 계좌번호 뒤 2자리 (상품코드)
            "PDNO": symbol,  # 종목코드
            "ORD_DVSN": price_type,  # 주문유형: 00-지정가, 01-시장가
            "ORD_QTY": str(quantity),  # 주문수량
            "ORD_UNPR": str(price) if price else "0",  # 주문단가
        }

        # API URL 설정
        base_url = self.virtual_url if self.use_virtual_url else self.real_url
        url = f"{base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        if action == TradeAction.BUY:
            # 매수
            request_data["BUY_TYPE"] = "00"  # 매수타입 (주식)
            query_path = "/uapi/domestic-stock/v1/trading/order-cash"
        else:
            # 매도
            request_data["SLL_TYPE"] = "00"  # 매도타입 (주식)
            query_path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        # 공통 헤더
        headers = {
            "Content-Type": "application/json",
            "authorization": authorization,
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "tr_id": "TTTC0802U" if action == TradeAction.BUY else "TTTC0801U"  # 실전환경: TTTC0802U(매수), TTTC0801U(매도)
        }
        
        # 모의투자 환경인 경우 tr_id 변경
        if self.use_virtual_url:
            headers["tr_id"] = "VTTC0802U" if action == TradeAction.BUY else "VTTC0801U"  # 모의투자: VTTC0802U(매수), VTTC0801U(매도)
            self.logger.debug("모의투자 환경으로 헤더 설정 변경")
            
        self.logger.debug(f"주문 요청 데이터: {request_data}")
        self.logger.debug(f"주문 요청 헤더: {headers}")
        
        try:
            # API 호출 (주문 실행)
            response = requests.post(url, headers=headers, data=json.dumps(request_data))
            self.logger.debug(f"주문 응답 상태코드: {response.status_code}")
            self.logger.debug(f"주문 응답 내용: {response.text}")
            
            if response.status_code != 200:
                self.logger.error(f"주문 실패 - 상태코드: {response.status_code}, 응답: {response.text}")
                return {
                    'success': False, 
                    'message': f"API 오류: {response.status_code}", 
                    'code': str(response.status_code)
                }
                
            # 응답 처리
            resp_data = response.json()
            
            # 응답 코드 확인
            if resp_data.get('rt_cd') == '0':  # 정상 처리
                order_no = resp_data.get('output', {}).get('ODNO', '')
                order_time = resp_data.get('output', {}).get('ORD_TMD', '')
                self.logger.info(f"주문 성공 - 주문번호: {order_no}, 주문시간: {order_time}")
                
                return {
                    'success': True, 
                    'message': '주문 성공', 
                    'order_no': order_no,
                    'order_time': order_time,
                    'status': 'EXECUTED'
                }
            else:
                # 실패 처리
                error_code = resp_data.get('rt_cd')
                error_msg = resp_data.get('msg1')
                self.logger.error(f"주문 실패 - 에러코드: {error_code}, 메시지: {error_msg}")
                return {
                    'success': False, 
                    'message': error_msg, 
                    'code': error_code,
                    'status': 'REJECTED'
                }
                
        except Exception as e:
            self.logger.error(f"주문 중 예외 발생: {str(e)}")
            return {'success': False, 'message': str(e), 'status': 'ERROR'}

    def is_real_trading(self):
        """
        현재 실전투자 모드인지 확인
        
        Returns:
            bool: 실전투자면 True, 모의투자면 False
        """
        return self.real_trading
    
    def get_headers(self, tr_id):
        """
        API 요청 헤더 생성
        
        Args:
            tr_id: TR ID
            
        Returns:
            dict: 헤더 정보
        """
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        return headers
        
    def check_error(self, result):
        """
        API 응답의 에러 확인
        
        Args:
            result: API 응답 결과
            
        Returns:
            bool: 에러 존재 여부
        """
        if not result:
            self.logger.error("API 응답이 비어 있습니다.")
            return True
            
        rt_cd = result.get('rt_cd')
        if rt_cd != '0':
            self.logger.error(f"API 오류 발생: [{rt_cd}] {result.get('msg1')}")
            return True
            
        return False
        
    def wait_for_order_execution(self, order_number, timeout=10):
        """
        주문 체결 대기 및 확인
        
        Args:
            order_number: 주문번호
            timeout: 타임아웃 시간(초)
            
        Returns:
            dict: 체결 결과 정보
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 주문 상태 확인
            try:
                order_status = self.get_order_status(order_number)
                
                if not order_status:
                    # 일시적인 조회 실패인 경우 재시도
                    self.logger.warning(f"주문 상태 조회 실패, 재시도 중... (주문번호: {order_number})")
                    time.sleep(1)
                    continue
                    
                # 주문 상태에 따라 처리
                if order_status.get('미체결수량', 0) == 0:
                    # 전체 체결된 경우
                    self.logger.info(f"주문 전체 체결 완료: {order_number}")
                    return {'status': 'FILLED', 'detail': order_status}
                
                # 일부만 체결된 경우
                if order_status.get('체결수량', 0) > 0:
                    self.logger.info(f"주문 일부 체결: {order_number}, 체결수량: {order_status.get('체결수량')}")
            except Exception as e:
                self.logger.error(f"주문 상태 조회 중 예외 발생: {e}")
                
            # 대기
            time.sleep(1)
            
        # 타임아웃 - 체결 완료되지 않음
        self.logger.warning(f"주문 체결 대기 타임아웃: {order_number}")
        try:
            last_status = self.get_order_status(order_number)
            return {'status': 'PARTIALLY_FILLED', 'detail': last_status}
        except Exception as e:
            self.logger.error(f"타임아웃 후 주문 상태 조회 실패: {e}")
            return {'status': 'UNKNOWN', 'detail': {'error': str(e)}}

    def get_account_balance(self):
        """계좌 잔고 조회 메서드
        
        Returns:
            dict: 계좌 잔고 정보를 담은 딕셔너리
        """
        try:
            # 재시도 로직 추가
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    # 기존 get_balance 메서드 활용
                    balance_info = self.get_balance(force_refresh=True)
                    if balance_info and "error" not in balance_info:
                        return balance_info
                    
                    self.logger.warning(f"계좌 잔고 조회 재시도 중... ({retry_count + 1}/{max_retries})")
                    retry_count += 1
                    time.sleep(2)
                except Exception as e:
                    self.logger.error(f"계좌 잔고 조회 시도 중 오류 발생: {e}")
                    retry_count += 1
                    time.sleep(2)
            
            self.logger.error("계좌 잔고 정보를 조회할 수 없습니다.")
            return {
                "총평가금액": 0,
                "예수금": 0,
                "D+2예수금": 0,
                "손익금액": 0,
                "손익률": 0.0
            }
        except Exception as e:
            self.logger.error(f"계좌 잔고 조회 중 오류 발생: {e}")
            return {
                "총평가금액": 0,
                "예수금": 0,
                "D+2예수금": 0,
                "손익금액": 0,
                "손익률": 0.0
            }