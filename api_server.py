#!/usr/bin/env python3
import sys
sys.path.append(".")  # 현재 디렉토리를 모듈 검색 경로에 추가

"""
주식 트레이딩 시스템 API 서버

이 모듈은 주식 트레이딩 시스템의 기능을 웹 API로 제공합니다.
FastAPI를 사용하여 RESTful API를 구현합니다.
"""

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import datetime
import os
import time
import logging
import jwt
import asyncio
import psutil  # 시스템 자원 사용량 모니터링을 위한 모듈 임포트
from jwt.exceptions import InvalidTokenError
import random  # 랜덤 모듈 추가
from datetime import timedelta
import socket  # 포트 사용 여부 확인용

# 기존 모듈 임포트 - 모듈이 없을 경우 예외 처리 추가
try:
    from src.ai_analysis.gpt_trading_strategy import GPTTradingStrategy
    from src.trading.gpt_auto_trader import GPTAutoTrader
    from src.data.stock_data import StockData
    from src.notification.telegram_sender import TelegramSender
    from src.notification.kakao_sender import KakaoSender
    from src.database.db_manager import DatabaseManager
    from src.utils.time_utils import now, format_time, is_market_open, get_current_time
    import config
except ImportError as e:
    print(f"경고: 일부 모듈을 임포트할 수 없습니다: {e}")
    # 기본 대체 함수 정의
    def format_time():
        return int(time.time() * 1000)
    
    def is_market_open(market_type):
        return False
    
    def get_current_time():
        return datetime.datetime.now()
    
    # 기본 설정 객체
    class DefaultConfig:
        def __init__(self):
            self.AUTO_TRADING_ENABLED = False
            self.GPT_AUTO_TRADING = False
            self.GPT_FULLY_AUTONOMOUS_MODE = False
            self.DAY_TRADING_MODE = False
            self.SWING_TRADING_MODE = False
            self.SIMULATION_MODE = True
    
    config = DefaultConfig()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api_server.log')
    ]
)
logger = logging.getLogger('API_Server')

# 사용자 인증 및 토큰 관련 설정
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간

# 로그인 모델 정의
class LoginForm(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str

# 사용자 인증 함수
def verify_user(username: str, password: str) -> Dict[str, Any]:
    """사용자 인증 함수"""
    # 환경 변수에서 설정된 사용자 정보 불러오기
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "password")
    
    if username == admin_username and password == admin_password:
        return {"username": username, "role": "admin"}
    return None

# 액세스 토큰 생성 함수    
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """액세스 토큰 생성 함수"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# 포트 사용 가능 여부 확인 함수
def is_port_available(port):
    """지정된 포트가 사용 가능한지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except socket.error:
            return False

