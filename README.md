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

## Hybrid RAG (v0.2 / v0.3)

문서 검색(keyword 또는 옵션 **pgvector**) + T2SQL(Guardrail)을 한 Envelope로 합친다.
HITL 기본 off. `VECTOR_DATABASE_URL`이 살아 있으면 **문서 벡터 + sales + RunStore(runs)** 를 같은 Postgres에 둔다.
URL 비움/PG 다운이면 keyword RAG + SQLite `samples/hybrid.db`(CSV 시드) + SQLite `data/runs.db`.

T2SQL은 기본 템플릿이다. `LLM_API_KEY`가 있고 `RULES_ONLY=false`이면 LLM 초안 → 동일 Guardrail.
키 없음/실패 시 template fallback. 위험 의도(DROP 등)는 템플릿이 그대로 Guardrail로 보낸다.

Router도 rule-first다. 모호한 질문(키워드 없음 또는 rag+sql 동시)이고
`LLM_API_KEY` + `RULES_ONLY=false`이면 LLM이 `rag|sql|both`를 고른다.

Guardrail은 sqlparse(주석) + **sqlglot AST**(서브쿼리·UNION·함수·테이블 allowlist·LIMIT)로 검사한다.
개선: T2SQL 단어경계 오탐 완화, 제목-only 청크 스킵, citation 헬퍼 공유.

### Vector RAG (pgvector, 옵션)

```powershell
docker compose up -d
# .env: VECTOR_DATABASE_URL, LLM_API_KEY
pip install -r requirements.txt
python scripts\index_docs.py
python scripts\smoke_vector_rag.py
```

`VECTOR_DATABASE_URL`/키/PG가 없으면 keyword·SQLite로 fallback.  
응답 `meta.rag_source` = `vector` | `keyword` | `none`,  
`meta.sql_backend` = `postgres` | `sqlite`.

```powershell
python scripts\smoke_hybrid.py
python scripts\smoke_t2sql_llm.py
python scripts\smoke_router_llm.py
python scripts\smoke_guardrail.py
python scripts\smoke_small_fixes.py
python scripts\smoke_vector_rag.py
python scripts\smoke_sales_pg.py
python scripts\smoke_run_store.py
```

- 문서 질문 → `citations.type=doc` (또는 `no_hit`)
- 매출/합계 → `sql` citation (`sales query (postgres|sqlite/…)`)
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

## 전체 스모크 (PoC 마무리)

서버 기동 후 (venv 활성):

```powershell
.\scripts\smoke_all.ps1
```

단위 스크립트(`smoke_guardrail`, `smoke_small_fixes`)는 서버 없이 먼저 돌린다.  
`demo_hitl.py`는 대화형이라 스크립트에 포함하지 않는다.

## Known limitations

- 프론트·Auth 없음
- `multi_agent`: LangGraph + 웹(mock/Tavily) + CSV. HITL은 interrupt + `/v1/hitl` 재개
- HITL warm resume는 프로세스 내 MemorySaver; 서버 재시작 후는 RunStore(`Postgres` 또는 SQLite) `agent_state` cold path
- 관측: JSONL + OTel 콘솔 + LangSmith on/off. Collector/평가 파이프라인 없음
- Usage/cost는 학습용 추정·단가표. 청구 SSOT 아님
- Feedback는 수집·영속만 (파인튜닝/평가 파이프라인 본문 없음)
- Reviewer 강제 실패는 tenant/env `force_reviewer_insufficient` (쿼리 매직 문자열 없음)
- `hybrid_rag`: keyword/pgvector + T2SQL(sales Postgres|SQLite). Guardrail은 sqlparse+**sqlglot AST**. RunStore도 공유 PG URL(없으면 SQLite)
- 개선: T2SQL 단어경계 오탐 완화, 제목-only 청크 스킵, `app/core/citations` 공유
- Python 3.9.0이면 pydantic 2.10.x 핀 필요 (`requirements.txt`). 가능하면 3.11+ 권장
