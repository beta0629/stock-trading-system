#!/usr/bin/env python3
"""
텔레그램 메시지 전송 테스트 스크립트
"""
import sys
import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TelegramTest')

async def send_telegram_message():
    """텔레그램 메시지 직접 전송"""
    try:
        print(f"텔레그램 봇 토큰: {config.TELEGRAM_BOT_TOKEN[:10]}...{config.TELEGRAM_BOT_TOKEN[-5:]}")
        print(f"텔레그램 채팅 ID: {config.TELEGRAM_CHAT_ID}")
        
        # 봇 인스턴스 생성
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        
        # 테스트 메시지 준비
        test_message = """
<b>📱 텔레그램 메시지 전송 테스트</b>

안녕하세요! 이 메시지는 텔레그램 메시지 전송 기능이 제대로 작동하는지 확인하기 위한 테스트입니다.

<b>AI 주식 자동매매 시스템 정보:</b>
- 시스템 상태: 정상 작동 중
- 모니터링 중인 종목 수: 8개
- 매매 신호: 활성화됨

<code>이 메시지가 보이면 텔레그램 메시지 전송이 성공적으로 작동하는 것입니다!</code>
"""
        
        # 메시지 전송
        print("메시지 전송 시도 중...")
        await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=test_message,
            parse_mode=ParseMode.HTML
        )
        print("메시지 전송 완료!")
        return True
        
    except Exception as e:
        print(f"오류 발생: {e}")
        return False

def main():
    """메인 함수"""
    print("텔레그램 메시지 전송 테스트 시작...")
    
    # 비동기 함수 실행
    success = asyncio.run(send_telegram_message())
    
    if success:
        print("텔레그램 메시지 전송이 성공적으로 완료되었습니다. 메시지가 수신되었는지 확인해주세요.")
    else:
        print("텔레그램 메시지 전송에 실패했습니다.")
    
    print("테스트 완료")

if __name__ == "__main__":
    main()