import { describe, expect, it } from 'vitest'
import type { MistakeOut } from '../api'
import {
  applyUciMove,
  calculateArrows,
  getAnalysisFen,
  getBoardOrientation,
  getSkillNameVi,
  parseUci,
} from './chessAnalysis'

const SAMPLE_START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const SAMPLE_BLACK_TURN_FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
const SAMPLE_PROMOTION_FEN = 'k7/4P3/8/8/8/8/8/4K3 w - - 0 1'

// Thế cờ cờ vua thực sự 100% hợp lệ:
// Khai cuộc Scotch Gambit sau 1. e4 e5 2. Nf3 Nc6 3. d4 exd4 4. Bc4
// Lượt Đen đi (b).
// Nước sai move_uci: 4... d6 ('d7d6')
// Nước tốt nhất best_move: 4... Nf6 ('g8f6')
// Nước phản đòn refutation_move của Trắng: 5. Ng5 ('f3g5')
const MOCK_LEGAL_MISTAKE: MistakeOut = {
  id: 1,
  ply: 8,
  move_number: 4,
  move_san: 'd6',
  move_uci: 'd7d6',
  fen: 'r1bqkbnr/pppp1ppp/2n5/8/2BpP3/5N2/PPP2PPP/RNBQK2R b KQkq - 1 4',
  win_before: 50.0,
  win_after: 25.0,
  win_loss: 25.0,
  skill_id: 'hanging_piece',
  motif: 'hanging_piece',
  game_phase: 'opening',
  best_move: 'g8f6',
  refutation_move: 'f3g5',
}

describe('chessAnalysis - UCI Helpers', () => {
  it('1. parseUci: parse chính xác nước đi thông thường', () => {
    const res = parseUci('d7d6')
    expect(res).toEqual({ from: 'd7', to: 'd6' })
  })

  it('2. parseUci: parse chính xác nước phong cấp', () => {
    const queenPromo = parseUci('e7e8q')
    expect(queenPromo).toEqual({ from: 'e7', to: 'e8', promotion: 'q' })

    const knightPromo = parseUci('a2a1n')
    expect(knightPromo).toEqual({ from: 'a2', to: 'a1', promotion: 'n' })

    const rookPromo = parseUci('b7b8r')
    expect(rookPromo).toEqual({ from: 'b7', to: 'b8', promotion: 'r' })

    const bishopPromo = parseUci('c2c1b')
    expect(bishopPromo).toEqual({ from: 'c2', to: 'c1', promotion: 'b' })
  })

  it('3. parseUci: trả về null cho các chuỗi UCI không hợp lệ', () => {
    expect(parseUci('')).toBeNull()
    expect(parseUci('   ')).toBeNull()
    expect(parseUci(null)).toBeNull()
    expect(parseUci(undefined)).toBeNull()
    expect(parseUci('e2')).toBeNull() // Quá ngắn
    expect(parseUci('e2e4q2')).toBeNull() // Quá dài
    expect(parseUci('z9a1')).toBeNull() // Tọa độ ô ngoài bàn cờ
    expect(parseUci('e7e8x')).toBeNull() // Ký tự phong cấp không hợp lệ ('x')
    expect(parseUci('e7e8k')).toBeNull() // Không thể phong cấp thành King ('k')
  })

  it('4. applyUciMove: đi nước hợp lệ trên FEN tạo ra FEN mới và SAN chính xác', () => {
    const res = applyUciMove(SAMPLE_START_FEN, 'e2e4')
    expect(res).not.toBeNull()
    expect(res?.san).toBe('e4')
    expect(res?.fen).toContain('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq')
  })

  it('4b. applyUciMove: thực hiện thành công nước phong cấp', () => {
    const res = applyUciMove(SAMPLE_PROMOTION_FEN, 'e7e8q')
    expect(res).not.toBeNull()
    expect(res?.san).toBe('e8=Q+')
    expect(res?.fen).toContain('k3Q3/8/8/8/8/8/8/4K3 b')
  })

  it('5. applyUciMove: trả về null an toàn khi nước đi không hợp lệ trên thế cờ', () => {
    // Quân tốt không thể nhảy từ e2 sang e5 trong 1 nước
    expect(applyUciMove(SAMPLE_START_FEN, 'e2e5')).toBeNull()
    // Quân đen không thể đi khi lượt là Trắng
    expect(applyUciMove(SAMPLE_START_FEN, 'e7e5')).toBeNull()
    // Chuỗi UCI rác
    expect(applyUciMove(SAMPLE_START_FEN, 'invalid')).toBeNull()
  })
})

