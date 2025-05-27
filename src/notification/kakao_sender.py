"""
카카오톡 메시지 전송 모듈
"""
import logging
import requests
from datetime import datetime

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
        self.initialize()
        
    def initialize(self):
        """카카오톡 API 초기화"""
        try:
            # 환경 변수에서 토큰 로드
            self.access_token = self.config.KAKAO_ACCESS_TOKEN
            self.refresh_token = self.config.KAKAO_REFRESH_TOKEN
            
            if not self.access_token:
                logger.error("카카오톡 액세스 토큰이 설정되지 않았습니다.")
                return
                
            # 토큰 유효성 테스트
            if self.test_token():
                logger.info("카카오톡 API 초기화 완료")
                # 시작 메시지 전송
                self.send_message("🚀 AI 주식 자동매매 시스템이 시작되었습니다.")
            else:
                logger.error("카카오톡 API 토큰이 유효하지 않습니다.")
                # 토큰 갱신 시도
                if self.refresh_auth_token():
                    logger.info("카카오톡 API 토큰 갱신 성공")
                    # 시작 메시지 전송
                    self.send_message("🚀 AI 주식 자동매매 시스템이 시작되었습니다.")
        except Exception as e:
            logger.error(f"카카오톡 API 초기화 실패: {e}")
    
    def test_token(self):
        """
        액세스 토큰 유효성 테스트
        
        Returns:
            bool: 토큰 유효 여부
        """
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
    
    def refresh_auth_token(self):
        """
        인증 토큰 갱신
        
        Returns:
            bool: 토큰 갱신 성공 여부
        """
        try:
            url = "https://kauth.kakao.com/oauth/token"
            data = {
                "grant_type": "refresh_token",
                "client_id": self.config.KAKAO_API_KEY,
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                
                # refresh_token은 선택적으로 포함될 수 있음
                if "refresh_token" in token_data:
                    self.refresh_token = token_data.get("refresh_token")
                    
                # 토큰 정보 업데이트 필요 (.env 파일 또는 설정에 저장)
                # 이 부분은 구현해야 함
                
                logger.info("카카오톡 인증 토큰 갱신 완료")
                return True
            else:
                logger.error(f"인증 토큰 갱신 실패: {response.text}")
                return False
        except Exception as e:
            logger.error(f"인증 토큰 갱신 중 오류: {e}")
            return False
    
    def send_message(self, message):
        """
        카카오톡으로 메시지 전송
        
        Args:
            message: 전송할 메시지 텍스트
            
        Returns:
            bool: 전송 성공 여부
        """
        if not self.access_token:
            logger.error("카카오톡 액세스 토큰이 설정되지 않았습니다.")
            return False
            
        try:
            # 메시지 전송 API 호출
            url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # 메시지 템플릿 설정
            import json
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
                logger.error(f"카카오톡 메시지 전송 실패: {response.text}")
                return False
        except Exception as e:
            logger.error(f"카카오톡 메시지 전송 중 오류: {e}")
            return False
    
    def send_signal_notification(self, signal_data):
        """
        매매 시그널 알림 전송
        
        Args:
            signal_data: 매매 시그널 정보
        """
        if not signal_data['signals']:
            return
            
        symbol = signal_data['symbol']
        price = signal_data['price']
        timestamp = signal_data['timestamp']
        signals = signal_data['signals']
        
        # 종목 이름 설정 (코드와 함께 표시)
        symbol_name = symbol
        
        # 메시지 생성
        message_parts = [
            f"📊 매매 시그널 알림",
            f"종목: {symbol_name}",
            f"현재가: {price:,.2f}",
            f"시간: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "발생 시그널:"
        ]
        
        for signal in signals:
            signal_type = signal['type']
            strength = signal['strength']
            reason = signal['reason']
            
            # 시그널 강도에 따른 이모지
            strength_emoji = "⚡" if strength == 'STRONG' else "✅" if strength == 'MEDIUM' else "ℹ️"
            
            # 매수/매도 이모지
            type_emoji = "🔴" if signal_type == 'SELL' else "🟢"
            
            message_parts.append(f"{type_emoji} {strength_emoji} {signal_type}: {reason}")
        
        message = "\n".join(message_parts)
        
        # 메시지 전송
        return self.send_message(message)
        
    def send_system_status(self, status_message):
        """
        시스템 상태 알림 전송
        
        Args:
            status_message: 상태 메시지
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"📊 시스템 상태\n시간: {current_time}\n\n{status_message}"
        
        # 메시지 전송
        return self.send_message(message)