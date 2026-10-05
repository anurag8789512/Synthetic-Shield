// SyntheticShield fraud-path demo recorder — drives mobile FNOL submission (fraudulent evidence)
// then the SIU dashboard review of that flagged claim, and stitches both into ONE video.
// Produces: demo/videos/SyntheticShield-Fraud-Review-Demo.mp4
import { chromium } from 'playwright-core'
import { execSync } from 'node:child_process'
import { mkdirSync, renameSync, existsSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const PY = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
const DB = path.join(ROOT, 'backend', 'claims.db')
const OUT = path.join(import.meta.dirname, 'videos')
mkdirSync(OUT, { recursive: true })

const EMAIL = 'krishnaanurag16@gmail.com'
const FIX = path.join(ROOT, 'backend', 'app', 'media_store')
// fraud-test.mp4 is the one video fixture in the repo that reliably trips the
// video-deepfake detector (Reality Defender scores it ~95% synthetic). Paired here
// with an actual car-damage photo (not the mismatched landscape fixture) so the
// evidence shown on screen is coherent: a real damage photo + a video that gets
// legitimately flagged as synthetic — landing the claim in moderator_review.
const VIDEO_FILE = path.join(FIX, 'CLM-2026-00004', 'fraud-test.mp4')
const IMAGE_FILE = path.join(FIX, 'CLM-2026-00007', 'driving-with-a-damaged-bumper-think-again-scaled.jpg')

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

// ────────────────────────────── Part 1: Mobile FNOL — fraudulent evidence ──────────────────────────────
async function recordMobile(browser) {
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

  const row = sql("SELECT code FROM otp_codes ORDER BY id DESC LIMIT 1")
  const otp = row.replace(/[^0-9]/g, '')
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
  await page.fill('input[placeholder*="47 Main St"]', '18 Riverside Drive, Austin TX')
  await sleep(600)
  await page.fill('textarea', 'Vehicle was hit while parked outside my office. Front bumper and headlight damaged. Attaching dashcam footage and photos as evidence.')
  await sleep(600)
  await page.fill('input[placeholder*="850"]', '4200')
  await sleep(1000)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step B — dashcam video (fraud fixture)
  await page.setInputFiles('input[accept="video/*"]', VIDEO_FILE)
  await page.waitForSelector('text=/selected|✓|uploaded/i', { timeout: 15000 }).catch(() => {})
  await sleep(2500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step C — damage photo (fraud fixture)
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

  // Step E — optional PDF: continue without document
  await page.click('button:has-text("Continue")')
  await sleep(1200)

  // Step F — review & submit
  await page.waitForSelector('text=Review your claim')
  await page.mouse.wheel(0, 400)
  await sleep(3000)
  await page.click('button:has-text("Submit Claim")')

  await sleep(12000)
  return saveVideo(page, ctx, 'part1-mobile-fraud-submission.webm')
}

// ────────────────────────────── Wait for AI pipeline ──────────────────────────────
async function waitForAnalysis() {
  console.log('Waiting for AI analysis to finish…')
  const before = sql("SELECT id FROM claims ORDER BY id DESC LIMIT 1")
  const deadline = Date.now() + 12 * 60 * 1000
  while (Date.now() < deadline) {
    const row = sql("SELECT claim_number || '|' || status FROM claims ORDER BY id DESC LIMIT 1")
    console.log('  latest claim:', row)
    if (row && !row.includes('processing')) return row
    await sleep(15000)
  }
  console.log('Timed out waiting — continuing with dashboard anyway.')
  return null
}

// ────────────────────────────── Part 2: Dashboard — claims officer reviews the flagged claim ──────────────────────────────
async function recordDashboard(browser, claimNumber) {
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1600, height: 900 } },
  })
  const page = await ctx.newPage()
  await page.goto('http://localhost:3000/')
  await page.waitForSelector('text=SIU Fraud Intelligence Platform', { timeout: 30000 })
  await sleep(2500)

  await page.click('button:has-text("Sign In")')
  await page.waitForSelector('button:has-text("Claims Queue")', { timeout: 30000 })
  await sleep(4000)

  // Select the newly submitted flagged claim explicitly (must click the actual
  // clickable queue-row div — a bare text= locator can match a non-interactive
  // child and silently no-op, leaving the previously-selected claim active).
  if (claimNumber) {
    const target = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber}")`).first()
    await target.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
    if (await target.count()) { await target.click(); await sleep(2500) }
    console.log('Selected claim row for', claimNumber, '-> found:', await target.count())
  }

  // Findings section — scroll through the fraud analysis report
  await page.mouse.wheel(0, 350); await sleep(2500)
  await page.mouse.wheel(0, 350); await sleep(2500)
  await page.mouse.wheel(0, -700); await sleep(1500)

  const clickIf = async (sel, wait = 3500) => {
    const el = page.locator(sel).first()
    if (await el.count()) { await el.click().catch(() => {}); await sleep(wait) }
  }

  // AI Copilot — ask about the flagged claim
  await clickIf('button:has-text("AI Copilot")')
  const copilotInput = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"]').first()
  if (await copilotInput.count()) {
    await copilotInput.fill('Why was this claim flagged for review? Summarize the fraud indicators.')
    await copilotInput.press('Enter')
    await sleep(14000)
    await page.mouse.wheel(0, 300); await sleep(2500)
  }

  // Actions — claims officer reviews and rejects the fraudulent claim
  await clickIf('button:has-text("Actions")', 2500)
  const rejectBtn = page.locator('button:has-text("Reject Claim")').first()
  if (await rejectBtn.count()) {
    await rejectBtn.click()
    await sleep(1500)
    const reasonInput = page.locator('textarea[placeholder*="rejection reason"]').first()
    if (await reasonInput.count()) {
      await reasonInput.fill('Dashcam footage and damage photo show manipulation artifacts consistent with synthetic/edited media. Escalating as confirmed fraud.')
      await sleep(1500)
    }
    const confirmBtn = page.locator('button:has-text("Confirm Rejection")').first()
    if (await confirmBtn.count()) {
      await confirmBtn.click()
      await sleep(3500)
    }
  }
  await clickIf('button:has-text("Findings")')

  // Other queue claims for context
  const rows = page.locator('div[style*="cursor: pointer"]:has-text("CLM-2026-")')
  const n = await rows.count()
  for (let i = 0; i < Math.min(n, 2); i++) { await rows.nth(i).click().catch(() => {}); await sleep(3000) }

  // Walk every top-level tab
  for (const tab of ['Analytics', 'Case Files', 'Lifecycle', 'Efficiency', 'Reports']) {
    const t = page.locator(`button:has-text("${tab}")`).first()
    if (!(await t.count())) continue
    await t.click().catch(() => {})
    await sleep(4000)
    await page.mouse.wheel(0, 400); await sleep(2500)
    await page.mouse.wheel(0, 400); await sleep(2500)
    await page.mouse.wheel(0, -800); await sleep(1500)
  }

  await page.click('button:has-text("Claims Queue")').catch(() => {})
  await sleep(4000)
  return saveVideo(page, ctx, 'part2-dashboard-fraud-review.webm')
}

