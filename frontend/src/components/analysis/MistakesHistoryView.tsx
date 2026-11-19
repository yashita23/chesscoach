import { useEffect, useState } from 'react'
import {
  api,
  type ListMistakesParams,
  type PlayerMistakeItemOut,
  type PlayerMistakesListOut,
} from '../../api'
import { getSkillNameVi, SKILL_NAMES_VI } from '../../utils/chessAnalysis'

export type MistakesHistoryViewProps = {
  onSelectMistake?: (gameId: number, mistakeId: number) => void
  initialParams?: ListMistakesParams
  limit?: number
}

const GAME_PHASE_NAMES_VI: Record<string, string> = {
  opening: 'Khai cuộc',
  middlegame: 'Trung cuộc',
  endgame: 'Tàn cuộc',
}

function getGamePhaseVi(phase: string): string {
  return GAME_PHASE_NAMES_VI[phase] ?? phase
}

function formatWinLoss(winLoss: number): string {
  return `${Math.abs(winLoss).toFixed(1)}%`
}

function formatDate(isoString: string): string {
  try {
    const d = new Date(isoString)
    if (isNaN(d.getTime())) return isoString
    return d.toLocaleDateString('vi-VN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoString
  }
}

/**
 * Sub-seam 5B: MistakesHistoryView
 * Bảng lịch sử lỗi chiến thuật của người chơi với bộ lọc 20 skills, 3 game phases, sắp xếp và phân trang.
 */
export function MistakesHistoryView({
  onSelectMistake,
  initialParams,
  limit = 20,
}: MistakesHistoryViewProps) {
  const [skillId, setSkillId] = useState<string>(initialParams?.skill_id ?? '')
  const [gamePhase, setGamePhase] = useState<string>(initialParams?.game_phase ?? '')
  const [orderBy, setOrderBy] = useState<
    'played_at_desc' | 'played_at_asc' | 'win_loss_desc' | 'win_loss_asc'
  >(initialParams?.order_by ?? 'played_at_desc')
  const [offset, setOffset] = useState<number>(initialParams?.offset ?? 0)

  const [data, setData] = useState<PlayerMistakesListOut | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)

    const params: ListMistakesParams = {
      limit,
      offset,
      order_by: orderBy,
    }
    if (skillId) params.skill_id = skillId
    if (gamePhase) {
      params.game_phase = gamePhase as 'opening' | 'middlegame' | 'endgame'
    }

    api
      .listPlayerMistakes(params)
      .then((res) => {
        if (!active) return
        setData(res)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Lỗi tải danh sách lỗi')
        setLoading(false)
      })

    return () => {
      active = false
    }
  }, [skillId, gamePhase, orderBy, offset, limit])

  const handleSkillChange = (newSkill: string) => {
    setSkillId(newSkill)
    setOffset(0)
  }

  const handlePhaseChange = (newPhase: string) => {
    setGamePhase(newPhase)
    setOffset(0)
  }

  const handleOrderChange = (
    newOrder: 'played_at_desc' | 'played_at_asc' | 'win_loss_desc' | 'win_loss_asc',
  ) => {
    setOrderBy(newOrder)
    setOffset(0)
  }

  const handleReset = () => {
    setSkillId('')
    setGamePhase('')
    setOrderBy('played_at_desc')
    setOffset(0)
  }

  const total = data?.total ?? 0
  const mistakes: PlayerMistakeItemOut[] = data?.mistakes ?? []
  const currentPage = Math.floor(offset / limit) + 1
  const totalPages = Math.max(1, Math.ceil(total / limit))

  const handlePrevPage = () => {
    setOffset((prev) => Math.max(0, prev - limit))
  }

  const handleNextPage = () => {
    setOffset((prev) => prev + limit)
  }

  return (
    <div className="mistakes-history-view" data-testid="mistakes-history-view">
      <header className="mistakes-history-header">
        <h2>Lịch sử sai lầm chiến thuật</h2>
        <div className="mistakes-summary">Tổng cộng: {total} lỗi</div>
      </header>

      {/* Thanh bộ lọc và sắp xếp */}
      <div className="mistakes-filters-bar" role="search">
        <div className="filter-group">
          <label htmlFor="skill-filter">Kỹ năng:</label>
          <select
            id="skill-filter"
            aria-label="Lọc theo kỹ năng"
            value={skillId}
            onChange={(e) => handleSkillChange(e.target.value)}
          >
            <option value="">Tất cả kỹ năng</option>
            {Object.entries(SKILL_NAMES_VI).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="phase-filter">Giai đoạn:</label>
          <select
            id="phase-filter"
            aria-label="Lọc theo giai đoạn"
            value={gamePhase}
            onChange={(e) => handlePhaseChange(e.target.value)}
          >
            <option value="">Tất cả giai đoạn</option>
            <option value="opening">Khai cuộc</option>
            <option value="middlegame">Trung cuộc</option>
            <option value="endgame">Tàn cuộc</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="order-filter">Sắp xếp:</label>
          <select
            id="order-filter"
            aria-label="Sắp xếp theo tiêu chí"
            value={orderBy}
            onChange={(e) =>
              handleOrderChange(
                e.target.value as
                  | 'played_at_desc'
                  | 'played_at_asc'
                  | 'win_loss_desc'
                  | 'win_loss_asc',
              )
            }
          >
            <option value="played_at_desc">Mới nhất</option>
            <option value="played_at_asc">Cũ nhất</option>
            <option value="win_loss_desc">Mất Win% nhiều nhất</option>
            <option value="win_loss_asc">Mất Win% ít nhất</option>
          </select>
        </div>

        <button
          type="button"
          className="btn-reset-filters"
          onClick={handleReset}
          aria-label="Đặt lại bộ lọc"
        >
          Đặt lại bộ lọc
        </button>
      </div>

      {/* Khu vực hiển thị trạng thái */}
      {loading && (
        <div role="status" className="loading-state">
          Đang tải danh sách lỗi...
        </div>
      )}

      {error && !loading && (
        <div role="alert" className="error-state">
          {error}
        </div>
      )}

      {!loading && !error && mistakes.length === 0 && (
        <div className="empty-state">Không tìm thấy lỗi nào phù hợp với bộ lọc.</div>
      )}

      {/* Bảng dữ liệu lỗi */}
      {!loading && !error && mistakes.length > 0 && (
        <div className="table-responsive">
          <table role="table" className="mistakes-table">
            <thead>
              <tr>
                <th scope="col">Nước đi</th>
                <th scope="col">Kỹ năng</th>
                <th scope="col">Giai đoạn</th>
                <th scope="col">Mất Win%</th>
                <th scope="col">Ngày đấu</th>
                <th scope="col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {mistakes.map((mistake) => (
                <tr key={`${mistake.game_id}-${mistake.id}`}>
                  <td className="cell-move">
                    <span className="move-san">{mistake.move_san || mistake.move_uci}</span>
                    <span className="move-number"> (nước {mistake.move_number})</span>
                  </td>
                  <td className="cell-skill">{getSkillNameVi(mistake.skill_id)}</td>
                  <td className="cell-phase">{getGamePhaseVi(mistake.game_phase)}</td>
                  <td className="cell-win-loss loss-negative">
                    -{formatWinLoss(mistake.win_loss)}
                  </td>
                  <td className="cell-date">{formatDate(mistake.played_at)}</td>
                  <td className="cell-actions">
                    <button
                      type="button"
                      className="btn-view-mistake"
                      onClick={() => onSelectMistake?.(mistake.game_id, mistake.id)}
                      aria-label={`Xem ván cờ ${mistake.game_id}`}
                    >
                      Xem ván cờ
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Điều khiển phân trang */}
      {!error && total > 0 && (
        <div className="pagination-bar" aria-label="Điều hướng phân trang">
          <button
            type="button"
            className="btn-page"
            disabled={offset === 0 || loading}
            onClick={handlePrevPage}
            aria-label="Trang trước"
          >
            Trang trước
          </button>
          <span className="pagination-info">
            Trang {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            className="btn-page"
            disabled={offset + limit >= total || loading}
            onClick={handleNextPage}
            aria-label="Trang sau"
          >
            Trang sau
          </button>
        </div>
      )}
    </div>
  )
}
