# Interview Chatbot

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

Four properties make it usable for work that has to be right.

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

**Nothing closes with silent gaps.** Running out of questions is not the same as
having answered them. When the last question is passed the interview stops one
step short and lists what is still blank, each entry a way back in. Closing over
gaps is allowed — some points genuinely have no answer — but it takes an
explicit acknowledgement, and the document is only ever produced from a
deliberately closed interview.

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
| One record per entity | An interview is opened once and never silently restarted |

Nothing an interviewee types is stored readable — not in the database, the logs,
the audit trail, or on disk.

## Conversation engine

Inference is **local**. Nothing an interviewee types is sent to a third-party
model, so the questionnaire can be run on data that is not allowed to leave the
network.

| `LLM_PROVIDER` | Engine | Leaves your network | Per turn |
| --- | --- | --- | --- |
| `ollama` | local model, `qwen2.5:3b` by default | **nothing** | 3–8 s |
| `off` | deterministic, no model at all | **nothing** | instant |

A 3B model cannot fill an eight-field turn schema in one pass — measured, it
answered *"question"* to every message with empty fields, because constrained
decoding forces it to commit to the label before generating any text. The local
path is therefore decomposed into small single-purpose calls
(`app/ai/staged.py`): classify, then either rewrite one value or extract table
rows. That is both more reliable and faster, since each call emits far fewer
tokens.

**Deterministic filters run before any model call.** Courtesy (`app/ai/social.py`),
navigation, and questions about the workshop itself (`app/ai/faq.py`) are matched
on the whole message and answered without inference. These are the cases where a
small model's judgement is worth nothing and the right answer is fixed — and
where a misclassification is expensive: a greeting recorded as an answer puts
"hello" in an audit document.

Definitions are served **verbatim** from the glossary rather than paraphrased. In
a document that will be audited the source wording is what matters, and a small
model cannot mangle text it never generates. A term that is genuinely absent is
admitted as absent; anything outside the workshop is declined plainly.

If a model call fails mid-interview the deterministic engine takes that turn and
the interface says so. A network incident never costs a session.

## Two ways to collect

The same question plan drives both, generated from one source
(`app/pca/blueprint.py`) rather than transcribed — so the two routes cannot
drift into asking different questions.

**The chatbot**, for a guided conversation with verification at every step.

**Google Forms**, for correspondents who will not sit through an interview.
`app/scripts/export_forms_spec.py` emits an Apps Script bundle that builds two
forms — one for the entity plan, one for the longer IT plan — and
`app/scripts/from_forms.py` feeds the exported responses back through the *same*
template filler, so both routes emit identical documents for identical answers.
See [`google-forms/README.md`](google-forms/README.md).

Google cannot produce the deliverable itself: the templates have fixed tables and
merged cells that do not survive a round trip through Google Docs.

## Oversight

Accounts carry a role. An **administrator** gets a progress screen covering every
entity, including the ones nobody has opened: state, points answered, points
outstanding, participant, last activity.

It is built from the same state the interviewee sees, so the two can never
disagree, and it exposes **counts and labels only** — the endpoint decrypts
nothing, and a test asserts that no answer text reaches the wire.

An administrator can also **reset** an interview: it returns to its first
question and a closed one reopens. That is the only way to undo a wrong entity
choice, so it is deliberately destructive and deliberately narrow — admin-only,
confirmed in the interface, and written to the audit chain with the counts it
destroyed.

## Accounts

One login per entity, each scoped to a single structure by `allowed_structures`.
The catalogue such an account is served has exactly one entry, and the picker
selects it automatically. Scoping is enforced **server-side** — opening someone
else's structure is a 403, not a hidden card.

Addresses derive from the structure code rather than a person's name: the
correspondent for an entity may change, the entity does not. `seed` can write the
provisional passwords to a CSV for distribution, because thirty-odd passwords
cannot be copied out of a console.

## Getting started

Requires Python 3.11+, Node 20+, and two `.docx` templates — see
[`backend/templates/README.md`](backend/templates/README.md).

