// SyntheticShield two-case demo recorder.
// Case 1: fraudulent claim (FNOL) → moderator-review routing → full dashboard tour
//         with a 10s presenter pause on every tab.
// Case 2: genuine claim (FNOL) → auto-approved → payout shown on dashboard.
// Produces: demo/videos/SyntheticShield-Two-Case-Demo.mp4
import { chromium } from 'playwright-core'
import { execSync } from 'node:child_process'
import { mkdirSync, renameSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const PY = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
const DB = path.join(ROOT, 'backend', 'claims.db')
const OUT = path.join(import.meta.dirname, 'videos')
mkdirSync(OUT, { recursive: true })

const EMAIL = 'krishnaanurag16@gmail.com'
const FIX = path.join(ROOT, 'backend', 'app', 'media_store')
// Filenames carry the demo-mode routing triggers (fraud→review, clean→approve).
const FRAUD_VIDEO = path.join(FIX, 'CLM-2026-00001', 'fraud-test.mp4')
const CLEAN_VIDEO = path.join(FIX, 'CLM-2026-00010', 'clean.mp4')
const IMAGE_FILE = path.join(FIX, 'CLM-2026-00010', 'driving-with-a-damaged-bumper-think-again-scaled.jpg')

const PAUSE = 10000 // presenter explanation pause per dashboard tab

const sql = q => execSync(
  `"${PY}" -c "import sqlite3,sys; c=sqlite3.connect(r'${DB}'); print(c.execute(sys.argv[1]).fetchone() or '')" "${q}"`,
  { encoding: 'utf8' }
).trim()

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function launch() {
  return chromium.launch({
    channel: 'msedge',
    headless: true,
    args: [
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
      '--autoplay-policy=no-user-gesture-required',
    ],
  })
}

async function saveVideo(page, ctx, finalName) {
  const video = page.video()
  await ctx.close()
  const p = await video.path()
  renameSync(p, path.join(OUT, finalName))
  console.log('Saved', finalName)
  return path.join(OUT, finalName)
}

// ────────────────────── Mobile FNOL submission (shared for both cases) ──────────────────────
async function recordMobile(browser, { videoFile, location, description, amount, outName }) {
  const ctx = await browser.newContext({
    viewport: { width: 500, height: 950 },
    recordVideo: { dir: OUT, size: { width: 500, height: 950 } },
    permissions: ['microphone'],
  })
  const page = await ctx.newPage()
  await page.goto('http://localhost:3001/')
  await page.waitForSelector('text=SyntheticShield')
  await sleep(2500)

  await page.click('button:has-text("Email Address")')
  await sleep(800)
  await page.fill('input[type="email"]', EMAIL)
  await sleep(800)
  await page.click('button:has-text("Send Verification Code")')
  await page.waitForSelector('text=Verify your identity', { timeout: 30000 })
  await sleep(1200)

  const otp = sql("SELECT code FROM otp_codes ORDER BY id DESC LIMIT 1").replace(/[^0-9]/g, '')
  console.log('OTP fetched:', otp)
  const boxes = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < 6; i++) {
    await boxes.nth(i).fill(otp[i])
    await sleep(220)
  }

  await page.waitForSelector('button:has-text("Submit a Claim")', { timeout: 30000 })
  await sleep(3000)
  await page.click('button:has-text("Submit a Claim")')
  await sleep(1500)

  // Step A — coverage details
  await page.selectOption('select', { index: 1 })
  await sleep(600)
  await page.fill('input[placeholder*="47 Main St"]', location)
  await sleep(600)
  await page.fill('textarea', description)
  await sleep(600)
  await page.fill('input[placeholder*="850"]', amount)
  await sleep(1000)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step B — dashcam video
  await page.setInputFiles('input[accept="video/*"]', videoFile)
  await page.waitForSelector('text=/selected|✓|uploaded/i', { timeout: 15000 }).catch(() => {})
  await sleep(2500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step C — damage photo
  await page.setInputFiles('input[accept="image/*"]', IMAGE_FILE)
  await sleep(2500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step D — voice statement (fake mic tone)
  const recBtn = page.locator('button[style*="50%"]').first()
  await recBtn.click()
  await sleep(6000)
  await recBtn.click()
  await page.waitForSelector('text=Statement captured', { timeout: 15000 })
  await sleep(1500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step E — optional PDF: skip
  await page.click('button:has-text("Continue")')
  await sleep(1200)

  // Step F — review & submit
  await page.waitForSelector('text=Review your claim')
  await page.mouse.wheel(0, 400)
  await sleep(3000)
  await page.click('button:has-text("Submit Claim")')

  await sleep(12000)
  return saveVideo(page, ctx, outName)
}

// ────────────────────── Wait for AI pipeline to finish on the newest claim ──────────────────────
async function waitForAnalysis() {
  console.log('Waiting for AI analysis…')
  const deadline = Date.now() + 12 * 60 * 1000
  while (Date.now() < deadline) {
    const row = sql("SELECT claim_number || '|' || status FROM claims ORDER BY id DESC LIMIT 1")
    console.log('  latest claim:', row)
    if (row && !row.includes('processing')) return row.match(/CLM-\d{4}-\d+/)?.[0] || null
    await sleep(10000)
  }
  console.log('Timed out — continuing anyway.')
  return null
}

async function dashboardLogin(browser) {
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1600, height: 900 } },
  })
  const page = await ctx.newPage()
  await page.goto('http://localhost:3000/')
  await page.waitForSelector('text=SIU Fraud Intelligence Platform', { timeout: 30000 })
  await sleep(2000)
  await page.click('button:has-text("Sign In")')
  await page.waitForSelector('button:has-text("Claims Queue")', { timeout: 30000 })
  await sleep(4000)
  return { ctx, page }
}

