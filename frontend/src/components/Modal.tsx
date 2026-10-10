import { useEffect } from 'react'
import { IconClose } from './Icons'

export default function Modal({ title, onClose, children, wide, ops }: {
  title: string
  onClose: () => void
  children: React.ReactNode
  wide?: boolean
  ops?: React.ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-mask" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <h3 style={{ flex: 1 }}>{title}</h3>
          <button className="bell" onClick={onClose}><IconClose size={17} /></button>
        </div>
        {children}
        {ops && <div className="modal-ops">{ops}</div>}
      </div>
    </div>
  )
}
