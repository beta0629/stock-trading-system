#!/usr/bin/env python
"""
한국투자증권 API 인증 토큰 발급 및 관리 유틸리티

실행방법: python kis_auth.py
"""

import os
import requests
import json
import logging
from dotenv import load_dotenv
from src.utils.time_utils import get_current_time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('KIS_AUTH')

# .env 파일 로드
load_dotenv()

def get_access_token(app_key, app_secret):
    """
    액세스 토큰을 발급받습니다.
    
    Args:
        app_key: API 앱키
        app_secret: API 앱시크릿
        
    Returns:
        str: 액세스 토큰
    
    Raises:
        Exception: 토큰 발급 실패 시
    """
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"Content-Type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to get access token: {response.text}")

def save_token_to_file(token_data, file_path="kis_token.json"):
    """토큰 정보를 JSON 파일로 저장합니다."""
    with open(file_path, "w") as f:
        json.dump(token_data, f, indent=2)
    logger.info(f"토큰 정보가 {file_path}에 저장되었습니다.")

def load_token_from_file(file_path="kis_token.json"):
    """JSON 파일에서 토큰 정보를 로드합니다."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def check_token_validity(token_data):
    """토큰 유효성을 확인합니다."""
    if not token_data or "access_token" not in token_data:
        return False
        
    # expires_in 값이 있는 경우 만료 시간 계산
    if "expires_in" in token_data:
        # 현재 시간과 토큰 생성 시간을 비교하여 만료 여부 확인
        created_at = token_data.get("created_at", 0)
        expires_in = token_data.get("expires_in", 86400)  # 기본 1일
        
        current_time = get_current_time().timestamp()  # datetime.datetime.now().timestamp() 대신 time_utils 사용
        # 만료 10분 전에 갱신되도록 설정 (600초)
        return current_time < (created_at + expires_in - 600)
    
    return False

def refresh_token(use_real_trading=False):
    """
    토큰을 확인하고 필요시 갱신합니다.
    
    Args:
        use_real_trading: 실전투자 API 사용 여부
    
    Returns:
        dict: 토큰 정보
    """
    # 실전/모의투자 설정에 따라 API 키 선택
    if use_real_trading:
        app_key = os.getenv("KIS_APP_KEY")
        app_secret = os.getenv("KIS_APP_SECRET")
        mode = "실전투자"
    else:
        app_key = os.getenv("KIS_VIRTUAL_APP_KEY")
        app_secret = os.getenv("KIS_VIRTUAL_APP_SECRET")
        mode = "모의투자"
    
    logger.info(f"{mode} 모드로 토큰을 발급합니다.")
    
    if not app_key or not app_secret:
        raise ValueError(f"{mode} API 키가 설정되지 않았습니다.")
    
    # 기존 토큰 로드
    token_file = "kis_real_token.json" if use_real_trading else "kis_virtual_token.json"
    token_data = load_token_from_file(token_file)
    
    # 토큰 유효성 검사
    if check_token_validity(token_data):
        logger.info("기존 토큰이 유효합니다.")
        return token_data
    
    # 토큰 갱신
    logger.info("토큰을 갱신합니다...")
    try:
        new_token_data = get_access_token(app_key, app_secret)
        # 토큰 생성 시간 추가
        new_token_data["created_at"] = get_current_time().timestamp()  # datetime.datetime.now().timestamp() 대신 time_utils 사용
        save_token_to_file(new_token_data, token_file)
        return new_token_data
    except Exception as e:
        logger.error(f"토큰 갱신 실패: {e}")
        if token_data and "access_token" in token_data:
            logger.warning("이전 토큰을 계속 사용합니다.")
            return token_data
        raise

def main():
    """메인 함수"""
    # 환경 변수에서 실전투자 여부 확인
    use_real_trading = os.getenv("KIS_REAL_TRADING", "False").lower() == "true"
    
    try:
        token_data = refresh_token(use_real_trading)
        print("=" * 50)
        print(f"{'실전투자' if use_real_trading else '모의투자'} API 토큰 정보:")
        print(f"액세스 토큰: {token_data['access_token']}")
        print(f"만료 시간: {token_data['expires_in']}초")
        if "scope" in token_data:
            print(f"권한 범위: {token_data['scope']}")
        print("=" * 50)
    except Exception as e:
        logger.error(f"오류 발생: {e}")

if __name__ == "__main__":
    main()