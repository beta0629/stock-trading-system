"""
증권사 API 기본 클래스 모듈
"""
import abc
import logging

# 로깅 설정
logger = logging.getLogger('BrokerAPI')

class BrokerBase(abc.ABC):
    """
    증권사 API 추상 기본 클래스
    모든 증권사 API 클래스는 이 클래스를 상속해야 함
    """
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        self.connected = False
        self.account_number = None
        self.user_id = None
        self.last_api_response = None  # 마지막 API 응답 저장 필드 추가
        logger.info(f"{self.__class__.__name__} 초기화")
    
    def store_api_response(self, response):
        """
        API 호출 응답 저장
        
        Args:
            response: API 응답 데이터
        """
        self.last_api_response = response
        return response
    
    def get_last_api_response(self):
        """
        마지막으로 저장된 API 응답 반환
        
        Returns:
            dict: 마지막 API 응답 또는 None
        """
        return self.last_api_response
    
    @abc.abstractmethod
    def connect(self):
        """
        API 서버에 연결
        """
        pass
        
    @abc.abstractmethod
    def disconnect(self):
        """
        API 서버 연결 종료
        """
        pass
    
    @abc.abstractmethod
    def login(self, user_id, password, cert_password=None):
        """
        증권사 계정으로 로그인
        
        Args:
            user_id: 사용자 ID
            password: 비밀번호
            cert_password: 공인인증서 비밀번호 (필요한 경우)
        
        Returns:
            bool: 로그인 성공 여부
        """
        pass
    
    @abc.abstractmethod
    def get_account_list(self):
        """
        연결된 계좌 목록 조회
        
        Returns:
            list: 계좌 목록
        """
        pass
    
    @abc.abstractmethod
    def get_balance(self, account_number=None):
        """
        계좌 잔고 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
        
        Returns:
            dict: 계좌 잔고 정보
        """
        pass
    
    @abc.abstractmethod
    def get_positions(self, account_number=None):
        """
        보유 주식 현황 조회
        
        Args:
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
        
        Returns:
            list: 보유 주식 목록
        """
        pass
    
    @abc.abstractmethod
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
        pass
    
    @abc.abstractmethod
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
        pass
    
    @abc.abstractmethod
    def cancel_order(self, order_number, code, quantity, account_number=None):
        """
        주문 취소
        
        Args:
            order_number: 주문번호
            code: 종목 코드
            quantity: 취소할 수량
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
            
        Returns:
            str: 취소 주문번호
        """
        pass
    
    @abc.abstractmethod
    def get_current_price(self, code):
        """
        현재가 조회
        
        Args:
            code: 종목 코드
        
        Returns:
            int: 현재가
        """
        pass
    
    @abc.abstractmethod
    def get_order_status(self, order_number, account_number=None):
        """
        주문 상태 조회
        
        Args:
            order_number: 주문번호
            account_number: 계좌번호 (None인 경우 기본 계좌 사용)
        
        Returns:
            dict: 주문 상태 정보
        """
        pass