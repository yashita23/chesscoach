import { useEffect, useState } from 'react'
import { api, ApiError, type Session } from './api'

const MINUTE_CHOICES = [10, 15, 20, 30, 45, 60]

/** Danh sách bài tập của buổi luyện tiếp theo; tải lại mỗi khi `version` đổi (sau mỗi lần giải). */
export default function SessionPanel({ version, current }: { version: number; current: string | null }) {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    api
      .session()
      .then((s) => {
        setSession(s)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Không tải được buổi luyện'))
  }, [version, reload])

  async function changeMinutes(minutes: number) {
    try {
      await api.updateMe(minutes)
      setReload((n) => n + 1)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được thời gian luyện')
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!session) return <p className="meta">Đang tính buổi luyện…</p>

  return (
    <div className="session">
      <div className="session-head">
        <h3>Buổi luyện</h3>
        <label className="minutes">
          <select
            id="daily-minutes"
            value={session.daily_minutes}
            onChange={(e) => void changeMinutes(Number(e.target.value))}
          >
            {(MINUTE_CHOICES.includes(session.daily_minutes)
              ? MINUTE_CHOICES
              : [...MINUTE_CHOICES, session.daily_minutes].sort((a, b) => a - b)
            ).map((m) => (
              <option key={m} value={m}>
                {m} phút
              </option>
            ))}
          </select>
          <span>mỗi ngày</span>
        </label>
      </div>
      <p className="meta">
        {session.items.length} bài tập, rating quanh {Math.round(session.target_rating)}: mức bạn giải đúng khoảng 70%.
      </p>
      <ol className="session-list">
        {session.items.map((item) => (
          <li key={item.puzzle_id} className={item.puzzle_id === current ? 'current' : undefined}>
            <span className="session-rating">{item.rating}</span>
            <span className="session-skills">{item.skills.map((s) => s.name).join(', ')}</span>
            <span className="session-p">{Math.round(item.predicted_p * 100)}%</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
