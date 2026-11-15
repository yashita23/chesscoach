import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Practice } from './api'

const MINUTE_CHOICES = [10, 15, 20, 30, 45, 60]

/** Danh sách bài tập của buổi luyện tiếp theo; tải lại mỗi khi `version` đổi (sau mỗi lần giải có nhãn). */
type Props = {
  version: number
  current: string | null
  /** Gọi một lần khi bài kiểm tra đầu vào vừa xong (chế độ đổi từ placement sang practice). */
  onPlacementDone: () => void
}

export default function PracticePanel({ version, current, onPlacementDone }: Props) {
  const [practice, setPractice] = useState<Practice | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const lastMode = useRef<Practice['mode'] | null>(null)

  useEffect(() => {
    api
      .practice()
      .then((p) => {
        if (lastMode.current === 'placement' && p.mode === 'practice') onPlacementDone()
        lastMode.current = p.mode
        setPractice(p)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Không tải được buổi luyện'))
  }, [version, reload, onPlacementDone])

  async function changeMinutes(minutes: number) {
    try {
      await api.updateMe({ daily_minutes: minutes })
      setReload((n) => n + 1)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không lưu được thời gian luyện')
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!practice) return <p className="meta">Đang tính buổi luyện…</p>

  if (practice.mode === 'placement' && practice.placement) {
    const { completed, total } = practice.placement
    return (
      <div className="practice">
        <h3>
          Bài kiểm tra đầu vào: {completed}/{total}
        </h3>
        <p className="meta">
          Mỗi bài tập đo một kỹ năng, ở mức bạn giải đúng khoảng một nửa. Làm xong, bạn sẽ thấy hồ sơ kỹ năng sơ bộ
          rồi bắt đầu buổi luyện.
        </p>
        <ol className="practice-list">
          {practice.items.map((item) => (
            <li key={item.puzzle_id} className={item.puzzle_id === current ? 'current' : undefined}>
              <span className="practice-rating">{item.rating}</span>
              <span className="practice-skills">{item.skills.map((s) => s.name).join(', ')}</span>
              <span className="practice-p">{Math.round(item.predicted_p * 100)}%</span>
            </li>
          ))}
        </ol>
      </div>
    )
  }

  return (
    <div className="practice">
      <div className="practice-head">
        <h3>Buổi luyện</h3>
        <label className="minutes">
          <select
            id="daily-minutes"
            value={practice.daily_minutes}
            onChange={(e) => void changeMinutes(Number(e.target.value))}
          >
            {(MINUTE_CHOICES.includes(practice.daily_minutes)
              ? MINUTE_CHOICES
              : [...MINUTE_CHOICES, practice.daily_minutes].sort((a, b) => a - b)
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
        {practice.items.length} bài tập, rating bài tập quanh {Math.round(practice.target_rating)}: mức bạn giải đúng khoảng 70%.
      </p>
      <ol className="practice-list">
        {practice.items.map((item) => (
          <li key={item.puzzle_id} className={item.puzzle_id === current ? 'current' : undefined}>
            <span className="practice-rating">{item.rating}</span>
            <span className="practice-skills">{item.skills.map((s) => s.name).join(', ')}</span>
            <span className="practice-p">{Math.round(item.predicted_p * 100)}%</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
