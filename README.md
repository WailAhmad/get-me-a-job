# JobsLand 🤖

**Autonomous LinkedIn Easy Apply agent powered by AI.**  
Searches GCC job boards, scores every listing against your CV, and submits Easy Apply applications automatically — while you sleep.

> 🚧 **Active development** — core engine is live and submitting real applications. New capabilities added daily.

---

## What it does

1. **Discovers jobs** — runs 100+ LinkedIn searches across your target roles and countries every hour
2. **Scores each job** — keyword + seniority matching against your CV (threshold: 60/100)
3. **Applies automatically** — walks every Easy Apply form step using an AI brain that reads your CV, remembers past answers, and calls an LLM for anything novel
4. **Routes the rest** — External Apply jobs get saved for manual review; unanswerable questions go to Pending Review; everything else is logged

---

## Live test results (May 2026)

| Run | Jobs scanned | Matched | Applied | Pending | External | Already applied |
|-----|-------------|---------|---------|---------|----------|-----------------|
| Test 1 (Apr 30) | 60 | 8 | 2 ✅ | 3 | 2 | 1 |
| Test 2 (May 1) | 300 | 11 | 1 ✅ | 4* | 5 | 13 |
| Test 3 (May 3) | 300 | 11 | — | — | — | — |

*Pending caused by a now-fixed bug (pre-filled field skip not carried to validation check)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Frontend  (React + Vite · :3000)        │
│  Dashboard · Job Explorer · Chat · CV · Settings     │
│  Pending Review · Answer Memory · App History        │
└──────────────────────┬──────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────┐
│              Backend  (FastAPI · :8001)               │
│                                                      │
│  ┌──────────────┐  ┌──────────────────────────────┐ │
│  │ State Manager│  │        Automation Loop        │ │
│  │ (JSON + mem) │  │  scraper → scorer → applier  │ │
│  └──────────────┘  └──────────┬───────────────────┘ │
│                               │                      │
│              ┌────────────────┼──────────────────┐   │
│              ▼                ▼                  ▼   │
│  ┌─────────────────┐ ┌──────────────┐ ┌──────────┐  │
│  │linkedin_scraper │ │form_inspector│ │form_brain│  │
│  │  (Selenium)     │ │ DOM snapshot │ │AI answers│  │
│  └─────────────────┘ └──────────────┘ └────┬─────┘  │
│                                            ▼         │
│                                     ┌──────────────┐ │
│                                     │ form_filler  │ │
│                                     │ per-type DOM │ │
│                                     │  interaction │ │
│                                     └──────────────┘ │
└─────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
   LinkedIn.com            Groq API (LLM)
   (Selenium)           Llama 3.3 70B Versatile
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite, react-router-dom, lucide-react |
| Styling | Vanilla CSS — dark theme, glassmorphism |
| Backend | Python 3.12 + FastAPI + Uvicorn |
| Automation | Selenium 4 + Chrome headless |
| AI (form filling) | Groq — `llama-3.3-70b-versatile` |
| AI (job scoring) | Keyword + seniority scoring engine |
| AI (chat) | Groq — natural language preference intake |
| State | `data/state.json` — in-memory + file persistence |

---

## Project structure

```
get-me-a-job/
├── backend/
│   ├── main.py                    # FastAPI app + router registration
│   ├── state.py                   # Thread-safe JSON state store
│   ├── config.py                  # Env vars (API keys, paths)
│   ├── routers/
│   │   ├── automation.py          # 🔑 Core loop: discover → score → apply
│   │   ├── dashboard.py           # Stats aggregation for UI cards
│   │   ├── jobs.py                # Job CRUD + status updates
│   │   ├── chat.py                # AI preference intake conversation
│   │   ├── cv.py                  # PDF upload + skill extraction
│   │   ├── auth.py                # Google OAuth
│   │   ├── profile.py             # User profile management
│   │   ├── settings.py            # LinkedIn session + live mode
│   │   ├── sources.py             # Job source connectors
│   │   ├── answers.py             # Answer bank CRUD
│   │   └── linkedin_debug.py      # Debug endpoints (search/apply tests)
│   └── services/
│       ├── linkedin_scraper.py    # Selenium LinkedIn job discovery
│       ├── linkedin_applier.py    # 🔑 Easy Apply form orchestrator
│       ├── form_inspector.py      # DOM → structured field snapshot
│       ├── form_brain.py          # AI decision layer (profile/bank/LLM)
│       ├── form_filler.py         # Per-type field interaction (click/type/select)
│       └── session_manager.py     # Chrome profile + LinkedIn cookie management
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx      # Main stats dashboard + automation control
│       │   ├── JobExplorer.jsx    # Browse/filter all discovered jobs
│       │   ├── Chat.jsx           # AI preference chat
│       │   ├── CVUpload.jsx       # CV upload + skill preview
│       │   ├── Settings.jsx       # LinkedIn session, live mode, AI config
│       │   ├── PendingReview.jsx  # Answer unknown form questions
│       │   ├── AnswerMemory.jsx   # View/edit saved Q&A bank
│       │   ├── ApplicationHistory.jsx  # Submitted applications log
│       │   └── Welcome.jsx        # Login / landing
│       ├── components/
│       │   ├── Sidebar.jsx        # Navigation
│       │   ├── AutomationPanel.jsx # Run/stop controls + live log stream
│       │   ├── AutomationWindow.jsx # SSE log window
│       │   ├── Logo.jsx           # App logo
│       │   ├── HourlyChart.jsx    # Activity chart
│       │   └── Layout.jsx         # Shell wrapper
│       └── api/client.js          # Typed API client (40+ functions)
├── agent/                         # Standalone agent module (experimental)
├── data/
│   ├── state.json                 # 🔒 gitignored — runtime state
│   ├── uploads/                   # 🔒 gitignored — CV PDFs
│   └── sessions/                  # 🔒 gitignored — Chrome profile + cookies
├── start.sh                       # One-command start (backend + frontend)
└── .env                           # 🔒 gitignored — API keys
```

