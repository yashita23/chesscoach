import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type Player } from './api'
import PuzzleTrainer from './PuzzleTrainer'

type Mode = 'login' | 'register'

export default function App() {
  const [player, setPlayer] = useState<Player | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setPlayer)
      .catch(() => setPlayer(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <main className="center">Đang tải…</main>
  if (player === null) return <AuthForm onAuthenticated={setPlayer} />
  return <Home player={player} onLogout={() => setPlayer(null)} />
}

function AuthForm({ onAuthenticated }: { onAuthenticated: (p: Player) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const p =
        mode === 'login'
          ? await api.login(email, password)
          : await api.register(email, password, displayName)
      onAuthenticated(p)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không kết nối được máy chủ')
    } finally {
      setBusy(false)
    }
  }

  const isLogin = mode === 'login'
  return (
    <main className="center">
      <form className="card" onSubmit={submit}>
        <h1>Chess Coach</h1>
        <h2>{isLogin ? 'Đăng nhập' : 'Đăng ký'}</h2>
        {!isLogin && (
          <label>
            Tên hiển thị
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Mật khẩu
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            minLength={isLogin ? undefined : 8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {isLogin ? 'Đăng nhập' : 'Đăng ký'}
        </button>
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(isLogin ? 'register' : 'login')
            setError(null)
          }}
        >
          {isLogin ? 'Chưa đăng ký? Đăng ký ngay' : 'Đã đăng ký? Đăng nhập'}
        </button>
      </form>
    </main>
  )
}

function Home({ player, onLogout }: { player: Player; onLogout: () => void }) {
  async function logout() {
    await api.logout().catch(() => undefined)
    onLogout()
  }

  return (
    <>
      <header className="topbar">
        <strong>Chess Coach</strong>
        <span>
          {player.display_name}
          <button type="button" className="link" onClick={logout}>
            Đăng xuất
          </button>
        </span>
      </header>
      <main className="content">
        <PuzzleTrainer />
      </main>
    </>
  )
}
