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

# (권장) 공유 Postgres + Jaeger
docker compose up -d

uvicorn app.main:app --port 8000
```

`VECTOR_DATABASE_URL`이 비어 있거나 PG가 다운이면 keyword RAG + SQLite T2SQL + SQLite RunStore로 fallback한다.  
호스트 포트는 `55432` (`docker-compose.yml`). Jaeger UI는 `16686`.

코드 수정 중 자동 재시작이 필요하면 `--reload`를 붙인다.  
`.env`를 바꾼 뒤에는 서버를 한 번 종료했다가 다시 켠다.

포트 8000이 이미 사용 중이면:

```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID> -Force
```

## 5분 데모 (Stretch 한 흐름)

서버·`docker compose` 기동 후, 아래 순서로 **UI → 웹/fetch → RAG → 관측/eval**을 한 번에 보여준다.

| 분 | 무엇을 | 어떻게 | 기대 |
|----|--------|--------|------|
| 1 | 채팅/HITL UI | 브라우저 [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui) · `tenant=demo` · `engine=multi_agent` | `waiting_human` → Approve/Revise/Reject |
| 2 | 웹검색 출처 | `python scripts\smoke_web_search.py` 또는 chat 후 `meta.web_search_source` | `tavily` 또는 `mock` |
| 3 | 실툴 fetch | chat `engine=tool_router`, query에 `https://example.com` | citation `type=tool`, SSRF 가드(사설 IP 거부) |
| 4 | RAG S3 | `python scripts\index_docs.py --force` → `python scripts\smoke_rag_s3.py` | collection · chunk · `meta.rag_rerank` |
| 5 | Jaeger + eval | `.env`: `OTEL_ENABLED=true`, `OTEL_EXPORTER=otlp` 후 서버 재기동 → chat 1회 → [Jaeger](http://127.0.0.1:16686) · `python scripts\run_eval.py` → `/ui`에서 Load eval report · completed 후 rating | span · `GET /v1/eval/report` · `POST /v1/feedback` |

수동 chat JSON 예:

```json
{"tenant_id":"demo","engine":"multi_agent","query":"웹과 CSV를 섞은 질문"}
{"tenant_id":"internal","engine":"tool_router","query":"12+5 계산"}
{"tenant_id":"internal","engine":"tool_router","query":"https://example.com 가져와"}
{"tenant_id":"internal","engine":"hybrid_rag","query":"환불 정책과 매출 합계"}
```

기대: 각각 `meta.engine`이 요청 엔진과 같고, HITL은 `waiting_human` → `/v1/hitl/{run_id}`만으로 재개.

## 데모·스모크 목록

| 순 | 무엇을 보여주나 | 명령 |
|----|-----------------|------|
| 1 | Registry 분기 | `python scripts\smoke_chat.py` |
| 2 | HITL approve | `python scripts\demo_hitl.py` (`tenant=demo`) |
| 3 | HITL 체크포인트 영속 | `python scripts\smoke_checkpoint.py` |
| 4 | 문서+SQL hybrid | `python scripts\smoke_hybrid.py` |
| 5 | 툴 디스패치(+fetch) | `python scripts\smoke_tool_router.py` |
| 6 | 웹검색 mock/Tavily | `python scripts\smoke_web_search.py` |
| 7 | RAG S3 | `python scripts\smoke_rag_s3.py` |
| 8 | Feedback | `python scripts\smoke_feedback.py` |
| 9 | OTel(console) | `python scripts\smoke_obs.py` |
| 10 | Eval 리포트 | `python scripts\run_eval.py` |
| 11 | 로컬→PG 마이그레이션 | `python scripts\migrate_local_to_pg.py --dry-run` |
| 12 | 얇은 UI · rating · eval · SSE | [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui) · stream 체크 · rating · Load eval report |
| 13 | chat SSE 스모크 | `python scripts\smoke_chat_stream.py` |

혼합 질문·타임아웃·루프:

```powershell
python scripts\smoke_s1.py
python scripts\smoke_timeout.py
python scripts\smoke_loop.py
```

근거 부족 시 현재 round citations는 `citation_history`에 남기고 live 목록만 비운 뒤 tools를 재시도한다.  
한도 초과면 `status=failed`, `error.code=MAX_ITERATIONS`.

`reset_compiled_graph()`는 REPL/단위 테스트용 캐시 리셋이며 API 경로에서는 호출하지 않는다.

## Tool Router

`engine=tool_router`: 규칙(±LLM)으로 `calc` / `clock` / `faq`(로컬) + **`fetch`(실 HTTP GET, SSRF 가드)** 를 고른 뒤 실행한다.  
HITL off. citations `type=tool`. `meta.route` = 단일 툴명 또는 `both` / `none`.

`multi_agent` 웹검색: `WEB_SEARCH_API_KEY`가 있으면 Tavily, 없으면 mock.  
응답 `meta.web_search_source`가 `tavily` | `mock`으로 구분된다.

```powershell
python scripts\smoke_tool_router.py
python scripts\smoke_web_search.py
```

## Hybrid RAG

문서 검색(keyword 또는 옵션 **pgvector**) + T2SQL(Guardrail)을 한 Envelope로 합친다.  
HITL 기본 off. `VECTOR_DATABASE_URL`이 살아 있으면 **문서 벡터 + sales + RunStore(runs)** 를 같은 Postgres에 둔다.  
URL 비움/PG 다운이면 keyword RAG + SQLite `samples/hybrid.db` + SQLite `data/runs.db`.

T2SQL·Router는 rule-first + 선택적 LLM. Guardrail은 sqlparse + **sqlglot AST**.

### Vector RAG (pgvector, 옵션)

문서 레이아웃: `samples/docs/{collection}/*.md`  
(`general/shipping.md`, `policy/refund_policy.md`). 루트 `*.md`는 collection=`default`.

Stretch S3: `collection` 컬럼, `RAG_CHUNK_SIZE`/`OVERLAP`, 후보 `RAG_CANDIDATE_K` 후  
토큰 overlap rerank (`meta.rag_rerank`). 필터는 `RAG_COLLECTION`.

```powershell
docker compose up -d
# .env: VECTOR_DATABASE_URL, LLM_API_KEY
python scripts\index_docs.py --force
python scripts\index_docs.py --force --chunk-size 200 --overlap 40
python scripts\smoke_rag_s3.py
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
```

## Feedback

완료된(또는 저장된) `run_id`에 대해 사용자 평가를 append 한다.  
`VECTOR_DATABASE_URL`이 살아 있으면 Postgres `feedback` 테이블,  
아니면 `data/feedback.jsonl` (gitignore).

```powershell
python scripts\smoke_feedback_store.py
python scripts\smoke_feedback.py
```

`POST /v1/feedback` — `rating` 1~5. 없는 `run_id`는 **404** `RUN_NOT_FOUND`.

## Observability

- **JSONL:** `data/runs.jsonl`
- **OTel:** 기본 off. `OTEL_ENABLED=true` + `OTEL_EXPORTER=console` → 콘솔 span
- **OTLP → Jaeger:** `docker compose up -d`에 Jaeger 포함.  
  `.env`: `OTEL_EXPORTER=otlp`, `OTEL_EXPORTER_ENDPOINT=http://127.0.0.1:4318/v1/traces`  
  UI: [http://127.0.0.1:16686](http://127.0.0.1:16686) (service `agent-platform-poc`)
- **LangSmith:** 키 있을 때만
- **Usage:** `meta.usage` (학습용 토큰·비용 추정)

```powershell
python scripts\smoke_obs.py
python scripts\smoke_usage.py
```

## Eval

서버 기동 후 휴리스틱 채점 (`samples/eval/questions.jsonl`):

```powershell
python scripts\run_eval.py
# 리포트: data/eval_report.md (gitignore)
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
`run_eval.py`도 `smoke_all` 밖(리포트 생성용).

## Known limitations

- 프론트는 React 없음. PoC용 정적 UI만 `/ui` (Auth 없음). chat SSE=`POST /v1/chat/stream`(노드 phase), rating=`POST /v1/feedback`, eval=`GET /v1/eval/report`. HITL resume·토큰 스트림은 비SSE
- `multi_agent`: LangGraph + 웹(mock/Tavily) + CSV. HITL은 interrupt + `/v1/hitl`
- HITL warm resume: LangGraph checkpointer (Postgres 또는 `data/checkpoints.db`). 재시작 후에도 `thread_id=run_id`로 resume 가능
- RunStore `agent_state` cold path는 체크포인트가 없을 때의 fallback
- RunStore: Postgres면 `graph_state`는 JSONB(구 TEXT 컬럼은 기동 시 자동 변환). SQLite는 TEXT JSON
- 로컬→PG 일회 이전: `python scripts/migrate_local_to_pg.py` (`--dry-run` 권장). sales/docs/checkpoints는 재시드·재인덱스
- 관측: JSONL + OTel(console|otlp→Jaeger) + LangSmith on/off. 휴리스틱 eval은 `run_eval.py`
- Usage/cost·Feedback은 학습/수집용. 파인튜닝 파이프라인 아님
- `hybrid_rag` / `tool_router`는 위에 기술한 PoC 범위(외부 상용 툴·완벽 RAG 아님)
- Python 3.9.0이면 pydantic 2.10.x 핀 필요. 가능하면 3.11+ 권장
