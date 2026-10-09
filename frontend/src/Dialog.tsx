import { useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

export default function Dialog({ title, onClose, children, eyebrow = 'DATASET / HISTÓRICO DE REVISÕES', closeLabel = 'Fechar revisão' }: { title: string; onClose: () => void; children: ReactNode; eyebrow?: string; closeLabel?: string }) {
  const titleId = useId()
  const ref = useRef<HTMLElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    ref.current?.focus()
    function keyboard(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); return }
      if (event.key !== 'Tab') return
      const controls = [...(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]') ?? [])]
      const first = controls[0], last = controls.at(-1)
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) {
        event.preventDefault(); last?.focus()
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === ref.current)) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', keyboard)
    return () => { document.removeEventListener('keydown', keyboard); previous?.focus() }
  }, [])
  return <div className="modal-backdrop"><section ref={ref} className="modal annotation-modal" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
    <button className="modal-close" aria-label={closeLabel} onClick={onClose}><X size={18}/></button>
    <p className="eyebrow">{eyebrow}</p><h2 id={titleId}>{title}</h2>{children}
  </section></div>
}
