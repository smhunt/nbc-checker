import type { CheckResult } from '../api'
import { StatusPill } from './StatusPill'

export function resultKey(r: CheckResult): string {
  return `${r.rule_id}::${r.entity_id}`
}

interface Props {
  results: CheckResult[]
  selectedKey: string | null
  onSelect: (r: CheckResult) => void
}

export function ResultsTable({ results, selectedKey, onSelect }: Props) {
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
          </tr>
        ))}
      </tbody>
    </table>
  )
}
