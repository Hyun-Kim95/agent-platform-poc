# Agent Platform PoC

질문 유형에 따라 웹 근거 수집 / 데이터 분석을 조합하는
플러그형 Agent 백엔드 PoC. HITL은 `/v1/hitl/{run_id}`로 재개한다.

## 목적

- 단일 HTTP API (`/v1/chat`)로 세로 슬라이스 검증
- 엔진 Registry로 `echo` / `multi_agent` / `hybrid_rag` / `tool_router` 분기
- `tenant=demo`에서 Human-in-the-loop 승인/수정/거절

## 빠른 시작

Windows PowerShell 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env: LLM_API_KEY(선택), VECTOR_DATABASE_URL(선택)

# (권장) 공유 Postgres: 문서벡터 + sales + RunStore + Feedback
docker compose up -d

uvicorn app.main:app --port 8000
```

브라우저 데모 UI: [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)  
(`tenant=demo` → HITL Approve / Revise / Reject)

`VECTOR_DATABASE_URL`이 비어 있거나 PG가 다운이면 keyword RAG + SQLite T2SQL + SQLite RunStore로 fallback한다.  
호스트 포트는 `55432` (`docker-compose.yml`).

코드 수정 중 자동 재시작이 필요하면 `--reload`를 붙인다.  
`.env`를 바꾼 뒤에는 서버를 한 번 종료했다가 다시 켠다.

포트 8000이 이미 사용 중이면:

```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID> -Force
```

## 데모 시나리오

서버 기동 후 다른 터미널(venv 활성):

| 순 | 무엇을 보여주나 | 명령/요청 |
|----|-----------------|-----------|
| 1 | Registry 분기 | `python scripts\smoke_chat.py` |
| 2 | HITL approve 흐름 | `python scripts\demo_hitl.py` (`tenant=demo`) |
| 3 | HITL 체크포인트 영속 | `python scripts\smoke_checkpoint.py` |
| 4 | 문서+SQL hybrid | `python scripts\smoke_hybrid.py` |
| 5 | 툴 디스패치 | `python scripts\smoke_tool_router.py` (단위) 또는 chat `engine=tool_router` |
| 6 | 로컬 runs/feedback → PG | `python scripts\migrate_local_to_pg.py --dry-run` |
| 7 | 얇은 채팅/HITL UI | 브라우저 `http://127.0.0.1:8000/ui` |

수동 chat 예:

```json
{"tenant_id":"internal","engine":"tool_router","query":"12+5 계산"}
{"tenant_id":"internal","engine":"hybrid_rag","query":"매출 합계는?"}
{"tenant_id":"demo","engine":"multi_agent","query":"웹과 CSV를 섞은 질문"}
```

기대: 각각 `meta.engine`이 요청 엔진과 같고, HITL은 `waiting_human` → `/v1/hitl/{run_id}`만으로 재개.

## 스모크 모음

Registry / 오류 코드:

```powershell
python scripts\smoke_chat.py
```

혼합 질문 (`tenant=internal`, HITL 없음):

```powershell
python scripts\smoke_s1.py
```

HITL 데모 (`tenant=demo`):

```powershell
python scripts\demo_hitl.py
```

HITL 타임아웃 (`demo_timeout`):

```powershell
python scripts\smoke_timeout.py
```

Reviewer loop (`demo_loop`):

```powershell
python scripts\smoke_loop.py
```

근거 부족 시 현재 round citations는 `citation_history`에 남기고 live 목록만 비운 뒤 tools를 재시도한다.  
한도 초과면 `status=failed`, `error.code=MAX_ITERATIONS`.

`reset_compiled_graph()`는 REPL/단위 테스트용 캐시 리셋이며 API 경로에서는 호출하지 않는다.

## Tool Router (P3)

`engine=tool_router`: 규칙(±LLM)으로 mock 툴 `calc` / `clock` / `faq`를 고른 뒤 실행한다.
HITL off. citations `type=tool`. `meta.route` = 단일 툴명 또는 `both` / `none`.

