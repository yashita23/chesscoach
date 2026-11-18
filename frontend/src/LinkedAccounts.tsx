import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type LinkedAccount, type SyncJobStatus } from './api'

export default function LinkedAccounts() {
  const [accounts, setAccounts] = useState<LinkedAccount[]>([])
  const [syncJob, setSyncJob] = useState<SyncJobStatus | null>(null)
  const [usernameInput, setUsernameInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const pollTimerRef = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  const reloadAccounts = () => {
    api
      .getAccounts()
      .then(setAccounts)
      .catch((err) => console.error('Lỗi tải danh sách tài khoản:', err))
  }

  const startPolling = () => {
    stopPolling()
    pollTimerRef.current = window.setInterval(async () => {
      try {
        const job = await api.getSyncStatus()
        setSyncJob(job)
        if (job.status === 'completed' || job.status === 'failed') {
          stopPolling()
          reloadAccounts()
          if (job.status === 'completed') {
            setSuccessMsg(`Đồng bộ thành công! (+${job.new_games_count} ván mới)`)
          }
        }
      } catch (err) {
        console.error('Lỗi polling trạng thái sync:', err)
      }
    }, 1500)
  }

  useEffect(() => {
    reloadAccounts()
    api
      .getSyncStatus()
      .then((job) => {
        setSyncJob(job)
        if (job.status === 'pending' || job.status === 'running') {
          startPolling()
        }
      })
      .catch((err) => console.error('Lỗi kiểm tra trạng thái sync ban đầu:', err))

    return () => stopPolling()
  }, [])

  const handleLink = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = usernameInput.trim()
    if (!trimmed) return

    setLoading(true)
    setActionError(null)
    setSuccessMsg(null)
    try {
      const res = await api.linkLichess(trimmed)
      setAccounts([res.account])
      setSyncJob(res.job)
      setUsernameInput('')
      setSuccessMsg(`Đã gắn tài khoản Lichess '${trimmed}'. Đang đồng bộ ván...`)
      startPolling()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Lỗi khi gắn tài khoản')
    } finally {
      setLoading(false)
    }
  }

  const handleSync = async () => {
    setLoading(true)
    setActionError(null)
    setSuccessMsg(null)
    try {
      const job = await api.syncLichess()
      setSyncJob(job)
      startPolling()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Lỗi khi kích hoạt đồng bộ')
    } finally {
      setLoading(false)
    }
  }

  const lichessAcc = accounts.find((a) => a.platform === 'lichess')
  const isSyncing = syncJob?.status === 'pending' || syncJob?.status === 'running'

  return (
    <div className="linked-accounts panel">
      <h3>Tài khoản liên kết</h3>
      <p className="meta">
        Gắn tài khoản Lichess để tải các ván cờ blitz/rapid/classical gần nhất và phân tích điểm yếu. Ván được lưu
        cục bộ nên app vẫn dùng được khi offline.
      </p>

      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}

      {successMsg && <p className="notice">{successMsg}</p>}

      {lichessAcc ? (
        <div className="account-card">
          <div className="account-info">
            <span className="account-platform">Lichess</span>
            <strong className="account-username">{lichessAcc.username}</strong>
            <span className="account-games-count">
              {lichessAcc.games_count} ván đã lưu
            </span>
            <span className="account-last-sync">
              Đồng bộ lần cuối:{' '}
              {lichessAcc.last_synced_at
                ? new Date(lichessAcc.last_synced_at).toLocaleString()
                : 'Chưa đồng bộ'}
            </span>
          </div>

          <button
            type="button"
            onClick={handleSync}
            disabled={loading || isSyncing}
            className="sync-button"
          >
            {isSyncing ? 'Đang đồng bộ…' : 'Cập nhật ván'}
          </button>
        </div>
      ) : (
        <form onSubmit={handleLink} className="link-account-form">
          <label htmlFor="lichess-username">Username Lichess:</label>
          <div className="form-row">
            <input
              id="lichess-username"
              type="text"
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              placeholder="Nhập username Lichess"
              disabled={loading}
              required
            />
            <button type="submit" disabled={loading || !usernameInput.trim()}>
              {loading ? 'Đang kiểm tra…' : 'Liên kết'}
            </button>
          </div>
        </form>
      )}

      {isSyncing && syncJob && (
        <div className="sync-progress">
          <p>
            {syncJob.status === 'pending'
              ? 'Đang chuẩn bị tiến trình...'
              : `Đang tải ván: ${syncJob.current} / ${syncJob.total || '...'}`}
          </p>
          <progress
            value={syncJob.current}
            max={syncJob.total > 0 ? syncJob.total : 1}
          />
        </div>
      )}

      {syncJob?.status === 'failed' && syncJob.error && (
        <p className="error" role="alert">
          Lỗi đồng bộ: {syncJob.error}
        </p>
      )}
    </div>
  )
}
