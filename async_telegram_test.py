#!/usr/bin/env python3
"""
비동기 방식의 텔레그램 메시지 전송 테스트 스크립트
"""
import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_test_message():
    """비동기 방식으로 텔레그램 메시지 전송"""
    print(f"봇 토큰: {TOKEN[:10]}...{TOKEN[-5:]}")
    print(f"채팅 ID: {CHAT_ID}")
    
    try:
        print("봇 초기화 중...")
        bot = Bot(token=TOKEN)
        
        print("봇 정보 확인 중...")
        me = await bot.get_me()
        print(f"봇 이름: {me.first_name}")
        print(f"봇 사용자명: @{me.username}")
        
        print("메시지 전송 시작...")
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 AI 주식 자동매매 시스템 테스트 메시지입니다.",
            parse_mode=ParseMode.HTML
        )
        print("✅ 메시지 전송 완료!")
        return True
    except TelegramError as e:
        print(f"텔레그램 오류: {e}")
        return False
    except Exception as e:
        print(f"일반 오류: {e}")
        return False

if __name__ == "__main__":
    print("비동기 텔레그램 테스트 시작")
    asyncio.run(send_test_message())
    print("테스트 종료")