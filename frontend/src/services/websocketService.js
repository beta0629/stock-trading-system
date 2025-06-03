/**
 * WebSocket 서비스
 * 알림과 실시간 트레이딩 업데이트를 위한 WebSocket 연결 관리
 */

// WebSocket URL 설정
// 기본 URL과 포트 설정 - localhost로 변경
const WS_HOST = process.env.REACT_APP_API_URL ? process.env.REACT_APP_API_URL.replace('http', 'ws') : 'ws://localhost';
const WS_PORT = process.env.REACT_APP_WS_PORT || '8000';
const WS_BASE_URL = WS_PORT === '80' ? WS_HOST : `${WS_HOST}:${WS_PORT}`;

// 헬스 체크 활성화 여부
const ENABLE_HEALTH_CHECK = process.env.REACT_APP_ENABLE_HEALTH_CHECK === 'true';

// 로깅을 위해 설정된 URL 출력
console.log(`WebSocket 서버 URL: ${WS_BASE_URL}`);

// WebSocket 연결 상태 열거형
const ConnectionStatus = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
  ERROR: 'error',
  DISABLED: 'disabled'  // 새로운 상태: 서버가 없는 등의 이유로 기능이 비활성화됨
};

// 기본 WebSocket 설정
const DEFAULT_RECONNECT_INTERVAL = 2000; // 기본 재연결 간격 (2초)
const MAX_RECONNECT_INTERVAL = 30000;    // 최대 재연결 간격 (30초)
const RECONNECT_DECAY = 1.5;             // 재연결 간격 증가 배수
const MAX_RECONNECT_ATTEMPTS = 3;        // 최대 재연결 시도 횟수 (10에서 3으로 줄임)

class WebSocketService {
  constructor() {
    // WebSocket 인스턴스
    this.notificationSocket = null;
    this.tradingSocket = null;
    this.priceSocket = null;
    
    // 연결 상태
    this.notificationStatus = ConnectionStatus.DISCONNECTED;
    this.tradingStatus = ConnectionStatus.DISCONNECTED;
    this.priceStatus = ConnectionStatus.DISCONNECTED;
    
    // 인증 토큰
    this.authToken = null;
    
    // 재연결 관련 변수
    this.notificationReconnectAttempts = 0;
    this.tradingReconnectAttempts = 0;
    this.priceReconnectAttempts = 0;
    this.notificationReconnectTimer = null;
    this.tradingReconnectTimer = null;
    this.priceReconnectTimer = null;
    this.notificationReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    this.tradingReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    this.priceReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    
    // 콜백 함수
    this.onNotification = null;
    this.onTradingUpdate = null;
    this.onPriceUpdate = null;
    this.onConnectionStatusChange = null;
    
    // 모니터링 대상 종목 목록
    this.watchedSymbols = [];
    this.priceUpdateTimer = null;
    
    // 서버 연결 가능 상태
    this.webSocketEnabled = true;
  }

  /**
   * WebSocket 서비스 초기화
   * @param {string} token - JWT 인증 토큰
   */
  initialize(token) {
    if (!token) {
      console.error('WebSocket 초기화 오류: 인증 토큰이 없습니다.');
      return;
    }
    
    this.authToken = token;
    
    // 기존 연결이 있으면 해제
    this.disconnectAll();
    
    // 서버 접속 가능 여부 확인 후 연결
    this.checkServerAvailability().then(isAvailable => {
      if (isAvailable) {
        // 재연결 카운터 초기화
        this.resetReconnectCounters();
        
        // 새로운 연결 시작
        this.connectNotifications();
        this.connectTradingUpdates();
        this.connectPriceUpdates();
      } else {
        console.log('WebSocket 서버에 접속할 수 없어 연결을 비활성화합니다.');
        this.disableWebSockets();
      }
    });
  }
  
