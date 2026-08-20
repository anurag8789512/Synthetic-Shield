# SyntheticShield — AI-Powered Insurance Fraud Detection

An end-to-end deepfake detection platform for motor insurance claims. Claimants submit evidence (video, photos, audio statement) via a mobile FNOL app. An AI pipeline analyzes each modality for synthetic manipulation and assigns a fraud score. Insurance officers review flagged claims on a real-time dashboard, assisted by an LLM-powered Copilot that can answer questions about the evidence and look up repair cost estimates.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend (Dashboard) | React 19 + TypeScript + Vite |
| Frontend (Mobile FNOL) | React 19 + TypeScript + Vite |
| Deepfake Detection | Reality Defender API / Resemble AI / Mock |
| LLM Copilot | Mistral AI (or Google Gemini) |
| Repair Cost Search | SerpApi |
| OTP / Auth | Resend (email) / 2Factor.in (SMS) / console (dev) |
| Vector Similarity | ChromaDB |
| PDF Reports | ReportLab |

---

## Project Structure

```
synthetic-shield/
├── backend/
│   ├── app/
│   │   ├── agents/              <- AI agents (detection, copilot, similarity, etc.)
│   │   ├── providers/
│   │   │   └── detection/       <- reality_defender.py, resemble_ai.py, mock_providers.py
│   │   ├── routers/             <- API route handlers
│   │   ├── config.py            <- All settings (reads from .env)
│   │   ├── models.py            <- SQLAlchemy DB models
│   │   ├── schemas.py           <- Pydantic request/response schemas
│   │   └── main.py              <- FastAPI app entry point
│   ├── .env                     <- CREATE THIS FILE — all API keys go here
│   ├── requirements.txt
│   └── seed_data.py             <- Populates DB with test users & sample claims
│
├── frontend/
│   ├── dashboard/               <- SIU Dashboard (port 3000)
│   │   └── src/
│   │       ├── components/dashboard/
│   │       └── data/api.ts      <- All backend API calls
│   └── mobile/                  <- Claimant FNOL App (port 3001)
│       └── src/
│           └── components/mobile/MobilePortal.tsx
│
└── instruction/
    └── SyntheticShield_Backend_Spec.md
```

---

## Prerequisites

- **Python 3.12 or 3.14** — https://www.python.org/downloads/
- **Node.js 18+** — https://nodejs.org/ (LTS recommended)
- **Git** — https://git-scm.com/

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/Anurag-Krishna_msgcp/Synthetic_Shield_updated.git
cd Synthetic_Shield_updated
```

---

## Step 2 — Backend Setup

### 2a. Create a virtual environment

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Mac / Linux:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

> If you get a script execution error on Windows, run this first:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

If you hit SSL errors on Windows:
```powershell
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### 2c. Create the `.env` file

In the `backend/` folder, create a file named **`.env`** (no file extension). Copy this full template and fill in keys as needed — everything defaults to `mock`/`console` so you can run with zero API keys:

```env
# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
DATABASE_URL=sqlite:///./claims.db

# ─────────────────────────────────────────────
#  DETECTION PROVIDERS
#  Options per modality: "mock" | "reality_defender" | "resemble_ai"
#  "mock" requires no API key — use it for a quick local run.
# ─────────────────────────────────────────────
VIDEO_DETECTION_PROVIDER=mock
AUDIO_DETECTION_PROVIDER=mock
IMAGE_DETECTION_PROVIDER=mock
TEXT_DETECTION_PROVIDER=mock

# Required only if any provider above is "reality_defender"
REALITY_DEFENDER_API_KEY=

# Required only if AUDIO_DETECTION_PROVIDER=resemble_ai
RESEMBLE_AI_API_KEY=

# ─────────────────────────────────────────────
#  LLM COPILOT
#  Options: "mistral" | "gemini" | "mock"
#  "mock" uses rule-based responses — no API key needed.
# ─────────────────────────────────────────────
COPILOT_LLM_PROVIDER=mock

# Required if COPILOT_LLM_PROVIDER=mistral
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest

# Required if COPILOT_LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# Used by the Copilot for real-time repair cost lookups (optional)
SERPAPI_API_KEY=

# ─────────────────────────────────────────────
#  OTP / AUTHENTICATION
#  Options: "console" | "email" | "fast2sms" | "twilio"
#  "console" prints OTPs to the terminal — no key needed.
# ─────────────────────────────────────────────
OTP_PROVIDER=console

# Required if OTP_PROVIDER=email   (get from https://resend.com)
RESEND_API_KEY=

# Required if OTP_PROVIDER=fast2sms   (get from https://fast2sms.com)
FAST2SMS_API_KEY=

# Alternative SMS provider   (get from https://2factor.in)
TWOFACTOR_API_KEY=

# ─────────────────────────────────────────────
#  FRAUD SCORE THRESHOLDS
#  Claims below AUTO_APPROVE_BELOW are auto-approved with payout.
#  Claims above SIU_FLAG_ABOVE are flagged for SIU investigation.
# ─────────────────────────────────────────────
AUTO_APPROVE_BELOW=15
SIU_FLAG_ABOVE=85

# ─────────────────────────────────────────────
#  MISC
# ─────────────────────────────────────────────
STORAGE_PROVIDER=local
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:5173
MOCK_PAYOUT_AMOUNT_CENTS=125000
```

