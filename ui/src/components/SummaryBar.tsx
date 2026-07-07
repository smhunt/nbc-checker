import type { CheckStatus } from '../api'
import { STATUS_COLORS, STATUS_LABELS } from './StatusPill'

const ORDER: CheckStatus[] = ['pass', 'fail', 'info_not_available', 'uncertain']

interface Props {
  summary: Record<CheckStatus, number>
  activeFilters: Set<CheckStatus>
  onToggle: (status: CheckStatus) => void
}

export function SummaryBar({ summary, activeFilters, onToggle }: Props) {
  return (
    <div className="summary-bar">
      {ORDER.map((status) => (
        <button
          key={status}
          className={`summary-chip${activeFilters.has(status) ? ' active' : ''}`}
          onClick={() => onToggle(status)}
          title={`Toggle filter: ${STATUS_LABELS[status]}`}
        >
          <span className="swatch" style={{ background: STATUS_COLORS[status] }} />
          <span>{STATUS_LABELS[status]}</span>
          <span className="count">{summary[status] ?? 0}</span>
        </button>
      ))}
    </div>
  )
}
