import apiClient from './apiClient';

// 주식 데이터 관련 서비스
export const stockService = {
  // 주식 목록 조회
  getStockList: async (market = 'KR') => {
    try {
      const response = await apiClient.get(`/api/stocks/list`, {
        params: { market }
      });
      return response.data;
    } catch (error) {
      console.error('주식 목록 조회 오류:', error);
      throw error;
    }
  },

  // 특정 종목 데이터 조회
  getStockData: async (symbol, market = 'KR', period = '1mo') => {
    try {
      const response = await apiClient.post(`/api/stocks/data`, {
        symbol,
        market,
        period
      });
      return response.data;
    } catch (error) {
      console.error(`${symbol} 데이터 조회 오류:`, error);
      throw error;
    }
  },

  // 종목 분석 요청
  analyzeStock: async (symbol, market = 'KR', analysisType = 'general') => {
    try {
      const response = await apiClient.post(`/api/stocks/analyze`, {
        symbol,
        market,
        analysis_type: analysisType
      });
      return response.data;
    } catch (error) {
      console.error(`${symbol} 분석 오류:`, error);
      throw error;
    }
  },

  // 주문 실행
  placeOrder: async (orderData) => {
    try {
      const response = await apiClient.post(`/api/trading/order`, orderData);
      return response.data;
    } catch (error) {
      console.error('주문 실행 오류:', error);
      throw error;
    }
  }
};