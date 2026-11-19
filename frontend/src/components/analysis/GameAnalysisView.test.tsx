import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { api, type GameAnalysisOut, type MistakeOut } from '../../api'
import GameAnalysisView from './GameAnalysisView'

// Thế cờ 1 (Đen đi - Scotch Gambit): 4... d6? ('d7d6'), best: 4... Nf6 ('g8f6'), refutation: 5. Ng5 ('f3g5')
const MOCK_MISTAKE_1: MistakeOut = {
  id: 101,
  ply: 8,
  move_number: 4,
  move_san: 'd6',
  move_uci: 'd7d6',
  fen: 'r1bqkbnr/pppp1ppp/2n5/8/2BpP3/5N2/PPP2PPP/RNBQK2R b KQkq - 1 4',
  win_before: 65.0,
  win_after: 38.0,
  win_loss: 27.0,
  skill_id: 'hanging_piece',
  motif: 'hanging_piece',
  game_phase: 'opening',
  best_move: 'g8f6',
  refutation_move: 'f3g5',
}

// Thế cờ 2 (Trắng đi): 4. dxe5 ('d4e5'), best: 4. Bc4 ('f1c4'), refutation: 4... dxe5 ('d6e5')
const MOCK_MISTAKE_2: MistakeOut = {
  id: 102,
  ply: 7,
  move_number: 4,
  move_san: 'dxe5',
  move_uci: 'd4e5',
  fen: 'r1bqkbnr/ppp2ppp/2np4/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R w KQkq - 0 4',
  win_before: 55.0,
  win_after: 20.0,
  win_loss: 35.0,
  skill_id: 'fork',
  motif: 'fork',
  game_phase: 'middlegame',
  best_move: 'f1c4',
  refutation_move: 'd6e5',
}

// Thế cờ 3 (Trắng đi): 5. Qe2 ('d1e2'), best: 5. Bc4 ('f1c4'), refutation: 5... Bg4 ('c8g4')
const MOCK_MISTAKE_3: MistakeOut = {
  id: 103,
  ply: 9,
  move_number: 5,
  move_san: 'Qe2',
  move_uci: 'd1e2',
  fen: 'r1bqkbnr/ppp2ppp/2np4/4P3/4P3/5N2/PPP2PPP/RNBQKB1R w KQkq - 0 5',
  win_before: 50.0,
  win_after: 28.0,
  win_loss: 22.0,
  skill_id: 'pin',
  motif: 'pin',
  game_phase: 'opening',
  best_move: 'f1c4',
  refutation_move: 'c8g4',
}

const MOCK_COMPLETED_GAME_1: GameAnalysisOut = {
  game_id: 42,
  platform: 'lichess',
  platform_game_id: 'test_game_42',
  perf_type: 'rapid',
  played_at: '2026-11-10T12:00:00Z',
  analysis_status: 'completed',
  analyzed_at: '2026-11-10T12:05:00Z',
  mistakes: [MOCK_MISTAKE_1, MOCK_MISTAKE_2],
}

// Game 99 có ít nhất 2 mistakes để chứng minh selectedIdx được reset về 0 (chọn MOCK_MISTAKE_2 thay vì MOCK_MISTAKE_3)
const MOCK_COMPLETED_GAME_2: GameAnalysisOut = {
  game_id: 99,
  platform: 'lichess',
  platform_game_id: 'test_game_99',
  perf_type: 'blitz',
  played_at: '2026-11-11T15:00:00Z',
  analysis_status: 'completed',
  analyzed_at: '2026-11-11T15:05:00Z',
  mistakes: [MOCK_MISTAKE_2, MOCK_MISTAKE_3],
}

const MOCK_PERFECT_GAME: GameAnalysisOut = {
  ...MOCK_COMPLETED_GAME_1,
  game_id: 43,
  mistakes: [],
}

const MOCK_PENDING_GAME: GameAnalysisOut = {
  ...MOCK_COMPLETED_GAME_1,
  game_id: 44,
  analysis_status: 'pending',
  mistakes: [],
}

