import React, { createContext, useState, useEffect } from 'react';
import { authService } from '../services/authService';
import websocketService from '../services/websocketService';
import apiClient from '../services/apiClient';

// 인증 토큰 키 이름 (authService.js와 일치시킴)
const TOKEN_KEY = 'auth_token';

// 인증 컨텍스트 생성
export const AuthContext = createContext(null);

// 인증 컨텍스트 제공자 컴포넌트
export const AuthProvider = ({ children }) => {
  // 인증 상태 관리
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [error, setError] = useState(null);

  // 로그인 함수
  const login = async (username, password) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await authService.login(username, password);
      
      // 토큰을 상태에 저장 (localStorage에는 authService.login 내부에서 저장함)
      setToken(response.access_token);
      setUser(response.user_info || { username }); 
      setIsAuthenticated(true);
      
      return response;
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || '로그인 실패';
      setError(errorMsg);
      throw new Error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  // 로그아웃 함수
  const logout = async () => {
    try {
      // 백엔드 로그아웃 API 호출 및 클라이언트 상태 정리
      await authService.logout();
    } catch (err) {
      console.error('로그아웃 API 오류:', err);
    } finally {
      // 로컬 상태 정리
      setToken(null);
      setUser(null);
      setIsAuthenticated(false);
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem('user_info');
    }
  };

  // 사용자 정보 가져오기
  const fetchUserInfo = async () => {
    if (!token) {
      setIsAuthenticated(false);
      setUser(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    
    try {
      // apiClient는 interceptor를 통해 자동으로 토큰을 헤더에 추가합니다
      try {
        // 시스템 상태를 통해 간접적으로 토큰 검증
        const systemStatus = await authService.getSystemStatus();
        
        // 사용자 정보 가져오기
        const userInfo = await authService.getUserInfo();
        setUser(userInfo || { username: "관리자" });
        setIsAuthenticated(true);
      } catch (innerErr) {
        if (innerErr.response?.status === 401 || innerErr.response?.status === 403) {
          console.error('인증 실패:', innerErr);
          await logout();
          setError('인증이 만료되었습니다. 다시 로그인해주세요.');
        } else {
          console.error('사용자 정보 가져오기 오류:', innerErr);
          // 서버 오류는 인증 실패로 간주하지 않음
          setUser({ username: "관리자" });
          setIsAuthenticated(true);  // 토큰이 있으면 인증된 것으로 간주
          setError('서버에 연결할 수 없습니다. 일부 기능이 제한될 수 있습니다.');
        }
      }
    } catch (err) {
      console.error('사용자 정보 가져오기 오류:', err);
      setError(err.message || '사용자 정보를 가져오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  // 컴포넌트가 마운트될 때 인증 상태 복원 및 토큰 유효성 검사
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // 저장된 인증 정보 복원
        if (token) {
          authService.restoreAuth();
          await fetchUserInfo();
          
          try {
            // WebSocket 서비스 초기화
            websocketService.initialize(token);
          } catch (wsError) {
            console.error('WebSocket 초기화 오류:', wsError);
            // WebSocket 오류는 치명적이지 않으므로 인증 과정은 계속 진행
          }
        } else {
          setIsLoading(false);
        }
      } catch (err) {
        console.error('인증 초기화 오류:', err);
        setIsLoading(false);
      }
    };
    
    initializeAuth();
    
    // 컴포넌트 언마운트 시 웹소켓 연결 해제
    return () => {
      try {
        websocketService.disconnectAll();
      } catch (error) {
        console.error('WebSocket 연결 해제 오류:', error);
      }
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated,
        error,
        login,
        logout,
        fetchUserInfo
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};