---

## The AI form-filling engine (v2.0)

This is the core innovation — three modules that work together to fill any LinkedIn Easy Apply form:

### `form_inspector.py` — DOM Snapshot
Walks the entire modal and returns every interactive field as structured JSON:
- Resolves label text from 8 sources (`for=`, `aria-label`, `aria-labelledby`, wrapping `<label>`, `<legend>`, placeholder, `name` attr, preceding text node)
- Detects all field types: `text`, `number`, `tel`, `email`, `url`, `select`, `radio`, `checkbox`, `combobox`, `typeahead`, `textarea`, `file`
- Captures ALL option texts verbatim for select/radio/combobox — so the LLM can pick character-for-character
- Reads current DOM values, required markers, validation errors

### `form_brain.py` — AI Decision Layer
Three-tier resolution for every field:

```
1. Profile heuristics  (instant, no API call)
   → name, email, phone, city, education, salary, LinkedIn URL,
     work authorisation, diversity questions, notice period …

2. Answers bank  (instant, fuzzy-matched)
   → 51 saved Q&A pairs from previous applications
   → exact match → substring → word-overlap (≥3 significant words)

3. Groq LLM — ONE call per form step  (~1.5s)
   → sees ALL fields + ALL options + validation errors together
   → returns exact option text for selects/radios (no paraphrasing)
   → confident=true for anything profile-derivable
   → confident=false only for genuinely unknown data (passport, SSN)
```

### `form_filler.py` — Smart DOM Interaction
Per-type fillers with JS fallbacks for LinkedIn's SDUI custom components:

| Field type | Strategy |
|---|---|
| `text / email / url / tel` | `clear()` + `send_keys()` → JS React-event setter fallback |
| `number` | integer coercion then `fill_text` |
| `textarea` | same as text |
| `select` | `Select.select_by_visible_text()` → iterate options → substring |
| `radio` | click label → `data-test-*` attr → word-overlap pick |
| `checkbox` | click only if state mismatch |
| `combobox` | click trigger → wait `[role='listbox']` → click `[role='option']` |
| `typeahead` | `send_keys` → wait dropdown → click first suggestion → Tab fallback |
| `file` | skip (LinkedIn uses stored resume) |

---

## Job routing logic

```
Discovered job
      │
      ├─ score < 60  ──────────────────────────────► Skipped
      │
      ├─ score ≥ 60, no Easy Apply button  ──────────► External Jobs
      │
      └─ score ≥ 60, Easy Apply ───► form_inspector
                                          │
                                     form_brain
                                          │
                                     form_filler
                                          │
                              ┌───────────┴───────────┐
                         success                  failed / stuck
                              │                        │
                         ✅ Applied            confident=false?
                                                       │
                                              ┌────────┴────────┐
                                           yes (truly         no (3 retries
                                           unknown)           exhausted)
                                              │                  │
                                         ⏸ Pending         ⏸ Pending
                                         (answer it)       (validation)
```

**External = jobs with no Easy Apply button only.** Form failures never route to External.

---

## Answer memory

Every time the LLM answers a new question confidently, the answer is saved to the bank. Next time the same question appears on any form, it's answered instantly — no API call needed.

The bank currently covers:
- Personal: name, first/last name, email, phone, city, country, nationality
- Professional: years of experience, LinkedIn URL, notice period, expected salary
- Education: degree level, bachelor/master/PhD completion
- Employment: work authorisation, sponsorship, relocation, commute, background check
- Proficiency: language levels (Arabic, English — "Native / Bilingual")
- Diversity: gender, ethnicity, veteran status, disability (all "Prefer not to say")
- Tech-specific: years with Python, SQL, AWS, Databricks, Power BI, etc.

---

## Getting started