```bash
cd backend
python -m pip install -r requirements.txt
python -m app.scripts.genkeys --write   # generates .env and three secrets
python -m app.scripts.seed              # sample catalogue + one account per entity
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. `seed` prints the provisional passwords once; each
account then enrols an authenticator app and chooses its own password. Add
`--credentials-file identifiants.csv` to get them as a file instead — it holds
plaintext secrets, so distribute it and delete it.

To try it out without creating real accounts:

```bash
python -m app.scripts.demo_account
```

Two ready-to-use logins — one interviewee, one administrator — with a known
password and a known TOTP secret, so no phone is needed; the script prints the
current six-digit code. It **refuses to run when `ENV=prod`**: a fixed second
factor is fine on a laptop and unacceptable on a server.

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

202 tests cover authentication, tenant isolation, encryption, audit-chain
integrity, the verification flow, the review gate, one-interview-per-entity,
account scoping, administration, the on-disk logs, the Forms round trip, engine
selection, the prompts built for small models, and the fidelity of the question
plan to the templates. They run offline: the suite pins `LLM_PROVIDER=off` and
never reaches a model. Tests that open a template skip cleanly when none is
present.

## Layout

```
backend/
  app/
    core/      config · crypto (AES-256-GCM) · security (Argon2id, JWT, TOTP, CSRF)
               ratelimit · audit (hash chain) · middleware (headers, log redaction)
    api/       auth · survey · chat · admin · deps (access guards)
    ai/        llm (Ollama client) · engine (routing) · staged (small models)
               social (courtesy, navigation) · faq (questions about the workshop)
    pca/       blueprint (question plan) · glossary · docx_filler
               transcript (readable per-entity log)
    scripts/   genkeys · seed · reset_account
               export_forms_spec · from_forms (Google Forms round trip)
  templates/   your .docx files - not committed
frontend/
  src/
    lib/api.ts       access token in memory, silent refresh, CSRF header
    components/      AuthFlow · StructurePicker · Chat · Composer
                     VerificationPanel · ProgressRail · ReviewGate
                     CompletedInterview · ThankYou · AdminConsole
google-forms/  Apps Script generator for the second collection route
deploy/        key generator, env template, install and update guide
```

The question plan is the heart of it. Each entry names the exact table, row and
column it writes to, so the interview and the document cannot drift apart — and
two tests fail loudly if they do.

## Transcripts

Optional, off by default. With `TRANSCRIPT_ENABLED=true` every interview is
written to a Markdown file per entity, rewritten after each turn: the whole
conversation, every answer, and the points still blank. It answers "what exactly
did this person say?" long after the fact, without decrypting a database.

The trade is explicit: **these files are plaintext** where the database encrypts
per field. Point `TRANSCRIPT_DIR` somewhere the operating system protects, or
leave the feature off.

## Security

Full detail in [`docs/SECURITY.md`](docs/SECURITY.md). In brief:

| Area | Control |
| --- | --- |
| Authentication | Argon2id · mandatory TOTP · lockout after 5 failures · indistinguishable error responses |
| Sessions | 10-minute JWT held in memory · rotating `HttpOnly` refresh cookie with **reuse detection** |
| CSRF | HMAC double-submit, bound to the session |
| Data | **AES-256-GCM per field**, session key wrapped under a master KEK |
| Authorisation | Per-entity scoping enforced server-side; destructive actions are admin-only |
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

`docker-compose.yml` runs four containers on one machine: PostgreSQL, Ollama, the
API, and the SPA behind nginx. Only nginx publishes a port. Once installed
nothing needs the internet — inference is local.

Step by step, including update, backup and the traps:
[`deploy/DEPLOY.md`](deploy/DEPLOY.md).

```bash
cp deploy/.env.example .env      # then run deploy/generate_keys.py and fill it in
docker compose up -d --build
docker compose exec api python -m app.scripts.seed
```

Two settings deserve a decision rather than a default. `COOKIE_SECURE` must be
`false` to work over plain HTTP on a LAN — a `Secure` cookie is never returned by
the browser, so sessions would not survive a minute — which means LAN traffic is
unencrypted; put TLS in front and set it back to `true`. And `CORS_ORIGINS` must
match exactly what users type, port included, or the page loads and the login
fails.

## Notes

The interface and the interview content are in **French** — the questionnaire
domain is French business-continuity practice. Code, comments and this document
are in English.

`CRYPTO_NAMESPACE` is the domain separator for every AAD and for the token
issuer. Changing it on a live deployment makes existing ciphertexts unreadable;
pin the previous value in `.env` when upgrading.
