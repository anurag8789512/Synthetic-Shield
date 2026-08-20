# SyntheticShield — Frontend Development Prompt (for Figma Make)

Paste everything below into Figma Make as your project brief. It covers two
separate applications, screen by screen, with the exact functional behavior
required. **Build UI only — use local mock/dummy state for everything. Do
not wire any real backend, database, or auth calls.** Structure data with
clearly separated mock arrays/objects so real API calls can be dropped in
later without restructuring components.

---

## 0. Project Overview

**Product:** SyntheticShield — an AI-powered deepfake detection system for
**motor insurance claims** (First Notice of Loss / FNOL). Scope for this
build is **motor insurance only** — no home, property, or other coverage
types.

**Two separate applications, two separate visual treatments:**

1. **FNOL Web App** — customer-facing, mobile-first, used by policyholders
   to log in and submit a claim.
2. **SIU Dashboard** — officer-facing, desktop-first, data-dense, used by
   claims moderators and SIU (Special Investigations Unit) investigators to
   review, moderate, and adjudicate claims.

---

## 1. Tech Stack & Global Requirements

- React + TypeScript, Vite-compatible
- Tailwind CSS v4 for styling
- `lucide-react` for icons
- `recharts` for charts (Analytics tab)
- Component-based: buttons, status pills/badges, cards, and form inputs
  should be built as reusable components, not one-off inline styles repeated
  per screen
- State: local React state (`useState`/`useEffect`) only — no Redux, no
  real API calls, no real WebSocket connections. Simulate async behavior
  (e.g. "scanning" delays) with `setTimeout`.
- All data (claims, policies, coverages, reports, analytics numbers) should
  be **mock arrays/objects living in clearly named constants at the top of
  each file** — not hardcoded inline in JSX — so they're easy to find and
  swap for real data later
- Responsive behavior:
  - FNOL Web App: **mobile-first**, should look and feel like a native
    mobile flow even in a browser (max content width, bottom-anchored
    primary actions, large tap targets)
  - SIU Dashboard: **desktop-first**, multi-column layout, data-dense,
    optimized for a claims officer's workstation, not mobile
- Accessibility: all form fields have visible labels, sufficient color
  contrast, and are keyboard-navigable

---

## 2. Design System

**Color palette** (carry this exact palette across both apps for brand
consistency):

| Token | Hex | Use |
|---|---|---|
| Primary background (dark) | `#0B0F17` | FNOL app background |
| Primary background (light) | `#F8FAFC` | SIU Dashboard background |
| Card surface (dark) | `rgba(255,255,255,0.04)` glass | FNOL app cards |
| Card surface (light) | `#FFFFFF` | SIU Dashboard cards |
| Primary accent | `#0284C7` (cyan-blue) | Buttons, links, active states |
| Secondary accent | `#2563EB` (blue) | Gradients, secondary emphasis |
| Risk — high / fraud | `#EF4444` (red) | SIU-flagged, critical risk |
| Risk — medium | `#F59E0B` (amber) | Manual review, pending |
| Risk — low / success | `#10B981` (green) | Auto-approved, cleared |
| Muted text | `#64748B` / `#94A3B8` | Secondary/caption text |
| Border (light) | `#E2E8F0` | SIU Dashboard borders |
| Border (dark) | `rgba(255,255,255,0.08)` | FNOL app borders |

**Typography:** Inter (or system-ui fallback) throughout. Headings bold,
body regular, monospace font for IDs/claim numbers (e.g. `CLM-2026-00042`).

**Component patterns to reuse:**
- **Status pills**: rounded, colored background at ~10% opacity of the
  status color, colored text/border to match (Approved = green,
  Moderator Review = amber, SIU Investigation = red, Processing = blue)
- **Cards**: rounded corners (~10-12px radius), subtle border, optional
  soft shadow on light backgrounds
- **Risk score badges**: colored by threshold — green under 15%, amber
  15-85%, red above 85% (this threshold logic matters — see Section 4)

