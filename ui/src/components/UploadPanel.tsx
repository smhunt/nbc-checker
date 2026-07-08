import { useRef, useState } from 'react'
import type { Job } from '../api'
import { getJob, uploadPlan } from '../api'

interface Props {
  onResult: (job: Job) => void
}

// Upload a PDF plan, start extraction, and poll until the report is ready.
export function UploadPanel({ onResult }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [ruleset, setRuleset] = useState<'nbc' | 'obc'>('nbc')
  const [mode, setMode] = useState<'whole' | 'tiled'>('whole')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function analyze() {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setErr('Choose a PDF first.')
      return
    }
    setErr(null)
    setBusy(true)
    setMessage('Uploading…')
    try {
      let job = await uploadPlan(file, ruleset, mode)
      // Poll every 3s until done or error.
      while (job.status === 'extracting' || job.status === 'checking') {
        setMessage(job.message)
        await new Promise((r) => setTimeout(r, 3000))
        job = await getJob(job.job_id)
      }
      if (job.status === 'error') {
        setErr(job.error ?? 'Extraction failed.')
      } else {
        setMessage(job.message)
        onResult(job)
      }
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
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
      <button onClick={analyze} disabled={busy}>
        {busy ? 'Analyzing…' : 'Analyze plan'}
      </button>
      {message && <span className="upload-msg">{message}</span>}
      {err && <span className="upload-err">{err}</span>}
    </div>
  )
}
