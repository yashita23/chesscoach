export type Player = {
  email: string
  display_name: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    throw new ApiError(res.status, await errorMessage(res))
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json()
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { loc?: unknown[]; msg?: string }
      const field = first.loc?.[first.loc.length - 1]
      if (field === 'email') return 'Email không hợp lệ'
      if (field === 'password') return 'Mật khẩu phải dài 8–72 byte'
      if (field === 'display_name') return 'Tên hiển thị không được để trống'
      return first.msg ?? 'Dữ liệu không hợp lệ'
    }
  } catch {
    // Không phải JSON: dùng thông báo chung bên dưới.
  }
  return `Lỗi máy chủ (${res.status})`
}

export type Color = 'white' | 'black'

export type Attempt = {
  attempt_id: number
  puzzle_id: string
  rating: number
  start_fen: string
  opponent_move: string
  fen: string
  player_color: Color
  /** Xác suất giải đúng mà mô hình năng lực dự đoán trước lần giải. */
  predicted_p: number
}

export type MoveResult = {
  verdict: 'correct' | 'wrong'
  fen: string
  opponent_move: string | null
  expected_move: string | null
  completed: boolean
  /** Nhãn của lần giải; null khi chưa chốt. */
  correct: boolean | null
}

export type SkillProfile = {
  id: string
  name: string
  description: string
  group: string
  rating: number
  deviation: number
  ci_low: number
  ci_high: number
  attempts: number
  enough_data: boolean
}

export type SkillGroupProfile = {
  id: string
  name: string
  rating: number | null
  skills: string[]
}

export type Profile = {
  theta: number
  ci_low: number
  ci_high: number
  attempts: number
  skills: SkillProfile[]
  groups: SkillGroupProfile[]
}

export const api = {
  me: () => request<Player>('GET', '/me'),
  register: (email: string, password: string, display_name: string) =>
    request<Player>('POST', '/auth/register', { email, password, display_name }),
  login: (email: string, password: string) =>
    request<Player>('POST', '/auth/login', { email, password }),
  logout: () => request<void>('POST', '/auth/logout'),
  nextPuzzle: () => request<{ puzzle_id: string }>('GET', '/puzzles/next'),
  startAttempt: (puzzle_id: string) => request<Attempt>('POST', '/attempts', { puzzle_id }),
  playMove: (attemptId: number, uci: string) =>
    request<MoveResult>('POST', `/attempts/${attemptId}/moves`, { uci }),
  profile: () => request<Profile>('GET', '/profile'),
}
