# 웹 기반 주식 트레이딩 시스템

파이썬으로 작성된 주식 트레이딩 시스템을 웹 기반으로 확장한 애플리케이션입니다. 이 시스템은 기존의 파이썬 기반 주식 트레이딩 로직을 유지하면서, 웹 인터페이스를 통해 원격 접속과 향상된 사용자 경험을 제공합니다.

## 시스템 아키텍처

시스템은 크게 다음과 같은 구조로 이루어져 있습니다:

```
Backend (FastAPI) <-> Frontend (React) <-> 사용자
      ^                    ^
      |                    |
      v                    v
   데이터베이스           브라우저
      ^
      |
      v
  외부 API 연동
  (증권사, AI 모델)
```

### 백엔드 (Python + FastAPI)
- 기존 파이썬 주식 트레이딩 로직 및 API 서버
- JWT 기반 인증 시스템
- RESTful API 엔드포인트
- WebSocket 기반 실시간 데이터 전송
- SQLite 데이터베이스 연동

### 프론트엔드 (React)
- 모던한 사용자 인터페이스
- 차트 기반 데이터 시각화
- 실시간 업데이트 (WebSocket 연동)
- 반응형 디자인
- 브라우저 알림 시스템

## 주요 기능

- **대시보드**: 트레이딩 시스템의 핵심 정보를 한 눈에 확인
- **주식 검색 및 분석**: 주식 목록 조회 및 상세 분석 확인
- **포트폴리오 관리**: 현재 보유 종목 및 자산 상태 관리
- **주문 실행**: 주식 매수 및 매도 주문 실행
- **자동 트레이딩**: AI 기반 자동 매매 시스템 구성 및 관리
- **리포팅**: 투자 성과 및 거래 내역 리포트 확인
- **실시간 알림**: 주요 이벤트 및 트레이딩 활동 실시간 알림
- **실시간 가격 업데이트**: WebSocket을 통한 실시간 가격 정보

## 설치 방법

### 요구 사항

- Python 3.9 이상
- Node.js 16 이상
- Docker (선택 사항)

### 로컬 개발 환경

1. **백엔드 설정**
   ```bash
   # 저장소 클론
   git clone https://github.com/yourusername/stock_sale.git
   cd stock_sale

   # 가상 환경 생성 및 활성화
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate

   # 의존성 설치
   pip install -r requirements.txt

   # API 서버 실행
   python api_server.py
   ```

2. **프론트엔드 설정**
   ```bash
   # 프론트엔드 디렉토리로 이동
   cd frontend

   # 의존성 설치
   npm install

   # 개발 서버 실행
   npm start
   ```

### Docker를 통한 배포

```bash
# Docker Compose를 통한 전체 시스템 배포
docker-compose up --build
```

## 환경 설정

기본 환경 설정을 위해 다음 환경 변수를 설정하거나 `.env` 파일을 생성하세요:

```
# 인증 설정
ADMIN_USERNAME=admin
ADMIN_PASSWORD=password
JWT_SECRET=your-secret-key-change-in-production

# API 키 설정
OPENAI_API_KEY=your-openai-api-key
GOOGLE_API_KEY=your-google-api-key
KIS_APP_KEY=your-kis-app-key
KIS_APP_SECRET=your-kis-app-secret
KIS_ACCOUNT_NO=your-kis-account-no

# 알림 설정
KAKAO_API_KEY=your-kakao-api-key
KAKAO_ACCESS_TOKEN=your-kakao-access-token
KAKAO_REFRESH_TOKEN=your-kakao-refresh-token
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id
```

## 사용 방법

### 웹 인터페이스 접속
- 로컬 개발: http://localhost:3000
- Docker 배포: http://localhost

### 로그인
- 기본 사용자이름: `admin`
- 기본 비밀번호: `password`
- 프로덕션 환경에서는 환경 변수를 통해 자격 증명을 설정하세요.

### 기본 워크플로우
1. 로그인 후 대시보드 확인
2. 주식 목록 페이지에서 관심 종목 조회
3. 종목 상세 페이지에서 분석 결과 확인 및 매매 주문 실행
4. 포트폴리오 페이지에서 보유 종목 및 계좌 현황 확인
5. 설정 페이지에서 자동 매매 기능 구성
6. 실시간 알림을 통해 중요 이벤트 모니터링

## 개발 가이드

### 프로젝트 구조

```
stock_sale/
│
├── api_server.py         # FastAPI 서버
├── main.py               # 기존 메인 스크립트
├── config.py             # 설정 파일
│
├── frontend/             # React 프론트엔드
│   ├── src/              # React 소스 코드
│   │   ├── components/   # 리액트 컴포넌트
│   │   ├── context/      # React 컨텍스트
│   │   ├── pages/        # 페이지 컴포넌트
│   │   └── services/     # API 서비스
│   └── public/           # 정적 파일
│
├── src/                  # 백엔드 소스 코드
│   ├── ai_analysis/      # AI 분석 모듈
│   ├── analysis/         # 기술적 분석 모듈
│   ├── data/             # 데이터 처리 모듈
│   ├── database/         # 데이터베이스 모듈
│   ├── notification/     # 알림 모듈
│   ├── trading/          # 트레이딩 모듈
│   └── utils/            # 유틸리티 모듈
│
├── data/                 # 데이터 저장소
│   └── stock_trading.db  # SQLite 데이터베이스
│
├── logs/                 # 로그 파일
└── cache/                # 캐시 파일
```

