import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AuthContext } from './AuthContext';
import websocketService from '../services/websocketService';

// 알림 컨텍스트 생성
export const NotificationContext = createContext(null);

// 알림 컨텍스트 제공자 컴포넌트
export const NotificationProvider = ({ children }) => {
  // 알림 메시지 배열 상태 관리
  const [notifications, setNotifications] = useState([]);
  // 알림 센터 표시 여부 상태
  const [showNotificationCenter, setShowNotificationCenter] = useState(false);
  // 새 알림 카운트 (읽지 않은 알림 수)
  const [newNotificationsCount, setNewNotificationsCount] = useState(0);
  // 웹소켓 연결 상태
  const [wsConnected, setWsConnected] = useState({
    notifications: false,
    trading: false,
    prices: false
  });
  
  // AuthContext에서 인증 정보 가져오기
  const { isAuthenticated, token } = useContext(AuthContext);

  // 알림 추가 함수
  const addNotification = useCallback((message, type = 'info', data = null) => {
    const newNotification = {
      id: uuidv4(),
      message,
      type,
      timestamp: new Date().toISOString(),
      read: false,
      data
    };
    
    setNotifications(prev => [newNotification, ...prev]);
    setNewNotificationsCount(prev => prev + 1);
    
    // 브라우저 알림 API 사용 (권한이 있는 경우)
    if (Notification.permission === 'granted') {
      // 브라우저 알림 타이틀 설정
      let title;
      switch (type) {
        case 'success': title = '성공'; break;
        case 'error': title = '오류'; break;
        case 'warning': title = '경고'; break;
        case 'trade': title = '거래 알림'; break;
        default: title = '정보'; break;
      }
      
      // 브라우저 알림 생성
      const notification = new Notification(title, {
        body: message,
        icon: '/favicon.ico'
      });
      
      // 알림 클릭 시 앱 포커스
      notification.onclick = () => {
        window.focus();
        setShowNotificationCenter(true);
      };
    }
    
    return newNotification.id;
  }, []);

  // 특정 알림 제거 함수
  const dismissNotification = useCallback((id) => {
    setNotifications(prev => {
      const notification = prev.find(n => n.id === id);
      // 읽지 않은 알림을 제거하는 경우 카운트 감소
      if (notification && !notification.read) {
        setNewNotificationsCount(count => Math.max(0, count - 1));
      }
      return prev.filter(notification => notification.id !== id);
    });
  }, []);

  // 모든 알림 제거 함수
  const clearAllNotifications = useCallback(() => {
    setNotifications([]);
    setNewNotificationsCount(0);
  }, []);

  // 알림 센터 표시/숨김 함수
  const toggleNotificationCenter = useCallback(() => {
    setShowNotificationCenter(prev => !prev);
    // 알림 센터를 열면 모든 알림이 읽은 상태로 표시
    if (!showNotificationCenter) {
      setNewNotificationsCount(0);
      setNotifications(prev => 
        prev.map(notification => ({ ...notification, read: true }))
      );
    }
  }, [showNotificationCenter]);

  // 웹소켓 알림 메시지 핸들러
  const handleNotification = useCallback((data) => {
    if (data.message) {
      addNotification(data.message, data.notification_type || 'info', data.data);
    }
  }, [addNotification]);

  // 웹소켓 트레이딩 업데이트 핸들러
  const handleTradingUpdate = useCallback((data) => {
    // 주문 실행 알림
    if (data.update_type === 'order_executed') {
      const orderData = data.data;
      const orderType = orderData.order_type === 'buy' ? '매수' : '매도';
      
      addNotification(
        `${orderData.symbol} ${orderType} 주문이 실행되었습니다. (${orderData.quantity}주, ${orderData.price ? orderData.price.toLocaleString() + '원' : '시장가'})`,
        'trade',
        orderData
      );
    }
    
    // 거래 사이클 완료 알림
    else if (data.update_type === 'cycle_completed') {
      const cycleData = data.data;
      
      if (cycleData.trades_count > 0) {
        addNotification(
          `자동 매매 사이클이 완료되었습니다. ${cycleData.trades_count}건의 거래가 실행되었습니다.`,
          'success',
          cycleData
        );
      }
    }
  }, [addNotification]);

  // 연결 상태 업데이트 함수
  const updateConnectionStatus = useCallback((type, isConnected) => {
    setWsConnected(prev => ({
      ...prev,
      [type]: isConnected
    }));
  }, []);

  // 웹소켓 서비스 초기화 및 구독
  useEffect(() => {
    // 인증 상태 변경에 따른 웹소켓 연결/해제 처리
    if (isAuthenticated && token) {
      // 웹소켓 서비스 초기화
      websocketService.initialize(token);
      
      // 알림 구독
      websocketService.subscribeNotifications(handleNotification);
      
      // 트레이딩 업데이트 구독
      websocketService.subscribeTradingUpdates(handleTradingUpdate);
      
      // 연결 성공 시 알림
      setTimeout(() => {
        if (websocketService.isConnected.notifications) {
          addNotification('실시간 알림 서비스에 연결되었습니다.', 'success');
        }
      }, 1000);
      
      // 연결 상태 변경 감시를 위한 인터벌 설정
      const intervalId = setInterval(() => {
        updateConnectionStatus('notifications', websocketService.isConnected.notifications);
        updateConnectionStatus('trading', websocketService.isConnected.trading);
        updateConnectionStatus('prices', websocketService.isConnected.prices);
      }, 3000);
      
      // 인증 토큰이 없는 경우 웹소켓 연결 해제
      return () => {
        clearInterval(intervalId);
        websocketService.unsubscribeNotifications(handleNotification);
        websocketService.unsubscribeTradingUpdates(handleTradingUpdate);
        websocketService.disconnectAll();
      };
    }
  }, [isAuthenticated, token, handleNotification, handleTradingUpdate, addNotification, updateConnectionStatus]);

  // 브라우저 알림 권한 요청
  useEffect(() => {
    // 브라우저가 알림을 지원하는지 확인
    if ('Notification' in window) {
      // 이미 권한이 부여되지 않은 경우에만 요청
      if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
      }
    }
  }, []);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        addNotification,
        dismissNotification,
        clearAllNotifications,
        showNotificationCenter,
        toggleNotificationCenter,
        newNotificationsCount,
        wsConnected
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
};