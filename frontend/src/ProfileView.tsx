import { useEffect, useState } from 'react'
import { api, ApiError, type Profile, type SkillGroupProfile } from './api'

const SIZE = 320
const CENTER = SIZE / 2
const RADIUS = 110
const RING_STEP = 200
// Trục radar trải 600 điểm mỗi phía quanh năng lực chung; vòng nét đứt là năng lực chung.
const SPAN = 600

function fmt(n: number): string {
  return Math.round(n).toString()
}

function Radar({ groups, theta }: { groups: SkillGroupProfile[]; theta: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const min = theta - SPAN
  const max = theta + SPAN
  const r = (rating: number) => (Math.min(Math.max(rating, min), max) - min) / (max - min) * RADIUS
  const angle = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / groups.length
  const point = (i: number, radius: number): [number, number] => [
    CENTER + radius * Math.cos(angle(i)),
    CENTER + radius * Math.sin(angle(i)),
  ]
  const rings = [] as number[]
  for (let v = Math.ceil(min / RING_STEP) * RING_STEP; v <= max; v += RING_STEP) rings.push(v)
  const known = groups.map((g, i) => (g.rating === null ? null : point(i, r(g.rating))))
  const polygon = known.every((p) => p !== null) ? known.map((p) => p!.join(',')).join(' ') : null
  const hovered = hover === null ? null : groups[hover]

  return (
    <div className="radar-wrap">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="radar"
        role="img"
        aria-label="Radar năng lực theo nhóm kỹ năng; số liệu đầy đủ ở bảng bên dưới"
      >
        {rings.map((v) => (
          <circle key={v} cx={CENTER} cy={CENTER} r={r(v)} className="radar-grid" />
        ))}
        <circle cx={CENTER} cy={CENTER} r={r(theta)} className="radar-theta" />
        {groups.map((g, i) => {
          const [x, y] = point(i, RADIUS)
          const [lx, ly] = point(i, RADIUS + 26)
          return (
            <g key={g.id}>
              <line x1={CENTER} y1={CENTER} x2={x} y2={y} className="radar-grid" />
              <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" className="radar-label">
                {g.name}
              </text>
            </g>
          )
        })}
        {polygon && <polygon points={polygon} className="radar-area" />}
        {groups.map((g, i) => {
          const p = known[i]
          if (!p) return null
          return (
            <g key={g.id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <circle cx={p[0]} cy={p[1]} r={14} fill="transparent" />
              <circle cx={p[0]} cy={p[1]} r={hover === i ? 6 : 4.5} className="radar-dot" />
            </g>
          )
        })}
      </svg>
      <div className="radar-legend">
        <span>
          <i className="swatch-line" /> năng lực chung {fmt(theta)}
        </span>
        <span>vòng tròn cách nhau {RING_STEP} điểm</span>
      </div>
      <p className="radar-tip" aria-live="polite">
        {hovered
          ? `${hovered.name}: ${hovered.rating === null ? 'chưa đủ dữ liệu' : fmt(hovered.rating)}`
          : groups.some((g) => g.rating === null)
            ? 'Nhóm chưa có lần giải nào chưa hiện trên radar.'
            : 'Rê chuột vào điểm để xem số.'}
      </p>
    </div>
  )
}

export default function ProfileView() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .profile()
      .then(setProfile)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Không kết nối được máy chủ'))
  }, [])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!profile) return <p>Đang tải hồ sơ…</p>

  const half = (profile.ci_high - profile.ci_low) / 2
  return (
    <section className="profile">
      <div className="profile-head">
        <div className="panel">
          <p className="meta">Năng lực chung</p>
          <p className="hero">{fmt(profile.theta)}</p>
          <p className="meta">
            ± {fmt(half)} (khoảng tin cậy 95%) · {profile.attempts} lần giải
          </p>
        </div>
        <Radar groups={profile.groups} theta={profile.theta} />
      </div>

      <table className="skills">
        <thead>
          <tr>
            <th scope="col">Kỹ năng</th>
            <th scope="col" className="num">Năng lực</th>
            <th scope="col" className="num">Khoảng tin cậy 95%</th>
            <th scope="col" className="num">Lần giải</th>
          </tr>
        </thead>
        {profile.groups.map((g) => (
          <tbody key={g.id}>
            <tr className="group-row">
              <th scope="rowgroup" colSpan={4}>
                {g.name}
              </th>
            </tr>
            {g.skills.map((id) => {
              const s = profile.skills.find((x) => x.id === id)!
              return (
                <tr key={s.id}>
                  <th scope="row">
                    <span className="skill-name">{s.name}</span>
                    <span className="skill-desc">{s.description}</span>
                  </th>
                  {s.enough_data ? (
                    <>
                      <td className="num">{fmt(s.rating)}</td>
                      <td className="num">
                        {fmt(s.ci_low)}–{fmt(s.ci_high)}
                      </td>
                    </>
                  ) : (
                    <td colSpan={2} className="muted">
                      chưa đủ dữ liệu
                    </td>
                  )}
                  <td className="num">{s.attempts}</td>
                </tr>
              )
            })}
          </tbody>
        ))}
      </table>
    </section>
  )
}
