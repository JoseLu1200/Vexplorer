import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Banderas de verificación: ?reduce=1 fuerza prefers-reduced-motion y ?nowebgl=1 fuerza el fallback SVG.
document.documentElement.lang = 'es'
const params = new URLSearchParams(location.search)
if (params.get('reduce') === '1') {
  const original = window.matchMedia.bind(window)
  window.matchMedia = (q: string) => {
    if (q.includes('prefers-reduced-motion')) {
      const reduce = q.includes('reduce')
      return { ...original(q), matches: reduce, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} } as MediaQueryList
    }
    return original(q)
  }
  document.documentElement.classList.add('force-reduce')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
