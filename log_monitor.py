#!/usr/bin/env python3
"""
로그 모니터링 도구

API 서버 로그와 트레이딩 로그를 실시간으로 모니터링합니다.
다음 로그 파일들을 모니터링합니다:
- api_server.log
- logs/ 디렉토리의 최신 로그 파일
- stock_analysis.log

사용법: python log_monitor.py [options]
옵션:
  --lines N       시작 시 표시할 로그 줄 수 (기본값: 50)
  --filter TEXT   특정 텍스트를 포함하는 로그만 표시
  --error-only    에러 로그만 표시
  --api-only      API 서버 로그만 표시
  --trade-only    트레이딩 로그만 표시
"""

import os
import sys
import time
import glob
import argparse
import datetime
import re
from collections import deque
import threading
import signal
import curses
import logging

# 상수 정의
LOG_REFRESH_INTERVAL = 0.5  # 로그 새로고침 간격 (초)
MAX_LOG_LINES = 1000        # 메모리에 유지할 최대 로그 라인 수
DEFAULT_DISPLAY_LINES = 50  # 기본적으로 표시할 로그 라인 수

# 로그 색상 정의 (curses 색상 쌍)
COLOR_DEFAULT = 1
COLOR_INFO = 2
COLOR_WARNING = 3
COLOR_ERROR = 4
COLOR_CRITICAL = 5
COLOR_TRADE = 6
COLOR_API = 7
COLOR_TIME = 8

# 로그 레벨 패턴
DEBUG_PATTERN = r'\bDEBUG\b'
INFO_PATTERN = r'\bINFO\b'
WARNING_PATTERN = r'\bWARNING\b'
ERROR_PATTERN = r'\b(ERROR|CRITICAL|EXCEPTION)\b'
TRADE_PATTERN = r'\b(매수|매도|거래|주문|체결)\b'

# 로그 파일 경로
API_SERVER_LOG = 'api_server.log'
STOCK_ANALYSIS_LOG = 'stock_analysis.log'
TRADING_LOGS_DIR = 'logs'

