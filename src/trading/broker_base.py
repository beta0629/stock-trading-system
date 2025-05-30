"""
증권사 API 기본 클래스 모듈
"""
import abc
import logging
import time
import traceback
from datetime import datetime

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
        # API 응답 관련 설정
        self.api_response_timeout = getattr(config, 'API_RESPONSE_TIMEOUT', 10)  # 기본 10초
        self.api_retry_count = getattr(config, 'API_RETRY_COUNT', 3)  # 기본 3회 재시도
        self.api_retry_delay = getattr(config, 'API_RETRY_DELAY', 1.0)  # 기본 1초 지연
        # 마지막 API 호출 시간 기록 (API 호출 간격 제한 준수)
        self.last_api_call = {}
        # API 호출 통계
        self.api_call_counts = {}
        logger.info(f"{self.__class__.__name__} 초기화")
    
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
    
    def wait_for_api_response(self, func, *args, max_retries=None, retry_delay=None, 
                              expected_key=None, expected_condition=None, **kwargs):
        """
        API 응답을 기다리고 검증하는 기능
        
        Args:
            func: 호출할 API 함수
            *args: API 함수에 전달할 위치 인자
            max_retries: 최대 재시도 횟수 (None인 경우 기본값 사용)
            retry_delay: 재시도 간 지연 시간 (None인 경우 기본값 사용)
            expected_key: 응답에서 확인할 키 (None인 경우 검증 건너뜀)
            expected_condition: 응답 검증을 위한 함수 (None인 경우 검증 건너뜀)
            **kwargs: API 함수에 전달할 키워드 인자
        
        Returns:
            응답 결과와 성공 여부 (result, success)
        """
        if max_retries is None:
            max_retries = self.api_retry_count
        if retry_delay is None:
            retry_delay = self.api_retry_delay
            
        # API 함수 이름 로깅
        func_name = getattr(func, '__name__', str(func))
        logger.info(f"API 호출 대기: {func_name} - 최대 {max_retries}회 시도")
        
        # API 호출 통계 업데이트
        if func_name not in self.api_call_counts:
            self.api_call_counts[func_name] = 0
        self.api_call_counts[func_name] += 1
        
        # API 호출 간격 제한 준수
        if func_name in self.last_api_call:
            time_since_last_call = time.time() - self.last_api_call[func_name]
            min_interval = getattr(self.config, 'API_MIN_INTERVAL', 0.2)  # 기본 0.2초 간격
            if time_since_last_call < min_interval:
                wait_time = min_interval - time_since_last_call
                logger.debug(f"API 호출 간격 준수를 위해 {wait_time:.2f}초 대기")
                time.sleep(wait_time)
        
        # 실행 시간 기록
        start_time = time.time()
        success = False
        result = None
        error = None
        
        # 재시도 루프
        for attempt in range(1, max_retries + 1):
            try:
                # API 함수 호출
                logger.debug(f"API 호출 시도 {attempt}/{max_retries}: {func_name}")
                result = func(*args, **kwargs)
                
                # API 호출 시간 기록
                self.last_api_call[func_name] = time.time()
                
                # 응답 검증
                if expected_key is not None:
                    if expected_key not in result:
                        logger.warning(f"API 응답에 필요한 키 없음: {expected_key}")
                        if attempt < max_retries:
                            time.sleep(retry_delay * attempt)  # 지연 시간 점진적 증가
                            continue
                        else:
                            break
                
                if expected_condition is not None:
                    if not expected_condition(result):
                        logger.warning(f"API 응답이 예상 조건을 충족하지 않음")
                        if attempt < max_retries:
                            time.sleep(retry_delay * attempt)  # 지연 시간 점진적 증가
                            continue
                        else:
                            break
                
                # 모든 검증 통과
                success = True
                elapsed_time = time.time() - start_time
                logger.info(f"API 호출 성공: {func_name} (소요시간: {elapsed_time:.2f}초)")
                break
                
            except Exception as e:
                error = e
                logger.error(f"API 호출 중 오류 (시도 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)  # 지연 시간 점진적 증가
                else:
                    logger.error(f"최대 재시도 횟수 초과: {max_retries}회")
                    logger.error(traceback.format_exc())
        
        if not success:
            if error:
                logger.error(f"API 호출 최종 실패 - 오류: {error}")
            else:
                logger.error(f"API 호출 최종 실패 - 응답 검증 실패")
        
        return result, success
    
    def wait_for_order_execution(self, order_number, max_wait_seconds=30, check_interval=2):
        """
        주문 체결 대기 및 확인 - 추상 메서드

        Args:
            order_number: 주문번호
            max_wait_seconds: 최대 대기 시간 (초)
            check_interval: 상태 확인 간격 (초)
            
        Returns:
            dict: 체결 정보
            
        Note:
            이 메서드는 자식 클래스에서 구현해야 합니다.
            주문 후 체결 정보를 확인하고, 일정 시간 동안 주문의 체결 상태를 확인하며 대기합니다.
        """
        raise NotImplementedError("각 증권사 API 클래스에서 구현해야 합니다.")

    def verify_api_response(self, response_data, expected_fields=None):
        """
        API 응답 검증 - 데이터 구조와 필수 필드 검증
        
        Args:
            response_data: API 응답 데이터
            expected_fields: 기대하는 필드 목록 (None일 경우 검증 생략)
            
        Returns:
            bool: 유효한 응답인지 여부
        """
        if response_data is None:
            self.logger.error("API 응답이 None입니다.")
            return False
            
        # 딕셔너리나 리스트 형식인지 확인
        if not isinstance(response_data, (dict, list)):
            self.logger.error(f"API 응답이 유효한 형식이 아닙니다: {type(response_data)}")
            return False
            
        # 에러 코드나 메시지 확인 (API마다 다를 수 있음)
        if isinstance(response_data, dict):
            # 에러 관련 필드 확인 (한국투자증권 API 기준)
            if 'error' in response_data:
                self.logger.error(f"API 응답에 오류가 포함되어 있습니다: {response_data['error']}")
                return False
                
            if 'rt_cd' in response_data and response_data['rt_cd'] != '0':
                self.logger.error(f"API 응답 오류: [{response_data.get('rt_cd')}] {response_data.get('msg1', '')}")
                return False
                
        # 기대하는 필드가 있는지 확인 
        if expected_fields and isinstance(response_data, dict):
            missing_fields = [field for field in expected_fields if field not in response_data]
            if missing_fields:
                self.logger.warning(f"API 응답에 일부 필드가 누락되었습니다: {missing_fields}")
                # 필드가 누락되었더라도 False를 반환하지 않고 경고만 기록
                
        return True
        
    def wait_for_api_response(self, api_call_func, max_retries=5, retry_delay=1, **kwargs):
        """
        API 응답 대기 - 재시도를 통한 안정적인 API 호출
        
        Args:
            api_call_func: API 호출 함수
            max_retries: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            **kwargs: API 호출 함수에 전달할 인자
            
        Returns:
            결과: API 호출 결과
        """
        attempt = 0
        last_error = None
        
        while attempt < max_retries:
            try:
                attempt += 1
                
                # API 호출
                result = api_call_func(**kwargs)
                
                # 유효한 응답인지 확인
                if result is not None:
                    return result
                    
                # None 응답은 실패로 간주하고 재시도
                self.logger.warning(f"API 호출 실패 (응답 없음), 재시도 {attempt}/{max_retries}")
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"API 호출 중 예외 발생, 재시도 {attempt}/{max_retries}: {e}")
            
            # 마지막 시도가 아니면 대기 후 재시도
            if attempt < max_retries:
                # 재시도마다 대기 시간 증가
                current_delay = retry_delay * (2 ** (attempt - 1))  # 지수 백오프
                self.logger.info(f"{current_delay}초 대기 후 재시도합니다.")
                time.sleep(current_delay)
        
        # 모든 재시도 실패
        if last_error:
            self.logger.error(f"최대 재시도 횟수({max_retries}회) 초과, API 호출 실패: {last_error}")
            raise last_error
        else:
            self.logger.error(f"최대 재시도 횟수({max_retries}회) 초과, API 호출 실패")
            return None
    
    def log_api_stats(self):
        """API 호출 통계 기록"""
        logger.info(f"API 호출 통계: {self.api_call_counts}")