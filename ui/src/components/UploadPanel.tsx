import { useEffect, useRef, useState } from 'react'
import type { Job } from '../api'
import { getJob, uploadPlan } from '../api'

interface Props {
  onResult: (job: Job) => void
  // Progressive streaming (server 0.8+): called with every polled job that
  // carries a page-barrier partial report, so the caller can show it while
  // extraction is still running. Optional/additive — omitting it keeps the
  // existing progress-only display unchanged.
  onPartial?: (job: Job) => void
}

// m:ss, e.g. 83.4 → "1:23".
function formatElapsed(s: number): string {
  const clamped = Math.max(0, Math.floor(s))
  return `${Math.floor(clamped / 60)}:${String(clamped % 60).padStart(2, '0')}`
}

// "~Ns remaining" — 5 s granularity once past 30 s so the number doesn't churn.
function formatEta(s: number): string {
  const n = s > 30 ? Math.round(s / 5) * 5 : Math.max(1, Math.round(s))
  return `~${n}s remaining`
}

// Upload a PDF plan, start extraction, and poll until the report is ready.
export function UploadPanel({ onResult, onPartial }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [ruleset, setRuleset] = useState<'nbc' | 'obc'>('nbc')
  const [mode, setMode] = useState<'whole' | 'tiled'>('whole')
  const [pages, setPages] = useState('auto')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // Page-selection summary from the finished job (server 0.7+), kept after
  // polling state is cleared so it can render next to the done message.
  const [donePages, setDonePages] = useState<Job['pages'] | null>(null)
  // Latest polled job + when it arrived, so elapsed/ETA can tick locally
  // between polls. Null when idle or when the server sends old-shape jobs.
  const [polled, setPolled] = useState<{ job: Job; at: number } | null>(null)
  const [now, setNow] = useState(() => Date.now())

  // 1 s tick while a job runs: elapsed counts up, ETA counts down.
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [busy])

  async function analyze() {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setErr('Choose a PDF first.')
      return
    }
    setErr(null)
    setBusy(true)
    setMessage('Uploading…')
    setPolled(null)
    setDonePages(null)
    try {
      // Backend rejects a malformed pages spec with a 400, which request()
      // turns into a thrown Error → the catch below shows it in upload-err.
      let job = await uploadPlan(file, ruleset, mode, pages.trim() || 'auto')
      setPolled({ job, at: Date.now() })
      setNow(Date.now())
      // Poll every 3s until done or error.
      while (job.status === 'extracting' || job.status === 'checking') {
        setMessage(job.message)
        await new Promise((r) => setTimeout(r, 3000))
        job = await getJob(job.job_id)
        setPolled({ job, at: Date.now() })
        if (job.partial && job.report) onPartial?.(job)
      }
      if (job.status === 'error') {
        setErr(job.error ?? 'Extraction failed.')
      } else {
        setMessage(job.message)
        setDonePages(job.pages ?? null)
        onResult(job)
      }
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
      setPolled(null)
    }
  }

  // Verbose stage display — only when the server sends the new fields;
  // old-shape jobs fall back to the plain message span below.
  let progressBlock = null
  if (busy && polled && polled.job.stage) {
    const { job, at } = polled
    const sincePoll = Math.max(0, (now - at) / 1000)
    const elapsed = (job.elapsed_s ?? 0) + sincePoll
    const done = job.progress?.done ?? 0
    const total = job.progress?.total ?? 0
    const remaining = job.eta_s == null ? null : job.eta_s - sincePoll
    progressBlock = (
      <div className="upload-progress">
        <div className="stage-row">
          <span className="stage-text">{job.stage}</span>
          {total > 0 && (
            <span className="tile-count mono">
              tile {done} of {total}
            </span>
          )}
        </div>
        {total > 0 && (
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${Math.min(100, (done / total) * 100)}%` }}
            />
          </div>
        )}
        <div className="progress-timing mono">
          <span>{formatElapsed(elapsed)} elapsed</span>
          {/* null eta_s = server has no basis for a number (last unit past
              budget) — show "finishing up…" until a poll brings a number back. */}
          <span>
            {remaining !== null && remaining > 0 ? formatEta(remaining) : 'finishing up…'}
          </span>
        </div>
        {job.message && <span className="upload-msg">{job.message}</span>}
      </div>
    )
  }

  return (
    <div className="upload-panel">
      <input ref={fileRef} type="file" accept="application/pdf,.pdf" disabled={busy} />
      <label>
        Code&nbsp;
        <select value={ruleset} onChange={(e) => setRuleset(e.target.value as 'nbc' | 'obc')} disabled={busy}>
          <option value="nbc">NBC 2020</option>
          <option value="obc">Ontario OBC 2024</option>
        </select>
      </label>
      <label>
        Extraction&nbsp;
        <select value={mode} onChange={(e) => setMode(e.target.value as 'whole' | 'tiled')} disabled={busy}>
          <option value="whole">Fast (one pass)</option>
          <option value="tiled">Thorough (tiled, slower)</option>
        </select>
      </label>
      <label title="Tiled mode: which pages to extract. auto = drawing pages only.">
        Pages&nbsp;
        <input
          className="pages-input"
          type="text"
          value={pages}
          onChange={(e) => setPages(e.target.value)}
          placeholder="auto | all | 1,3-5"
          disabled={busy}
        />
      </label>
      <button onClick={analyze} disabled={busy}>
        {busy ? 'Analyzing…' : 'Analyze plan'}
      </button>
      {progressBlock}
      {!progressBlock && message && <span className="upload-msg">{message}</span>}
      {!progressBlock && donePages && (
        <span className="upload-msg">
          processed {donePages.selected} of {donePages.total} pages
          {donePages.skipped ? ` — ${donePages.skipped} skipped (see report metadata)` : ''}
        </span>
      )}
      {err && <span className="upload-err">{err}</span>}
    </div>
  )
}
