import { useEffect, useState, useSyncExternalStore } from 'react'

export const prefersReduced = (): boolean =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Progreso 0..1 de una sección: 0 cuando su borde superior toca el borde superior del viewport, 1 cuando su borde inferior lo toca. */
export function useSectionProgress(id: string): number {
  const [p, setP] = useState(0)
  useEffect(() => {
    let raf = 0
    const read = () => {
      raf = 0
      const el = document.getElementById(id)
      if (!el) return
      const r = el.getBoundingClientRect()
      const span = Math.max(1, r.height - window.innerHeight * 0.35)
      const v = Math.min(1, Math.max(0, -r.top / span))
      setP(prev => (Math.abs(prev - v) < 0.002 ? prev : v))
    }
    const on = () => {
      if (!raf) raf = requestAnimationFrame(read)
    }
    read()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
      cancelAnimationFrame(raf)
    }
  }, [id])
  return p
}

/** Clase de dato seleccionada en la sección de capas, compartida entre el plano y los controles. */
export type DataClass = 'observado' | 'calculado' | 'hipotesis' | 'confirmado' | 'desconocido'
export const CLASSES: DataClass[] = ['observado', 'calculado', 'hipotesis', 'confirmado', 'desconocido']

let selected: DataClass | null = null
const subs = new Set<() => void>()
export const setSelected = (c: DataClass | null) => {
  if (c === selected) return
  selected = c
  subs.forEach(f => f())
}
export const useSelected = () =>
  useSyncExternalStore(
    f => {
      subs.add(f)
      return () => subs.delete(f)
    },
    () => selected
  )

export function useTheme(): 'dark' | 'light' {
  const get = () => {
    const attr = document.documentElement.getAttribute('data-theme')
    if (attr === 'dark' || attr === 'light') return attr
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }
  const [t, setT] = useState<'dark' | 'light'>(get)
  useEffect(() => {
    const mo = new MutationObserver(() => setT(get()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const h = () => setT(get())
    mq.addEventListener('change', h)
    return () => {
      mo.disconnect()
      mq.removeEventListener('change', h)
    }
  }, [])
  return t
}

export const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

/** Progreso 0..1 de un tramo con escenario sticky: 0 al empezar a fijarse, 1 cuando el escenario se suelta. */
export function useTrackProgress(id: string): number {
  const [p, setP] = useState(0)
  useEffect(() => {
    let raf = 0
    const read = () => {
      raf = 0
      const el = document.getElementById(id)
      if (!el) return
      const r = el.getBoundingClientRect()
      const span = Math.max(1, r.height - window.innerHeight)
      const v = Math.min(1, Math.max(0, -r.top / span))
      setP(prev => (Math.abs(prev - v) < 0.001 ? prev : v))
    }
    const on = () => {
      if (!raf) raf = requestAnimationFrame(read)
    }
    read()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
      cancelAnimationFrame(raf)
    }
  }, [id])
  return p
}

export function useMode(): 'mobile' | 'desktop' {
  const get = () => (window.innerWidth < 760 || window.innerWidth / window.innerHeight < 0.9 ? 'mobile' : 'desktop')
  const [m, setM] = useState<'mobile' | 'desktop'>(get)
  useEffect(() => {
    const on = () => setM(get())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return m
}

/** Progreso 0..1 de una sección normal mientras entra en pantalla: 0 cuando asoma por abajo, 1 cuando su borde superior pasa del centro. */
export function useEnterProgress(id: string): number {
  const [p, setP] = useState(0)
  useEffect(() => {
    let raf = 0
    const read = () => {
      raf = 0
      const el = document.getElementById(id)
      if (!el) return
      const r = el.getBoundingClientRect()
      const vh = window.innerHeight
      const v = Math.min(1, Math.max(0, (vh - r.top) / (vh + r.height * 0.2)))
      setP(prev => (Math.abs(prev - v) < 0.002 ? prev : v))
    }
    const on = () => {
      if (!raf) raf = requestAnimationFrame(read)
    }
    read()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
      cancelAnimationFrame(raf)
    }
  }, [id])
  return p
}