async function selectQueueRow(page, claimNumber) {
  if (!claimNumber) return
  const target = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber}")`).first()
  await target.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
  if (await target.count()) { await target.click(); await sleep(2500) }
}

// Click a download link that opens in a new tab; close the popup after a beat.
async function clickDownload(page, ctx, locator) {
  const el = locator.first()
  if (!(await el.count())) return
  const popupPromise = ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null)
  await el.click().catch(() => {})
  await sleep(2500)
  const popup = await popupPromise
  if (popup) await popup.close().catch(() => {})
  await sleep(800)
}

// ────────────────────── Case 1 dashboard: flagged claim + full tab tour ──────────────────────
async function recordDashboardCase1(browser, claimNumber) {
  const { ctx, page } = await dashboardLogin(browser)

  // Header features: MCP dropdown + profile dropdown
  await page.click('button:has-text("MCP")').catch(() => {})
  await sleep(2500)
  await page.click('button:has-text("MCP")').catch(() => {})
  await sleep(800)
  await page.click('text=Krishna Anurag').catch(() => {})
  await sleep(2500)
  await page.keyboard.press('Escape').catch(() => {})
  await page.click('button:has-text("Claims Queue")').catch(() => {})
  await sleep(1200)

  // Flagged claim lands in the queue for moderator review
  await selectQueueRow(page, claimNumber)
  await page.mouse.wheel(0, 350); await sleep(3000)
  await page.mouse.wheel(0, 400); await sleep(3000) // score breakdown panel
  await page.mouse.wheel(0, -750); await sleep(1500)
  await sleep(PAUSE) // presenter: Claims Queue tab

  // AI Copilot tab — ask about the flagged claim
  await page.click('button:has-text("AI Copilot")').catch(() => {})
  await sleep(2000)
  const copilotInput = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"]').first()
  if (await copilotInput.count()) {
    await copilotInput.fill('Why was this claim flagged for review?')
    await copilotInput.press('Enter')
    await sleep(14000)
    await page.mouse.wheel(0, 300); await sleep(2500)
  }

  // Actions tab — moderator REJECTS the fraudulent claim
  await page.click('button:has-text("Actions")').catch(() => {})
  await sleep(2500)
  const rejectBtn = page.locator('button:has-text("Reject Claim")').first()
  if (await rejectBtn.count()) {
    await rejectBtn.click()
    await sleep(1500)
    const reason = page.locator('textarea[placeholder*="rejection reason"]').first()
    if (await reason.count()) {
      await reason.fill('Dashcam footage shows manipulation artifacts consistent with synthetic media. Evidence does not support the claimed loss.')
      await sleep(1800)
    }
    await page.click('button:has-text("Confirm Rejection")').catch(() => {})
    await sleep(4000)
  }

  // Moderator APPROVES another pending review claim (human acceptance path)
  const approveTarget = page.locator('div[style*="cursor: pointer"]:has-text("CLM-2026-00016")').first()
  if (await approveTarget.count()) {
    await approveTarget.click(); await sleep(2500)
    await page.click('button:has-text("Actions")').catch(() => {})
    await sleep(2000)
    const approveBtn = page.locator('button:has-text("Approve Claim")').first()
    if (await approveBtn.count()) {
      await approveBtn.click()
      await sleep(4500) // "Claim Approved" confirmation + payout trigger
    }
  }

  // ── Analytics ──
  await page.click('button:has-text("Analytics")').catch(() => {})
  await sleep(1500)
  await sleep(PAUSE)
  await page.mouse.wheel(0, 400); await sleep(2000)
  await page.mouse.wheel(0, -400); await sleep(1000)

  // ── Case Files: filters, accordion, export/download buttons ──
  await page.click('button:has-text("Case Files")').catch(() => {})
  await sleep(1500)
  for (const f of ['Approved', 'Rejected', 'SIU Outcome', 'All']) {
    await page.click(`button:has-text("${f}")`).catch(() => {})
    await sleep(1300)
  }
  const rejectedCase = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber.replace('CLM-', 'CASE-')}")`).first()
  if (await rejectedCase.count()) { await rejectedCase.click(); await sleep(1500) }
  await sleep(PAUSE)
  await page.mouse.wheel(0, 600); await sleep(2000)
  await page.mouse.wheel(0, 900); await sleep(2000) // audit trail + export buttons
  await clickDownload(page, ctx, page.locator('a:has-text("Export Case Summary")'))
  await clickDownload(page, ctx, page.locator('a:has-text("Full Forensic Audit PDF")'))
  await page.mouse.wheel(0, -1500); await sleep(1000)

  // ── Lifecycle ──
  await page.click('button:has-text("Lifecycle")').catch(() => {})
  await sleep(1500)
  await sleep(PAUSE)
  await page.mouse.wheel(0, 400); await sleep(2000)
  await page.mouse.wheel(0, -400); await sleep(1000)

  // ── Efficiency: senior Details dropdown + live reassignment ──
  await page.click('button:has-text("Efficiency")').catch(() => {})
  await sleep(1500)
  await page.mouse.wheel(0, 500); await sleep(1500) // officer performance table
  const details = page.locator('button:has-text("Details")').first()
  if (await details.count()) {
    await details.click().catch(() => {})
    await sleep(2500)
    const sel = page.locator('select').last()
    if (await sel.count()) {
      await sel.selectOption({ index: 1 }).catch(() => {})
      await sleep(1500)
      await page.click('button:has-text("Reassign")').catch(() => {})
      await sleep(3000) // workload refreshes live
    }
  }
  await sleep(PAUSE)

  // ── Reports: expand detail + both download buttons ──
  await page.click('button:has-text("Reports")').catch(() => {})
  await sleep(1500)
  const reportRow = page.locator('div[style*="cursor: pointer"]:has-text("RPT-")').first()
  if (await reportRow.count()) { await reportRow.click(); await sleep(1500) }
  await sleep(PAUSE)
  await page.mouse.wheel(0, 500); await sleep(1500)
  await clickDownload(page, ctx, page.locator('a:has-text("Download Report PDF")'))
  await page.mouse.wheel(0, -700); await sleep(800)
  await clickDownload(page, ctx, page.locator('a:has-text("Download")'))

  // Back to the queue
  await page.click('button:has-text("Claims Queue")').catch(() => {})
  await sleep(3000)
  return saveVideo(page, ctx, 'twocase-part2-dashboard-review.webm')
}

