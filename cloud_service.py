#!/usr/bin/env python3
"""
클라우드 환경(GitHub Actions 등)에서 주식 분석 시스템 실행 및 모니터링 스크립트
- 환경 검사 및 초기화
- 의존성 설치
- 서비스 실행 및 모니터링
- 오류 복구 기능
"""
import os
import sys
import subprocess
import time
import logging
import argparse
import signal
import json
from datetime import datetime, timedelta
import traceback
import platform
import atexit

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('cloud_service.log')
    ]
)
logger = logging.getLogger('CloudService')

class CloudService:
    """클라우드 환경에서 서비스 실행 및 모니터링"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 정보 딕셔너리
        """
        self.config = config
        self.is_github_actions = 'GITHUB_ACTIONS' in os.environ
        self.running = False
        self.service_processes = {}  # 실행 중인 프로세스 추적
        self.start_time = datetime.now()
        self.last_resource_check = datetime.now() - timedelta(minutes=10)  # 초기값
        self.own_pid = os.getpid()  # 현재 프로세스의 PID
        
        # 실행 환경 정보
        self.system_info = {
            'platform': platform.system(),
            'release': platform.release(),
            'python_version': platform.python_version(),
            'is_github_actions': self.is_github_actions,
        }
        
        # 종료 핸들러 등록
        atexit.register(self._cleanup_at_exit)
        
        logger.info(f"클라우드 서비스 초기화 - 실행 환경: {json.dumps(self.system_info)}")
    
    def _cleanup_at_exit(self):
        """
        프로그램 종료 시 실행될 정리 함수
        atexit에 의해 자동으로 호출됨
        """
        logger.info("프로그램 종료 감지, 리소스 정리 중...")
        self.stop()
        
        if self.is_github_actions:
            try:
                # GitHub Actions에서는 자신의 프로세스 계층에서 실행하는 Python 프로세스만 종료
                logger.info("GitHub Actions 환경에서 자식 프로세스 정리 중...")
                
                # psutil을 사용해 안전하게 프로세스 검색 및 종료
                try:
                    import psutil
                    
                    current_process = psutil.Process(self.own_pid)
                    
                    # 자신의 자식 프로세스 종료
                    for child in current_process.children(recursive=True):
                        try:
                            logger.info(f"자식 프로세스 종료 시도: PID={child.pid}, 이름={child.name()}")
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.AccessDenied:
                            logger.info(f"프로세스 {child.pid} 종료 권한 없음 (시스템 프로세스로 추정)")
                        except Exception as e:
                            logger.error(f"프로세스 {child.pid} 종료 중 오류: {e}")
                            
                    # 2초 대기 후 여전히 살아있는 자식 프로세스 강제 종료
                    time.sleep(2)
                    for child in current_process.children(recursive=True):
                        try:
                            if child.is_running():
                                logger.info(f"자식 프로세스 강제 종료: PID={child.pid}")
                                child.kill()
                        except Exception:
                            pass
                
                except ImportError:
                    logger.warning("psutil 모듈이 없어 프로세스 정리가 제한됩니다.")
                    
                    # psutil이 없는 경우 직접 등록된 프로세스만 종료
                    for name, process in self.service_processes.items():
                        if process and process.poll() is None:
                            logger.info(f"{name} 프로세스 종료 (PID: {process.pid})")
                            try:
                                process.terminate()
                                time.sleep(1)
                                if process.poll() is None:
                                    process.kill()
                            except Exception as e:
                                logger.error(f"{name} 종료 중 오류: {e}")
            
            except Exception as e:
                logger.error(f"종료 정리 중 오류 발생: {e}")
                traceback.print_exc()

    def check_dependencies(self):
        """
        필요한 의존성 패키지 확인 및 설치
        
        Returns:
            bool: 설치 성공 여부
        """
        try:
            logger.info("의존성 패키지 확인 중...")
            
            # requirements.txt 파일 확인
            req_file = 'requirements.txt'
            if not os.path.exists(req_file):
                logger.warning("requirements.txt 파일이 없습니다.")
                return False
            
            # 필요한 패키지 설치 (pip)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file],
                check=True,
                capture_output=True,
                text=True
            )
            
            logger.info("의존성 패키지 설치 완료")
            logger.debug(f"설치 출력: {result.stdout}")
            
            # process_monitor.py가 필요로 하는 psutil이 설치되어 있는지 확인
            try:
                import psutil
                logger.info("psutil 패키지 사용 가능")
            except ImportError:
                logger.warning("psutil 패키지가 누락되었습니다. 설치 중...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "psutil"],
                    check=True
                )
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"의존성 패키지 설치 중 오류 발생: {e}")
            logger.error(f"오류 출력: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"의존성 확인 중 예상치 못한 오류: {e}")
            return False
    
    def prepare_environment(self):
        """
        실행 환경 준비
        
        Returns:
            bool: 준비 성공 여부
        """
        try:
            logger.info("실행 환경 준비 중...")
            
            # 로그 디렉토리 확인
            if not os.path.exists('logs'):
                os.makedirs('logs')
                logger.info("로그 디렉토리 생성 완료")
            
            # 서비스 실행에 필요한 환경 변수 설정
            if self.is_github_actions:
                # GitHub Actions 환경에서 필요한 환경 변수 설정
                os.environ['STOCK_ANALYSIS_ENV'] = 'github_actions'
                os.environ['CI'] = 'true'
                
                # 타임존 설정 (한국 시간)
                os.environ['TZ'] = 'Asia/Seoul'
                
                logger.info("GitHub Actions 환경 변수 설정 완료")
            
            # 설정 파일 존재 여부 확인
            if not os.path.exists('config.py'):
                logger.error("config.py 파일이 존재하지 않습니다.")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"환경 준비 중 오류 발생: {e}")
            traceback.print_exc()
            return False
    
    def start_process_monitor(self):
        """
        프로세스 모니터 시작
        
        Returns:
            subprocess.Popen 또는 None: 프로세스 객체
        """
        try:
            logger.info("프로세스 모니터 시작 중...")
            
            # process_monitor.py가 존재하는지 확인
            if not os.path.exists('process_monitor.py'):
                logger.error("process_monitor.py 파일이 존재하지 않습니다.")
                return None
            
            # 프로세스 모니터 시작 (main.py를 모니터링 및 자동 시작)
            monitor_process = subprocess.Popen(
                [
                    sys.executable,
                    'process_monitor.py',
                    '--script', 'main.py',
                    '--interval', '30',
                    '--start'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True
            )
            
            # 프로세스가 즉시 종료되지 않았는지 확인
            time.sleep(2)
            if monitor_process.poll() is not None:
                logger.error(f"프로세스 모니터가 즉시 종료됨: {monitor_process.returncode}")
                return None
            
            logger.info(f"프로세스 모니터 시작됨: PID={monitor_process.pid}")
            return monitor_process
            
        except Exception as e:
            logger.error(f"프로세스 모니터 시작 중 오류 발생: {e}")
            traceback.print_exc()
            return None
    
    def start_main_service(self):
        """
        주 서비스 직접 시작 (프로세스 모니터 없이)
        
        Returns:
            subprocess.Popen 또는 None: 프로세스 객체
        """
        try:
            logger.info("주 서비스(main.py) 직접 시작 중...")
            
            # main.py가 존재하는지 확인
            if not os.path.exists('main.py'):
                logger.error("main.py 파일이 존재하지 않습니다.")
                return None
            
            # 로그 파일 경로
            log_file_path = os.path.join('logs', f'main_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            
            # 로그 파일 생성
            log_file = open(log_file_path, 'w')
            
            # 메인 서비스 시작
            main_process = subprocess.Popen(
                [sys.executable, 'main.py'],
                stdout=log_file,
                stderr=log_file,
                text=True,
                start_new_session=True
            )
            
            # 프로세스가 즉시 종료되지 않았는지 확인
            time.sleep(2)
            if main_process.poll() is not None:
                logger.error(f"메인 서비스가 즉시 종료됨: {main_process.returncode}")
                log_file.close()
                return None
            
            logger.info(f"메인 서비스 시작됨: PID={main_process.pid}, 로그={log_file_path}")
            return main_process
            
        except Exception as e:
            logger.error(f"메인 서비스 시작 중 오류 발생: {e}")
            traceback.print_exc()
            return None
    
    def check_process_status(self, process, process_name):
        """
        프로세스 상태 확인
        
        Args:
            process: 확인할 프로세스 객체
            process_name: 프로세스 이름
            
        Returns:
            bool: 프로세스가 실행 중이면 True
        """
        if process is None:
            logger.warning(f"{process_name} 프로세스 객체가 None입니다.")
            return False
            
        # 프로세스 상태 확인
        returncode = process.poll()
        if returncode is None:
            # 프로세스 실행 중
            return True
        else:
            logger.warning(f"{process_name} 프로세스가 종료됨: 반환 코드={returncode}")
            
            # 종료된 프로세스의 출력 가져오기 (가능한 경우)
            if hasattr(process, 'stdout') and process.stdout:
                stdout_data = process.stdout.read()
                if stdout_data:
                    logger.info(f"{process_name} 프로세스 표준 출력: {stdout_data}")
            
            if hasattr(process, 'stderr') and process.stderr:
                stderr_data = process.stderr.read()
                if stderr_data:
                    logger.error(f"{process_name} 프로세스 오류 출력: {stderr_data}")
                    
            return False
    
    def check_system_resources(self):
        """
        시스템 리소스 상태 확인 및 기록
        """
        try:
            import psutil
            
            # 메모리 사용량
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # CPU 사용량
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 디스크 사용량
            disk = psutil.disk_usage('/')
            
            # 로그 출력
            logger.info(f"시스템 리소스 - CPU: {cpu_percent}%, "
                       f"메모리: {memory.percent}% ({memory.used / (1024**3):.2f}GB/{memory.total / (1024**3):.2f}GB), "
                       f"디스크: {disk.percent}% ({disk.used / (1024**3):.2f}GB/{disk.total / (1024**3):.2f}GB), "
                       f"스왑: {swap.percent}% ({swap.used / (1024**3):.2f}GB/{swap.total / (1024**3):.2f}GB)")
            
        except ImportError:
            logger.warning("psutil 모듈이 설치되지 않았습니다. 시스템 리소스 체크가 불가능합니다.")
        except Exception as e:
            logger.error(f"시스템 리소스 확인 중 오류 발생: {e}")
    
    def run(self):
        """
        서비스 실행
        """
        self.running = True
        restart_count = {
            'process_monitor': 0,
            'main_service': 0
        }
        
        logger.info("클라우드 서비스 실행 시작")
        
        # 1. 의존성 확인 및 설치
        if not self.check_dependencies():
            logger.error("필요한 의존성 설치에 실패했습니다. 서비스를 종료합니다.")
            return False
        
        # 2. 환경 준비
        if not self.prepare_environment():
            logger.error("실행 환경 준비에 실패했습니다. 서비스를 종료합니다.")
            return False
        
        # 3. 서비스 시작 (설정에 따라 프로세스 모니터 또는 직접 실행)
        if self.config.get('use_process_monitor', True):
            logger.info("프로세스 모니터를 통한 서비스 실행 모드")
            self.service_processes['process_monitor'] = self.start_process_monitor()
            if self.service_processes['process_monitor'] is None:
                logger.error("프로세스 모니터 시작 실패")
                return False
        else:
            logger.info("메인 서비스 직접 실행 모드")
            self.service_processes['main_service'] = self.start_main_service()
            if self.service_processes['main_service'] is None:
                logger.error("메인 서비스 시작 실패")
                return False
        
        # 4. 모니터링 루프
        try:
            while self.running:
                current_time = datetime.now()
                
                # 4.1. 프로세스 모니터 상태 확인
                if 'process_monitor' in self.service_processes:
                    if not self.check_process_status(self.service_processes['process_monitor'], "프로세스 모니터"):
                        # 재시작 시도
                        restart_count['process_monitor'] += 1
                        logger.warning(f"프로세스 모니터 재시작 시도 ({restart_count['process_monitor']}회)")
                        self.service_processes['process_monitor'] = self.start_process_monitor()
                
                # 4.2. 메인 서비스 상태 확인 (직접 실행 모드인 경우)
                if 'main_service' in self.service_processes:
                    if not self.check_process_status(self.service_processes['main_service'], "메인 서비스"):
                        # 재시작 시도
                        restart_count['main_service'] += 1
                        logger.warning(f"메인 서비스 재시작 시도 ({restart_count['main_service']}회)")
                        self.service_processes['main_service'] = self.start_main_service()
                
                # 4.3. 시스템 리소스 모니터링 (10분 간격)
                if (current_time - self.last_resource_check).total_seconds() > 600:
                    self.check_system_resources()
                    self.last_resource_check = current_time
                    
                    # 서비스 실행 시간 출력
                    uptime = current_time - self.start_time
                    days, seconds = uptime.days, uptime.seconds
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    seconds = seconds % 60
                    logger.info(f"서비스 실행 시간: {days}일 {hours}시간 {minutes}분 {seconds}초")
                
                # 4.4. 대기 (10초 간격)
                time.sleep(10)
                
        except KeyboardInterrupt:
            logger.info("사용자에 의한 중단 신호 감지")
        except Exception as e:
            logger.error(f"모니터링 루프 중 예상치 못한 오류 발생: {e}")
            traceback.print_exc()
        finally:
            # 5. 종료 처리
            self.stop()
            
        return True
    
    def stop(self):
        """
        서비스 종료
        """
        if not self.running:
            return  # 이미 종료됨
            
        self.running = False
        logger.info("서비스 종료 중...")
        
        # 실행 중인 모든 프로세스 종료
        for name, process in self.service_processes.items():
            if process and process.poll() is None:
                logger.info(f"{name} 프로세스 종료 중 (PID: {process.pid})")
                try:
                    # SIGTERM 신호 전송
                    process.terminate()
                    
                    # 3초 대기 후 여전히 실행 중이면 강제 종료
                    for _ in range(30):  # 3초 대기 (10번 * 0.3초)
                        if process.poll() is not None:
                            break
                        time.sleep(0.3)
                    else:
                        logger.warning(f"{name} 프로세스가 응답하지 않습니다. 강제 종료합니다.")
                        process.kill()
                    
                except Exception as e:
                    logger.error(f"{name} 프로세스 종료 중 오류 발생: {e}")
        
        logger.info("모든 프로세스 종료 완료")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="클라우드 환경에서 주식 분석 시스템 실행 및 모니터링")
    parser.add_argument("--direct", "-d", action="store_true", help="프로세스 모니터 없이 직접 실행")
    
    args = parser.parse_args()
    
    # 설정값
    config = {
        'use_process_monitor': not args.direct
    }
    
    # 클라우드 서비스 객체 생성 및 실행
    service = CloudService(config)
    service.run()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"메인 스크립트 실행 실패: {e}")
        traceback.print_exc()
        sys.exit(1)