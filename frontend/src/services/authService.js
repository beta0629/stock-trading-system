import axios from 'axios';
import jwtDecode from 'jwt-decode';
import apiClient, { API_URL, TOKEN_KEY } from './apiClient';
import websocketService from './websocketService';

// 사용자 정보 저장 키
const USER_INFO_KEY = 'user_info';
const OFFLINE_MODE_KEY = 'offline_mode';

// 인증 관련 서비스
export const authService = {
  /**
   * 사용자 로그인
   * @param {string} username - 사용자 이름
   * @param {string} password - 비밀번호
   * @returns {Promise<Object>} 토큰 정보
   */
  async login(username, password) {
    try {
      // 로그인 요청은 apiClient를 사용하지 않고 직접 axios 호출
      // (로그인 전이므로 토큰이 없음)
      const response = await axios.post(`${API_URL}/api/login`, {
        username,
        password
      });
      
      if (response.data.access_token) {
        // 토큰과 사용자 정보 저장
        localStorage.setItem(TOKEN_KEY, response.data.access_token);
        localStorage.setItem(USER_INFO_KEY, JSON.stringify(response.data.user_info || {}));
        
        // 오프라인 모드 해제
        localStorage.removeItem(OFFLINE_MODE_KEY);
        
        // WebSocket 서비스 초기화
        websocketService.initialize(response.data.access_token);
      }
      
      return response.data;
    } catch (error) {
      console.error('로그인 실패:', error);
      
      // 네트워크 오류인 경우 오프라인 모드 제안
      if (!error.response) {
        throw new Error('서버에 연결할 수 없습니다. 네트워크 연결을 확인해 주세요.');
      }
      
      // 서버 오류인 경우
      if (error.response && error.response.status >= 500) {
        throw new Error('서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }
      
      // 자격 증명 오류인 경우
      if (error.response && error.response.status === 401) {
        throw new Error('아이디 또는 비밀번호가 올바르지 않습니다.');
      }
      
      throw error;
    }
  },

  /**
   * 서버에 로그아웃 요청 (필요한 경우)
   */
  async logout() {
    try {
      // 토큰 및 사용자 정보 삭제
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_INFO_KEY);
      localStorage.removeItem(OFFLINE_MODE_KEY);
      
      // WebSocket 연결 종료
      websocketService.disconnectAll();
      
      return { success: true };
    } catch (error) {
      console.error('로그아웃 오류:', error);
      return { success: false, error: error.message };
    }
  },

  /**
   * 시스템 상태 확인 (토큰 유효성 간접 검증)
   */
  async getSystemStatus() {
    try {
      // 오프라인 모드인 경우
      if (this.isOfflineMode()) {
        return { 
          status: 'offline', 
          message: '오프라인 모드로 작동 중입니다.',
          serverVersion: '알 수 없음',
          lastUpdate: new Date().toISOString()
        };
      }
      
      const response = await apiClient.get('/api/system/status', { 
        timeout: 5000 // 5초 타임아웃 설정
      });
      
      // 오프라인 모드 해제 (정상 응답 받음)
      localStorage.removeItem(OFFLINE_MODE_KEY);
      
      // WebSocket 재연결 시도
      websocketService.reconnectAll();
      
      return response.data;
    } catch (error) {
      console.error('시스템 상태 확인 오류:', error);
      
      // 네트워크 오류이거나 서버 오류인 경우
      if (!error.response || error.response.status >= 500) {
        // 오프라인 모드 설정
        localStorage.setItem(OFFLINE_MODE_KEY, 'true');
        
        return { 
          status: 'error', 
          message: '서버에 연결할 수 없습니다. 오프라인 모드로 전환합니다.',
          serverVersion: '알 수 없음',
          lastUpdate: new Date().toISOString()
        };
      }
      
      throw error;
    }
  },
  
  /**
   * App.js에서 호출하는 함수명과 일치시키기 위한 별칭
   * @returns {boolean} 로그인 상태 여부
   */
  async isAuthenticated() {
    return this.isLoggedIn();
  },
  
  /**
   * 현재 사용자가 로그인 상태인지 확인
   * @returns {boolean} 로그인 상태 여부
   */
  isLoggedIn() {
    const token = this.getToken();
    
    // 토큰이 없으면 로그인 상태가 아님
    if (!token) return false;
    
    try {
      // 토큰 만료 여부 확인
      const decodedToken = jwtDecode(token);
      const currentTime = Date.now() / 1000;
      
      // 토큰이 만료되었으면 로그인 상태가 아님
      if (decodedToken.exp < currentTime) {
        this.logout(); // 만료된 토큰 제거
        return false;
      }
      
      return true;
    } catch (error) {
      console.error('토큰 검증 오류:', error);
      return false;
    }
  },

  /**
   * 현재 로그인한 사용자 정보 가져오기
   * @returns {Promise<Object>} 사용자 정보
   */
  async getCurrentUser() {
    return this.getUserInfo();
  },
  
  /**
   * 저장된 인증 토큰 가져오기
   * @returns {string|null} JWT 토큰
   */
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },
  
  /**
   * 저장된 사용자 정보 가져오기
   * @returns {Object} 사용자 정보
   */
  getUserInfo() {
    const userInfo = localStorage.getItem(USER_INFO_KEY);
    return userInfo ? JSON.parse(userInfo) : {};
  },
  
  /**
   * 어플리케이션 시작 시 인증 상태 복원
   */
  restoreAuth() {
    const token = this.getToken();
    if (token) {
      try {
        // 토큰 만료 여부 확인
        const decodedToken = jwtDecode(token);
        const currentTime = Date.now() / 1000;
        
        // 토큰이 만료된 경우
        if (decodedToken.exp < currentTime) {
          this.logout();
          return false;
        }
        
        // WebSocket 서비스 초기화 (오프라인 모드가 아닌 경우에만)
        if (!this.isOfflineMode()) {
          websocketService.initialize(token);
        }
        
        return true;
      } catch (error) {
        console.error('인증 상태 복원 오류:', error);
        this.logout();
        return false;
      }
    }
    return false;
  },
  
  /**
   * 오프라인 모드 여부 확인
   * @returns {boolean} 오프라인 모드 여부
   */
  isOfflineMode() {
    return localStorage.getItem(OFFLINE_MODE_KEY) === 'true';
  },
  
  /**
   * 오프라인 모드 설정
   * @param {boolean} isOffline - 오프라인 모드로 설정할지 여부
   */
  setOfflineMode(isOffline) {
    if (isOffline) {
      localStorage.setItem(OFFLINE_MODE_KEY, 'true');
    } else {
      localStorage.removeItem(OFFLINE_MODE_KEY);
      
      // 오프라인 모드 해제 시 WebSocket 재연결
      const token = this.getToken();
      if (token) {
        websocketService.reconnectAll();
      }
    }
  },
  
  /**
   * 서버 연결 상태 확인
   * @returns {Promise<boolean>} 서버 연결 가능 여부
   */
  async checkServerConnection() {
    try {
      await axios.get(`${API_URL}/api/health`, { 
        timeout: 3000 // 3초 타임아웃 설정
      });
      
      // 연결 성공 시 오프라인 모드 해제
      this.setOfflineMode(false);
      
      return true;
    } catch (error) {
      console.error('서버 연결 확인 오류:', error);
      
      // 연결 실패 시 오프라인 모드 설정
      this.setOfflineMode(true);
      
      return false;
    }
  }
};