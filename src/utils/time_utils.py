#!/usr/bin/env python3
"""
시간 관련 유틸리티 모듈

이 모듈은 한국 시간(KST)과 미국 동부 시간(EST) 관련 기능을 제공합니다.
시간 변환, 시장 개장 여부 확인 등의 기능을 포함합니다.
"""

import datetime
import os
import pytz
import logging

# 로거 설정
logger = logging.getLogger('TimeUtils')

try:
    import config
except ImportError:
    logger.warning("config 모듈을 가져올 수 없습니다. 환경 변수에서 설정을 가져옵니다.")
    config = None

# 타임존 설정
KST = pytz.timezone('Asia/Seoul')
EST = pytz.timezone('US/Eastern')

# 시장 설정 기본값
DEFAULT_KR_MARKET_OPEN_TIME = "09:00"
DEFAULT_KR_MARKET_CLOSE_TIME = "15:30"
DEFAULT_US_MARKET_OPEN_TIME = "09:30"
DEFAULT_US_MARKET_CLOSE_TIME = "16:00"

def get_config_value(attr_name, default_value, config_obj=None):
    """
    config 객체나 환경 변수에서 설정 값을 가져옵니다.
    
    Args:
        attr_name: 설정 속성 이름
        default_value: 기본값
        config_obj: 설정 객체 (None일 경우 환경 변수 사용)
        
    Returns:
        설정 값
    """
    if config_obj is not None:
        return getattr(config_obj, attr_name, default_value)
    
    try:
        if config is not None:
            return getattr(config, attr_name, default_value)
    except Exception:
        pass
    
    # 환경 변수에서 가져오기
    env_name = attr_name.upper()
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value
    
    return default_value

def now(timezone=KST):
    """
    현재 시간을 지정된 시간대로 반환 (get_current_time의 별칭)
    
    Args:
        timezone: 시간대 (기본값: KST)
        
    Returns:
        datetime: 현재 시간 (해당 시간대)
    """
    return get_current_time(timezone)

def format_time(dt=None, format_string='%Y-%m-%d %H:%M:%S', timezone=KST):
    """
    datetime 객체를 포맷된 문자열로 변환
    
    Args:
        dt: 변환할 datetime 객체 (기본값: 현재 시간)
        format_string: 시간 포맷 (기본값: '%Y-%m-%d %H:%M:%S')
        timezone: 시간대
        
    Returns:
        str: 포맷된 시간 문자열
    """
    if dt is None:
        dt = get_current_time(timezone)
    
    # 시간대 설정이 되어 있지 않으면 설정
    if dt.tzinfo is None:
        dt = timezone.localize(dt)
    
    return dt.strftime(format_string)

def get_korean_datetime_format(dt=None, include_seconds=True):
    """
    한국식 시간 포맷 문자열 반환 (예: 2025년 5월 28일 14:30:25)
    
    Args:
        dt: datetime 객체 (기본값: 현재 시간)
        include_seconds: 초 포함 여부
        
    Returns:
        str: 한국식 포맷의 시간 문자열
    """
    if dt is None:
        dt = get_current_time(KST)
        
    if include_seconds:
        format_str = '%Y년 %m월 %d일 %H:%M:%S'
    else:
        format_str = '%Y년 %m월 %d일 %H:%M'
    
    return dt.strftime(format_str)

def get_market_schedule(date=None, market="KR", config=None):
    """
    특정 날짜의 시장 스케줄 정보 반환
    
    Args:
        date: 날짜 (기본값: 오늘)
        market: 시장 코드 ("KR" 또는 "US")
        config: 설정 모듈
        
    Returns:
        dict: 시장 스케줄 정보
    """
    if date is None:
        date = get_current_time(KST if market == "KR" else EST).date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
        
    # 요일 확인 (0=월요일, 6=일요일)
    weekday = date.weekday()
    is_weekend = weekday >= 5
    
    # 시장 기본 정보 및 설정 가져오기
    if market == "KR":
        timezone = KST
        open_time_str = get_config_value('KR_MARKET_OPEN_TIME', DEFAULT_KR_MARKET_OPEN_TIME, config)
        close_time_str = get_config_value('KR_MARKET_CLOSE_TIME', DEFAULT_KR_MARKET_CLOSE_TIME, config)
    else:  # "US"
        timezone = EST
        open_time_str = get_config_value('US_MARKET_OPEN_TIME', DEFAULT_US_MARKET_OPEN_TIME, config)
        close_time_str = get_config_value('US_MARKET_CLOSE_TIME', DEFAULT_US_MARKET_CLOSE_TIME, config)
    
    # 개장/마감 시간 생성
    open_time = datetime.datetime.strptime(f"{date.strftime('%Y-%m-%d')} {open_time_str}", "%Y-%m-%d %H:%M")
    close_time = datetime.datetime.strptime(f"{date.strftime('%Y-%m-%d')} {close_time_str}", "%Y-%m-%d %H:%M")
    
    # 시간대 정보 추가
    open_time = timezone.localize(open_time)
    close_time = timezone.localize(close_time)
    
    # 개장 여부 결정
    is_open = not is_weekend
    
    # 강제 개장 설정 확인
    force_open = get_config_value('FORCE_MARKET_OPEN', False, config)
    if isinstance(force_open, str):
        force_open = force_open.lower() == "true"
    
    if force_open:
        is_open = True
    
    return {
        'date': date,
        'is_open': is_open,
        'is_weekend': is_weekend,
        'open_time': open_time if is_open else None,
        'close_time': close_time if is_open else None,
        'market': market,
        'timezone': timezone
    }

