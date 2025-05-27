"""
카카오톡 메시지 전송 테스트 스크립트
"""
import sys
import logging
import config
from src.notification.kakao_sender import KakaoSender

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TestKakao')

def test_kakao_message():
    """카카오톡 메시지 전송을 테스트합니다."""
    try:
        logger.info("카카오톡 메시지 전송 테스트를 시작합니다...")
        
        # KakaoSender 객체 생성
        sender = KakaoSender(config)
        
        # 테스트 메시지 전송
        test_message = "🔔 AI 주식 자동매매 시스템 카카오톡 연동 테스트 메시지입니다."
        result = sender.send_message(test_message)
        
        if result:
            logger.info("카카오톡 메시지 전송 성공!")
        else:
            logger.error("카카오톡 메시지 전송 실패!")
            
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {e}")
        return False
        
    return True

if __name__ == "__main__":
    if test_kakao_message():
        logger.info("테스트가 성공적으로 완료되었습니다.")
        sys.exit(0)
    else:
        logger.error("테스트에 실패했습니다.")
        sys.exit(1)