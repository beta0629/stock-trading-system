#!/usr/bin/env python
"""
카카오톡 메시지 전송 테스트 스크립트
"""
import config
from src.notification.kakao_sender import KakaoSender
import logging
import sys
import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("KakaoTest")

def test_kakao_message():
    """카카오 메시지 전송 테스트"""
    try:
        # KakaoSender 인스턴스 생성
        kakao = KakaoSender(config)
        
        # 현재 시간 가져오기
        now = datetime.datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 테스트 메시지 전송
        message = f"🔔 카카오톡 알림 테스트 ({current_time})\n\n이 메시지가 보인다면 카카오톡 알림이 정상적으로 설정되었습니다."
        success = kakao.send_message(message)
        
        if success:
            logger.info("카카오톡 메시지 전송 성공!")
        else:
            logger.error("카카오톡 메시지 전송 실패")
            
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {e}")
        
if __name__ == "__main__":
    logger.info("카카오톡 메시지 전송 테스트를 시작합니다...")
    test_kakao_message()