const DASHBOARD_ONLY = process.argv.includes('--dashboard-only')
const FORCE_CLAIM = process.argv.find(a => a.startsWith('--claim='))?.split('=')[1]

const browser = await launch()
let mobileWebm, dashboardWebm, claimRow
try {
  if (DASHBOARD_ONLY) {
    mobileWebm = path.join(OUT, 'part1-mobile-fraud-submission.webm')
  } else {
    mobileWebm = await recordMobile(browser)
    claimRow = await waitForAnalysis()
    console.log('Claim resolved as:', claimRow)
  }
  // sql() prints Python's raw tuple repr (e.g. "('CLM-2026-00013|moderator_review',)"),
  // so pull the claim number out with a pattern match instead of a naive split('|').
  const claimNumber = FORCE_CLAIM || claimRow?.match(/CLM-\d{4}-\d+/)?.[0] || null
  dashboardWebm = await recordDashboard(browser, claimNumber)
} finally {
  await browser.close()
}

// ────────────────────────────── Stitch into ONE final video ──────────────────────────────
console.log('Stitching final combined video…')
const mp4_1 = mobileWebm.replace('.webm', '.mp4')
const mp4_2 = dashboardWebm.replace('.webm', '.mp4')
const FINAL = path.join(OUT, 'SyntheticShield-Fraud-Review-Demo.mp4')
const CANVAS = '1600x900'

// Scale/pad the portrait mobile clip onto the same 1600x900 canvas as the dashboard clip,
// then concat both at matching resolution/fps/codec so ffmpeg concat is lossless-safe.
if (!(DASHBOARD_ONLY && existsSync(mp4_1))) {
  execSync(`ffmpeg -y -i "${mobileWebm}" -vf "scale=w=1600:h=900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" -c:v libx264 -pix_fmt yuv420p -an "${mp4_1}"`, { stdio: 'inherit' })
}
execSync(`ffmpeg -y -i "${dashboardWebm}" -vf "scale=${CANVAS},fps=30" -c:v libx264 -pix_fmt yuv420p -an "${mp4_2}"`, { stdio: 'inherit' })

const listFile = path.join(OUT, 'concat-list.txt')
const fs = await import('node:fs')
fs.writeFileSync(listFile, `file '${mp4_1.replace(/\\/g, '/')}'\nfile '${mp4_2.replace(/\\/g, '/')}'\n`)
execSync(`ffmpeg -y -f concat -safe 0 -i "${listFile}" -c copy "${FINAL}"`, { stdio: 'inherit' })

console.log('DONE — final combined video at', FINAL)
