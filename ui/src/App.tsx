import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CheckResult, CheckStatus, State } from './api'
import { deleteOverride, getState, postOverride } from './api'
import { ChangelogModal, APP_VERSION } from './components/ChangelogModal'
import { DetailDrawer } from './components/DetailDrawer'
import { ResultsTable, resultKey } from './components/ResultsTable'
import { SummaryBar } from './components/SummaryBar'

export default function App() {
  const [state, setState] = useState<State | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Set<CheckStatus>>(new Set())
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [showAbout, setShowAbout] = useState(false)

  useEffect(() => {
    getState()
      .then(setState)
      .catch((e: Error) => setError(e.message))
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
        setState(await postOverride({ entity_id: entityId, fact, value, note }))
        setError(null)
      } catch (e) {
        setError((e as Error).message)
      }
    },
    [],
  )

  const handleDeleteOverride = useCallback(async (entityId: string, fact: string) => {
    try {
      setState(await deleteOverride(entityId, fact))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

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
        <span
          className="determinism-badge"
          title="identical inputs → identical report"
        >
          <span className="dot">●</span>
          {state.report_sha256.slice(0, 12)}
        </span>
      </header>

      <SummaryBar summary={report.summary} activeFilters={filters} onToggle={toggleFilter} />

      {error && <div className="error-banner">{error}</div>}

      <div className="main-split">
        <div className="table-pane">
          <ResultsTable
            results={filtered}
            selectedKey={selected ? resultKey(selected) : null}
            onSelect={(r) => setSelectedKey(resultKey(r))}
          />
        </div>
        {selected && (
          <DetailDrawer
            result={selected}
            ruleMeta={state.rules[selected.rule_id]}
            overrides={state.overrides}
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
