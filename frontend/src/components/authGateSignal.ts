// 顶栏 → App 的认证门桥接：单人开放模式下顶栏提供「注册 / 登录」入口，
// App 的 gate 是组件局部状态，通过 window 事件打开。
export const AUTH_GATE_EVENT = 'nl-open-auth-gate'

export function openAuthGate() {
  window.dispatchEvent(new Event(AUTH_GATE_EVENT))
}