```powershell
python scripts\smoke_tool_router.py
```

## Hybrid RAG (v0.2 / v0.3)

문서 검색(keyword 또는 옵션 **pgvector**) + T2SQL(Guardrail)을 한 Envelope로 합친다.
HITL 기본 off. `VECTOR_DATABASE_URL`이 살아 있으면 **문서 벡터 + sales + RunStore(runs)** 를 같은 Postgres에 둔다.
URL 비움/PG 다운이면 keyword RAG + SQLite `samples/hybrid.db` + SQLite `data/runs.db`.

T2SQL·Router는 rule-first + 선택적 LLM. Guardrail은 sqlparse + **sqlglot AST**.

### Vector RAG (pgvector, 옵션)

```powershell
docker compose up -d
# .env: VECTOR_DATABASE_URL, LLM_API_KEY
python scripts\index_docs.py
python scripts\smoke_vector_rag.py
```

`meta.rag_source` = `vector` | `keyword` | `none`,  
`meta.sql_backend` = `postgres` | `sqlite`,  
`/health.run_store_backend` = `postgres` | `sqlite`.

```powershell
python scripts\smoke_hybrid.py
python scripts\smoke_t2sql_llm.py
python scripts\smoke_router_llm.py
python scripts\smoke_guardrail.py
python scripts\smoke_small_fixes.py
python scripts\smoke_vector_rag.py
python scripts\smoke_sales_pg.py
python scripts\smoke_run_store.py
python scripts\smoke_tool_router.py
```

## Feedback (v0.2)

완료된(또는 저장된) `run_id`에 대해 사용자 평가를 append 한다.  
`VECTOR_DATABASE_URL`이 살아 있으면 Postgres `feedback` 테이블,  
아니면 `data/feedback.jsonl` (gitignore).

```powershell
python scripts\smoke_feedback_store.py
python scripts\smoke_feedback.py
```

`POST /v1/feedback` — `rating` 1~5. 없는 `run_id`는 **404** `RUN_NOT_FOUND`.

## Observability (optional)

- **JSONL:** `data/runs.jsonl`
- **OTel:** 기본 off. `OTEL_ENABLED=true`면 콘솔 span
- **LangSmith:** 키 있을 때만
- **Usage:** `meta.usage` (학습용 토큰·비용 추정)

```powershell
python scripts\smoke_obs.py
python scripts\smoke_usage.py
```

## 전체 스모크

```powershell
docker compose up -d
uvicorn app.main:app --port 8000
# 다른 터미널
.\scripts\smoke_all.ps1
```

단위 스크립트는 서버 없이 먼저, HTTP 구간은 `/health` 필요.  
`demo_hitl.py`는 대화형이라 `smoke_all`에 포함하지 않는다.

## Known limitations

- 프론트는 React 없음. PoC용 정적 UI만 `/ui` (Auth·스트리밍 없음)
- `multi_agent`: LangGraph + 웹(mock/Tavily) + CSV. HITL은 interrupt + `/v1/hitl`
- HITL warm resume: LangGraph checkpointer (Postgres 또는 `data/checkpoints.db`). 재시작 후에도 `thread_id=run_id`로 resume 가능
- RunStore `agent_state` cold path는 체크포인트가 없을 때의 fallback
- RunStore: Postgres면 `graph_state`는 JSONB(구 TEXT 컬럼은 기동 시 자동 변환). SQLite는 TEXT JSON
- 로컬→PG 일회 이전: `python scripts/migrate_local_to_pg.py` (`--dry-run` 권장). sales/docs/checkpoints는 재시드·재인덱스(체크포인트는 C 범위)
- 관측: JSONL + OTel 콘솔 + LangSmith on/off. Collector/평가 파이프라인 없음
- Usage/cost·Feedback은 학습/수집용. 파인튜닝 파이프라인 아님
- `hybrid_rag` / `tool_router`는 위에 기술한 PoC 범위(외부 상용 툴·완벽 RAG 아님)
- Python 3.9.0이면 pydantic 2.10.x 핀 필요. 가능하면 3.11+ 권장
