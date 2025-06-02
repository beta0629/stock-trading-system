"""
주식 매매 시스템 데이터베이스 관리 모듈
"""
import os
import sqlite3
import pandas as pd
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from threading import Lock

class DatabaseManager:
    _instance = None
    _lock = Lock()
    
    @classmethod
    def get_instance(cls, config=None):
        """싱글톤 패턴으로 인스턴스 반환"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    if config is None:
                        # 환경 변수에서 직접 설정 가져오기
                        import os
                        import sys
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        parent_dir = os.path.dirname(os.path.dirname(current_dir))
                        sys.path.insert(0, parent_dir)
                        
                        # 환경 변수에서 설정 가져오기
                        try:
                            import config as config_module
                            config = config_module
                        except ImportError:
                            logger = logging.getLogger('DatabaseManager')
                            logger.error("config 모듈을 가져올 수 없습니다.")
                            # 기본값으로 환경 변수 설정
                            class ConfigFromEnv:
                                pass
                            config = ConfigFromEnv()
                    # 어떤 경우든 환경 변수를 통한 설정 객체를 생성
                    cls._instance = DatabaseManager(config)
        return cls._instance
    
    def __init__(self, config):
        """데이터베이스 관리자 초기화"""
        self.logger = logging.getLogger('DatabaseManager')
        self.config = config
        
        # 환경 변수에서 설정 가져오기
        import os
        
        # 데이터베이스 사용 여부 설정
        try:
            self.use_db = config.USE_DATABASE
        except AttributeError:
            self.use_db = os.environ.get("USE_DATABASE", "True").lower() == "true"
            self.logger.info(f"환경 변수에서 USE_DATABASE 설정: {self.use_db}")
        
        if not self.use_db:
            self.logger.warning("데이터베이스 사용이 비활성화되어 있습니다.")
            return
        
        # 데이터베이스 타입 설정
        try:
            self.db_type = config.DB_TYPE
        except AttributeError:
            self.db_type = os.environ.get("DB_TYPE", "sqlite").lower()
            self.logger.info(f"환경 변수에서 DB_TYPE 설정: {self.db_type}")
        
        # SQLite 설정
        if self.db_type == 'sqlite':
            try:
                self.db_path = config.SQLITE_DB_PATH
            except AttributeError:
                from pathlib import Path
                default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "stock_trading.db")
                self.db_path = os.environ.get("SQLITE_DB_PATH", default_path)
                self.logger.info(f"환경 변수에서 SQLITE_DB_PATH 설정: {self.db_path}")
            
            # 데이터베이스 디렉토리 생성
            from pathlib import Path
            Path(os.path.dirname(self.db_path)).mkdir(parents=True, exist_ok=True)
            # 데이터베이스 초기화
            self._init_sqlite_db()
        
        # MySQL 설정
        elif self.db_type == 'mysql':
            try:
                self.mysql_host = config.MYSQL_HOST
                self.mysql_port = config.MYSQL_PORT
                self.mysql_user = config.MYSQL_USER
                self.mysql_password = config.MYSQL_PASSWORD
                self.mysql_db = config.MYSQL_DB
            except AttributeError:
                self.mysql_host = os.environ.get("MYSQL_HOST", "localhost")
                self.mysql_port = int(os.environ.get("MYSQL_PORT", "3306"))
                self.mysql_user = os.environ.get("MYSQL_USER", "root")
                self.mysql_password = os.environ.get("MYSQL_PASSWORD", "")
                self.mysql_db = os.environ.get("MYSQL_DB", "stock_trading")
                self.logger.info(f"환경 변수에서 MySQL 설정을 가져왔습니다: {self.mysql_host}:{self.mysql_port}")
            
            # MySQL 데이터베이스 초기화
            self._init_mysql_db()
        else:
            self.logger.error(f"지원하지 않는 데이터베이스 타입: {self.db_type}")
            raise ValueError(f"지원하지 않는 데이터베이스 타입: {self.db_type}")
        
        # 자동 백업 설정
        try:
            self.auto_backup = config.DB_AUTO_BACKUP
            self.backup_interval = config.DB_BACKUP_INTERVAL
        except AttributeError:
            self.auto_backup = os.environ.get("DB_AUTO_BACKUP", "True").lower() == "true"
            self.backup_interval = int(os.environ.get("DB_BACKUP_INTERVAL", "24"))
            self.logger.info(f"환경 변수에서 백업 설정을 가져왔습니다: 자동 백업 {self.auto_backup}, 간격 {self.backup_interval}시간")
        
        # 마지막 백업 시간 초기화
        self.last_backup_time = datetime.now()
        
        # 자동 백업이 활성화된 경우 백업 디렉토리 생성
        if self.auto_backup:
            backup_dir = os.path.join(os.path.dirname(self.db_path), 'backup')
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
    
    def _init_sqlite_db(self):
        """SQLite 데이터베이스 초기화"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 트레이딩 이력 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                symbol TEXT,
                market TEXT,
                action TEXT,
                price REAL,
                quantity INTEGER,
                amount REAL,
                trade_type TEXT,
                strategy TEXT,
                confidence REAL,
                order_id TEXT,
                status TEXT,
                broker TEXT
            )
            ''')
            
            # 포트폴리오 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                symbol TEXT PRIMARY KEY,
                market TEXT,
                quantity INTEGER,
                avg_price REAL,
                current_price REAL,
                last_updated DATETIME,
                profit_loss REAL,
                profit_loss_pct REAL
            )
            ''')
            
            # GPT 추천 종목 이력
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS gpt_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                market TEXT,
                strategy TEXT,
                symbols TEXT,
                rationale TEXT,
                model TEXT
            )
            ''')
            
            # 시스템 이벤트 로그
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                event_type TEXT,
                description TEXT,
                details TEXT
            )
            ''')
            
            # 주가 데이터 캐시
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                market TEXT,
                date TEXT,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume INTEGER,
                UNIQUE(symbol, market, date)
            )
            ''')
            
            # 거래 성능 분석
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT,
                end_date TEXT,
                symbol TEXT,
                market TEXT,
                strategy TEXT,
                total_trades INTEGER,
                win_trades INTEGER,
                loss_trades INTEGER,
                win_rate REAL,
                avg_profit REAL,
                avg_loss REAL,
                total_profit_loss REAL,
                profit_loss_pct REAL
            )
            ''')
            
            # 한국 주식 종목 정보 테이블 추가
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS kr_stock_info (
                code TEXT PRIMARY KEY,
                name TEXT,
                market TEXT DEFAULT 'KR',
                sector TEXT,
                industry TEXT,
                updated_at DATETIME
            )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("SQLITE 데이터베이스 초기화 완료")
        except Exception as e:
            self.logger.error(f"SQLITE 데이터베이스 초기화 오류: {e}")
            raise
    
    def _init_mysql_db(self):
        """MySQL 데이터베이스 초기화"""
        try:
            import mysql.connector
            
            # MySQL 연결
            conn = mysql.connector.connect(
                host=self.mysql_host,
                port=self.mysql_port,
                user=self.mysql_user,
                password=self.mysql_password,
            )
            
            # 커서 생성
            cursor = conn.cursor()
            
            # 데이터베이스 생성 (없는 경우)
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.mysql_db}")
            cursor.execute(f"USE {self.mysql_db}")
            
            # 트레이딩 이력 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME,
                symbol VARCHAR(20),
                market VARCHAR(10),
                action VARCHAR(10),
                price DECIMAL(15, 2),
                quantity INT,
                amount DECIMAL(15, 2),
                trade_type VARCHAR(20),
                strategy VARCHAR(50),
                confidence DECIMAL(5, 4),
                order_id VARCHAR(50),
                status VARCHAR(20),
                broker VARCHAR(20)
            )
            ''')
            
            # 포트폴리오 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                symbol VARCHAR(20) PRIMARY KEY,
                market VARCHAR(10),
                quantity INT,
                avg_price DECIMAL(15, 2),
                current_price DECIMAL(15, 2),
                last_updated DATETIME,
                profit_loss DECIMAL(15, 2),
                profit_loss_pct DECIMAL(10, 6)
            )
            ''')
            
            # GPT 추천 종목 이력
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS gpt_recommendations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME,
                market VARCHAR(10),
                strategy VARCHAR(50),
                symbols TEXT,
                rationale TEXT,
                model VARCHAR(50)
            )
            ''')
            
            # 시스템 이벤트 로그
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME,
                event_type VARCHAR(50),
                description VARCHAR(255),
                details TEXT
            )
            ''')
            
            # 주가 데이터 캐시
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_cache (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20),
                market VARCHAR(10),
                date VARCHAR(10),
                open_price DECIMAL(15, 2),
                high_price DECIMAL(15, 2),
                low_price DECIMAL(15, 2),
                close_price DECIMAL(15, 2),
                volume BIGINT,
                UNIQUE KEY symbol_market_date (symbol, market, date)
            )
            ''')
            
            # 거래 성능 분석
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_performance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                start_date VARCHAR(10),
                end_date VARCHAR(10),
                symbol VARCHAR(20),
                market VARCHAR(10),
                strategy VARCHAR(50),
                total_trades INT,
                win_trades INT,
                loss_trades INT,
                win_rate DECIMAL(5, 2),
                avg_profit DECIMAL(15, 2),
                avg_loss DECIMAL(15, 2),
                total_profit_loss DECIMAL(15, 2),
                profit_loss_pct DECIMAL(10, 6)
            )
            ''')
            
            # 한국 주식 종목 정보 테이블 추가
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS kr_stock_info (
                code VARCHAR(10) PRIMARY KEY,
                name VARCHAR(50),
                market VARCHAR(10) DEFAULT 'KR',
                sector VARCHAR(50),
                industry VARCHAR(50),
                updated_at DATETIME
            )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("MySQL 데이터베이스 초기화 완료")
        except ImportError:
            self.logger.error("MySQL 연결을 위한 mysql-connector 모듈이 설치되어 있지 않습니다. pip install mysql-connector-python을 실행하세요.")
            raise
        except Exception as e:
            self.logger.error(f"MySQL 데이터베이스 초기화 오류: {e}")
            raise
    
    def _get_sqlite_connection(self):
        """SQLite 연결 반환"""
        return sqlite3.connect(self.db_path)
    
    def _get_mysql_connection(self):
        """MySQL 연결 반환"""
        import mysql.connector
        return mysql.connector.connect(
            host=self.mysql_host,
            port=self.mysql_port,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.mysql_db
        )
    
    def _get_connection(self):
        """데이터베이스 타입에 따라 적절한 연결 반환"""
        if not self.use_db:
            return None
            
        if self.db_type == 'sqlite':
            return self._get_sqlite_connection()
        elif self.db_type == 'mysql':
            return self._get_mysql_connection()
        else:
            raise ValueError(f"지원하지 않는 데이터베이스 타입: {self.db_type}")
    
    def record_trade(self, symbol, market, action, price, quantity, amount, trade_type="market", 
                    strategy="gpt", confidence=None, order_id=None, status="executed", broker="KIS"):
        """거래 내역 기록"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now()
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT INTO trade_history (timestamp, symbol, market, action, price, quantity, amount, 
                                        trade_type, strategy, confidence, order_id, status, broker)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (timestamp, symbol, market, action, price, quantity, amount, 
                    trade_type, strategy, confidence, order_id, status, broker))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO trade_history (timestamp, symbol, market, action, price, quantity, amount, 
                                        trade_type, strategy, confidence, order_id, status, broker)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (timestamp, symbol, market, action, price, quantity, amount, 
                    trade_type, strategy, confidence, order_id, status, broker))
            
            conn.commit()
            conn.close()
            self.logger.info(f"거래 내역 기록: {symbol} {action} {quantity}주 @ {price}")
            
            # 포트폴리오 업데이트
            if status == "executed":
                self._update_portfolio_after_trade(symbol, market, action, price, quantity)
            
            # 자동 백업 확인
            self._check_auto_backup()
            
            return True
        except Exception as e:
            self.logger.error(f"거래 내역 기록 오류: {e}")
            return False
    
    def _update_portfolio_after_trade(self, symbol, market, action, price, quantity):
        """거래 후 포트폴리오 업데이트"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 현재 포트폴리오 정보 조회
            if self.db_type == 'sqlite':
                cursor.execute('''
                SELECT quantity, avg_price FROM portfolio WHERE symbol = ?
                ''', (symbol,))
                result = cursor.fetchone()
            else:  # MySQL
                cursor.execute('''
                SELECT quantity, avg_price FROM portfolio WHERE symbol = %s
                ''', (symbol,))
                result = cursor.fetchone()
            
            current_qty = 0
            current_avg_price = 0
            
            if result:
                current_qty, current_avg_price = result
            
            # 매수/매도에 따라 수량과 평균가 업데이트
            if action.lower() == 'buy':
                # 신규 매수 또는 추가 매수
                new_quantity = current_qty + quantity
                if new_quantity > 0:
                    # 평균 매수가 계산
                    new_avg_price = (current_qty * current_avg_price + quantity * price) / new_quantity
                else:
                    new_avg_price = 0
                
                # 포트폴리오 업데이트
                self.update_portfolio(symbol, market, new_quantity, new_avg_price, price)
            
            elif action.lower() == 'sell':
                # 일부 매도 또는 전량 매도
                new_quantity = current_qty - quantity
                
                if new_quantity > 0:
                    # 평균가는 변경 없음 (매도 시에는 평균 매수가가 변경되지 않음)
                    self.update_portfolio(symbol, market, new_quantity, current_avg_price, price)
                elif new_quantity <= 0:
                    # 보유 수량이 0 이하면 포트폴리오에서 제거
                    if self.db_type == 'sqlite':
                        cursor.execute('''
                        DELETE FROM portfolio WHERE symbol = ?
                        ''', (symbol,))
                    else:  # MySQL
                        cursor.execute('''
                        DELETE FROM portfolio WHERE symbol = %s
                        ''', (symbol,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"포트폴리오 업데이트 오류: {e}")
    
    def update_portfolio(self, symbol, market, quantity, avg_price, current_price):
        """포트폴리오 정보 업데이트"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now()
            
            # 손익 계산
            profit_loss = (current_price - avg_price) * quantity
            profit_loss_pct = (current_price - avg_price) / avg_price * 100 if avg_price > 0 else 0
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT OR REPLACE INTO portfolio 
                (symbol, market, quantity, avg_price, current_price, last_updated, profit_loss, profit_loss_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (symbol, market, quantity, avg_price, current_price, timestamp, profit_loss, profit_loss_pct))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO portfolio 
                (symbol, market, quantity, avg_price, current_price, last_updated, profit_loss, profit_loss_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                quantity = %s,
                avg_price = %s,
                current_price = %s,
                last_updated = %s,
                profit_loss = %s,
                profit_loss_pct = %s
                ''', (
                    symbol, market, quantity, avg_price, current_price, timestamp, profit_loss, profit_loss_pct,
                    quantity, avg_price, current_price, timestamp, profit_loss, profit_loss_pct
                ))
            
            conn.commit()
            conn.close()
            
            # 자동 백업 확인
            self._check_auto_backup()
            
            return True
        except Exception as e:
            self.logger.error(f"포트폴리오 업데이트 오류: {e}")
            return False
    
    def save_gpt_recommendations(self, market, strategy, symbols, rationale, model="gpt-4o"):
        """GPT 종목 추천 저장"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now()
            
            # 리스트 또는 딕셔너리는 JSON으로 변환하여 저장
            if isinstance(symbols, (list, dict)):
                symbols = json.dumps(symbols, ensure_ascii=False)
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT INTO gpt_recommendations (timestamp, market, strategy, symbols, rationale, model)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (timestamp, market, strategy, symbols, rationale, model))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO gpt_recommendations (timestamp, market, strategy, symbols, rationale, model)
                VALUES (%s, %s, %s, %s, %s, %s)
                ''', (timestamp, market, strategy, symbols, rationale, model))
            
            conn.commit()
            conn.close()
            self.logger.info(f"GPT 추천 저장 완료: {market} {strategy} 전략")
            
            # 자동 백업 확인
            self._check_auto_backup()
            
            return True
        except Exception as e:
            self.logger.error(f"GPT 추천 저장 오류: {e}")
            return False
    
    def log_system_event(self, event_type, description, details=None):
        """시스템 이벤트 로깅"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now()
            
            if isinstance(details, (list, dict)):
                details = json.dumps(details, ensure_ascii=False)
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT INTO system_events (timestamp, event_type, description, details)
                VALUES (?, ?, ?, ?)
                ''', (timestamp, event_type, description, details))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO system_events (timestamp, event_type, description, details)
                VALUES (%s, %s, %s, %s)
                ''', (timestamp, event_type, description, details))
            
            conn.commit()
            conn.close()
            
            # 자동 백업 확인 (로그가 많이 쌓이므로 이벤트마다 체크할 필요는 없음)
            # self._check_auto_backup()
            
            return True
        except Exception as e:
            self.logger.error(f"시스템 이벤트 로깅 오류: {e}")
            return False
    
    def cache_price_data(self, symbol, market, date, open_price, high_price, low_price, close_price, volume):
        """주가 데이터 캐싱"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT OR REPLACE INTO price_cache 
                (symbol, market, date, open_price, high_price, low_price, close_price, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (symbol, market, date, open_price, high_price, low_price, close_price, volume))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO price_cache 
                (symbol, market, date, open_price, high_price, low_price, close_price, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                open_price = %s,
                high_price = %s,
                low_price = %s,
                close_price = %s,
                volume = %s
                ''', (
                    symbol, market, date, open_price, high_price, low_price, close_price, volume,
                    open_price, high_price, low_price, close_price, volume
                ))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            self.logger.error(f"주가 데이터 캐싱 오류: {e}")
            return False
    
    def get_cached_price_data(self, symbol, market, start_date=None, end_date=None):
        """캐시된 주가 데이터 조회"""
        if not self.use_db:
            return None
            
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM price_cache WHERE symbol = ? AND market = ?"
            params = [symbol, market]
            
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            
            query += " ORDER BY date"
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
        except Exception as e:
            self.logger.error(f"캐시된 주가 데이터 조회 오류: {e}")
            return None
    
    def get_trade_history(self, symbol=None, market=None, start_date=None, end_date=None, limit=100):
        """거래 이력 조회"""
        if not self.use_db:
            return pd.DataFrame()
            
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM trade_history WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if market:
                query += " AND market = ?"
                params.append(market)
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
        except Exception as e:
            self.logger.error(f"거래 이력 조회 오류: {e}")
            return pd.DataFrame()
    
    def get_portfolio(self):
        """현재 포트폴리오 조회"""
        if not self.use_db:
            return pd.DataFrame()
            
        try:
            conn = self._get_connection()
            df = pd.read_sql_query("SELECT * FROM portfolio", conn)
            conn.close()
            
            return df
        except Exception as e:
            self.logger.error(f"포트폴리오 조회 오류: {e}")
            return pd.DataFrame()
    
    def get_recent_recommendations(self, market=None, limit=10):
        """최근 GPT 추천 종목 조회"""
        if not self.use_db:
            return pd.DataFrame()
            
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM gpt_recommendations"
            params = []
            
            if market:
                query += " WHERE market = ?"
                params.append(market)
            
            query += " ORDER BY timestamp DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            # JSON 문자열을 Python 객체로 변환
            if not df.empty and 'symbols' in df.columns:
                df['symbols'] = df['symbols'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
            
            return df
        except Exception as e:
            self.logger.error(f"GPT 추천 종목 조회 오류: {e}")
            return pd.DataFrame()
    
    def get_system_events(self, event_type=None, start_date=None, end_date=None, limit=100):
        """시스템 이벤트 로그 조회"""
        if not self.use_db:
            return pd.DataFrame()
            
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM system_events WHERE 1=1"
            params = []
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            # JSON 문자열을 Python 객체로 변환
            if not df.empty and 'details' in df.columns:
                df['details'] = df['details'].apply(lambda x: json.loads(x) if isinstance(x, str) and x.strip() else x)
            
            return df
        except Exception as e:
            self.logger.error(f"시스템 이벤트 로그 조회 오류: {e}")
            return pd.DataFrame()
    
    def save_trade_performance(self, symbol, market, strategy, start_date, end_date, performance_data):
        """거래 성능 분석 결과 저장"""
        if not self.use_db:
            return
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 성능 데이터 추출
            total_trades = performance_data.get('total_trades', 0)
            win_trades = performance_data.get('win_trades', 0)
            loss_trades = performance_data.get('loss_trades', 0)
            win_rate = performance_data.get('win_rate', 0.0)
            avg_profit = performance_data.get('avg_profit', 0.0)
            avg_loss = performance_data.get('avg_loss', 0.0)
            total_profit_loss = performance_data.get('total_profit_loss', 0.0)
            profit_loss_pct = performance_data.get('profit_loss_pct', 0.0)
            
            if self.db_type == 'sqlite':
                cursor.execute('''
                INSERT INTO trade_performance 
                (start_date, end_date, symbol, market, strategy, total_trades, win_trades, 
                loss_trades, win_rate, avg_profit, avg_loss, total_profit_loss, profit_loss_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (start_date, end_date, symbol, market, strategy, total_trades, win_trades, 
                    loss_trades, win_rate, avg_profit, avg_loss, total_profit_loss, profit_loss_pct))
            else:  # MySQL
                cursor.execute('''
                INSERT INTO trade_performance 
                (start_date, end_date, symbol, market, strategy, total_trades, win_trades, 
                loss_trades, win_rate, avg_profit, avg_loss, total_profit_loss, profit_loss_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (start_date, end_date, symbol, market, strategy, total_trades, win_trades, 
                    loss_trades, win_rate, avg_profit, avg_loss, total_profit_loss, profit_loss_pct))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            self.logger.error(f"거래 성능 분석 결과 저장 오류: {e}")
            return False
    
    def _check_auto_backup(self):
        """자동 백업 수행 여부 확인"""
        if not self.use_db or not self.auto_backup:
            return
        
        current_time = datetime.now()
        time_diff = current_time - self.last_backup_time
        
        # 백업 간격을 시간으로 설정
        if time_diff.total_seconds() >= self.backup_interval * 3600:
            self.backup_database()
            self.last_backup_time = current_time
    
    def backup_database(self):
        """데이터베이스 백업"""
        if not self.use_db:
            return None
        
        # SQLite만 지원
        if self.db_type != 'sqlite':
            self.logger.warning("현재 SQLite 데이터베이스만 백업을 지원합니다.")
            return None
        
        try:
            # 백업 파일 이름 생성 (현재 시간 포함)
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(os.path.dirname(self.db_path), 'backup')
            backup_file = os.path.join(backup_dir, f"stock_trading_backup_{current_time}.db")
            
            # 디렉토리가 없으면 생성
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            
            # 데이터베이스 파일 복사
            shutil.copy2(self.db_path, backup_file)
            
            self.logger.info(f"데이터베이스 백업 완료: {backup_file}")
            return backup_file
        except Exception as e:
            self.logger.error(f"데이터베이스 백업 오류: {e}")
            return None
    
    def vacuum_database(self):
        """SQLite 데이터베이스 최적화 (VACUUM)"""
        if not self.use_db:
            return False
        
        # SQLite만 지원
        if self.db_type != 'sqlite':
            self.logger.warning("현재 SQLite 데이터베이스만 VACUUM을 지원합니다.")
            return False
        
        try:
            conn = self._get_connection()
            conn.execute("VACUUM")
            conn.close()
            
            self.logger.info("SQLite 데이터베이스 최적화 (VACUUM) 완료")
            return True
        except Exception as e:
            self.logger.error(f"SQLite 데이터베이스 최적화 오류: {e}")
            return False
    
    def get_daily_trading_summary(self, date=None):
        """일일 거래 요약"""
        if not self.use_db:
            return None
            
        try:
            conn = self._get_connection()
            
            # 날짜가 지정되지 않은 경우 오늘 날짜 사용
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # 해당 날짜 거래 내역 조회
            query = """
            SELECT 
                market,
                action,
                COUNT(*) as trade_count,
                SUM(amount) as total_amount,
                SUM(CASE WHEN action = 'buy' THEN amount ELSE 0 END) as buy_amount,
                SUM(CASE WHEN action = 'sell' THEN amount ELSE 0 END) as sell_amount
            FROM trade_history
            WHERE timestamp LIKE ?
            GROUP BY market, action
            """
            
            params = [f"{date}%"]
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
        except Exception as e:
            self.logger.error(f"일일 거래 요약 조회 오류: {e}")
            return None
    
    def analyze_performance(self, strategy=None, start_date=None, end_date=None):
        """전략별 성과 분석"""
        if not self.use_db:
            return None
            
        try:
            conn = self._get_connection()
            
            query = """
            SELECT 
                strategy,
                COUNT(*) as trade_count,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN profit_loss <= 0 THEN 1 ELSE 0 END) as loss_count,
                AVG(profit_loss) as avg_profit_loss,
                SUM(profit_loss) as total_profit_loss
            FROM (
                SELECT 
                    t1.strategy,
                    t1.symbol,
                    t1.price as buy_price,
                    t2.price as sell_price,
                    (t2.price - t1.price) * t1.quantity as profit_loss
                FROM trade_history t1
                JOIN trade_history t2 ON t1.symbol = t2.symbol AND t1.order_id = t2.order_id
                WHERE t1.action = 'buy' AND t2.action = 'sell'
                    AND t1.timestamp >= ?
                    AND t2.timestamp <= ?
            ) trades
            """
            
            params = []
            
            # 시작 날짜가 지정되지 않은 경우 30일 전으로 설정
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            # 종료 날짜가 지정되지 않은 경우 오늘 날짜로 설정
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            params.append(start_date)
            params.append(end_date)
            
            # 전략이 지정된 경우 필터링
            if strategy:
                query += " WHERE strategy = ?"
                params.append(strategy)
            
            query += " GROUP BY strategy"
            
            # MySQL 파라미터 형식으로 변환
            if self.db_type == 'mysql':
                query = query.replace('?', '%s')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
        except Exception as e:
            self.logger.error(f"전략별 성과 분석 오류: {e}")
            return None
    
    def save_kr_stock_info(self, stock_info_list):
        """한국 주식 종목 정보 저장/업데이트"""
        if not self.use_db:
            return False
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now()
            success_count = 0
            
            for stock in stock_info_list:
                code = stock.get('code')
                name = stock.get('name')
                sector = stock.get('sector', '')
                industry = stock.get('industry', '')
                
                if not code or not name:
                    self.logger.warning(f"종목 코드 또는 이름 누락: {stock}")
                    continue
                
                if self.db_type == 'sqlite':
                    cursor.execute('''
                    INSERT OR REPLACE INTO kr_stock_info 
                    (code, name, market, sector, industry, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (code, name, 'KR', sector, industry, timestamp))
                else:  # MySQL
                    cursor.execute('''
                    INSERT INTO kr_stock_info 
                    (code, name, market, sector, industry, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    name = %s,
                    sector = %s,
                    industry = %s,
                    updated_at = %s
                    ''', (code, name, 'KR', sector, industry, timestamp,
                           name, sector, industry, timestamp))
                success_count += 1
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"한국 주식 종목 정보 {success_count}개 저장/업데이트 완료")
            return True
        except Exception as e:
            self.logger.error(f"한국 주식 종목 정보 저장 오류: {e}")
            return False
    
    def get_kr_stock_info(self):
        """한국 주식 종목 정보 조회"""
        if not self.use_db:
            return []
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if self.db_type == 'sqlite':
                cursor.execute("SELECT code, name, sector, industry FROM kr_stock_info")
            else:  # MySQL
                cursor.execute("SELECT code, name, sector, industry FROM kr_stock_info")
            
            rows = cursor.fetchall()
            conn.close()
            
            # 결과를 딕셔너리 리스트로 변환
            stock_info_list = []
            for row in rows:
                if self.db_type == 'sqlite':
                    stock_info_list.append({
                        'code': row[0],
                        'name': row[1],
                        'sector': row[2] if row[2] else '',
                        'industry': row[3] if row[3] else ''
                    })
                else:  # MySQL은 커서가 다르게 동작할 수 있음
                    stock_info_list.append({
                        'code': row[0],
                        'name': row[1],
                        'sector': row[2] if row[2] else '',
                        'industry': row[3] if row[3] else ''
                    })
            
            self.logger.info(f"한국 주식 종목 정보 {len(stock_info_list)}개 조회 완료")
            return stock_info_list
        except Exception as e:
            self.logger.error(f"한국 주식 종목 정보 조회 오류: {e}")
            return []
    
    def init_kr_stock_info(self):
        """한국 주식 종목 정보 초기화 (없는 경우에만 기본 데이터 삽입)"""
        if not self.use_db:
            return False
            
        try:
            # 현재 저장된 종목 정보 확인
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM kr_stock_info")
            count = cursor.fetchone()[0]
            
            # 이미 데이터가 있으면 초기화 건너뛰기
            if count > 0:
                conn.close()
                self.logger.info(f"이미 {count}개의 한국 주식 종목 정보가 있습니다. 초기화 건너뜀.")
                return True
            
            # 기본 데이터 준비
            default_stocks = [
                {'code': '005930', 'name': '삼성전자'},
                {'code': '005940', 'name': 'NH투자증권'},
                {'code': '051900', 'name': 'LG생활건강'},
                {'code': '000660', 'name': 'SK하이닉스'},
                {'code': '051910', 'name': 'LG화학'},
                {'code': '035420', 'name': 'NAVER'},
                {'code': '096770', 'name': 'SK이노베이션'},
                {'code': '005380', 'name': '현대차'},
                {'code': '035720', 'name': '카카오'},
                {'code': '068270', 'name': '셀트리온'},
                {'code': '207940', 'name': '삼성바이오로직스'},
                {'code': '006400', 'name': '삼성SDI'},
                {'code': '018260', 'name': '삼성에스디에스'},
                {'code': '000270', 'name': '기아'},
                {'code': '005490', 'name': 'POSCO홀딩스'},
                {'code': '036570', 'name': 'NCsoft'},
                {'code': '055550', 'name': '신한지주'}
            ]
            
            timestamp = datetime.now()
            
            # 데이터 삽입
            for stock in default_stocks:
                code = stock['code']
                name = stock['name']
                
                if self.db_type == 'sqlite':
                    cursor.execute('''
                    INSERT INTO kr_stock_info (code, name, market, updated_at)
                    VALUES (?, ?, ?, ?)
                    ''', (code, name, 'KR', timestamp))
                else:  # MySQL
                    cursor.execute('''
                    INSERT INTO kr_stock_info (code, name, market, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ''', (code, name, 'KR', timestamp))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"한국 주식 종목 기본 정보 {len(default_stocks)}개 초기화 완료")
            return True
        except Exception as e:
            self.logger.error(f"한국 주식 종목 정보 초기화 오류: {e}")
            return False
    
    def check_connection(self):
        """데이터베이스 연결 상태 확인
        
        Returns:
            dict: 데이터베이스 연결 상태 정보
        """
        try:
            if not self.use_db:
                return {
                    "status": "disabled",
                    "message": "데이터베이스 사용이 비활성화되어 있습니다.",
                    "type": "none"
                }
            
            conn = self._get_connection()
            if conn is None:
                return {
                    "status": "error",
                    "message": "데이터베이스 연결에 실패했습니다.",
                    "type": self.db_type
                }
            
            # 간단한 쿼리 실행하여 연결 테스트
            cursor = conn.cursor()
            if self.db_type == 'sqlite':
                cursor.execute("SELECT sqlite_version();")
                version = cursor.fetchone()[0]
            else:  # MySQL
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
            
            conn.close()
            
            # 백업 디렉토리 확인
            backup_dir = os.path.join(os.path.dirname(self.db_path), 'backup')
            backup_available = os.path.exists(backup_dir)
            
            # 최근 백업 파일 확인
            latest_backup = None
            if backup_available:
                backup_files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
                if backup_files:
                    latest_backup = backup_files[-1]
            
            return {
                "status": "connected",
                "message": "데이터베이스 연결이 정상입니다.",
                "type": self.db_type,
                "version": version,
                "path": self.db_path if self.db_type == 'sqlite' else self.mysql_host,
                "auto_backup": self.auto_backup,
                "backup_available": backup_available,
                "latest_backup": latest_backup,
                "last_backup_time": self.last_backup_time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            self.logger.error(f"데이터베이스 연결 확인 오류: {e}")
            return {
                "status": "error",
                "message": f"데이터베이스 연결 확인 중 오류 발생: {str(e)}",
                "type": self.db_type
            }
    
    def get_db(self):
        """
        데이터베이스 연결 객체 반환
        
        Returns:
            object: 데이터베이스 연결 객체
        """
        conn = self._get_connection()
        if conn is None:
            raise Exception("데이터베이스 연결에 실패했습니다.")
        return conn