// ────────────────────── Case 2 dashboard: auto-approved claim + payout + review-done ──────────────────────
async function recordDashboardCase2(browser, claimNumber) {
  const { ctx, page } = await dashboardLogin(browser)

  await selectQueueRow(page, claimNumber)
  await page.mouse.wheel(0, 350); await sleep(3500) // payout complete panel
  await page.mouse.wheel(0, 400); await sleep(3500) // AI report + breakdown
  await page.mouse.wheel(0, -750); await sleep(2000)

  // Details tab (review-only) — officer acknowledges the auto-approved claim
  await page.click('button:has-text("Details")').catch(() => {})
  await sleep(3000)
  await page.mouse.wheel(0, 400); await sleep(2000)
  const reviewDone = page.locator('button:has-text("Review Done")').first()
  if (await reviewDone.count()) {
    await reviewDone.click()
    await sleep(7000) // queue poll removes the acknowledged claim
  }
  await page.mouse.wheel(0, -600); await sleep(2500) // queue without the claim

  // Show it arriving in Case Files as an auto-approved case
  await page.click('button:has-text("Case Files")').catch(() => {})
  await sleep(2500)
  await page.click('button:has-text("Approved")').catch(() => {})
  await sleep(1500)
  const row = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber.replace('CLM-', 'CASE-')}")`).first()
  if (await row.count()) { await row.click().catch(() => {}); await sleep(1500) }
  await page.mouse.wheel(0, 400); await sleep(3000)
  await page.mouse.wheel(0, 500); await sleep(3000)
  await clickDownload(page, ctx, page.locator('a:has-text("Export Case Summary")'))
  await sleep(2000)
  return saveVideo(page, ctx, 'twocase-part4-dashboard-approved.webm')
}

