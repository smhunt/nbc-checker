// Pan/zoom viewer for a server-rendered PDF page with evidence highlights.
// Pure presentation: the bbox is a pointer back to the drawing, never an
// input to compliance (EO1) — this component only draws rectangles.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Evidence } from '../api'

export interface EvidenceHighlight {
  fact: string
  evidence: Evidence
}

interface Props {
  imageUrl: string
  focus: Evidence
  highlights: EvidenceHighlight[]
  onClose: () => void
}

interface Transform {
  tx: number
  ty: number
  s: number
}

// Zoom target: the focused bbox padded to ~3x its size should fill the viewport…
const BBOX_PADDING = 3
// …but never zoom past 8x the fit-to-page scale (tiny bboxes stay legible).
const MAX_ZOOM_OVER_FIT = 8
// Pointer travel below this (px) counts as a click, not a drag.
const CLICK_SLOP = 5

function sameRegion(a: Evidence, b: Evidence): boolean {
  return (
    a.doc === b.doc &&
    a.page === b.page &&
    JSON.stringify(a.bbox ?? null) === JSON.stringify(b.bbox ?? null)
  )
}

export function EvidenceViewer({ imageUrl, focus, highlights, onClose }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [transform, setTransform] = useState<Transform>({ tx: 0, ty: 0, s: 1 })
  const [animate, setAnimate] = useState(false)
  const [dragging, setDragging] = useState(false)
  // Local focus so clicking a highlight re-focuses without a parent round-trip;
  // kept in sync when the parent focuses a different fact.
  const [current, setCurrent] = useState<Evidence>(focus)
  const fittedRef = useRef(false)
  const dragRef = useRef<{
    x: number
    y: number
    tx: number
    ty: number
    moved: number
    hitIdx: number | null
  } | null>(null)

  // New page image: forget the old geometry until it loads.
  useEffect(() => {
    setImgSize(null)
    setError(null)
    setAnimate(false)
    fittedRef.current = false
  }, [imageUrl])

  useEffect(() => setCurrent(focus), [focus])

  const fitTransform = useCallback((size: { w: number; h: number }): Transform => {
    const vp = viewportRef.current
    if (!vp) return { tx: 0, ty: 0, s: 1 }
    const s = Math.min(vp.clientWidth / size.w, vp.clientHeight / size.h)
    return {
      s,
      tx: (vp.clientWidth - size.w * s) / 2,
      ty: (vp.clientHeight - size.h * s) / 2,
    }
  }, [])

  const bboxTransform = useCallback(
    (size: { w: number; h: number }, bbox: [number, number, number, number]): Transform => {
      const vp = viewportRef.current
      if (!vp) return { tx: 0, ty: 0, s: 1 }
      const fit = Math.min(vp.clientWidth / size.w, vp.clientHeight / size.h)
      const [x0, y0, x1, y1] = bbox
      const bw = Math.max(0, x1 - x0) * size.w
      const bh = Math.max(0, y1 - y0) * size.h
      // Scale so the padded bbox fits; degenerate (zero-size) boxes hit the cap.
      let s = Math.min(
        vp.clientWidth / (bw * BBOX_PADDING),
        vp.clientHeight / (bh * BBOX_PADDING),
      )
      s = Math.min(s, fit * MAX_ZOOM_OVER_FIT)
      s = Math.max(s, fit)
      const cx = ((x0 + x1) / 2) * size.w
      const cy = ((y0 + y1) / 2) * size.h
      return { s, tx: vp.clientWidth / 2 - cx * s, ty: vp.clientHeight / 2 - cy * s }
    },
    [],
  )

  // On load: snap to fit-to-page, then (next frame) animate to the focused
  // bbox. Later re-focuses animate directly from wherever the view is.
  useEffect(() => {
    if (!imgSize) return
    if (!fittedRef.current) {
      fittedRef.current = true
      setAnimate(false)
      setTransform(fitTransform(imgSize))
      if (!current.bbox) return
      const bbox = current.bbox
      let raf = requestAnimationFrame(() => {
        raf = requestAnimationFrame(() => {
          setAnimate(true)
          setTransform(bboxTransform(imgSize, bbox))
        })
      })
      return () => cancelAnimationFrame(raf)
    }
    setAnimate(true)
    setTransform(current.bbox ? bboxTransform(imgSize, current.bbox) : fitTransform(imgSize))
  }, [imgSize, current, fitTransform, bboxTransform])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!imgSize) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    const hit = (e.target as Element).closest?.('[data-highlight-idx]')
    dragRef.current = {
      x: e.clientX,
      y: e.clientY,
      tx: transform.tx,
      ty: transform.ty,
      moved: 0,
      hitIdx: hit ? Number(hit.getAttribute('data-highlight-idx')) : null,
    }
    setDragging(true)
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    d.moved = Math.max(d.moved, Math.abs(dx) + Math.abs(dy))
    setAnimate(false)
    setTransform((t) => ({ ...t, tx: d.tx + dx, ty: d.ty + dy }))
  }

  const onPointerUp = () => {
    const d = dragRef.current
    dragRef.current = null
    setDragging(false)
    // A stationary press on a highlight re-focuses it.
    if (d && d.moved < CLICK_SLOP && d.hitIdx !== null && highlights[d.hitIdx]) {
      setCurrent(highlights[d.hitIdx].evidence)
    }
  }

  const fitPage = () => {
    if (!imgSize) return
    setAnimate(true)
    setTransform(fitTransform(imgSize))
  }

  return (
    <div className="evidence-viewer">
      <div className="evidence-toolbar">
        <button className="btn" onClick={fitPage} disabled={!imgSize}>
          Fit page
        </button>
        <button className="close-btn" onClick={onClose} title="Close evidence viewer">
          ✕
        </button>
      </div>
      {error ? (
        <div className="evidence-error">{error}</div>
      ) : (
        <div
          ref={viewportRef}
          className={`evidence-viewport${dragging ? ' dragging' : ''}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <div
            className="evidence-wrapper"
            style={{
              width: imgSize?.w,
              height: imgSize?.h,
              transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.s})`,
              transition: animate ? undefined : 'none',
            }}
          >
            <img
              src={imageUrl}
              alt={`${focus.doc} — page ${focus.page}`}
              draggable={false}
              onLoad={(e) =>
                setImgSize({
                  w: e.currentTarget.naturalWidth,
                  h: e.currentTarget.naturalHeight,
                })
              }
              onError={() => setError('Could not load the drawing page image.')}
            />
            {imgSize &&
              highlights.map((h, i) => {
                const bbox = h.evidence.bbox
                if (!bbox) return null
                const focused = sameRegion(h.evidence, current)
                return (
                  <div
                    key={h.fact}
                    data-highlight-idx={i}
                    className={`evidence-highlight${focused ? ' focused' : ''}`}
                    title={h.fact}
                    style={{
                      left: `${bbox[0] * 100}%`,
                      top: `${bbox[1] * 100}%`,
                      width: `${(bbox[2] - bbox[0]) * 100}%`,
                      height: `${(bbox[3] - bbox[1]) * 100}%`,
                    }}
                  />
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