def get_current_time(timezone=KST, tz=None):
    """
    현재 시간을 지정된 시간대로 반환
    
    Args:
        timezone: 시간대 (기본값: KST)
        tz: timezone의 별칭, 이 인수가 제공되면 timezone보다 우선함
        
    Returns:
        datetime: 현재 시간 (해당 시간대)
    """
    # tz 인자가 제공된 경우 timezone 대신 사용
    if tz is not None:
        timezone = tz
        
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
            
    try:
        # 먼저 ISO 형식 확인 (2025-06-27T10:00:48.152276+09:00)
        if 'T' in time_str and ('+' in time_str or 'Z' in time_str or '-' in time_str.split('T')[1]):
            try:
                # ISO 형식 문자열은 datetime.fromisoformat() 사용 (Python 3.7+)
                dt = datetime.datetime.fromisoformat(time_str)
                
                # 이미 시간대 정보가 있으면 변환만 수행
                if dt.tzinfo:
                    return dt.astimezone(timezone)
                # 시간대 정보가 없으면 지정된 시간대 설정
                return timezone.localize(dt)
            except (ValueError, AttributeError):
                # Python 3.6 이하 또는 다른 오류 발생 시 대체 방법
                import dateutil.parser
                dt = dateutil.parser.parse(time_str)
                if dt.tzinfo:
                    return dt.astimezone(timezone)
                return timezone.localize(dt)
        
        # 표준 형식 파싱
        dt = datetime.datetime.strptime(time_str, format_str)
        return timezone.localize(dt)
        
    except ValueError as e:
        # 파싱 오류 발생 시 원래 오류 메시지와 함께 다시 발생
        logger.error(f"시간 문자열 '{time_str}' 파싱 오류: {e}")
        
        # 최후 대안으로 dateutil.parser 사용
        try:
            import dateutil.parser
            dt = dateutil.parser.parse(time_str)
            if dt.tzinfo:
                return dt.astimezone(timezone)
            return timezone.localize(dt)
        except Exception as e2:
            logger.error(f"dateutil로도 파싱 실패: {e2}")
            raise ValueError(f"시간 문자열 '{time_str}'을 파싱할 수 없습니다.") from e

