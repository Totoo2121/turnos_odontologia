# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| Build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests | tdd | C:\Users\Renzo\.agents\skills\tdd\SKILL.md |
| Anything with PDF files (.pdf mentioned, produce one, read/extract/merge/split/rotate/watermark/forms/encrypt/OCR) | pdf | C:\Users\Renzo\.agents\skills\pdf\SKILL.md |
| BEFORE writing/changing anything in Postgres (tables, columns, types, schema, migrations, RLS, indexes, triggers, functions, queues, pgvector, restores) or diagnosing slow queries/CPU/timeouts/locks/wrong-tenant rows | supabase-postgres-best-practices | C:\Users\Renzo\.agents\skills\supabase-postgres-best-practices\SKILL.md |
| Python FastAPI backend development with async patterns, SQLAlchemy, Pydantic, authentication, production API patterns | python-fastapi-development | C:\Users\Renzo\.agents\skills\python-fastapi-development\SKILL.md |
| Writing, reviewing, or refactoring React/Next.js code; components, pages, data fetching, bundle optimization, performance | vercel-react-best-practices | C:\Users\Renzo\.agents\skills\vercel-react-best-practices\SKILL.md |
| /active-orchestrator:init, :kb, :rules, :discovery, :openspec, :devops, :find-skill — or starting a new project from scratch with the SDD/OpenSpec foundation flow | active-orchestrator | C:\Users\Renzo\.config\opencode\skills\active-orchestrator\SKILL.md |
| Create/build/generate a project knowledge base, document a project from source documents (.txt, .docx, .pdf), "armar base de conocimiento" / "crear KB" / "documentar proyecto" | kb-creator | C:\Users\Renzo\.config\opencode\skills\kb-creator\SKILL.md |
| Create/build/regenerate/update CHANGES.md, roadmap, change map, implementation plan; "armar CHANGES" / "armar roadmap" / "qué changes necesito" / "índice de changes" | roadmap-generator | C:\Users\Renzo\.config\opencode\skills\roadmap-generator\SKILL.md |
| "how do I do X", "find a skill for X", "is there a skill that can...", extending capabilities | find-skills | C:\Users\Renzo\.config\opencode\skills\find-skill\SKILL.md |
| Investigar mercado/pensar qué construir antes de tener claridad; fase discovery del flujo fundación (problema, usuarios, casos de uso, competidores, funcionalidades, reglas de negocio, integraciones, restricciones, riesgos) | discovery-research | C:\Users\Renzo\.config\opencode\skills\discovery-research\SKILL.md |
| Investigar/scrapear un competidor a partir de una URL concreta | web-scraper | C:\Users\Renzo\.config\opencode\skills\web-scraper\SKILL.md |
| Crear/generar/actualizar AGENTS.md o CLAUDE.md, "armar las reglas del proyecto", "instrucciones para los agentes", "generar claude.md", o tras kb-creator + roadmap-generator | agents-md-generator | C:\Users\Renzo\.config\opencode\skills\agent-instruction\SKILL.md |
| Create a skill from scratch, edit/optimize an existing skill, run evals, benchmark skill performance, optimize a skill description | skill-creator | C:\Users\Renzo\.config\opencode\skills\skill-creator\SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### tdd
- Red before green: write the failing test FIRST, then only enough code to pass it; never anticipate future tests.
- Test at pre-agreed seams only (public boundaries/interfaces); confirm seams with the user before writing tests. Never test privates/internals.
- One slice at a time: one seam, one test, one minimal implementation per cycle; work in vertical slices (test → implement → repeat), never bulk-write all tests first.
- Tests verify observable behavior through the public interface ("user can checkout with valid cart"); must survive refactors.
- NEVER tautological assertions: expected values must be independent known literals/worked examples from the spec, not recomputed the way the code computes (`expect(add(a,b)).toBe(a+b)` is forbidden).
- NEVER mock your own classes/modules/internal collaborators; mock ONLY at system boundaries (external APIs, DB — prefer real test DB, time/randomness, FS).
- At system boundaries use dependency injection + SDK-style interfaces (one function per operation) so mocks stay trivial.
- Refactoring is NOT part of the red→green loop; it belongs to review stage.