### API 엔드포인트

기본 API 엔드포인트는 다음과 같습니다:

#### REST API
- `POST /api/login` - 사용자 로그인
- `GET /api/system/status` - 시스템 상태 정보
- `GET /api/portfolio` - 포트폴리오 정보
- `GET /api/stocks/list` - 주식 목록
- `POST /api/stocks/data` - 특정 종목 데이터
- `POST /api/stocks/analyze` - 특정 종목 분석
- `POST /api/trading/order` - 주문 실행
- `GET /api/trading/history` - 거래 내역
- `GET /api/automation/status` - 자동화 상태
- `POST /api/automation/toggle` - 자동화 설정 변경
- `POST /api/automation/run_cycle` - 트레이딩 사이클 실행
- `GET /api/reports/performance` - 성과 리포트
- `GET /api/health` - 서버 상태 확인

#### WebSocket 엔드포인트
- `/ws/prices/{token}` - 실시간 가격 업데이트
- `/ws/notifications/{token}` - 실시간 알림
- `/ws/trading/{token}` - 실시간 트레이딩 업데이트

자세한 API 명세는 백엔드 서버 실행 후 `/docs` 또는 `/redoc` 엔드포인트에서 확인할 수 있습니다.

## 실시간 기능

### WebSocket 연결
프론트엔드는 세 가지 주요 WebSocket 채널을 통해 실시간 데이터를 수신합니다:

1. **가격 업데이트 채널**
   - 사용자가 모니터링하는 종목의 실시간 가격 정보
   - 변동률 및 거래량 정보

2. **알림 채널**
   - 시스템 알림 및 이벤트 통지
   - 중요 상태 변경 알림
   - 브라우저 알림과 연동

3. **트레이딩 업데이트 채널**
   - 주문 체결 정보
   - 자동 매매 시스템 상태 및 활동 내역
   - 트레이딩 사이클 실행 결과

### 실시간 알림 시스템
- 브라우저 알림 API 통합
- 알림 센터를 통한 중요 메시지 관리
- 읽음/안 읽음 상태 관리

## 다음 단계 개발 계획

다음은 시스템 개선을 위한 개발 계획입니다:

### 1. 고급 차트 기능
- TradingView 차트 통합
- 더 많은 기술적 지표 추가
- 사용자 정의 차트 레이아웃

### 2. AI 분석 엔진 확장
- 다양한 AI 모델(GPT-4, Gemini) 통합
- 멀티모달 분석 (뉴스, 차트, 재무제표 통합 분석)
- 사용자 정의 투자 전략 생성기

### 3. 모바일 앱 개발
- React Native를 활용한 모바일 앱 구현
- 푸시 알림 기능 추가
- 생체 인증 로그인

### 4. 백테스팅 모듈
- 과거 데이터를 활용한 전략 테스트 기능 구현
- 백테스트 결과 시각화
- 전략 최적화 도구

### 5. 사용자 관리 시스템
- 다중 사용자 지원
- 역할 기반 접근 제어
- 사용자 활동 로깅 및 감사

## 문제 해결 및 유지보수

### 로그 확인
- 백엔드 로그: `logs/` 디렉토리 확인
- 트레이딩 로그: `logs/trading_log_*.log`
- 주문 로그: `logs/order_log_*.log`
- API 서버 로그: `api_server.log`

### 일반적인 문제 해결
1. **API 연결 오류**: API 키와 시크릿이 올바르게 설정되었는지 확인
2. **인증 오류**: JWT 시크릿 키가 올바르게 설정되었는지 확인
3. **주문 실행 실패**: 시장 시간 및 계좌 잔고 확인
4. **WebSocket 연결 오류**: 네트워크 연결 및 토큰 유효성 확인
5. **실시간 데이터 누락**: 브라우저 콘솔에서 WebSocket 로그 확인

### 시스템 모니터링
- `process_monitor.py`를 통한 프로세스 상태 모니터링
- `check_status.py`를 통한 API 연결 상태 확인
- Docker 환경에서의 컨테이너 로그 확인

## 라이센스

이 프로젝트는 MIT 라이센스 하에 있습니다. 자세한 내용은 LICENSE 파일을 참조하십시오.

## 기여

1. 저장소를 Fork 하세요
2. 기능 브랜치를 생성하세요 (`git checkout -b feature/amazing-feature`)
3. 변경 사항을 커밋하세요 (`git commit -m 'Add some amazing feature'`)
4. 브랜치에 푸시하세요 (`git push origin feature/amazing-feature`)
5. Pull Request를 개설하세요

## 업데이트 내역

### 2025년 6월 1일
- WebSocket 기능 통합 완료
- 실시간 알림 시스템 구현
- 브라우저 알림 기능 추가
- 에러 처리 및 재연결 메커니즘 강화

### 2025년 5월
- 초기 버전 릴리스
- REST API 엔드포인트 구현
- 기본 UI 구성
- 자동 매매 시스템 통합

## 연락처

프로젝트 관리자 - [@yourusername](https://github.com/yourusername)