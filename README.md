# AI 주식 분석 시스템

24시간 운영되는 클라우드 기반 주식 분석 시스템으로, 국내 주식(낮)과 미국 주식(밤)을 하이브리드 AI를 활용하여 자동으로 분석합니다.

## 주요 기능

- 국내/미국 주식 가격 데이터 수집
- RSI, 이동평균 등 기술적 지표 기반 매매 시그널 분석
- ChatGPT(GPT-4o)와 Gemini Pro를 활용한 하이브리드 AI 주식 분석
- 매수/매도 시그널 감지 시 텔레그램 및 카카오톡으로 알림 전송
- GitHub Actions를 통한 자동화된 정기 분석 및 보고서 생성
- 자동 매매 시스템 지원 (선택적 사용)

## 시스템 구조

- `src/data`: 주식 데이터 수집 모듈
- `src/analysis`: 기술적 지표 계산 및 매매 시그널 분석 모듈
- `src/ai_analysis`: AI 기반 주식 분석 모듈 (ChatGPT, Gemini, 하이브리드 전략)
- `src/notification`: 텔레그램 및 카카오톡 알림 전송 모듈
- `src/trading`: 자동 매매 시스템 및 증권사 API 연동 모듈
- `src/utils`: 유틸리티 함수 모듈
- `tests`: 테스트 코드
- `.github/workflows`: GitHub Actions 워크플로우 정의

## 설치 및 실행 방법

### 의존성 설치
```bash
pip install -r requirements.txt
```

### 실행 방법
```bash
# 전체 기능 실행
python main.py

# 분석만 실행 (국내 및 미국 시장)
python main.py --mode=analysis --market=all

# 한국 시장만 분석
python main.py --mode=analysis --market=KR

# 미국 시장만 분석
python main.py --mode=analysis --market=US

# 자동 매매만 실행
python main.py --mode=trading
```

## 환경 설정

### API 키 설정
`.env` 파일을 생성하고 다음의 API 키를 설정하세요:
```
# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o

# Google Gemini API 설정
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-pro

# 텔레그램 설정
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# 카카오톡 설정
KAKAO_API_KEY=your_kakao_api_key
KAKAO_ACCESS_TOKEN=your_kakao_access_token
KAKAO_REFRESH_TOKEN=your_kakao_refresh_token
```

### GitHub Actions 설정
GitHub 저장소에서 다음 Secrets를 설정하세요:

1. Settings > Secrets and variables > Actions로 이동
2. 다음 Secrets 추가:
   - `OPENAI_API_KEY`: OpenAI API 키
   - `GEMINI_API_KEY`: Gemini API 키
   - `KAKAO_API_KEY`: 카카오톡 API 키
   - `KAKAO_ACCESS_TOKEN`: 카카오톡 액세스 토큰
   - `KAKAO_REFRESH_TOKEN`: 카카오톡 리프레시 토큰
   - `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
   - `TELEGRAM_CHAT_ID`: 텔레그램 채팅 ID

## 최근 업데이트 (2025-05-28)

- Gemini API를 통합한 하이브리드 AI 분석 시스템 추가
- 시간대(timezone) 관련 버그 수정
- GitHub Actions 자동화 파이프라인 추가
- 명령줄 인수 처리 기능 추가
- 카카오톡 알림 개선 (AI 모델 구분 표시)