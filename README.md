# Agent Platform PoC

질문 유형에 따라 웹 근거 수집 / 데이터 분석을 조합하는
플러그형 Agent 백엔드 PoC. HITL은 `/v1/hitl/{run_id}`로 재개한다.

## 목적

- 단일 HTTP API (`/v1/chat`)로 세로 슬라이스 검증
- 엔진 Registry로 `multi_agent` / `hybrid_rag` / `echo` stub 분기
- `tenant=demo`에서 Human-in-the-loop 승인/수정/거절

## 빠른 시작

Windows PowerShell 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env에 키 입력 후 (선택) WEB_SEARCH_API_KEY 등
uvicorn app.main:app --port 8000
```

코드 수정 중 자동 재시작이 필요하면 `--reload`를 붙인다.  
`.env`를 바꾼 뒤에는 reload와 관계없이 서버를 한 번 종료했다가 다시 켠다.

포트 8000이 이미 사용 중이면:

```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID> -Force
```

Registry 분기 스모크 (다른 터미널, venv 활성화 후):

```powershell
python scripts\smoke_chat.py
```

혼합 질문 스모크 (`tenant=internal`, HITL 없음):

```powershell
python scripts\smoke_s1.py
```

HITL 데모 (`tenant=demo`, 서버 기동 후):

```powershell
python scripts\demo_hitl.py
```

`POST /v1/chat` → `waiting_human` → `POST /v1/hitl/{run_id}` 로만 재개한다.

HITL 타임아웃 스모크 (`tenant=demo_timeout`, `timeout_ms=1`):

```powershell
python scripts\smoke_timeout.py
```

Reviewer loop 스모크 (`tenant=demo_loop`, `max_iterations=1`,
`force_reviewer_insufficient: true`):

```powershell
python scripts\smoke_loop.py
```

근거 부족 시 현재 round citations는 `citation_history`에 남기고 live 목록만 비운 뒤 tools를 재시도한다.  
한도 초과면 `status=failed`, `error.code=MAX_ITERATIONS`.

`reset_compiled_graph()`는 REPL/단위 테스트용 캐시 리셋이며 API 경로에서는 호출하지 않는다.

`engine=echo`와 `engine=multi_agent` 응답의 `meta.engine`이 서로 다르면 Registry 분기가 동작하는 것이다.

## Hybrid RAG (v0.2)

문서 keyword 검색 + SQLite T2SQL(Guardrail)을 한 Envelope로 합친다.
HITL 기본 off. DB는 최초 실행 시 `samples/mini.csv`로 `samples/hybrid.db`를 만든다(`*.db` gitignore).

T2SQL은 기본 템플릿이다. `LLM_API_KEY`가 있고 `RULES_ONLY=false`이면 LLM 초안 → 동일 Guardrail.
키 없음/실패 시 template fallback. 위험 의도(DROP 등)는 템플릿이 그대로 Guardrail로 보낸다.

Router도 rule-first다. 모호한 질문(키워드 없음 또는 rag+sql 동시)이고
`LLM_API_KEY` + `RULES_ONLY=false`이면 LLM이 `rag|sql|both`를 고른다.

```powershell
python scripts\smoke_hybrid.py
python scripts\smoke_t2sql_llm.py
python scripts\smoke_router_llm.py
```

- 문서 질문 → `citations.type=doc` (또는 `no_hit`)
- 매출/합계 → `sql` citation
- `DROP` 등 위험 의도 → `status=failed`, `error.code=SQL_GUARDRAIL`
- `meta.engine=hybrid_rag` (`multi_agent`와 구분)

## Feedback (v0.2)

완료된(또는 저장된) `run_id`에 대해 사용자 평가를 append 한다.  
저장 경로: `data/feedback.jsonl` (gitignore).

```powershell
python scripts\smoke_feedback.py
```

`POST /v1/feedback` — `rating` 1~5. 없는 `run_id`는 **404** `RUN_NOT_FOUND`.

## Observability (optional)

- **JSONL:** 기본 `data/runs.jsonl` — chat/hitl마다 `trace_id`, `engine`, `latency_ms`, `status` 한 줄
- **OTel:** 기본 `OTEL_ENABLED=false`. `true`면 요청 span이 **콘솔**에 출력 (`OTEL_EXPORTER=none`이면 끔). `OTEL_SPAN_PROCESSOR=simple|batch` (학습 기본 simple)
- **LangSmith:** `LANGSMITH_API_KEY`가 있을 때만 LangGraph 트레이스 전송. 비어 있으면 no-op
- **Usage (Should):** chat/hitl `meta.usage` + JSONL `usage`
  (`prompt_tokens` / `completion_tokens` / `total_tokens` / `cost_usd` / `estimated`).
  LLM 미호출 시 char/4 추정 (`USAGE_ESTIMATE_ENABLED`).

```powershell
python scripts\smoke_obs.py
python scripts\smoke_usage.py
```

## Known limitations

- v0.1: 프론트 없음, Auth 없음, 풀 RAG 없음
- `multi_agent`는 LangGraph 파이프라인(웹 mock 또는 Tavily + CSV). HITL은 interrupt + `/v1/hitl`로 재개
- HITL warm resume은 프로세스 내 MemorySaver; 서버 재시작 후에는 SQLite agent_state cold path
- 관측은 JSONL + OTel 콘솔 + LangSmith on/off 최소셋. Collector/평가 파이프라인 없음
- Usage/cost는 학습용 추정·단가표. 청구 SSOT 아님. 엔진 LLM 실측은 `app/llm/client` 준비만
- Feedback는 수집·영속만 (파인튜닝/평가 파이프라인 본문 없음)
- Reviewer 강제 실패는 tenant/env 플래그(`force_reviewer_insufficient`). 쿼리 매직 문자열 없음
- `hybrid_rag`: rule-first router + keyword 청크 + SQLite Guardrail. T2SQL은 템플릿 + 선택적 LLM(키 있을 때). 벡터DB 없음
- 계획/API 상세 문서는 로컬 `docs/` only (gitignore)
- 로컬 Python 3.9.0에서는 pydantic을 2.10.x로 고정해야 FastAPI `/docs`가 동작한다 (requirements.txt 참고). 가능하면 3.11+ 권장.
