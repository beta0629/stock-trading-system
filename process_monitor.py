#!/usr/bin/env python3
"""
주식 분석 시스템 프로세스 모니터링 및 관리 스크립트
- 실행 중인 Python 프로세스 확인
- 시스템 프로세스 상태 확인
- 좀비 프로세스 정리
- 필요시 main.py 및 api_server.py 자동 재시작
"""
import os
import sys
import time
import signal
import logging
import subprocess
import argparse
import psutil
from datetime import datetime, timedelta

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('process_monitor.log')
    ]
)
logger = logging.getLogger('ProcessMonitor')

class ProcessMonitor:
    """프로세스 모니터링 및 관리 클래스"""

    def __init__(self, target_script="main.py", check_interval=60, auto_restart=True,
                 max_memory_percent=90, max_cpu_percent=95, monitor_api_server=True):
        """
        초기화 함수
        
        Args:
            target_script: 모니터링 및 재시작 대상 스크립트
            check_interval: 프로세스 확인 간격 (초)
            auto_restart: 자동 재시작 활성화 여부
            max_memory_percent: 최대 메모리 사용률 (이 값 이상이면 경고)
            max_cpu_percent: 최대 CPU 사용률 (이 값 이상이면 경고)
            monitor_api_server: API 서버도 모니터링할지 여부
        """
        self.target_script = target_script
        self.check_interval = check_interval
        self.auto_restart = auto_restart
        self.max_memory_percent = max_memory_percent
        self.max_cpu_percent = max_cpu_percent
        self.running = False
        self.pid_file = "stock_analysis.pid"
        self.api_server_pid_file = "api_server.pid"
        self.monitor_api_server = monitor_api_server
        
        # 스크립트 경로 (상대 경로를 절대 경로로 변환)
        if not os.path.isabs(target_script):
            self.script_path = os.path.join(os.getcwd(), target_script)
        else:
            self.script_path = target_script
            
        # API 서버 스크립트 경로
        self.api_server_path = os.path.join(os.getcwd(), "api_server.py")
            
        logger.info(f"프로세스 모니터 초기화: 대상 스크립트={self.target_script}" +
                   (f", API 서버 모니터링={self.monitor_api_server}" if self.monitor_api_server else ""))

    def find_process_by_name(self, script_name):
        """
        이름으로 프로세스 찾기
        
        Args:
            script_name: 찾을 스크립트 이름
            
        Returns:
            발견된 프로세스 객체 리스트
        """
        target_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
            try:
                cmdline = proc.info['cmdline']
                # None이 아니고 빈 리스트가 아닌지 확인
                if cmdline and len(cmdline) > 1:
                    # 명령줄에 스크립트 이름이 포함되어 있는지 확인
                    if any(script_name in cmd for cmd in cmdline):
                        target_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        return target_processes

    def check_pid_file(self, pid_file=None):
        """
        PID 파일에서 프로세스 ID 확인
        
        Args:
            pid_file: 확인할 PID 파일 (기본값: self.pid_file)
            
        Returns:
            int 또는 None: 프로세스 ID 또는 파일이 없거나 유효하지 않을 경우 None
        """
        if pid_file is None:
            pid_file = self.pid_file
            
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                    if psutil.pid_exists(pid):
                        return pid
                    else:
                        logger.warning(f"PID 파일이 존재하지만, 프로세스({pid})가 실행 중이지 않습니다.")
            except Exception as e:
                logger.error(f"PID 파일 확인 중 오류 발생: {e}")
                
        return None

    def write_pid_file(self, pid, pid_file=None):
        """
        PID를 파일에 저장
        
        Args:
            pid: 저장할 프로세스 ID
            pid_file: 저장할 PID 파일 (기본값: self.pid_file)
        """
        if pid_file is None:
            pid_file = self.pid_file
            
        try:
            with open(pid_file, 'w') as f:
                f.write(str(pid))
            logger.info(f"PID {pid}를 파일 {pid_file}에 저장했습니다.")
        except Exception as e:
            logger.error(f"PID 파일 {pid_file} 저장 중 오류 발생: {e}")

    def check_system_resources(self):
        """
        시스템 리소스 확인
        
        Returns:
            bool: 리소스가 충분하면 True, 부족하면 False
        """
        try:
            # 메모리 사용량 확인
            memory = psutil.virtual_memory()
            if memory.percent >= self.max_memory_percent:
                logger.warning(f"메모리 사용량이 높습니다: {memory.percent}% (최대 허용: {self.max_memory_percent}%)")
                return False
                
            # CPU 사용량 확인
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent >= self.max_cpu_percent:
                logger.warning(f"CPU 사용량이 높습니다: {cpu_percent}% (최대 허용: {self.max_cpu_percent}%)")
                return False
                
            # 디스크 공간 확인
            disk = psutil.disk_usage('/')
            if disk.percent >= 90:
                logger.warning(f"디스크 사용량이 높습니다: {disk.percent}%")
                return False
                
            logger.info(f"시스템 리소스 정상 - 메모리: {memory.percent}%, CPU: {cpu_percent}%, 디스크: {disk.percent}%")
            return True
            
        except Exception as e:
            logger.error(f"시스템 리소스 확인 중 오류 발생: {e}")
            return True  # 오류 시 기본적으로 계속 진행

    def clean_zombie_processes(self):
        """
        좀비 상태의 프로세스 정리
        
        Returns:
            int: 정리된 좀비 프로세스 수
        """
        cleaned_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            try:
                # 좀비 프로세스인지 확인
                if proc.info['status'] == psutil.STATUS_ZOMBIE:
                    proc_name = proc.info['name']
                    proc_pid = proc.info['pid']
                    logger.info(f"좀비 프로세스 발견: {proc_name} (PID: {proc_pid})")
                    
                    try:
                        os.kill(proc_pid, signal.SIGKILL)
                        logger.info(f"좀비 프로세스 종료 시도: {proc_pid}")
                        cleaned_count += 1
                    except (ProcessLookupError, PermissionError) as e:
                        logger.warning(f"프로세스 {proc_pid} 종료 실패: {e}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return cleaned_count

    def start_target_process(self, script_path=None, pid_file=None):
        """
        대상 프로세스 시작
        
        Args:
            script_path: 시작할 스크립트 경로 (기본값: self.script_path)
            pid_file: PID 저장 파일 (기본값: self.pid_file)
            
        Returns:
            int 또는 None: 시작된 프로세스 ID 또는 실패 시 None
        """
        if script_path is None:
            script_path = self.script_path
            
        if pid_file is None:
            pid_file = self.pid_file
            
        try:
            # 현재 환경 변수 복사
            env = os.environ.copy()
            
            # 표준 출력 및 표준 오류를 로그 파일로 리다이렉션
            script_name = os.path.basename(script_path)
            log_file = f"{os.path.splitext(script_name)[0]}.log"
            with open(log_file, 'a') as f:
                logger.info(f"대상 스크립트 시작: {script_path} (로그: {log_file})")
                
                # 백그라운드에서 프로세스 실행
                process = subprocess.Popen(
                    [sys.executable, script_path],
                    stdout=f,
                    stderr=f,
                    env=env,
                    start_new_session=True  # 새 프로세스 그룹에서 실행하여 부모 종료 시 영향 받지 않도록
                )
                
                logger.info(f"프로세스 시작됨: PID={process.pid}")
                return process.pid
                
        except Exception as e:
            logger.error(f"프로세스 시작 중 오류 발생: {e}")
            return None

    def check_process_health(self, target_pid=None):
        """
        특정 프로세스의 상태 확인
        
        Args:
            target_pid: 확인할 프로세스 ID
            
        Returns:
            bool: 프로세스가 정상이면 True, 그렇지 않으면 False
        """
        try:
            if target_pid and psutil.pid_exists(target_pid):
                # 프로세스 객체 가져오기
                process = psutil.Process(target_pid)
                
                # 프로세스 상태 확인
                if process.status() in [psutil.STATUS_RUNNING, psutil.STATUS_SLEEPING]:
                    # CPU 및 메모리 사용량 확인
                    memory_info = process.memory_percent()
                    cpu_percent = process.cpu_percent(interval=0.5)
                    
                    logger.info(f"프로세스 {target_pid} 상태: 정상 (CPU: {cpu_percent:.1f}%, 메모리: {memory_info:.1f}%)")
                    return True
                else:
                    logger.warning(f"프로세스 {target_pid} 상태 비정상: {process.status()}")
                    return False
            else:
                logger.warning(f"프로세스 {target_pid}가 실행 중이지 않습니다.")
                return False
                
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"프로세스 {target_pid} 상태 확인 중 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"프로세스 상태 확인 중 예상치 못한 오류: {e}")
            return False

    def kill_process(self, pid):
        """
        프로세스 강제 종료
        
        Args:
            pid: 종료할 프로세스 ID
            
        Returns:
            bool: 종료 성공 여부
        """
        try:
            if psutil.pid_exists(pid):
                os.kill(pid, signal.SIGTERM)
                logger.info(f"프로세스 {pid}에 SIGTERM 신호 전송")
                
                # 프로세스가 종료될 때까지 최대 5초 대기
                wait_time = 0
                while psutil.pid_exists(pid) and wait_time < 5:
                    time.sleep(1)
                    wait_time += 1
                
                # 프로세스가 여전히 존재하면 SIGKILL 보내기
                if psutil.pid_exists(pid):
                    os.kill(pid, signal.SIGKILL)
                    logger.info(f"프로세스 {pid}에 SIGKILL 신호 전송")
                    time.sleep(1)
                
                return not psutil.pid_exists(pid)
            else:
                logger.warning(f"PID {pid}를 가진 프로세스가 존재하지 않습니다.")
                return True
        except Exception as e:
            logger.error(f"프로세스 {pid} 종료 중 오류 발생: {e}")
            return False

    def restart_process(self, script_path, pid_file):
        """
        특정 프로세스 재시작
        
        Args:
            script_path: 재시작할 스크립트 경로
            pid_file: PID 저장 파일
            
        Returns:
            bool: 재시작 성공 여부
        """
        # 이전 PID 확인
        old_pid = self.check_pid_file(pid_file)
        
        # 기존 프로세스 종료
        if old_pid:
            success = self.kill_process(old_pid)
            if not success:
                logger.error(f"기존 프로세스 {old_pid} 종료 실패")
                return False
        
        # PID 파일 삭제
        if os.path.exists(pid_file):
            os.remove(pid_file)
        
        # 프로세스 재시작
        new_pid = self.start_target_process(script_path, pid_file)
        if new_pid:
            self.write_pid_file(new_pid, pid_file)
            logger.info(f"프로세스 재시작 성공: {script_path}, PID={new_pid}")
            return True
        else:
            logger.error(f"프로세스 재시작 실패: {script_path}")
            return False

    def check_api_server(self):
        """
        API 서버 프로세스 확인 및 관리
        
        Returns:
            bool: API 서버가 정상이면 True, 그렇지 않으면 False
        """
        if not self.monitor_api_server:
            return True
            
        # 1. PID 파일에서 API 서버 프로세스 ID 확인
        api_server_pid = self.check_pid_file(self.api_server_pid_file)
        
        # 2. PID 파일이 없으면 실행 중인 API 서버 프로세스 찾기
        if api_server_pid is None:
            api_server_processes = self.find_process_by_name("api_server.py")
            if api_server_processes:
                api_server_pid = api_server_processes[0].pid
                logger.info(f"'api_server.py' 프로세스를 찾았습니다: PID={api_server_pid}")
                self.write_pid_file(api_server_pid, self.api_server_pid_file)
        
        # 3. API 서버 상태 확인
        api_server_running = False
        if api_server_pid is not None:
            api_server_running = self.check_process_health(api_server_pid)
            
        # 4. 필요시 API 서버 재시작
        if not api_server_running and self.auto_restart:
            logger.info("API 서버가 실행 중이지 않거나 비정상 상태입니다. 재시작합니다.")
            success = self.restart_process(self.api_server_path, self.api_server_pid_file)
            return success
            
        return api_server_running

    def run_monitor(self):
        """
        모니터링 루프 실행
        """
        self.running = True
        restart_count = 0
        api_restart_count = 0
        last_restart_time = datetime.now() - timedelta(hours=1)  # 초기값
        last_api_restart_time = datetime.now() - timedelta(hours=1)  # 초기값
        
        logger.info("프로세스 모니터링 시작")
        
        # API 서버 상태 먼저 확인하고 필요시 재시작
        if self.monitor_api_server:
            self.check_api_server()
        
        while self.running:
            try:
                # 1. 시스템 리소스 확인
                resources_ok = self.check_system_resources()
                if not resources_ok:
                    logger.warning("시스템 리소스 부족. 프로세스 재시작을 일시 중단합니다.")
                    time.sleep(self.check_interval * 2)  # 리소스 부족 시 체크 간격 2배로
                    continue
                
                # 2. 좀비 프로세스 정리
                cleaned_count = self.clean_zombie_processes()
                if cleaned_count > 0:
                    logger.info(f"{cleaned_count}개의 좀비 프로세스를 정리했습니다.")
                
                # 3. API 서버 상태 확인 및 관리
                if self.monitor_api_server:
                    # 마지막 API 서버 재시작 이후 경과 시간 확인
                    time_since_api_restart = (datetime.now() - last_api_restart_time).total_seconds()
                    
                    if time_since_api_restart >= 60:  # 최소 60초 간격으로 재시작
                        api_server_ok = self.check_api_server()
                        
                        if not api_server_ok:
                            logger.warning("API 서버 상태 비정상. 재시작합니다.")
                            success = self.restart_process(self.api_server_path, self.api_server_pid_file)
                            
                            if success:
                                last_api_restart_time = datetime.now()
                                api_restart_count += 1
                                logger.info(f"API 서버 재시작 완료 (재시작 횟수: {api_restart_count})")
                
                # 4. PID 파일에서 메인 프로세스 ID 확인
                target_pid = self.check_pid_file()
                
                # 5. PID 파일이 없으면 실행 중인 프로세스 찾기
                if target_pid is None:
                    target_processes = self.find_process_by_name(self.target_script)
                    if target_processes:
                        target_pid = target_processes[0].pid
                        logger.info(f"'{self.target_script}' 프로세스를 찾았습니다: PID={target_pid}")
                        self.write_pid_file(target_pid)
                
                # 6. 메인 프로세스 상태 확인
                process_running = False
                if target_pid is not None:
                    process_running = self.check_process_health(target_pid)
                
                # 7. 필요시 메인 프로세스 재시작
                if not process_running and self.auto_restart:
                    # 빠르게 연속적인 재시작 방지
                    time_since_last_restart = (datetime.now() - last_restart_time).total_seconds()
                    if time_since_last_restart < 60:
                        logger.warning(f"마지막 재시작 후 {time_since_last_restart:.1f}초 경과. 재시작 지연...")
                        time.sleep(60 - time_since_last_restart)  # 최소 60초 간격으로 재시작
                    
                    restart_count += 1
                    logger.info(f"메인 프로세스가 실행 중이지 않습니다. 재시작합니다. (시도 #{restart_count})")
                    
                    success = self.restart_process(self.script_path, self.pid_file)
                    if success:
                        last_restart_time = datetime.now()
                
                # 8. 대기
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("사용자 중단. 모니터링을 종료합니다.")
                self.running = False
            except Exception as e:
                logger.error(f"모니터링 중 오류 발생: {e}")
                time.sleep(self.check_interval)
        
        logger.info("프로세스 모니터링 종료")

    def stop(self):
        """모니터링 중지"""
        self.running = False
        logger.info("프로세스 모니터링 중지 명령 수신")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="프로세스 모니터링 및 자동 재시작 도구")
    parser.add_argument("--script", "-s", default="main.py", help="모니터링할 스크립트 이름 (기본값: main.py)")
    parser.add_argument("--interval", "-i", type=int, default=60, help="모니터링 간격(초) (기본값: 60)")
    parser.add_argument("--no-restart", "-n", action="store_true", help="자동 재시작 비활성화")
    parser.add_argument("--start", "-r", action="store_true", help="스크립트 즉시 시작")
    parser.add_argument("--api-server", "-a", action="store_true", help="API 서버도 모니터링")
    parser.add_argument("--restart-api", action="store_true", help="API 서버 즉시 재시작")
    
    args = parser.parse_args()
    
    monitor = ProcessMonitor(
        target_script=args.script,
        check_interval=args.interval,
        auto_restart=not args.no_restart,
        monitor_api_server=True  # 기본적으로 API 서버 모니터링 활성화
    )
    
    # API 서버 즉시 재시작 옵션
    if args.restart_api:
        logger.info("API 서버를 즉시 재시작합니다.")
        monitor.restart_process(monitor.api_server_path, monitor.api_server_pid_file)
    
    # 스크립트 즉시 시작 옵션
    if args.start:
        logger.info(f"'{args.script}' 스크립트를 즉시 시작합니다.")
        pid = monitor.start_target_process()
        if pid:
            monitor.write_pid_file(pid)
    
    # 모니터링 시작
    monitor.run_monitor()

if __name__ == "__main__":
    main()