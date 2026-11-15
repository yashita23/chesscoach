import { useCallback, useEffect, useRef, useState } from 'react'
import { Chess } from 'chess.js'
import { Chessboard } from 'react-chessboard'
import type { Arrow, Piece, PromotionPieceOption, Square } from 'react-chessboard/dist/chessboard/types'
import { api, ApiError, type Attempt } from './api'
import PracticePanel from './PracticePanel'

const OPPONENT_DELAY_MS = 450

type Phase =
  | { kind: 'loading' }
  | { kind: 'intro'; total: number } // trước bài kiểm tra đầu vào: hỏi rating ván (tùy chọn)
  | { kind: 'error'; message: string }
  | { kind: 'opponent' } // đang chờ diễn nước của đối thủ
  | { kind: 'turn' } // tới lượt người chơi
  | { kind: 'sending' }
  | { kind: 'done'; correct: boolean }

type Feedback = { tone: 'good' | 'bad' | 'info'; text: string } | null

function squares(uci: string): [Square, Square] {
  return [uci.slice(0, 2) as Square, uci.slice(2, 4) as Square]
}

function highlight(uci: string | null): Record<string, React.CSSProperties> {
  if (!uci) return {}
  const [from, to] = squares(uci)
  const style = { background: 'rgba(255, 214, 10, 0.45)' }
  return { [from]: style, [to]: style }
}

export default function PuzzleTrainer({ onPlacementDone }: { onPlacementDone: () => void }) {
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [fen, setFen] = useState<string>('start')
  const [lastMove, setLastMove] = useState<string | null>(null)
  const [arrow, setArrow] = useState<Arrow[]>([])
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  const [feedback, setFeedback] = useState<Feedback>(null)
  // Đã đi sai trong lần giải này: nhãn đã chốt là sai, người chơi đang đi tiếp lời giải.
  const [failed, setFailed] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  // Tăng mỗi khi lần giải có nhãn, để danh sách buổi luyện tính lại.
  const [practiceVersion, setPracticeVersion] = useState(0)
  /** Gọi đúng một lần cho mỗi lần giải, khi nhãn được chốt (nước sai đầu tiên hoặc giải xong). */
  const onLabelDecided = () => setPracticeVersion((v) => v + 1)

  const later = useCallback((fn: () => void) => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(fn, OPPONENT_DELAY_MS)
  }, [])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  // Người chơi đã qua màn hình giới thiệu bài kiểm tra (hoặc không cần) trong lần mở trang này.
  const introSeen = useRef(false)

  const loadNext = useCallback(async () => {
    setPhase({ kind: 'loading' })
    setFeedback(null)
    setArrow([])
    setLastMove(null)
    setFailed(false)
    try {
      if (!introSeen.current) {
        const practice = await api.practice()
        if (practice.mode === 'placement' && practice.placement && !practice.placement.started) {
          setPhase({ kind: 'intro', total: practice.placement.total })
          return
        }
        introSeen.current = true
      }
      const { puzzle_id } = await api.nextPuzzle()
      const a = await api.startAttempt(puzzle_id)
      setAttempt(a)
      setFen(a.start_fen)
      setPhase({ kind: 'opponent' })
      later(() => {
        setFen(a.fen)
        setLastMove(a.opponent_move)
        setPhase({ kind: 'turn' })
      })
    } catch (err) {
      setPhase({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Không kết nối được máy chủ',
      })
    }
  }, [later])

  useEffect(() => {
    void loadNext()
  }, [loadNext])

  /** Đi thử nước trên bàn cờ phía trình duyệt; trả về UCI nếu hợp lệ. */
  function localMove(from: Square, to: Square, promotion?: string): string | null {
    const game = new Chess(fen)
    try {
      const m = game.move({ from, to, promotion })
      return m.from + m.to + (m.promotion ?? '')
    } catch {
      return null
    }
  }

  async function submit(uci: string) {
    if (!attempt) return
    const before = fen
    const [from, to] = squares(uci)
    setFen(new Chess(fen).move({ from, to, promotion: uci[4] }).after)
    setLastMove(uci)
    setArrow([])
    setPhase({ kind: 'sending' })
    try {
      const r = await api.playMove(attempt.attempt_id, uci)
      if (r.verdict === 'wrong') {
        setFen(before)
        setLastMove(null)
        if (!failed) onLabelDecided()
        setFailed(true)
        if (r.expected_move) setArrow([[...squares(r.expected_move), 'rgb(47, 111, 78)']])
        setFeedback({ tone: 'bad', text: 'Chưa đúng. Mũi tên chỉ nước đúng, đi tiếp lời giải nhé.' })
        setPhase({ kind: 'turn' })
        return
      }
      if (r.completed) {
        setFen(r.fen)
        const correct = r.correct === true
        setFeedback(
          correct
            ? { tone: 'good', text: 'Chính xác! Bạn đã giải xong bài tập này.' }
            : { tone: 'info', text: 'Đã đi hết lời giải. Lần giải này được tính là sai.' },
        )
        setPhase({ kind: 'done', correct })
        if (!failed) onLabelDecided()
        return
      }
      setFeedback({ tone: 'good', text: failed ? 'Đúng nước lời giải, đi tiếp.' : 'Đúng! Đi tiếp.' })
      setPhase({ kind: 'opponent' })
      later(() => {
        setFen(r.fen)
        setLastMove(r.opponent_move)
        setPhase({ kind: 'turn' })
      })
    } catch (err) {
      setFen(before)
      setLastMove(null)
      setFeedback({ tone: 'bad', text: err instanceof ApiError ? err.message : 'Mất kết nối máy chủ' })
      setPhase({ kind: 'turn' })
    }
  }

  /** Kéo thả thường và chọn quân phong cấp đều đi qua đây; trả về để bàn cờ giữ hay bật quân lại. */
  function tryMove(from: Square, to: Square, promotion?: string): boolean {
    if (phase.kind !== 'turn') return false
    const uci = localMove(from, to, promotion)
    if (!uci) return false
    void submit(uci)
    return true
  }

  function onPromotionPieceSelect(piece?: PromotionPieceOption, from?: Square, to?: Square): boolean {
    return piece !== undefined && from !== undefined && to !== undefined
      ? tryMove(from, to, piece[1].toLowerCase())
      : false
  }

  function isDraggablePiece({ piece }: { piece: Piece }): boolean {
    return phase.kind === 'turn' && attempt !== null && piece[0] === attempt.player_color[0]
  }

  if (phase.kind === 'intro') {
    return (
      <PlacementIntro
        total={phase.total}
        onStart={() => {
          introSeen.current = true
          setPracticeVersion((v) => v + 1)
          void loadNext()
        }}
      />
    )
  }

  if (phase.kind === 'error') {
    return (
      <section className="trainer">
        <p className="error" role="alert">
          {phase.message}
        </p>
        <button type="button" onClick={() => void loadNext()}>
          Thử lại
        </button>
      </section>
    )
  }

  const toMove = attempt?.player_color === 'black' ? 'Đen' : 'Trắng'
  return (
    <section className="trainer">
      <div className="board">
        <Chessboard
          position={fen}
          boardOrientation={attempt?.player_color ?? 'white'}
          onPieceDrop={(from, to) => tryMove(from, to)}
          onPromotionPieceSelect={onPromotionPieceSelect}
          isDraggablePiece={isDraggablePiece}
          customSquareStyles={highlight(lastMove)}
          customArrows={arrow}
          animationDuration={250}
        />
      </div>
      <aside className="panel">
        {attempt && (
          <p className="meta">
            Bài tập <code>{attempt.puzzle_id}</code> · rating {attempt.rating} · dự đoán bạn giải đúng{' '}
            {Math.round(attempt.predicted_p * 100)}%
          </p>
        )}
        <p className="turn">
          {phase.kind === 'loading' && 'Đang lấy bài tập…'}
          {phase.kind === 'opponent' && 'Đối thủ đang đi…'}
          {(phase.kind === 'turn' || phase.kind === 'sending') && `${toMove} đi. Tìm nước tốt nhất.`}
          {phase.kind === 'done' && (phase.correct ? 'Lần giải: đúng' : 'Lần giải: sai')}
        </p>
        {feedback && <p className={`feedback ${feedback.tone}`}>{feedback.text}</p>}
        {phase.kind === 'done' && (
          <button type="button" onClick={() => void loadNext()}>
            Bài tập tiếp theo
          </button>
        )}
        <PracticePanel
          version={practiceVersion}
          current={attempt?.puzzle_id ?? null}
          onPlacementDone={onPlacementDone}
        />
      </aside>
    </section>
  )
}

