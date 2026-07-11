import { useEffect, useRef, useState } from 'react'
import type { CheckResult, Evidence, FactUsed, Overrides, RuleMeta } from '../api'
import { EvidenceViewer } from './EvidenceViewer'
import { StatusPill } from './StatusPill'

const CONFIDENCE_THRESHOLD = 0.9

// Drawer resize: width in px, dragged from the left edge, persisted per browser.
const DRAWER_WIDTH_KEY = 'nbc.drawerWidth'
const DEFAULT_DRAWER_WIDTH = 420
const MIN_DRAWER_WIDTH = 380

function clampDrawerWidth(w: number): number {
  return Math.min(Math.max(w, MIN_DRAWER_WIDTH), Math.round(window.innerWidth * 0.7))
}

function initialDrawerWidth(): number {
  const saved = Number(localStorage.getItem(DRAWER_WIDTH_KEY))
  return Number.isFinite(saved) && saved > 0 ? clampDrawerWidth(saved) : DEFAULT_DRAWER_WIDTH
}

interface Props {
  result: CheckResult
  ruleMeta: RuleMeta | undefined
  overrides: Overrides
  jobId: string | null
  // True while the report is a mid-extraction partial (progressive
  // streaming): the server already 404s override/export against a job that
  // has no `facts` yet (only `partial_facts`) — this is UX only, hiding the
  // override form in favour of an explanatory note instead of letting the
  // reviewer submit something the server will reject.
  readOnly?: boolean
  // Fact name to auto-focus in the evidence viewer when the drawer opens
  // (same effect as clicking that fact's ⌖ view button). Optional — absent
  // means the drawer opens with the viewer closed, as before.
  // nonce makes re-clicking the same row's ⌖ re-open the viewer even when
  // the fact name is unchanged (fresh object identity re-fires the effect).
  initialEvidenceFocus?: { fact: string; nonce: number }
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
  jobId,
  readOnly = false,
  initialEvidenceFocus,
  onOverride,
  onDeleteOverride,
  onClose,
}: Props) {
  const notes = ruleMeta?.verification_notes
  const entityOverrides = overrides[result.entity_id] ?? {}

  // Fact whose evidence region is open in the drawing viewer. When the row
  // was opened via its ⌖ evidence affordance, start with that fact focused.
  const [focused, setFocused] = useState<{ fact: string; evidence: Evidence } | null>(null)
  useEffect(() => {
    const f = initialEvidenceFocus
      ? result.facts_used.find((g) => g.fact === initialEvidenceFocus.fact && g.evidence)
      : undefined
    setFocused(f ? { fact: f.fact, evidence: f.evidence! } : null)
  }, [result, initialEvidenceFocus])

  // Drag-resizable width (pointer capture on the left-edge handle, same
  // pattern as EvidenceViewer's pan drag). Double-click resets to default.
  const [width, setWidth] = useState(initialDrawerWidth)
  const [resizing, setResizing] = useState(false)
  const resizeRef = useRef<{ x: number; w: number } | null>(null)

  useEffect(() => {
    if (!resizing) localStorage.setItem(DRAWER_WIDTH_KEY, String(width))
  }, [width, resizing])

  // Text stays unselectable body-wide while the handle is being dragged.
  useEffect(() => {
    if (!resizing) return
    document.body.classList.add('drawer-resizing')
    return () => document.body.classList.remove('drawer-resizing')
  }, [resizing])

  const onHandlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    resizeRef.current = { x: e.clientX, w: width }
    setResizing(true)
  }

  const onHandlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = resizeRef.current
    if (!d) return
    // Dragging left widens the drawer (it sits on the right side).
    setWidth(clampDrawerWidth(d.w + (d.x - e.clientX)))
  }

  const onHandlePointerUp = () => {
    resizeRef.current = null
    setResizing(false)
  }

  // All facts on this check with evidence on the same sheet+page as the
  // focused one (deduped by fact name) get highlight rectangles.
  const highlights = focused
    ? result.facts_used
        .filter(
          (f) =>
            f.evidence &&
            f.evidence.doc === focused.evidence.doc &&
            f.evidence.page === focused.evidence.page,
        )
        .filter((f, i, arr) => arr.findIndex((g) => g.fact === f.fact) === i)
        .map((f) => ({ fact: f.fact, evidence: f.evidence as Evidence }))
    : []

  // Facts the reviewer can act on: low-confidence or absent, deduplicated
  const reviewable = result.facts_used.filter(
    (f, i, arr) =>
      (!f.present || (f.confidence !== null && f.confidence < CONFIDENCE_THRESHOLD)) &&
      arr.findIndex((g) => g.fact === f.fact) === i,
  )

  return (
    <div className="drawer-shell" style={{ width }}>
      <div
        className={`drawer-resize-handle${resizing ? ' active' : ''}`}
        title="Drag to resize · double-click to reset"
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={onHandlePointerUp}
        onPointerCancel={onHandlePointerUp}
        onDoubleClick={() => setWidth(DEFAULT_DRAWER_WIDTH)}
      />
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
                    <td className="source-cell">
                      {f.source ?? '—'}
                      {f.evidence && (
                        <button
                          className={`evidence-btn${
                            focused?.fact === f.fact ? ' active' : ''
                          }`}
                          title="View this fact on the drawing"
                          onClick={() =>
                            setFocused({ fact: f.fact, evidence: f.evidence! })
                          }
                        >
                          ⌖ view
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {focused && (
            <>
              <h3>
                Evidence{' '}
                <span className="evidence-loc mono">
                  {focused.evidence.doc} · p.{focused.evidence.page}
                </span>
              </h3>
              <EvidenceViewer
                jobId={jobId}
                focus={focused.evidence}
                highlights={highlights}
                onClose={() => setFocused(null)}
              />
            </>
          )}
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
      {readOnly ? (
        <p className="empty-note">
          Extraction is still in progress for this plan — overrides and export unlock once the
          report is final.
        </p>
      ) : (
        <>
          {reviewable.length === 0 && Object.keys(entityOverrides).length === 0 && (
            <p className="empty-note">
              No facts on this check need review — every fact is present at confidence ≥{' '}
              {CONFIDENCE_THRESHOLD}.
            </p>
          )}
          {reviewable.map((f) => (
            <OverrideForm key={f.fact} fact={f} entityId={result.entity_id} onOverride={onOverride} />
          ))}
        </>
      )}

      {!readOnly && Object.keys(entityOverrides).length > 0 && (
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
    </div>
  )
}
