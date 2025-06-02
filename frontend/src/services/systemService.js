import apiClient from './apiClient';

// 시스템 관련 서비스
export const systemService = {
  // 시스템 상태 조회 (자동화 상태 포함)
  getSystemStatus: async () => {
    try {
      // 두 API 동시 호출 (시스템 상태와 자동화 상태를 병렬로 요청)
      const [systemResponse, automationResponse] = await Promise.all([
        apiClient.get('/api/system/status'),
        apiClient.get('/api/automation/status').catch(err => {
          console.warn('자동화 상태 조회 실패, 기본값 사용:', err);
          return { data: { auto_trading_enabled: false, gpt_auto_trading_enabled: false, gpt_auto_trader_running: false } };
        })
      ]);

      // 기존 시스템 상태 데이터
      const systemData = systemResponse.data;
      
      // 자동화 상태 데이터
      const automationData = automationResponse.data;
      
      // 데이터 병합
      return {
        ...systemData,
        trading_status: {
          ...systemData.trading_status,
          auto_trading_enabled: automationData.auto_trading_enabled,
          gpt_auto_trading_enabled: automationData.gpt_auto_trading_enabled,
          gpt_auto_trader_running: automationData.gpt_auto_trader_running
        }
      };
    } catch (error) {
      console.error('시스템 상태 조회 오류:', error);
      throw error;
    }
  },

  // 자동화 상태 조회
  getAutomationStatus: async () => {
    try {
      const response = await apiClient.get('/api/automation/status');
      return response.data;
    } catch (error) {
      console.error('자동화 상태 조회 오류:', error);
      throw error;
    }
  },

  // 자동화 설정 변경
  updateSettings: async (settings) => {
    try {
      const response = await apiClient.post('/api/automation/toggle', settings);
      return response.data;
    } catch (error) {
      console.error('자동화 설정 변경 오류:', error);
      throw error;
    }
  },

  // 트레이딩 사이클 실행
  runTradingCycle: async () => {
    try {
      const response = await apiClient.post('/api/automation/run_cycle', {});
      return response.data;
    } catch (error) {
      console.error('트레이딩 사이클 실행 오류:', error);
      throw error;
    }
  },

  // 서버 상태 확인 (헬스체크)
  healthCheck: async () => {
    try {
      const response = await apiClient.get('/api/health');
      return response.data;
    } catch (error) {
      console.error('서버 상태 확인 오류:', error);
      throw error;
    }
  }
};