### Prerequisites
- Python 3.12+
- Node.js 18+
- Google Chrome
- A [Groq API key](https://console.groq.com) (free tier works)

### Setup

```bash
git clone https://github.com/WailAhmad/get-me-a-job.git
cd get-me-a-job

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..

# Environment
cp .env.example .env        # then fill in your keys
```

### `.env` keys

```env
AI_API_KEY=gsk_...          # Groq API key (required)
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile

GOOGLE_CLIENT_ID=...        # Google OAuth (for login)
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:8001/api/auth/google/callback
```

### Run

```bash
./start.sh
# → Backend:  http://127.0.0.1:8001
# → Frontend: http://127.0.0.1:3000
```

### First-time flow

1. **Log in** with Google
2. **Upload your CV** (PDF) — skills and years are extracted automatically
3. **Open Settings → LinkedIn** → click "Open Login Window" → log in to LinkedIn in the Chrome window that appears → click "Verify Session"
4. **Chat tab** → tell the AI what roles and countries you're targeting
5. **Dashboard** → click **Run Now** → watch the live log

---

## API reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard/stats` | All counters (last run, today, all-time) |
| GET | `/api/automation/status` | Engine state + rate-limit counters |
| POST | `/api/automation/start` | Start automation cycle |
| POST | `/api/automation/stop` | Stop engine |
| GET | `/api/automation/logs` | SSE live log stream |
| GET | `/api/automation/logs/poll` | Poll-based log fallback |
| POST | `/api/automation/clear-jobs` | Reset all job data |
| GET | `/api/jobs/` | All discovered jobs |
| GET | `/api/jobs/pending` | Jobs needing manual answer |
| GET | `/api/jobs/external` | External apply jobs |
| POST | `/api/jobs/{id}/answer` | Submit answer for pending job |
| GET | `/api/cv/` | CV metadata + extracted skills |
| POST | `/api/cv/upload` | Upload PDF |
| GET | `/api/chat/` | Chat history + current preferences |
| POST | `/api/chat/` | Send message |
| GET | `/api/settings/live-mode` | Live vs demo mode |
| PUT | `/api/settings/live-mode` | Toggle live/demo |
| POST | `/api/settings/linkedin-session/open` | Open Chrome login window |
| POST | `/api/settings/linkedin-session/verify` | Verify LinkedIn cookies |
| GET | `/api/answers/` | Answer bank |
| POST | `/api/answers/` | Add answer |
| DELETE | `/api/answers/{id}` | Remove answer |
| GET | `/api/profile/` | User profile |
| POST | `/api/profile/google/connect` | Google OAuth callback |

---

## Feature status

### ✅ Working

- LinkedIn live job discovery (Selenium, authenticated session)
- Multi-keyword × multi-country search grid (102 combinations)
- Easy Apply form walking — all field types including SDUI custom dropdowns
- AI form brain — profile heuristics → answer bank → single LLM call per step
- Answer memory with fuzzy matching — remembers all answered questions
- Pre-filled field detection — skips fields LinkedIn already populated
- Validation error feedback loop — errors passed back to LLM on retry
- Already-applied detection — skips duplicates
- Job routing: Applied / External / Pending / Failed / Skipped
- Dashboard with last-run stats, today stats, all-time stats
- Live log streaming (SSE)
- Google OAuth login
- CV upload with skill extraction
- AI preference intake chat
- Answer Memory page (view/edit bank)
- Pending Review page (answer unknown questions)

### 🚧 In progress

- Score calibration — some off-domain roles still reaching 60+ threshold
- Search keyword quality — 0-result terms being replaced with better ones
- Pre-filled field handling edge cases

### 📋 Planned

- [ ] Playwright migration (replace Selenium — faster, more reliable)
- [ ] SQLite history database (replace in-memory JSON)
- [ ] Scheduler (run every hour automatically without server restart)
- [ ] Email/Telegram notifications on application
- [ ] Cover letter generation per job
- [ ] Resume tailoring per job description
- [ ] Indeed / GulfTalent / Bayt scrapers
- [ ] Proxy / fingerprint rotation (anti-bot)
- [ ] Semantic job scoring (sentence-transformers, replace keyword overlap)
- [ ] Unit + integration tests

---

## Known limitations

- **Single user** — state is a single JSON file, not multi-tenant
- **macOS only** — Chrome profile path and Keychain assumptions; untested on Linux/Windows
- **LinkedIn TOS** — automation may violate LinkedIn's terms of service; use responsibly
- **Rate limits** — LinkedIn detects rapid activity; currently capped at 100 apps/day, 10/hour
- **Session expiry** — LinkedIn cookies expire; requires periodic re-login through the Settings page

---

## Codebase metrics

| Component | Files | Lines |
|---|---|---|
| Backend Python | 20 | ~8,500 |
| Frontend JSX/JS | 17 | ~4,200 |
| Agent module | 16 | ~1,400 |
| **Total** | **53** | **~14,100** |

---

## License

MIT — do whatever you want with it.

---

*Built by Wael Ahmad · May 2026 · v2.0 in active development*
