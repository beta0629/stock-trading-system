"""
주식 기술적 지표 계산 모듈
"""
import pandas as pd
import numpy as np
import logging
import ta

# 로깅 설정
logger = logging.getLogger('Technical')

def calculate_indicators(df, config):
    """
    기술적 지표 계산
    
    Args:
        df: 주가 데이터 DataFrame (Open, High, Low, Close, Volume 컬럼 필요)
        config: 설정 모듈
        
    Returns:
        DataFrame: 기술적 지표가 추가된 DataFrame
    """
    try:
        # 입력 데이터 복사
        df_copy = df.copy()
        
        # RSI 계산
        df_copy['RSI'] = ta.momentum.RSIIndicator(
            close=df_copy['Close'], 
            window=config.RSI_PERIOD
        ).rsi()
        
        # 이동평균 계산
        df_copy['SMA_short'] = ta.trend.SMAIndicator(
            close=df_copy['Close'], 
            window=config.SHORT_TERM_MA
        ).sma_indicator()
        
        df_copy['SMA_long'] = ta.trend.SMAIndicator(
            close=df_copy['Close'], 
            window=config.LONG_TERM_MA
        ).sma_indicator()
        
        # MACD 계산
        macd = ta.trend.MACD(
            close=df_copy['Close'],
            window_slow=26,
            window_fast=12,
            window_sign=9
        )
        df_copy['MACD'] = macd.macd()
        df_copy['MACD_signal'] = macd.macd_signal()
        df_copy['MACD_hist'] = macd.macd_diff()
        
        # 볼린저 밴드 계산
        bollinger = ta.volatility.BollingerBands(
            close=df_copy['Close'],
            window=20,
            window_dev=2
        )
        df_copy['BB_high'] = bollinger.bollinger_hband()
        df_copy['BB_mid'] = bollinger.bollinger_mavg()
        df_copy['BB_low'] = bollinger.bollinger_lband()
        
        return df_copy
        
    except Exception as e:
        logger.error(f"기술적 지표 계산 중 오류 발생: {e}")
        return df

def analyze_signals(df, symbol, config):
    """
    매매 시그널 분석
    
    Args:
        df: 기술적 지표가 계산된 DataFrame
        symbol: 주식 코드/티커
        config: 설정 모듈
        
    Returns:
        dict: 매매 시그널 정보
    """
    signals = {
        'symbol': symbol,
        'price': df['Close'].iloc[-1],
        'timestamp': df.index[-1],
        'signals': []
    }
    
    # 최근 데이터가 없으면 빈 시그널 반환
    if len(df) < config.LONG_TERM_MA:
        return signals
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # RSI 매수/매도 신호
    if latest['RSI'] < config.RSI_OVERSOLD:
        signals['signals'].append({
            'type': 'BUY',
            'strength': 'MEDIUM',
            'reason': f'RSI 과매도 ({latest["RSI"]:.2f})'
        })
    elif latest['RSI'] > config.RSI_OVERBOUGHT:
        signals['signals'].append({
            'type': 'SELL',
            'strength': 'MEDIUM',
            'reason': f'RSI 과매수 ({latest["RSI"]:.2f})'
        })
    
    # 골든 크로스/데드 크로스
    if prev['SMA_short'] <= prev['SMA_long'] and latest['SMA_short'] > latest['SMA_long']:
        signals['signals'].append({
            'type': 'BUY',
            'strength': 'STRONG',
            'reason': '골든 크로스 발생'
        })
    elif prev['SMA_short'] >= prev['SMA_long'] and latest['SMA_short'] < latest['SMA_long']:
        signals['signals'].append({
            'type': 'SELL',
            'strength': 'STRONG',
            'reason': '데드 크로스 발생'
        })
    
    # MACD 신호
    if prev['MACD'] <= prev['MACD_signal'] and latest['MACD'] > latest['MACD_signal']:
        signals['signals'].append({
            'type': 'BUY',
            'strength': 'MEDIUM',
            'reason': 'MACD 매수 신호'
        })
    elif prev['MACD'] >= prev['MACD_signal'] and latest['MACD'] < latest['MACD_signal']:
        signals['signals'].append({
            'type': 'SELL',
            'strength': 'MEDIUM',
            'reason': 'MACD 매도 신호'
        })
    
    # 볼린저 밴드 신호
    if latest['Close'] < latest['BB_low']:
        signals['signals'].append({
            'type': 'BUY',
            'strength': 'WEAK',
            'reason': '볼린저 밴드 하단 돌파'
        })
    elif latest['Close'] > latest['BB_high']:
        signals['signals'].append({
            'type': 'SELL',
            'strength': 'WEAK',
            'reason': '볼린저 밴드 상단 돌파'
        })
    
    return signals