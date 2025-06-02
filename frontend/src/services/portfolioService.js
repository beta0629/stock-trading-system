import apiClient from './apiClient';

// 포트폴리오 관련 서비스
export const portfolioService = {
  // 포트폴리오 정보 조회
  getPortfolio: async () => {
    try {
      const response = await apiClient.get('/api/portfolio');
      return response.data;
    } catch (error) {
      console.error('포트폴리오 조회 오류:', error);
      throw error;
    }
  },

  // 거래 내역 조회
  getTradingHistory: async (market = null, days = 30) => {
    try {
      const params = { days };
      if (market) params.market = market;
      
      const response = await apiClient.get('/api/trading/history', { params });
      return response.data;
    } catch (error) {
      console.error('거래 내역 조회 오류:', error);
      throw error;
    }
  },
  
  // 성과 리포트 조회
  getPerformanceReport: async (days = 30) => {
    try {
      const response = await apiClient.get('/api/reports/performance', { 
        params: { days } 
      });
      return response.data;
    } catch (error) {
      console.error('성과 리포트 조회 오류:', error);
      throw error;
    }
  },
  
  // 주문 실행
  placeOrder: async (orderData) => {
    try {
      const response = await apiClient.post('/api/trading/order', orderData);
      return response.data;
    } catch (error) {
      console.error('주문 실행 오류:', error);
      throw error;
    }
  }
};