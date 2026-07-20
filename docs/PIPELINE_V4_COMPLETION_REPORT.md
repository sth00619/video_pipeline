# Pipeline v4 completion report

## Scope and deployment boundary

This report follows `CODEX_REQUEST_combined.md`.  Source changes include Spring
so the next normal Java release contains the state/selection model, but this
work only rebuilds and deploys **fastapi-workers**.  Spring is not redeployed
while a long-form job is running.

## Phase 1 — narration correctness and length safety

Changed `backend/fastapi-workers/app/workers/script_worker.py`.

- A percent is now rendered as `퍼센트`; it is never converted to `포인트`.
- Decimal-aware sentence splitting is used by unit validation and narration
  capping.  A cap keeps a complete sentence rather than cutting `6.37` or a
  number/unit pair in half.
- Over-long text gets one constrained rewrite before deterministic capping.
- The no-key mock response now has the same core response fields as a live
  request and sets `requires_manual_review=true`.

Evidence: direct assertions passed for `하락률 6.37퍼센트`, mixed
`463포인트 / 6.37퍼센트`, decimal-safe capping and mock schema.  Python
`py_compile` passed.

## Phase 2 — input-keyword-first selection

Changed `KeywordService`, `KeywordSearchResponse`, `JobStatus`,
`KeywordWorker`, and `ScriptWorker`.

Selection is deterministic:

1. `INPUT_KEYWORD`: a non-empty request keyword is confirmed exactly.
2. `EXISTING_JOB_KEYWORD`: otherwise retain an already-confirmed job keyword.
3. `AUTO_DISCOVERY`: otherwise use ranked candidate #1 and record its reason.

`selection_path`, `selected_keyword`, and `selection_reason` are stored in the
keyword asset metadata, so a later UI reload can explain the decision.  Ranking
cannot replace `삼성전자 3분기 반도체 실적` with a generic KOSPI topic.

`keyword_time_context.py` resolves an unqualified quarter deterministically.
On 2026-07-20, `3분기` resolves to 2025 Q3; a current/future unreported
quarter returns `TOPIC_EVIDENCE_REQUIRED` rather than allowing a fabricated or
generic script.

Evidence: direct tests passed for the unqualified-quarter anchor, future
quarter stop, seed alias match, and generic-KOSPI mismatch.  Spring `classes`
build passed.

## Phase 3 — aliases, provider transparency, images

`backend/shared/keyword_aliases.json` is the single source for Python and
Spring.  It contains 30+ canonical mappings (for example `삼전→삼성전자`,
`삼전닉스→삼성전자/SK하이닉스`, `3분기→Q3`).  `seed_overlap_terms` and count are
returned per candidate.  Both candidate filtering and script coverage validation
use these canonical terms.

Candidate extraction now turns a title into a concise topic phrase where
possible and sets `keyword_is_raw_title` when it cannot safely do so.  Missing
metrics remain unavailable/zero rather than fabricated search volume.

The script worker records whether Claude or a Gemini fallback produced content;
a fallback sets `requires_manual_review` for the approval UI.

Image-worker stability was verified in `images_worker.py`: invalid local/code
errors are non-retryable, 429/503/timeout use bounded retries, identical errors
open a circuit breaker, a recovery round handles only failed scenes, successful
manifest images resume, and final images are file/decode validated.  The former
`runtime_config.value(..., default)`, missing `integer()`, and parallel-return
`budget_preflight` failures are absent.  `GeminiBatchImagePollingService` now
only polls pending assets and closes `BATCH_FAILED`/20 repeated polling errors.

## Phase 4 — Shorts pipeline verification

The existing `shorts_worker.py` already implements the requested advanced path:

1. upload → transcript provider (Korean) → timestamped segments;
2. score/extract suggested highlights, then generate three contiguous scenarios
   plus ten keywords through `extract_scenarios()`;
3. operator chooses a scenario; `cut_and_merge()` expands too-short subtitle
   spans, applies 9:16 centre fill/crop, caps output at 60 seconds, and merges
   only validated clips;
4. Spring stores scenario metadata as `SHORTS_SCENARIO`, and metadata/thumbnail
   generation remains linked to the same job.

No replacement worker was added because it would duplicate the production
implementation.  The source interfaces are `FastApiClient` shorts methods,
`LongformService` scenario persistence, and FastAPI endpoints in `app/main.py`.

## Phase 5 — operating guide

### Long-form flow

`JobNew.jsx` creates a job → `KeywordService.search()` calls
`KeywordWorker.search()` → the keyword asset keeps evidence and selection path
→ `ScriptService` calls `ScriptWorker.generate()` → fact checks and keyword
coverage gate → TTS worker (voice/timestamps) → `ImagesWorker.generate()` →
`LongformService`/FFmpeg assembly.  In automatic mode Temporal advances after a
successful gate; in semi-automatic mode each asset is reviewed before the next
gate.  Refreshing the detail page reloads persisted assets rather than losing
earlier output.

### Failure protocol

- no LLM key: valid mock payload + manual review; never pretend it is live AI;
- no evidence for a time-qualified subject: `TOPIC_EVIDENCE_REQUIRED`, no TTS;
- local image configuration bug: terminate without retries;
- transient image provider outage: bounded retry/recovery only;
- any incomplete image set: never call final assembly.

## Verification commands executed

```powershell
$env:PYTHONPATH='backend/fastapi-workers'
python -c "... time/alias assertions ..."
python -m py_compile backend/fastapi-workers/app/utils/keyword_time_context.py `
  backend/fastapi-workers/app/utils/keyword_aliases.py `
  backend/fastapi-workers/app/workers/keyword_worker.py `
  backend/fastapi-workers/app/workers/script_worker.py
cd backend/spring-app; .\gradlew.bat classes
```

Results: all assertions passed; Python compilation passed; Gradle completed
`BUILD SUCCESSFUL`.
