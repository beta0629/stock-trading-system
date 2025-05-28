"""
텔레그램 메시지 전송 모듈
"""
import logging
import asyncio
import concurrent.futures
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from ..utils.time_utils import get_current_time, get_current_time_str, format_timestamp

# 로깅 설정
logger = logging.getLogger('TelegramSender')

class TelegramSender:
    """텔레그램 메시지 전송 클래스"""
    
    def __init__(self, config):
        """
        초기화 함수
        
        Args:
            config: 설정 모듈
        """
        self.config = config
        self.bot = None
        self.initialized = False
        self.enabled = getattr(self.config, 'USE_TELEGRAM', False)
        
        # 텔레그램 사용이 설정된 경우에만 초기화 진행
        if self.enabled:
            self.initialize()
        else:
            logger.info("텔레그램 알림 기능이 비활성화되어 있습니다.")
        
    def initialize(self):
        """텔레그램 봇 초기화"""
        if not self.enabled:
            logger.info("텔레그램 알림 기능이 비활성화되어 있어 초기화를 건너뜁니다.")
            return False
            
        try:
            # 봇 토큰 확인 및 로깅
            token = self.config.TELEGRAM_BOT_TOKEN
            if not token:
                logger.error("텔레그램 봇 토큰이 설정되지 않았습니다.")
                return False
                
            chat_id = self.config.TELEGRAM_CHAT_ID
            if not chat_id:
                logger.error("텔레그램 채팅 ID가 설정되지 않았습니다.")
                return False
                
            # 봇 초기화
            self.bot = Bot(token=token)
            logger.info("텔레그램 봇 초기화 완료")
            
            # 테스트 메시지 전송 (확인용)
            try:
                asyncio.run(self.send_test_message())
                self.initialized = True
                return True
            except Exception as e:
                logger.error(f"텔레그램 테스트 메시지 전송 실패: {e}")
                return False
            
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
            return False
    
    async def send_test_message(self):
        """텔레그램 연결 테스트 메시지 전송"""
        if not self.enabled or not self.bot:
            return

        try:
            current_time = get_current_time_str("%Y-%m-%d %H:%M:%S")
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=f"🚀 AI 주식 자동매매 시스템이 {current_time}에 시작되었습니다.",
                parse_mode=ParseMode.HTML
            )
            logger.info("텔레그램 테스트 메시지 전송 완료")
        except TelegramError as e:
            logger.error(f"텔레그램 테스트 메시지 전송 실패: {e}")
            raise
        except Exception as e:
            logger.error(f"텔레그램 테스트 메시지 전송 중 예상치 못한 오류: {e}")
            raise
    
    async def send_message(self, message):
        """
        텔레그램으로 메시지 전송
        
        Args:
            message: 전송할 메시지 텍스트
        """
        if not self.enabled or not self.bot:
            return
            
        try:
            await self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info("텔레그램 메시지 전송 완료")
        except TelegramError as e:
            logger.error(f"텔레그램 메시지 전송 실패: {e}")
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 중 예상치 못한 오류: {e}")
    
    def send_message_sync(self, message):
        """
        동기식 메시지 전송 래퍼 함수
        
        Args:
            message: 전송할 메시지 텍스트
        """
        # 텔레그램이 비활성화되어 있으면 바로 리턴
        if not self.enabled or not self.bot:
            return True
            
        try:
            # GitHub Actions나 기타 환경에서 안전하게 비동기 함수 실행하기
            async def _send_message_task():
                try:
                    await self.bot.send_message(
                        chat_id=self.config.TELEGRAM_CHAT_ID,
                        text=message,
                        parse_mode=ParseMode.HTML
                    )
                    return True
                except Exception as e:
                    logger.error(f"텔레그램 메시지 전송 중 오류: {e}")
                    return False
            
            # 기존 이벤트 루프가 있는지 확인하고 적절히 처리
            try:
                loop = asyncio.get_event_loop()
                # 이벤트 루프가 닫혀있는지 확인
                if loop.is_closed():
                    logger.debug("기존 이벤트 루프가 닫혀있어 새 루프 생성")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(_send_message_task())
                elif loop.is_running():
                    # 이미 실행 중인 루프가 있는 경우 (GitHub Actions 등의 환경)
                    # Future를 생성하고 결과를 동기적으로 기다림
                    logger.debug("이벤트 루프가 이미 실행 중입니다. Future 사용")
                    future = asyncio.run_coroutine_threadsafe(_send_message_task(), loop)
                    try:
                        result = future.result(timeout=10)  # 10초 타임아웃
                        return result
                    except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                        logger.error("텔레그램 메시지 전송 시간 초과")
                        return False
                else:
                    # 루프가 있지만 실행 중이 아닌 경우
                    logger.debug("기존 루프 사용하여 실행")
                    return loop.run_until_complete(_send_message_task())
            except RuntimeError:
                # 이벤트 루프가 없는 경우
                logger.debug("이벤트 루프를 찾을 수 없어 새로 생성")
                return asyncio.run(_send_message_task())
                
            logger.info("텔레그램 메시지 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"동기식 메시지 전송 중 오류: {e}")
            return False
    
    def send_signal_notification(self, signal_data):
        """
        매매 시그널 알림 전송
        
        Args:
            signal_data: 매매 시그널 정보
        """
        # 텔레그램이 비활성화되어 있으면 바로 리턴
        if not self.enabled or not self.bot:
            return
            
        if not signal_data['signals']:
            return
            
        symbol = signal_data['symbol']
        price = signal_data['price']
        timestamp = signal_data['timestamp']
        signals = signal_data['signals']
        
        # 종목 이름 설정 (코드와 함께 표시)
        symbol_name = symbol
        
        # 메시지 생성
        message_parts = [
            f"<b>🔔 매매 시그널 알림</b>",
            f"<b>종목:</b> {symbol_name}",
            f"<b>현재가:</b> {price:,.2f}",
            f"<b>시간:</b> {format_timestamp(timestamp, '%Y-%m-%d %H:%M:%S')}",
            "",
            "<b>🚨 발생 시그널:</b>"
        ]
        
        for signal in signals:
            signal_type = signal['type']
            strength = signal['strength']
            reason = signal['reason']
            
            # 시그널 강도에 따른 이모지
            strength_emoji = "⚡" if strength == 'STRONG' else "✅" if strength == 'MEDIUM' else "ℹ️"
            
            # 매수/매도 이모지
            type_emoji = "🔴" if signal_type == 'SELL' else "🟢"
            
            message_parts.append(f"{type_emoji} {strength_emoji} <b>{signal_type}:</b> {reason}")
        
        message = "\n".join(message_parts)
        
        # 동기식으로 메시지 전송
        self.send_message_sync(message)
        
    def send_system_status(self, status_message):
        """
        시스템 상태 알림 전송
        
        Args:
            status_message: 상태 메시지
        """
        # 텔레그램이 비활성화되어 있으면 바로 리턴
        if not self.enabled or not self.bot:
            return
            
        current_time = get_current_time_str("%Y-%m-%d %H:%M:%S")
        message = f"<b>📊 시스템 상태</b>\n<b>시간:</b> {current_time}\n\n{status_message}"
        
        # 동기식으로 메시지 전송
        self.send_message_sync(message)
        
    def send_direct_message(self, message):
        """
        즉시 텔레그램 메시지 전송(테스트용)
        
        Args:
            message: 전송할 메시지
        """
        # 텔레그램이 비활성화되어 있으면 바로 리턴
        if not self.enabled or not self.bot:
            return True
            
        try:
            current_time = get_current_time_str("%Y-%m-%d %H:%M:%S")
            full_message = f"<b>⏰ {current_time}</b>\n\n{message}"
            self.send_message_sync(full_message)
            return True
        except Exception as e:
            logger.error(f"직접 메시지 전송 중 오류: {e}")
            return False