/** Màn hình trước bài kiểm tra đầu vào: giải thích ngắn và hỏi rating ván (không bắt buộc). */
function PlacementIntro({ total, onStart }: { total: number; onStart: () => void }) {
  const [rating, setRating] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function start(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (rating.trim()) {
      setBusy(true)
      try {
        await api.updateMe({ claimed_rating: Number(rating) })
      } catch (err) {
        setError(err instanceof ApiError ? 'Rating ván phải từ 400 đến 3000' : 'Không kết nối được máy chủ')
        setBusy(false)
        return
      }
    }
    onStart()
  }

  return (
    <section className="center">
      <form className="card" onSubmit={start}>
        <h1>Bài kiểm tra đầu vào</h1>
        <p>
          Trước khi luyện, bạn giải {total} bài tập, mỗi bài tập một kỹ năng. Kết quả giúp hệ thống biết bạn mạnh, yếu ở
          đâu để chọn bài tập vừa sức.
        </p>
        <label htmlFor="claimed-rating">
          Rating ván của bạn trên Lichess hoặc Chess.com (không bắt buộc)
          <input
            id="claimed-rating"
            type="number"
            inputMode="numeric"
            min={400}
            max={3000}
            placeholder="Ví dụ 1200"
            value={rating}
            onChange={(e) => setRating(e.target.value)}
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          Bắt đầu bài kiểm tra
        </button>
      </form>
    </section>
  )
}
