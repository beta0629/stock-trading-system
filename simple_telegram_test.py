#!/usr/bin/env python3
"""
간단한 텔레그램 메시지 전송 테스트 스크립트
"""
import requests
import os
from dotenv import load_dotenv
import time

# 환경 변수 직접 로드
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message():
    """HTTP 요청을 통한 텔레그램 메시지 전송"""
    print(f"토큰: {TOKEN[:10]}...{TOKEN[-5:]}")
    print(f"채팅 ID: {CHAT_ID}")
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": "🚀 자동매매 시스템 테스트 메시지입니다.",
        "parse_mode": "HTML"
    }
    
    try:
        print("HTTP 요청 전송 시작...")
        start_time = time.time()
        # 타임아웃을 5초로 줄임
        response = requests.post(url, json=payload, timeout=5)
        end_time = time.time()
        print(f"요청 소요 시간: {end_time - start_time:.2f}초")
        print(f"응답 상태 코드: {response.status_code}")
        print(f"응답 내용: {response.text}")
        
        return response.status_code == 200
    except requests.exceptions.Timeout:
        print("요청 시간 초과 (5초) - 네트워크 연결 상태를 확인하세요")
        return False
    except Exception as e:
        print(f"오류 발생: {e}")
        return False

if __name__ == "__main__":
    print("간단한 텔레그램 테스트 시작")
    
    # 먼저 봇 정보를 가져와 연결 상태 확인
    try:
        print("텔레그램 봇 정보 확인 중...")
        info_url = f"https://api.telegram.org/bot{TOKEN}/getMe"
        info_response = requests.get(info_url, timeout=5)
        print(f"봇 정보 응답: {info_response.text}")
    except Exception as e:
        print(f"봇 정보 확인 실패: {e}")
    
    success = send_telegram_message()
    
    if success:
        print("✅ 메시지 전송 성공! 텔레그램 앱을 확인하세요.")
    else:
        print("❌ 메시지 전송 실패. 응답을 확인하세요.")