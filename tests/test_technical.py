"""
기술적 지표 분석 모듈 테스트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from src.analysis.technical import calculate_indicators, analyze_signals
import config

class TestTechnicalAnalysis(unittest.TestCase):
    """기술적 지표 분석 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # 테스트용 데이터 생성
        dates = pd.date_range(start='2022-01-01', periods=100)
        self.df = pd.DataFrame({
            'Open': np.random.normal(100, 5, 100),
            'High': np.random.normal(105, 5, 100),
            'Low': np.random.normal(95, 5, 100),
            'Close': np.random.normal(100, 5, 100),
            'Volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
    def test_calculate_indicators(self):
        """지표 계산 테스트"""
        # 기술적 지표 계산
        df_with_indicators = calculate_indicators(self.df, config)
        
        # 결과 확인
        self.assertIn('RSI', df_with_indicators.columns)
        self.assertIn('SMA_short', df_with_indicators.columns)
        self.assertIn('SMA_long', df_with_indicators.columns)
        self.assertIn('MACD', df_with_indicators.columns)
        self.assertIn('MACD_signal', df_with_indicators.columns)
        self.assertIn('BB_high', df_with_indicators.columns)
        self.assertIn('BB_mid', df_with_indicators.columns)
        self.assertIn('BB_low', df_with_indicators.columns)
        
    def test_analyze_signals(self):
        """시그널 분석 테스트"""
        # 기술적 지표가 계산된 데이터 준비
        df_with_indicators = calculate_indicators(self.df, config)
        
        # 매매 시그널 분석
        signals = analyze_signals(df_with_indicators, "TEST", config)
        
        # 결과 확인
        self.assertIn('symbol', signals)
        self.assertEqual(signals['symbol'], "TEST")
        self.assertIn('price', signals)
        self.assertIn('timestamp', signals)
        self.assertIn('signals', signals)
        
        # 시그널 목록이 리스트인지 확인
        self.assertIsInstance(signals['signals'], list)

if __name__ == "__main__":
    unittest.main()