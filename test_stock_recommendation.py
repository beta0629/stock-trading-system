#!/usr/bin/env python3
"""
GPT 종목 선정 및 자동매매 테스트 스크립트
"""
import logging
import sys
import time
from src.ai_analysis.stock_selector import StockSelector
from src.notification.telegram_sender import TelegramSender
from src.notification.kakao_sender import KakaoSender
import config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('stock_recommendation_test.log')
    ]
)
logger = logging.getLogger('StockRecommendationTest')

class StockRecommendationTest:
    """종목 선정 테스트 클래스"""
    
    def __init__(self):
        """초기화 함수"""
        self.config = config
        
        # 카카오톡 메시지 전송 초기화
        self.use_kakao = self.config.USE_KAKAO
        self.kakao_sender = KakaoSender(config) if self.use_kakao else None
        
        # 텔레그램은 연결 문제로 이번 테스트에서는 사용하지 않음
        # self.telegram_sender = TelegramSender(config)
        
        # GPT 기반 종목 선정기 초기화
        self.stock_selector = StockSelector(config)
        
        logger.info("종목 선정 테스트 시스템 초기화 완료")
    
    def send_notification(self, message_type, data):
        """
        알림 메시지 전송 (카카오톡)
        
        Args:
            message_type: 메시지 유형 ('signal', 'status')
            data: 알림 데이터 또는 문자열
        """
        # 카카오톡으로 메시지 전송 (활성화된 경우)
        if self.use_kakao and self.kakao_sender:
            try:
                if message_type == 'signal':
                    self.kakao_sender.send_signal_notification(data)
                elif message_type == 'status':
                    self.kakao_sender.send_system_status(data)
                logger.info("카카오톡 메시지 전송 완료")
            except Exception as e:
                logger.error(f"카카오톡 메시지 전송 실패: {e}")
    
    def select_stocks_with_gpt(self):
        """GPT를 활용한 종목 선정"""
        logger.info("GPT 종목 선정 프로세스 시작")
        try:
            # 한국 시장 종목 추천 (균형, 성장, 배당 전략 모두 적용)
            strategies = ["balanced", "growth", "dividend"]
            kr_recommendations = {}
            
            for strategy in strategies:
                kr_result = self.stock_selector.recommend_stocks(
                    market="KR", 
                    count=3, 
                    strategy=strategy
                )
                kr_recommendations[strategy] = kr_result
                logger.info(f"KR {strategy} 전략 종목 추천 완료: {len(kr_result.get('recommended_stocks', []))}개")
                
            # 추천 종목 통합
            combined_kr_stocks = []
            kr_analysis = "📊 GPT 추천 국내 종목 분석\n\n"
            
            for strategy, result in kr_recommendations.items():
                if "recommended_stocks" in result and result["recommended_stocks"]:
                    kr_analysis += f"· {strategy.capitalize()} 전략:\n"
                    
                    for stock in result["recommended_stocks"]:
                        symbol = stock.get("symbol")
                        name = stock.get("name", symbol)
                        reason = stock.get("reason", "")
                        weight = stock.get("suggested_weight", 0)
                        
                        combined_kr_stocks.append({
                            "symbol": symbol,
                            "name": name,
                            "strategy": strategy
                        })
                        
                        kr_analysis += f"- {name} ({symbol}): {reason} (추천 비중: {weight}%)\n"
                    
                    kr_analysis += "\n"
            
            # 미국 시장 종목 추천
            us_result = self.stock_selector.recommend_stocks(
                market="US", 
                count=5, 
                strategy="balanced"
            )
            
            # 미국 종목 분석 추가
            us_analysis = "📊 GPT 추천 미국 종목 분석\n\n"
            if "recommended_stocks" in us_result and us_result["recommended_stocks"]:
                for stock in us_result["recommended_stocks"]:
                    symbol = stock.get("symbol")
                    name = stock.get("name", symbol)
                    reason = stock.get("reason", "")
                    weight = stock.get("suggested_weight", 0)
                    
                    us_analysis += f"- {name} ({symbol}): {reason} (추천 비중: {weight}%)\n"
            
            # 섹터 분석 추가
            sector_analysis = self.stock_selector.advanced_sector_selection(market="KR", sectors_count=3)
            
            # 섹터 분석 요약
            sector_summary = "📊 GPT 추천 유망 산업 분석\n\n"
            if "promising_sectors" in sector_analysis and sector_analysis["promising_sectors"]:
                for sector in sector_analysis["promising_sectors"]:
                    sector_name = sector.get("name")
                    growth = sector.get("growth_potential", 0)
                    key_drivers = sector.get("key_drivers", [])
                    
                    sector_summary += f"· {sector_name} (성장 잠재력: {growth}/10)\n"
                    sector_summary += f"  주요 성장 동력: {', '.join(key_drivers[:3])}\n\n"
                    
                    # 유망 섹터 내 종목 추천
                    sector_stocks = self.stock_selector.recommend_sector_stocks(
                        sector_name=sector_name,
                        market="KR",
                        count=2
                    )
                    
                    if "recommended_stocks" in sector_stocks and sector_stocks["recommended_stocks"]:
                        sector_summary += "  추천 종목:\n"
                        for stock in sector_stocks["recommended_stocks"]:
                            stock_symbol = stock.get("symbol")
                            stock_name = stock.get("name", stock_symbol)
                            reason = stock.get("reason", "")
                            
                            sector_summary += f"  - {stock_name} ({stock_symbol}): {reason[:50]}...\n"
                        
                        sector_summary += "\n"
            
            # 종목 리스트 업데이트
            self.stock_selector.update_config_stocks(
                kr_recommendations={"recommended_stocks": [stock for stock in combined_kr_stocks]},
                us_recommendations=us_result
            )
            
            # 종목 리스트 업데이트 확인
            updated_kr_stocks = getattr(self.config, 'KR_STOCKS', [])
            updated_us_stocks = getattr(self.config, 'US_STOCKS', [])
            kr_stock_info = getattr(self.config, 'KR_STOCK_INFO', [])
            us_stock_info = getattr(self.config, 'US_STOCK_INFO', [])
            
            # 종목 이름과 코드를 함께 표시하는 함수
            def format_stock_list(stock_info_list):
                formatted = []
                for item in stock_info_list:
                    formatted.append(f"{item['code']}({item['name']})")
                return ', '.join(formatted) if formatted else "없음"
            
            # 종목 업데이트 요약
            update_summary = "🔄 종목 리스트 업데이트\n\n"
            update_summary += f"- 국내 종목: {len(updated_kr_stocks)}개\n"
            if kr_stock_info:
                update_summary += f"  {format_stock_list(kr_stock_info)}\n"
            update_summary += f"\n- 미국 종목: {len(updated_us_stocks)}개\n"
            if us_stock_info:
                update_summary += f"  {format_stock_list(us_stock_info)}\n"
            update_summary += "\n종목 리스트가 GPT의 추천에 따라 업데이트되었습니다."
            
            # 분석 결과 전송
            self.send_notification('status', update_summary)
            time.sleep(2)  # API 제한 방지
            self.send_notification('status', kr_analysis)
            time.sleep(2)  # API 제한 방지
            self.send_notification('status', us_analysis)
            time.sleep(2)  # API 제한 방지
            self.send_notification('status', sector_summary)
            
            logger.info("GPT 종목 선정 및 업데이트 완료")
            return True
            
        except Exception as e:
            logger.error(f"GPT 종목 선정 중 오류 발생: {e}")
            self.send_notification('status', f"❌ GPT 종목 선정 중 오류 발생: {str(e)}")
            return False

if __name__ == "__main__":
    logger.info("GPT 종목 선정 테스트 시작")
    test = StockRecommendationTest()
    test.select_stocks_with_gpt()
    logger.info("GPT 종목 선정 테스트 완료")