---

## 3. Application 1 — FNOL Web App (Customer-Facing)

### Screen 1: Login
- Toggle or tab between "Phone Number" and "Email" input
- Single input field + "Send Code" primary button
- Clean, minimal, centered on screen, dark theme
- Mock behavior: any input proceeds to the OTP screen after a brief loading
  state on the button

### Screen 2: OTP Verification
- 6 individual digit-entry boxes (auto-advance focus between boxes)
- "Resend code" link with a 30-second countdown before it becomes active
- Back button to return to Screen 1
- Mock behavior: any 6-digit code proceeds to the Policy Dashboard after a
  brief loading state

### Screen 3: Policy Dashboard
This is the screen shown immediately after login. Show:
- Policyholder name and a policy status badge (Active/Lapsed)
- Policy number (monospace)
- Vehicle details (make/model/year)
- List of coverages on this policy (mock 2-3 motor coverages, e.g. "Own
  Damage", "Third-Party Liability", "Roadside Assistance Add-On")
- Renewal date
- A large, prominent **"Submit a Claim"** button — this is the primary CTA
  on this screen

### Screen 4: Claim Submission (multi-step flow)
Build this as a step-by-step flow (progress indicator at top showing
current step). Steps:

**Step A — Coverage & Incident Details**
- Dropdown/selector: "What would you like to claim under?" — populated
  from the policy's actual coverage list from Screen 3 (motor-only
  options: Own Damage, Third-Party Liability, Comprehensive, Add-ons)
- Text input: accident location
- Text area: brief description of what happened

**Step B — Video/Photo Evidence (mandatory)**
- Drag-and-drop or tap-to-upload zone for a video or photo of the damage
- Show upload progress state, then a success/preview state
- Cannot proceed without this

**Step C — Voice Statement (mandatory)**
- Record button (tap to start/stop recording)
- Waveform or timer animation while recording
- Playback control once recorded, with a "re-record" option
- Cannot proceed without this

**Step D — Supporting Document (optional)**
- Upload zone explicitly labeled "PDF only — optional"
- Clear visual distinction that this step can be skipped
- Reject/show an error state if a non-PDF file is dropped

**Step E — Review & Submit**
- Summary of everything entered/uploaded across steps A-D
- Final "Submit Claim" button

### Screen 5: AI Verification (processing state)
- Full-screen or card-based "Scanning Media for Authenticity..." state with
  a loading animation (pulsing shield icon, spinner, or similar)
- Mock behavior: after ~3-4 seconds, randomly transition to one of the
  three outcome screens below (for demo purposes, make this easy to force
  via a dev toggle or predictable mock logic)

### Screen 6: Outcome Screens (three variants)
- **Auto-Approved** (green theme): checkmark icon, "Claim Approved" message,
  claim number, amount released (mock value)
- **Manual Review** (amber theme): pending icon, "Under Moderator Review"
  message, claim number, explanation that a human will review shortly
- **SIU Flagged** (red theme): warning icon, "Claim Paused — Discrepancies
  Detected" message, claim number, note that an investigator will be in
  touch

### Screen 7: Claim Confirmation / Status
- Shows claim number prominently
- Current status badge
- "What happens next" explanation text
- Option to return to Policy Dashboard

---

## 4. Application 2 — SIU Dashboard (Officer-Facing)

### Global layout
- Top nav bar with 4 tabs: **Claims Queue | Analytics | Case Files |
  Reports** — active tab clearly highlighted
- Notification bell icon in the header showing an unread count badge,
  opens a dropdown listing recent new-claim notifications
- Search bar accessible from the header

### Tab 1: Claims Queue (default/landing tab)
Three-column layout:

**Left column — Claim list**
- Filterable by risk level (All / High / Medium / Low) and searchable by
  claimant name or claim ID
- Each row shows: claimant name, claim ID (monospace), a "LIVE" badge for
  real-time submissions vs. older ones, risk score badge (colored per the
  thresholds in Section 2), submission time
