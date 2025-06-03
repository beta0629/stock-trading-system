// API 클라이언트 모듈
import axios from 'axios';

// API 기본 URL 및 포트 설정
const API_HOST = process.env.REACT_APP_API_URL || 'http://localhost';
const API_PORT = process.env.REACT_APP_API_PORT || '8000';
export const API_URL = API_PORT === '80' ? API_HOST : `${API_HOST}:${API_PORT}`;

// 콘솔에 현재 API URL 표시 (디버깅용)
console.log(`API 서버 URL: ${API_URL}`);

// JWT 토큰 저장 키
export const TOKEN_KEY = 'auth_token';

// 기본 Axios 인스턴스 생성
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json'
  },
  timeout: 10000 // 10초 타임아웃
});

// 요청 인터셉터 설정
apiClient.interceptors.request.use(
  (config) => {
    // 로컬 스토리지에서 토큰 가져오기
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 응답 인터셉터 설정
apiClient.interceptors.response.use(
  (response) => {
    // 응답 성공 시 그대로 반환
    return response;
  },
  (error) => {
    // 인증 오류 처리 (401)
    if (error.response && error.response.status === 401) {
      // 토큰 만료 시 로그아웃 처리
      // 여기서는 로그아웃 함수를 직접 호출하지 않고 오류만 반환
      console.error('인증 실패: 토큰이 만료되었거나 유효하지 않습니다.');
    }
    
    // 서버 오류 처리 (500)
    if (error.response && error.response.status >= 500) {
      console.error('서버 오류 발생:', error.response.data);
    }
    
    // 네트워크 오류
    if (!error.response) {
      console.error('네트워크 오류: 서버에 연결할 수 없습니다.');
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;