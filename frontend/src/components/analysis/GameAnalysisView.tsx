import { useEffect, useState } from 'react'
import { Chessboard } from 'react-chessboard'
import { api, ApiError, type GameAnalysisOut } from '../../api'
import {
  calculateArrows,
  getAnalysisFen,
  getBoardOrientation,
  getSkillNameVi,
  type PlayerColor,
} from '../../utils/chessAnalysis'

export type GameAnalysisViewProps = {
  gameId: number
  onBack?: () => void
  initialData?: GameAnalysisOut
}

export default function GameAnalysisView({
  gameId,
  onBack,
  initialData,
}: GameAnalysisViewProps) {
  const [data, setData] = useState<GameAnalysisOut | null>(
    initialData && initialData.game_id === gameId ? initialData : null
  )
  const [loading, setLoading] = useState(
    !(initialData && initialData.game_id === gameId)
  )
  const [error, setError] = useState<string | null>(null)
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [mode, setMode] = useState<'mistake' | 'refutation'>('mistake')
  const [userOrientation, setUserOrientation] = useState<PlayerColor | null>(null)

  useEffect(() => {
    let active = true

    // Luôn reset toàn bộ state điều khiển khi gameId thay đổi
    setSelectedIdx(0)
    setMode('mistake')
    setUserOrientation(null)

    if (initialData && initialData.game_id === gameId) {
      setData(initialData)
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    setError(null)
    setData(null)

    api
      .getGameAnalysis(gameId)
      .then((res) => {
        if (!active) return
        setData(res)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof ApiError ? err.message : 'Không tải được phân tích ván cờ')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [gameId, initialData])

  if (loading) {
    return (
      <section className="center">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <p>Đang tải dữ liệu phân tích ván cờ…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel card">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <p className="error" role="alert">
          {error}
        </p>
      </section>
    )
  }

  if (!data) return null

  // 1. Xử lý các trạng thái chưa hoàn tất phân tích
  if (data.analysis_status === 'pending' || data.analysis_status === 'analyzing') {
    return (
      <section className="card">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <h2>Trạng thái phân tích</h2>
        <p className="notice" role="status">
          Ván cờ đang chờ phân tích. Vui lòng quay lại sau ít phút.
        </p>
      </section>
    )
  }

  if (data.analysis_status === 'failed') {
    return (
      <section className="card">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <h2>Phân tích thất bại</h2>
        <p className="error" role="alert">
          Không thể phân tích ván cờ này. Vui lòng thử đồng bộ lại sau.
        </p>
      </section>
    )
  }

  // 2. Ván cờ completed nhưng không có sai lầm nào
  if (data.mistakes.length === 0) {
    return (
      <section className="card">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <h2>Kết quả phân tích</h2>
        <p className="notice" role="status">
          Xuất sắc! Hệ thống không phát hiện sai lầm chiến thuật đáng kể nào trong ván đấu này.
        </p>
      </section>
    )
  }

  // 3. Ván cờ completed và có danh sách lỗi
  const mistakes = data.mistakes
  const currentMistake = mistakes[selectedIdx] ?? mistakes[0]

  // Xác định hướng bàn cờ: suy ra từ FEN thế cờ hoặc override bởi nút Flip Board
  const derivedOrientation = getBoardOrientation(currentMistake.fen)
  const orientation = userOrientation ?? derivedOrientation

  const displayFen = getAnalysisFen(mode, currentMistake)
  const arrows = calculateArrows(mode, currentMistake)

  const toggleOrientation = () => {
    setUserOrientation((prev) => {
      const current = prev ?? derivedOrientation
      return current === 'white' ? 'black' : 'white'
    })
  }

  return (
    <div className="game-analysis-view">
      <header className="analysis-header">
        {onBack && (
          <button
            type="button"
            className="link btn-back-to-list"
            onClick={onBack}
            aria-label="Quay lại danh sách"
          >
            ← Quay lại danh sách
          </button>
        )}
        <h2>Phân tích ván cờ #{data.game_id}</h2>
        <p className="meta">
          Nền tảng: <strong>{data.platform}</strong> · Thể loại: <strong>{data.perf_type}</strong> · Phát hiện{' '}
          <strong>{mistakes.length} lỗi chiến thuật</strong>
        </p>
      </header>

      <div className="trainer">
        {/* Cột trái: Bàn cờ và các nút thao tác góc nhìn */}
        <div className="board-column">
          <div
            data-testid="analysis-board-wrapper"
            data-orientation={orientation}
            className="board"
          >
            <Chessboard
              position={displayFen}
              boardOrientation={orientation}
              arePiecesDraggable={false}
              customArrows={arrows}
              animationDuration={150}
            />
          </div>

          <div className="board-controls form-row" style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
            <button
              type="button"
              className={mode === 'mistake' ? '' : 'link'}
              onClick={() => setMode('mistake')}
            >
              Thế cờ trước lỗi
            </button>
            <button
              type="button"
              className={mode === 'refutation' ? '' : 'link'}
              onClick={() => setMode('refutation')}
            >
              Phản đòn của đối thủ
            </button>
            <button type="button" className="link" onClick={toggleOrientation} title="Đảo góc nhìn bàn cờ">
              Lật bàn cờ 🔄
            </button>
          </div>
        </div>

        {/* Cột phải: Selector các lỗi và Chi tiết sai lầm */}
        <aside className="panel">
          {/* Mistake Selector */}
          <div className="mistake-selector card" style={{ maxWidth: '100%' }}>
            <h3>Danh sách lỗi ({mistakes.length})</h3>
            <div className="selector-buttons" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {mistakes.map((m, idx) => {
                const isSelected = idx === selectedIdx
                return (
                  <button
                    key={m.id}
                    type="button"
                    className={isSelected ? '' : 'link'}
                    style={{
                      border: isSelected ? '2px solid var(--accent)' : '1px solid var(--border)',
                      padding: '6px 10px',
                      fontSize: '0.85rem',
                    }}
                    onClick={() => {
                      setSelectedIdx(idx)
                      setMode('mistake')
                    }}
                  >
                    #{idx + 1}: {m.move_san}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Mistake Detail Panel */}
          <div className="mistake-detail card" style={{ maxWidth: '100%', marginTop: '12px' }}>
            <h3>
              Nước #{currentMistake.move_number}: <code>{currentMistake.move_san}</code> ({currentMistake.move_uci})
            </h3>
            <p className="error" style={{ fontSize: '1.05rem', fontWeight: 600 }}>
              Tổn thất: -{Math.abs(currentMistake.win_loss).toFixed(1)}% tỉ lệ thắng
            </p>

            <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <li>
                <strong>Kỹ năng:</strong> <span>{getSkillNameVi(currentMistake.skill_id)}</span>
              </li>
              <li>
                <strong>Motif chiến thuật:</strong> <span>{currentMistake.motif}</span>
              </li>
              <li>
                <strong>Giai đoạn:</strong> <span>{currentMistake.game_phase}</span>
              </li>
              <li>
                <strong>Tỉ lệ thắng:</strong> {currentMistake.win_before.toFixed(1)}% → {currentMistake.win_after.toFixed(1)}%
              </li>
              {currentMistake.best_move && (
                <li>
                  <strong style={{ color: 'var(--accent)' }}>Nước tốt nhất (Best Move):</strong>{' '}
                  <code>{currentMistake.best_move}</code>
                </li>
              )}
              {currentMistake.refutation_move && (
                <li>
                  <strong style={{ color: '#d97706' }}>Nước đối thủ phản đòn (Refutation):</strong>{' '}
                  <code>{currentMistake.refutation_move}</code>
                </li>
              )}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  )
}
