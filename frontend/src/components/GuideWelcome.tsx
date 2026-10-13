import { useNavigate } from 'react-router-dom'
import Modal from './Modal'
import { LogoMark } from './Icons'

// 首次进入的新手欢迎弹窗：点任一按钮都会记录 nl-guide-seen，之后不再自动弹出；
// 想再看随时从侧边栏「新手指引」回到 /guide。
export default function GuideWelcome({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  return (
    <Modal title="" onClose={onClose}>
      <div style={{ textAlign: 'center', padding: '4px 6px 2px' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10 }}><LogoMark size={44} /></div>
        <div style={{ fontSize: 18, fontWeight: 700 }}>欢迎使用墨链 NoteLink</div>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 6, lineHeight: 1.7 }}>
          基于 Markdown 文件的 AI 学习笔记：AI 生成笔记、划选即问、概念双链、知识图谱、出题陪练。
        </div>
        <div className="guide-points">
          <div className="gp-item"><span className="gp-ico">📂</span>数据是你的 —— 一摞普通 .md 文件夹，Obsidian 直接打开</div>
          <div className="gp-item"><span className="gp-ico">🤖</span>AI 是你的 —— 任意 OpenAI 兼容接口，随时切换不绑定</div>
          <div className="gp-item"><span className="gp-ico">🌱</span>从零开始也不慌 —— 说个主题，AI 先帮你搭好知识框架</div>
        </div>
      </div>
      <div className="modal-ops" style={{ justifyContent: 'center', gap: 10 }}>
        <button className="btn" onClick={onClose}>直接开始</button>
        <button className="btn primary" onClick={() => { onClose(); navigate('/guide') }}>看看新手指引 →</button>
      </div>
    </Modal>
  )
}
