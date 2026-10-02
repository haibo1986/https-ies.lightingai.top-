// LED 光通量估算的纯计算逻辑：与界面解耦，便于单元测试与回归验证。

const n = value => Number(value)
const positive = value => Number.isFinite(n(value)) && n(value) > 0

export function parseCurve(text) {
  const points = String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    .map(line => line.split(/[\s,;，\t]+/).map(Number))
    .filter(row => row.length >= 2 && row.every(Number.isFinite))
    .map(([current, flux]) => ({ current, flux })).sort((a, b) => a.current - b.current)
  return points.filter((point, index) => index === 0 || point.current !== points[index - 1].current)
}

export function interpolate(points, current) {
  if (points.length < 2 || current < points[0].current || current > points.at(-1).current) return null
  const exact = points.find(point => point.current === current)
  if (exact) return exact.flux
  const upper = points.findIndex(point => point.current > current)
  const a = points[upper - 1], b = points[upper]
  return a.flux + (current - a.current) * (b.flux - a.flux) / (b.current - a.current)
}

/**
 * 计算估算结果。
 * @param {object} input
 *  - scenario：场景 id
 *  - values：估算器各字段原始字符串值
 *  - points：解析后的 LED 曲线点
 *  - sourceFlux：表单里的原始实测总光通量（字符串）
 *  - targetPower：表单里的目标功率（字符串）
 *  - sourceLengthDefault：来自 IES 的原始发光长度默认值（mm，数字或 ''）
 *  - mainDims：主表单发光面尺寸 {length, width}（数字或 null）
 *  - autoSource：估算器上次自动填入表单的原始光通量（用于模式粘性，避免回填后路径翻转）
 * @returns {{result:number|null, sourceFluxAbs:number|null, error:string, warning:string, confidence:string, changeType:string}}
 */
