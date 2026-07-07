import { useState } from 'react'

export const APP_VERSION = '0.5.0'

export const CHANGELOG = [
  {
    version: '0.5.0',
    date: '2026-07-07',
    changes: [
      'Ontario OBC 2024 ruleset variant — correct jurisdiction, documents every OBC-vs-NBC difference',
      'High-DPI tiled PDF extraction — ~6× more facts from real permit sheets, confidence cap preserved',
      'Renovation scoping (new-work-only) skips existing-to-remain elements',
      'Case study: a real Ontario permit drawing run end to end',
    ],
  },
  {
    version: '0.4.0',
    date: '2026-07-07',
    changes: [
      'Human-review web UI: results table, detail drawer, override workflow',
      'FastAPI review service with persisted overrides and deterministic re-run',
      'Determinism badge — report SHA-256 proves identical inputs give identical reports',
    ],
  },
  {
    version: '0.3.0',
    date: '2026-07-07',
    changes: [
      'T1-T3 pipeline: expanded ruleset, IFC extractor hardening, fact-to-fact comparisons',
      'Pytest regression suite locking the four-status engine contract',
    ],
  },
  {
    version: '0.2.0',
    date: '2026-07-07',
    changes: [
      'V1 verification: all rules checked against published NBC 2020 text',
      'verification_notes with verbatim code quotes and sources on every rule',
    ],
  },
  {
    version: '0.1.0',
    date: '2026-07-07',
    changes: [
      'Scaffold: deterministic rule engine, NBC 2020 Part 9 core ruleset',
      'IFC extractor and sample dwelling facts',
    ],
  },
]

export const ROADMAP = [
  {
    category: 'In Progress',
    icon: '🚧',
    items: [
      'Verify Ontario OBC rules against machine-readable e-Laws text (4 still unverified)',
      'Tag OBC rules with new-work-only scope for change-of-use projects',
    ],
  },
  {
    category: 'Planned',
    icon: '📋',
    items: [
      'BCF export',
      'Partial-area / sloped-ceiling evaluation',
      'Vendor-pset mapping + multilingual room-use for real IFC exports',
      'Municipal pilot with real permit sets',
    ],
  },
]

export const HOW_IT_WORKS = [
  {
    title: 'Extract',
    description:
      'Facts are pulled from the BIM model (IFC, deterministic, confidence 1.0) and from PDF drawings (LLM-assisted, always confidence < 1.0). Every fact cites its source.',
    icon: '📐',
  },
  {
    title: 'Check',
    description:
      'A deterministic rule engine compares facts against machine-readable NBC 2020 Part 9 rules. No AI participates in pass/fail judgment — same inputs, same report, every time.',
    icon: '⚖️',
  },
  {
    title: 'Review',
    description:
      'Checks land in one of four statuses. UNCERTAIN and INFO N/A checks are routed here: a human reviewer confirms or corrects the underlying fact and records a note.',
    icon: '🧑‍💼',
  },
  {
    title: 'Re-run',
    description:
      'Confirmed facts are applied as overrides (confidence 1.0, source "human review") and the engine re-runs deterministically. The report hash updates to prove the new result.',
    icon: '🔁',
  },
]

type Tab = 'changelog' | 'how' | 'roadmap'

export function ChangelogModal({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('changelog')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>NBC Checker</h2>
          <span className="version">v{APP_VERSION}</span>
          <button className="close-btn" onClick={onClose} title="Close">
            ✕
          </button>
        </div>
        <div className="modal-tabs">
          <button className={tab === 'changelog' ? 'active' : ''} onClick={() => setTab('changelog')}>
            Changelog
          </button>
          <button className={tab === 'how' ? 'active' : ''} onClick={() => setTab('how')}>
            How It Works
          </button>
          <button className={tab === 'roadmap' ? 'active' : ''} onClick={() => setTab('roadmap')}>
            Roadmap
          </button>
        </div>
        <div className="modal-body">
          {tab === 'changelog' &&
            CHANGELOG.map((entry) => (
              <div key={entry.version}>
                <h4>
                  v{entry.version} <span className="mono">({entry.date})</span>
                </h4>
                <ul>
                  {entry.changes.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            ))}
          {tab === 'how' &&
            HOW_IT_WORKS.map((step, i) => (
              <div className="how-step" key={step.title}>
                <span className="icon">{step.icon}</span>
                <div>
                  <strong>
                    {i + 1}. {step.title}
                  </strong>
                  <div className="desc">{step.description}</div>
                </div>
              </div>
            ))}
          {tab === 'roadmap' &&
            ROADMAP.map((group) => (
              <div key={group.category}>
                <h4>
                  {group.icon} {group.category}
                </h4>
                <ul>
                  {group.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}
