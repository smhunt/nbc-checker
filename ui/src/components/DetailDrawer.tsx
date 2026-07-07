import { useState } from 'react'
import type { CheckResult, FactUsed, Overrides, RuleMeta } from '../api'
import { StatusPill } from './StatusPill'

const CONFIDENCE_THRESHOLD = 0.9

interface Props {
  result: CheckResult
  ruleMeta: RuleMeta | undefined
  overrides: Overrides
  onOverride: (entityId: string, fact: string, value: string, note: string) => Promise<void>
  onDeleteOverride: (entityId: string, fact: string) => Promise<void>
  onClose: () => void
}

function OverrideForm({
  fact,
  entityId,
  onOverride,
}: {
  fact: FactUsed
  entityId: string
  onOverride: Props['onOverride']
}) {
  const [value, setValue] = useState(fact.present ? String(fact.value ?? '') : '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const why = fact.present
    ? `confidence ${fact.confidence?.toFixed(2)} < ${CONFIDENCE_THRESHOLD} — needs human review`
    : 'not found in extracted model — reviewer must supply a value'

  const submit = async () => {
    setBusy(true)
    try {
      await onOverride(entityId, fact.fact, value, note)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="override-row">
      <div className="fact-name">{fact.fact}</div>
      <div className="why">{why}</div>
      <div className="inputs">
        <input
          className="value-input"
          placeholder="value"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <input
          placeholder="review note (e.g. confirmed on site)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button className="btn primary" disabled={busy || value === ''} onClick={submit}>
          Confirm as reviewed
        </button>
      </div>
    </div>
  )
}

export function DetailDrawer({
  result,
  ruleMeta,
  overrides,
  onOverride,
  onDeleteOverride,
  onClose,
}: Props) {
  const notes = ruleMeta?.verification_notes
  const entityOverrides = overrides[result.entity_id] ?? {}

  // Facts the reviewer can act on: low-confidence or absent, deduplicated
  const reviewable = result.facts_used.filter(
    (f, i, arr) =>
      (!f.present || (f.confidence !== null && f.confidence < CONFIDENCE_THRESHOLD)) &&
      arr.findIndex((g) => g.fact === f.fact) === i,
  )

  return (
    <aside className="detail-drawer">
      <button className="close-btn" onClick={onClose} title="Close">
        ✕
      </button>
      <h2>
        {result.title} <StatusPill status={result.status} />
      </h2>
      <div className="provision mono">
        {result.rule_id} · {result.provision}
      </div>
      <div className="provision">
        Entity: <strong>{result.entity_name}</strong>{' '}
        <span className="mono">({result.entity_id})</span>
      </div>
      <p className="detail-text">{result.detail}</p>

      {notes?.quote && (
        <>
          <h3>Code text</h3>
          <blockquote className="code-quote">
            <span className="caption">NBC 2020 text</span>
            {notes.quote}
          </blockquote>
          {notes.sources && notes.sources.length > 0 && (
            <ul className="sources-list">
              {notes.sources.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {result.facts_used.length > 0 && (
        <>
          <h3>Facts used</h3>
          <table className="facts-table">
            <thead>
              <tr>
                <th>Fact</th>
                <th>Value</th>
                <th>Conf.</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {result.facts_used.map((f, i) => {
                const low = f.confidence !== null && f.confidence < CONFIDENCE_THRESHOLD
                return (
                  <tr key={`${f.fact}-${i}`}>
                    <td className="mono">{f.fact}</td>
                    <td className="mono">{f.present ? String(f.value) : '—'}</td>
                    <td className={`mono${low ? ' low-confidence' : ''}`}>
                      {f.confidence !== null && f.present ? f.confidence.toFixed(2) : '—'}
                    </td>
                    <td className="source-cell">{f.source ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}

      {result.comparisons.length > 0 && (
        <>
          <h3>Comparisons</h3>
          <ul className="comparisons-list">
            {result.comparisons.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Reviewer override</h3>
      {reviewable.length === 0 && Object.keys(entityOverrides).length === 0 && (
        <p className="empty-note">
          No facts on this check need review — every fact is present at confidence ≥{' '}
          {CONFIDENCE_THRESHOLD}.
        </p>
      )}
      {reviewable.map((f) => (
        <OverrideForm key={f.fact} fact={f} entityId={result.entity_id} onOverride={onOverride} />
      ))}

      {Object.keys(entityOverrides).length > 0 && (
        <>
          <h3>Active overrides for this entity</h3>
          {Object.entries(entityOverrides).map(([fact, o]) => (
            <div className="existing-override" key={fact}>
              <span className="mono">
                {fact} = {String(o.value)}
              </span>
              <span className="src" title={o.source}>
                {o.source}
              </span>
              <button
                className="delete-btn"
                title="Remove override and re-run"
                onClick={() => onDeleteOverride(result.entity_id, fact)}
              >
                ×
              </button>
            </div>
          ))}
        </>
      )}
    </aside>
  )
}