describe('GameAnalysisView - Component Tests', () => {
  it('11. Hiển thị chi tiết lỗi của nước đi đang chọn: tên kỹ năng tiếng Việt, motif, win loss, giai đoạn', () => {
    render(<GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />)

    // Hiển thị nước đi trong tiêu đề chi tiết lỗi
    expect(screen.getByRole('heading', { name: /d6/i })).toBeInTheDocument()
    // Hiển thị tổn thất Win% (-27.0%)
    expect(screen.getByText(/-27(\.0)?%/)).toBeInTheDocument()
    // Hiển thị tên kỹ năng tiếng Việt (Quân treo) thay vì ID nội bộ
    expect(screen.getByText(/Quân treo/i)).toBeInTheDocument()
    // Hiển thị motif chiến thuật
    expect(screen.getByText(/hanging_piece/i)).toBeInTheDocument()
    // Hiển thị giai đoạn ván cờ
    expect(screen.getByText(/opening/i)).toBeInTheDocument()
  })

  it('12. Chuyển đổi giữa 2 chế độ: Thế cờ trước lỗi và Phản đòn của đối thủ', () => {
    render(<GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />)

    const mistakeTab = screen.getByRole('button', { name: /thế cờ trước lỗi|nước đã đi/i })
    const refutationTab = screen.getByRole('button', { name: /phản đòn|nước đối thủ/i })

    expect(mistakeTab).toBeInTheDocument()
    expect(refutationTab).toBeInTheDocument()

    // Click xem phản đòn
    fireEvent.click(refutationTab)
    expect(screen.getByText(/f3g5/i)).toBeInTheDocument()

    // Click quay lại thế cờ trước lỗi
    fireEvent.click(mistakeTab)
    expect(screen.getByText(/g8f6/i)).toBeInTheDocument()
  })

  it('13. MistakeSelector: Chuyển đổi qua lại giữa các lỗi trong ván cờ', () => {
    render(<GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />)

    // Ban đầu chọn lỗi 1 (d6)
    expect(screen.getByRole('heading', { name: /d6/i })).toBeInTheDocument()

    // Click chọn lỗi 2 (dxe5)
    const mistake2Btn = screen.getByRole('button', { name: /dxe5|lỗi 2/i })
    fireEvent.click(mistake2Btn)

    // Cập nhật chi tiết sang lỗi 2
    expect(screen.getByRole('heading', { name: /dxe5/i })).toBeInTheDocument()
    expect(screen.getByText(/-35(\.0)?%/)).toBeInTheDocument()
    expect(screen.getByText(/Fork \(đòn đôi\)/i)).toBeInTheDocument()
    expect(screen.getByText(/middlegame/i)).toBeInTheDocument()
  })

  it('14. Hiển thị thông báo trạng thái khi ván completed nhưng không có lỗi', () => {
    render(<GameAnalysisView gameId={43} initialData={MOCK_PERFECT_GAME} />)

    expect(
      screen.getByText(/không phát hiện sai lầm|không có lỗi/i)
    ).toBeInTheDocument()
  })

  it('15. Nút Lật bàn cờ (Flip Board) cho phép đảo chiều góc nhìn', () => {
    render(<GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />)

    const boardContainer = screen.getByTestId('analysis-board-wrapper')
    // Vì MOCK_MISTAKE_1 là lượt Đen ('b'), ban đầu orientation là 'black'
    expect(boardContainer).toHaveAttribute('data-orientation', 'black')

    const flipBtn = screen.getByRole('button', { name: /lật bàn cờ|flip/i })
    expect(flipBtn).toBeInTheDocument()

    // Bấm lật bàn cờ
    fireEvent.click(flipBtn)
    // Sau khi bấm, trạng thái orientation đổi sang 'white'
    expect(boardContainer).toHaveAttribute('data-orientation', 'white')
  })

  it('16. Xử lý các trạng thái chưa hoàn tất phân tích (pending/analyzing)', () => {
    render(<GameAnalysisView gameId={44} initialData={MOCK_PENDING_GAME} />)

    expect(screen.getByText(/đang chờ phân tích|chưa phân tích/i)).toBeInTheDocument()
  })

  it('17. Reset toàn bộ state (selectedIdx, mode, userOrientation) khi gameId thay đổi', () => {
    const { rerender } = render(
      <GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />
    )

    // Ở game 42: chuyển sang lỗi 2 (index 1: dxe5), bật chế độ refutation, bấm flip board
    fireEvent.click(screen.getByRole('button', { name: /dxe5|lỗi 2/i }))
    expect(screen.getByRole('heading', { name: /dxe5/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /phản đòn/i }))
    fireEvent.click(screen.getByRole('button', { name: /lật bàn cờ/i }))

    // Rerender sang game khác: gameId 99 (có 2 lỗi: [0] là dxe5, [1] là Qe2)
    rerender(<GameAnalysisView gameId={99} initialData={MOCK_COMPLETED_GAME_2} />)

    // Tiêu đề game đã đổi sang #99
    expect(screen.getByText(/phân tích ván cờ #99/i)).toBeInTheDocument()

    // Chứng minh selectedIdx thực sự trở về 0:
    // Game 99 hiển thị lỗi đầu tiên (dxe5), KHÔNG PHẢI lỗi thứ hai (Qe2)
    expect(screen.getByRole('heading', { name: /dxe5/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Qe2/i })).not.toBeInTheDocument()

    // Chế độ được reset về mặc định 'Thế cờ trước lỗi'
    const mistakeTab = screen.getByRole('button', { name: /thế cờ trước lỗi/i })
    expect(mistakeTab).not.toHaveClass('link') // tab được active (không có class 'link')

    // Hướng bàn cờ được reset theo FEN mới của game 99 (lượt Trắng 'w' -> 'white')
    const boardWrapper = screen.getByTestId('analysis-board-wrapper')
    expect(boardWrapper).toHaveAttribute('data-orientation', 'white')
  })

  it('18. Ngăn chặn race condition: stale response của game cũ đến sau không ghi đè game mới', async () => {
    let resolveGame42: (value: GameAnalysisOut) => void = () => {}
    let resolveGame99: (value: GameAnalysisOut) => void = () => {}

    const game42Promise = new Promise<GameAnalysisOut>((resolve) => {
      resolveGame42 = resolve
    })
    const game99Promise = new Promise<GameAnalysisOut>((resolve) => {
      resolveGame99 = resolve
    })

    const spy = vi.spyOn(api, 'getGameAnalysis').mockImplementation((id: number) => {
      if (id === 42) return game42Promise
      if (id === 99) return game99Promise
      return Promise.reject(new Error('Unknown gameId'))
    })

    // 1. Render game 42 (không có initialData -> gọi api.getGameAnalysis(42))
    const { rerender } = render(<GameAnalysisView gameId={42} />)
    expect(screen.getByText(/đang tải dữ liệu phân tích/i)).toBeInTheDocument()

    // 2. Chuyển sang game 99 trong khi request của game 42 vẫn đang chờ
    rerender(<GameAnalysisView gameId={99} />)

    // 3. Cho request của game 99 hoàn tất trước
    await act(async () => {
      resolveGame99(MOCK_COMPLETED_GAME_2)
    })

    // UI đã cập nhật và hiển thị game 99
    expect(screen.getByText(/phân tích ván cờ #99/i)).toBeInTheDocument()

    // 4. Bây giờ mới cho request cũ của game 42 hoàn tất muộn
    await act(async () => {
      resolveGame42(MOCK_COMPLETED_GAME_1)
    })

    // 5. Xác nhận UI vẫn hiển thị game 99, KHÔNG bị response cũ của game 42 ghi đè!
    expect(screen.getByText(/phân tích ván cờ #99/i)).toBeInTheDocument()
    expect(screen.queryByText(/phân tích ván cờ #42/i)).not.toBeInTheDocument()

    spy.mockRestore()
  })

  it('19. Cập nhật giao diện khi initialData của cùng gameId thay đổi', () => {
    // Render ban đầu với game 42 ở trạng thái pending
    const { rerender } = render(
      <GameAnalysisView
        gameId={42}
        initialData={{ ...MOCK_PENDING_GAME, game_id: 42 }}
      />
    )
    expect(screen.getByText(/ván cờ đang chờ phân tích/i)).toBeInTheDocument()

    // Cùng gameId=42 nhưng initialData đã được cập nhật sang completed (MOCK_COMPLETED_GAME_1)
    rerender(
      <GameAnalysisView gameId={42} initialData={MOCK_COMPLETED_GAME_1} />
    )

    // UI lập tức cập nhật sang dữ liệu completed mới
    expect(screen.queryByText(/ván cờ đang chờ phân tích/i)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /d6/i })).toBeInTheDocument()
  })
})