describe('chessAnalysis - Orientation & Board Modes', () => {
  it('6. getBoardOrientation: xác định hướng bàn cờ theo side-to-move của FEN', () => {
    expect(getBoardOrientation(SAMPLE_START_FEN)).toBe('white')
    expect(getBoardOrientation(SAMPLE_BLACK_TURN_FEN)).toBe('black')
    // Nếu FEN rỗng hoặc không truyền, mặc định là white
    expect(getBoardOrientation('')).toBe('white')
    expect(getBoardOrientation(undefined)).toBe('white')
  })

  it('7. getAnalysisFen: trả về FEN chính xác cho 2 chế độ mistake và refutation', () => {
    // Chế độ 1: Mistake -> FEN trước lỗi
    const mistakeFen = getAnalysisFen('mistake', MOCK_LEGAL_MISTAKE)
    expect(mistakeFen).toBe(MOCK_LEGAL_MISTAKE.fen)

    // Chế độ 2: Refutation -> FEN sau khi đã đi move_uci (d7d6)
    const refutationFen = getAnalysisFen('refutation', MOCK_LEGAL_MISTAKE)
    expect(refutationFen).not.toBe('')
    expect(refutationFen).not.toBe(MOCK_LEGAL_MISTAKE.fen)
    // Sau d7d6, tốt đen nằm ở d6
    expect(refutationFen).toContain('2np4')
  })

  it('8. calculateArrows: sinh đúng mũi tên trong chế độ mistake trên thế cờ hợp lệ', () => {
    const arrows = calculateArrows('mistake', MOCK_LEGAL_MISTAKE)
    expect(arrows).toHaveLength(2)

    // Mũi tên đỏ chỉ nước người chơi đã đi: d7 -> d6
    const redArrow = arrows.find((a) => a[0] === 'd7' && a[1] === 'd6')
    expect(redArrow).toBeDefined()
    expect(redArrow?.[2]).toContain('rgb(220, 53, 69)')

    // Mũi tên xanh lá chỉ nước tốt nhất: g8 -> f6
    const greenArrow = arrows.find((a) => a[0] === 'g8' && a[1] === 'f6')
    expect(greenArrow).toBeDefined()
    expect(greenArrow?.[2]).toContain('rgb(40, 167, 69)')
  })

  it('9. calculateArrows: sinh đúng mũi tên trong chế độ refutation trên thế cờ hợp lệ', () => {
    const arrows = calculateArrows('refutation', MOCK_LEGAL_MISTAKE)
    expect(arrows).toHaveLength(1)

    // Mũi tên cam chỉ nước phản đòn của đối thủ: f3 -> g5
    const orangeArrow = arrows[0]
    expect(orangeArrow[0]).toBe('f3')
    expect(orangeArrow[1]).toBe('g5')
    expect(orangeArrow[2]).toContain('rgb(245, 158, 11)')
  })

  it('10. calculateArrows: xử lý an toàn khi best_move hoặc refutation_move là null', () => {
    const mistakeWithoutMoves: MistakeOut = {
      ...MOCK_LEGAL_MISTAKE,
      best_move: null,
      refutation_move: null,
    }

    // Chế độ mistake: chỉ có 1 mũi tên đỏ cho move_uci
    const mistakeArrows = calculateArrows('mistake', mistakeWithoutMoves)
    expect(mistakeArrows).toHaveLength(1)
    expect(mistakeArrows[0][0]).toBe('d7')
    expect(mistakeArrows[0][1]).toBe('d6')

    // Chế độ refutation: không có mũi tên vì refutation_move là null
    const refutationArrows = calculateArrows('refutation', mistakeWithoutMoves)
    expect(refutationArrows).toHaveLength(0)
  })

  it('10b. calculateArrows: không vẽ mũi tên nếu nước đi đúng định dạng UCI nhưng không hợp lệ trên bàn cờ', () => {
    // UCI đúng cú pháp 'e1e8', nhưng vua không thể nhảy từ e1 lên e8
    const invalidMovesMistake: MistakeOut = {
      ...MOCK_LEGAL_MISTAKE,
      move_uci: 'e1e8', // Nước đi sai luật
      best_move: 'a1h8', // Nước đi sai luật
    }

    const arrows = calculateArrows('mistake', invalidMovesMistake)
    // Cả 2 nước đều sai luật cờ trên FEN ban đầu -> không sinh mũi tên nào
    expect(arrows).toHaveLength(0)
  })

  it('10c. calculateArrows: không xuất hiện mũi tên phản đòn khi không thể tạo FEN sau nước sai', () => {
    const unplayableMistake: MistakeOut = {
      ...MOCK_LEGAL_MISTAKE,
      move_uci: 'h7h1', // Không thể đi được
      refutation_move: 'f3g5',
    }

    // Ở chế độ refutation, vì move_uci không đi được -> không sinh FEN mới -> không vẽ mũi tên phản đòn
    const arrows = calculateArrows('refutation', unplayableMistake)
    expect(arrows).toHaveLength(0)
  })

  it('10d. getSkillNameVi: ánh xạ chính xác 20 kỹ năng sang tiếng Việt', () => {
    expect(getSkillNameVi('hanging_piece')).toBe('Quân treo')
    expect(getSkillNameVi('fork')).toBe('Fork (đòn đôi)')
    expect(getSkillNameVi('pin')).toBe('Ghim quân')
    expect(getSkillNameVi('skewer')).toBe('Xiên quân')
    expect(getSkillNameVi('trapped_piece')).toBe('Quân bị nhốt')
    expect(getSkillNameVi('discovered_attack')).toBe('Tấn công phát hiện')
    expect(getSkillNameVi('deflection')).toBe('Làm lệch quân bảo vệ')
    expect(getSkillNameVi('attraction')).toBe('Dụ quân và thí quân')
    expect(getSkillNameVi('quiet_move')).toBe('Nước lặng và nước trung gian')
    expect(getSkillNameVi('missed_tactic')).toBe('Bỏ lỡ chiến thuật')
    expect(getSkillNameVi('mate_in_1')).toBe('Chiếu hết 1 nước')
    expect(getSkillNameVi('mate_in_n')).toBe('Chiếu hết nhiều nước')
    expect(getSkillNameVi('back_rank_mate')).toBe('Chiếu hết hàng cuối')
    expect(getSkillNameVi('mate_patterns')).toBe('Mẫu chiếu hết')
    expect(getSkillNameVi('king_attack')).toBe('Tấn công vua')
    expect(getSkillNameVi('promotion')).toBe('Tốt phong cấp')
    expect(getSkillNameVi('pawn_endgame')).toBe('Tàn cuộc tốt')
    expect(getSkillNameVi('rook_endgame')).toBe('Tàn cuộc xe')
    expect(getSkillNameVi('other_endgame')).toBe('Tàn cuộc quân nhẹ và hậu')
    expect(getSkillNameVi('defense')).toBe('Nước phòng thủ')
    // Fallback khi gặp ID không xác định
    expect(getSkillNameVi('unknown_skill')).toBe('unknown_skill')
  })
})
