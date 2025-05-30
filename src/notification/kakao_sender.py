"""
카카오톡 메시지 전송 모듈
"""
import logging
import requests
import os
import json
import time
import re
from datetime import timedelta, datetime

# time_utils 모듈 import
from ..utils.time_utils import get_current_time, get_current_time_str, parse_time, get_adjusted_time

# 로깅 설정
logger = logging.getLogger('KakaoSender')

class KakaoSender:
    """카카오톡 메시지 전송 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        self.access_token = None
        self.refresh_token = None
        self.token_expire_at = None
        self.initialized = False
        
        # 토큰 갱신 요청 제한을 위한 변수 추가
        self.last_token_refresh_attempt = None
        self.token_refresh_cooldown = 3600  # 1시간 (초 단위)
        
        # CI 환경인지 확인
        self.is_ci_env = os.environ.get('CI') == 'true'
        
        # 시스템 시작시 토큰 초기화
        self.initialize()
        
    def initialize(self):
        """카카오톡 API 초기화"""
        try:
            # CI 환경이고, KAKAO_API_KEY가 없으면 비활성화 모드로 설정
            if self.is_ci_env and not os.environ.get('KAKAO_API_KEY'):
                logger.warning("CI 환경에서 KAKAO_API_KEY가 설정되지 않아 카카오톡 알림은 비활성화됩니다.")
                return False
            
            # 환경 변수 우선 확인 (CI/CD 환경용)
            self.access_token = os.environ.get('KAKAO_ACCESS_TOKEN')
            self.refresh_token = os.environ.get('KAKAO_REFRESH_TOKEN')
            
            # 환경변수에 없으면 파일에서 토큰 로드
            if not self.access_token or not self.refresh_token:
                token_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'kakao_token.json')
                if os.path.exists(token_file):
                    try:
                        with open(token_file, 'r') as f:
                            token_data = json.load(f)
                            self.access_token = token_data.get('access_token')
                            self.refresh_token = token_data.get('refresh_token')
                            self.token_expire_at = token_data.get('expire_at')
                            logger.info("카카오톡 토큰 파일에서 로드 완료")
                    except Exception as e:
                        logger.error(f"카카오톡 토큰 파일 로드 실패: {e}")
            
            # 환경 변수에서 토큰 로드 (파일에서 로드 실패시)
            if not self.access_token and hasattr(self.config, 'KAKAO_ACCESS_TOKEN'):
                self.access_token = self.config.KAKAO_ACCESS_TOKEN
            if not self.refresh_token and hasattr(self.config, 'KAKAO_REFRESH_TOKEN'):
                self.refresh_token = self.config.KAKAO_REFRESH_TOKEN
            
            if not self.access_token or not self.refresh_token:
                if self.is_ci_env:
                    logger.warning("CI 환경에서 카카오톡 토큰이 설정되지 않아 알림은 비활성화됩니다.")
                    return False
                else:
                    logger.error("카카오톡 토큰이 설정되지 않았습니다.")
                    return False
            
            # 토큰의 만료 시간 확인
            if self.token_expire_at:
                try:
                    expire_time = parse_time(self.token_expire_at)
                    current_time = get_current_time()
                    # 만료된 경우에만 갱신 요청
                    if current_time >= expire_time:
                        logger.info("카카오톡 토큰이 만료되었습니다. 갱신을 시도합니다.")
                        if not self._can_refresh_token():
                            logger.warning("토큰 갱신 요청 제한 시간(1시간) 내에 있습니다. 토큰 갱신을 건너뜁니다.")
                        elif not self.refresh_auth_token():
                            logger.error("토큰 갱신 실패")
                            return False
                except Exception as e:
                    logger.error(f"토큰 만료 시간 확인 중 오류: {e}")
            
            # 토큰 유효성 테스트 (테스트는 반드시 한 번만 실행)
            token_valid = self.test_token()
            if token_valid:
                logger.info("카카오톡 API 초기화 완료")
                self.initialized = True
                return True
            else:
                # 토큰 테스트 실패 시 갱신 시도 (제한 시간 검사 후)
                logger.warning("카카오톡 API 토큰이 유효하지 않습니다. 갱신을 시도합니다.")
                if not self._can_refresh_token():
                    logger.warning("토큰 갱신 요청 제한 시간(1시간) 내에 있습니다. 갱신을 건너뜁니다.")
                    return False
                elif self.refresh_auth_token():
                    logger.info("카카오톡 API 토큰 갱신 성공")
                    self.initialized = True
                    return True
                else:
                    if self.is_ci_env:
                        logger.warning("CI 환경에서 토큰 갱신 실패. 카카오톡 알림은 비활성화됩니다.")
                    else:
                        logger.error("카카오톡 API 토큰 갱신 실패")
                    return False
        except Exception as e:
            logger.error(f"카카오톡 API 초기화 실패: {e}")
            return False
    
    def _can_refresh_token(self):
        """
        토큰 갱신 요청이 가능한지 검사 (rate limit 방지)
        
        Returns:
            bool: 갱신 요청 가능 여부
        """
        # 최근 갱신 요청 시간이 없으면 가능
        if self.last_token_refresh_attempt is None:
            return True
            
        # 현재 시간과 최근 갱신 요청 시간의 차이 계산
        current_time = time.time()
        time_diff = current_time - self.last_token_refresh_attempt
        
        # 제한 시간(cooldown) 이후면 가능
        return time_diff >= self.token_refresh_cooldown
    
    def test_token(self):
        """
        액세스 토큰 유효성 테스트
        
        Returns:
            bool: 토큰 유효 여부
        """
        if not self.access_token:
            logger.error("액세스 토큰이 없어 테스트할 수 없습니다.")
            return False
            
        try:
            url = "https://kapi.kakao.com/v2/api/talk/profile"
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = requests.get(url, headers=headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"토큰 테스트 실패: {e}")
            return False
    
    def save_tokens_to_file(self):
        """토큰을 파일에 저장"""
        try:
            # CI 환경에서는 파일 저장 건너뛰기
            if self.is_ci_env:
                logger.info("CI 환경에서는 토큰 파일을 저장하지 않습니다.")
                return True
                
            token_data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expire_at": get_adjusted_time(adjust_days=29).isoformat(),  # 약 30일 후 만료
                "updated_at": get_current_time().isoformat()
            }
            
            token_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'kakao_token.json')
            with open(token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
                
            logger.info("카카오톡 토큰 파일 저장 완료")
            
            # GitHub Actions에서 실행 중이면 환경 변수 업데이트
            if 'GITHUB_ENV' in os.environ:
                with open(os.environ['GITHUB_ENV'], 'a') as env_file:
                    env_file.write(f"KAKAO_ACCESS_TOKEN={self.access_token}\n")
                    env_file.write(f"KAKAO_REFRESH_TOKEN={self.refresh_token}\n")
                logger.info("GitHub 환경 변수에 토큰 업데이트 완료")
                
            return True
        except Exception as e:
            logger.error(f"카카오톡 토큰 파일 저장 실패: {e}")
            return False
    
    def refresh_auth_token(self):
        """
        인증 토큰 갱신
        
        Returns:
            bool: 토큰 갱신 성공 여부
        """
        # 갱신 요청 시간 기록 (요청 성공 여부와 무관하게)
        self.last_token_refresh_attempt = time.time()

        try:
            url = "https://kauth.kakao.com/oauth/token"
            
            # client_id가 없는 경우 환경 변수나 config에서 가져오기
            client_id = os.environ.get('KAKAO_API_KEY')
            if not client_id and hasattr(self.config, 'KAKAO_API_KEY'):
                client_id = self.config.KAKAO_API_KEY
                
            if not client_id:
                if self.is_ci_env:
                    logger.warning("CI 환경에서 KAKAO_API_KEY가 설정되지 않아 토큰 갱신을 건너뜁니다.")
                    return False
                else:
                    logger.error("KAKAO_API_KEY가 설정되지 않았습니다.")
                    return False
                
            data = {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                
                # refresh_token은 선택적으로 포함될 수 있음
                if "refresh_token" in token_data:
                    self.refresh_token = token_data.get("refresh_token")
                
                # 토큰 만료 시간 설정 (약 30일)
                self.token_expire_at = get_adjusted_time(adjust_days=29).isoformat()
                    
                # 토큰을 파일에 저장
                self.save_tokens_to_file()
                
                logger.info("카카오톡 인증 토큰 갱신 완료")
                return True
            else:
                logger.error(f"인증 토큰 갱신 실패: {response.text}")
                return False
        except Exception as e:
            logger.error(f"인증 토큰 갱신 중 오류: {e}")
            return False
    
    def ensure_token_valid(self):
        """토큰이 유효한지 확인하고, 필요시 갱신"""
        if not self.initialized:
            return self.initialize()
        
        # 토큰 만료 시간 확인 - 실제 만료된 경우에만 갱신 시도
        if self.token_expire_at:
            try:
                expire_time = parse_time(self.token_expire_at)
                current_time = get_current_time()
                if current_time >= expire_time:
                    logger.info("토큰이 만료되었습니다. 갱신을 시도합니다.")
                    if self._can_refresh_token():
                        return self.refresh_auth_token()
                    else:
                        logger.warning("토큰 갱신 요청 제한 시간 내에 있습니다. 현재 토큰을 계속 사용합니다.")
                        # 이미 만료되었지만 갱신 요청 제한으로 인해 갱신하지 못할 때는, 
                        # 기존 토큰으로라도 메시지 전송 시도
                        return True
                # 만료되지 않았으면 현재 토큰 사용
                return True
            except Exception as e:
                logger.error(f"토큰 만료 시간 확인 중 오류: {e}")
        
        # 만료 시간 정보가 없으면 토큰 테스트 후 필요시 갱신
        if not self.test_token():
            logger.info("토큰 테스트 실패. 갱신을 시도합니다.")
            if self._can_refresh_token():
                return self.refresh_auth_token()
            else:
                logger.warning("토큰 갱신 요청 제한 시간 내에 있습니다. 갱신을 건너뜁니다.")
                return False
        return True
    
    def send_message(self, message):
        """
        카카오톡으로 메시지 전송
        
        Args:
            message: 전송할 메시지 텍스트
            
        Returns:
            bool: 전송 성공 여부
        """
        # GitHub Actions 환경인지 확인하고 로그 추가
        is_github_actions = 'GITHUB_ACTIONS' in os.environ
        if is_github_actions:
            logger.info(f"GitHub Actions 환경에서 실행 중, 환경변수 확인: KAKAO_API_KEY={os.environ.get('KAKAO_API_KEY') is not None}, KAKAO_ACCESS_TOKEN={os.environ.get('KAKAO_ACCESS_TOKEN') is not None}")
        
        # CI 환경에서도 토큰이 유효하면 메시지 전송 시도
        if self.is_ci_env:
            # 토큰이 없을 때만 건너뛰기
            if not self.access_token or not self.refresh_token:
                logger.info("CI 환경에서 카카오톡 토큰이 없어 메시지 전송을 건너뜁니다.")
                return True  # 전송 성공으로 처리하여 프로세스 계속 진행
            
            logger.info(f"CI 환경에서 카카오톡 메시지 전송 시도: {message[:30]}...")
        
        # 메시지 전송 전에 토큰 유효성 확인
        if not self.ensure_token_valid():
            logger.error("유효한 카카오톡 액세스 토큰이 없습니다.")
            # 토큰 정보 출력 (민감 정보 일부만 표시)
            if self.access_token:
                token_preview = f"{self.access_token[:5]}...{self.access_token[-5:]}"
                logger.debug(f"액세스 토큰 미리보기: {token_preview}")
            
            # CI 환경이더라도 토큰을 재생성할 수 있도록 시도
            if self.is_ci_env and os.environ.get('KAKAO_API_KEY'):
                logger.info("CI 환경에서 토큰 재생성 시도")
                if self.refresh_auth_token():
                    logger.info("CI 환경에서 토큰 재생성 성공")
                    # 여기서는 계속 진행하고 메시지 전송 시도
                else:
                    logger.warning("CI 환경에서 토큰 재생성 실패, 메시지 전송은 건너뜁니다")
                    return True  # 프로세스는 계속 진행
            elif self.is_ci_env:
                logger.info("CI 환경에서 토큰이 유효하지 않아 메시지 전송은 건너뜁니다.")
                return True
            return False
        
        # 메시지 길이가 제한을 초과하면 여러 메시지로 분할
        max_message_length = 1800  # 안전한 길이 제한 (2000자보다 작게 설정)
        
        # 메시지를 분할
        if len(message) > max_message_length:
            parts = self._split_message(message, max_message_length)
            success = True
            
            # 분할된 메시지 각각을 전송
            for i, part in enumerate(parts):
                part_message = f"[{i+1}/{len(parts)}] {part}"
                if not self._send_single_message(part_message):
                    success = False
                # 연속 메시지 전송 시 약간의 딜레이 추가
                if i < len(parts) - 1:
                    time.sleep(0.5)
                    
            return success
        else:
            # 단일 메시지 전송
            return self._send_single_message(message)
            
    def _send_single_message(self, message):
        """
        단일 카카오톡 메시지 전송 (내부 함수)
        
        Args:
            message: 전송할 메시지 텍스트
            
        Returns:
            bool: 전송 성공 여부
        """
        try:
            # 메시지 전송 API 호출
            url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # 메시지 템플릿 설정
            template = {
                "object_type": "text",
                "text": message,
                "link": {
                    "web_url": "https://developers.kakao.com",
                    "mobile_web_url": "https://developers.kakao.com"
                },
                "button_title": "자세히 보기"
            }
            
            data = {
                "template_object": json.dumps(template)
            }
            
            response = requests.post(url, headers=headers, data=data)
            if response.status_code == 200:
                logger.info("카카오톡 메시지 전송 완료")
                return True
            else:
                # 토큰 만료일 때 갱신 후 재시도
                if response.status_code == 401:
                    logger.warning("토큰이 만료되었습니다. 갱신 후 재시도합니다.")
                    if self.refresh_auth_token():
                        return self._send_single_message(message)  # 재귀적으로 다시 시도
                logger.error(f"카카오톡 메시지 전송 실패: {response.text}")
                if self.is_ci_env:
                    logger.info("CI 환경에서 메시지 전송 실패는 무시하고 계속 진행합니다.")
                    return True
                return False
        except Exception as e:
            logger.error(f"카카오톡 메시지 전송 중 오류: {e}")
            if self.is_ci_env:
                logger.info("CI 환경에서 발생한 오류는 무시하고 계속 진행합니다.")
                return True
            return False
            
    def _split_message(self, message, max_length):
        """
        긴 메시지를 적절한 크기로 분할
        
        Args:
            message: 원본 메시지 텍스트
            max_length: 분할된 조각의 최대 길이
            
        Returns:
            list: 분할된 메시지의 리스트
        """
        # 줄바꿈으로 먼저 분할하여 문맥을 유지
        lines = message.split('\n')
        parts = []
        current_part = ""
        
        for line in lines:
            # 한 줄이 max_length를 초과하면 해당 줄을 다시 분할
            if len(line) > max_length:
                # 현재까지 모인 내용이 있으면 parts에 추가
                if current_part:
                    parts.append(current_part)
                    current_part = ""
                
                # 긴 줄을 단어 단위로 분할
                words = line.split(' ')
                word_part = ""
                
                for word in words:
                    if len(word_part) + len(word) + 1 <= max_length:
                        if word_part:
                            word_part += " " + word
                        else:
                            word_part = word
                    else:
                        parts.append(word_part)
                        word_part = word
                
                if word_part:
                    current_part = word_part
            else:
                # 현재 부분에 이 줄을 추가했을 때 max_length를 초과하면 새 부분 시작
                if len(current_part) + len(line) + 1 > max_length:
                    parts.append(current_part)
                    current_part = line
                else:
                    # 현재 부분에 줄 추가
                    if current_part:
                        current_part += "\n" + line
                    else:
                        current_part = line
        
        # 남은 텍스트 추가
        if current_part:
            parts.append(current_part)
            
        return parts
    
    def send_signal_notification(self, signal_data):
        """
        매매 시그널 알림 전송 (핵심적인 정보만 간결하게 표시)
        
        Args:
            signal_data: 매매 시그널 정보
        """
        if not signal_data.get('signals'):
            return
            
        # 디버깅: 전체 signal_data 로깅
        logger.info(f"매매 신호 데이터: {json.dumps(signal_data, ensure_ascii=False, default=str)}")
            
        symbol = signal_data['symbol']
        price = signal_data.get('price', signal_data.get('close', 0))
        
        # price가 문자열인 경우 숫자로 변환 (ValueError 방지)
        try:
            if isinstance(price, str):
                price = float(price.replace(',', ''))  # 콤마 제거 후 변환
            elif not isinstance(price, (int, float)):
                price = 0  # 변환 불가능한 경우 기본값
        except Exception as e:
            logger.warning(f"가격 형식 변환 중 오류: {e}, 기본값 0으로 설정")
            price = 0
            
        signals = signal_data['signals']
        market = signal_data.get('market', 'KR')  # 기본값은 KR
        
        # 종목 이름 설정 (코드와 함께 표시)
        stock_name = signal_data.get('name')
        if not stock_name:
            stock_name = self._get_stock_name(symbol)
        
        # 로그 추가 - 종목명 디버깅
        logger.info(f"종목명 확인: symbol={symbol}, stock_name={stock_name}, market={market}")
        
        # 가장 중요한 신호 찾기
        latest_signal = signals[0]
        for signal in signals:
            if signal.get('confidence', 0) > latest_signal.get('confidence', 0):
                latest_signal = signal
        
        signal_type = latest_signal['type']
        confidence = latest_signal.get('confidence', 0)
        
        # 매매 데이터 가져오기 (구매 수량, 평단가, 잔고 등)
        trade_info = signal_data.get('trade_info', {})
        # 디버깅: trade_info 내용 확인
        logger.info(f"매매 정보 확인: {json.dumps(trade_info, ensure_ascii=False, default=str)}")
        
        trade_quantity = trade_info.get('quantity', 0)  # 매매 수량
        total_quantity = trade_info.get('total_quantity', 0)  # 매매 후 총 보유 수량
        avg_price = trade_info.get('avg_price', 0)  # 평균단가
        balance = trade_info.get('balance', 0)  # 계좌 잔고
        prev_quantity = trade_info.get('prev_quantity', 0)  # 매매 전 보유 수량
        total_eval = trade_info.get('total_eval', 0)  # 총평가금액
        
        # balance가 문자열인 경우 숫자로 변환 (TypeError 방지)
        try:
            if isinstance(balance, str):
                balance = float(balance.replace(',', ''))  # 콤마 제거 후 변환
            elif not isinstance(balance, (int, float)):
                balance = 0  # 변환 불가능한 경우 기본값
        except Exception as e:
            logger.warning(f"계좌 잔고 형식 변환 중 오류: {e}, 기본값 0으로 설정")
            balance = 0
            
        # 매매 수량, 보유량 값 검증 및 로깅
        logger.info(f"매매 수량: {trade_quantity}, 이전 보유량: {prev_quantity}, 현재 보유량: {total_quantity}")
        
        # 포맷팅에 사용될 값들이 None이 아닌지 확인하고 숫자형으로 변환
        try:
            if prev_quantity is None:
                prev_quantity = 0
            else:
                prev_quantity = int(float(str(prev_quantity).replace(',', '') or 0))
        except Exception as e:
            logger.warning(f"이전 보유량 변환 오류: {e}")
            prev_quantity = 0
            
        try:
            if total_quantity is None:
                total_quantity = trade_quantity  # 없으면 매매 수량으로 대체
            else:
                total_quantity = int(float(str(total_quantity).replace(',', '') or 0))
        except Exception as e:
            logger.warning(f"총 보유량 변환 오류: {e}")
            total_quantity = trade_quantity
            
        try:
            if avg_price is None:
                avg_price = price  # 없으면 현재가로 대체
            else:
                avg_price = float(str(avg_price).replace(',', '') or 0)
        except Exception as e:
            logger.warning(f"평균단가 변환 오류: {e}")
            avg_price = price
        
        # 증권사 API 관련 정보
        order_no = trade_info.get('order_no', '')  # 주문 번호
        executed_price = trade_info.get('executed_price', price)  # 체결 가격
        
        # executed_price가 문자열인 경우 숫자로 변환
        try:
            if isinstance(executed_price, str):
                executed_price = float(executed_price.replace(',', ''))
        except Exception:
            executed_price = price  # 변환 실패 시 기본 price 값 사용
            
        executed_qty = trade_info.get('executed_qty', 0)  # 체결 수량
        remain_qty = trade_info.get('remain_qty', 0)  # 미체결 수량
        order_status = trade_info.get('order_status', '')  # 주문 상태
        fee = trade_info.get('fee', 0)  # 수수료
        transaction_time = trade_info.get('transaction_time', '')  # 거래 시간

        # 메시지 포맷 설정 - 기존 스타일로 돌아가기
        if signal_type == "BUY":
            header_message = "BUY:"
        else:  # "SELL"
            header_message = "SELL:"

        # 기존 포맷 (구매 수량 정보 포함)
        message = f"{header_message}\n"
        
        # 종목명 표시 (종목코드를 괄호 안에 표시)
        if stock_name:
            message += f"{stock_name} ({symbol})\n"
        else:
            message += f"{symbol}\n"
            
        # 현재가와 신뢰도 표시 - .0 제거를 위해 정수로 변환 후 천 단위 콤마 표시
        if price > 0:
            message += f"현재가: {int(price):,}원"
        else:
            # 현재가가 0이면 executed_price나 avg_price를 사용
            if executed_price > 0:
                message += f"현재가: {int(executed_price):,}원"
            elif avg_price > 0:
                message += f"현재가: {int(avg_price):,}원"
            else:
                message += "현재가: 정보 없음"
        
        # 신뢰도가 있으면 추가
        if confidence:
            message += f" (신뢰도: {confidence*100:.1f}%)\n"
        else:
            message += "\n"
            
        # 매매 수량 표시
        message += f"매수량: {trade_quantity}주\n"
        
        # 보유량 변화 표시 (이전 → 현재)
        message += f"보유량: {prev_quantity}주 → {total_quantity}주\n"
        
        # 평단가 (.0 제거를 위해 정수로 변환)
        if avg_price > 0:
            message += f"평단가: {int(avg_price):,}원\n"
        else:
            message += f"평단가: 정보 없음\n"
            
        # 계좌 잔고 (.0 제거를 위해 정수로 변환)
        if balance > 0:
            message += f"계좌잔고: {int(balance):,}원"
        else:
            message += f"계좌잔고: 정보 없음"

        # 주문 정보 추가
        if order_no:
            message += f"\n\n📝 주문정보\n"
            message += f"주문번호: {order_no}\n"
            
            # 거래 시간 (있는 경우)
            if transaction_time:
                message += f"거래시간: {transaction_time}"
        
        # 최종 메시지 내용 확인
        logger.info(f"카카오톡 메시지 내용: {message}")
        
        # 메시지 전송
        return self.send_message(message)
    
    def send_detailed_analysis(self, signal_data, symbol_name):
        """
        상세 분석은 사용자 요청 시에만 보내도록 상세 보기 안내 메시지만 전송
        
        Args:
            signal_data: 매매 시그널 정보
            symbol_name: 종목명 (코드 포함)
        """
        # 상세 분석이 필요한 경우 안내 메시지만 전송
        return
    
    def send_system_status(self, status_message):
        """
        시스템 상태 알림 전송 (정보 알림은 모든 내용 표시)
        
        Args:
            status_message: 상태 메시지
        """
        # HTML 태그 제거
        clean_message = self._remove_html_tags(status_message)
        
        # 아이콘 설정
        icon = "📊"
        if "분석" in clean_message:
            icon = "📈"
        elif "매매" in clean_message:
            icon = "🔔"
        elif "오류" in clean_message or "실패" in clean_message:
            icon = "⚠️"
        elif "업데이트" in clean_message:
            icon = "🔄"
            
        # 메시지 특성에 따른 처리
        if "GPT 추천" in clean_message or "종목 리스트 업데이트" in clean_message:
            # GPT 추천 종목 분석과 종목 업데이트 메시지는 전체 내용 표시
            logger.info("GPT 종목 추천 또는 종목 업데이트 메시지 전송 (전체 내용)")
            return self.send_message(f"{icon} {get_current_time_str(format_str='%m-%d %H:%M')}\n\n{clean_message}")
        elif "### RSI" in clean_message:
            # RSI 분석 등 기술적 분석 메시지는 핵심만 추출
            return self._send_technical_analysis(clean_message)
        elif len(clean_message) > 1800:
            # 길이 제한에 걸리는 아주 긴 메시지만 분할 전송
            logger.info("매우 긴 메시지 분할 전송")
            parts = self._split_message(clean_message, 1800)
            success = True
            
            for i, part in enumerate(parts):
                part_with_header = f"{icon} {get_current_time_str(format_str='%m-%d %H:%M')} [{i+1}/{len(parts)}]\n\n{part}"
                if not self._send_single_message(part_with_header):
                    success = False
                # 연속 메시지 전송 시 약간의 딜레이 추가
                if i < len(parts) - 1:
                    time.sleep(0.5)
                    
            return success
        else:
            # 일반 정보 알림 메시지는 전체 내용 표시
            return self.send_message(f"{icon} {get_current_time_str(format_str='%m-%d %H:%M')}\n\n{clean_message}")
            
    def _send_technical_analysis(self, message):
        """기술적 분석 메시지에서 핵심 내용만 추출하여 전송
        
        Args:
            message: 전체 기술적 분석 메시지
            
        Returns:
            bool: 전송 성공 여부
        """
        # 각 분석 섹션 구분
        sections = message.split('###')
        result_parts = []
        
        # 제목 부분 처리
        if sections[0].strip():
            title_match = re.search(r'([^\n]+)', sections[0])
            if title_match:
                result_parts.append(f"📊 {title_match.group(1).strip()}")
        
        # 각 섹션에서 첫 1-2문장만 추출
        for section in sections[1:]:
            if not section.strip():
                continue
                
            lines = section.strip().split('\n')
            section_title = lines[0].strip() if lines else ""
            
            if section_title:
                # 섹션 제목은 완전히 포함
                if "RSI" in section_title:
                    result_parts.append(f"📈 {section_title}")
                elif "매도" in section_title:
                    result_parts.append(f"🔴 {section_title}")
                elif "매수" in section_title or "신호" in section_title:
                    result_parts.append(f"🟢 {section_title}")
                elif "추세" in section_title or "추가" in section_title:
                    result_parts.append(f"📉 {section_title}")
                else:
                    result_parts.append(f"📌 {section_title}")
                
                # 내용에서 첫 문장 추출
                content = ' '.join(lines[1:]).strip()
                sentences = re.split(r'(?<=[.!?])\s+', content)
                
                if sentences and len(sentences[0]) > 10:
                    # 첫 문장이 너무 길면 축약
                    first_sentence = sentences[0]
                    if len(first_sentence) > 80:
                        first_sentence = first_sentence[:77] + "..."
                    result_parts.append(f"  {first_sentence}")
        
        # 결과 조합 및 전송
        result_message = '\n'.join(result_parts)
        return self.send_message(result_message)
    
    def _get_stock_name(self, symbol):
        """종목 코드에 해당하는 종목 이름 반환

        Args:
            symbol: 종목 코드

        Returns:
            str: 종목 이름 (얻을 수 없는 경우 종목 코드 반환)
        """
        # 한국 주식 KR_STOCK_INFO에서 종목명 찾기
        if hasattr(self.config, 'KR_STOCK_INFO'):
            for stock in self.config.KR_STOCK_INFO:
                if stock['code'] == symbol:
                    return stock['name']
        
        # 미국 주식 US_STOCK_INFO에서 종목명 찾기
        if hasattr(self.config, 'US_STOCK_INFO'):
            for stock in self.config.US_STOCK_INFO:
                if stock['code'] == symbol:
                    return stock['name']
        
        # config에 종목 이름 매핑이 있는지 확인
        if hasattr(self.config, 'STOCK_NAMES') and symbol in self.config.STOCK_NAMES:
            return self.config.STOCK_NAMES.get(symbol, symbol)
        
        # 마지막 대안으로 symbol 그대로 반환
        return symbol
    
    def _remove_html_tags(self, text):
        """HTML 태그 제거

        Args:
            text: HTML 태그가 포함된 텍스트

        Returns:
            str: HTML 태그가 제거된 텍스트
        """
        if not text:
            return ""
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)