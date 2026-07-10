import type { CheckResult } from '../api'
import { StatusPill } from './StatusPill'

export function resultKey(r: CheckResult): string {
  return `${r.rule_id}::${r.entity_id}`
}

interface Props {
  results: CheckResult[]
  selectedKey: string | null
  onSelect: (r: CheckResult) => void
  // Open the drawer for this row with its first evidence-carrying fact
  // already focused in the drawing viewer.
  onViewEvidence: (r: CheckResult) => void
}

// Only PDF-extracted facts (and overrides of them) carry evidence regions —
// IFC- and JSON-sourced facts have none, so their rows get no view affordance.
function hasEvidence(r: CheckResult): boolean {
  return r.facts_used.some((f) => f.evidence)
}

export function ResultsTable({ results, selectedKey, onSelect, onViewEvidence }: Props) {
  if (results.length === 0) {
    return <p className="empty-note">No checks match the current filter.</p>
  }
  return (
    <table className="results-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>Rule</th>
          <th>Title</th>
          <th>Provision</th>
          <th>Entity</th>
          <th>Detail</th>
          <th className="evidence-col" aria-label="Evidence" />
        </tr>
      </thead>
      <tbody>
        {results.map((r) => (
          <tr
            key={resultKey(r)}
            className={selectedKey === resultKey(r) ? 'selected' : ''}
            onClick={() => onSelect(r)}
          >
            <td>
              <StatusPill status={r.status} />
            </td>
            <td className="mono">{r.rule_id}</td>
            <td>{r.title}</td>
            <td className="mono">{r.provision}</td>
            <td>{r.entity_name}</td>
            <td className="detail-cell" title={r.detail}>
              {r.detail}
            </td>
            <td className="evidence-cell">
              {hasEvidence(r) && (
                <button
                  className="evidence-btn"
                  title="View evidence on the drawing"
                  onClick={(e) => {
                    e.stopPropagation()
                    onViewEvidence(r)
                  }}
                >
                  ⌖
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