class LogMonitor:
    def __init__(self, args):
        self.args = args
        self.logs = deque(maxlen=MAX_LOG_LINES)
        self.log_files = {}
        self.should_exit = False
        self.filter_text = args.filter
        self.error_only = args.error_only
        self.api_only = args.api_only
        self.trade_only = args.trade_only
        self.display_lines = args.lines
        self.mutex = threading.Lock()
        self.setup_logging()

    def setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('log_monitor.log')
            ]
        )
        self.logger = logging.getLogger('LogMonitor')

    def find_latest_log_files(self):
        """최신 로그 파일 찾기"""
        log_files = {}
        
        # API 서버 로그
        if os.path.exists(API_SERVER_LOG) and not self.trade_only:
            log_files['api'] = API_SERVER_LOG
            
        # 스톡 분석 로그
        if os.path.exists(STOCK_ANALYSIS_LOG) and not self.trade_only:
            log_files['analysis'] = STOCK_ANALYSIS_LOG
            
        # 트레이딩 로그 (최신 파일)
        if os.path.exists(TRADING_LOGS_DIR) and not self.api_only:
            # 오더 로그 (최신 파일)
            order_logs = sorted(glob.glob(f'{TRADING_LOGS_DIR}/order_log_*.log'), key=os.path.getmtime, reverse=True)
            if order_logs:
                log_files['order'] = order_logs[0]
                
            # 트레이딩 로그 (최신 파일)
            trading_logs = sorted(glob.glob(f'{TRADING_LOGS_DIR}/trading_log_*.log'), key=os.path.getmtime, reverse=True)
            if trading_logs:
                log_files['trading'] = trading_logs[0]
        
        return log_files

    def tail_logs(self):
        """로그 파일을 tail하는 스레드 함수"""
        while not self.should_exit:
            try:
                current_files = self.find_latest_log_files()
                
                # 새 로그 파일 추가 및 수정된 기존 로그 파일 처리
                for log_type, file_path in current_files.items():
                    file_info = self.log_files.get(log_type)
                    
                    # 새 로그 파일이거나 파일이 변경된 경우
                    if not file_info or file_path != file_info['path']:
                        # 파일 존재 여부 확인
                        if not os.path.exists(file_path):
                            continue
                            
                        try:
                            # 이미 열려있는 파일 핸들 닫기
                            if file_info and 'handle' in file_info and file_info['handle']:
                                file_info['handle'].close()
                                
                            # 새 파일 열기
                            file_handle = open(file_path, 'r')
                            # 파일의 마지막 부분으로 이동 (처음 실행 시 기존 로그는 무시)
                            file_handle.seek(0, os.SEEK_END)
                            
                            self.log_files[log_type] = {
                                'path': file_path,
                                'handle': file_handle,
                                'position': file_handle.tell()
                            }
                            
                            self.logger.info(f"로그 파일 모니터링 시작: {file_path}")
                        except Exception as e:
                            self.logger.error(f"로그 파일 열기 실패: {file_path} - {e}")
                    
                # 모든 로그 파일에서 새 로그 라인 읽기
                for log_type, file_info in self.log_files.items():
                    try:
                        file_handle = file_info['handle']
                        file_handle.seek(file_info['position'])
                        
                        new_lines = file_handle.readlines()
                        if new_lines:
                            for line in new_lines:
                                line = line.strip()
                                if line:
                                    # 필터 적용
                                    if self.should_display_log(line):
                                        # 로그 타입 태그 추가
                                        tagged_line = f"[{log_type.upper()}] {line}"
                                        with self.mutex:
                                            self.logs.append(tagged_line)
                            
                            # 파일 위치 업데이트
                            file_info['position'] = file_handle.tell()
                    except Exception as e:
                        self.logger.error(f"로그 읽기 실패 ({log_type}): {e}")
                
                # 잠시 대기
                time.sleep(LOG_REFRESH_INTERVAL)
            
            except Exception as e:
                self.logger.error(f"로그 모니터링 중 오류 발생: {e}")
                time.sleep(LOG_REFRESH_INTERVAL * 2)  # 오류 발생 시 더 오래 대기
    
    def should_display_log(self, log_line):
        """로그를 표시할지 결정"""
        # 에러 로그만 표시하는 경우
        if self.error_only and not re.search(ERROR_PATTERN, log_line, re.IGNORECASE):
            return False
            
        # 필터 텍스트가 있으면 확인
        if self.filter_text and self.filter_text.lower() not in log_line.lower():
            return False
            
        return True
    
    def get_log_color(self, log_line):
        """로그 라인의 색상 결정"""
        if re.search(ERROR_PATTERN, log_line, re.IGNORECASE):
            return COLOR_ERROR
        elif re.search(WARNING_PATTERN, log_line, re.IGNORECASE):
            return COLOR_WARNING
        elif re.search(TRADE_PATTERN, log_line, re.IGNORECASE):
            return COLOR_TRADE
        elif '[API]' in log_line:
            return COLOR_API
        elif re.search(INFO_PATTERN, log_line, re.IGNORECASE):
            return COLOR_INFO
        else:
            return COLOR_DEFAULT
    
    def display_logs(self, stdscr):
        """curses를 사용하여 로그 표시"""
        curses.curs_set(0)  # 커서 숨기기
        curses.start_color()
        curses.use_default_colors()
        
        # 색상 쌍 초기화
        curses.init_pair(COLOR_DEFAULT, curses.COLOR_WHITE, -1)
        curses.init_pair(COLOR_INFO, curses.COLOR_CYAN, -1)
        curses.init_pair(COLOR_WARNING, curses.COLOR_YELLOW, -1)
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_CRITICAL, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(COLOR_TRADE, curses.COLOR_GREEN, -1)
        curses.init_pair(COLOR_API, curses.COLOR_MAGENTA, -1)
        curses.init_pair(COLOR_TIME, curses.COLOR_BLUE, -1)
        
        # 화면 크기 가져오기
        max_y, max_x = stdscr.getmaxyx()
        
        # 명령 표시 영역 높이
        cmd_area_height = 3
        log_area_height = max_y - cmd_area_height
        
        # 스크롤 위치
        scroll_position = 0
        
        while not self.should_exit:
            try:
                stdscr.clear()
                
                # 현재 시간 및 상태 표시
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                status_line = f" Log Monitor - {current_time} | "
                if self.filter_text:
                    status_line += f"Filter: {self.filter_text} | "
                if self.error_only:
                    status_line += "Errors only | "
                if self.api_only:
                    status_line += "API logs only | "
                if self.trade_only:
                    status_line += "Trade logs only | "
                    
                file_count = len(self.log_files)
                status_line += f"Monitoring {file_count} log files"
                
                stdscr.addstr(0, 0, status_line[:max_x-1], curses.color_pair(COLOR_INFO))
                stdscr.hline(1, 0, '-', max_x)
                
                # 명령 도움말
                help_text = " q:종료 | f:필터 | e:에러만 | r:필터초기화 | ↑/↓:스크롤 | h:도움말"
                stdscr.addstr(max_y - cmd_area_height + 1, 0, help_text[:max_x-1], curses.color_pair(COLOR_DEFAULT))
                
                # 로그 표시
                with self.mutex:
                    # 표시할 수 있는 로그 라인 수 제한
                    total_logs = len(self.logs)
                    
                    # 스크롤 범위 조정
                    if scroll_position > total_logs - log_area_height:
                        scroll_position = max(0, total_logs - log_area_height)
                    
                    # 로그 표시 범위 계산
                    start_idx = max(0, total_logs - log_area_height - scroll_position)
                    end_idx = total_logs - scroll_position
                    
                    display_logs = list(self.logs)[start_idx:end_idx]
                    
                    # 로그 표시
                    for i, log in enumerate(display_logs):
                        if i >= log_area_height - 1:  # 명령줄 공간 확보
                            break
                            
                        # 로그 색상 결정
                        color = self.get_log_color(log)
                        
                        # 시간 부분 추출 및 다른 색상으로 표시
                        time_match = re.search(r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', log)
                        if time_match:
                            time_part = time_match.group(1)
                            time_pos = log.find(time_part)
                            before_time = log[:time_pos]
                            after_time = log[time_pos + len(time_part):]
                            
                            # 로그 표시
                            line_pos = 2 + i  # 상단 상태표시줄 2줄 아래부터
                            x_pos = 0
                            
                            if before_time:
                                stdscr.addstr(line_pos, x_pos, before_time[:max_x], curses.color_pair(color))
                                x_pos += len(before_time)
                                
                            if time_part:
                                stdscr.addstr(line_pos, x_pos, time_part[:max_x-x_pos], curses.color_pair(COLOR_TIME))
                                x_pos += len(time_part)
                                
                            if after_time:
                                stdscr.addstr(line_pos, x_pos, after_time[:max_x-x_pos], curses.color_pair(color))
                        else:
                            # 시간 정보가 없는 경우 전체를 한 색상으로
                            stdscr.addstr(2 + i, 0, log[:max_x-1], curses.color_pair(color))
                
                # 화면 갱신
                stdscr.refresh()
                
                # 키 입력 대기 (0.1초 타임아웃)
                stdscr.timeout(100)
                key = stdscr.getch()
                
                # 키 처리
                if key == ord('q'):  # 종료
                    self.should_exit = True
                elif key == ord('f'):  # 필터 변경
                    stdscr.addstr(max_y - 1, 0, "필터 입력: ", curses.color_pair(COLOR_DEFAULT))
                    curses.echo()
                    curses.curs_set(1)  # 커서 보이기
                    filter_text = stdscr.getstr(max_y - 1, 11, 50).decode('utf-8')
                    self.filter_text = filter_text if filter_text else None
                    curses.curs_set(0)  # 커서 숨기기
                    curses.noecho()
                elif key == ord('e'):  # 에러 로그만 토글
                    self.error_only = not self.error_only
                elif key == ord('r'):  # 필터 초기화
                    self.filter_text = None
                    self.error_only = False
                    self.api_only = False
                    self.trade_only = False
                elif key == curses.KEY_UP:  # 위로 스크롤
                    scroll_position = min(total_logs - 1, scroll_position + 1)
                elif key == curses.KEY_DOWN:  # 아래로 스크롤
                    scroll_position = max(0, scroll_position - 1)
                elif key == ord('h'):  # 도움말
                    self.show_help(stdscr)
                
            except Exception as e:
                self.logger.error(f"화면 표시 중 오류 발생: {e}")
                time.sleep(1)
    
    def show_help(self, stdscr):
        """도움말 표시"""
        max_y, max_x = stdscr.getmaxyx()
        
        help_text = [
            "로그 모니터 도움말",
            "----------------",
            "",
            "q: 프로그램 종료",
            "f: 필터 텍스트 설정 (로그에서 특정 문자열 검색)",
            "e: 에러 로그만 표시 토글",
            "a: API 서버 로그만 표시 토글",
            "t: 트레이딩 로그만 표시 토글",
            "r: 모든 필터 초기화",
            "↑/↓: 로그 스크롤",
            "h: 이 도움말 표시",
            "",
            "아무 키나 누르면 돌아갑니다..."
        ]
        
        stdscr.clear()
        for i, line in enumerate(help_text):
            if i >= max_y:
                break
            stdscr.addstr(i, 0, line[:max_x-1], curses.color_pair(COLOR_DEFAULT))
        
        stdscr.refresh()
        stdscr.timeout(-1)  # 키 입력 대기 (무한정)
        stdscr.getch()
        stdscr.timeout(100)  # 타임아웃 복원
    
    def load_initial_logs(self):
        """초기 실행 시 기존 로그 불러오기"""
        self.logger.info("초기 로그 파일 로딩 중...")
        
        # 로그 파일 목록 가져오기
        log_files = self.find_latest_log_files()
        
        for log_type, file_path in log_files.items():
            try:
                # 파일이 존재하는지 확인
                if not os.path.exists(file_path):
                    continue
                    
                # 파일 열기
                with open(file_path, 'r') as f:
                    # 파일의 끝 부분으로 이동 (필요한만큼의 라인만 읽기 위해)
                    f.seek(0, os.SEEK_END)
                    file_size = f.tell()
                    
                    # 대략적으로 필요한 바이트 수 계산 (라인당 평균 100바이트 가정)
                    bytes_to_read = min(file_size, self.display_lines * 200)
                    
                    # 파일 포인터 이동
                    f.seek(max(0, file_size - bytes_to_read), os.SEEK_SET)
                    
                    # 첫 번째 줄은 일부만 읽힐 수 있으므로 무시
                    if bytes_to_read < file_size:
                        f.readline()
                    
                    # 필요한 줄 수만큼 읽기
                    lines = f.readlines()
                    filtered_lines = []
                    
                    for line in lines:
                        line = line.strip()
                        if line and self.should_display_log(line):
                            tagged_line = f"[{log_type.upper()}] {line}"
                            filtered_lines.append(tagged_line)
                    
                    # 필요한 줄 수만큼만 가져오기
                    lines_to_add = filtered_lines[-self.display_lines:] if len(filtered_lines) > self.display_lines else filtered_lines
                    
                    # 로그 추가
                    with self.mutex:
                        for line in lines_to_add:
                            self.logs.append(line)
                            
                    self.logger.info(f"{log_type} 로그에서 {len(lines_to_add)}줄 로드됨")
            
            except Exception as e:
                self.logger.error(f"초기 로그 로딩 중 오류: {file_path} - {e}")
    
    def run(self):
        """모니터링 시작"""
        self.logger.info("로그 모니터링 시작...")
        
        # 초기 로그 로드
        self.load_initial_logs()
        
        # 로그 테일링 스레드 시작
        tail_thread = threading.Thread(target=self.tail_logs, daemon=True)
        tail_thread.start()
        
        # curses 인터페이스 시작
        try:
            curses.wrapper(self.display_logs)
        except Exception as e:
            self.logger.error(f"UI 표시 중 오류 발생: {e}")
        finally:
            # 종료 처리
            self.should_exit = True
            tail_thread.join(timeout=1.0)
            
            # 파일 핸들 정리
            for log_type, file_info in self.log_files.items():
                if 'handle' in file_info and file_info['handle']:
                    try:
                        file_info['handle'].close()
                    except Exception:
                        pass
            
            self.logger.info("로그 모니터링 종료")

def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C)"""
    print("\n프로그램 종료 중...")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='로그 모니터링 도구')
    parser.add_argument('--lines', type=int, default=DEFAULT_DISPLAY_LINES,
                        help=f'시작 시 표시할 로그 줄 수 (기본값: {DEFAULT_DISPLAY_LINES})')
    parser.add_argument('--filter', type=str, default=None,
                        help='특정 텍스트를 포함하는 로그만 표시')
    parser.add_argument('--error-only', action='store_true',
                        help='에러 로그만 표시')
    parser.add_argument('--api-only', action='store_true',
                        help='API 서버 로그만 표시')
    parser.add_argument('--trade-only', action='store_true',
                        help='트레이딩 로그만 표시')
    
    args = parser.parse_args()
    
    # 시그널 핸들러 설정
    signal.signal(signal.SIGINT, signal_handler)
    
    # 로그 모니터 실행
    monitor = LogMonitor(args)
    monitor.run()

if __name__ == '__main__':
    main()