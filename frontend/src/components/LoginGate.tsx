import { useState } from 'react'
import { api } from '../api'
import { LogoMark } from './Icons'

/** 登录 / 注册门：多用户模式下未登录时全屏展示。 */
export default function LoginGate({ onOk }: { onOk: (username: string) => void }) {
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [firstUser, setFirstUser] = useState(false) // 还是没人注册（首位注册者可接管旧数据）
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [claim, setClaim] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const probeStatus = (t: 'login' | 'register') => {
    setTab(t)
    setErr('')
    if (t === 'register') {
      api.authStatus()
        .then((s) => setFirstUser(s.mode === 'open'))
        .catch(() => setFirstUser(false))
    }
  }

  const submit = async () => {
    if (busy) return
    setErr('')
    const name = username.trim()
    if (!name || !password) { setErr('请输入用户名和密码'); return }
    if (tab === 'register' && password !== confirm) { setErr('两次输入的密码不一致'); return }
    setBusy(true)
    try {
      const r = tab === 'login'
        ? await api.login(name, password)
        : await api.register(name, password, claim)
      onOk(r.username)
    } catch (e: any) {
      setErr(e.message || '出错了，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--side-bg)' }}>
      <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 18, padding: '36px 40px', width: 380 }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}><LogoMark size={40} /></div>
        <div style={{ fontSize: 18, fontWeight: 700, textAlign: 'center' }}>墨链 NoteLink</div>
        <div style={{ color: 'var(--muted)', fontSize: 13, textAlign: 'center', margin: '6px 0 18px' }}>
          每个人都可以通过 AI 学习知识与技能！
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {(['login', 'register'] as const).map((t) => (
            <button
              key={t}
              className={`btn ${tab === t ? 'primary' : ''}`}
              style={{ flex: 1, justifyContent: 'center' }}
              onClick={() => probeStatus(t)}
            >
              {t === 'login' ? '登录' : '注册'}
            </button>
          ))}
        </div>

        <input
          className="text-input"
          style={{ width: '100%', marginBottom: 10 }}
          placeholder="用户名（2-32 位字母、数字、中文、_ 或 -）"
          value={username}
          autoFocus
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        <input
          className="text-input"
          style={{ width: '100%', marginBottom: tab === 'register' ? 10 : 0 }}
          type="password"
          placeholder="密码（至少 6 位）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        {tab === 'register' && (
          <>
            <input
              className="text-input"
              style={{ width: '100%' }}
              type="password"
              placeholder="再输一遍密码"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
            {firstUser && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--muted)', margin: '10px 0 0' }}>
                <input type="checkbox" checked={claim} onChange={(e) => setClaim(e.target.checked)} />
                接管此服务器上已有的笔记与设置
              </label>
            )}
          </>
        )}

        {err && <div style={{ color: 'var(--err)', fontSize: 12.5, marginTop: 8 }}>{err}</div>}
        <button className="btn primary" style={{ width: '100%', justifyContent: 'center', marginTop: 14 }} disabled={busy} onClick={submit}>
          {busy ? '请稍候…' : tab === 'login' ? '登录' : '创建账号并进入'}
        </button>
      </div>
    </div>
  )
}
