import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, type PlayerMistakeItemOut, type PlayerMistakesListOut } from '../../api'
import { MistakesHistoryView } from './MistakesHistoryView'

const MOCK_MISTAKE_1: PlayerMistakeItemOut = {
  id: 101,
  game_id: 1,
  platform: 'lichess',
  platform_game_id: 'lich_001',
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
}

const MOCK_MISTAKE_2: PlayerMistakeItemOut = {
  id: 102,
  game_id: 2,
  platform: 'lichess',
  platform_game_id: 'lich_002',
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
}

const MOCK_MISTAKE_3: PlayerMistakeItemOut = {
  id: 103,
  game_id: 3,
  platform: 'lichess',
  platform_game_id: 'lich_003',
  ply: 54,
  move_number: 27,
  move_san: 'Ke4',
  move_uci: 'e3e4',
  fen: '8/5k2/8/8/4K3/8/8/8 w - - 0 35',
  win_before: 50.0,
  win_after: 0.0,
  win_loss: 50.0,
  skill_id: 'pawn_endgame',
  motif: 'pawn_endgame',
  game_phase: 'endgame',
  best_move: 'e3f4',
  refutation_move: 'f7e6',
  played_at: '2026-11-17T09:15:00Z',
}

const MOCK_DEFAULT_RESPONSE: PlayerMistakesListOut = {
  total: 3,
  mistakes: [MOCK_MISTAKE_1, MOCK_MISTAKE_2, MOCK_MISTAKE_3],
}