### 2d. Seed the database

```bash
python seed_data.py
```

Expected output:
```
Database seeded successfully!
======= Test Credentials =======
Mobile App (OTP login):
  Phone: 6202234696
  Email: krishnaanurag16@gmail.com
SIU Dashboard:
  Email: krishnaanurag16@gmail.com
  Password: shield@123
```

---

## Step 3 — Start the Backend

```powershell
# Windows — from the backend/ folder with venv active
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```bash
# Mac / Linux
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Verify: open **http://localhost:8000/docs** — Swagger UI with all endpoints listed.

---

## Step 4 — Frontend Setup

Each app has its own `package.json`. Open two new terminals.

```bash
# Dashboard
cd frontend/dashboard
npm install
npm run dev          # -> http://localhost:3000

# Mobile App (separate terminal)
cd frontend/mobile
npm install
npm run dev          # -> http://localhost:3001
```

---

## Step 5 — Test the Full Flow

### Claimant Flow — Mobile App (http://localhost:3001)

1. Enter phone `6202234696` or email `krishnaanurag16@gmail.com`
2. **OTP:** if `OTP_PROVIDER=console`, the 6-digit code prints in the **backend terminal**
3. Enter the OTP to log in
4. Tap **Submit a Claim** → complete the 6-step FNOL wizard:
   - Step 1: Select coverage type
   - Step 2: Upload a dashcam / incident video (optional)
   - Step 3: Upload photos of the damage
   - Step 4: Record an audio statement
   - Step 5: Attach supporting documents (optional)
   - Step 6: Review & submit
5. The AI detection pipeline runs automatically in the background

### Officer Flow — Dashboard (http://localhost:3000)

1. Login: `krishnaanurag16@gmail.com` / `shield@123`
2. **Claims Queue** — see all submitted claims with AI fraud scores and per-modality analysis
3. Click any claim → view evidence (video, photos, audio) and individual modality scores
4. **AI Copilot tab** — ask natural-language questions:
   - "Why was this claim flagged?"
   - "Is the claimed amount reasonable for this damage?"
   - "What is the confidence on the audio analysis?"
   - "Summarize the evidence for this claim"
5. **Actions tab** — Approve or Reject a claim (only shows for non-auto-approved claims)
6. **SIU Vote tab** — cast investigator votes on SIU-referred claims
7. **Reports** — download a full AI analysis PDF

---

## Demo Credentials

### Claimant — Mobile App (OTP login)

| Field | Value |
|-------|-------|
| Phone | 6202234696 |
| Email | krishnaanurag16@gmail.com |

### Officers — Dashboard (password login)

| Name | Email | Password | Role |
|------|-------|----------|------|
| Krishna Anurag | krishnaanurag16@gmail.com | shield@123 | Lead Officer |
| D. Torres | d.torres@syntheticshield.demo | demo123 | SIU Officer |
| R. Park | r.park@syntheticshield.demo | demo123 | SIU Officer |
| S. Okonkwo | s.okonkwo@syntheticshield.demo | demo123 | SIU Officer |
| M. Reyes | m.reyes@syntheticshield.demo | demo123 | SIU Officer |
| J. Chen | j.chen@syntheticshield.demo | demo123 | Moderator |

---

## API Keys — Where to Get Them

All keys go in `backend/.env`. None are required for a zero-config local run.

### Reality Defender — Deepfake Detection
- **What it does:** Analyzes images and audio for AI-generated / deepfake content
- **Sign up:** https://app.realitydefender.com — API Keys section in the dashboard
- **Free tier:** Image + audio analysis. Video and text require a paid plan.
- **`.env` settings:**
  ```env
  IMAGE_DETECTION_PROVIDER=reality_defender
  AUDIO_DETECTION_PROVIDER=reality_defender
  VIDEO_DETECTION_PROVIDER=reality_defender
  REALITY_DEFENDER_API_KEY=your_key_here
  ```

### Resemble AI — Synthetic Voice Detection
- **What it does:** Detects AI-cloned / synthetically generated speech
- **Sign up:** https://app.resemble.ai — API section, generate a key
- **Note:** Requires account credits to run inference
- **`.env` settings:**
  ```env
  AUDIO_DETECTION_PROVIDER=resemble_ai
  RESEMBLE_AI_API_KEY=your_key_here
  ```

