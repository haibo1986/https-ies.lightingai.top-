import './IntensityTable.css'

const STANDARD_ANGLES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90]
const number = (value, digits = 1) => value == null ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })

function planeValue(plane, angles, gamma) {
  if (!plane || gamma > angles[angles.length - 1]) return null
  const values = plane.candela
  if (gamma <= angles[0]) return values[0]
  for (let index = 0; index < angles.length - 1; index++) {
    const a = angles[index], b = angles[index + 1]
    if (a <= gamma && gamma <= b) return values[index] + (gamma - a) / (b - a) * (values[index + 1] - values[index])
  }
  return null
}

function PlaneTable({ title, positive, negative, angles, totalLumens }) {
  const rows = STANDARD_ANGLES.map(gamma => {
    const p = planeValue(positive, angles, gamma)
    const n = planeValue(negative, angles, gamma)
    const perKlm = value => value != null && totalLumens ? number(value / totalLumens * 1000, 1) : '—'
    return <tr key={gamma}><td>{gamma}°</td><td>{number(p, 1)}</td><td>{perKlm(p)}</td><td>{number(n, 1)}</td><td>{perKlm(n)}</td></tr>
  })
  return <div className="intensity-plane">
    <h3>{title}</h3>
    <table><thead><tr><th>γ</th><th>{positive?.label ?? '—'} (cd)</th><th>cd/klm</th><th>{negative?.label ?? '—'} (cd)</th><th>cd/klm</th></tr></thead><tbody>{rows}</tbody></table>
  </div>
}

export default function IntensityTable({ planes, angles, totalLumens, zonalFlux, totalFlux }) {
  const at = angle => planes.find(plane => plane.c_angle === angle)
  const axis = (positiveAngle, negativeAngle, title) => {
    const positive = at(positiveAngle), negative = at(negativeAngle)
    return <PlaneTable title={title}
      positive={positive && { label: `C${Number(positive.c_angle).toFixed(0)}°`, ...positive }}
      negative={negative && { label: `C${Number(negative.c_angle).toFixed(0)}°`, ...negative }}
      angles={angles} totalLumens={totalLumens}/>
  }
  return <div className="intensity-tables">
    <p className="intensity-kicker">STANDARD INTENSITY · 标准角度光强表（cd 与每 1000 流明归一化值 cd/klm）</p>
    <div className="intensity-grid">
      {axis(0, 180, 'C0–C180 平面')}
      {axis(90, 270, 'C90–C270 平面')}
    </div>
    {zonalFlux?.length > 0 && <div className="zonal-block">
      <h3>区域光通量（Zonal Flux）</h3>
      <table><thead><tr><th>区间</th><th>光通量 (lm)</th><th>占比</th><th>累计 (lm)</th></tr></thead>
        <tbody>{zonalFlux.map(zone => <tr key={zone.start_angle}><td>{zone.start_angle}°–{zone.end_angle}°</td><td>{number(zone.flux_lm, 1)}</td><td>{number(zone.percent, 1)}%</td><td>{number(zone.cumulative_lm, 1)}</td></tr>)}</tbody>
      </table>
      <p className="zonal-total">总光束流明（0–90° 积分）：{number(totalFlux, 1)} lm</p>
    </div>}
  </div>
}
