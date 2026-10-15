import { useEffect, useState } from 'react'
import { api } from '../api'
import { LogoMark } from './Icons'

/** 登录 / 注册门：多用户模式下未登录时全屏展示。开启邮箱验证时注册需验证码。 */
export default function LoginGate({ onOk }: { onOk: (username: string) => void }) {
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [emailVerify, setEmailVerify] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [cooldown, setCooldown] = useState(0) // 发送验证码倒计时
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => window.clearTimeout(t)
  }, [cooldown])

  const probeStatus = (t: 'login' | 'register') => {
    setTab(t)
    setErr('')
    if (t === 'register') {
      api.authStatus()
        .then((s) => setEmailVerify(!!s.email_verify))
        .catch(() => {})
    }
  }

  const sendCode = async () => {
    if (cooldown > 0) return
    const em = email.trim()
    if (!em) { setErr('请先填写邮箱'); return }
    setErr('')
    try {
      const r = await api.sendEmailCode(em)
      setCooldown(r.cooldown || 60)
    } catch (e: any) {
      const msg = e.message || '发送失败'
      const m = msg.match(/(\d+)\s*秒/)
      if (m) setCooldown(Number(m[1]))
      setErr(msg)
    }
  }

  const submit = async () => {
    if (busy) return
    setErr('')
    const name = username.trim()
    if (!name || !password) { setErr('请输入用户名和密码'); return }
    if (tab === 'register' && password !== confirm) { setErr('两次输入的密码不一致'); return }
    if (tab === 'register' && emailVerify && !code.trim()) { setErr('请填写邮箱验证码'); return }
    setBusy(true)
    try {
      const r = tab === 'login'
        ? await api.login(name, password)
        : await api.register(name, password, email.trim(), code.trim())
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
            {emailVerify && (
              <>
                <input
                  className="text-input"
                  style={{ width: '100%', marginBottom: 10 }}
                  placeholder="邮箱（用于接收验证码）"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <input
                    className="text-input"
                    style={{ flex: 1, marginBottom: 0 }}
                    placeholder="6 位验证码"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && submit()}
                  />
                  <button className="btn" style={{ flex: 'none' }} disabled={cooldown > 0} onClick={sendCode}>
                    {cooldown > 0 ? `${cooldown}s` : '发送验证码'}
                  </button>
                </div>
              </>
            )}
            <input
              className="text-input"
              style={{ width: '100%' }}
              type="password"
              placeholder="再输一遍密码"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
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