### Mistral AI — LLM Copilot
- **What it does:** Powers the AI Copilot chat with tool calling, reasoning, and repair cost lookups
- **Sign up:** https://console.mistral.ai — API Keys section
- **Free tier:** Available with rate limits; `mistral-small-latest` is the most cost-effective model
- **`.env` settings:**
  ```env
  COPILOT_LLM_PROVIDER=mistral
  MISTRAL_API_KEY=your_key_here
  MISTRAL_MODEL=mistral-small-latest
  ```

### Google Gemini — LLM Copilot (alternative to Mistral)
- **What it does:** Alternative LLM backend for the Copilot
- **Get a key:** https://aistudio.google.com/apikey
- **Free tier:** Generous quota on Gemini 2.0 Flash
- **`.env` settings:**
  ```env
  COPILOT_LLM_PROVIDER=gemini
  GEMINI_API_KEY=your_key_here
  GEMINI_MODEL=gemini-2.0-flash
  ```

### SerpApi — Repair Cost Lookup
- **What it does:** Lets the Copilot search Google for real-world part/repair cost estimates when officers ask price questions
- **Sign up:** https://serpapi.com — Dashboard → API Key
- **Free tier:** 100 searches/month
- **`.env` settings:**
  ```env
  SERPAPI_API_KEY=your_key_here
  ```

### Resend — Email OTP
- **What it does:** Sends one-time passwords to claimants via email
- **Sign up:** https://resend.com — API Keys → Create
- **Free tier:** 3,000 emails/month
- **`.env` settings:**
  ```env
  OTP_PROVIDER=email
  RESEND_API_KEY=your_key_here
  ```

### Fast2SMS — SMS OTP (India)
- **What it does:** Sends OTPs via SMS to Indian mobile numbers
- **Sign up:** https://fast2sms.com — Dev API section
- **`.env` settings:**
  ```env
  OTP_PROVIDER=fast2sms
  FAST2SMS_API_KEY=your_key_here
  ```

### 2Factor.in — SMS OTP (India, alternative)
- **What it does:** Alternative SMS OTP provider for Indian numbers
- **Sign up:** https://2factor.in
- **`.env` settings:**
  ```env
  TWOFACTOR_API_KEY=your_key_here
  ```

---

## Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server health check |
| POST | `/auth/request-otp` | Send OTP to phone/email |
| POST | `/auth/verify-otp` | Verify OTP, receive session token |
| POST | `/auth/dashboard-login` | Officer password login |
| POST | `/claims` | Submit a new claim (multipart/form-data) |
| GET | `/claims/queue/all` | All claims for the dashboard |
| GET | `/claims/{id}` | Single claim detail |
| POST | `/claims/{id}/copilot-chat` | Chat with AI Copilot about a claim |
| GET | `/claims/{id}/copilot-history` | Full Copilot chat history |
| POST | `/claims/{id}/moderator-approve` | Approve a claim |
| POST | `/claims/{id}/moderator-reject` | Reject a claim |
| POST | `/claims/{id}/siu-vote` | Cast SIU officer vote |
| GET | `/claims/report/{id}/pdf` | Download AI analysis PDF |
| GET | `/similarity/claim/{id}` | Find similar historical claims |
| GET | `/efficiency/officers` | Officer workload statistics |

Full interactive docs: **http://localhost:8000/docs**

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Activate.ps1 cannot be loaded` (Windows) | Run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| SSL errors during `pip install` | Add `--trusted-host pypi.org --trusted-host files.pythonhosted.org` to the pip command |
| `ModuleNotFoundError` on startup | Confirm venv is active (`(venv)` prefix in terminal) and requirements installed |
| OTP not arriving | Set `OTP_PROVIDER=console` in `.env` and look in the backend terminal for the printed code |
| CORS errors in browser console | Ensure `CORS_ORIGINS` in `.env` includes both `http://localhost:3000` and `http://localhost:3001` |
| Port 8000 already in use | Windows: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F` |
| Database errors or missing demo data | Delete `backend/claims.db` and re-run `python seed_data.py` |
| Frontend won't compile | Re-run `npm install` inside the specific app folder |
| Copilot gives generic rule-based answers | Set `COPILOT_LLM_PROVIDER=mistral` and add `MISTRAL_API_KEY` in `.env` |
| Detection always shows mock results | Set `IMAGE_DETECTION_PROVIDER=reality_defender` and add `REALITY_DEFENDER_API_KEY` |

---

## Quick-Start Summary

Three terminals, three commands:

```bash
# Terminal 1 — Backend
cd backend
.\venv\Scripts\Activate.ps1      # Windows  (Mac/Linux: source venv/bin/activate)
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Dashboard
cd frontend/dashboard
npm run dev

# Terminal 3 — Mobile App
cd frontend/mobile
npm run dev
```

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| SIU Dashboard | http://localhost:3000 |
| Mobile FNOL App | http://localhost:3001 |
