import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  api,
  type GameAnalysisOut,
  type Player,
  type PlayerMistakesListOut,
  type Profile,
} from './api'
import App from './App'

const MOCK_PLAYER: Player = {
  email: 'test@chesscoach.vn',
  display_name: 'Kỳ Thủ Thử Nghiệm',
  daily_minutes: 15,
  claimed_rating: 1500,
}

const MOCK_MISTAKE_LIST: PlayerMistakesListOut = {
  total: 2,
  mistakes: [
    {
      id: 101,
      game_id: 42,
      platform: 'lichess',
      platform_game_id: 'lich_042',
      ply: 12,
      move_number: 6,
      move_san: 'Nxd4',
      move_uci: 'c6d4',
      fen: 'r1bqkbnr/pppp1ppp/2n5/8/2BpP3/5N2/PPP2PPP/RNBQK2R b KQkq - 1 4',
      win_before: 45.0,
      win_after: 15.0,
      win_loss: 30.0,
      skill_id: 'hanging_piece',
      motif: 'hanging_piece',
      game_phase: 'opening',
      best_move: 'g8f6',
      refutation_move: 'f3g5',
      played_at: '2026-11-15T10:00:00Z',
    },
    {
      id: 102,
      game_id: 99,
      platform: 'lichess',
      platform_game_id: 'lich_099',
      ply: 28,
      move_number: 14,
      move_san: 'Qe2',
      move_uci: 'd1e2',
      fen: 'r1bq1rk1/ppp2ppp/2np4/4p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 w - - 0 7',
      win_before: 60.0,
      win_after: 25.0,
      win_loss: 35.0,
      skill_id: 'fork',
      motif: 'fork',
      game_phase: 'middlegame',
      best_move: 'c1g5',
      refutation_move: 'c6d4',
      played_at: '2026-11-16T14:30:00Z',
    },
  ],
}

const MOCK_GAME_42_ANALYSIS: GameAnalysisOut = {
  game_id: 42,
  platform: 'lichess',
  platform_game_id: 'lich_042',
  perf_type: 'blitz',
  played_at: '2026-11-15T10:00:00Z',
  analysis_status: 'completed',
  analyzed_at: '2026-11-15T10:05:00Z',
  mistakes: [
    {
      id: 101,
      ply: 12,
      move_number: 6,
      move_san: 'Nxd4',
      move_uci: 'c6d4',
      fen: 'r1bqkbnr/pppp1ppp/2n5/8/2BpP3/5N2/PPP2PPP/RNBQK2R b KQkq - 1 4',
      win_before: 45.0,
      win_after: 15.0,
      win_loss: 30.0,
      skill_id: 'hanging_piece',
      motif: 'hanging_piece',
      game_phase: 'opening',
      best_move: 'g8f6',
      refutation_move: 'f3g5',
    },
  ],
}

const MOCK_PROFILE: Profile = {
  theta: 1500,
  ci: { low: 1400, high: 1600 },
  attempts: 20,
  skills: [],
  groups: [],
}

