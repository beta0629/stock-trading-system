#!/usr/bin/env python3
"""
시간 관련 유틸리티 모듈

이 모듈은 한국 시간(KST)과 미국 동부 시간(EST) 관련 기능을 제공합니다.
시간 변환, 시장 개장 여부 확인 등의 기능을 포함합니다.
"""

import datetime
import pytz
import config

# 타임존 설정
KST = pytz.timezone('Asia/Seoul')
EST = pytz.timezone('US/Eastern')

def get_current_time(timezone=KST):
    """
    현재 시간을 지정된 시간대로 반환
    
    Args:
        timezone: 시간대 (기본값: KST)
        
    Returns:
        datetime: 현재 시간 (해당 시간대)
    """
    # 문자열로 전달된 timezone 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            # 알 수 없는 시간대일 경우 기본 KST 사용
            timezone = KST
            
    return datetime.datetime.now(timezone)

def get_current_time_str(timezone=KST, format_str='%Y-%m-%d %H:%M:%S'):
    """
    현재 시간 문자열을 지정된 시간대와 포맷으로 반환
    
    Args:
        timezone: 시간대 (기본값: KST)
        format_str: 시간 포맷 (기본값: '%Y-%m-%d %H:%M:%S')
        
    Returns:
        str: 포맷된 현재 시간 문자열
    """
    return get_current_time(timezone).strftime(format_str)

def convert_time(dt, from_timezone=KST, to_timezone=EST):
    """
    시간을 한 시간대에서 다른 시간대로 변환
    
    Args:
        dt: 변환할 datetime 객체
        from_timezone: 원본 시간대
        to_timezone: 변환할 시간대
        
    Returns:
        datetime: 변환된 시간
    """
    if dt.tzinfo is None:
        dt = from_timezone.localize(dt)
    return dt.astimezone(to_timezone)

def parse_time(time_str, format_str='%Y-%m-%d %H:%M:%S', timezone=KST):
    """
    문자열을 datetime 객체로 파싱
    
    Args:
        time_str: 시간 문자열
        format_str: 시간 포맷
        timezone: 시간대
        
    Returns:
        datetime: 파싱된 datetime 객체
    """
    # 문자열로 전달된 timezone 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone = KST
            
    dt = datetime.datetime.strptime(time_str, format_str)
    return timezone.localize(dt)

def is_market_open(market="KR"):
    """
    주식 시장이 현재 개장 중인지 확인
    
    Args:
        market: 시장 코드 ("KR" 또는 "US")
        
    Returns:
        bool: 시장 개장 여부
    """
    now = get_current_time(KST if market == "KR" else EST)
    today = now.strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=월요일, 6=일요일
    
    # 주말 확인
    if weekday >= 5:  # 토, 일
        return False
    
    # 시장별 운영 시간 확인
    if market == "KR":
        start_time = config.KR_MARKET_OPEN_TIME
        end_time = config.KR_MARKET_CLOSE_TIME
    else:
        start_time = config.US_MARKET_OPEN_TIME
        end_time = config.US_MARKET_CLOSE_TIME
    
    # 시간 변환
    start_dt = datetime.datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.datetime.strptime(f"{today} {end_time}", "%Y-%m-%d %H:%M")
    
    # 현재 시간에서 시간/분만 추출
    current_time = now.replace(tzinfo=None)
    
    # 시장 개장 시간인지 확인
    return start_dt <= current_time <= end_dt

def format_timestamp(timestamp, format_str='%Y-%m-%d %H:%M:%S', timezone=KST):
    """
    타임스탬프를 포맷된 문자열로 변환
    
    Args:
        timestamp: 변환할 타임스탬프
        format_str: 시간 포맷
        timezone: 시간대 (KST, EST 또는 pytz.timezone 객체)
        
    Returns:
        str: 포맷된 시간 문자열
    """
    dt = datetime.datetime.fromtimestamp(timestamp)
    
    # 문자열로 전달된 timezone을 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            # 알 수 없는 시간대일 경우 기본 KST 사용
            timezone = KST
    
    # timezone이 None이 아닐 경우에만 적용
    if timezone:
        dt = timezone.localize(dt.replace(tzinfo=None))
    
    return dt.strftime(format_str)

def get_market_hours(market="KR"):
    """
    시장 운영 시간 정보를 반환
    
    Args:
        market: 시장 코드 ("KR" 또는 "US")
        
    Returns:
        dict: 시장 운영 시간 정보
    """
    if market == "KR":
        return {
            'start': config.KR_MARKET_OPEN_TIME,
            'end': config.KR_MARKET_CLOSE_TIME,
            'timezone': 'Asia/Seoul'
        }
    else:
        return {
            'start': config.US_MARKET_OPEN_TIME,
            'end': config.US_MARKET_CLOSE_TIME,
            'timezone': 'US/Eastern'
        }

def get_adjusted_time(adjust_days=0, adjust_hours=0, adjust_minutes=0, timezone=KST):
    """
    현재 시간에서 일/시간/분을 조정한 시간 반환
    
    Args:
        adjust_days: 조정할 일 수
        adjust_hours: 조정할 시간
        adjust_minutes: 조정할 분
        timezone: 시간대
        
    Returns:
        datetime: 조정된 시간
    """
    # 문자열로 전달된 timezone 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone = KST
            
    now = get_current_time(timezone)
    adjusted = now + datetime.timedelta(
        days=adjust_days,
        hours=adjust_hours,
        minutes=adjust_minutes
    )
    return adjusted

def get_date_range(days, end_date=None, timezone=KST):
    """
    지정된 일 수만큼의 날짜 범위 반환
    
    Args:
        days: 일 수
        end_date: 종료일 (기본값: 현재 날짜)
        timezone: 시간대
        
    Returns:
        tuple: (시작일, 종료일) 형식의 날짜 범위
    """
    if end_date is None:
        end_date = get_current_time(timezone).date()
    elif isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    start_date = end_date - datetime.timedelta(days=days)
    return start_date, end_date

def get_date_days_ago(days, from_date=None, timezone=KST):
    """
    지정된 날짜에서 일수만큼 이전 날짜를 반환
    
    Args:
        days: 이전으로 돌아갈 일 수
        from_date: 기준 날짜 (기본값: 현재 날짜)
        timezone: 시간대
        
    Returns:
        date: X일 전 날짜
    """
    # 문자열로 전달된 timezone 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone = KST
            
    if from_date is None:
        from_date = get_current_time(timezone).date()
    elif isinstance(from_date, datetime.datetime):
        from_date = from_date.date()
    
    return from_date - datetime.timedelta(days=days)

def get_datetime_from_days_ago(days, timezone=KST):
    """
    현재 기준 X일 전의 날짜와 시간을 반환
    
    Args:
        days: 이전으로 돌아갈 일 수
        timezone: 시간대
        
    Returns:
        datetime: X일 전 날짜와 시간
    """
    # 문자열로 전달된 timezone 처리
    if isinstance(timezone, str):
        try:
            timezone = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone = KST
            
    return get_current_time(timezone) - datetime.timedelta(days=days)