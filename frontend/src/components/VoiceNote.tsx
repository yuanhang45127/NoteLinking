// 语音速记：Web Speech API 实时转写（中文），追加到当前阅读章节末尾或笔记文末。
// 浏览器不支持时按钮置灰提示；后端 ASR 预留二期接入。
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { insertIntoSection } from '../lib/contentEdit'
import Modal from './Modal'

interface RecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: any) => void) | null
  onerror: ((e: any) => void) | null
  onend: (() => void) | null
}

function getRecognitionCtor(): any | null {
  const w = window as any
  return w.webkitSpeechRecognition || w.SpeechRecognition || null
}

export default function VoiceNote({ path, content, sectionTitle, onSaved, onClose, toast }: {
  path: string
  content: string
  /** 当前滚动所在的章节标题（目录高亮节）；null = 还没滚到任何小节 */
  sectionTitle: string | null
  onSaved: () => Promise<void>
  onClose: () => void
  toast: (t: string, k?: 'ok' | 'err') => void
}) {
  const supported = !!getRecognitionCtor()
  const [text, setText] = useState('')
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const recRef = useRef<RecognitionLike | null>(null)

  useEffect(() => () => recRef.current?.stop(), [])

  const toggle = () => {
    if (listening) { recRef.current?.stop(); return }
    const Ctor = getRecognitionCtor()
    if (!Ctor) { toast('当前浏览器不支持语音识别，请用 Chrome / Edge / Safari', 'err'); return }
    const rec: RecognitionLike = new Ctor()
    rec.lang = 'zh-CN'
    rec.continuous = true
    rec.interimResults = true
    rec.onresult = (e: any) => {
      let finalText = ''
      let mid = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) finalText += r[0].transcript
        else mid += r[0].transcript
      }
      if (finalText) setText((t) => (t ? t + finalText : finalText))
      setInterim(mid)
    }
    rec.onerror = (e: any) => {
      setListening(false); setInterim('')
      const reason = e?.error === 'not-allowed' ? '麦克风权限被拒绝' : e?.error === 'network' ? '语音服务网络不可用' : '识别出错'
      toast(`语音识别：${reason}`, 'err')
    }
    rec.onend = () => { setListening(false); setInterim('') }
    recRef.current = rec
    try { rec.start(); setListening(true) }
    catch { setListening(false) }
  }

  const appendToSection = async () => {
    if (!text.trim()) return
    if (!sectionTitle) { toast('没定位到当前章节，请先滚动到目标小节，或选「追加到文末」', 'err'); return }
    const next = insertIntoSection(content, sectionTitle, text.trim())
    if (next === null) { toast('没能在正文中定位该章节', 'err'); return }
    try {
      await api.saveNote(path, next)
      toast(`已追加到「${sectionTitle}」末尾`)
      setText(''); await onSaved()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const appendToEnd = async () => {
    if (!text.trim()) return
    try {
      await api.appendToNote(path, text.trim())
      toast('已追加到文末')
      setText(''); await onSaved()
    } catch (e: any) { toast(e.message, 'err') }
  }

  return (
    <Modal title="🎙 语音速记" onClose={onClose}>
      <div className="hint">
        说话会实时转成文字（中文）。写完点下方按钮追加到笔记
        {sectionTitle ? `，当前章节：「${sectionTitle}」` : '（尚未定位到章节）'}。
      </div>
      <textarea className="text-input" style={{ width: '100%', minHeight: 140, marginTop: 10 }}
        placeholder={listening ? '正在听写…（临时结果见下方灰字）' : '点 🎙 开始说话，或直接在这里打字…'}
        value={text} onChange={(e) => setText(e.target.value)} autoFocus />
      {interim && <div className="voice-interim">{interim}…</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className={`btn ${listening ? '' : 'primary'}`} disabled={!supported}
          title={supported ? (listening ? '停止听写' : '开始听写（中文）') : '当前浏览器不支持语音识别'}
          onClick={toggle}>
          {listening ? '⏹ 停止听写' : '🎙 开始听写'}
        </button>
        <button className="btn small" disabled={!text.trim()} onClick={appendToSection}>
          追加到本章
        </button>
        <button className="btn small" disabled={!text.trim()} onClick={appendToEnd}>
          追加到文末
        </button>
        {!supported && <span className="ann-comment empty">当前浏览器不支持，请用 Chrome / Edge / Safari</span>}
      </div>
    </Modal>
  )
}