- Clicking a row selects it and updates the other two columns

**Center column — Media workspace**
- Video player with playback controls for the submitted damage video
- Audio player for the voice statement
- Photo gallery if multiple images were submitted
- Inline PDF viewer/preview for any supporting document
- This column should visually adapt based on what media types the selected
  claim actually has (don't show an audio player if there's no audio, etc.)

**Right column — Analysis & Actions**
- **Fraud confidence score**, shown prominently (large number/gauge),
  color-coded per threshold (green <15%, amber 15-85%, red >85%)
- **AI-generated explanation panel** — a list of specific findings the AI
  produced (e.g. "Inconsistent audio frequencies detected between 0:02 and
  0:05", "Frame-level artifacts detected around 0:11-0:14") — this is a
  distinct, clearly-labeled section, not just the score
- **AI Copilot chat panel** — a chat interface scoped to the currently
  selected claim, where the officer can type follow-up questions (e.g.
  "why was this flagged?") and see AI responses in a conversational thread;
  include a few pre-filled suggested questions as clickable chips
- **Moderator actions** (only shown for Moderator Review claims):
  - "Approve" button
  - "Reject" button — clicking opens a text field for the officer to enter
    a rejection reason before confirming
- **SIU quorum voting** (only shown for SIU-flagged claims, styled with a
  red accent/border to stand out): shows 4 officer slots, each with a
  Confirm Fraud / Clear vote toggle and an optional notes field; show
  overall tally (e.g. "2 of 4 votes cast")
- **Audit trail / activity timeline** — a chronological list of events on
  this claim (submitted, scanned, flagged, etc.) with timestamps

### Tab 2: Analytics
- Row of 4 KPI cards: Claims Processed, Estimated Fraud Prevented,
  Detection Accuracy, Average Processing Time — each with a value and a
  small up/down trend indicator
- A volume trend chart (area or line) showing total claims vs. flagged
  claims over the last ~8-14 days
- A donut/pie chart showing claim outcome distribution (Auto-Approved /
  Manual Review / SIU Investigation)
- A bar chart showing fraud signal breakdown by type (e.g. Video Deepfake,
  Voice Clone, Photo Manipulation, Document Forgery)

### Tab 3: Case Files
- Searchable list of investigation case files (search by case ID,
  claimant, or investigator name)
- Each row: case ID, claimant, assigned investigator, status badge, risk
  score
- Selecting a case opens a detail panel: claimant info, dates, assigned
  investigator, status, risk score, and investigator notes

### Tab 4: Reports
- List of generated reports with columns: report title, type (e.g.
  Investigation Summary, Fraud Pattern Analysis, Monthly Digest), date,
  status (Draft/Final), page count
- Filter dropdown by report type
- A "Download PDF" action button per row (can be non-functional/mock for
  now)

---

## 5. Functional Logic to Encode in the Mock Data/State

Even though nothing connects to a real backend yet, structure the mock
behavior to match this real logic, so it's a true representation of the
product and not just static screens:

- A claim's fraud score determines its status:
  **< 15% → Auto-Approved · 15-85% → Moderator Review · > 85% → SIU
  Investigation**
- Moderator Review claims can only be Approved or Rejected by a moderator
  (via the buttons in Section 4) — there's no auto-resolution
- SIU Investigation claims require all 4 officer votes before the case can
  be finalized as confirmed-fraud or cleared
- The claim submission flow (App 1) enforces: video/photo mandatory, audio
  mandatory, PDF optional — the "Submit" action should be disabled/blocked
  until both mandatory items are present

---

## 6. What NOT to Build Yet

- No real authentication, OTP delivery, or session handling — mock it
- No real database or API calls — use local state and mock data arrays
- No real file upload to any server — simulate the upload UI/UX only
- No real payment/payout processing
- No real email/SMS sending

This is a frontend-only pass. Backend wiring comes in a separate phase
after this UI is finalized.
