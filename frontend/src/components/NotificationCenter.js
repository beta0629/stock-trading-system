import React from 'react';
import { Offcanvas, ListGroup, Button, Badge } from 'react-bootstrap';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

function NotificationCenter({ show, onClose, notifications, onDismiss, onClearAll }) {
  // 알림 타입별 Badge 색상 설정
  const getNotificationBadge = (type) => {
    switch (type) {
      case 'success':
        return 'success';
      case 'error':
        return 'danger';
      case 'warning':
        return 'warning';
      case 'trade':
        return 'primary';
      default:
        return 'info';
    }
  };

  // 상대적 시간 포맷팅 (예: '3시간 전')
  const formatTimeAgo = (timestamp) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true, locale: ko });
    } catch (e) {
      return '알 수 없음';
    }
  };

  return (
    <Offcanvas show={show} onHide={onClose} placement="end">
      <Offcanvas.Header closeButton>
        <Offcanvas.Title>알림 센터</Offcanvas.Title>
        {notifications.length > 0 && (
          <Button 
            variant="outline-secondary" 
            size="sm" 
            onClick={onClearAll}
            className="ms-auto me-2"
          >
            모두 지우기
          </Button>
        )}
      </Offcanvas.Header>
      <Offcanvas.Body>
        {notifications.length === 0 ? (
          <div className="text-center text-muted py-4">
            새로운 알림이 없습니다
          </div>
        ) : (
          <ListGroup variant="flush">
            {notifications.map((notification) => (
              <ListGroup.Item 
                key={notification.id} 
                className="d-flex justify-content-between align-items-start"
              >
                <div className="ms-2 me-auto">
                  <div className="fw-bold">
                    <Badge bg={getNotificationBadge(notification.type)} className="me-1">
                      {notification.type === 'success' ? '성공' :
                       notification.type === 'error' ? '오류' :
                       notification.type === 'warning' ? '경고' :
                       notification.type === 'trade' ? '거래' : '정보'}
                    </Badge>
                    {formatTimeAgo(notification.timestamp)}
                  </div>
                  <p className="mb-1">{notification.message}</p>
                  {notification.data && notification.type === 'trade' && (
                    <div className="notification-details">
                      <small>
                        {notification.data.symbol} - 
                        {notification.data.action === 'buy' ? '매수' : '매도'} - 
                        {notification.data.quantity}주 - 
                        ₩{notification.data.price?.toLocaleString()}
                      </small>
                    </div>
                  )}
                </div>
                <Button 
                  variant="light" 
                  size="sm" 
                  onClick={() => onDismiss(notification.id)}
                  className="ms-2"
                >
                  ×
                </Button>
              </ListGroup.Item>
            ))}
          </ListGroup>
        )}
      </Offcanvas.Body>
    </Offcanvas>
  );
}

export default NotificationCenter;