import { useState } from 'react'
import { downloadUrl, uploadSourceReport } from '../api.js'
import FluxEstimator from './FluxEstimator.jsx'
import ManualPdfMapper from './ManualPdfMapper.jsx'
import ReportSupplementForm from './ReportSupplementForm.jsx'
import './TargetForm.css'
import './SourceRecognition.css'

export const CHANGES = {
  power_only: { label: '仅功率或电流变化', level: 'low', allow: true, text: '同系列、同光学结构与角度，适合估算换算。' },
  led_count_change: { label: 'LED 数量或密度变化', level: 'medium', allow: true, text: '可能影响近场洗墙均匀性，估算器会检查 LED 密度。' },
  length_change: { label: '灯具长度或模组变化', level: 'medium', allow: true, text: '将同步更新 IES 发光尺寸，但近场均匀性仍需验证。' },
  beam_angle_change: { label: '光束角变化', level: 'high', allow: false, text: '会改变配光形状，必须重新实测。' },
  lens_change: { label: '透镜变化', level: 'high', allow: false, text: '会改变配光形状，必须重新实测。' },
  optical_structure_change: { label: '光学结构变化', level: 'high', allow: false, text: '风险高，必须重新实测。' },
}

export default function TargetForm({ form, setForm, onGenerate, loading, upload, generateError }) {
  const [reportUploading, setReportUploading] = useState(false)
  const [reportError, setReportError] = useState('')
  const risk = CHANGES[form.change_type]
  const peak = upload?.photometry?.peak_direction
  const peakGamma = peak ? Number(peak.gamma_angle || 0) : null
  const update = event => setForm(current => ({ ...current, [event.target.name]: event.target.value }))
  const applyEstimate = ({ flux, changeType, targetLength, targetWidth }) => setForm(current => ({
    ...current, target_luminous_flux_lm: String(flux), change_type: changeType,
    target_luminous_length_mm: targetLength ? String(targetLength) : '',
    target_luminous_width_mm: targetWidth ? String(targetWidth) : '',
  }))

  async function addSourceReport(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setReportUploading(true); setReportError('')
    try {
      const report = await uploadSourceReport(file)
      setForm(current => ({ ...current, source_report_id: report.source_report_id, source_report_name: report.file_name, source_report_preview_url: report.preview_url, source_report_analysis: report.analysis, source_field_mapping: {} }))
    } catch (reason) { setReportError(reason.message) }
    finally { setReportUploading(false); event.target.value = '' }
  }

  return <section className="card step-card appear">
    <div className="step-number">2</div>
    <div className="card-content">
      <div className="section-heading"><div><p className="eyebrow">TARGET</p><h2>填写目标参数</h2></div></div>
      <div className="form-grid">
        <label><span>原始实测总光通量 <b>*</b></span><div className="input-unit"><input name="source_luminous_flux_lm" type="number" min="0.000001" step="any" required value={form.source_luminous_flux_lm} onChange={update}/><i>lm</i></div></label>
        <label><span>目标型号 <b>*</b></span><input name="target_model" required maxLength="200" value={form.target_model} onChange={update} placeholder="例如 WWL-3030-36W-20D"/></label>
        <label><span>目标功率 <b>*</b></span><div className="input-unit"><input name="target_power_w" type="number" min="0.000001" step="any" required value={form.target_power_w} onChange={update}/><i>W</i></div></label>
        <label><span>目标光通量 <b>*</b></span><div className="input-unit"><input name="target_luminous_flux_lm" type="number" min="0.000001" step="any" required value={form.target_luminous_flux_lm} onChange={update}/><i>lm</i></div></label>
        <label className="required-dimension"><span>发光面长度 <b>* · 亮度计算必填</b></span><div className="input-unit"><input name="target_luminous_length_mm" type="number" min="0.01" step="any" required value={form.target_luminous_length_mm} onChange={update}/><i>mm</i></div></label>
        <label className="required-dimension"><span>发光面宽度 <b>* · 亮度计算必填</b></span><div className="input-unit"><input name="target_luminous_width_mm" type="number" min="0.01" step="any" required value={form.target_luminous_width_mm} onChange={update}/><i>mm</i></div></label>
        <FluxEstimator sourceFlux={form.source_luminous_flux_lm} targetPower={form.target_power_w} parsedInfo={upload.parsed_info} onApply={applyEstimate}/>
        <label className="wide"><span>变更类型 <b>*</b></span><select name="change_type" value={form.change_type} onChange={update}>{Object.entries(CHANGES).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select></label>
        <label className="wide"><span>配光对中校正</span><div className="check-field">
          <input type="checkbox" name="center_photometry" checked={!!form.center_photometry} onChange={event => setForm(current => ({ ...current, center_photometry: event.target.checked }))}/>
          <div className="check-field-copy">
            <p>勾选后各 C 平面配光曲线按自身峰值平移至正下方（γ=0°），曲线形状与光束角保持不变。仅适用于<b>非偏光设计</b>的灯具；洗墙灯等偏光配光请勿勾选。</p>
            {peak && (peakGamma <= 1
              ? <p className="peak-hint ok">当前文件最大光强方向 C{Number(peak.c_angle).toFixed(1)}° / γ{peakGamma.toFixed(1)}°，已基本居中，无需校正。</p>
              : <p className="peak-hint warn">当前文件最大光强方向 C{Number(peak.c_angle).toFixed(1)}° / γ{peakGamma.toFixed(1)}°，偏离正下方约 {peakGamma.toFixed(1)}°。若灯具并非偏光设计，建议勾选对中校正。</p>)}
          </div>
        </div></label>
      </div>
      {form.target_luminous_length_mm && form.target_luminous_width_mm && <div className="dimension-preview"><b>发光面积与亮度计算</b><span>{form.target_luminous_length_mm} × {form.target_luminous_width_mm} mm · 面积 {(Number(form.target_luminous_length_mm)*Number(form.target_luminous_width_mm)/1000000).toFixed(4)} m²</span></div>}

      <div className="source-report-box">
        <div><strong>原始光度测试 PDF（可选溯源附件）</strong><p>原文件不会被修改。标准 13 页报告始终由目标 IES 统一生成；识别成功的原版式文件还可额外生成一份覆盖估算数据的原版式报告。</p></div>
        <label className="button secondary source-report-button">
          {reportUploading ? '正在上传…' : form.source_report_id ? '更换 PDF' : '上传原始 PDF'}
          <input type="file" accept="application/pdf,.pdf" onChange={addSourceReport} disabled={reportUploading}/>
        </label>
        {form.source_report_id && <div className="source-report-ready"><span>✓ {form.source_report_name}</span><a href={downloadUrl(form.source_report_preview_url)} target="_blank" rel="noreferrer">预览原文件</a></div>}
        {form.source_report_analysis && <div className="source-recognition">
          <div className="recognition-head"><strong>来源报告识别结果</strong><span>用于数据核对与原版式报告叠加</span></div>
          {Object.values(form.source_report_analysis.fields || {}).length > 0 && <div className="recognition-grid">{Object.values(form.source_report_analysis.fields).map(field => <span key={field.label}><i>{field.label}</i><b>{field.value}</b></span>)}</div>}
          {form.source_report_analysis.warnings?.map(message => <p className="recognition-warning" key={message}>{message}</p>)}
          <p>识别值不会覆盖目标 IES 的计算结果；标准报告以目标 IES 和补充表单为唯一数据源。</p>
        </div>}
        {form.source_report_analysis?.template?.mode === 'manual' && <ManualPdfMapper reportId={form.source_report_id} value={form.source_field_mapping || {}} onChange={source_field_mapping => setForm(current => ({ ...current, source_field_mapping }))}/>}
        {reportError && <p className="inline-error" role="alert">{reportError}</p>}
      </div>

      <ReportSupplementForm value={form.report_supplement} onChange={report_supplement => setForm(current => ({ ...current, report_supplement }))}/>

      <div className={`risk-preview ${risk.level}`} role="status" aria-live="polite"><span className="risk-dot" aria-hidden="true"/><div><strong>{risk.level === 'low' ? '低风险' : risk.level === 'medium' ? '中风险' : '高风险 · 禁止生成'}</strong><p>{risk.text}</p></div></div>
      <button type="button" className="button primary generate" onClick={onGenerate} disabled={loading || !risk.allow} aria-busy={loading}>{loading ? '正在生成 IES 与专业光度报告…' : risk.allow ? '生成估算 IES + 专业光度报告' : '该变更类型需要重新实测'}</button>
      {generateError && <div className="generate-feedback error" role="alert"><strong>没有生成：</strong><span>{generateError}</span><small>请检查必填参数；如果提示无法连接，请重新启动后端服务。</small></div>}
      {loading && <div className="generate-feedback working" role="status"><strong>正在处理</strong><span>正在计算亮度、等照度、区域光通量和完整光强矩阵。</span></div>}
    </div>
  </section>
}
