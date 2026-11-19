import { Chess } from 'chess.js'
import type { Arrow, Square } from 'react-chessboard/dist/chessboard/types'
import type { MistakeOut } from '../api'

export type PlayerColor = 'white' | 'black'

export type UciMove = {
  from: Square
  to: Square
  promotion?: 'q' | 'r' | 'b' | 'n'
}

const SQUARE_REGEX = /^[a-h][1-8]$/
const PROMOTION_PIECES = new Set(['q', 'r', 'b', 'n'])

export const ARROW_COLORS = {
  playedMistake: 'rgb(220, 53, 69)', // Đỏ: nước người chơi đã đi
  bestMove: 'rgb(40, 167, 69)', // Xanh lá: nước tốt nhất người chơi nên đi
  refutation: 'rgb(245, 158, 11)', // Cam / vàng: nước đối thủ phản đòn
}

export const SKILL_NAMES_VI: Record<string, string> = {
  hanging_piece: 'Quân treo',
  fork: 'Fork (đòn đôi)',
  pin: 'Ghim quân',
  skewer: 'Xiên quân',
  trapped_piece: 'Quân bị nhốt',
  discovered_attack: 'Tấn công phát hiện',
  deflection: 'Làm lệch quân bảo vệ',
  attraction: 'Dụ quân và thí quân',
  quiet_move: 'Nước lặng và nước trung gian',
  missed_tactic: 'Bỏ lỡ chiến thuật',
  mate_in_1: 'Chiếu hết 1 nước',
  mate_in_n: 'Chiếu hết nhiều nước',
  back_rank_mate: 'Chiếu hết hàng cuối',
  mate_patterns: 'Mẫu chiếu hết',
  king_attack: 'Tấn công vua',
  promotion: 'Tốt phong cấp',
  pawn_endgame: 'Tàn cuộc tốt',
  rook_endgame: 'Tàn cuộc xe',
  other_endgame: 'Tàn cuộc quân nhẹ và hậu',
  defense: 'Nước phòng thủ',
}

/** Trả về tên tiếng Việt hiển thị thân thiện cho 20 kỹ năng. */
export function getSkillNameVi(skillId: string): string {
  return SKILL_NAMES_VI[skillId] ?? skillId
}

/**
 * Parse chuỗi UCI (vd: 'c6d4', 'e7e8q') sang cấu trúc UciMove.
 * Trả về null nếu định dạng không hợp lệ.
 */
export function parseUci(uci: string | null | undefined): UciMove | null {
  if (!uci || typeof uci !== 'string') return null
  const clean = uci.trim().toLowerCase()
  if (clean.length !== 4 && clean.length !== 5) return null
  const from = clean.slice(0, 2)
  const to = clean.slice(2, 4)
  if (!SQUARE_REGEX.test(from) || !SQUARE_REGEX.test(to)) return null
  if (clean.length === 5) {
    const promo = clean[4]
    if (!PROMOTION_PIECES.has(promo)) return null
    return { from: from as Square, to: to as Square, promotion: promo as UciMove['promotion'] }
  }
  return { from: from as Square, to: to as Square }
}

/**
 * Thực hiện nước đi UCI trên thế cờ FEN, trả về FEN mới và SAN.
 * Trả về null an toàn nếu nước đi không hợp lệ theo luật cờ.
 */
export function applyUciMove(fen: string, uci: string): { fen: string; san: string } | null {
  const parsed = parseUci(uci)
  if (!parsed) return null
  try {
    const chess = new Chess(fen)
    const res = chess.move(parsed)
    return { fen: chess.fen(), san: res.san }
  } catch {
    return null
  }
}

/**
 * Xác định hướng bàn cờ mặc định dựa theo side-to-move của FEN.
 * Nếu FEN rỗng hoặc lượt là Trắng -> 'white'; nếu lượt là Đen -> 'black'.
 */
export function getBoardOrientation(fen?: string): PlayerColor {
  if (!fen) return 'white'
  const parts = fen.trim().split(/\s+/)
  if (parts.length >= 2 && parts[1] === 'b') {
    return 'black'
  }
  return 'white'
}

/**
 * Trả về thế cờ FEN hiển thị theo chế độ:
 * - 'mistake': FEN trước nước đi lỗi.
 * - 'refutation': FEN sau khi đã đi move_uci (để đối thủ phản đòn).
 * Nếu move_uci không đi được trên FEN, fallback an toàn về mistake.fen.
 */
export function getAnalysisFen(mode: 'mistake' | 'refutation', mistake: MistakeOut): string {
  if (mode === 'mistake') {
    return mistake.fen
  }
  const next = applyUciMove(mistake.fen, mistake.move_uci)
  return next ? next.fen : mistake.fen
}

/**
 * Tính toán mảng mũi tên (Arrow) cho react-chessboard:
 * - Chế độ 'mistake':
 *   + Mũi tên đỏ: nước đã chơi (move_uci) — chỉ vẽ khi hợp lệ trên FEN ban đầu.
 *   + Mũi tên xanh lá: nước tốt nhất (best_move) — chỉ vẽ khi hợp lệ trên FEN ban đầu.
 * - Chế độ 'refutation':
 *   + Chỉ vẽ khi đi thành công move_uci trên FEN ban đầu để tạo FEN sau nước sai.
 *   + Mũi tên cam: nước phản đòn (refutation_move) — chỉ vẽ khi hợp lệ trên FEN sau nước sai.
 */
export function calculateArrows(mode: 'mistake' | 'refutation', mistake: MistakeOut): Arrow[] {
  const arrows: Arrow[] = []

  if (mode === 'mistake') {
    // 1. Kiểm tra tính hợp lệ của move_uci trên FEN ban đầu
    const playedMove = applyUciMove(mistake.fen, mistake.move_uci)
    const playedParsed = parseUci(mistake.move_uci)
    if (playedMove && playedParsed) {
      arrows.push([playedParsed.from, playedParsed.to, ARROW_COLORS.playedMistake])
    }

    // 2. Kiểm tra tính hợp lệ của best_move trên FEN ban đầu
    if (mistake.best_move) {
      const bestMove = applyUciMove(mistake.fen, mistake.best_move)
      const bestParsed = parseUci(mistake.best_move)
      if (bestMove && bestParsed) {
        arrows.push([bestParsed.from, bestParsed.to, ARROW_COLORS.bestMove])
      }
    }
  } else {
    // Chế độ phản đòn:
    // 1. Đi nước sai trên FEN ban đầu để tạo FEN sau nước sai
    const afterPlayed = applyUciMove(mistake.fen, mistake.move_uci)
    if (!afterPlayed) {
      // Nếu không đi được nước sai thì không bao giờ vẽ mũi tên phản đòn trên FEN cũ
      return arrows
    }

    // 2. Kiểm tra tính hợp lệ của refutation_move trên FEN sau nước sai
    if (mistake.refutation_move) {
      const refMove = applyUciMove(afterPlayed.fen, mistake.refutation_move)
      const refParsed = parseUci(mistake.refutation_move)
      if (refMove && refParsed) {
        arrows.push([refParsed.from, refParsed.to, ARROW_COLORS.refutation])
      }
    }
  }

  return arrows
}
