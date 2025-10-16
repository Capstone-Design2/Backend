# FastAPI Backend

객체지향 설계 원칙을 따른 FastAPI 백엔드 애플리케이션입니다.

## 📁 프로젝트 구조

```
Backend/
├── app/                        # 메인 애플리케이션 패키지
│   ├── core/                   # 환경설정 및 설정 관리
│   │   └── config.py           # 설정(환경 변수 로딩, Settings 클래스 등)
│   ├── models/                 # 데이터베이스 모델 (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py             # Base 클래스 (declarative_base 등)
│   │   └── user.py             # 사용자 모델
│   ├── repositories/           # 데이터 접근 계층 (DB 쿼리 로직)
│   │   ├── __init__.py
│   │   └── user_repository.py  # 사용자 CRUD
│   ├── routers/                # API 라우터
│   │   ├── __init__.py
│   │   ├── user_router.py      # 사용자 API
│   │   └── auth_router.py      # 인증/인가 API (로그인/토큰 갱신 등)
│   ├── schemas/                # Pydantic 스키마 (요청/응답)
│   │   ├── __init__.py
│   │   ├── user_schema.py      # 사용자 스키마
│   │   └── auth_schema.py      # 토큰/로그인 스키마
│   ├── services/               # 비즈니스 로직 계층
│   │   ├── __init__.py
│   │   ├── user_service.py     # 사용자 서비스
│   │   └── auth_service.py     # 인증 로직 (패스워드 검증, 토큰 발급)
│   ├── utils/                  # 유틸리티
│   │   ├── __init__.py
│   │   ├── datetime_utils.py   # 날짜/시간 유틸
│   │   ├── dependencies.py     # get_current_user 등 DI 의존성
│   │   ├── logger.py           # 로깅 설정/헬퍼
│   │   ├── router_utils.py     # 라우터 공통 유틸
│   │   └── security.py         # 해시/검증, JWT 유틸, OAuth2 스킴
│   ├── __init__.py
│   ├── database.py             # DB 연결/세션 관리
│   └── main.py                 # FastAPI 앱 진입점 (라우터 등록)
├── venv/                       # 가상환경 (커밋 금지 권장)
├── .env                        # 환경 변수 (커밋 금지)
├── .gitignore                  # Git 무시 규칙
├── README.md                   # 프로젝트 문서
├── requirements.txt            # Python 의존성
└── run.sh                      # 실행 스크립트
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 설정값을 조정하세요
```

### 2. 의존성 설치

```bash
# Python 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 또는 개발 의존성 포함 설치
pip install -e ".[dev]"
```

### 3. 애플리케이션 실행

```bash
# 개발 서버 실행
make run
# 또는
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Docker로 실행

```bash
# Docker Compose로 전체 스택 실행
docker-compose up --build

# 또는 Docker만 사용
docker build -t fastapi-backend .
docker run -p 8000:8000 fastapi-backend
```

## 📖 API 문서

서버 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:8000/caps_lock/api/docs
- **ReDoc**: http://localhost:8000/redoc

## 🏗️ 아키텍처

이 프로젝트는 **레이어드 아키텍처(Layered Architecture)** 패턴을 따릅니다:

1. **Controller Layer**: API 엔드포인트와 요청/응답 처리
2. **Service Layer**: 비즈니스 로직 처리
3. **Repository Layer**: 데이터 접근 추상화
4. **Model Layer**: 데이터 모델 정의

### 주요 설계 원칙

- **의존성 역전 원칙**: 상위 계층이 하위 계층에 의존하지 않도록 추상화 사용
- **단일 책임 원칙**: 각 클래스와 모듈은 하나의 책임만 가짐
- **개방-폐쇄 원칙**: 확장에는 열려있고 수정에는 닫혀있는 구조
- **인터페이스 분리 원칙**: 클라이언트가 사용하지 않는 인터페이스에 의존하지 않음

## 🛠️ 개발 도구

### 코드 품질

```bash
# 코드 포맷팅
make format

# 린팅
make lint

# 테스트
make test

# 커버리지 테스트
make test-cov
```

### 유용한 명령어

```bash
# 도움말 보기
make help

# 개발 환경 설정
make dev-install

# 프로덕션 서버 실행
make run-prod

# 캐시 정리
make clean
```

## 🔧 환경 변수

주요 환경 변수들:

| 변수명         | 설명              | 기본값                 |
| -------------- | ----------------- | ---------------------- |
| `APP_NAME`     | 애플리케이션 이름 | `FastAPI Backend`      |
| `ENVIRONMENT`  | 실행 환경         | `development`          |
| `DATABASE_URL` | 데이터베이스 URL  | `sqlite:///./app.db`   |
| `SECRET_KEY`   | JWT 비밀 키       | `your-secret-key-here` |
| `LOG_LEVEL`    | 로그 레벨         | `INFO`                 |

자세한 설정은 `.env.example` 파일을 참조하세요.

## 📝 개발 가이드

### 새로운 기능 추가

1. **모델 정의**: `app/models/`에 SQLAlchemy 모델 추가
2. **스키마 정의**: `app/schemas/`에 Pydantic 스키마 추가
3. **Repository 생성**: `app/repositories/`에 데이터 접근 로직 추가
4. **Service 생성**: `app/services/`에 비즈니스 로직 추가
5. **Controller 생성**: `app/controllers/`에 API 엔드포인트 추가
6. **라우터 등록**: `app/main.py`에 라우터 추가

### 테스트 작성

```python
# tests/test_example.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

## 🤝 기여하기

1. 프로젝트를 포크합니다
2. 기능 브랜치를 생성합니다 (`git checkout -b feature/AmazingFeature`)
3. 변경사항을 커밋합니다 (`git commit -m 'Add some AmazingFeature'`)
4. 브랜치에 푸시합니다 (`git push origin feature/AmazingFeature`)
5. Pull Request를 생성합니다

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 있습니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.
