import type { CheckStatus } from '../api'

export const STATUS_COLORS: Record<CheckStatus, string> = {
  pass: '#16a34a',
  fail: '#dc2626',
  info_not_available: '#6b7280',
  uncertain: '#d97706',
}

export const STATUS_LABELS: Record<CheckStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  info_not_available: 'INFO N/A',
  uncertain: 'UNCERTAIN',
}

export function StatusPill({ status }: { status: CheckStatus }) {
  return (
    <span className="status-pill" style={{ background: STATUS_COLORS[status] }}>
      {STATUS_LABELS[status]}
    </span>
  )
}
