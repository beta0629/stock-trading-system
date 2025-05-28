"""
카카오톡 메시지 전송 모듈
"""
import logging
import requests
import os
import json
import time
import re
from datetime import timedelta

# time_utils 모듈 import
from ..utils.time_utils import get_current_time, get_current_time_str, parse_time, get_adjusted_time

# 로깅 설정
logger = logging.getLogger('KakaoSender')

class KakaoSender:
    """카카오톡 메시지 전송 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        self.access_token = None
        self.refresh_token = None
        self.token_expire_at = None
        self.initialized = False
        
        # CI 환경인지 확인
        self.is_ci_env = os.environ.get('CI') == 'true'
        
        # 시스템 시작시 토큰 초기화
        self.initialize()
        
    def initialize(self):
        """카카오톡 API 초기화"""
        try:
            # CI 환경이고, KAKAO_API_KEY가 없으면 비활성화 모드로 설정
            if self.is_ci_env and not os.environ.get('KAKAO_API_KEY'):
                logger.warning("CI 환경에서 KAKAO_API_KEY가 설정되지 않아 카카오톡 알림은 비활성화됩니다.")
                return False
            
            # 환경 변수 우선 확인 (CI/CD 환경용)
            self.access_token = os.environ.get('KAKAO_ACCESS_TOKEN')
            self.refresh_token = os.environ.get('KAKAO_REFRESH_TOKEN')
            
            # 환경변수에 없으면 파일에서 토큰 로드
            if not self.access_token or not self.refresh_token:
                token_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'kakao_token.json')
                if os.path.exists(token_file):
                    try:
                        with open(token_file, 'r') as f:
                            token_data = json.load(f)
                            self.access_token = token_data.get('access_token')
                            self.refresh_token = token_data.get('refresh_token')
                            self.token_expire_at = token_data.get('expire_at')
                            logger.info("카카오톡 토큰 파일에서 로드 완료")
                    except Exception as e:
                        logger.error(f"카카오톡 토큰 파일 로드 실패: {e}")
            
            # 환경 변수에서 토큰 로드 (파일에서 로드 실패시)
            if not self.access_token and hasattr(self.config, 'KAKAO_ACCESS_TOKEN'):
                self.access_token = self.config.KAKAO_ACCESS_TOKEN
            if not self.refresh_token and hasattr(self.config, 'KAKAO_REFRESH_TOKEN'):
                self.refresh_token = self.config.KAKAO_REFRESH_TOKEN
            
            if not self.access_token or not self.refresh_token:
                if self.is_ci_env:
                    logger.warning("CI 환경에서 카카오톡 토큰이 설정되지 않아 알림은 비활성화됩니다.")
                    return False
                else:
                    logger.error("카카오톡 토큰이 설정되지 않았습니다.")
                    return False
            
            # 토큰의 만료 시간 확인
            if self.token_expire_at:
                try:
                    expire_time = parse_time(self.token_expire_at)
                    current_time = get_current_time()
                    if current_time >= expire_time:
                        logger.info("카카오톡 토큰이 만료되었습니다. 갱신을 시도합니다.")
                        if not self.refresh_auth_token():
                            logger.error("토큰 갱신 실패")
                            return False
                except Exception as e:
                    logger.error(f"토큰 만료 시간 확인 중 오류: {e}")
            
            # 토큰 유효성 테스트
            if self.test_token():
                logger.info("카카오톡 API 초기화 완료")
                self.initialized = True
                return True
            else:
                logger.warning("카카오톡 API 토큰이 유효하지 않습니다. 갱신을 시도합니다.")
                # 토큰 갱신 시도
                if self.refresh_auth_token():
                    logger.info("카카오톡 API 토큰 갱신 성공")
                    self.initialized = True
                    return True
                else:
                    if self.is_ci_env:
                        logger.warning("CI 환경에서 토큰 갱신 실패. 카카오톡 알림은 비활성화됩니다.")
                    else:
                        logger.error("카카오톡 API 토큰 갱신 실패")
                    return False
        except Exception as e:
            logger.error(f"카카오톡 API 초기화 실패: {e}")
            return False
    
    def test_token(self):
        """
        액세스 토큰 유효성 테스트
        
        Returns:
            bool: 토큰 유효 여부
        """
        if not self.access_token:
            logger.error("액세스 토큰이 없어 테스트할 수 없습니다.")
            return False
            
        try:
            url = "https://kapi.kakao.com/v2/api/talk/profile"
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = requests.get(url, headers=headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"토큰 테스트 실패: {e}")
            return False
    
    def save_tokens_to_file(self):
        """토큰을 파일에 저장"""
        try:
            # CI 환경에서는 파일 저장 건너뛰기
            if self.is_ci_env:
                logger.info("CI 환경에서는 토큰 파일을 저장하지 않습니다.")
                return True
                
            token_data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expire_at": get_adjusted_time(adjust_days=29).isoformat(),  # 약 30일 후 만료
                "updated_at": get_current_time().isoformat()
            }
            
            token_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'kakao_token.json')
            with open(token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
                
            logger.info("카카오톡 토큰 파일 저장 완료")
            
            # GitHub Actions에서 실행 중이면 환경 변수 업데이트
            if 'GITHUB_ENV' in os.environ:
                with open(os.environ['GITHUB_ENV'], 'a') as env_file:
                    env_file.write(f"KAKAO_ACCESS_TOKEN={self.access_token}\n")
                    env_file.write(f"KAKAO_REFRESH_TOKEN={self.refresh_token}\n")
                logger.info("GitHub 환경 변수에 토큰 업데이트 완료")
                
            return True
        except Exception as e:
            logger.error(f"카카오톡 토큰 파일 저장 실패: {e}")
            return False
    
    def refresh_auth_token(self):
        """
        인증 토큰 갱신
        
        Returns:
            bool: 토큰 갱신 성공 여부
        """
        try:
            url = "https://kauth.kakao.com/oauth/token"
            
            # client_id가 없는 경우 환경 변수나 config에서 가져오기
            client_id = os.environ.get('KAKAO_API_KEY')
            if not client_id and hasattr(self.config, 'KAKAO_API_KEY'):
                client_id = self.config.KAKAO_API_KEY
                
            if not client_id:
                if self.is_ci_env:
                    logger.warning("CI 환경에서 KAKAO_API_KEY가 설정되지 않아 토큰 갱신을 건너뜁니다.")
                    return False
                else:
                    logger.error("KAKAO_API_KEY가 설정되지 않았습니다.")
                    return False
                
            data = {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                
                # refresh_token은 선택적으로 포함될 수 있음
                if "refresh_token" in token_data:
                    self.refresh_token = token_data.get("refresh_token")
                
                # 토큰 만료 시간 설정 (약 30일)
                self.token_expire_at = get_adjusted_time(adjust_days=29).isoformat()
                    
                # 토큰을 파일에 저장
                self.save_tokens_to_file()
                
                logger.info("카카오톡 인증 토큰 갱신 완료")
                return True
            else:
                logger.error(f"인증 토큰 갱신 실패: {response.text}")
                return False
        except Exception as e:
            logger.error(f"인증 토큰 갱신 중 오류: {e}")
            return False
    
    def ensure_token_valid(self):
        """토큰이 유효한지 확인하고, 필요시 갱신"""
        if not self.initialized:
            return self.initialize()
            
        # 토큰 테스트
        if not self.test_token():
            logger.info("토큰이 유효하지 않습니다. 갱신을 시도합니다.")
            return self.refresh_auth_token()
        return True
    
    def send_message(self, message):
        """
        카카오톡으로 메시지 전송
        
        Args:
            message: 전송할 메시지 텍스트
            
        Returns:
            bool: 전송 성공 여부
        """
        # CI 환경이고 카카오톡 설정이 없으면 메시지 전송 건너뛰기
        if self.is_ci_env and not self.initialized:
            logger.info("CI 환경에서 카카오톡 설정이 되지 않아 메시지 전송을 건너뜁니다.")
            return True  # 전송 성공으로 처리하여 프로세스 계속 진행
            
        # 메시지 전송 전에 토큰 유효성 확인
        if not self.ensure_token_valid():
            logger.error("유효한 카카오톡 액세스 토큰이 없습니다.")
            # CI 환경에서는 성공으로 처리하여 계속 진행
            if self.is_ci_env:
                logger.info("CI 환경에서 토큰이 유효하지 않아 메시지 전송은 건너뜁니다.")
                return True
            return False
        
        # 메시지 길이가 제한을 초과하면 여러 메시지로 분할
        max_message_length = 1800  # 안전한 길이 제한 (2000자보다 작게 설정)
        
        # 메시지를 분할
        if len(message) > max_message_length:
            parts = self._split_message(message, max_message_length)
            success = True
            
            # 분할된 메시지 각각을 전송
            for i, part in enumerate(parts):
                part_message = f"[{i+1}/{len(parts)}] {part}"
                if not self._send_single_message(part_message):
                    success = False
                # 연속 메시지 전송 시 약간의 딜레이 추가
                if i < len(parts) - 1:
                    time.sleep(0.5)
                    
            return success
        else:
            # 단일 메시지 전송
            return self._send_single_message(message)
            
    def _send_single_message(self, message):
        """
        단일 카카오톡 메시지 전송 (내부 함수)
        
        Args:
            message: 전송할 메시지 텍스트
            
        Returns:
            bool: 전송 성공 여부
        """
        try:
            # 메시지 전송 API 호출
            url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # 메시지 템플릿 설정
            template = {
                "object_type": "text",
                "text": message,
                "link": {
                    "web_url": "https://developers.kakao.com",
                    "mobile_web_url": "https://developers.kakao.com"
                },
                "button_title": "자세히 보기"
            }
            
            data = {
                "template_object": json.dumps(template)
            }
            
            response = requests.post(url, headers=headers, data=data)
            if response.status_code == 200:
                logger.info("카카오톡 메시지 전송 완료")
                return True
            else:
                # 토큰 만료일 때 갱신 후 재시도
                if response.status_code == 401:
                    logger.warning("토큰이 만료되었습니다. 갱신 후 재시도합니다.")
                    if self.refresh_auth_token():
                        return self._send_single_message(message)  # 재귀적으로 다시 시도
                logger.error(f"카카오톡 메시지 전송 실패: {response.text}")
                if self.is_ci_env:
                    logger.info("CI 환경에서 메시지 전송 실패는 무시하고 계속 진행합니다.")
                    return True
                return False
        except Exception as e:
            logger.error(f"카카오톡 메시지 전송 중 오류: {e}")
            if self.is_ci_env:
                logger.info("CI 환경에서 발생한 오류는 무시하고 계속 진행합니다.")
                return True
            return False
            
    def _split_message(self, message, max_length):
        """
        긴 메시지를 적절한 크기로 분할
        
        Args:
            message: 원본 메시지 텍스트
            max_length: 분할된 조각의 최대 길이
            
        Returns:
            list: 분할된 메시지의 리스트
        """
        # 줄바꿈으로 먼저 분할하여 문맥을 유지
        lines = message.split('\n')
        parts = []
        current_part = ""
        
        for line in lines:
            # 한 줄이 max_length를 초과하면 해당 줄을 다시 분할
            if len(line) > max_length:
                # 현재까지 모인 내용이 있으면 parts에 추가
                if current_part:
                    parts.append(current_part)
                    current_part = ""
                
                # 긴 줄을 단어 단위로 분할
                words = line.split(' ')
                word_part = ""
                
                for word in words:
                    if len(word_part) + len(word) + 1 <= max_length:
                        if word_part:
                            word_part += " " + word
                        else:
                            word_part = word
                    else:
                        parts.append(word_part)
                        word_part = word
                
                if word_part:
                    current_part = word_part
            else:
                # 현재 부분에 이 줄을 추가했을 때 max_length를 초과하면 새 부분 시작
                if len(current_part) + len(line) + 1 > max_length:
                    parts.append(current_part)
                    current_part = line
                else:
                    # 현재 부분에 줄 추가
                    if current_part:
                        current_part += "\n" + line
                    else:
                        current_part = line
        
        # 남은 텍스트 추가
        if current_part:
            parts.append(current_part)
            
        return parts
    
    def send_signal_notification(self, signal_data):
        """
        매매 시그널 알림 전송 (축약된 형태)
        
        Args:
            signal_data: 매매 시그널 정보
        """
        if not signal_data.get('signals'):
            return
            
        symbol = signal_data['symbol']
        price = signal_data.get('price', signal_data.get('close', 0))
        timestamp = signal_data.get('timestamp', get_current_time())
        signals = signal_data['signals']
        
        # 타임스탬프가 문자열인 경우 처리
        if isinstance(timestamp, str):
            try:
                timestamp = parse_time(timestamp)
            except:
                timestamp = get_current_time()
        
        # 종목 이름 설정 (코드와 함께 표시)
        stock_name = self._get_stock_name(symbol)
        symbol_name = f"{stock_name} ({symbol})"
        
        # AI 모델 정보 축약
        model_used = signal_data.get('model_used', '').lower()
        model_icon = "🧠" if model_used == 'gpt' else "🤖" if model_used == 'gemini' else "🔍"
        
        # 가장 중요한 신호 찾기
        latest_signal = signals[0]
        for signal in signals:
            if signal.get('confidence', 0) > latest_signal.get('confidence', 0):
                latest_signal = signal
        
        signal_type = latest_signal['type']
        signal_emoji = "🔴" if signal_type == 'SELL' else "🟢"
        confidence = latest_signal.get('confidence', 0.0)
        confidence_str = f" (신뢰도: {confidence:.1f})" if confidence else ""
        
        # 메시지 생성 (축약된 형태)
        message = f"{signal_emoji} {symbol_name} {signal_type} 신호{confidence_str}\n"
        message += f"현재가: {price:,.2f}원\n"
        message += f"시간: {get_current_time_str(format_str='%m-%d %H:%M')}\n"
        
        # AI 분석 요약
        ai_analysis = signal_data.get('ai_analysis', '')
        gpt_analysis = signal_data.get('gpt_analysis', '')
        
        if ai_analysis or gpt_analysis:
            analysis = ai_analysis if ai_analysis else gpt_analysis
            # HTML 태그 제거
            analysis = self._remove_html_tags(analysis)
            
            # 요약 메시지로 줄이기
            if len(analysis) > 100:
                # 첫 문장만 추출
                first_sentence = analysis.split('.')[0]
                if len(first_sentence) > 100:
                    summary = first_sentence[:97] + "..."
                else:
                    summary = first_sentence + "..."
                message += f"\n💡 요약: {summary}"
            else:
                message += f"\n💡 분석: {analysis}"
        
        # 메시지 전송
        sent = self.send_message(message)
        
        # 추가 분석이 필요한 경우에만 상세 메시지 전송
        if sent and (len(signals) > 1 or len(ai_analysis) > 100 or len(gpt_analysis) > 100):
            # 사용자가 상세 내용을 보고 싶을 때만 전송하도록 안내
            self.send_detailed_analysis(signal_data, symbol_name)
        
        return sent
    
    def send_detailed_analysis(self, signal_data, symbol_name):
        """
        상세 분석 결과 전송 (분리된 메시지)
        
        Args:
            signal_data: 매매 시그널 정보
            symbol_name: 종목명 (코드 포함)
        """
        # AI 분석이 포함된 경우
        ai_analysis = signal_data.get('ai_analysis', '')
        gpt_analysis = signal_data.get('gpt_analysis', '')
        
        # HTML 태그 제거
        ai_analysis = self._remove_html_tags(ai_analysis)
        gpt_analysis = self._remove_html_tags(gpt_analysis)
        
        # 모델 정보 가져오기
        model_used = signal_data.get('model_used', '').lower()
        model_icon = "🧠" if model_used == 'gpt' else "🤖" if model_used == 'gemini' else "🔍"
        model_name = "GPT" if model_used == 'gpt' else "Gemini" if model_used == 'gemini' else "AI"
        
        # 상세 분석 전송 (가장 중요한 부분만)
        if ai_analysis or gpt_analysis:
            analysis = ai_analysis if ai_analysis else gpt_analysis
            detail_message = f"{model_icon} {symbol_name} 상세 분석\n\n{analysis}"
            
            # 긴 메시지는 축약
            if len(detail_message) > 1800:
                # 첫 1700자만 보내기
                detail_message = detail_message[:1700] + "...\n(분석 요약: 길이 제한으로 일부만 표시)"
                
            self.send_message(detail_message)
    
    def send_system_status(self, status_message):
        """
        시스템 상태 알림 전송 (축약된 형태)
        
        Args:
            status_message: 상태 메시지
        """
        # HTML 태그 제거
        clean_message = self._remove_html_tags(status_message)
        
        # 아이콘 설정
        icon = "📊"
        if "분석 결과" in clean_message:
            icon = "📈"
        elif "매매 신호" in clean_message:
            icon = "🔔"
        elif "오류" in clean_message:
            icon = "⚠️"
        
        # 메시지 헤더 간소화
        header = f"{icon} {get_current_time_str(format_str='%m-%d %H:%M')}\n\n"
        
        # 메시지 본문 길이 제한
        max_content_length = 1500
        
        # 중요한 부분만 추출
        if len(clean_message) > max_content_length:
            # 처음 300자 + ... + 마지막 300자 
            # 또는 문단 단위로 요약
            paragraphs = clean_message.split('\n\n')
            if len(paragraphs) > 4:
                # 첫 번째와 마지막 두 개 문단만 유지
                summary = paragraphs[0] + "\n\n"
                summary += "...(중략)...\n\n"
                summary += "\n\n".join(paragraphs[-2:])
                clean_message = summary
            else:
                # 그냥 앞뒤 텍스트만 보여주기
                clean_message = clean_message[:700] + "\n\n...(중략)...\n\n" + clean_message[-700:]
        
        # 메시지 전송
        return self.send_message(header + clean_message)
    
    def _check_token(self):
        """토큰이 유효한지 확인하고 필요시 갱신"""
        # 토큰이 없거나 만료되었으면 갱신
        if not self.token or not self.token_expire_at:
            self._refresh_token()
            return
        
        # datetime 사용 대신 parse_time 함수를 사용하여 시간 파싱
        expire_time = parse_time(self.token_expire_at)
        current_time = get_current_time()
        if current_time >= expire_time:
            self._refresh_token()
            return
    
    def _save_token(self, token_json):
        """API 응답으로부터 토큰 저장"""
        token_data = token_json
        
        if isinstance(token_json, str):
            token_data = json.loads(token_json)
        
        self.token = token_data.get('access_token')
        # datetime.now() + timedelta 대신 get_adjusted_time 사용
        self.token_expire_at = get_adjusted_time(adjust_days=29).isoformat()
        
        # 토큰 파일에 저장
        with open(self.token_file, 'w') as f:
            json.dump({
                "access_token": self.token,
                "expire_at": self.token_expire_at,
                "updated_at": get_current_time().isoformat()
            }, f, indent=4)
    
    def _refresh_token(self):
        """카카오 토큰 갱신"""
        if not os.path.exists(self.token_file):
            self._request_new_token()
            return
            
        try:
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)
                
            self.refresh_token = token_data.get('refresh_token')
            if not self.refresh_token:
                self._request_new_token()
                return
                
            url = "https://kauth.kakao.com/oauth/token"
            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token
            }
            response = requests.post(url, data=data)
            
            if response.status_code != 200:
                logger.error(f"토큰 갱신 실패: {response.text}")
                self._request_new_token()
                return
                
            token_dict = response.json()
            self.token = token_dict.get('access_token')
            
            # datetime 대신 time_utils 함수 사용
            self.token_expire_at = get_adjusted_time(adjust_days=29).isoformat()
            
            # 새로운 refresh_token이 포함되어 있으면 업데이트
            if token_dict.get('refresh_token'):
                self.refresh_token = token_dict.get('refresh_token')
                
            self._save_token(token_dict)
            
        except Exception as e:
            logger.error(f"토큰 갱신 중 오류: {e}")
            self._request_new_token()
    
    def _check_token_validity(self):
        """토큰 유효성 검사 및 필요시 갱신"""
        if not self.token or not self.token_expire_at:
            self._load_token_from_file()
            
        if not self.token:
            self._get_authorize_code()
            return
            
        if self.token_expire_at:
            # datetime.fromisoformat 대신 parse_time 사용
            expire_time = parse_time(self.token_expire_at)
            current_time = get_current_time()
            
            if current_time >= expire_time:
                self._refresh_token()
                return
    
    def _remove_html_tags(self, text):
        """HTML 태그를 제거하고 일반 텍스트로 변환
        
        Args:
            text: HTML 태그가 포함된 문자열
            
        Returns:
            str: HTML 태그가 제거된 문자열
        """
        if not text:
            return ""
        
        # 볼드 태그 처리: <b>텍스트</b> -> *텍스트*
        text = re.sub(r'<b>(.*?)</b>', r'*\1*', text)
        
        # 이탤릭 태그 처리: <i>텍스트</i> -> _텍스트_
        text = re.sub(r'<i>(.*?)</i>', r'_\1_', text)
        
        # 나머지 모든 HTML 태그 제거
        text = re.sub(r'<.*?>', '', text)
        
        return text
    
    def _get_stock_name(self, symbol):
        """주식 종목 코드로부터 종목명을 반환
        
        Args:
            symbol: 종목 코드
            
        Returns:
            str: 종목명 (없으면 종목 코드 그대로 반환)
        """
        # 종목 정보 리스트 (config에서 가져오기)
        kr_stock_info = []
        us_stock_info = []
        
        if hasattr(self.config, 'KR_STOCK_INFO'):
            kr_stock_info = self.config.KR_STOCK_INFO
        if hasattr(self.config, 'US_STOCK_INFO'):
            us_stock_info = self.config.US_STOCK_INFO
        
        # 종목 코드가 한국 주식인지 미국 주식인지 판단
        if symbol.isdigit():
            # 한국 주식: 코드로 종목 정보 찾기
            for stock in kr_stock_info:
                if stock.get('code') == symbol:
                    return stock.get('name', symbol)
        else:
            # 미국 주식: 코드로 종목 정보 찾기
            for stock in us_stock_info:
                if stock.get('code') == symbol:
                    return stock.get('name', symbol)
                    
        # 종목 정보가 없으면 코드 그대로 반환
        return symbol