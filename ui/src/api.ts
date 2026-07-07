// Typed client for the review API. All report data originates in
// engine/checker.py — the UI never computes compliance itself.

export type CheckStatus = 'pass' | 'fail' | 'info_not_available' | 'uncertain'

export interface FactUsed {
  fact: string
  value: unknown
  confidence: number | null
  source: string | null
  present: boolean
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