describe('App Integration: Issue #8 (Phân tích ván cờ)', () => {
  let listMistakesSpy: ReturnType<typeof vi.spyOn>
  let getAnalysisSpy: ReturnType<typeof vi.spyOn>
  let profileSpy: ReturnType<typeof vi.spyOn>
  let nextPuzzleSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.spyOn(api, 'me').mockResolvedValue(MOCK_PLAYER)
    listMistakesSpy = vi.spyOn(api, 'listPlayerMistakes').mockResolvedValue(MOCK_MISTAKE_LIST)
    getAnalysisSpy = vi.spyOn(api, 'getGameAnalysis').mockResolvedValue(MOCK_GAME_42_ANALYSIS)
    profileSpy = vi.spyOn(api, 'profile').mockResolvedValue(MOCK_PROFILE)
    vi.spyOn(api, 'practice').mockResolvedValue({
      mode: 'practice',
      placement: null,
      daily_minutes: 15,
      size: 1,
      target_rating: 1500,
      items: [],
    })
    nextPuzzleSpy = vi.spyOn(api, 'nextPuzzle').mockResolvedValue({ puzzle_id: 'puz_001' })
    vi.spyOn(api, 'getAccounts').mockResolvedValue([])
    vi.spyOn(api, 'getSyncStatus').mockResolvedValue({
      status: 'idle',
      platform: 'lichess',
      current: 0,
      total: 0,
      new_games_count: 0,
      error: null,
      last_synced_at: null,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('1. Tab Navigation: Hiển thị tab "Phân tích ván cờ" trên thanh điều hướng', async () => {
    render(<App />)

    // Chờ người dùng đăng nhập xong và render thanh điều hướng
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: /màn hình/i })
    expect(within(nav).getByRole('button', { name: /luyện tập/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /hồ sơ kỹ năng/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /phân tích ván cờ/i })).toBeInTheDocument()

    // Mặc định tab Luyện tập đang active
    expect(within(nav).getByRole('button', { name: /luyện tập/i })).toHaveAttribute(
      'aria-current',
      'true',
    )
    expect(within(nav).getByRole('button', { name: /phân tích ván cờ/i })).toHaveAttribute(
      'aria-current',
      'false',
    )
  })

  it('2. Default View: Mặc định hiển thị MistakesHistoryView khi chọn tab Phân tích ván cờ', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    const analysisTabBtn = screen.getByRole('button', { name: /phân tích ván cờ/i })
    fireEvent.click(analysisTabBtn)

    // Tab Phân tích ván cờ trở thành active
    expect(analysisTabBtn).toHaveAttribute('aria-current', 'true')

    // Hiển thị giao diện Lịch sử sai lầm chiến thuật
    expect(await screen.findByRole('heading', { name: /lịch sử sai lầm chiến thuật/i })).toBeInTheDocument()
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByText(/tổng cộng: 2 lỗi/i)).toBeInTheDocument()

    // Xác nhận gọi đúng API danh sách lỗi
    expect(listMistakesSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        limit: 20,
        offset: 0,
        order_by: 'played_at_desc',
      }),
    )
  })

  it('3. Navigation Flow: Click "Xem ván cờ" chuyển sang GameAnalysisView của đúng game được chọn', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    // Chuyển sang tab Phân tích
    fireEvent.click(screen.getByRole('button', { name: /phân tích ván cờ/i }))

    // Tìm nút "Xem ván cờ" của ván 42
    const viewGame42Btn = await screen.findByRole('button', { name: /xem ván cờ 42/i })
    expect(viewGame42Btn).toBeInTheDocument()

    // Click xem ván cờ 42
    fireEvent.click(viewGame42Btn)

    // Xác nhận gọi API chi tiết ván 42 đúng 1 lần với tham số chính xác
    await waitFor(() => {
      expect(getAnalysisSpy).toHaveBeenCalledTimes(1)
      expect(getAnalysisSpy).toHaveBeenCalledWith(42)
    })

    // Giao diện chuyển sang GameAnalysisView (hiển thị chi tiết ván 42)
    expect(await screen.findByText(/ván cờ #42/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /quay lại danh sách/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /lật bàn cờ/i })).toBeInTheDocument()
  })

  it('4. Back Navigation: Click "Quay lại danh sách" đưa người dùng trở về MistakesHistoryView', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    // Vào tab Phân tích -> Mở ván 42
    fireEvent.click(screen.getByRole('button', { name: /phân tích ván cờ/i }))
    const viewBtn = await screen.findByRole('button', { name: /xem ván cờ 42/i })
    fireEvent.click(viewBtn)

    // Chờ giao diện phân tích ván 42 hiển thị hoàn tất
    expect(await screen.findByText(/ván cờ #42/i)).toBeInTheDocument()
    const backBtn = screen.getByRole('button', { name: /quay lại danh sách/i })
    expect(backBtn).toBeInTheDocument()

    // Click nút quay lại
    fireEvent.click(backBtn)

    // Trở về giao diện Lịch sử sai lầm
    expect(await screen.findByRole('heading', { name: /lịch sử sai lầm chiến thuật/i })).toBeInTheDocument()
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('5. Existing Tabs Preservation: Hai tab Luyện tập và Hồ sơ kỹ năng vẫn hoạt động bình thường', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    // Chuyển sang Hồ sơ kỹ năng
    const profileTabBtn = screen.getByRole('button', { name: /hồ sơ kỹ năng/i })
    fireEvent.click(profileTabBtn)
    expect(profileTabBtn).toHaveAttribute('aria-current', 'true')
    await waitFor(() => {
      expect(profileSpy).toHaveBeenCalled()
    })

    // Chuyển lại về Luyện tập
    const trainTabBtn = screen.getByRole('button', { name: /luyện tập/i })
    fireEvent.click(trainTabBtn)
    expect(trainTabBtn).toHaveAttribute('aria-current', 'true')
    await waitFor(() => {
      expect(nextPuzzleSpy).toHaveBeenCalled()
    })

    // Chuyển sang Phân tích ván cờ rồi quay lại
    const analysisTabBtn = screen.getByRole('button', { name: /phân tích ván cờ/i })
    fireEvent.click(analysisTabBtn)
    expect(analysisTabBtn).toHaveAttribute('aria-current', 'true')
    expect(await screen.findByRole('heading', { name: /lịch sử sai lầm chiến thuật/i })).toBeInTheDocument()

    fireEvent.click(trainTabBtn)
    expect(trainTabBtn).toHaveAttribute('aria-current', 'true')
  })

  it('6. Tab Re-click: Click lại tab Phân tích ván cờ khi đang xem chi tiết ván cờ sẽ quay lại danh sách', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    const analysisTabBtn = screen.getByRole('button', { name: /phân tích ván cờ/i })
    fireEvent.click(analysisTabBtn)

    // Mở ván 42
    const viewBtn = await screen.findByRole('button', { name: /xem ván cờ 42/i })
    fireEvent.click(viewBtn)
    expect(await screen.findByText(/ván cờ #42/i)).toBeInTheDocument()

    // Click lại tab "Phân tích ván cờ" trên topbar
    fireEvent.click(analysisTabBtn)

    // Quay lại màn hình danh sách lỗi
    expect(await screen.findByRole('heading', { name: /lịch sử sai lầm chiến thuật/i })).toBeInTheDocument()
  })

  it('7. Game Persistence Across Tabs: Giữ nguyên ván đang xem khi chuyển sang Hồ sơ kỹ năng rồi quay lại', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    // 1. Vào tab Phân tích -> Mở ván 42
    const analysisTabBtn = screen.getByRole('button', { name: /phân tích ván cờ/i })
    fireEvent.click(analysisTabBtn)

    const viewBtn = await screen.findByRole('button', { name: /xem ván cờ 42/i })
    fireEvent.click(viewBtn)
    expect(await screen.findByText(/ván cờ #42/i)).toBeInTheDocument()

    // 2. Chuyển sang tab Hồ sơ kỹ năng
    const profileTabBtn = screen.getByRole('button', { name: /hồ sơ kỹ năng/i })
    fireEvent.click(profileTabBtn)
    expect(profileTabBtn).toHaveAttribute('aria-current', 'true')

    // 3. Quay lại tab Phân tích ván cờ
    fireEvent.click(analysisTabBtn)
    expect(analysisTabBtn).toHaveAttribute('aria-current', 'true')

    // 4. Ván cờ 42 vẫn được giữ nguyên trên giao diện, không bị reset về danh sách
    expect(await screen.findByText(/ván cờ #42/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /quay lại danh sách/i })).toBeInTheDocument()
  })

  it('8. App-level Fast Navigation: Chuyển tab liên tục khi API đang tải không gây crash hay stale state', async () => {
    render(<App />)
    expect(await screen.findByText('Kỳ Thủ Thử Nghiệm')).toBeInTheDocument()

    const trainTabBtn = screen.getByRole('button', { name: /luyện tập/i })
    const profileTabBtn = screen.getByRole('button', { name: /hồ sơ kỹ năng/i })
    const analysisTabBtn = screen.getByRole('button', { name: /phân tích ván cờ/i })

    // Click liên tục giữa các tab
    fireEvent.click(analysisTabBtn)
    fireEvent.click(profileTabBtn)
    fireEvent.click(trainTabBtn)
    fireEvent.click(analysisTabBtn)

    // Cuối cùng vẫn ở đúng tab Phân tích ván cờ và hiển thị danh sách lỗi an toàn
    expect(analysisTabBtn).toHaveAttribute('aria-current', 'true')
    expect(await screen.findByRole('heading', { name: /lịch sử sai lầm chiến thuật/i })).toBeInTheDocument()
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})