export function computeEstimate(input) {
  const { scenario, values, points, sourceFlux, targetPower, sourceLengthDefault, mainDims, autoSource } = input
  const source = n(sourceFlux)
  const hasSource = positive(source)
  // 绝对路径粘性：表单里的原始光通量如果是估算器自己填入的，继续按绝对路径计算，
  // 避免「回填 → 切换路径 → 显示内容突变」的翻转；用户手改成别的值后自动回到比例路径。
  const useAbsolute = scenario === 'combined' && (!hasSource || (autoSource != null && Math.abs(source - autoSource) < 1))
  const reference = positive(values.reference_current) && positive(values.reference_flux)
    ? { current: n(values.reference_current), flux: n(values.reference_flux) } : null
  const opticalFactor = values.optical === 'transmission' && positive(values.source_transmission) && positive(values.target_transmission)
    ? n(values.target_transmission) / n(values.source_transmission) : 1
  const out = { result: null, sourceFluxAbs: null, error: '', warning: '', confidence: 'high', changeType: 'power_only' }
  if (!scenario) return out
  if (values.optical === 'changed') {
    out.error = '透镜或光学结构变化会改变配光形状，不能使用简单换算，请重新实测。'
    return out
  }
  if (scenario === 'current' || scenario === 'combined') {
    if (!positive(values.source_current) || !positive(values.target_current)) {
      out.error = '请填写原始和目标单颗电流。'
      return out
    }
    if (points.length < 2) {
      out.error = '请导入或粘贴至少两个“电流,相对光通量”数据点。'
      return out
    }
    const a = interpolate(points, n(values.source_current))
    const b = interpolate(points, n(values.target_current))
    if (a == null || b == null) {
      out.error = `电流必须位于曲线范围 ${points[0].current}–${points.at(-1).current} mA 内，软件不会自动外推。`
      return out
    }
    if (useAbsolute) {
      // 绝对光通量路径：用曲线基准点（电流→lm）直接算灯总光通量
      const refRel = reference ? interpolate(points, reference.current) : null
      if (!reference || refRel == null) {
        out.error = '没有原始实测总光通量。要直接按 LED 曲线算绝对光通量，请选择带基准光通量的型号曲线（如「添鑫3535」，300mA→218lm），并在下方填写基准点。'
        return out
      }
      if (!positive(values.source_count) || !positive(values.target_count)) {
        out.error = '请填写原始和目标LED颗数。'
        return out
      }
      const sourceAbs = a / refRel * reference.flux * n(values.source_count) * opticalFactor
      const targetAbs = b / refRel * reference.flux * n(values.target_count) * opticalFactor
      out.result = targetAbs
      out.sourceFluxAbs = Math.round(sourceAbs)
      out.confidence = 'low'
      out.changeType = 'led_count_change'
      out.warning = `按曲线基准点（${reference.current}mA → ${reference.flux}lm）直接估算：目标光通量由目标电流与目标颗数决定，原始电流/颗数只影响原始光通量估算；未计入驱动损耗与温升，建议使用范围值并复核。`
      return out
    }
    // 比例路径：原始光通量 × 曲线比例 × 颗数比例
    if (!hasSource) {
      out.error = '没有原始实测总光通量。直接算灯总光通量需要颗数信息，请改用「颗数和电流都变」场景。'
      return out
    }
    let factor = b / a
    if (scenario === 'combined') {
      if (!positive(values.source_count) || !positive(values.target_count)) {
        out.error = '请填写原始和目标LED颗数。'
        return out
      }
      factor *= n(values.target_count) / n(values.source_count)
    }
    out.result = source * factor * opticalFactor
    out.confidence = values.thermal === 'unknown' ? 'low' : 'medium'
    out.changeType = scenario === 'combined' ? 'led_count_change' : 'power_only'
    out.warning = values.thermal === 'unknown'
      ? '散热和结温未知，结果范围已扩大；建议补充同型号LED温度曲线或实测温度。'
      : '按热条件基本相同估算；提高电流后如温升明显，实际光通量可能偏低。'
    return out
  }
  if (scenario === 'count') {
    if (!hasSource) {
      out.error = '请先在上方填写「原始实测总光通量」，该估算方式需要它作为换算基数。'
      return out
    }
    if (!positive(values.source_count) || !positive(values.target_count)) {
      out.error = '请填写原始和目标LED颗数。'
      return out
    }
    out.result = source * n(values.target_count) / n(values.source_count) * opticalFactor
    out.changeType = 'led_count_change'
    const sl = n(values.source_length_mm || sourceLengthDefault)
    const tl = mainDims.length || n(sourceLengthDefault)
    if (sl > 0 && tl > 0) {
      const sourceDensity = n(values.source_count) / (sl / 1000)
      const targetDensity = n(values.target_count) / (tl / 1000)
      const drop = 1 - targetDensity / sourceDensity
      if (drop > .25) {
        out.error = `LED密度下降${Math.round(drop * 100)}%，可能明显产生亮暗斑；请调整方案或重新实测。`
        out.result = null
      } else if (drop > .1) {
        out.warning = `LED密度下降${Math.round(drop * 100)}%（${sourceDensity.toFixed(1)}→${targetDensity.toFixed(1)}颗/m），可能影响近场洗墙均匀性。`
        out.confidence = 'medium'
      }
    }
    if (!mainDims.length && !out.error) out.warning = (out.warning ? out.warning + ' ' : '') + '目标发光长度请在上方主表单填写，密度检查暂按源尺寸计算。'
    return out
  }
  if (scenario === 'module') {
    if (!hasSource) {
      out.error = '请先在上方填写「原始实测总光通量」，该估算方式需要它作为换算基数。'
      return out
    }
    if (!positive(values.source_modules) || !positive(values.target_modules)) {
      out.error = '请填写原始和目标模组数量。'
      return out
    }
    if (!mainDims.length || !mainDims.width) {
      out.error = '请先在上方主表单填写发光面长度和宽度，模组变化会同步写入IES。'
      return out
    }
    out.result = source * n(values.target_modules) / n(values.source_modules) * opticalFactor
    out.changeType = 'length_change'
    out.confidence = 'medium'
    out.warning = '发光尺寸会同步写入IES，但模组间距变化仍可能影响近场均匀性。'
    return out
  }
  if (scenario === 'pwm') {
    if (!hasSource) {
      out.error = '请先在上方填写「原始实测总光通量」，该估算方式需要它作为换算基数。'
      return out
    }
    if (!positive(values.source_duty) || !positive(values.target_duty) || n(values.source_duty) > 100 || n(values.target_duty) > 100) {
      out.error = 'PWM占空比必须在0–100%之间。'
      return out
    }
    out.result = source * n(values.target_duty) / n(values.source_duty)
    out.warning = '仅适用于峰值电流不变的PWM调光，不适用于模拟调流。'
    return out
  }
  if (scenario === 'efficacy') {
    if (!positive(targetPower) || !positive(values.target_efficacy)) {
      out.error = '请先填写目标功率和预计目标光效。'
      return out
    }
    out.result = n(targetPower) * n(values.target_efficacy)
    out.confidence = 'low'
    out.warning = '功率×光效属于低置信度备用估算，未直接反映LED电流、驱动效率和温升。'
    return out
  }
  return out
}

export function rangeFor(value, confidence) {
  const spread = confidence === 'high' ? .05 : confidence === 'medium' ? .1 : .2
  return [value * (1 - spread), value * (1 + spread)]
}