### pdf
- Text/table extraction → pdfplumber (`page.extract_text()`, `page.extract_tables()`); basic ops (merge/split/rotate/encrypt/watermark) → pypdf; creation → reportlab; CLI merge → qpdf; layout-preserving text → `pdftotext -layout`.
- NEVER use Unicode subscript/superscript chars (₀₁₂.., ⁰¹²..) in ReportLab — built-in fonts render them as black boxes; use `<sub>`/`<super>` XML tags in Paragraph, or manual size/position offset on canvas.
- Forms → read FORMS.md first (pdf-lib or pypdf per that guide); advanced pypdfium2/JS libs/troubleshooting → REFERENCE.md.
- Scanned PDFs → pdf2image + pytesseract OCR per page; check `table` non-empty before building DataFrames.
- This project emits signed consents, budgets and reports as PDF — encrypt when they carry patient data.

### supabase-postgres-best-practices
- Load BEFORE any Postgres change (even one column / one query) and for slow queries, CPU, timeouts, EXPLAIN plans, locks, or wrong-tenant rows. Rule files live in `references/`; each has incorrect-vs-correct SQL.
- RLS (CRITICAL, multi-tenant/HCE isolation at DB level): `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` on every tenant table; never rely on app-level `WHERE` filtering alone — relevant to HCE odontológica per-clínica/paciente.
- RLS performance: wrap volatile calls in SELECT — `using ((select auth.uid()) = user_id)`, never bare `auth.uid()` per row (100x+ on large tables); complex checks via `SECURITY DEFINER` helper in a private schema with explicit `auth.uid()` check inside, `search_path=''`, and `REVOKE EXECUTE` from public roles.
- Connection pooling is mandatory (PgBouncer; pool_size ≈ (cores×2)+spindles); transaction mode default, session mode only for prepared statements/temp tables.
- Schema: lowercase identifiers, explicit PKs on every table, indexes on all FK columns, CHECK constraints in DB, correct types (timestamptz, numeric for money, jsonb + GIN where needed); N+1 → joins/batch, pagination via keyset, batch inserts, upserts with ON CONFLICT.
- Short transactions, `SKIP LOCKED` for queue-style picks (e.g. lista de espera), advisory locks for cross-row booking guards (anti-solapamiento profesional/sillón); EXPLAIN ANALYZE + pg_stat_statements + VACUUM/ANALYZE for diagnostics.

### python-fastapi-development
- Stack: Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL, Alembic, JWT/OAuth2, pytest. Follow phases in order: setup (uv/poetry, structure, logging, env) → DB/schema → routers → auth → errors → tests → docs → deploy.
- Async end-to-end (async endpoints + async SQLAlchemy session); Pydantic v2 request/response models with validation on every endpoint; Alembic migration per schema change; never raw ad-hoc DDL.
- Auth: JWT access+refresh (or OAuth2), password hashing, auth middleware; custom exceptions + global handlers with consistent error responses and request logging.
- Quality gates mandatory: tests >80% coverage passing, mypy clean, ruff/black clean, OpenAPI docs complete, security scan passed.
- Scope guard: use only when the task matches FastAPI backend scope; stop and ask if inputs, permissions, or success criteria are missing.

### vercel-react-best-practices
- Eliminate waterfalls (CRITICAL): `Promise.all()` for independent fetches, start promises early/await late, check cheap sync conditions before awaiting, Suspense boundaries for streaming; per-rule detail in `rules/`, full text in `AGENTS.md`.
- Bundle (CRITICAL): direct imports, never barrel files; `next/dynamic` for heavy components (e.g. odontograma FDI interactivo); defer analytics/logging past hydration; conditional-load feature modules; statically analyzable paths only.
- Server: `React.cache()` per-request dedup, LRU cross-request cache, parallelize fetches via component composition, minimize RSC-boundary serialization, never module-level mutable request state, `after()` for non-blocking work, authenticate server actions like API routes.
- Client: SWR for dedup, dedup global listeners, passive scroll listeners, versioned minimal localStorage.
- Re-render/render: derive state during render (not effects), primitive effect deps, no inline component definitions, `startTransition`/`useDeferredValue` for non-urgent UI, ternary (not `&&`) for conditionals, `content-visibility` for long lists (agenda diaria), hoist static JSX, resource hints + defer/async scripts.