  /**
   * 서버 접속 가능 여부 확인
   * @returns {Promise<boolean>} 서버 접속 가능 여부
   */
  async checkServerAvailability() {
    // 헬스 체크가 비활성화된 경우 항상 서버가 가용한 것으로 간주
    if (ENABLE_HEALTH_CHECK === false) {
      console.log('헬스 체크 비활성화: 서버가 가용한 것으로 간주합니다.');
      this.webSocketEnabled = true;
      return true;
    }
    
    try {
      // 먼저 /api/health 엔드포인트로 서버 상태 확인
      console.log('API 서버 상태 확인 시도...');
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000); // 3초 타임아웃 설정
      
      const response = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/health`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
        signal: controller.signal
      }).finally(() => {
        clearTimeout(timeoutId);
      });
      
      if (response.ok) {
        console.log('API 서버 상태 확인 성공, 웹소켓 연결 활성화');
        this.webSocketEnabled = true;
        return true;
      } else {
        console.warn('API 서버 상태 확인 실패 (응답 코드:', response.status, ')');
        this.webSocketEnabled = false;
        return false;
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.warn('API 서버 상태 확인 타임아웃');
      } else {
        console.warn('서버 접속 불가능, WebSocket 비활성화:', error);
      }
      this.webSocketEnabled = false;
      return false;
    }
  }
  
  /**
   * WebSocket 기능 비활성화
   */
  disableWebSockets() {
    this.notificationStatus = ConnectionStatus.DISABLED;
    this.tradingStatus = ConnectionStatus.DISABLED;
    this.priceStatus = ConnectionStatus.DISABLED;
    this.webSocketEnabled = false;
    this.updateConnectionStatus();
    
    // 모든 타이머 및 연결 해제
    this.resetReconnectCounters();
    this.disconnectAll();
  }
  
  /**
   * 모니터링할 종목 심볼 설정
   * @param {Array<string>} symbols - 모니터링할 종목 코드 배열
   */
  updateWatchedSymbols(symbols) {
    // WebSocket이 비활성화된 경우 무시
    if (!this.webSocketEnabled) {
      return;
    }
    
    // 중복 제거 및 정리
    this.watchedSymbols = [...new Set(symbols.filter(Boolean))];
    
    // 이미 연결된 경우 모니터링 종목 업데이트 요청
    try {
      this.sendWatchedSymbolsUpdate();
    } catch (error) {
      console.error('감시 종목 업데이트 실패:', error);
    }
    
    // 가격 업데이트 타이머가 있으면 취소하고 다시 시작
    if (this.priceUpdateTimer) {
      clearInterval(this.priceUpdateTimer);
    }
    
    // 가격 업데이트 소켓이 연결되어 있지 않거나 오류 상태인 경우 재연결
    if (
      this.priceStatus !== ConnectionStatus.CONNECTED &&
      this.priceStatus !== ConnectionStatus.CONNECTING &&
      this.priceStatus !== ConnectionStatus.DISABLED
    ) {
      try {
        this.connectPriceUpdates();
      } catch (error) {
        console.error('가격 업데이트 소켓 연결 실패:', error);
      }
    }
    
    // 주기적으로 가격 업데이트 요청 (5초마다)
    if (this.webSocketEnabled && this.watchedSymbols.length > 0) {
      try {
        this.priceUpdateTimer = setInterval(() => {
          this.requestPriceUpdates();
        }, 5000);
      } catch (error) {
        console.error('가격 업데이트 타이머 설정 실패:', error);
      }
    }
  }
  
  /**
   * 가격 업데이트 요청
   */
  requestPriceUpdates() {
    if (
      this.priceSocket && 
      this.priceSocket.readyState === WebSocket.OPEN &&
      this.watchedSymbols.length > 0
    ) {
      try {
        // 감시 중인 종목의 가격 업데이트 요청
        this.priceSocket.send(JSON.stringify({
          symbols: this.watchedSymbols,
          markets: ['KR', 'US'] // 한국, 미국 시장 모두 포함
        }));
      } catch (error) {
        console.error('가격 업데이트 요청 중 오류:', error);
      }
    }
  }
  
  /**
   * 감시 종목 목록 업데이트 메시지 전송
   */
  sendWatchedSymbolsUpdate() {
    if (
      this.priceSocket && 
      this.priceSocket.readyState === WebSocket.OPEN &&
      this.watchedSymbols.length > 0
    ) {
      try {
        // 서버에 감시 종목 목록 업데이트 요청
        this.priceSocket.send(JSON.stringify({
          type: 'update_watched_symbols',
          symbols: this.watchedSymbols,
          markets: ['KR', 'US']
        }));
      } catch (error) {
        console.error('감시 종목 목록 업데이트 중 오류:', error);
      }
    }
  }
  
  /**
   * 알림 WebSocket 연결
   */
  connectNotifications() {
    // WebSocket이 비활성화된 경우 무시
    if (!this.webSocketEnabled) {
      return;
    }
    
    // 이미 연결 중이거나 연결된 상태면 무시
    if (
      this.notificationStatus === ConnectionStatus.CONNECTING ||
      this.notificationStatus === ConnectionStatus.CONNECTED
    ) {
      return;
    }
    
    try {
      // 연결 상태 업데이트
      this.notificationStatus = ConnectionStatus.CONNECTING;
      this.updateConnectionStatus();
      
      // WebSocket URL 생성 - '/ws' 경로 추가
      const wsUrl = `${WS_BASE_URL}/ws/notifications/${this.authToken}`;
      
      // WebSocket 인스턴스 생성
      this.notificationSocket = new WebSocket(wsUrl);
      
      // 이벤트 리스너 설정
      this.notificationSocket.onopen = this.handleNotificationOpen.bind(this);
      this.notificationSocket.onmessage = this.handleNotificationMessage.bind(this);
      this.notificationSocket.onclose = this.handleNotificationClose.bind(this);
      this.notificationSocket.onerror = this.handleNotificationError.bind(this);
    } catch (error) {
      console.error('알림 WebSocket 연결 오류:', error);
      this.notificationStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      this.scheduleNotificationReconnect();
    }
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 연결
   */
  connectTradingUpdates() {
    // WebSocket이 비활성화된 경우 무시
    if (!this.webSocketEnabled) {
      return;
    }
    
    // 이미 연결 중이거나 연결된 상태면 무시
    if (
      this.tradingStatus === ConnectionStatus.CONNECTING ||
      this.tradingStatus === ConnectionStatus.CONNECTED
    ) {
      return;
    }
    
    try {
      // 연결 상태 업데이트
      this.tradingStatus = ConnectionStatus.CONNECTING;
      this.updateConnectionStatus();
      
      // WebSocket URL 생성 - '/ws' 경로 추가
      const wsUrl = `${WS_BASE_URL}/ws/trading/${this.authToken}`;
      
      // WebSocket 인스턴스 생성
      this.tradingSocket = new WebSocket(wsUrl);
      
      // 이벤트 리스너 설정
      this.tradingSocket.onopen = this.handleTradingOpen.bind(this);
      this.tradingSocket.onmessage = this.handleTradingMessage.bind(this);
      this.tradingSocket.onclose = this.handleTradingClose.bind(this);
      this.tradingSocket.onerror = this.handleTradingError.bind(this);
    } catch (error) {
      console.error('트레이딩 업데이트 WebSocket 연결 오류:', error);
      this.tradingStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      this.scheduleTradingReconnect();
    }
  }
  
  /**
   * 가격 업데이트 WebSocket 연결
   */
  connectPriceUpdates() {
    // WebSocket이 비활성화된 경우 무시
    if (!this.webSocketEnabled) {
      return;
    }
    
    // 이미 연결 중이거나 연결된 상태면 무시
    if (
      this.priceStatus === ConnectionStatus.CONNECTING ||
      this.priceStatus === ConnectionStatus.CONNECTED
    ) {
      return;
    }
    
    try {
      // 연결 상태 업데이트
      this.priceStatus = ConnectionStatus.CONNECTING;
      this.updateConnectionStatus();
      
      // WebSocket URL 생성 - '/ws' 경로 추가
      const wsUrl = `${WS_BASE_URL}/ws/prices/${this.authToken}`;
      
      // WebSocket 인스턴스 생성
      this.priceSocket = new WebSocket(wsUrl);
      
      // 이벤트 리스너 설정
      this.priceSocket.onopen = this.handlePriceOpen.bind(this);
      this.priceSocket.onmessage = this.handlePriceMessage.bind(this);
      this.priceSocket.onclose = this.handlePriceClose.bind(this);
      this.priceSocket.onerror = this.handlePriceError.bind(this);
    } catch (error) {
      console.error('가격 업데이트 WebSocket 연결 오류:', error);
      this.priceStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      this.schedulePriceReconnect();
    }
  }
  
  /**
   * 알림 WebSocket 연결 해제
   */
  disconnectNotifications() {
    if (this.notificationSocket) {
      try {
        // 재연결 타이머 취소
        this.clearNotificationReconnectTimer();
        
        // 이벤트 리스너 제거 (메모리 누수 방지)
        this.notificationSocket.onopen = null;
        this.notificationSocket.onmessage = null;
        this.notificationSocket.onclose = null;
        this.notificationSocket.onerror = null;
        
        // 연결이 열려있을 때만 정상 종료
        if (this.notificationSocket.readyState === WebSocket.OPEN) {
          this.notificationSocket.close(1000, '사용자가 연결을 종료했습니다.');
        }
        
        // 인스턴스 정리
        this.notificationSocket = null;
        this.notificationStatus = ConnectionStatus.DISCONNECTED;
        this.updateConnectionStatus();
        
      } catch (error) {
        console.error('알림 WebSocket 연결 해제 오류:', error);
      }
    }
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 연결 해제
   */
  disconnectTradingUpdates() {
    if (this.tradingSocket) {
      try {
        // 재연결 타이머 취소
        this.clearTradingReconnectTimer();
        
        // 이벤트 리스너 제거 (메모리 누수 방지)
        this.tradingSocket.onopen = null;
        this.tradingSocket.onmessage = null;
        this.tradingSocket.onclose = null;
        this.tradingSocket.onerror = null;
        
        // 연결이 열려있을 때만 정상 종료
        if (this.tradingSocket.readyState === WebSocket.OPEN) {
          this.tradingSocket.close(1000, '사용자가 연결을 종료했습니다.');
        }
        
        // 인스턴스 정리
        this.tradingSocket = null;
        this.tradingStatus = ConnectionStatus.DISCONNECTED;
        this.updateConnectionStatus();
        
      } catch (error) {
        console.error('트레이딩 업데이트 WebSocket 연결 해제 오류:', error);
      }
    }
  }
  
  /**
   * 가격 업데이트 WebSocket 연결 해제
   */
  disconnectPriceUpdates() {
    if (this.priceSocket) {
      try {
        // 재연결 타이머 취소
        this.clearPriceReconnectTimer();
        
        // 이벤트 리스너 제거 (메모리 누수 방지)
        this.priceSocket.onopen = null;
        this.priceSocket.onmessage = null;
        this.priceSocket.onclose = null;
        this.priceSocket.onerror = null;
        
        // 연결이 열려있을 때만 정상 종료
        if (this.priceSocket.readyState === WebSocket.OPEN) {
          this.priceSocket.close(1000, '사용자가 연결을 종료했습니다.');
        }
        
        // 인스턴스 정리
        this.priceSocket = null;
        this.priceStatus = ConnectionStatus.DISCONNECTED;
        this.updateConnectionStatus();
        
      } catch (error) {
        console.error('가격 업데이트 WebSocket 연결 해제 오류:', error);
      }
    }
  }
  
  /**
   * 모든 WebSocket 연결 해제
   */
  disconnectAll() {
    this.disconnectNotifications();
    this.disconnectTradingUpdates();
    this.disconnectPriceUpdates();
  }
  
  /**
   * 모든 WebSocket 재연결 시도
   */
  reconnectAll() {
    // 재연결 카운터 초기화
    this.resetReconnectCounters();
    
    // 새 연결 시도
    this.connectNotifications();
    this.connectTradingUpdates();
    this.connectPriceUpdates();
  }
  
  /**
   * 알림 WebSocket 열림 이벤트 핸들러
   */
  handleNotificationOpen() {
    console.log('알림 WebSocket 연결 성공');
    
    // 연결 상태 업데이트
    this.notificationStatus = ConnectionStatus.CONNECTED;
    this.updateConnectionStatus();
    
    // 재연결 카운터 초기화
    this.notificationReconnectAttempts = 0;
    this.notificationReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    
    // 핑 메시지 보내기 (연결 유지)
    this.startNotificationPing();
  }
  
  /**
   * 알림 WebSocket 메시지 이벤트 핸들러
   * @param {MessageEvent} event - WebSocket 메시지 이벤트
   */
  handleNotificationMessage(event) {
    try {
      const data = JSON.parse(event.data);
      
      // 핑/퐁 메시지 처리
      if (data.type === 'ping') {
        this.sendNotificationPong();
        return;
      }
      
      // 콜백 함수가 등록되어 있으면 호출
      if (this.onNotification) {
        this.onNotification(data);
      }
    } catch (error) {
      console.error('알림 WebSocket 메시지 처리 오류:', error, event.data);
    }
  }
  
  /**
   * 알림 WebSocket 닫힘 이벤트 핸들러
   * @param {CloseEvent} event - WebSocket 닫힘 이벤트
   */
  handleNotificationClose(event) {
    console.log('알림 WebSocket 연결 종료:', event.code);
    
    // 이미 정상적으로 종료된 경우이거나 최대 재연결 횟수를 초과한 경우
    if (
      (event.code === 1000 && event.reason === '사용자가 연결을 종료했습니다.') ||
      this.notificationReconnectAttempts >= MAX_RECONNECT_ATTEMPTS
    ) {
      this.notificationStatus = ConnectionStatus.DISCONNECTED;
    } else {
      this.notificationStatus = ConnectionStatus.RECONNECTING;
      this.scheduleNotificationReconnect();
    }
    
    this.updateConnectionStatus();
    this.stopNotificationPing();
  }
  
  /**
   * 알림 WebSocket 오류 이벤트 핸들러
   * @param {Event} event - WebSocket 오류 이벤트
   */
  handleNotificationError(event) {
    console.error('알림 WebSocket 오류:', event);
    
    this.notificationStatus = ConnectionStatus.ERROR;
    this.updateConnectionStatus();
    
    // 오류 발생 시 재연결 시도
    this.scheduleNotificationReconnect();
    
    // 연속적인 오류가 발생하면 WebSocket 비활성화 검토
    if (this.notificationReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.checkServerAvailability().then(isAvailable => {
        if (!isAvailable) {
          this.disableWebSockets();
        }
      });
    }
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 열림 이벤트 핸들러
   */
  handleTradingOpen() {
    console.log('트레이딩 업데이트 WebSocket 연결 성공');
    
    // 연결 상태 업데이트
    this.tradingStatus = ConnectionStatus.CONNECTED;
    this.updateConnectionStatus();
    
    // 재연결 카운터 초기화
    this.tradingReconnectAttempts = 0;
    this.tradingReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    
    // 핑 메시지 보내기 (연결 유지)
    this.startTradingPing();
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 메시지 이벤트 핸들러
   * @param {MessageEvent} event - WebSocket 메시지 이벤트
   */
  handleTradingMessage(event) {
    try {
      const data = JSON.parse(event.data);
      
      // 핑/퐁 메시지 처리
      if (data.type === 'ping') {
        this.sendTradingPong();
        return;
      }
      
      // 콜백 함수가 등록되어 있으면 호출
      if (this.onTradingUpdate) {
        this.onTradingUpdate(data);
      }
    } catch (error) {
      console.error('트레이딩 업데이트 WebSocket 메시지 처리 오류:', error, event.data);
    }
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 닫힘 이벤트 핸들러
   * @param {CloseEvent} event - WebSocket 닫힘 이벤트
   */
  handleTradingClose(event) {
    console.log('트레이딩 업데이트 WebSocket 연결 종료:', event.code);
    
    // 이미 정상적으로 종료된 경우이거나 최대 재연결 횟수를 초과한 경우
    if (
      (event.code === 1000 && event.reason === '사용자가 연결을 종료했습니다.') ||
      this.tradingReconnectAttempts >= MAX_RECONNECT_ATTEMPTS
    ) {
      this.tradingStatus = ConnectionStatus.DISCONNECTED;
    } else {
      this.tradingStatus = ConnectionStatus.RECONNECTING;
      this.scheduleTradingReconnect();
    }
    
    this.updateConnectionStatus();
    this.stopTradingPing();
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 오류 이벤트 핸들러
   * @param {Event} event - WebSocket 오류 이벤트
   */
  handleTradingError(event) {
    console.error('트레이딩 업데이트 WebSocket 오류:', event);
    
    this.tradingStatus = ConnectionStatus.ERROR;
    this.updateConnectionStatus();
    
    // 오류 발생 시 재연결 시도
    this.scheduleTradingReconnect();
    
    // 연속적인 오류가 발생하면 WebSocket 비활성화 검토
    if (this.tradingReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.checkServerAvailability().then(isAvailable => {
        if (!isAvailable) {
          this.disableWebSockets();
        }
      });
    }
  }
  
  /**
   * 가격 업데이트 WebSocket 열림 이벤트 핸들러
   */
  handlePriceOpen() {
    console.log('가격 업데이트 WebSocket 연결 성공');
    
    // 연결 상태 업데이트
    this.priceStatus = ConnectionStatus.CONNECTED;
    this.updateConnectionStatus();
    
    // 재연결 카운터 초기화
    this.priceReconnectAttempts = 0;
    this.priceReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    
    // 핑 메시지 보내기 (연결 유지)
    this.startPricePing();
  }
  
  /**
   * 가격 업데이트 WebSocket 메시지 이벤트 핸들러
   * @param {MessageEvent} event - WebSocket 메시지 이벤트
   */
  handlePriceMessage(event) {
    try {
      const data = JSON.parse(event.data);
      
      // 핑/퐁 메시지 처리
      if (data.type === 'ping') {
        this.sendPricePong();
        return;
      }
      
      // 콜백 함수가 등록되어 있으면 호출
      if (this.onPriceUpdate) {
        this.onPriceUpdate(data);
      }
    } catch (error) {
      console.error('가격 업데이트 WebSocket 메시지 처리 오류:', error, event.data);
    }
  }
  
  /**
   * 가격 업데이트 WebSocket 닫힘 이벤트 핸들러
   * @param {CloseEvent} event - WebSocket 닫힘 이벤트
   */
  handlePriceClose(event) {
    console.log('가격 업데이트 WebSocket 연결 종료:', event.code);
    
    // 이미 정상적으로 종료된 경우이거나 최대 재연결 횟수를 초과한 경우
    if (
      (event.code === 1000 && event.reason === '사용자가 연결을 종료했습니다.') ||
      this.priceReconnectAttempts >= MAX_RECONNECT_ATTEMPTS
    ) {
      this.priceStatus = ConnectionStatus.DISCONNECTED;
    } else {
      this.priceStatus = ConnectionStatus.RECONNECTING;
      this.schedulePriceReconnect();
    }
    
    this.updateConnectionStatus();
    this.stopPricePing();
  }
  
  /**
   * 가격 업데이트 WebSocket 오류 이벤트 핸들러
   * @param {Event} event - WebSocket 오류 이벤트
   */
  handlePriceError(event) {
    console.error('가격 업데이트 WebSocket 오류:', event);
    
    this.priceStatus = ConnectionStatus.ERROR;
    this.updateConnectionStatus();
    
    // 오류 발생 시 재연결 시도
    this.schedulePriceReconnect();
    
    // 연속적인 오류가 발생하면 WebSocket 비활성화 검토
    if (this.priceReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.checkServerAvailability().then(isAvailable => {
        if (!isAvailable) {
          this.disableWebSockets();
        }
      });
    }
  }
  
  /**
   * 알림 WebSocket 재연결 예약
   */
  scheduleNotificationReconnect() {
    // 재연결 타이머가 이미 설정되어 있으면 취소
    this.clearNotificationReconnectTimer();
    
    // 최대 재연결 시도 횟수 초과 시 중단
    if (this.notificationReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.log(`알림 WebSocket 최대 재연결 시도 횟수 초과 (${MAX_RECONNECT_ATTEMPTS}회)`);
      this.notificationStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      return;
    }
    
    // 재연결 시도 횟수 증가
    this.notificationReconnectAttempts++;
    
    // 지수 백오프 알고리즘 적용 (재연결 간격 점점 증가)
    this.notificationReconnectInterval = Math.min(
      this.notificationReconnectInterval * RECONNECT_DECAY,
      MAX_RECONNECT_INTERVAL
    );
    
    console.log(`알림 WebSocket 재연결 시도 (${this.notificationReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}, ${this.notificationReconnectInterval}ms 후)`);
    
    // 타이머 설정
    this.notificationReconnectTimer = setTimeout(() => {
      this.connectNotifications();
    }, this.notificationReconnectInterval);
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 재연결 예약
   */
  scheduleTradingReconnect() {
    // 재연결 타이머가 이미 설정되어 있으면 취소
    this.clearTradingReconnectTimer();
    
    // 최대 재연결 시도 횟수 초과 시 중단
    if (this.tradingReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.log(`트레이딩 업데이트 WebSocket 최대 재연결 시도 횟수 초과 (${MAX_RECONNECT_ATTEMPTS}회)`);
      this.tradingStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      return;
    }
    
    // 재연결 시도 횟수 증가
    this.tradingReconnectAttempts++;
    
    // 지수 백오프 알고리즘 적용 (재연결 간격 점점 증가)
    this.tradingReconnectInterval = Math.min(
      this.tradingReconnectInterval * RECONNECT_DECAY,
      MAX_RECONNECT_INTERVAL
    );
    
    console.log(`트레이딩 업데이트 WebSocket 재연결 시도 (${this.tradingReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}, ${this.tradingReconnectInterval}ms 후)`);
    
    // 타이머 설정
    this.tradingReconnectTimer = setTimeout(() => {
      this.connectTradingUpdates();
    }, this.tradingReconnectInterval);
  }
  
  /**
   * 가격 업데이트 WebSocket 재연결 예약
   */
  schedulePriceReconnect() {
    // 재연결 타이머가 이미 설정되어 있으면 취소
    this.clearPriceReconnectTimer();
    
    // 최대 재연결 시도 횟수 초과 시 중단
    if (this.priceReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.log(`가격 업데이트 WebSocket 최대 재연결 시도 횟수 초과 (${MAX_RECONNECT_ATTEMPTS}회)`);
      this.priceStatus = ConnectionStatus.ERROR;
      this.updateConnectionStatus();
      return;
    }
    
    // 재연결 시도 횟수 증가
    this.priceReconnectAttempts++;
    
    // 지수 백오프 알고리즘 적용 (재연결 간격 점점 증가)
    this.priceReconnectInterval = Math.min(
      this.priceReconnectInterval * RECONNECT_DECAY,
      MAX_RECONNECT_INTERVAL
    );
    
    console.log(`가격 업데이트 WebSocket 재연결 시도 (${this.priceReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}, ${this.priceReconnectInterval}ms 후)`);
    
    // 타이머 설정
    this.priceReconnectTimer = setTimeout(() => {
      this.connectPriceUpdates();
    }, this.priceReconnectInterval);
  }
  
  /**
   * 알림 WebSocket 재연결 타이머 취소
   */
  clearNotificationReconnectTimer() {
    if (this.notificationReconnectTimer) {
      clearTimeout(this.notificationReconnectTimer);
      this.notificationReconnectTimer = null;
    }
  }
  
  /**
   * 트레이딩 업데이트 WebSocket 재연결 타이머 취소
   */
  clearTradingReconnectTimer() {
    if (this.tradingReconnectTimer) {
      clearTimeout(this.tradingReconnectTimer);
      this.tradingReconnectTimer = null;
    }
  }
  
  /**
   * 가격 업데이트 WebSocket 재연결 타이머 취소
   */
  clearPriceReconnectTimer() {
    if (this.priceReconnectTimer) {
      clearTimeout(this.priceReconnectTimer);
      this.priceReconnectTimer = null;
    }
  }
  
  /**
   * 재연결 관련 카운터 초기화
   */
  resetReconnectCounters() {
    this.notificationReconnectAttempts = 0;
    this.tradingReconnectAttempts = 0;
    this.priceReconnectAttempts = 0;
    this.notificationReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    this.tradingReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    this.priceReconnectInterval = DEFAULT_RECONNECT_INTERVAL;
    this.clearNotificationReconnectTimer();
    this.clearTradingReconnectTimer();
    this.clearPriceReconnectTimer();
  }
  
  /**
   * 연결 상태 변경 알림
   */
  updateConnectionStatus() {
    if (this.onConnectionStatusChange) {
      this.onConnectionStatusChange({
        notifications: this.notificationStatus,
        trading: this.tradingStatus,
        prices: this.priceStatus
      });
    }
  }
  
  /**
   * 알림 핑 메시지 시작
   */
  startNotificationPing() {
    // 이미 설정된 타이머가 있으면 취소
    this.stopNotificationPing();
    
    // 30초마다 핑 메시지 전송
    this.notificationPingTimer = setInterval(() => {
      this.sendNotificationPing();
    }, 30000);
  }
  
  /**
   * 알림 핑 메시지 중지
   */
  stopNotificationPing() {
    if (this.notificationPingTimer) {
      clearInterval(this.notificationPingTimer);
      this.notificationPingTimer = null;
    }
  }
  
  /**
   * 트레이딩 핑 메시지 시작
   */
  startTradingPing() {
    // 이미 설정된 타이머가 있으면 취소
    this.stopTradingPing();
    
    // 30초마다 핑 메시지 전송
    this.tradingPingTimer = setInterval(() => {
      this.sendTradingPing();
    }, 30000);
  }
  
  /**
   * 트레이딩 핑 메시지 중지
   */
  stopTradingPing() {
    if (this.tradingPingTimer) {
      clearInterval(this.tradingPingTimer);
      this.tradingPingTimer = null;
    }
  }
  
  /**
   * 가격 핑 메시지 시작
   */
  startPricePing() {
    // 이미 설정된 타이머가 있으면 취소
    this.stopPricePing();
    
    // 30초마다 핑 메시지 전송
    this.pricePingTimer = setInterval(() => {
      this.sendPricePing();
    }, 30000);
  }
  
  /**
   * 가격 핑 메시지 중지
   */
  stopPricePing() {
    if (this.pricePingTimer) {
      clearInterval(this.pricePingTimer);
      this.pricePingTimer = null;
    }
  }
  
  /**
   * 알림 핑 메시지 전송
   */
  sendNotificationPing() {
    if (this.notificationSocket && this.notificationSocket.readyState === WebSocket.OPEN) {
      try {
        this.notificationSocket.send(JSON.stringify({ type: 'ping' }));
      } catch (error) {
        console.error('알림 WebSocket 핑 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 알림 퐁 메시지 전송
   */
  sendNotificationPong() {
    if (this.notificationSocket && this.notificationSocket.readyState === WebSocket.OPEN) {
      try {
        this.notificationSocket.send(JSON.stringify({ type: 'pong' }));
      } catch (error) {
        console.error('알림 WebSocket 퐁 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 트레이딩 핑 메시지 전송
   */
  sendTradingPing() {
    if (this.tradingSocket && this.tradingSocket.readyState === WebSocket.OPEN) {
      try {
        this.tradingSocket.send(JSON.stringify({ type: 'ping' }));
      } catch (error) {
        console.error('트레이딩 WebSocket 핑 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 트레이딩 퐁 메시지 전송
   */
  sendTradingPong() {
    if (this.tradingSocket && this.tradingSocket.readyState === WebSocket.OPEN) {
      try {
        this.tradingSocket.send(JSON.stringify({ type: 'pong' }));
      } catch (error) {
        console.error('트레이딩 WebSocket 퐁 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 가격 핑 메시지 전송
   */
  sendPricePing() {
    if (this.priceSocket && this.priceSocket.readyState === WebSocket.OPEN) {
      try {
        this.priceSocket.send(JSON.stringify({ type: 'ping' }));
      } catch (error) {
        console.error('가격 업데이트 WebSocket 핑 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 가격 퐁 메시지 전송
   */
  sendPricePong() {
    if (this.priceSocket && this.priceSocket.readyState === WebSocket.OPEN) {
      try {
        this.priceSocket.send(JSON.stringify({ type: 'pong' }));
      } catch (error) {
        console.error('가격 업데이트 WebSocket 퐁 메시지 전송 오류:', error);
      }
    }
  }
  
  /**
   * 알림 콜백 설정
   * @param {Function} callback - 알림 메시지 수신 시 호출할 콜백 함수
   */
  setNotificationCallback(callback) {
    this.onNotification = callback;
  }
  
  /**
   * 트레이딩 업데이트 콜백 설정
   * @param {Function} callback - 트레이딩 업데이트 메시지 수신 시 호출할 콜백 함수
   */
  setTradingUpdateCallback(callback) {
    this.onTradingUpdate = callback;
  }
  
  /**
   * 가격 업데이트 콜백 설정
   * @param {Function} callback - 가격 업데이트 메시지 수신 시 호출할 콜백 함수
   */
  setPriceUpdateCallback(callback) {
    this.onPriceUpdate = callback;
  }
  
  /**
   * 알림 구독 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 알림 메시지 수신 시 호출할 콜백 함수
   */
  subscribeNotifications(callback) {
    this.setNotificationCallback(callback);
  }
  
  /**
   * 알림 구독 해제 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 해제할 콜백 함수
   */
  unsubscribeNotifications(callback) {
    if (this.onNotification === callback) {
      this.onNotification = null;
    }
  }
  
  /**
   * 트레이딩 업데이트 구독 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 트레이딩 업데이트 메시지 수신 시 호출할 콜백 함수
   */
  subscribeTradingUpdates(callback) {
    this.setTradingUpdateCallback(callback);
  }
  
  /**
   * 트레이딩 업데이트 구독 해제 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 해제할 콜백 함수
   */
  unsubscribeTradingUpdates(callback) {
    if (this.onTradingUpdate === callback) {
      this.onTradingUpdate = null;
    }
  }
  
  /**
   * 가격 업데이트 구독 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 가격 업데이트 메시지 수신 시 호출할 콜백 함수
   */
  subscribePriceUpdates(callback) {
    this.setPriceUpdateCallback(callback);
  }
  
  /**
   * 가격 업데이트 구독 해제 (NotificationContext에서 사용하는 인터페이스)
   * @param {Function} callback - 해제할 콜백 함수
   */
  unsubscribePriceUpdates(callback) {
    if (this.onPriceUpdate === callback) {
      this.onPriceUpdate = null;
    }
  }
  
  /**
   * 연결 상태 변경 콜백 설정
   * @param {Function} callback - 연결 상태 변경 시 호출할 콜백 함수
   */
  setConnectionStatusCallback(callback) {
    this.onConnectionStatusChange = callback;
  }
  
  /**
   * 현재 연결 상태 가져오기
   * @returns {Object} 연결 상태 객체
   */
  getConnectionStatus() {
    return {
      notifications: this.notificationStatus,
      trading: this.tradingStatus,
      prices: this.priceStatus
    };
  }
  
  /**
   * 현재 WebSocket 서비스가 연결되어 있는지 확인
   * @returns {boolean} 연결 상태 여부
   */
  isConnected() {
    return (
      this.notificationStatus === ConnectionStatus.CONNECTED ||
      this.tradingStatus === ConnectionStatus.CONNECTED ||
      this.priceStatus === ConnectionStatus.CONNECTED
    );
  }
}

// 싱글톤 인스턴스 생성
const websocketService = new WebSocketService();

export default websocketService;