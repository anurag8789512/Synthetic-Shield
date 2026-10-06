// SyntheticShield ~6-minute customer demo recorder (real scoring, no demo mode).
// Case 1: AI-generated evidence (Tests/*dupe*) via FNOL → SIU investigation →
//         3-of-5 majority vote confirms fraud → full platform tour, 10s presenter
//         pause at the end of every tab.
// Case 2: genuine evidence (Tests/*clean*) via FNOL → auto-approved → Review Done
//         → shown in Case Files.
// Produces: demo/videos/SyntheticShield-6min-Demo.mp4
import { chromium } from 'playwright-core'
import { execSync } from 'node:child_process'
import { mkdirSync, renameSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const PY = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
const DB = path.join(ROOT, 'backend', 'claims.db')
const OUT = path.join(import.meta.dirname, 'videos')
const TESTS = path.join(ROOT, 'Tests')
const ASSETS = path.join(import.meta.dirname, 'assets')
mkdirSync(OUT, { recursive: true })

const EMAIL = 'krishnaanurag16@gmail.com'
const PAUSE = 10000 // presenter explanation pause before leaving each tab

const sql = q => execSync(
  `"${PY}" -c "import sqlite3,sys; c=sqlite3.connect(r'${DB}'); print(c.execute(sys.argv[1]).fetchone() or '')" "${q}"`,
  { encoding: 'utf8' }
).trim()
const sleep = ms => new Promise(r => setTimeout(r, ms))

// Voice statement is fed to the browser as its microphone (TTS wav).
async function launch(voiceWav) {
  const args = ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required']
  if (voiceWav) args.push(`--use-file-for-fake-audio-capture=${voiceWav}`)
  return chromium.launch({ channel: 'msedge', headless: true, args })
}

async function saveVideo(page, ctx, finalName) {
  const video = page.video()
  await ctx.close()
  const p = await video.path()
  renameSync(p, path.join(OUT, finalName))
  console.log('Saved', finalName)
  return path.join(OUT, finalName)
}

const pad = n => String(n).padStart(2, '0')
function localDateTime(hoursAgo) {
  const d = new Date(Date.now() - hoursAgo * 3600 * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ────────────────────── Mobile FNOL submission ──────────────────────
async function recordMobile({ voiceWav, videoFile, imageFile, location, description, amount, outName }) {
  const browser = await launch(voiceWav)
  try {
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
    await sleep(700)
    await page.fill('input[type="email"]', EMAIL)
    await sleep(700)
    await page.click('button:has-text("Send Verification Code")')
    await page.waitForSelector('text=Verify your identity', { timeout: 30000 })
    await sleep(1200)
    const otp = sql('SELECT code FROM otp_codes ORDER BY id DESC LIMIT 1').replace(/[^0-9]/g, '')
    const boxes = page.locator('input[inputmode="numeric"]')
    for (let i = 0; i < 6; i++) { await boxes.nth(i).fill(otp[i]); await sleep(200) }

    await page.waitForSelector('button:has-text("Submit a Claim")', { timeout: 30000 })
    await sleep(2500)
    await page.click('button:has-text("Submit a Claim")')
    await sleep(1500)

    // Step A — claim details incl. incident time
    await page.selectOption('select', { index: 1 }); await sleep(500)
    await page.fill('input[placeholder*="47 Main St"]', location); await sleep(500)
    await page.fill('input[type="datetime-local"]', localDateTime(3)).catch(() => {}); await sleep(500)
    await page.fill('textarea', description); await sleep(500)
    await page.fill('input[placeholder*="850"]', amount); await sleep(1200)
    await page.click('button:has-text("Continue")'); await sleep(1000)

    // Step B — video
    await page.setInputFiles('input[accept="video/*"]', videoFile)
    await sleep(2800)
    await page.click('button:has-text("Continue")'); await sleep(1000)

    // Step C — photo
    await page.setInputFiles('input[accept="image/*"]', imageFile)
    await sleep(2800)
    await page.click('button:has-text("Continue")'); await sleep(1000)

    // Step D — live voice statement (TTS wav as the microphone)
    const recBtn = page.locator('button[style*="50%"]').first()
    await recBtn.click()
    await sleep(9000)
    await recBtn.click()
    await page.waitForSelector('text=Statement captured', { timeout: 15000 })
    await sleep(1500)
    await page.click('button:has-text("Continue")'); await sleep(1000)

    // Step E — optional PDF: skip
    await page.click('button:has-text("Continue")'); await sleep(1200)

    // Step F — review & submit
    await page.waitForSelector('text=Review your claim')
    await page.mouse.move(250, 600)
    await page.mouse.wheel(0, 400); await sleep(3000)
    await page.click('button:has-text("Submit Claim")')
    await sleep(10000) // AI verification screen
    return await saveVideo(page, ctx, outName)
  } finally {
    await browser.close()
  }
}

async function waitForAnalysis(afterId) {
  console.log('Waiting for AI analysis…')
  const deadline = Date.now() + 12 * 60 * 1000
  while (Date.now() < deadline) {
    const row = sql(`SELECT claim_number || '|' || status FROM claims WHERE id > ${afterId} ORDER BY id DESC LIMIT 1`)
    console.log('  newest claim:', row || '(not created yet)')
    if (row && !row.includes('processing')) {
      const [num, status] = row.replace(/[()',]/g, '').split('|')
      return { claimNumber: num.trim(), status: status.trim() }
    }
    await sleep(8000)
  }
  throw new Error('analysis timed out')
}

// ────────────────────── Dashboard helpers ──────────────────────
async function dashboardLogin(browser) {
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
  await sleep(3000)
  return { ctx, page }
}

const tab = async (page, name) => { await page.click(`button:has-text("${name}")`).catch(() => {}); await sleep(1800) }
const scroll = async (page, x, y, dy, wait = 2000) => { await page.mouse.move(x, y); await page.mouse.wheel(0, dy); await sleep(wait) }

async function selectQueueRow(page, claimNumber) {
  const search = page.locator('input[placeholder="Search…"]').first()
  if (await search.count()) { await search.fill(claimNumber); await sleep(1500) }
  const row = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber}")`).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
  await sleep(2500)
}

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

// ────────────────────── Case 1 dashboard: SIU vote + full tour ──────────────────────
async function recordDashboardFraud(claimNumber) {
  const browser = await launch()
  try {
    const { ctx, page } = await dashboardLogin(browser)

    // Header: notifications, MCP server menu, profile
    const bell = page.locator('button:has(svg.lucide-bell)').first()
    await bell.click().catch(() => {}); await sleep(3000)
    await bell.click().catch(() => {}); await sleep(800)
    await page.click('button:has-text("MCP")').catch(() => {}); await sleep(3500)
    await page.click('button:has-text("MCP")').catch(() => {}); await sleep(800)
    await page.click('text=Krishna Anurag').catch(() => {}); await sleep(2500)
    await page.mouse.click(800, 600); await sleep(800)

    // ── Claims Queue: the SIU claim, evidence, heatmap, findings + score breakdown ──
    await selectQueueRow(page, claimNumber)
    const heat = page.locator('button:has-text("Heatmap")').first()
    await heat.click().catch(() => {}); await sleep(2500)
    await heat.click().catch(() => {}); await sleep(1000)
    await scroll(page, 1350, 500, 350, 3000)
    await scroll(page, 1350, 500, 450, 3500)   // score breakdown by level
    await scroll(page, 1350, 500, 450, 3000)   // findings + audit trail
    await scroll(page, 1350, 500, -1250, 1500)
    await sleep(PAUSE)

    // ── AI Copilot ──
    await tab(page, 'AI Copilot')
    const ask = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"]').first()
    if (await ask.count()) {
      await ask.fill('Why was this claim sent to SIU investigation?')
      await sleep(800)
      await ask.press('Enter')
      await sleep(16000)
      await scroll(page, 1350, 500, 400, 2500)
    }
    await sleep(PAUSE)

    // ── SIU Vote: 3 of 5 confirm fraud → majority decision ──
    await tab(page, 'SIU Vote')
    const notes = [
      'Video and photo show AI-synthesis indicators (100/100).',
      'Voice says rear damage, written statement says front. Contradiction.',
      'Evidence matches earlier claims. Confirming fraud.',
    ]
    for (const note of notes) {
      const confirm = page.locator('button:has-text("Confirm Fraud")').first()
      if (!(await confirm.count())) break
      await confirm.click(); await sleep(1200)
      await page.locator('input[placeholder="Optional notes…"]').first().fill(note).catch(() => {})
      await sleep(1500)
      await page.locator('button:has-text("Cast Vote")').first().click().catch(() => {})
      await sleep(3000)
    }
    // The decided claim leaves the queue on the next poll, so go straight to its
    // Case File (SIU Outcome) and pause there rather than on the queue.
    await page.waitForSelector('text=Fraud Confirmed', { timeout: 15000 }).catch(() => {})
    await sleep(3000)

    // ── Case Files: the SIU-confirmed case, filters, exports ──
    await tab(page, 'Case Files')
    await page.click('button:has-text("SIU Outcome")').catch(() => {}); await sleep(1500)
    const caseRow = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber.replace('CLM-', 'CASE-')}")`).first()
    await caseRow.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
    if (await caseRow.count()) { await caseRow.click().catch(() => {}); await sleep(2500) }
    await scroll(page, 800, 500, 500, 2500)
    await scroll(page, 800, 500, 700, 2500)
    await clickDownload(page, ctx, page.locator('a:has-text("Export Case Summary")'))
    await clickDownload(page, ctx, page.locator('a:has-text("Full Forensic Audit PDF")'))
    await scroll(page, 800, 500, -1200, 1000)
    await sleep(PAUSE)
    for (const f of ['Approved', 'Rejected', 'All']) {
      await page.click(`button:has-text("${f}")`).catch(() => {}); await sleep(1400)
    }

    // ── Analytics ──
    await tab(page, 'Analytics')
    await scroll(page, 800, 500, 450, 3000)
    await scroll(page, 800, 500, -450, 1000)
    await sleep(PAUSE)

    // ── Lifecycle: this claim's end-to-end audit flow ──
    await tab(page, 'Lifecycle')
    const lc = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber}")`).first()
    if (await lc.count()) { await lc.click().catch(() => {}); await sleep(2000) }
    await scroll(page, 1000, 500, 500, 3000)
    await scroll(page, 1000, 500, -500, 1000)
    await sleep(PAUSE)

    // ── Efficiency: officer workload + senior reassignment ──
    await tab(page, 'Efficiency')
    await scroll(page, 800, 500, 500, 2000)
    const details = page.locator('button:has-text("Details")').first()
    if (await details.count()) {
      await details.click().catch(() => {}); await sleep(2500)
      const sel = page.locator('select').last()
      if (await sel.count()) {
        await sel.selectOption({ index: 1 }).catch(() => {}); await sleep(1500)
        await page.locator('button:has-text("Reassign")').last().click().catch(() => {}); await sleep(3000)
      }
    }
    await sleep(PAUSE)

    // ── Reports ──
    await tab(page, 'Reports')
    const rpt = page.locator('div[style*="cursor: pointer"]:has-text("RPT-")').first()
    if (await rpt.count()) { await rpt.click().catch(() => {}); await sleep(2000) }
    await scroll(page, 800, 500, 500, 2000)
    await clickDownload(page, ctx, page.locator('a:has-text("Download Report PDF")'))
    await scroll(page, 800, 500, -500, 1000)
    await sleep(PAUSE)

    await tab(page, 'Claims Queue')
    await sleep(2000)
    return await saveVideo(page, ctx, 'demo6-part2-dashboard-fraud.webm')
  } finally {
    await browser.close()
  }
}

// ────────────────────── Case 2 dashboard: auto-approved → Review Done → Case Files ──────────────────────
async function recordDashboardGenuine(claimNumber) {
  const browser = await launch()
  try {
    const { ctx, page } = await dashboardLogin(browser)
    await selectQueueRow(page, claimNumber)
    await scroll(page, 1350, 500, 350, 3500)   // payout panel
    await scroll(page, 1350, 500, 450, 3500)   // score breakdown
    await scroll(page, 1350, 500, -800, 1500)
    await sleep(4000)

    await tab(page, 'Details')
    await scroll(page, 1350, 500, 400, 2000)
    const done = page.locator('button:has-text("Review Done")').first()
    if (await done.count()) { await done.click(); await sleep(7000) }
    await page.locator('input[placeholder="Search…"]').first().fill('').catch(() => {})
    await sleep(3000) // queue no longer lists the claim

    await tab(page, 'Case Files')
    await page.click('button:has-text("Approved")').catch(() => {}); await sleep(1500)
    const row = page.locator(`div[style*="cursor: pointer"]:has-text("${claimNumber.replace('CLM-', 'CASE-')}")`).first()
    if (await row.count()) { await row.click().catch(() => {}); await sleep(2000) }
    await scroll(page, 800, 500, 450, 3500)
    await scroll(page, 800, 500, 500, 3500)
    await sleep(5000)
    return await saveVideo(page, ctx, 'demo6-part4-dashboard-genuine.webm')
  } finally {
    await browser.close()
  }
}

// ────────────────────── Run ──────────────────────
const lastId = () => Number(sql('SELECT COALESCE(MAX(id), 0) FROM claims').replace(/[^0-9]/g, '')) || 0

console.log('── Case 1: AI-generated evidence ──')
let before = lastId()
const m1 = await recordMobile({
  voiceWav: path.join(ASSETS, 'voice_fraud.wav'),
  videoFile: path.join(TESTS, 'car_crash_dupe.mp4'),
  imageFile: path.join(TESTS, 'car_accident_dupe.png'),
  location: '18 Riverside Drive, Austin TX',
  description: 'Vehicle was hit while parked outside my office. Front bumper and headlight damaged. Attaching dashcam footage and photos as evidence.',
  amount: '4200',
  outName: 'demo6-part1-mobile-fraud.webm',
})
const fraud = await waitForAnalysis(before)
console.log('Case 1:', fraud)
if (fraud.status !== 'siu_investigation') console.warn('!! expected siu_investigation, got', fraud.status)
const d1 = await recordDashboardFraud(fraud.claimNumber)

// --fraud-only: re-record case 1 and reuse the existing case 2 clips
let m2 = path.join(OUT, 'demo6-part3-mobile-genuine.webm')
let d2 = path.join(OUT, 'demo6-part4-dashboard-genuine.webm')
if (!process.argv.includes('--fraud-only')) {
  console.log('── Case 2: genuine evidence ──')
  before = lastId()
  m2 = await recordMobile({
    voiceWav: path.join(ASSETS, 'voice_genuine.wav'),
    videoFile: path.join(TESTS, 'car_accident_clean.mp4'),
    imageFile: path.join(TESTS, 'car_accident_clean.jpg'),
    location: 'MG Road & 5th Cross junction, Bengaluru',
    description: 'Rear-ended at a red light; the driver behind failed to brake. Cracked rear bumper and broken tail light. Other driver accepted fault and we exchanged details.',
    amount: '850',
    outName: 'demo6-part3-mobile-genuine.webm',
  })
  const genuine = await waitForAnalysis(before)
  console.log('Case 2:', genuine)
  if (genuine.status !== 'auto_approved') console.warn('!! expected auto_approved, got', genuine.status)
  d2 = await recordDashboardGenuine(genuine.claimNumber)
}

// ────────────────────── Stitch into one video ──────────────────────
console.log('Stitching…')
const mp4s = []
for (const clip of [m1, d1, m2, d2]) {
  const mp4 = clip.replace('.webm', '.mp4')
  const vf = clip.includes('mobile')
    ? 'scale=w=1600:h=900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black,fps=30'
    : 'scale=1600:900,fps=30'
  execSync(`ffmpeg -y -v error -i "${clip}" -vf "${vf}" -c:v libx264 -pix_fmt yuv420p -an "${mp4}"`, { stdio: 'inherit' })
  mp4s.push(mp4)
}
const FINAL = path.join(OUT, 'SyntheticShield-6min-Demo.mp4')
const list = path.join(OUT, 'demo6-concat.txt')
writeFileSync(list, mp4s.map(f => `file '${f.replace(/\\/g, '/')}'`).join('\n') + '\n')
execSync(`ffmpeg -y -v error -f concat -safe 0 -i "${list}" -c copy "${FINAL}"`, { stdio: 'inherit' })
const secs = Number(execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 "${FINAL}"`, { encoding: 'utf8' }))
console.log(`DONE — ${FINAL} (${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s)`)
