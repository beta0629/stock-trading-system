"""
텔레그램 메시지 전송 모듈
"""
import logging
import asyncio
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
        self.initialize()
        
    def initialize(self):
        """텔레그램 봇 초기화"""
        try:
            # 봇 토큰 확인 및 로깅
            token = self.config.TELEGRAM_BOT_TOKEN
            if not token:
                logger.error("텔레그램 봇 토큰이 설정되지 않았습니다.")
                return
                
            chat_id = self.config.TELEGRAM_CHAT_ID
            if not chat_id:
                logger.error("텔레그램 채팅 ID가 설정되지 않았습니다.")
                return
                
            # 봇 초기화
            self.bot = Bot(token=token)
            logger.info("텔레그램 봇 초기화 완료")
            
            # 테스트 메시지 전송 (확인용)
            asyncio.run(self.send_test_message())
            
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
    
    async def send_test_message(self):
        """텔레그램 연결 테스트 메시지 전송"""
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
        except Exception as e:
            logger.error(f"텔레그램 테스트 메시지 전송 중 예상치 못한 오류: {e}")
    
    async def send_message(self, message):
        """
        텔레그램으로 메시지 전송
        
        Args:
            message: 전송할 메시지 텍스트
        """
        if self.bot is None:
            logger.error("텔레그램 봇이 초기화되지 않았습니다.")
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
        try:
            # 비동기 함수를 안전하게 호출하는 방법
            if self.bot is None:
                logger.error("텔레그램 봇이 초기화되지 않았습니다.")
                return

            # 이벤트 루프 확인
            try:
                # 현재 이벤트 루프를 가져옵니다
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    # 이벤트 루프가 닫혔으면 새로 생성
                    logger.debug("이벤트 루프가 닫혔습니다. 새 루프를 생성합니다.")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # 이벤트 루프가 없으면 새로 생성
                logger.debug("이벤트 루프가 없습니다. 새 루프를 생성합니다.")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 안전하게 비동기 메시지 전송
            coroutine = self.bot.send_message(
                chat_id=self.config.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode=ParseMode.HTML
            )
                
            # 메시지 전송
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            result = future.result(timeout=10)  # 10초 타임아웃
            
            logger.info("텔레그램 메시지 전송 완료")
            return True
            
        except asyncio.CancelledError:
            logger.error("텔레그램 메시지 전송이 취소되었습니다.")
            return False
        except asyncio.TimeoutError:
            logger.error("텔레그램 메시지 전송 시간 초과")
            return False
        except Exception as e:
            logger.error(f"동기식 메시지 전송 중 오류: {e}")
            # 대체 방법 시도: asyncio.run 사용
            try:
                logger.debug("대체 메시지 전송 방식 시도")
                # 완전히 새로운 이벤트 루프에서 단일 메시지 전송
                async def send_single_message():
                    await self.bot.send_message(
                        chat_id=self.config.TELEGRAM_CHAT_ID, 
                        text=message,
                        parse_mode=ParseMode.HTML
                    )
                
                asyncio.run(send_single_message())
                logger.info("대체 방식으로 텔레그램 메시지 전송 완료")
                return True
            except Exception as alt_e:
                logger.error(f"대체 전송 방식도 실패: {alt_e}")
                return False
    
    def send_signal_notification(self, signal_data):
        """
        매매 시그널 알림 전송
        
        Args:
            signal_data: 매매 시그널 정보
        """
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
        try:
            current_time = get_current_time_str("%Y-%m-%d %H:%M:%S")
            full_message = f"<b>⏰ {current_time}</b>\n\n{message}"
            self.send_message_sync(full_message)
            return True
        except Exception as e:
            logger.error(f"직접 메시지 전송 중 오류: {e}")
            return False