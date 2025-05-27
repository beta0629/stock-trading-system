"""
키움증권 API 연동 모듈
"""
import logging
import time
from pykiwoom.kiwoom import Kiwoom
import pywinauto
import os
import sys
import pandas as pd

from .broker_base import BrokerBase

# 로깅 설정
logger = logging.getLogger('KiwoomAPI')

class KiwoomAPI(BrokerBase):
    """키움증권 API 연동 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        super().__init__(config)
        self.api = None
        
    def connect(self):
        """
        키움증권 API 서버에 연결
        """
        try:
            self.api = Kiwoom()
            self.connected = True
            logger.info("키움증권 API 연결 성공")
            return True
        except Exception as e:
            logger.error(f"키움증권 API 연결 실패: {e}")
            return False
            
    def disconnect(self):
        """
        API 서버 연결 종료
        """
        self.connected = False
        self.api = None
        logger.info("키움증권 API 연결 종료")
        return True
        
    def login(self, user_id=None, password=None, cert_password=None):
        """
        키움증권 로그인 (자동 로그인 사용)
        
        Args:
            user_id: 사용자 ID (자동 로그인 사용 시 불필요)
            password: 비밀번호 (자동 로그인 사용 시 불필요)
            cert_password: 공인인증서 비밀번호 (자동 로그인 사용 시 불필요)
        
        Returns:
            bool: 로그인 성공 여부
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다. connect()를 먼저 호출하세요.")
            return False
            
        try:
            # 자동 로그인 사용 (OpenAPI 설정에서 자동 로그인 체크 필요)
            self.api.CommConnect()
            
            # 로그인 완료까지 대기
            for i in range(30):  # 최대 30초 대기
                if self.api.GetConnectState() == 1:  # 연결 성공
                    self.user_id = self.api.GetLoginInfo("USER_ID")
                    logger.info(f"키움증권 로그인 성공 (사용자: {self.user_id})")
                    return True
                time.sleep(1)
                
            logger.error("키움증권 로그인 시간 초과")
            return False
            
        except Exception as e:
            logger.error(f"키움증권 로그인 실패: {e}")
            return False
    
    def get_account_list(self):
        """
        연결된 계좌 목록 조회
        
        Returns:
            list: 계좌 목록
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return []
            
        try:
            accounts = self.api.GetLoginInfo("ACCNO").split(';')
            # 빈 문자열 제거
            accounts = [acc for acc in accounts if acc]
            logger.info(f"계좌 목록 조회 성공: {accounts}")
            
            # 기본 계좌 설정
            if accounts and not self.account_number:
                self.account_number = accounts[0]
                logger.info(f"기본 계좌 설정: {self.account_number}")
                
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
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return {}
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return {}
            
        try:
            # 예수금 조회
            self.api.SetInputValue("계좌번호", account_number)
            self.api.SetInputValue("비밀번호", "")  # 공백 입력시 저장된 비밀번호 사용
            self.api.CommRqData("예수금조회", "opw00001", 0, "0101")
            
            # 조회 결과 대기
            time.sleep(0.5)
            
            # 예수금 데이터 추출
            deposit = self.api.GetCommData("opw00001", "예수금", 0, "")
            available = self.api.GetCommData("opw00001", "출금가능금액", 0, "")
            
            balance_info = {
                "예수금": int(deposit.strip()),
                "출금가능금액": int(available.strip())
            }
            
            logger.info(f"계좌 잔고 조회 성공: {balance_info}")
            return balance_info
            
        except Exception as e:
            logger.error(f"계좌 잔고 조회 실패: {e}")
            return {}
    
    def get_positions(self, account_number=None):
        """
        보유 주식 현황 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            list: 보유 주식 목록
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return []
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return []
            
        try:
            # 계좌 평가 잔고 요청
            self.api.SetInputValue("계좌번호", account_number)
            self.api.SetInputValue("비밀번호", "")  # 공백 입력시 저장된 비밀번호 사용
            self.api.CommRqData("계좌평가잔고", "opw00018", 0, "0101")
            
            # 조회 결과 대기
            time.sleep(0.5)
            
            # 종목 수 확인
            count = int(self.api.GetRepeatCnt("opw00018", "계좌평가잔고"))
            positions = []
            
            # 보유 종목 정보 추출
            for i in range(count):
                code = self.api.GetCommData("opw00018", "종목코드", i, "").strip()
                name = self.api.GetCommData("opw00018", "종목명", i, "").strip()
                quantity = int(self.api.GetCommData("opw00018", "보유수량", i, "").strip())
                purchase_price = int(self.api.GetCommData("opw00018", "평균단가", i, "").strip())
                current_price = int(self.api.GetCommData("opw00018", "현재가", i, "").strip())
                eval_amount = int(self.api.GetCommData("opw00018", "평가금액", i, "").strip())
                profit_loss = int(self.api.GetCommData("opw00018", "손익금액", i, "").strip())
                
                positions.append({
                    "종목코드": code,
                    "종목명": name,
                    "보유수량": quantity,
                    "평균단가": purchase_price,
                    "현재가": current_price,
                    "평가금액": eval_amount,
                    "손익금액": profit_loss
                })
                
            logger.info(f"보유 주식 현황 조회 성공: {len(positions)}종목")
            return positions
            
        except Exception as e:
            logger.error(f"보유 주식 현황 조회 실패: {e}")
            return []
    
    def buy_stock(self, code, quantity, price=0, price_type='limit', account_number=None):
        """
        주식 매수
        
        Args:
            code: 종목 코드 (앞의 'A' 포함)
            quantity: 수량
            price: 가격 (시장가의 경우 0)
            price_type: 가격 유형 ('limit': 지정가, 'market': 시장가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 주문번호
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        # 종목 코드에 'A' 제거 (키움 API는 종목 코드만 사용)
        if code.startswith('A'):
            code = code[1:]
            
        try:
            # 주문 유형 설정
            order_type = 1  # 매수
            hoga_type = 0 if price_type == 'market' else 1  # 시장가(0), 지정가(1)
            
            # 주문 요청
            result = self.api.SendOrder("매수주문", "0101", account_number, order_type, code, quantity, price, hoga_type, "")
            
            if result == 0:
                logger.info(f"매수 주문 전송 성공: {code}, {quantity}주, {price}원")
                
                # 주문번호 조회 (실제로는 TraceHandler를 구현하여 OnReceiveChejanData 이벤트로 처리해야 함)
                # 여기서는 간단히 현재 시간을 주문번호로 사용
                order_number = str(int(time.time()))
                logger.info(f"주문번호: {order_number}")
                return order_number
            else:
                logger.error(f"매수 주문 전송 실패: {result}")
                return ""
                
        except Exception as e:
            logger.error(f"매수 주문 실패: {e}")
            return ""
    
    def sell_stock(self, code, quantity, price=0, price_type='limit', account_number=None):
        """
        주식 매도
        
        Args:
            code: 종목 코드 (앞의 'A' 포함)
            quantity: 수량
            price: 가격 (시장가의 경우 0)
            price_type: 가격 유형 ('limit': 지정가, 'market': 시장가)
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 주문번호
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        # 종목 코드에 'A' 제거 (키움 API는 종목 코드만 사용)
        if code.startswith('A'):
            code = code[1:]
            
        try:
            # 주문 유형 설정
            order_type = 2  # 매도
            hoga_type = 0 if price_type == 'market' else 1  # 시장가(0), 지정가(1)
            
            # 주문 요청
            result = self.api.SendOrder("매도주문", "0101", account_number, order_type, code, quantity, price, hoga_type, "")
            
            if result == 0:
                logger.info(f"매도 주문 전송 성공: {code}, {quantity}주, {price}원")
                
                # 주문번호 조회 (실제로는 TraceHandler를 구현하여 OnReceiveChejanData 이벤트로 처리해야 함)
                # 여기서는 간단히 현재 시간을 주문번호로 사용
                order_number = str(int(time.time()))
                logger.info(f"주문번호: {order_number}")
                return order_number
            else:
                logger.error(f"매도 주문 전송 실패: {result}")
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
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return ""
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return ""
            
        # 종목 코드에 'A' 제거 (키움 API는 종목 코드만 사용)
        if code.startswith('A'):
            code = code[1:]
            
        try:
            # 주문 유형 설정
            order_type = 3  # 취소
            
            # 주문 요청
            result = self.api.SendOrder("주문취소", "0101", account_number, order_type, code, quantity, 0, 0, order_number)
            
            if result == 0:
                logger.info(f"주문 취소 전송 성공: {order_number}, {code}, {quantity}주")
                
                # 취소 주문번호
                cancel_order_number = str(int(time.time()))
                logger.info(f"취소 주문번호: {cancel_order_number}")
                return cancel_order_number
            else:
                logger.error(f"주문 취소 전송 실패: {result}")
                return ""
                
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return ""
    
    def get_current_price(self, code):
        """
        현재가 조회
        
        Args:
            code: 종목 코드 (앞의 'A' 포함)
            
        Returns:
            int: 현재가
        """
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return 0
            
        # 종목 코드에 'A' 제거 (키움 API는 종목 코드만 사용)
        if code.startswith('A'):
            code = code[1:]
            
        try:
            # TR 요청
            self.api.SetInputValue("종목코드", code)
            self.api.CommRqData("현재가조회", "opt10001", 0, "0101")
            
            # 조회 결과 대기
            time.sleep(0.5)
            
            # 현재가 데이터 추출
            price = int(self.api.GetCommData("opt10001", "현재가", 0, "").strip())
            logger.info(f"현재가 조회 성공: {code}, {price}원")
            return abs(price)  # 음수인 경우 절대값 반환
            
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
        if not self.connected or self.api is None:
            logger.error("API가 연결되지 않았습니다.")
            return {}
            
        if account_number is None:
            account_number = self.account_number
            
        if not account_number:
            logger.error("계좌번호가 설정되지 않았습니다.")
            return {}
            
        try:
            # 미체결 주문 조회
            self.api.SetInputValue("계좌번호", account_number)
            self.api.SetInputValue("전체종목구분", "0")  # 0:전체, 1:종목
            self.api.SetInputValue("매매구분", "0")  # 0:전체, 1:매도, 2:매수
            self.api.SetInputValue("체결구분", "1")  # 0:전체, 1:미체결, 2:체결
            self.api.CommRqData("실시간미체결요청", "opt10075", 0, "0101")
            
            # 조회 결과 대기
            time.sleep(0.5)
            
            # 미체결 주문 수
            count = int(self.api.GetRepeatCnt("opt10075", "실시간미체결"))
            
            # 주문 정보 검색
            for i in range(count):
                curr_order_number = self.api.GetCommData("opt10075", "주문번호", i, "").strip()
                
                if curr_order_number == order_number:
                    code = self.api.GetCommData("opt10075", "종목코드", i, "").strip()
                    name = self.api.GetCommData("opt10075", "종목명", i, "").strip()
                    order_status = self.api.GetCommData("opt10075", "주문상태", i, "").strip()
                    order_quantity = int(self.api.GetCommData("opt10075", "주문수량", i, "").strip())
                    executed_quantity = int(self.api.GetCommData("opt10075", "체결수량", i, "").strip())
                    remaining_quantity = int(self.api.GetCommData("opt10075", "미체결수량", i, "").strip())
                    order_price = int(self.api.GetCommData("opt10075", "주문가격", i, "").strip())
                    
                    order_info = {
                        "주문번호": curr_order_number,
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
            
        except Exception as e:
            logger.error(f"주문 상태 조회 실패: {e}")
            return {}