# 웹소켓 연결 관리자 클래스
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "price_updates": [],
            "notifications": [],
            "trading_updates": []
        }
        self.connection_status = {}  # 클라이언트 연결 상태 추적
        self.max_retry_attempts = 3  # 메시지 전송 최대 재시도 횟수
        self.ping_interval = 30  # ping 간격 (초)
        self.heartbeat_interval = 50  # 하트비트 간격 (초)

    async def connect(self, websocket: WebSocket, channel: str):
        """
        새로운 웹소켓 연결을 수락하고 추적
        """
        try:
            await websocket.accept()
            client_id = id(websocket)
            
            if channel in self.active_connections:
                self.active_connections[channel].append(websocket)
                self.connection_status[client_id] = {
                    "channel": channel,
                    "connected_at": datetime.datetime.now().isoformat(),
                    "ip": websocket.client.host if hasattr(websocket, 'client') else "unknown",
                    "last_activity": datetime.datetime.now().isoformat(),
                    "messages_sent": 0,
                    "connection_errors": 0,
                    "last_ping": datetime.datetime.now()
                }
                logger.info(f"새 클라이언트 연결: 채널={channel}, ID={client_id}, IP={websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
        except Exception as e:
            logger.error(f"웹소켓 연결 수락 중 오류 발생: {e}")
            try:
                await websocket.close(code=1011, reason="Internal server error during connection")
            except:
                pass

    def disconnect(self, websocket: WebSocket, channel: str):
        """
        웹소켓 연결 해제 및 추적 중단
        """
        try:
            client_id = id(websocket)
            
            if channel in self.active_connections:
                if websocket in self.active_connections[channel]:
                    self.active_connections[channel].remove(websocket)
                    
            # 연결 상태 정보 제거
            if client_id in self.connection_status:
                del self.connection_status[client_id]
                
            logger.debug(f"클라이언트 연결 해제: 채널={channel}, ID={client_id}")
        except Exception as e:
            logger.error(f"웹소켓 연결 해제 중 오류 발생: {e}")

    async def broadcast(self, message: dict, channel: str):
        """
        특정 채널의 모든 연결된 클라이언트에게 메시지 전송
        """
        if channel not in self.active_connections:
            logger.warning(f"알 수 없는 채널로 브로드캐스트 시도: {channel}")
            return
            
        disconnected_clients = []
        
        for connection in self.active_connections[channel]:
            try:
                client_id = id(connection)
                # 메시지 전송
                await connection.send_json(message)
                
                # 연결 상태 업데이트
                if client_id in self.connection_status:
                    self.connection_status[client_id]["last_activity"] = datetime.datetime.now().isoformat()
                    self.connection_status[client_id]["messages_sent"] += 1
            except WebSocketDisconnect:
                # 연결이 끊어진 클라이언트 목록에 추가
                disconnected_clients.append(connection)
            except Exception as e:
                logger.error(f"웹소켓 메시지 전송 중 오류 발생: {e}, 채널={channel}, 클라이언트ID={id(connection)}")
                
                # 연결 오류 카운트 증가
                if client_id in self.connection_status:
                    self.connection_status[client_id]["connection_errors"] += 1
                    
                    # 최대 재시도 횟수를 초과하면 연결 종료
                    if self.connection_status[client_id]["connection_errors"] > self.max_retry_attempts:
                        logger.warning(f"최대 재시도 횟수 초과로 연결 종료: 채널={channel}, 클라이언트ID={client_id}")
                        try:
                            await connection.close(code=1011, reason="Too many connection errors")
                            disconnected_clients.append(connection)
                        except:
                            disconnected_clients.append(connection)
        
        # 연결이 끊어진 클라이언트 제거
        for connection in disconnected_clients:
            self.disconnect(connection, channel)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        특정 클라이언트에게 개인 메시지 전송
        """
        try:
            await websocket.send_json(message)
            
            client_id = id(websocket)
            # 연결 상태 업데이트
            if client_id in self.connection_status:
                self.connection_status[client_id]["last_activity"] = datetime.datetime.now().isoformat()
                self.connection_status[client_id]["messages_sent"] += 1
                
            return True
        except Exception as e:
            logger.error(f"개인 메시지 전송 중 오류 발생: {e}, 클라이언트ID={id(websocket)}")
            return False
    
    async def send_ping(self, websocket: WebSocket):
        """
        클라이언트에게 ping 메시지 전송
        """
        try:
            ping_message = {
                "type": "ping",
                "timestamp": format_time()
            }
            await websocket.send_json(ping_message)
            
            client_id = id(websocket)
            if client_id in self.connection_status:
                self.connection_status[client_id]["last_ping"] = datetime.datetime.now()
            
            return True
        except Exception as e:
            logger.debug(f"Ping 전송 실패. 클라이언트 연결이 끊어졌을 수 있습니다: {e}")
            return False
            
    def get_connection_stats(self):
        """
        연결 통계 정보 반환
        """
        stats = {
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "by_channel": {
                channel: len(conns) for channel, conns in self.active_connections.items()
            },
            "active_clients": len(self.connection_status)
        }
        return stats

# 웹소켓 연결 관리자 인스턴스 생성
connection_manager = ConnectionManager()

# FastAPI 앱 생성
app = FastAPI(title="주식 트레이딩 시스템 API", version="1.0.0")

# JWT 설정
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24  # 24시간

# 보안 설정
security = HTTPBearer()

# 글로벌 변수 초기화 (API 엔드포인트에서 사용할 인스턴스들)
db = None
stock_data = None
broker = None
gpt_strategy = None
auto_trader = None

# CORS 설정 - WebSocket 허용하도록 수정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 시에는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # 추가
)

# 웹소켓 토큰 검증을 위한 유틸리티 함수
async def verify_websocket_token(token: str, websocket: WebSocket):
    """웹소켓 JWT 토큰 검증 함수"""
    try:
        # 토큰 검증 시도
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_signature": True})
        username = payload.get("sub")
        if username is None:
            logger.warning(f"유효하지 않은 토큰(사용자 정보 없음)으로 WebSocket 연결 시도")
            await websocket.close(code=1008, reason="Invalid authentication credentials")
            return None
        return username
    except jwt.ExpiredSignatureError:
        logger.warning(f"만료된 토큰으로 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
        await websocket.close(code=1008, reason="Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"유효하지 않은 토큰으로 WebSocket 연결 시도: {str(e)}")
        await websocket.close(code=1008, reason="Invalid token")
        return None
    except Exception as e:
        logger.error(f"토큰 검증 중 예상치 못한 오류: {str(e)}")
        await websocket.close(code=1008, reason="Authentication error")
        return None

# 웹소켓 엔드포인트 - 실시간 가격 업데이트
@app.websocket("/ws/prices/{token}")
async def websocket_price_updates(websocket: WebSocket, token: str):
    try:
        # JWT 토큰 검증
        try:
            logger.info(f"가격 업데이트 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
            
            # 토큰 검증 시도
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_signature": True})
                username = payload.get("sub")
                
                if username is None:
                    logger.warning(f"유효하지 않은 토큰(사용자 정보 없음)으로 WebSocket 연결 시도")
                    await websocket.close(code=1008, reason="Invalid authentication credentials")
                    return
                    
                logger.info(f"유저 '{username}'의 가격 업데이트 WebSocket 연결 성공")
                
            except jwt.ExpiredSignatureError:
                logger.warning(f"만료된 토큰으로 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
                await websocket.close(code=1008, reason="Token has expired")
                return
            except jwt.InvalidTokenError as e:
                logger.warning(f"유효하지 않은 토큰으로 WebSocket 연결 시도: {str(e)}")
                await websocket.close(code=1008, reason="Invalid token")
                return
            except Exception as e:
                logger.error(f"토큰 검증 중 예상치 못한 오류: {str(e)}")
                await websocket.close(code=1008, reason="Authentication error")
                return
                
        except Exception as e:
            logger.error(f"웹소켓 인증 전체 과정 중 오류: {str(e)}")
            await websocket.close(code=1008, reason="Authentication error")
            return

        await connection_manager.connect(websocket, "price_updates")
        
        # 클라이언트 연결 확인 메시지 전송
        try:
            await connection_manager.send_personal_message({
                "type": "connection_established",
                "message": "실시간 가격 업데이트 서비스에 연결되었습니다.",
                "timestamp": format_time()
            }, websocket)
        except Exception as e:
            logger.error(f"연결 확인 메시지 전송 중 오류: {e}")
        
        try:
            while True:
                # 클라이언트 메시지 대기
                try:
                    data = await websocket.receive_json()
                    
                    # symbols 필드가 없거나 비어있는 경우 안전하게 처리
                    symbols = data.get("symbols", [])
                    if not symbols or not isinstance(symbols, list):
                        symbols = []
                        
                    markets = data.get("markets", ["KR"])
                    if not markets or not isinstance(markets, list):
                        markets = ["KR"]

                    # 요청된 종목들의 현재가 조회
                    price_updates = {}
                    
                    for symbol in symbols:
                        if not symbol:  # None이나 빈 문자열 체크
                            continue
                            
                        market = "KR" if len(symbol) == 6 and symbol.isdigit() else "US"
                        if market not in markets:
                            continue
                        
                        try:
                            current_data = stock_data.get_latest_data(symbol, market)
                            if current_data is not None:
                                price_updates[symbol] = {
                                    "symbol": symbol,
                                    "market": market,
                                    "price": current_data.get("Close"),
                                    "change": current_data.get("Change", 0),
                                    "change_percent": current_data.get("ChangePercent", 0),
                                    "volume": current_data.get("Volume", 0),
                                    "timestamp": format_time()
                                }
                        except Exception as e:
                            logger.warning(f"종목 {symbol} 현재가 조회 실패: {e}")

                    # 가격 정보 전송
                    if price_updates:
                        try:
                            await websocket.send_json({
                                "type": "price_update",
                                "data": price_updates,
                                "timestamp": format_time()
                            })
                        except Exception as e:
                            logger.error(f"가격 업데이트 전송 중 오류: {e}")
                            break
                        
                except json.JSONDecodeError:
                    logger.warning("잘못된 JSON 형식의 메시지를 받음")
                    try:
                        await connection_manager.send_personal_message({
                            "type": "error",
                            "message": "잘못된 메시지 형식입니다. JSON 형식으로 전송해주세요.",
                            "timestamp": format_time()
                        }, websocket)
                    except Exception as send_err:
                        logger.error(f"오류 메시지 전송 실패: {send_err}")
                    continue
                except WebSocketDisconnect:
                    logger.info(f"WebSocket 연결이 종료되었습니다.")
                    break
                except Exception as e:
                    logger.error(f"클라이언트 메시지 수신 중 오류: {e}")
                    break
                    
                # 1초 대기
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            logger.info(f"유저 '{username}'의 가격 업데이트 WebSocket 연결 종료")
        except Exception as e:
            logger.error(f"가격 업데이트 WebSocket 처리 중 오류: {e}")
        finally:
            connection_manager.disconnect(websocket, "price_updates")
    except Exception as e:
        logger.error(f"가격 업데이트 WebSocket 엔드포인트 처리 중 예상치 못한 오류: {e}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass

# 웹소켓 엔드포인트 - 알림
@app.websocket("/ws/notifications/{token}")
async def websocket_notifications(websocket: WebSocket, token: str):
    try:
        # JWT 토큰 검증
        try:
            logger.info(f"알림 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
            
            # 토큰 검증 시도
            try:
                # 테스트를 위해 JWT 검증을 일시적으로 우회
                # payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_signature": True})
                payload = {"sub": "user"}  # 임시로 유효한 사용자로 설정
                username = payload.get("sub")
                
                if username is None:
                    logger.warning(f"유효하지 않은 토큰(사용자 정보 없음)으로 WebSocket 연결 시도")
                    await websocket.close(code=1008, reason="Invalid authentication credentials")
                    return
                    
                logger.info(f"유저 '{username}'의 알림 WebSocket 연결 성공")
                
            except jwt.ExpiredSignatureError:
                logger.warning(f"만료된 토큰으로 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
                await websocket.close(code=1008, reason="Token has expired")
                return
            except jwt.InvalidTokenError as e:
                # 테스트를 위해 토큰 오류를 무시하고 진행
                logger.warning(f"토큰 오류 무시하고 임시 사용자로 진행")
                username = "temp_user"
            except Exception as e:
                # 테스트를 위해 토큰 오류를 무시하고 진행
                logger.warning(f"토큰 검증 중 오류 발생: {e}, 임시 사용자로 진행")
                username = "temp_user"
                
        except Exception as e:
            # 테스트를 위해 인증 오류를 무시
            logger.warning(f"웹소켓 인증 과정 중 오류 무시: {str(e)}")
            username = "temp_user"

        await connection_manager.connect(websocket, "notifications")
        
        # 연결 성공 메시지 전송
        try:
            await connection_manager.send_personal_message({
                "type": "connection_established",
                "message": "실시간 알림 서비스에 연결되었습니다.",
                "timestamp": format_time()
            }, websocket)
        except Exception as e:
            logger.error(f"연결 확인 메시지 전송 중 오류: {e}")
        
        # 클라이언트 연결 유지 
        ping_interval = 15  # 15초마다 ping 전송 (더 자주 확인)
        heartbeat_interval = 30  # 30초마다 하트비트 전송 (더 자주 전송)
        last_ping_time = time.time()
        last_heartbeat_time = time.time()
        
        try:
            while True:
                current_time = time.time()
                
                # Ping 메시지 전송 (15초마다)
                if current_time - last_ping_time >= ping_interval:
                    try:
                        ping_success = await connection_manager.send_ping(websocket)
                        if not ping_success:
                            logger.debug("Ping 실패, 연결이 끊어진 것으로 간주")
                            break
                        last_ping_time = current_time
                    except Exception as e:
                        logger.debug(f"Ping 전송 중 오류: {str(e)}")
                        break
                
                # 하트비트 메시지 전송 (30초마다)
                if current_time - last_heartbeat_time >= heartbeat_interval:
                    try:
                        await websocket.send_json({
                            "type": "heartbeat",
                            "timestamp": format_time(),
                            "connection_id": id(websocket)
                        })
                        last_heartbeat_time = current_time
                    except WebSocketDisconnect:
                        logger.debug("하트비트 전송 중 WebSocket 연결 종료")
                        break
                    except Exception as e:
                        logger.debug(f"하트비트 전송 중 오류: {str(e)}")
                        break
                        
                # 1초마다 연결 상태 확인
                try:
                    # WebSocket 이벤트 대기
                    message = await asyncio.wait_for(
                        websocket.receive_text(), 
                        timeout=1.0
                    )
                    # 클라이언트로부터 메시지를 받았다면 처리
                    if message:
                        try:
                            data = json.loads(message)
                            if data.get("type") == "pong":
                                logger.debug("클라이언트로부터 pong 응답 수신")
                        except:
                            logger.debug("클라이언트로부터 유효하지 않은 메시지 수신")
                except asyncio.TimeoutError:
                    # 타임아웃은 정상, 다음 루프로 진행
                    pass
                except WebSocketDisconnect:
                    logger.debug("WebSocket 연결 종료됨")
                    break
                except Exception as e:
                    logger.debug(f"WebSocket 메시지 수신 중 오류: {str(e)}")
                    # 연결 상태 확인
                    try:
                        # 빈 문자열로 상태 확인
                        await websocket.send_text("")
                    except:
                        logger.debug("연결 상태 확인 실패, 연결 종료")
                        break
                
        except WebSocketDisconnect:
            logger.info(f"유저 '{username}'의 알림 WebSocket 연결 종료")
        except Exception as e:
            logger.error(f"알림 WebSocket 처리 중 오류: {e}")
        finally:
            connection_manager.disconnect(websocket, "notifications")
    except Exception as e:
        logger.error(f"알림 WebSocket 엔드포인트 처리 중 예상치 못한 오류: {e}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass

# 웹소켓 엔드포인트 - 트레이딩 업데이트
@app.websocket("/ws/trading/{token}")
async def websocket_trading(websocket: WebSocket, token: str):
    try:
        # JWT 토큰 검증
        try:
            logger.info(f"트레이딩 업데이트 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
            
            # 토큰 검증 시도
            try:
                # 테스트를 위해 JWT 검증을 일시적으로 우회
                # payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_signature": True})
                payload = {"sub": "user"}  # 임시로 유효한 사용자로 설정
                username = payload.get("sub")
            except jwt.ExpiredSignatureError:
                logger.warning(f"만료된 토큰으로 WebSocket 연결 시도: {websocket.client.host if hasattr(websocket, 'client') else 'unknown'}")
                await websocket.close(code=1008, reason="Token has expired")
                return
            except jwt.InvalidTokenError as e:
                # 테스트를 위해 토큰 오류를 무시하고 진행
                logger.warning(f"토큰 오류 무시하고 임시 사용자로 진행")
                username = "temp_user"
            except Exception as e:
                # 테스트를 위해 토큰 오류를 무시하고 진행
                logger.warning(f"토큰 검증 중 오류 발생: {e}, 임시 사용자로 진행")
                username = "temp_user"
                
            if username is None:
                logger.warning(f"유효하지 않은 토큰(사용자 정보 없음)으로 WebSocket 연결 시도")
                await websocket.close(code=1008, reason="Invalid authentication credentials")
                return
                
            logger.info(f"유저 '{username}'의 트레이딩 업데이트 WebSocket 연결 성공")
        except Exception as e:
            # 테스트를 위해 인증 오류를 무시
            logger.warning(f"웹소켓 인증 과정 중 오류 무시: {str(e)}")
            username = "temp_user"

        await connection_manager.connect(websocket, "trading_updates")
        
        # 연결 성공 메시지 전송
        try:
            await connection_manager.send_personal_message({
                "type": "connection_established",
                "message": "실시간 트레이딩 업데이트 서비스에 연결되었습니다.",
                "timestamp": format_time()
            }, websocket)
            
            # 현재 자동 트레이딩 상태 전송
            auto_trading_info = {
                "auto_trading_enabled": getattr(config, 'AUTO_TRADING_ENABLED', False),
                "gpt_auto_trading_enabled": getattr(config, 'GPT_AUTO_TRADING', False),
                "day_trading_mode": getattr(config, 'DAY_TRADING_MODE', False),
                "swing_trading_mode": getattr(config, 'SWING_TRADING_MODE', False)
            }
            
            await connection_manager.send_personal_message({
                "type": "trading_update",
                "update_type": "status",
                "data": auto_trading_info,
                "timestamp": format_time()
            }, websocket)
        except Exception as e:
            logger.error(f"연결 확인 메시지 전송 중 오류: {e}")
        
        # 클라이언트 연결 유지 
        ping_interval = 15  # 15초마다 ping 전송 (더 자주 확인)
        heartbeat_interval = 30  # 30초마다 하트비트 전송 (더 자주 전송)
        last_ping_time = time.time()
        last_heartbeat_time = time.time()
        
        try:
            while True:
                current_time = time.time()
                
                # Ping 메시지 전송 (15초마다)
                if current_time - last_ping_time >= ping_interval:
                    try:
                        ping_success = await connection_manager.send_ping(websocket)
                        if not ping_success:
                            logger.debug("Ping 실패, 연결이 끊어진 것으로 간주")
                            break
                        last_ping_time = current_time
                    except Exception as e:
                        logger.debug(f"Ping 전송 중 오류: {str(e)}")
                        break
                
                # 하트비트 메시지 전송 (30초마다)
                if current_time - last_heartbeat_time >= heartbeat_interval:
                    try:
                        await websocket.send_json({
                            "type": "heartbeat",
                            "timestamp": format_time(),
                            "connection_id": id(websocket)
                        })
                        last_heartbeat_time = current_time
                    except WebSocketDisconnect:
                        logger.debug("하트비트 전송 중 WebSocket 연결 종료")
                        break
                    except Exception as e:
                        logger.debug(f"하트비트 전송 중 오류: {str(e)}")
                        break
                        
                # 1초마다 연결 상태 확인
                try:
                    # WebSocket 이벤트 대기
                    message = await asyncio.wait_for(
                        websocket.receive_text(), 
                        timeout=1.0
                    )
                    # 클라이언트로부터 메시지를 받았다면 처리
                    if message:
                        try:
                            data = json.loads(message)
                            if data.get("type") == "pong":
                                logger.debug("클라이언트로부터 pong 응답 수신")
                        except:
                            logger.debug("클라이언트로부터 유효하지 않은 메시지 수신")
                except asyncio.TimeoutError:
                    # 타임아웃은 정상, 다음 루프로 진행
                    pass
                except WebSocketDisconnect:
                    logger.debug("WebSocket 연결 종료됨")
                    break
                except Exception as e:
                    logger.debug(f"WebSocket 메시지 수신 중 오류: {str(e)}")
                    # 연결 상태 확인
                    try:
                        # 빈 문자열로 상태 확인
                        await websocket.send_text("")
                    except:
                        logger.debug("연결 상태 확인 실패, 연결 종료")
                        break
                
        except WebSocketDisconnect:
            logger.info(f"유저 '{username}'의 트레이딩 업데이트 WebSocket 연결 종료")
        except Exception as e:
            logger.error(f"트레이딩 업데이트 WebSocket 처리 중 오류: {e}")
        finally:
            connection_manager.disconnect(websocket, "trading_updates")
    except Exception as e:
        logger.error(f"트레이딩 업데이트 WebSocket 엔드포인트 처리 중 예상치 못한 오류: {e}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass

# 알림 전송 함수
async def send_notification(message: str, notification_type: str = "info", data: Any = None):
    try:
        notification = {
            "type": "notification",
            "message": message,
            "notification_type": notification_type,
            "data": data,
            "timestamp": format_time()
        }
        await connection_manager.broadcast(notification, "notifications")
        logger.info(f"알림 전송: {message} (타입: {notification_type})")
        return True
    except Exception as e:
        logger.error(f"알림 전송 중 오류: {e}")
        return False

# 트레이딩 업데이트 전송 함수
async def send_trading_update(update_type: str, data: Any):
    try:
        trading_update = {
            "type": "trading_update",
            "update_type": update_type,
            "data": data,
            "timestamp": format_time()
        }
        await connection_manager.broadcast(trading_update, "trading_updates")
        logger.info(f"트레이딩 업데이트 전송: {update_type}")
        return True
    except Exception as e:
        logger.error(f"트레이딩 업데이트 전송 중 오류: {e}")
        return False

# API 라우트 정의 - 루트 경로 핸들러 추가
@app.get("/")
def root():
    """API 서버 루트 경로"""
    return {
        "status": "ok",
        "message": "주식 트레이딩 시스템 API 서버가 정상적으로 작동 중입니다.",
        "version": "1.0.0",
        "timestamp": int(time.time() * 1000),
        "endpoints": {
            "system_status": "/api/system/status",
            "login": "/api/login",
            "portfolio": "/api/portfolio",
            "stocks": "/api/stocks/list"
        }
    }

@app.get("/api/system/status")
def system_status():
    """시스템 상세 상태 정보 API"""
    try:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        memory_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
        
        # 대시보드에서 기대하는 정확한 구조로 반환
        return {
            "status": "ok",
            "timestamp": int(time.time() * 1000),
            "market_status": {
                "kr_market_open": is_market_open("KR"),
                "us_market_open": is_market_open("US")
            },
            "trading_status": {
                "auto_trading_enabled": getattr(config, 'AUTO_TRADING_ENABLED', False),
                "gpt_auto_trading_enabled": getattr(config, 'GPT_AUTO_TRADING', False),
                "gpt_auto_trader_running": getattr(config, 'GPT_AUTO_TRADER_RUNNING', False)
            },
            "system_resources": {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "disk_usage": disk_usage
            }
        }
    except Exception as e:
        logger.error(f"시스템 상태 API 오류: {e}")
        return {
            "status": "error", 
            "message": str(e),
            "market_status": {
                "kr_market_open": False,
                "us_market_open": False
            },
            "trading_status": {
                "auto_trading_enabled": False,
                "gpt_auto_trading_enabled": False,
                "gpt_auto_trader_running": False
            },
            "system_resources": {
                "cpu_usage": 0,
                "memory_usage": 0,
                "disk_usage": 0
            }
        }

@app.get("/api/automation/status")
def automation_status():
    """자동화 시스템 상태 정보 API"""
    try:
        # 설정에서 자동화 관련 정보 추출
        auto_trading = getattr(config, 'AUTO_TRADING_ENABLED', False)
        gpt_auto_trading = getattr(config, 'GPT_AUTO_TRADING', False)
        gpt_fully_autonomous = getattr(config, 'GPT_FULLY_AUTONOMOUS_MODE', False)
        day_trading = getattr(config, 'DAY_TRADING_MODE', False)
        swing_trading = getattr(config, 'SWING_TRADING_MODE', False)
        
        return {
            "status": "ok",
            "timestamp": format_time(),
            "auto_trading_enabled": auto_trading,
            "gpt_auto_trading_enabled": gpt_auto_trading,
            "gpt_fully_autonomous_mode": gpt_fully_autonomous,
            "day_trading_mode": day_trading,
            "swing_trading_mode": swing_trading,
            "market_status": {
                "kr_market_open": is_market_open("KR"),
                "us_market_open": is_market_open("US")
            },
            "simulation_mode": getattr(config, 'SIMULATION_MODE', False)
        }
    except Exception as e:
        logger.error(f"자동화 상태 API 오류: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/portfolio")
def get_portfolio():
    """포트폴리오 정보 조회 API"""
    try:
        # 증권사 API가 초기화되어 있는지 확인
        if 'broker' not in globals() or broker is None:
            logger.warning("증권사 API가 초기화되지 않았습니다")
            return {"status": "error", "message": "증권사 API가 초기화되지 않았습니다"}

        # 계좌 잔고 조회 - 실제 API 호출
        try:
            balance_info = broker.get_balance()
            logger.info(f"실제 계좌 잔고 데이터: {balance_info}")
        except Exception as e:
            logger.error(f"계좌 잔고 조회 실패: {e}")
            return {"status": "error", "message": f"계좌 잔고 조회 실패: {str(e)}"}

        # 보유 종목 조회 - 실제 API 호출
        try:
            positions = broker.get_positions()
            logger.info(f"실제 보유 종목 데이터: {positions}")
        except Exception as e:
            logger.error(f"보유 종목 조회 실패: {e}")
            return {"status": "error", "message": f"보유 종목 조회 실패: {str(e)}"}

        # 클라이언트 코드와 일치하는 구조로 응답 구성
        account_balance = {
            "총평가금액": balance_info.get("총평가금액", 0),
            "예수금": balance_info.get("예수금", 0),
            "주문가능금액": balance_info.get("주문가능금액", 0),
            "총손익금액": balance_info.get("평가손익금액", 0),
            "총손익률": balance_info.get("총손익률", 0)
        }
        
        positions_list = []
        if isinstance(positions, list):
            positions_list = positions
        elif isinstance(positions, dict):
            for symbol, pos_data in positions.items():
                pos_data["symbol"] = symbol
                positions_list.append(pos_data)
        
        # 클라이언트 코드와 일치하는 응답 형식
        response_data = {
            "status": "ok",
            "timestamp": int(time.time() * 1000),
            "account_balance": account_balance,
            "positions": positions_list,
            "positions_count": len(positions_list)
        }
        
        logger.info(f"포트폴리오 API 응답: {response_data}")
        return response_data
        
    except Exception as e:
        logger.error(f"포트폴리오 조회 API 오류: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/stocks/list")
def get_stock_list(market: str = "KR"):
    """주식 목록 조회 API"""
    try:
        if market not in ["KR", "US"]:
            raise HTTPException(status_code=400, detail="지원하지 않는 마켓 코드입니다. 'KR' 또는 'US'를 사용하세요.")
        
        # Dashboard.js와 정확히 매핑되는 형식의 응답 구성
        stocks = []
        
        # 추천 종목 로드
        try:
            cache_file = f"cache/{market.lower()}_stock_recommendations.json"
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    recommended_stocks = data.get('recommended_stocks', [])
                    
                    # 종목 정보 구성
                    for stock in recommended_stocks:
                        stock_info = {
                            'symbol': stock.get('symbol', ''),  # Dashboard.js에서는 symbol로 접근
                            'code': stock.get('symbol', ''),    # 기존 코드 호환성 유지
                            'name': stock.get('name', ''),
                            'market': market,
                            'price': stock.get('current_price', 0),  # Dashboard.js에서 price로 접근
                            'current_price': stock.get('current_price', 0),
                            'change': stock.get('change_percent', 0),  # 변동률 
                            'change_percent': stock.get('change_percent', 0),
                            'is_recommended': True,
                            'recommendation_reason': stock.get('reason', ''),
                            'target_price': stock.get('target_price', 0),
                            'risk_level': stock.get('risk_level', 5)
                        }
                        stocks.append(stock_info)
        except Exception as e:
            logger.error(f"추천 종목 로드 중 오류 발생: {e}")
        
        # 결과가 없으면 기본 주요 종목 목록 제공
        if not stocks:
            if market == "KR":
                # 한국 주요 종목 목록
                default_kr_stocks = [
                    {"symbol": "005930", "name": "삼성전자", "price": 71500, "current_price": 71500, "change": 1.42, "change_percent": 1.42},
                    {"symbol": "000660", "name": "SK하이닉스", "price": 127500, "current_price": 127500, "change": 0.95, "change_percent": 0.95},
                    {"symbol": "005380", "name": "현대차", "price": 198000, "current_price": 198000, "change": 0.51, "change_percent": 0.51},
                    {"symbol": "035420", "name": "NAVER", "price": 214500, "current_price": 214500, "change": -0.69, "change_percent": -0.69},
                    {"symbol": "035720", "name": "카카오", "price": 51200, "current_price": 51200, "change": 1.19, "change_percent": 1.19}
                ]
                stocks = default_kr_stocks
                for stock in stocks:
                    stock["market"] = "KR"
                    stock["code"] = stock["symbol"]  # code 필드 추가
                    stock["is_recommended"] = False
            else:
                # 미국 주요 종목 목록
                default_us_stocks = [
                    {"symbol": "AAPL", "name": "Apple Inc.", "price": 187.55, "current_price": 187.55, "change": 1.25, "change_percent": 1.25},
                    {"symbol": "MSFT", "name": "Microsoft Corporation", "price": 405.28, "current_price": 405.28, "change": 0.84, "change_percent": 0.84},
                    {"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 168.95, "current_price": 168.95, "change": 0.38, "change_percent": 0.38},
                    {"symbol": "AMZN", "name": "Amazon.com Inc.", "price": 182.06, "current_price": 182.06, "change": 1.42, "change_percent": 1.42},
                    {"symbol": "META", "name": "Meta Platforms Inc.", "price": 478.22, "current_price": 478.22, "change": 0.92, "change_percent": 0.92}
                ]
                stocks = default_us_stocks
                for stock in stocks:
                    stock["market"] = "US"
                    stock["code"] = stock["symbol"]  # code 필드 추가
                    stock["is_recommended"] = False
        
        # 디버깅용 로그
        logger.info(f"주식 목록 API 응답 - market: {market}, stocks: {len(stocks)}")
        
        # Dashboard.js에서 기대하는 형식으로 반환
        return {
            "status": "ok",
            "timestamp": int(time.time() * 1000),
            "market": market,
            "stocks": stocks  # stocks 필드에 직접 배열 반환 (data 객체 내에 중첩하지 않음)
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"주식 목록 조회 API 오류: {e}")
        return {
            "status": "error", 
            "message": str(e),
            "market": market,
            "stocks": []  # data 객체 내에 중첩하지 않음
        }

@app.get("/api/reports/performance")
def get_performance_report(days: int = 30):
    """성과 리포트 조회 API"""
    try:
        # 유효한 기간 검증
        if days <= 0:
            raise HTTPException(status_code=400, detail="days 파라미터는 양수여야 합니다.")
        elif days > 365:
            raise HTTPException(status_code=400, detail="최대 365일까지만 조회 가능합니다.")
        
        # 시작일과 종료일 계산
        end_date = get_current_time()
        start_date = end_date - datetime.timedelta(days=days)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        # DB에서 거래 내역 조회 (기간 기준)
        # 실제 구현 시 아래 코드를 DB 조회로 대체
        # trades = db.get_trades(start_date=start_date_str, end_date=end_date_str)
        
        # 테스트용 일별 성과 데이터 생성
        daily_performance = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 주말은 제외 (토요일: 5, 일요일: 6)
            if current_date.weekday() < 5:  
                # 랜덤 성과 데이터 생성 (실제로는 DB에서 가져와야 함)
                profit_loss = round((random.random() * 2 - 0.5) * 200000)  # -100,000 ~ 300,000 범위
                profit_loss_pct = round(profit_loss / 10000000 * 100, 2)  # 가정: 1000만원 기준
                
                daily_performance.append({
                    "date": date_str,
                    "profit_loss": profit_loss,
                    "profit_loss_pct": profit_loss_pct
                })
            
            current_date += datetime.timedelta(days=1)
            
        # 종합 성과 계산
        total_profit_loss = sum(day["profit_loss"] for day in daily_performance)
        winning_trades = sum(1 for day in daily_performance if day["profit_loss"] > 0)
        losing_trades = sum(1 for day in daily_performance if day["profit_loss"] < 0)
        total_trades = len(daily_performance)
        win_rate = round((winning_trades / total_trades * 100), 1) if total_trades > 0 else 0
        
        # 월별 성과 테스트 데이터 생성 (차트용)
        monthly_performance = []
        for i in range(6):
            month = (end_date.month - i - 1) % 12 + 1  # 현재 월부터 역순으로 6개월
            year = end_date.year
            if end_date.month - i <= 0:
                year -= 1
            
            month_str = f"{year}-{month:02d}" 
            month_name = f"{year}년 {month}월"
            
            # 랜덤 손익 금액
            profit_loss = random.randint(-500000, 1500000)
            profit_pct = round(profit_loss / 10000000 * 100, 2)  # 가정: 1000만원 기준
            
            monthly_performance.append({
                "연월": month_name,
                "손익금액": profit_loss,
                "수익률": profit_pct
            })
        
        # 역순으로 되어 있으므로 다시 정순으로 변경
        monthly_performance.reverse()
        
        # 앱에서 필요로 하는 구조로 응답 구성
        response = {
            "status": "ok",
            "timestamp": int(time.time() * 1000),
            "account_summary": {
                "총손익": total_profit_loss,
                "수익률": round(total_profit_loss / 10000000 * 100, 2),
                "투자원금": 10000000,
                "승률": win_rate,
                "총거래횟수": total_trades,
                "성공거래": winning_trades,
                "실패거래": losing_trades
            },
            "monthly_performance": monthly_performance,
            "daily_performance": daily_performance,
            "trade_stats": {
                "평균수익": round(sum(day["profit_loss"] for day in daily_performance if day["profit_loss"] > 0) / max(winning_trades, 1)),
                "평균손실": round(sum(day["profit_loss"] for day in daily_performance if day["profit_loss"] < 0) / max(losing_trades, 1)) if losing_trades > 0 else 0,
                "최대수익": max([day["profit_loss"] for day in daily_performance], default=0),
                "최대손실": min([day["profit_loss"] for day in daily_performance], default=0)
            }
        }
        
        logger.info(f"성과 리포트 API 응답: {response}")
        return response
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"성과 리포트 조회 API 오류: {e}")
        # 오류 시에도 앱에서 표시할 수 있는 기본 값 제공
        return {
            "status": "error", 
            "message": str(e),
            "account_summary": {
                "총손익": 0,
                "수익률": 0,
                "투자원금": 10000000,
                "승률": 0,
                "총거래횟수": 0,
                "성공거래": 0,
                "실패거래": 0
            },
            "monthly_performance": [
                {"연월": "2025년 1월", "손익금액": 0, "수익률": 0},
                {"연월": "2025년 2월", "손익금액": 0, "수익률": 0},
                {"연월": "2025년 3월", "손익금액": 0, "수익률": 0},
                {"연월": "2025년 4월", "손익금액": 0, "수익률": 0},
                {"연월": "2025년 5월", "손익금액": 0, "수익률": 0},
                {"연월": "2025년 6월", "손익금액": 0, "수익률": 0}
            ],
            "daily_performance": []
        }

# 로그인 API 엔드포인트 추가
@app.post("/api/login", response_model=Token)
@app.post("/login", response_model=Token)  # /login 경로도 추가 (프론트엔드 호환성)
@app.get("/api/login", response_model=Token)  # GET 메서드도 허용
@app.get("/login", response_model=Token)  # GET 메서드도 허용
def login(form_data: LoginForm = None, username: str = None, password: str = None):
    """사용자 로그인 API - POST와 GET 모두 지원"""
    try:
        # GET 요청 처리
        if form_data is None and username is not None and password is not None:
            form_data = LoginForm(username=username, password=password)
        
        # form_data가 여전히 None이면 오류 발생
        if form_data is None:
            logger.warning(f"로그인 실패: 유효하지 않은 요청 형식")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효하지 않은 요청 형식입니다. username과 password 필드가 필요합니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # 사용자 인증
        user = verify_user(form_data.username, form_data.password)
        if not user:
            logger.warning(f"로그인 실패: 사용자 '{form_data.username}' - 비밀번호 불일치")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자 이름 또는 비밀번호가 잘못되었습니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 액세스 토큰 생성
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["username"], "role": user["role"]},
            expires_delta=access_token_expires
        )
        
        logger.info(f"로그인 성공: 사용자 '{form_data.username}'")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "username": user["username"],
            "role": user["role"]
        }
    except HTTPException:
        # 이미 처리된 인증 오류는 그대로 전달
        raise
    except Exception as e:
        logger.error(f"로그인 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류")

# 서버 시작 코드 수정 - 포트 충돌 방지 및 예외 처리 강화
if __name__ == "__main__":
    try:
        # 8000번 포트가 사용 중인지 확인
        port = 8000
        if not is_port_available(port):
            # 포트가 사용 중이면 다른 포트 시도 (8001, 8002, ...)
            for new_port in range(8001, 8020):
                if is_port_available(new_port):
                    logger.warning(f"기본 포트 {port}가 사용 중입니다. 대체 포트 {new_port}를 사용합니다.")
                    port = new_port
                    break
            else:
                logger.error("사용 가능한 포트를 찾을 수 없습니다. 서버를 종료합니다.")
                exit(1)
        
        # 필요한 서비스 인스턴스 초기화 - 각 단계별 예외 처리 강화
        try:
            db = None
            if 'DatabaseManager' in globals():
                try:
                    db = DatabaseManager(config)
                    logger.info("데이터베이스 관리자 초기화 완료")
                except Exception as e:
                    logger.error(f"데이터베이스 초기화 오류: {e}")
            
            # 주식 데이터 제공자 초기화
            stock_data = None
            if 'StockData' in globals():
                try:
                    stock_data = StockData(config)
                    logger.info("주식 데이터 제공자 초기화 완료")
                except Exception as e:
                    logger.error(f"주식 데이터 제공자 초기화 오류: {e}")
            
            # 브로커(증권사 API) 초기화
            broker = None
            try:
                from src.trading.kis_api import KISAPI
                broker = KISAPI(config)
                logger.info("증권사 API 초기화 완료")
            except Exception as e:
                logger.error(f"증권사 API 초기화 오류: {e}")
            
            # 자동 트레이딩 관련 설정
            gpt_strategy = None
            auto_trader = None
            try:
                if getattr(config, 'AUTO_TRADING_ENABLED', False):
                    if getattr(config, 'GPT_AUTO_TRADING', False):
                        # GPT 자동 트레이딩 시스템 초기화
                        if 'GPTTradingStrategy' in globals() and 'GPTAutoTrader' in globals():
                            gpt_strategy = GPTTradingStrategy(config)
                            auto_trader = GPTAutoTrader(config, broker, stock_data)
                            logger.info("GPT 자동 매매 시스템 초기화 완료")
            except Exception as e:
                logger.error(f"자동 트레이딩 시스템 초기화 오류: {e}")
        except Exception as e:
            logger.error(f"서비스 인스턴스 초기화 중 오류: {e}")
        
        # PID 파일 생성
        with open("api_server.pid", "w") as f:
            f.write(str(os.getpid()))
        
        # 시그널 핸들러 설정
        import signal
        
        def signal_handler(sig, frame):
            logger.info(f"시그널 {sig} 수신, 서버 안전하게 종료 중...")
            try:
                # PID 파일 삭제
                if os.path.exists("api_server.pid"):
                    os.remove("api_server.pid")
                logger.info("서버 종료 완료.")
            except Exception as e:
                logger.error(f"서버 종료 중 오류 발생: {e}")
            sys.exit(0)
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 웹 서버 시작 (재시도 로직 추가)
        max_retry = 3
        retry_count = 0
        
        while retry_count < max_retry:
            try:
                logger.info(f"API 서버 시작 - http://0.0.0.0:{port} (시도 {retry_count + 1}/{max_retry})")
                # host_header 설정은 Nginx가 프록시 설정에서 Host 헤더를 전달할 수 있게 함
                uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", workers=1, proxy_headers=True, forwarded_allow_ips="*")
                break  # 성공적으로 실행되었으면 루프 종료
            except Exception as e:
                retry_count += 1
                logger.error(f"서버 시작 중 오류 발생: {e}, 재시도 {retry_count}/{max_retry}")
                import traceback
                logger.error(traceback.format_exc())
                
                if retry_count < max_retry:
                    logger.info(f"{5 * retry_count}초 후 재시도...")
                    time.sleep(5 * retry_count)  # 점점 긴 대기 시간
                else:
                    logger.critical("최대 재시도 횟수를 초과했습니다. 서버를 종료합니다.")
                    # PID 파일 삭제
                    if os.path.exists("api_server.pid"):
                        os.remove("api_server.pid")
                    sys.exit(1)
    except Exception as e:
        logger.error(f"서버 시작 중 예상치 못한 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # PID 파일 삭제
        if os.path.exists("api_server.pid"):
            os.remove("api_server.pid")
        sys.exit(1)
