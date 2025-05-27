"""
주식 데이터 수집 모듈 테스트
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
from src.data.stock_data import StockData
import config

class TestStockData(unittest.TestCase):
    """StockData 클래스 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.stock_data = StockData(config)
        
    def test_get_korean_stock_data(self):
        """한국 주식 데이터 수집 테스트"""
        # 삼성전자 데이터 가져오기
        df = self.stock_data.get_korean_stock_data("005930", days=10)
        
        # 데이터프레임이 비어있지 않은지 확인
        self.assertFalse(df.empty)
        
        # 필요한 컬럼이 있는지 확인
        expected_columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'SMA_short', 'SMA_long']
        for col in expected_columns:
            self.assertIn(col, df.columns)
            
    def test_get_us_stock_data(self):
        """미국 주식 데이터 수집 테스트"""
        # 애플 데이터 가져오기
        df = self.stock_data.get_us_stock_data("AAPL", period="1mo")
        
        # 데이터프레임이 비어있지 않은지 확인
        self.assertFalse(df.empty)
        
        # 필요한 컬럼이 있는지 확인
        expected_columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'SMA_short', 'SMA_long']
        for col in expected_columns:
            self.assertIn(col, df.columns)

if __name__ == "__main__":
    unittest.main()