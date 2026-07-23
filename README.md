# Agent Platform PoC

질문 유형에 따라 웹 근거 수집 / 데이터 분석을 조합하는
플러그형 Agent 백엔드 PoC. (사람 승인 HITL은 추후 추가 예정)

## 목적

- 단일 HTTP API (`/v1/chat`)로 세로 슬라이스 검증
- 엔진 Registry로 `multi_agent`와 `echo` stub 분기

## 빠른 시작

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Registry 분기 스모크 (다른 터미널, 서버 기동 후):

```bash
python scripts/smoke_chat.py
```

혼합 질문 스모크 (`tenant=internal`, HITL 없음):

```bash
python scripts/smoke_s1.py
```

`engine=echo`와 `engine=multi_agent` 응답의 `meta.engine`이 서로 다르면 Registry 분기가 동작하는 것이다.

## Known limitations

- v0.1: 프론트 없음, Auth 없음, 풀 RAG 없음
- `multi_agent`는 순차 파이프라인(웹 mock 또는 Tavily + CSV). HITL 승인 API는 아직 미구현
- 계획/API 상세 문서는 로컬 `docs/` only (gitignore)
- 로컬 Python 3.9.0에서는 pydantic을 2.10.x로 고정해야 FastAPI `/docs`가 동작한다 (requirements.txt 참고). 가능하면 3.11+ 권장.