### active-orchestrator
- Thin orchestrator only: NEVER reimplement a phase's logic, NEVER ask strategic content questions (system_type, stack, problem, 11-point checklist belong to kb-creator/discovery-research); only ask phase-selection (whether to run Discovery).
- Owns `step`/`version`/`owner` in `.active-orchestrator-state.json` ONLY; sub-skills own their sections — never touch `kb`, `roadmap`, `skills`, `agents`, `registry`, `discovery`.
- Order: [discovery-research] → kb-creator → roadmap-generator → find-skill → skill-registry → agent-instruction; checkpoint (advance gate) at EVERY phase boundary, never chain without explicit "Continuar".
- Interactive phases run inline (kb-creator, agent-instruction, discovery-research); mechanical phases delegate to sub-agents (roadmap, find-skill recommend-only, registry).
- NEVER install skills autonomously — find-skill recommends, user picks via multiSelect, then install picked only.

### kb-creator
- Output ALWAYS to `knowledge-base/` at project root with the 10 canonical files + `README.md` index; NEVER mix with `docs/` (sources live there); extras allowed only as `1X_*`/`2X_*` kebab-case, never replacing the 10.
- Mode A (docs/ has sources): silent fire-and-forget, no questions — ambiguities go to `10_preguntas_abiertas.md`, never invent values; Mode B (from scratch): strategic partner, 3–5 questions with options + "por qué importa", iterate file-by-file with validation.
- If top-level `state.discovery` exists, read it to pre-fill (never re-ask what Discovery answered); low-confidence fields → `10_preguntas_abiertas.md`.
- Writes ONLY `state.kb` (incl. `kb.discovery` 6 fields + `source` ingest|interactive + `files`); never touch step/owner/roadmap/skills/agents.
- Don't use when KB already complete (update single files instead) or when user wants ONE doc.

### roadmap-generator
- Pre-checks mandatory: `knowledge-base/` with 10 canonicals + `openspec/` must exist, else generate NOTHING and say which to run first.
- Output is ONE file: `CHANGES.md` at project root (never inside openspec/); fixed top-level structure (Cómo usar → Árbol → Paralelismo/GATES → Camino crítico → Plan 3 agentes → FASEs) — never add/remove L1 sections.
- Ordering rules: C-01 always foundation-setup; core models before features; auth before protected resources; referenced entity before referrer; backend before coupled frontend; external integrations/payments/webhooks + admin/dashboards + visual restyle last.
- Per change write: Estado `[ ]`, operational Scope bullets (models, endpoints, migration N°, WS events, expected tests — never vague prose), Dependencias, Governance (BAJO/MEDIO/ALTO/CRITICO — auth/pagos/HCE/audit = CRITICO), Leer antes (3–5 KB files with §).
- GATES mark every fork with [Agente A/B/C] assignments; critical path = shortest linear chain to production (no refactors/optionals).
- Writes ONLY `state.roadmap` (`created_by`, `source: "CHANGES.md"`, ordered `changes` IDs); never touch other sections.

### find-skills
- Recommend-only in orchestrated runs: derive {stack, domains, problem} from `state.kb.discovery`; NEVER run `npx skills add` autonomously — user picks, orchestrator installs.
- Search flow: skills.sh leaderboard first, then `npx skills find <query>`; verify quality before recommending (prefer 1K+ installs; official sources vercel-labs/anthropics/microsoft trusted; <100 stars GitHub = skepticism; report Snyk-type warnings).
- Present: name + what it does + installs + source + install command + skills.sh link; categories cheat-sheet: web-dev, testing, DevOps, docs, code-quality, design, productivity.
- If nothing found: say so, help directly with general capabilities, optionally suggest `npx skills init`.

