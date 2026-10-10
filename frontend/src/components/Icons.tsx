// 内联 SVG 图标（线性风格，匹配设计稿）
import React from 'react'

interface P { size?: number; className?: string; style?: React.CSSProperties }
const S = (p: P) => ({ width: p.size ?? 18, height: p.size ?? 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, className: p.className, style: p.style })

export const LogoMark = ({ size = 30 }: P) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
    <path d="M5 27V5l11 9L27 5v22h-5.4V14.8L16 19.6l-5.6-4.8V27z" fill="#5457e5" />
    <circle cx="16" cy="19.6" r="2.1" fill="#8f92f2" />
  </svg>
)
export const IconNote = (p: P) => (
  <svg {...S(p)}><path d="M5 4h11l4 4v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" /><path d="M16 4v4h4M8.5 12h7M8.5 16h5" /></svg>
)
export const IconGraph = (p: P) => (
  <svg {...S(p)}><circle cx="6" cy="6" r="2.6" /><circle cx="18" cy="7" r="2.6" /><circle cx="12" cy="18" r="2.6" /><path d="M8.2 7.2 15.5 8m-9 5 4-3.6m3.6-.6-1.4 6" /></svg>
)
export const IconGrad = (p: P) => (
  <svg {...S(p)}><path d="m12 4 10 5.5L12 15 2 9.5z" /><path d="M6.5 12v4.6c0 1.3 2.5 2.9 5.5 2.9s5.5-1.6 5.5-2.9V12" /></svg>
)
export const IconGear = (p: P) => (
  <svg {...S(p)}><circle cx="12" cy="12" r="3.2" /><path d="M19 12a7 7 0 0 0-.14-1.4l2-1.55-2-3.46-2.35.95A7 7 0 0 0 14 5.1L13.6 2.6h-4L9.2 5.1a7 7 0 0 0-2.5 1.44l-2.36-.95-2 3.46 2 1.55a7 7 0 0 0 0 2.8l-2 1.55 2 3.46 2.35-.95a7 7 0 0 0 2.51 1.44l.4 2.5h4l.4-2.5a7 7 0 0 0 2.5-1.44l2.36.95 2-3.46-2-1.55A7 7 0 0 0 19 12z" /></svg>
)
export const IconFolder = (p: P) => (
  <svg {...S(p)}><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
)
export const IconFolderOpen = (p: P) => (
  <svg {...S(p)}><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="m3 11 2.4-4H21l-2.6 8.5a2 2 0 0 1-1.9 1.5H5.5" /></svg>
)
export const IconConcept = (p: P) => (
  <svg {...S(p)}><path d="m12 3 2.5 5.3 5.5.8-4 4.1 1 5.8-5-2.8-5 2.8 1-5.8-4-4.1 5.5-.8z" /></svg>
)
export const IconChevron = (p: P) => (<svg {...S(p)}><path d="m9 6 6 6-6 6" /></svg>)
export const IconCaretDown = (p: P) => (<svg {...S(p)}><path d="m6 9 6 6 6-6" /></svg>)
export const IconSearch = (p: P) => (
  <svg {...S(p)}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.8-3.8" /></svg>
)
export const IconBell = (p: P) => (
  <svg {...S(p)}><path d="M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" /><path d="M10 20a2.2 2.2 0 0 0 4 0" /></svg>
)
export const IconBulb = (p: P) => (
  <svg {...S(p)}><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z" /></svg>
)
export const IconLink = (p: P) => (
  <svg {...S(p)}><path d="M10 14a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" /><path d="M14 10a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" /></svg>
)
export const IconList = (p: P) => (
  <svg {...S(p)}><path d="M8.5 6h12M8.5 12h12M8.5 18h12M4 6h.01M4 12h.01M4 18h.01" /></svg>
)
export const IconWand = (p: P) => (
  <svg {...S(p)}><path d="m5 19 9.5-9.5M15 4l.9 2.1L18 7l-2.1.9L15 10l-.9-2.1L12 7l2.1-.9zM19.5 12.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6zM6.5 3l.5 1.2L8.2 4.7 7 5.2 6.5 6.5 6 5.2 4.7 4.7l1.3-.5z" /></svg>
)
export const IconFilePdf = (p: P) => (
  <svg {...S(p)}><path d="M5 4h11l4 4v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" /><path d="M16 4v4h4" /><text x="12" y="17" textAnchor="middle" fontSize="7.5" fill="currentColor" stroke="none" fontWeight="700">PDF</text></svg>
)
export const IconSpark = (p: P) => (
  <svg {...S(p)}><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /><circle cx="12" cy="12" r="3.2" /></svg>
)
export const IconArrowLeft = (p: P) => (<svg {...S(p)}><path d="M19 12H5m6 7-7-7 7-7" /></svg>)
export const IconArrowUp = (p: P) => (<svg {...S(p)}><path d="M12 19V5m-7 7 7-7 7 7" /></svg>)
export const IconPlus = (p: P) => (<svg {...S(p)}><path d="M12 5v14M5 12h14" /></svg>)
export const IconSend = (p: P) => (
  <svg {...S(p)}><path d="m21.5 2.5-10 10M21.5 2.5 15 21.5l-3.5-9-9-3.5z" /></svg>
)
export const IconTrash = (p: P) => (
  <svg {...S(p)}><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m3 0v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7M10 11v6M14 11v6" /></svg>
)
export const IconEdit = (p: P) => (
  <svg {...S(p)}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
)
export const IconRefresh = (p: P) => (
  <svg {...S(p)}><path d="M21 12a9 9 0 1 1-2.6-6.3L21 8" /><path d="M21 3v5h-5" /></svg>
)
export const IconClose = (p: P) => (<svg {...S(p)}><path d="m6 6 12 12M18 6 6 18" /></svg>)
export const IconCheck = (p: P) => (<svg {...S(p)}><path d="m4 12.5 5 5L20 6.5" /></svg>)
export const IconUpload = (p: P) => (
  <svg {...S(p)}><path d="M12 16V4m-6 6 6-6 6 6" /><path d="M4 20h16" /></svg>
)
export const IconDownload = (p: P) => (
  <svg {...S(p)}><path d="M12 4v12m-6-6 6 6 6-6" /><path d="M4 20h16" /></svg>
)
export const IconCard = (p: P) => (
  <svg {...S(p)}><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m3 10 9 5 9-5" /></svg>
)
export const IconDoc = (p: P) => (
  <svg {...S(p)}><path d="M5 4h11l4 4v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" /><path d="M16 4v4h4" /></svg>
)
