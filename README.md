# Interview → DOCX

**A guided interview assistant that collects structured data in conversation and
writes it back into your own Word template — with a human verification step
before anything reaches the document.**

Filling a long questionnaire is tedious, and letting an LLM do it unsupervised is
worse: it invents. This does neither. It runs the questionnaire as a
conversation, extracts what the interviewee actually said, and shows them the
filled table before a single cell is written.

---

## What it does

```
Authentication          Interview                Verification            Document
┌────────────┐   ┌───────────────────┐   ┌──────────────────┐   ┌──────────────┐
│ password   │   │ one question at a │   │ the filled table │   │ your own     │
│    +       │──▶│ time; ask for a   │──▶│ shown as it will │──▶│ .docx, filled│
│ TOTP       │   │ definition and    │   │ appear — editable│   │ in place     │
│    +       │   │ nothing is stored │   │ before it counts │   │ + SHA-256    │
│ new pass   │   └───────────────────┘   └──────────────────┘   └──────────────┘
└────────────┘
```

Three properties make it usable for work that has to be right.

**It tells a question from an answer.** *"What does criticality level V mean?"* is
answered from a glossary built out of the template's own footnotes, and nothing
is recorded. *"Credit | Origination | Loan assessment"* is a table row. Getting
this wrong silently destroys data, so the routing is deterministic wherever it
can be, and the model is overruled when it disagrees with hard evidence.

**Nothing is recorded until a human confirms it.** Every extraction becomes a
*draft*. The interview holds while a side panel shows the target table exactly as
it will appear in the document — column headers locked, because they come from
the template; cells editable; rows addable. A draft counts for no progress and
never reaches the deliverable.

**It fills the original file.** The template is opened and written into, not
regenerated: styles, table of contents, headers and pre-printed instructions all
survive. Repeating tables grow and shrink to match the data by cloning an
existing row, so new rows carry the document's own formatting.

## Why it is built this way

The design assumptions come from the data it handles — organisational dependency
maps, key-person lists, incident history. Whoever holds that holds a map of where
an organisation breaks.

| Concern | Approach |
| --- | --- |
| Answers must not leak | AES-256-GCM **per field**, with the `(session, field)` address bound in as AAD |
| Answers must not be invented | Schema-constrained output, deterministic guards, human confirmation |
| Data must not leave the network | Runs entirely against a local model via Ollama |
| Actions must be provable afterwards | Hash-chained audit log; tampering is detectable to the row |

Nothing an interviewee types is stored readable — not in the database, the logs,
the audit trail, or on disk.

## Conversation engine

Three interchangeable backends, chosen with `LLM_PROVIDER`:

| Setting | Engine | Leaves your network | Per turn |
| --- | --- | --- | --- |
| `ollama` | local model, `qwen2.5:3b` by default | **nothing** | 3–8 s |
| `anthropic` | `claude-opus-5` | the current turn only | 2–5 s |
| `off` | deterministic, no model at all | nothing | instant |

A 3B model cannot fill an eight-field turn schema in one pass — measured, it
answered *"question"* to every message with empty fields, because constrained
decoding forces it to commit to the label before generating any text. The local
path is therefore decomposed into small single-purpose calls
(`app/ai/staged.py`): classify, then either rewrite one value or extract table
rows. That is both more reliable and faster, since each call emits far fewer
tokens.

Definitions are served **verbatim** from the glossary rather than paraphrased. In
a document that will be audited the source wording is what matters, and a small
model cannot mangle text it never generates.

If a model call fails mid-interview the deterministic engine takes that turn and
the interface says so. A network incident never costs a session.

## Getting started

Requires Python 3.11+, Node 20+, and two `.docx` templates — see
[`backend/templates/README.md`](backend/templates/README.md).

```bash
cd backend
python -m pip install -r requirements.txt
python -m app.scripts.genkeys --write   # generates .env and three secrets
python -m app.scripts.seed              # sample catalogue + initial accounts
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. `seed` prints the provisional passwords once; each
account then enrols an authenticator app and chooses its own password.

For local inference:

```bash
ollama pull qwen2.5:3b
```

then set `LLM_PROVIDER=ollama` in `backend/.env`. With no provider configured the
application is still fully usable — it falls back to the deterministic engine and
shows a "degraded mode" badge, which is convenient for demos.

### Tests

```bash
cd backend && python -m pytest
```

97 tests cover authentication, tenant isolation, encryption, audit-chain
integrity, the verification flow, engine selection, the prompts built for small
models, and the fidelity of the question plan to the templates. They run offline:
the suite pins `LLM_PROVIDER=off` and never reaches a model. Tests that open a
template skip cleanly when none is present.

## Layout

```
backend/
  app/
    core/      config · crypto (AES-256-GCM) · security (Argon2id, JWT, TOTP, CSRF)
               ratelimit · audit (hash chain) · middleware (headers, log redaction)
    api/       auth · survey · chat · admin · deps (access guards)
    ai/        llm (Anthropic + Ollama) · engine (routing) · staged (small models)
               social (deterministic courtesy and navigation)
    pca/       blueprint (question plan) · glossary · docx_filler
    scripts/   genkeys · seed · reset_account
  templates/   your .docx files - not committed
frontend/
  src/
    lib/api.ts       access token in memory, silent refresh, CSRF header
    components/      AuthFlow · StructurePicker · Chat · Composer
                     VerificationPanel · ProgressRail · ThankYou
```

The question plan is the heart of it. Each entry names the exact table, row and
column it writes to, so the interview and the document cannot drift apart — and
two tests fail loudly if they do.

## Security

Full detail in [`docs/SECURITY.md`](docs/SECURITY.md). In brief:

| Area | Control |
| --- | --- |
| Authentication | Argon2id · mandatory TOTP · lockout after 5 failures · indistinguishable error responses |
| Sessions | 10-minute JWT held in memory · rotating `HttpOnly` refresh cookie with **reuse detection** |
| CSRF | HMAC double-submit, bound to the session |
| Data | **AES-256-GCM per field**, session key wrapped under a master KEK |
| Integrity | **Hash-chained** audit log; the first broken row is reported |
| Transport | Strict CSP, HSTS, `no-store`, explicit CORS allow-list |
| Deliverable | Encrypted at rest; download link signed and valid for two minutes |

Known limits are documented rather than glossed over: rate limiting is
in-process (fine for a single instance, needs Redis beyond that), the schema is
created with `create_all` (introduce Alembic before the first production
migration), and the master key is read from the environment (use a vault or KMS
in production).

**Losing the master key destroys the data permanently.** Arrange escrow before
going anywhere near real content.

## Deployment

`docker-compose.yml` runs the API, the SPA behind nginx, and PostgreSQL. Three
things are mandatory first: `ENV=prod` with TLS terminated upstream and
`COOKIE_SECURE=true`; the master key served from a secrets manager rather than a
file; and `CORS_ORIGINS` restricted to the real portal origin.

## Notes

The interface and the interview content are in **French** — the questionnaire
domain is French business-continuity practice. Code, comments and this document
are in English.

`CRYPTO_NAMESPACE` is the domain separator for every AAD and for the token
issuer. Changing it on a live deployment makes existing ciphertexts unreadable;
pin the previous value in `.env` when upgrading.