### discovery-research
- Converts "tengo una idea" into build-ready context BEFORE any KB: never fill a checklist point with an assumption when you can ask or research it.
- Flow: 1) Fuentes (ask once for URLs/docs; invoke web-scraper once per URL, or `collect_sources.py` table if notes exist; Q&A-only if no sources — never block) → 2) Checklist Q&A (11 points via `references/checklist.md`, 3–5 questions/round with a/b/c + "por qué importa"; never re-ask what scraping resolved — confirm instead) → 3) Gate final (readable summary + explicit user confirmation BEFORE writing anything) → 4) Write `discovery/discovery.md` (prose per `assets/example-discovery.md`) + `state.discovery` ONLY.
- Assumption-mapping for riesgos/preguntas abiertas: every unverified taken-for-granted = risk or open question.
- MEDIUM governance: checkpoints on non-obvious decisions; depends on web-scraper as sub-skill — if missing, continue Q&A-only and report it.

### web-scraper
- Fixed 8-field output schema ALWAYS, same order, even if a field ends `(no publicado)` — comparability is the point; template: `assets/example-source-note.md`, fields: `references/output-schema.md`.
- NEVER invent a datum the page doesn't show (hidden pricing = `(no publicado)`, not estimated); on empty content/SPA shell/403/paywall/CAPTCHA report the limitation as-is, no evasion tricks.
- One page per call, one-by-one for batches (never abort whole batch on one failure); NO full-site crawling/mass scraping (rate limits/robots.txt out of v1 scope); heavy-JS/anti-bot sites are known v1 non-coverage.
- Filename via `scripts/slugify.py` kebab-case so re-runs overwrite, never duplicate; write to `discovery/sources/<slug>.md` (create dir if needed).
- Read-only skill: no user-system writes, no approval gate needed per single URL.

### agents-md-generator
- Output: `AGENTS.md` + `CLAUDE.md` (identical copy) at project root, never inside `.claude/`/`openspec/`; fixed L1 structure (Stack → KB → Skills → Roadmap → Reglas Duras → Flujo) — never drop sections.
- Skills source of truth = `.atl/skill-registry.md` (read it, don't re-scan; fallback: `.claude/skills/` + `~/.claude/skills/`); map skill→agent-role table, NEVER copy compact rules into AGENTS.md (they live only in the registry) + the verbatim registry-reference line.
- Reglas duras = ONLY interactive part: read global `~/.claude/CLAUDE.md` first and NEVER repeat what it already defines (reference it in one line); derive stack-aware candidates from KB 02 (adapt to real stack, never hardcode a language); CONFIRM via AskUserQuestion and write ONLY confirmed rules as `NUNCA X → hacer Y`.
- Pre-checks: KB + `02_descripcion_general.md` required (else don't generate); missing CHANGES.md = generate anyway minus Roadmap section + warning.
- Don't use for single-rule edits (edit AGENTS.md directly) or harness hooks (that's settings.json).

### skill-creator
- Loop: capture intent (what/trigger/output/evals?) → interview edge cases → draft SKILL.md → 2–3 realistic test prompts → parallel with-skill AND baseline runs → user review via eval-viewer (`generate_review.py`, ALWAYS before self-evaluating) → generalize improvements (no overfit MUSTs, explain why) → repeat; package `.skill` at the end.
- SKILL.md anatomy: frontmatter (pushy description = primary trigger, name preserved on updates) + body <500 lines; bundle scripts/references/assets with progressive disclosure (metadata → body → resources as-needed); read-only installed paths → copy to /tmp before editing.
- Assertions must be objectively verifiable with descriptive names; `grading.json` uses exact fields `text`/`passed`/`evidence`; capture `timing.json` (tokens/duration) from each run notification immediately.
- Description optimization: 20 mixed trigger/non-trigger realistic eval queries (near-miss negatives), user-reviewed, then `run_loop.py` (60/40 train/test, 3 runs each, ≤5 iters, pick by TEST score); benchmark via `aggregate_benchmark`.
- Safety: no malware/exfiltration/misleading skills; adapt questions to user's jargon level.

## Project Conventions

_No project convention files found (no CLAUDE.md / AGENTS.md / agents.md / .cursorrules / GEMINI.md / copilot-instructions.md at project root). Expected in this first foundation pass — agent-instruction generates CLAUDE.md/AGENTS.md in the next phase. Re-run skill-registry afterwards to index them._
