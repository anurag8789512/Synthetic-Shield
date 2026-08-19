# SyntheticShield — AI-Powered Insurance Fraud Detection

An end-to-end deepfake detection system for motor insurance claims. Claimants submit evidence via a mobile app; AI analyzes video, audio, images, and text for synthetic manipulation; officers review flagged claims on a dashboard.

---

## Prerequisites

- **Python 3.12+** (3.14 works too)
- **Node.js 18+** with npm
- **Git** (optional, for cloning)

---

## Project Structure

```
synthetic shield/
├── backend/          ← FastAPI server (Python)
│   ├── app/          ← Application code
│   ├── venv/         ← Python virtual environment
│   ├── .env          ← Configuration & API keys
│   ├── claims.db     ← SQLite database (auto-created)
│   └── seed_data.py  ← Creates test users & officers
│
├── frontend/         ← React + Vite (TypeScript)
│   ├── src/          ← Source code
│   ├── dashboard.html ← SIU Dashboard entry
│   ├── mobile.html    ← Mobile FNOL app entry
│   └── package.json
│
└── instruction/      ← Spec documents
```

---

## Step 1: Set Up the Backend

Open a terminal and run:

```powershell
cd "synthetic shield/backend"

# Create virtual environment
python -m venv venv

# Activate it (Windows)
.\venv\Scripts\Activate.ps1

# Or on Mac/Linux:
# source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings python-multipart httpx chromadb reportlab pillow

# Seed the database with test data
python seed_data.py
```

You should see:
```
Database seeded successfully!
═══ Test Credentials ═══
Mobile App (OTP login):
  Phone: 6202234696
  Email: krishnaanurag16@gmail.com
SIU Dashboard:
  Email: krishnaanurag16@gmail.com
  Password: shield@123
```

---

## Step 2: Configure Environment Variables

Edit `backend/.env` — the key settings are:

```env
# OTP delivery (set to "console" to just print codes, or "email" for real delivery)
OTP_PROVIDER=console

# For real email OTP delivery (optional):
# OTP_PROVIDER=email
# RESEND_API_KEY=your_resend_api_key
# TWOFACTOR_API_KEY=your_2factor_api_key

# Detection (keep as "mock" unless you have vendor API keys)
VIDEO_DETECTION_PROVIDER=mock
AUDIO_DETECTION_PROVIDER=mock
IMAGE_DETECTION_PROVIDER=mock
TEXT_DETECTION_PROVIDER=mock
```

For a first run, the defaults work fine — everything runs with mock providers.

---

## Step 3: Start the Backend

```powershell
cd "synthetic shield/backend"
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Verify it works: open http://localhost:8000/docs in your browser (Swagger UI).

---

## Step 4: Set Up the Frontend

Open a **new terminal**:

```powershell
cd "synthetic shield/frontend"
npm install
```

---

## Step 5: Start the Frontend (Two Apps)

**SIU Dashboard** (for insurance officers):
```powershell
npx vite --config vite.dashboard.config.ts
```
Opens at: **http://localhost:3000/dashboard.html**

**Mobile FNOL App** (for claimants) — in another terminal:
```powershell
npx vite --config vite.mobile.config.ts
```
Opens at: **http://localhost:3001/mobile.html**

---

## How to Test

### Mobile App (Claimant Flow)
1. Open http://localhost:3001/mobile.html
2. Enter phone `6202234696` or email `krishnaanurag16@gmail.com`
3. If `OTP_PROVIDER=console`: the OTP will show on screen. If `email`: check your inbox
4. Enter the OTP → you're logged in
5. View your policy → Submit a Claim → upload a photo/video → record audio → submit
6. The AI detection runs in the background (~2 seconds)

### SIU Dashboard (Officer Flow)
1. Open http://localhost:3000/dashboard.html
2. Login with: `krishnaanurag16@gmail.com` / `shield@123`
3. **Claims Queue**: see submitted claims with fraud scores and AI analysis
4. **Lifecycle**: view the full claim flowchart from submission to decision
5. **Efficiency** (lead only): see officer workload distribution
6. **Reports**: download PDF reports
7. Click the AI Copilot tab on any claim to ask questions about the evidence

---

## API Endpoints (Key Ones)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server health check |
| `/auth/request-otp` | POST | Send OTP to phone/email |
| `/auth/verify-otp` | POST | Verify OTP, get session token |
| `/auth/dashboard-login` | POST | Officer login |
| `/claims` | POST | Submit a new claim (multipart) |
| `/claims/queue/all` | GET | All claims for dashboard |
| `/claims/report/{id}/pdf` | GET | Download AI analysis PDF |
| `/claims/{id}/copilot-chat` | POST | Ask AI about a claim |
| `/claims/{id}/moderator-approve` | POST | Approve a claim |
| `/claims/{id}/moderator-reject` | POST | Reject a claim |
| `/claims/{id}/siu-vote` | POST | Cast SIU vote |
| `/similarity/claim/{id}` | GET | Find similar claims |
| `/efficiency/officers` | GET | Officer workload stats |

Full API docs: http://localhost:8000/docs

---

## Officer Credentials (Demo)

| Name | Email | Password | Role |
|------|-------|----------|------|
| Krishna Anurag | krishnaanurag16@gmail.com | shield@123 | Lead (sees all tabs) |
| D. Torres | d.torres@syntheticshield.demo | demo123 | SIU Officer |
| R. Park | r.park@syntheticshield.demo | demo123 | SIU Officer |
| S. Okonkwo | s.okonkwo@syntheticshield.demo | demo123 | SIU Officer |
| M. Reyes | m.reyes@syntheticshield.demo | demo123 | SIU Officer |
| J. Chen | j.chen@syntheticshield.demo | demo123 | Moderator |

---

## Switching to Real Detection Providers

To use real AI detection instead of mock:

1. Get API keys from vendors (Reality Defender, Resemble AI, Truepic, GPTZero)
2. Update `backend/.env`:
   ```env
   VIDEO_DETECTION_PROVIDER=reality_defender
   REALITY_DEFENDER_API_KEY=your_key
   ```
3. Restart the backend — no code changes needed

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Cannot reach server" on mobile app | Make sure backend is running on port 8000 |
| OTP not received | Set `OTP_PROVIDER=console` to see codes on screen |
| SSL errors with pip | Use `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org` |
| Port already in use | Kill the process: `Get-Process -Name node,python | Stop-Process` |
| Database issues | Delete `claims.db` and re-run `python seed_data.py` |

---

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite, ChromaDB, ReportLab
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS, Recharts, Lucide Icons
- **Detection**: Mock providers (swappable to Reality Defender, Resemble AI, Truepic, GPTZero)
- **Notifications**: Resend (email), 2Factor.in (SMS)
