// SyntheticShield demo recorder — drives mobile FNOL submission + dashboard walkthrough
// Produces: demo/videos/1-mobile-claim-submission.webm and 2-dashboard-walkthrough.webm
import { chromium } from 'playwright-core'
import { execSync } from 'node:child_process'
import { mkdirSync, readdirSync, renameSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const PY = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
const DB = path.join(ROOT, 'backend', 'claims.db')
const OUT = path.join(import.meta.dirname, 'videos')
mkdirSync(OUT, { recursive: true })

const EMAIL = 'krishnaanurag16@gmail.com'
const FIX = path.join(ROOT, 'backend', 'app', 'media_store')
const VIDEO_FILE = path.join(FIX, 'CLM-2026-00007', 'clean.mp4')
const IMAGE_FILE = path.join(FIX, 'CLM-2026-00007', 'driving-with-a-damaged-bumper-think-again-scaled.jpg')

const sql = q => execSync(
  `"${PY}" -c "import sqlite3,sys; c=sqlite3.connect(r'${DB}'); print(c.execute(sys.argv[1]).fetchone() or '')" "${q}"`,
  { encoding: 'utf8' }
).trim()

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function launch() {
  return chromium.launch({
    channel: 'msedge',
    headless: true, // headless recording matches the viewport exactly (no window-size letterboxing)
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
}

// ────────────────────────────── Part 1: Mobile claim submission ──────────────────────────────
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

  // Login via email
  await page.click('button:has-text("Email Address")')
  await sleep(800)
  await page.fill('input[type="email"]', EMAIL)
  await sleep(800)
  await page.click('button:has-text("Send Verification Code")')
  await page.waitForSelector('text=Verify your identity', { timeout: 30000 })
  await sleep(1200)

  // Read the freshly issued OTP from the local DB
  const row = sql("SELECT code FROM otp_codes ORDER BY id DESC LIMIT 1")
  const otp = row.replace(/[^0-9]/g, '')
  console.log('OTP fetched:', otp)
  const boxes = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < 6; i++) {
    await boxes.nth(i).fill(otp[i])
    await sleep(220)
  }

  // Policy dashboard → start claim
  await page.waitForSelector('button:has-text("Submit a Claim")', { timeout: 30000 })
  await sleep(3000)
  await page.click('button:has-text("Submit a Claim")')
  await sleep(1500)

  // Step A — coverage details
  await page.selectOption('select', { index: 1 })
  await sleep(600)
  await page.fill('input[placeholder*="47 Main St"]', '221B Collins Street, Melbourne VIC')
  await sleep(600)
  await page.fill('textarea', 'Rear-ended at a traffic light on my way to work. The other vehicle fled the scene. Rear bumper and boot lid are damaged, brake lights broken.')
  await sleep(600)
  await page.fill('input[placeholder*="850"]', '1850')
  await sleep(1000)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step B — dashcam video
  await page.setInputFiles('input[accept="video/*"]', VIDEO_FILE)
  await page.waitForSelector('text=/selected|✓|uploaded/i', { timeout: 15000 }).catch(() => {})
  await sleep(2500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step C — damage photos
  await page.setInputFiles('input[accept="image/*"]', IMAGE_FILE)
  await sleep(2500)
  await page.click('button:has-text("Continue")')
  await sleep(1000)

  // Step D — voice statement (fake mic tone)
  const recBtn = page.locator('button[style*="50%"]').first()
  await recBtn.click()
  await sleep(6000) // record ~6s
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

  // Show the AI-verification screen for a few seconds
  await sleep(12000)
  await saveVideo(page, ctx, '1-mobile-claim-submission.webm')
}

// ────────────────────────────── Wait for AI pipeline ──────────────────────────────
async function waitForAnalysis() {
  console.log('Waiting for AI analysis to finish…')
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

// ────────────────────────────── Part 2: Dashboard walkthrough ──────────────────────────────
async function recordDashboard(browser) {
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1600, height: 900 } },
  })
  const page = await ctx.newPage()
  await page.goto('http://localhost:3000/')
  await page.waitForSelector('text=SIU Fraud Intelligence Platform', { timeout: 30000 })
  await sleep(2500)

  // Credentials are pre-filled — sign in
  await page.click('button:has-text("Sign In")')
  await page.waitForSelector('button:has-text("Claims Queue")', { timeout: 30000 })
  await sleep(4000)

  // ── Claims Queue: select newest claim, walk the right-panel sections ──
  const newest = page.locator('div:has-text("CLM-2026-")').locator('visible=true')
  await sleep(2000)
  // Findings section is default; scroll through the report
  await page.mouse.wheel(0, 350); await sleep(2500)
  await page.mouse.wheel(0, 350); await sleep(2500)
  await page.mouse.wheel(0, -700); await sleep(1500)

  const clickIf = async (sel, wait = 3500) => {
    const el = page.locator(sel).first()
    if (await el.count()) { await el.click().catch(() => {}); await sleep(wait) }
  }

  // Right-panel tabs: Findings → AI Copilot → Actions/Details
  await clickIf('button:has-text("AI Copilot")')
  // Ask the Copilot a question if the input is present
  const copilotInput = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"]').first()
  if (await copilotInput.count()) {
    await copilotInput.fill('Summarize the AI findings for this claim in two sentences.')
    await copilotInput.press('Enter')
    await sleep(14000)
    await page.mouse.wheel(0, 300); await sleep(2500)
  }
  await clickIf('button:has-text("Actions")')
  await clickIf('button:has-text("Details")')
  await clickIf('button:has-text("Findings")')

  // ── Other queue claims: click a couple of rows in the left list ──
  const rows = page.locator('div[style*="cursor: pointer"]:has-text("CLM-2026-")')
  const n = await rows.count()
  for (let i = 0; i < Math.min(n, 2); i++) { await rows.nth(i).click().catch(() => {}); await sleep(3000) }

  // ── Walk every top-level tab ──
  for (const tab of ['Analytics', 'Case Files', 'Lifecycle', 'Efficiency', 'Reports']) {
    const t = page.locator(`button:has-text("${tab}")`).first()
    if (!(await t.count())) continue
    await t.click().catch(() => {})
    await sleep(4000)
    await page.mouse.wheel(0, 400); await sleep(2500)
    await page.mouse.wheel(0, 400); await sleep(2500)
    await page.mouse.wheel(0, -800); await sleep(1500)
  }

  // Back to the queue for a closing shot
  await page.click('button:has-text("Claims Queue")').catch(() => {})
  await sleep(4000)
  await saveVideo(page, ctx, '2-dashboard-walkthrough.webm')
}

const browser = await launch()
try {
  if (!process.argv.includes('--dashboard-only')) {
    await recordMobile(browser)
    const resolved = await waitForAnalysis()
    console.log('Claim resolved as:', resolved)
  }
  if (!process.argv.includes('--mobile-only')) await recordDashboard(browser)
} finally {
  await browser.close()
}
console.log('DONE — videos in', OUT)
