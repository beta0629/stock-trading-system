"""
한국투자증권 API 연동 모듈
"""
import logging
import time
import requests
import json
import datetime
import hashlib
import jwt  # PyJWT 라이브러리 필요
from urllib.parse import urljoin, unquote
import pandas as pd

from .broker_base import BrokerBase

# 로깅 설정
logger = logging.getLogger('KISAPI')

class KISAPI(BrokerBase):
    """한국투자증권 API 연동 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        super().__init__(config)
        # 실전투자 여부 확인
        self.real_trading = config.KIS_REAL_TRADING
        
        # 실전/모의투자에 따른 설정
        if self.real_trading:
            self.base_url = "https://openapi.koreainvestment.com:9443"
            self.app_key = config.KIS_APP_KEY
            self.app_secret = config.KIS_APP_SECRET
            self.account_no = config.KIS_ACCOUNT_NO
            logger.info("실전투자 모드로 설정되었습니다.")
        else:
            self.base_url = config.KIS_VIRTUAL_URL
            self.app_key = config.KIS_VIRTUAL_APP_KEY
            self.app_secret = config.KIS_VIRTUAL_APP_SECRET
            self.account_no = config.KIS_VIRTUAL_ACCOUNT_NO
            logger.info("모의투자 모드로 설정되었습니다.")
        
        # 계좌번호 초기화
        self.account_number = self.account_no
        
        # 계좌번호 형식 처리 (수정)
        self.cano = self.account_no  # 전체 계좌번호 (모든 자리)
        
        # 미국 주식 계좌의 경우 첫 자리가 다를 수 있으므로 로깅으로 확인
        logger.info(f"계좌번호: {self.cano}")
        
        self.approval_key = None
        self.access_token = None
        self.token_expired_at = None
        self.hashkey = None
        
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
            url = urljoin(self.base_url, "oauth2/tokenP")
            
            # 필수 설정값 확인
            if not self.app_key or not self.app_secret:
                logger.error("APP_KEY와 APP_SECRET이 설정되지 않았습니다.")
                return False
                
            headers = {
                "content-type": "application/json"
            }
            
            body = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }
            
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response_data = response.json()
            
            if response.status_code == 200:
                self.access_token = response_data.get('access_token')
                expires_in = response_data.get('expires_in', 86400)  # 기본 유효기간: 1일
                self.token_expired_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                self.connected = True
                logger.info(f"한국투자증권 API 연결 성공. 토큰 만료시간: {self.token_expired_at}")
                return True
            else:
                logger.error(f"한국투자증권 API 연결 실패: {response_data.get('error_description', '')}")
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
            
        # 토큰 만료 10분 전에 재발급
        if datetime.datetime.now() > self.token_expired_at - datetime.timedelta(minutes=10):
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
    
    def get_balance(self, account_number=None):
        """
        계좌 잔고 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            dict: 계좌 잔고 정보
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
            # 계좌번호가 8자리인 경우, 앞 8자리를 CANO로, "01"을 ACNT_PRDT_CD로 설정
            cano = account_number
            acnt_prdt_cd = "01"
            
            logger.info(f"계좌 조회 요청: {cano}-{acnt_prdt_cd}")
            
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
            
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                # output1에 데이터가 있는지 확인
                if 'output1' in response_data and response_data['output1']:
                    data = response_data.get('output1', [{}])[0]
                    
                    # 예수금 정보
                    balance_info = {
                        "예수금": int(data.get('dnca_tot_amt', '0')),
                        "출금가능금액": int(data.get('magt_rt_amt', '0'))
                    }
                    
                    logger.info(f"계좌 잔고 조회 성공: {balance_info}")
                    return balance_info
                else:
                    # output1이 없는 경우 기본값 반환
                    logger.warning("계좌 잔고 정보가 없습니다. 기본값 반환")
                    return {"예수금": 0, "출금가능금액": 0}
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"계좌 잔고 조회 실패: [{err_code}] {err_msg}")
                return {"예수금": 0, "출금가능금액": 0}
                
        except Exception as e:
            logger.error(f"계좌 잔고 조회 실패: {e}")
            return {"예수금": 0, "출금가능금액": 0}
    
    def get_positions(self, account_number=None):
        """
        보유 주식 현황 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            list: 보유 주식 목록
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
            # 계좌번호가 8자리인 경우, 앞 8자리를 CANO로, "01"을 ACNT_PRDT_CD로 설정
            cano = account_number
            acnt_prdt_cd = "01"
            
            logger.info(f"보유 주식 조회 요청: {cano}-{acnt_prdt_cd}")
            
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
            
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                positions = []
                # output2에 데이터가 있는지 확인
                stock_list = response_data.get('output2', [])
                
                # 디버깅용 로그 추가
                logger.debug(f"API 응답 데이터: {response_data}")
                
                for stock in stock_list:
                    try:
                        code = stock.get('pdno', '')
                        name = stock.get('prdt_name', '')
                        quantity = int(stock.get('hldg_qty', '0'))
                        purchase_price = int(float(stock.get('pchs_avg_pric', '0')))
                        current_price = int(float(stock.get('prpr', '0')))
                        eval_amount = int(float(stock.get('evlu_amt', '0')))
                        profit_loss = int(float(stock.get('evlu_pfls_amt', '0')))
                        
                        # 0으로 나누는 오류 방지
                        if purchase_price <= 0:
                            purchase_price = 1  # 0 대신 1로 설정
                        
                        positions.append({
                            "종목코드": code,
                            "종목명": name,
                            "보유수량": quantity,
                            "평균단가": purchase_price,
                            "현재가": current_price,
                            "평가금액": eval_amount,
                            "손익금액": profit_loss
                        })
                    except Exception as stock_e:
                        logger.error(f"종목 정보 처리 중 오류: {stock_e}, 데이터: {stock}")
                        continue
                
                logger.info(f"보유 주식 현황 조회 성공: {len(positions)}종목")
                return positions
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"보유 주식 현황 조회 실패: [{err_code}] {err_msg}")
                return []
                
        except Exception as e:
            logger.error(f"보유 주식 현황 조회 실패: {e}")
            return []
    
    def buy_stock(self, code, quantity, price=0, price_type='limit', account_number=None):
        """
        주식 매수
        
        Args:
            code: 종목 코드
            quantity: 수량
            price: 가격 (시장가의 경우 0)
            price_type: 가격 유형 ('limit': 지정가, 'market': 시장가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 주문번호
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-cash")
            
            # 주문 타입 설정
            order_type = "00" if price_type == 'limit' else "01"  # 00: 지정가, 01: 시장가
            
            # 8자리 계좌번호 형식으로 변환
            account_no_prefix = account_number[:3]
            account_no_postfix = account_number[3:]
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 매수 주문 데이터
            body = {
                "CANO": account_no_prefix,
                "ACNT_PRDT_CD": account_no_postfix,
                "PDNO": code,
                "ORD_DVSN": order_type,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0" if price_type == 'market' else str(price)
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
            
            # 주문 요청
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                order_number = response_data.get('output', {}).get('ODNO', '')
                logger.info(f"매수 주문 전송 성공: {code}, {quantity}주, {price}원, 주문번호: {order_number}")
                return order_number
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"매수 주문 전송 실패: [{err_code}] {err_msg}")
                return ""
                
        except Exception as e:
            logger.error(f"매수 주문 실패: {e}")
            return ""
    
    def sell_stock(self, code, quantity, price=0, price_type='limit', account_number=None):
        """
        주식 매도
        
        Args:
            code: 종목 코드
            quantity: 수량
            price: 가격 (시장가의 경우 0)
            price_type: 가격 유형 ('limit': 지정가, 'market': 시장가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 주문번호
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-cash")
            
            # 주문 타입 설정
            order_type = "00" if price_type == 'limit' else "01"  # 00: 지정가, 01: 시장가
            
            # 8자리 계좌번호 형식으로 변환
            account_no_prefix = account_number[:3]
            account_no_postfix = account_number[3:]
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 매도 주문 데이터
            body = {
                "CANO": account_no_prefix,
                "ACNT_PRDT_CD": account_no_postfix,
                "PDNO": code,
                "ORD_DVSN": order_type,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0" if price_type == 'market' else str(price)
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
            
            # 주문 요청
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                order_number = response_data.get('output', {}).get('ODNO', '')
                logger.info(f"매도 주문 전송 성공: {code}, {quantity}주, {price}원, 주문번호: {order_number}")
                return order_number
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"매도 주문 전송 실패: [{err_code}] {err_msg}")
                return ""
                
        except Exception as e:
            logger.error(f"매도 주문 실패: {e}")
            return ""
    
    def cancel_order(self, order_number, code, quantity, account_number=None):
        """
        주문 취소
        
        Args:
            order_number: 원래 주문번호
            code: 종목 코드
            quantity: 취소할 수량
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 취소 주문번호
        """
        if not self._check_token():
            logger.error("API 연결이 되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        try:
            # 주문 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/order-rvsecncl")
            
            # 8자리 계좌번호 형식으로 변환
            account_no_prefix = account_number[:3]
            account_no_postfix = account_number[3:]
            
            # 종목코드에서 'A' 제거
            if code.startswith('A'):
                code = code[1:]
                
            # 취소 주문 데이터
            body = {
                "CANO": account_no_prefix,
                "ACNT_PRDT_CD": account_no_postfix,
                "KRX_FWDG_ORD_ORGNO": "",  # 한국투자증권 시스템에서 지정
                "ORGN_ODNO": order_number,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",  # 01: 정정, 02: 취소
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y"  # Y: 잔량 전부 취소, N: 일부 취소
            }
            
            # 해시키 생성
            hashkey = self._get_hashkey(body)
            if not hashkey:
                logger.error("해시키 생성 실패")
                return ""
            
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
            
            # 주문 요청
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
                cancel_order_number = response_data.get('output', {}).get('ODNO', '')
                logger.info(f"주문 취소 전송 성공: {order_number}, {code}, {quantity}주, 취소주문번호: {cancel_order_number}")
                return cancel_order_number
            else:
                err_code = response_data.get('rt_cd')
                err_msg = response_data.get('msg1')
                logger.error(f"주문 취소 전송 실패: [{err_code}] {err_msg}")
                return ""
                
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return ""
    
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
            # 주문 조회 URL
            url = urljoin(self.base_url, "uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl")
            
            # 8자리 계좌번호 형식으로 변환
            account_no_prefix = account_number[:3]
            account_no_postfix = account_number[3:]
            
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
            
            # 요청 파라미터
            params = {
                "CANO": account_no_prefix,
                "ACNT_PRDT_CD": account_no_postfix,
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "INQR_DVSN_1": "0",
                "INQR_DVSN_2": "0"
            }
            
            # 요청 보내기
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('rt_cd') == '0':
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
                
        except Exception as e:
            logger.error(f"주문 상태 조회 실패: {e}")
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