describe('Sub-seam 5B: MistakesHistoryView', () => {
  let listSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    listSpy = vi.spyOn(api, 'listPlayerMistakes').mockResolvedValue(MOCK_DEFAULT_RESPONSE)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('1. Rendering & Table structure', () => {
    it('Test 1: renders mistakes table with mistake details (move, skill tiếng Việt, phase, win loss, date)', async () => {
      render(<MistakesHistoryView />)

      // Chờ bảng dữ liệu xuất hiện
      const table = await screen.findByRole('table')
      expect(table).toBeInTheDocument()

      // Kiểm tra các cột tiêu đề
      expect(screen.getByRole('columnheader', { name: /nước đi/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /kỹ năng/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /giai đoạn/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /mất win%/i })).toBeInTheDocument()

      // Kiểm tra dòng dữ liệu mistake 1 trong bảng (thang 0-100: win_loss=30.0 -> hiển thị -30.0%, tuyệt đối không phải -3000.0%)
      expect(within(table).getByText('Nxd4')).toBeInTheDocument()
      expect(within(table).getByText('Quân treo')).toBeInTheDocument()
      expect(within(table).getByText(/khai cuộc/i)).toBeInTheDocument()
      expect(within(table).getByText('-30.0%')).toBeInTheDocument()
      expect(within(table).queryByText('-3000.0%')).not.toBeInTheDocument()

      // Kiểm tra dòng dữ liệu mistake 2 trong bảng (thang 0-100: win_loss=35.0 -> hiển thị -35.0%, không phải -3500.0%)
      expect(within(table).getByText('Qe2')).toBeInTheDocument()
      expect(within(table).getByText('Fork (đòn đôi)')).toBeInTheDocument()
      expect(within(table).getByText(/trung cuộc/i)).toBeInTheDocument()
      expect(within(table).getByText('-35.0%')).toBeInTheDocument()
      expect(within(table).queryByText('-3500.0%')).not.toBeInTheDocument()
    })

    it('Test 2: displays total mistake count summary', async () => {
      render(<MistakesHistoryView />)

      // Hiển thị tổng số lỗi đã ghi nhận
      expect(await screen.findByText(/tổng cộng.*3.*lỗi/i)).toBeInTheDocument()
    })
  })

  describe('2. Skill Filter (20 kỹ năng)', () => {
    it('Test 3: renders skill dropdown with all 20 skills and triggers api call with selected skill_id and resets offset', async () => {
      render(<MistakesHistoryView />)

      const skillSelect = await screen.findByRole('combobox', { name: /kỹ năng/i })
      expect(skillSelect).toBeInTheDocument()

      // Kiểm tra tùy chọn mặc định "Tất cả kỹ năng"
      expect(within(skillSelect).getByRole('option', { name: /tất cả kỹ năng/i })).toBeInTheDocument()

      // Kiểm tra sự hiện diện của một số kỹ năng tiêu biểu trong 20 kỹ năng
      expect(within(skillSelect).getByRole('option', { name: /quân treo/i })).toBeInTheDocument()
      expect(within(skillSelect).getByRole('option', { name: /fork/i })).toBeInTheDocument()
      expect(within(skillSelect).getByRole('option', { name: /ghim quân/i })).toBeInTheDocument()
      expect(within(skillSelect).getByRole('option', { name: /xiên quân/i })).toBeInTheDocument()
      expect(within(skillSelect).getByRole('option', { name: /tàn cuộc tốt/i })).toBeInTheDocument()

      // Chọn lọc theo kỹ năng fork
      fireEvent.change(skillSelect, { target: { value: 'fork' } })

      // Kiểm tra API được gọi với skill_id: 'fork' và offset: 0
      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            skill_id: 'fork',
            offset: 0,
          }),
        )
      })
    })
  })

  describe('3. Phase Filter (3 giai đoạn cờ)', () => {
    it('Test 4: renders game phase filter (Opening, Middlegame, Endgame) and triggers api call with selected game_phase', async () => {
      render(<MistakesHistoryView />)

      const phaseSelect = await screen.findByRole('combobox', { name: /giai đoạn/i })
      expect(phaseSelect).toBeInTheDocument()

      // Kiểm tra các tùy chọn
      expect(within(phaseSelect).getByRole('option', { name: /tất cả giai đoạn/i })).toBeInTheDocument()
      expect(within(phaseSelect).getByRole('option', { name: /khai cuộc/i })).toBeInTheDocument()
      expect(within(phaseSelect).getByRole('option', { name: /trung cuộc/i })).toBeInTheDocument()
      expect(within(phaseSelect).getByRole('option', { name: /tàn cuộc/i })).toBeInTheDocument()

      // Chọn lọc theo Trung cuộc
      fireEvent.change(phaseSelect, { target: { value: 'middlegame' } })

      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            game_phase: 'middlegame',
            offset: 0,
          }),
        )
      })
    })
  })

  describe('4. Sorting criteria', () => {
    it('Test 5: allows sorting by played_at and win_loss (desc/asc) and triggers api call with order_by', async () => {
      render(<MistakesHistoryView />)

      const sortSelect = await screen.findByRole('combobox', { name: /sắp xếp/i })
      expect(sortSelect).toBeInTheDocument()

      // Chuyển sang sắp xếp theo mất Win% nhiều nhất
      fireEvent.change(sortSelect, { target: { value: 'win_loss_desc' } })

      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            order_by: 'win_loss_desc',
            offset: 0,
          }),
        )
      })

      // Chuyển sang sắp xếp theo ngày cũ nhất
      fireEvent.change(sortSelect, { target: { value: 'played_at_asc' } })

      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            order_by: 'played_at_asc',
            offset: 0,
          }),
        )
      })
    })
  })

  describe('5. Pagination', () => {
    const PAGINATED_RESPONSE: PlayerMistakesListOut = {
      total: 45,
      mistakes: Array.from({ length: 20 }, (_, i) => ({
        ...MOCK_MISTAKE_1,
        id: 200 + i,
      })),
    }

    it('Test 6: navigates to next page, updates offset and calls api with next page offset', async () => {
      listSpy.mockResolvedValueOnce(PAGINATED_RESPONSE)
      render(<MistakesHistoryView limit={20} />)

      const nextBtn = await screen.findByRole('button', { name: /trang sau/i })
      expect(nextBtn).toBeEnabled()

      fireEvent.click(nextBtn)

      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            offset: 20,
            limit: 20,
          }),
        )
      })
    })

    it('Test 7: disables previous button on page 1 and enables it on subsequent pages', async () => {
      listSpy.mockResolvedValue(PAGINATED_RESPONSE)
      render(<MistakesHistoryView limit={20} />)

      const prevBtn = await screen.findByRole('button', { name: /trang trước/i })
      const nextBtn = await screen.findByRole('button', { name: /trang sau/i })

      // Trang 1: Trang trước bị disable
      expect(prevBtn).toBeDisabled()

      // Chuyển sang trang 2
      fireEvent.click(nextBtn)

      // Chờ chuyển hẳn sang Trang 2 (kết thúc loading)
      expect(await screen.findByText(/trang 2 \//i)).toBeInTheDocument()
      expect(prevBtn).toBeEnabled()

      // Bấm quay lại trang 1
      fireEvent.click(prevBtn)

      // Chờ quay về Trang 1
      expect(await screen.findByText(/trang 1 \//i)).toBeInTheDocument()
      expect(listSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({
          offset: 0,
        }),
      )
    })

    it('Test 8: disables next button on the last page based on total count', async () => {
      // 25 kết quả, limit 20 -> Trang 2 (offset 20) là trang cuối cùng
      const LAST_PAGE_RESPONSE: PlayerMistakesListOut = {
        total: 25,
        mistakes: [MOCK_MISTAKE_1, MOCK_MISTAKE_2, MOCK_MISTAKE_3],
      }
      listSpy.mockResolvedValue(LAST_PAGE_RESPONSE)
      render(<MistakesHistoryView limit={20} />)

      const nextBtn = await screen.findByRole('button', { name: /trang sau/i })
      fireEvent.click(nextBtn)

      // Ở trang 2, nút Trang sau phải bị disable vì đã hết bản ghi
      await waitFor(() => {
        expect(nextBtn).toBeDisabled()
      })
    })
  })

  describe('6. API Integration & Default parameters', () => {
    it('Test 9: fetches player mistakes on mount with default query parameters (limit: 20, offset: 0, order_by: "played_at_desc")', async () => {
      render(<MistakesHistoryView />)

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith({
          limit: 20,
          offset: 0,
          order_by: 'played_at_desc',
        })
      })
    })
  })

  describe('7. Async States (Loading, Error, Empty)', () => {
    it('Test 10: displays loading indicator while fetching data', async () => {
      let resolvePromise: (val: PlayerMistakesListOut) => void = () => {}
      const pendingPromise = new Promise<PlayerMistakesListOut>((res) => {
        resolvePromise = res
      })
      listSpy.mockReturnValueOnce(pendingPromise)

      render(<MistakesHistoryView />)

      // Đang tải
      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.getByText(/đang tải/i)).toBeInTheDocument()

      // Sau khi giải quyết
      resolvePromise(MOCK_DEFAULT_RESPONSE)
      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument()
      })
    })

    it('Test 11: displays error message when API call fails', async () => {
      listSpy.mockRejectedValueOnce(new Error('Lỗi kết nối máy chủ'))
      render(<MistakesHistoryView />)

      const alert = await screen.findByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(screen.getByText(/lỗi kết nối máy chủ/i)).toBeInTheDocument()
    })

    it('Test 12: displays empty state message when total is 0', async () => {
      listSpy.mockResolvedValueOnce({ total: 0, mistakes: [] })
      render(<MistakesHistoryView />)

      expect(await screen.findByText(/không tìm thấy lỗi nào/i)).toBeInTheDocument()
    })
  })

  describe('8. Reset Filters & Selection Interaction', () => {
    it('Test 13: resets all filters to default when reset button is clicked', async () => {
      render(<MistakesHistoryView />)

      const skillSelect = await screen.findByRole('combobox', { name: /kỹ năng/i })
      fireEvent.change(skillSelect, { target: { value: 'fork' } })

      const resetBtn = screen.getByRole('button', { name: /đặt lại|xóa bộ lọc/i })
      fireEvent.click(resetBtn)

      // Filter quay về rỗng / mặc định
      expect(skillSelect).toHaveValue('')
      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            limit: 20,
            offset: 0,
            order_by: 'played_at_desc',
          }),
        )
      })
    })

    it('Test 14: calls onSelectMistake when a row or view button is clicked', async () => {
      const onSelect = vi.fn()
      render(<MistakesHistoryView onSelectMistake={onSelect} />)

      // Tìm nút "Xem" của dòng mistake 101 (ván 1)
      const viewButtons = await screen.findAllByRole('button', { name: /xem ván cờ/i })
      expect(viewButtons.length).toBeGreaterThan(0)

      fireEvent.click(viewButtons[0])

      expect(onSelect).toHaveBeenCalledWith(1, 101)
    })
  })

  describe('9. Multi-filter Combination & Race Condition Handling', () => {
    it('Test 15: preserves combined filter parameters when updating multiple filters sequentially (skill + phase + order_by)', async () => {
      render(<MistakesHistoryView />)

      // 1. Chọn kỹ năng fork
      const skillSelect = await screen.findByRole('combobox', { name: /kỹ năng/i })
      fireEvent.change(skillSelect, { target: { value: 'fork' } })
      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            skill_id: 'fork',
            offset: 0,
          }),
        )
      })

      // 2. Chọn tiếp giai đoạn trung cuộc
      const phaseSelect = screen.getByRole('combobox', { name: /giai đoạn/i })
      fireEvent.change(phaseSelect, { target: { value: 'middlegame' } })
      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            skill_id: 'fork',
            game_phase: 'middlegame',
            offset: 0,
          }),
        )
      })

      // 3. Chọn tiếp tiêu chí sắp xếp mất Win% nhiều nhất
      const sortSelect = screen.getByRole('combobox', { name: /sắp xếp/i })
      fireEvent.change(sortSelect, { target: { value: 'win_loss_desc' } })
      await waitFor(() => {
        expect(listSpy).toHaveBeenLastCalledWith(
          expect.objectContaining({
            skill_id: 'fork',
            game_phase: 'middlegame',
            order_by: 'win_loss_desc',
            offset: 0,
          }),
        )
      })
    })

    it('Test 16: prevents race condition / stale response from overwriting newer query results', async () => {
      let resolveFirstReq: (val: PlayerMistakesListOut) => void = () => {}
      let resolveSecondReq: (val: PlayerMistakesListOut) => void = () => {}

      const firstPromise = new Promise<PlayerMistakesListOut>((res) => {
        resolveFirstReq = res
      })
      const secondPromise = new Promise<PlayerMistakesListOut>((res) => {
        resolveSecondReq = res
      })

      // Lần 1: mount component
      listSpy.mockResolvedValueOnce(MOCK_DEFAULT_RESPONSE)
      render(<MistakesHistoryView />)
      expect(await screen.findByRole('table')).toBeInTheDocument()

      // Lần 2: User chọn fork (Request 1 - xử lý chậm)
      listSpy.mockReturnValueOnce(firstPromise)
      const skillSelect = screen.getByRole('combobox', { name: /kỹ năng/i })
      fireEvent.change(skillSelect, { target: { value: 'fork' } })

      // Lần 3: User nhanh chóng đổi sang pin (Request 2)
      listSpy.mockReturnValueOnce(secondPromise)
      fireEvent.change(skillSelect, { target: { value: 'pin' } })

      // Dữ liệu mock cho Request 2 (Pin)
      const PIN_RESPONSE: PlayerMistakesListOut = {
        total: 1,
        mistakes: [
          {
            ...MOCK_MISTAKE_1,
            id: 888,
            skill_id: 'pin',
            move_san: 'Bg5',
          },
        ],
      }

      // Dữ liệu mock cho Request 1 (Fork)
      const FORK_RESPONSE: PlayerMistakesListOut = {
        total: 1,
        mistakes: [
          {
            ...MOCK_MISTAKE_2,
            id: 999,
            skill_id: 'fork',
            move_san: 'Nd5',
          },
        ],
      }

      // Giả lập Request 2 resolve TRƯỚC
      resolveSecondReq(PIN_RESPONSE)

      // Giao diện hiển thị đúng dữ liệu của Request 2
      const table = await screen.findByRole('table')
      expect(within(table).getByText('Bg5')).toBeInTheDocument()
      expect(within(table).getByText('Ghim quân')).toBeInTheDocument()

      // Giả lập Request 1 (cũ) resolve SAU
      resolveFirstReq(FORK_RESPONSE)

      // Dữ liệu hiển thị VẪN PHẢI LÀ Request 2 (Bg5 / Ghim quân), KHÔNG ĐƯỢC bị ghi đè bởi Fork (Nd5)
      await new Promise((r) => setTimeout(r, 50))
      expect(within(table).getByText('Bg5')).toBeInTheDocument()
      expect(within(table).getByText('Ghim quân')).toBeInTheDocument()
      expect(within(table).queryByText('Nd5')).not.toBeInTheDocument()
    })
  })
})