def is_market_open(market="KR", config=None):
    """
    주식 시장이 현재 개장 중인지 확인
    
    Args:
        market: 시장 코드 ("KR" 또는 "US")
        config: 설정 모듈 (기본값: None, 전역 config 또는 환경 변수 사용)
        
    Returns:
        bool: 시장 개장 여부
    """
    # 시스템 로컬 시간 로깅 (디버깅용)
    system_now = datetime.datetime.now()
    logger.debug(f"시스템 로컬 시간: {system_now}")
    
    # 강제 개장 설정 확인
    force_open = get_config_value('FORCE_MARKET_OPEN', False, config)
    if isinstance(force_open, str):
        force_open = force_open.lower() == "true"
    
    if force_open:
        logger.info(f"FORCE_MARKET_OPEN이 활성화되어 있습니다. 시장({market})을 강제로 열린 상태로 간주합니다.")
        return True
        
    # 시간대 설정
    timezone = KST if market == "KR" else EST
    
    # 현재 시간을 해당 시장의 시간대로 가져옴
    now = get_current_time(timezone)
    today = now.strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=월요일, 6=일요일
    
    # 로깅 추가 - 시간대 정보 확인
    logger.debug(f"{market} 시장 확인: 현재 시간({timezone}): {now}, 요일: {weekday}")
    
    # 주말 확인
    if weekday >= 5:  # 토, 일
        logger.debug(f"{market} 시장 확인: 주말({weekday})이므로 시장 닫힘")
        return False
    
    # 시장별 운영 시간 확인
    if market == "KR":
        start_time = get_config_value('KR_MARKET_OPEN_TIME', DEFAULT_KR_MARKET_OPEN_TIME, config)
        end_time = get_config_value('KR_MARKET_CLOSE_TIME', DEFAULT_KR_MARKET_CLOSE_TIME, config)
    else:
        start_time = get_config_value('US_MARKET_OPEN_TIME', DEFAULT_US_MARKET_OPEN_TIME, config)
        end_time = get_config_value('US_MARKET_CLOSE_TIME', DEFAULT_US_MARKET_CLOSE_TIME, config)
    
    # 시간 변환
    start_dt = datetime.datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.datetime.strptime(f"{today} {end_time}", "%Y-%m-%d %H:%M")
    
    # 시간대 정보 추가
    start_dt = timezone.localize(start_dt)
    end_dt = timezone.localize(end_dt)
    
    # 디버깅을 위한 추가 로깅
    logger.debug(f"{market} 시장 시간: {start_dt} ~ {end_dt}")
    logger.debug(f"{market} 시장 개장 여부 확인 결과: {start_dt <= now <= end_dt}")
    
    # 시장 개장 시간인지 확인 (시간대 정보를 유지한 채 비교)
    return start_dt <= now <= end_dt

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
            'start': get_config_value('KR_MARKET_OPEN_TIME', DEFAULT_KR_MARKET_OPEN_TIME),
            'end': get_config_value('KR_MARKET_CLOSE_TIME', DEFAULT_KR_MARKET_CLOSE_TIME),
            'timezone': 'Asia/Seoul'
        }
    else:
        return {
            'start': get_config_value('US_MARKET_OPEN_TIME', DEFAULT_US_MARKET_OPEN_TIME),
            'end': get_config_value('US_MARKET_CLOSE_TIME', DEFAULT_US_MARKET_CLOSE_TIME),
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

def is_after_market_open(market="KR", config=None):
    """
    시간외 거래(애프터 마켓)가 현재 열려 있는지 확인
    
    Args:
        market: 시장 코드 ("KR" 또는 "US")
        config: 설정 모듈 (기본값: None, 전역 config 또는 환경 변수 사용)
        
    Returns:
        bool: 시간외 거래 개장 여부
    """
    # 시간외 거래 활성화 여부 확인
    if market == "KR":
        after_market_enabled = get_config_value('KR_AFTER_MARKET_ENABLED', False, config)
        after_market_trading = get_config_value('KR_AFTER_MARKET_TRADING', False, config)
    else:  # US 시장
        after_market_enabled = get_config_value('US_AFTER_MARKET_ENABLED', False, config)
        after_market_trading = get_config_value('US_AFTER_MARKET_TRADING', False, config)
    
    # 시간외 거래가 비활성화된 경우 즉시 False 반환
    if not after_market_enabled or not after_market_trading:
        return False
        
    # 강제 개장 설정 확인
    force_open = get_config_value('FORCE_MARKET_OPEN', False, config)
    if isinstance(force_open, str):
        force_open = force_open.lower() == "true"
    
    if force_open:
        return True
        
    now = get_current_time(KST if market == "KR" else EST)
    today = now.strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=월요일, 6=일요일
    
    # 주말 확인
    if weekday >= 5:  # 토, 일
        return False
    
    # 시장별 시간외 거래 시간 확인
    if market == "KR":
        start_time = get_config_value('KR_AFTER_MARKET_OPEN_TIME', "16:00", config)
        end_time = get_config_value('KR_AFTER_MARKET_CLOSE_TIME', "18:00", config)
    else:
        start_time = get_config_value('US_AFTER_MARKET_OPEN_TIME', "16:00", config)
        end_time = get_config_value('US_AFTER_MARKET_CLOSE_TIME', "20:00", config)
    
    # 시간 변환
    start_dt = datetime.datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.datetime.strptime(f"{today} {end_time}", "%Y-%m-%d %H:%M")
    
    # 현재 시간에서 시간/분만 추출
    current_time = now.replace(tzinfo=None)
    
    # 시간외 거래 시간인지 확인
    return start_dt <= current_time <= end_dt

def is_trading_time(market="KR", config=None, include_after_hours=True):
    """
    현재가 거래 시간(정규장 또는 시간외 거래)인지 확인
    
    Args:
        market: 시장 코드 ("KR" 또는 "US")
        config: 설정 모듈
        include_after_hours: 시간외 거래 포함 여부
        
    Returns:
        bool: 거래 가능 시간 여부
    """
    # 강제 개장 설정 확인
    force_open = get_config_value('FORCE_MARKET_OPEN', False, config)
    if isinstance(force_open, str):
        force_open = force_open.lower() == "true"
    
    if force_open:
        return True
    
    # 정규장 확인
    if is_market_open(market, config):
        return True
    
    # 시간외 거래 확인 (설정 활성화 & 포함 옵션 활성화시)
    if include_after_hours:
        use_extended_hours = get_config_value('USE_EXTENDED_HOURS', False, config)
        if use_extended_hours and is_after_market_open(market, config):
            return True
    
    return False