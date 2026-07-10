// Typed client for the review API. All report data originates in
// engine/checker.py — the UI never computes compliance itself.

export type CheckStatus = 'pass' | 'fail' | 'info_not_available' | 'uncertain'

// Machine-usable provenance region for a fact extracted from a PDF drawing.
// bbox is [x0, y0, x1, y1] normalized 0-1, top-left origin, y-down (raster
// space — same convention as the server-rendered page PNGs). Absent bbox
// degrades to a page-level view; absent evidence degrades to source-string-only.
export interface Evidence {
  doc: string
  page: number
  bbox?: [number, number, number, number]
}

export interface FactUsed {
  fact: string
  value: unknown
  confidence: number | null
  source: string | null
  present: boolean
  evidence?: Evidence | null
}

export interface CheckResult {
  rule_id: string
  provision: string
  title: string
  entity_id: string
  entity_name: string
  status: CheckStatus
  detail: string
  facts_used: FactUsed[]
  comparisons: string[]
}

export interface Report {
  ruleset_id: string
  code_edition: string
  project: { name?: string; municipality?: string; sources?: string[] }
  summary: Record<CheckStatus, number>
  results: CheckResult[]
  engine: {
    deterministic: boolean
    confidence_threshold: number
    note: string
  }
}

export interface FactObject {
  value: unknown
  confidence?: number
  source?: string
  evidence?: Evidence | null
}

export interface Entity {
  entity_type: string
  id: string
  name: string
  attributes: Record<string, unknown | FactObject>
}

export interface Facts {
  project: Record<string, unknown>
  entities: Entity[]
}

export interface VerificationNotes {
  quote?: string
  sources?: string[]
  verified_date?: string
  reviewer?: string
  notes?: string
}

export interface RuleMeta {
  provision: string
  title: string
  verification_notes: VerificationNotes | null
}

export type Overrides = Record<string, Record<string, FactObject>>

export interface State {
  report: Report
  facts: Facts
  overrides: Overrides
  rules: Record<string, RuleMeta>
  report_sha256: string
}

export interface OverrideBody {
  entity_id: string
  fact: string
  value: unknown
  note: string
}

// URL of the server-rendered PNG for the page an evidence region points at.
// Job PDFs are addressed by job id; sample/pre-loaded documents by basename.
export function pageImageUrl(jobId: string | null, ev: Evidence, dpi = 150): string {
  return jobId
    ? `/api/jobs/${encodeURIComponent(jobId)}/page/${ev.page}.png?dpi=${dpi}`
    : `/api/documents/${encodeURIComponent(ev.doc)}/page/${ev.page}.png?dpi=${dpi}`
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function getState(): Promise<State> {
  return request<State>('/api/state')
}

export function postOverride(body: OverrideBody): Promise<State> {
  return request<State>('/api/override', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteOverride(entityId: string, fact: string): Promise<State> {
  return request<State>(
    `/api/override/${encodeURIComponent(entityId)}/${encodeURIComponent(fact)}`,
    { method: 'DELETE' },
  )
}

// --- Upload your own PDF plan ---

export type JobStatus = 'extracting' | 'checking' | 'done' | 'error'

export interface Job extends Partial<State> {
  job_id: string
  filename: string
  ruleset_key: string
  mode: string
  status: JobStatus
  message: string
  error: string | null
  // Verbose progress (server 0.6+). Optional so old-shape job responses
  // still typecheck — the UI falls back to the plain message display.
  stage?: string
  progress?: { done: number; total: number }
  elapsed_s?: number
  eta_s?: number | null
  // Page-selection summary (server 0.7+, tiled multi-page runs). Present
  // once extraction finishes; absent on old-shape job responses.
  pages?: { total: number; selected: number; skipped: number }
}

export async function uploadPlan(
  file: File,
  ruleset: 'nbc' | 'obc',
  mode: 'whole' | 'tiled',
  pages: string = 'auto',
): Promise<Job> {
  const form = new FormData()
  form.append('file', file)
  form.append('ruleset', ruleset)
  form.append('mode', mode)
  form.append('pages', pages)
  return request<Job>('/api/upload', { method: 'POST', body: form })
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`)
}

export function postJobOverride(jobId: string, body: OverrideBody): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteJobOverride(jobId: string, entityId: string, fact: string): Promise<Job> {
  return request<Job>(
    `/api/jobs/${encodeURIComponent(jobId)}/override/${encodeURIComponent(entityId)}/${encodeURIComponent(fact)}`,
    { method: 'DELETE' },
  )
}
