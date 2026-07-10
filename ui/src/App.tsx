import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CheckResult, CheckStatus, Job, State } from './api'
import {
  deleteJobOverride,
  deleteOverride,
  getState,
  postJobOverride,
  postOverride,
} from './api'
import { ChangelogModal, APP_VERSION } from './components/ChangelogModal'
import { DetailDrawer } from './components/DetailDrawer'
import { ResultsTable, resultKey } from './components/ResultsTable'
import { SummaryBar } from './components/SummaryBar'
import { UploadPanel } from './components/UploadPanel'

export default function App() {
  const [state, setState] = useState<State | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Set<CheckStatus>>(new Set())
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  // Fact name the drawer should auto-focus in the evidence viewer — set when
  // a row is opened via its ⌖ evidence affordance, cleared on plain row click.
  const [evidenceFocus, setEvidenceFocus] = useState<{ fact: string; nonce: number } | null>(null)
  const [showAbout, setShowAbout] = useState(false)

  const loadSample = useCallback(() => {
    getState()
      .then((s) => {
        setState(s)
        setJobId(null)
        setSource(null)
        setSelectedKey(null)
        setEvidenceFocus(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(loadSample, [loadSample])

  const showJob = useCallback((job: Job) => {
    if (!job.report) return
    setState({
      report: job.report,
      facts: job.facts!,
      overrides: job.overrides ?? {},
      rules: job.rules ?? {},
      report_sha256: job.report_sha256 ?? '',
    })
    setJobId(job.job_id)
    setSource(`${job.filename} · ${job.ruleset_key.toUpperCase()} · ${job.mode}`)
    setSelectedKey(null)
    setEvidenceFocus(null)
    setError(null)
  }, [])

  const toggleFilter = useCallback((status: CheckStatus) => {
    setFilters((prev) => {
      const next = new Set(prev)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }, [])

  const results = state?.report.results ?? []
  const filtered = useMemo(
    () => (filters.size === 0 ? results : results.filter((r) => filters.has(r.status))),
    [results, filters],
  )

  const selected: CheckResult | null =
    (selectedKey && results.find((r) => resultKey(r) === selectedKey)) || null

  const handleOverride = useCallback(
    async (entityId: string, fact: string, value: string, note: string) => {
      try {
        const body = { entity_id: entityId, fact, value, note }
        setState(jobId ? await postJobOverride(jobId, body) as State : await postOverride(body))
        setError(null)
      } catch (e) {
        setError((e as Error).message)
      }
    },
    [jobId],
  )

  const handleDeleteOverride = useCallback(
    async (entityId: string, fact: string) => {
      try {
        setState(
          jobId
            ? (await deleteJobOverride(jobId, entityId, fact)) as State
            : await deleteOverride(entityId, fact),
        )
        setError(null)
      } catch (e) {
        setError((e as Error).message)
      }
    },
    [jobId],
  )

  if (error && !state) {
    return <div className="error-banner">Failed to load review state: {error}</div>
  }
  if (!state) {
    return <div className="loading">Loading compliance report…</div>
  }

  const { report } = state

  return (
    <>
      <header className="app-header">
        <h1>{report.project.name ?? 'Untitled project'}</h1>
        <span className="meta mono">{report.ruleset_id}</span>
        <span className="meta">{report.code_edition}</span>
        {source && (
          <button className="source-pill" onClick={loadSample} title="Back to the sample project">
            ← {source}
          </button>
        )}
        <span
          className="determinism-badge"
          title="identical inputs → identical report"
        >
          <span className="dot">●</span>
          {state.report_sha256.slice(0, 12)}
        </span>
      </header>

      <UploadPanel onResult={showJob} />

      <SummaryBar summary={report.summary} activeFilters={filters} onToggle={toggleFilter} />

      {error && <div className="error-banner">{error}</div>}

      <div className="main-split">
        <div className="table-pane">
          <ResultsTable
            results={filtered}
            selectedKey={selected ? resultKey(selected) : null}
            onSelect={(r) => {
              setSelectedKey(resultKey(r))
              setEvidenceFocus(null)
            }}
            onViewEvidence={(r) => {
              setSelectedKey(resultKey(r))
              const fact = r.facts_used.find((f) => f.evidence)?.fact
              setEvidenceFocus(fact ? { fact, nonce: Date.now() } : null)
            }}
          />
        </div>
        {selected && (
          <DetailDrawer
            result={selected}
            ruleMeta={state.rules[selected.rule_id]}
            overrides={state.overrides}
            jobId={jobId}
            initialEvidenceFocus={evidenceFocus ?? undefined}
            onOverride={handleOverride}
            onDeleteOverride={handleDeleteOverride}
            onClose={() => setSelectedKey(null)}
          />
        )}
      </div>

      <footer className="app-footer">
        <span>{report.engine.note}</span>
        <button className="about-btn" onClick={() => setShowAbout(true)}>
          About · v{APP_VERSION}
        </button>
      </footer>

      {showAbout && <ChangelogModal onClose={() => setShowAbout(false)} />}
    </>
  )
}