// ────────────────────── Run everything ──────────────────────
const browser = await launch()
let clips = []
try {
  console.log('── Case 1: fraudulent claim ──')
  const m1 = await recordMobile(browser, {
    videoFile: FRAUD_VIDEO,
    location: '18 Riverside Drive, Austin TX',
    description: 'Vehicle was hit while parked outside my office. Front bumper and headlight damaged. Attaching dashcam footage and photos as evidence.',
    amount: '4200',
    outName: 'twocase-part1-mobile-fraud.webm',
  })
  const fraudClaim = await waitForAnalysis()
  console.log('Case 1 claim:', fraudClaim)
  const d1 = await recordDashboardCase1(browser, fraudClaim)

  console.log('── Case 2: genuine claim ──')
  const m2 = await recordMobile(browser, {
    videoFile: CLEAN_VIDEO,
    location: 'MG Road & 5th Cross junction, Bengaluru',
    description: 'Rear-ended at a red light; the driver behind failed to brake. Cracked rear bumper and broken tail light. Other driver accepted fault and we exchanged details.',
    amount: '850',
    outName: 'twocase-part3-mobile-genuine.webm',
  })
  const genuineClaim = await waitForAnalysis()
  console.log('Case 2 claim:', genuineClaim)
  const d2 = await recordDashboardCase2(browser, genuineClaim)

  clips = [m1, d1, m2, d2]
} finally {
  await browser.close()
}

// ────────────────────── Stitch into ONE final video ──────────────────────
console.log('Stitching final video…')
const CANVAS = '1600x900'
const mp4s = []
for (const clip of clips) {
  const mp4 = clip.replace('.webm', '.mp4')
  const portrait = clip.includes('mobile')
  const vf = portrait
    ? `scale=w=1600:h=900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black,fps=30`
    : `scale=${CANVAS},fps=30`
  execSync(`ffmpeg -y -i "${clip}" -vf "${vf}" -c:v libx264 -pix_fmt yuv420p -an "${mp4}"`, { stdio: 'inherit' })
  mp4s.push(mp4)
}

const FINAL = path.join(OUT, 'SyntheticShield-Two-Case-Demo.mp4')
const listFile = path.join(OUT, 'concat-list.txt')
writeFileSync(listFile, mp4s.map(f => `file '${f.replace(/\\/g, '/')}'`).join('\n') + '\n')
execSync(`ffmpeg -y -f concat -safe 0 -i "${listFile}" -c copy "${FINAL}"`, { stdio: 'inherit' })
console.log('DONE — final video at', FINAL)
