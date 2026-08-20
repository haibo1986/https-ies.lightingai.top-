import { useState } from 'react'
import { generateIes, uploadIes } from './api.js'
import UploadForm from './components/UploadForm.jsx'
import IesInfoPanel from './components/IesInfoPanel.jsx'
import TargetForm, { CHANGES } from './components/TargetForm.jsx'
import ResultPanel from './components/ResultPanel.jsx'

const EMPTY = {
  source_luminous_flux_lm: '', target_model: '', target_power_w: '',
  target_luminous_flux_lm: '', change_type: 'power_only',
  target_luminous_length_mm: '', target_luminous_width_mm: '',
  source_report_id: '', source_report_name: '', source_report_preview_url: '', source_report_analysis: null, source_field_mapping: {},
  report_supplement: {},
}

export default function App() {
  const [file, setFile] = useState(null)
  const [upload, setUpload] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [generating, setGenerating] = useState(false)

  function selectFile(event) {
    setFile(event.target.files?.[0] || null)
    setUpload(null); setResult(null); setError(''); setForm(EMPTY)
  }

  async function handleUpload() {
    if (!file) return setError('请先选择 IES 文件。')
    setUploading(true); setError(''); setResult(null)
    try {
      const data = await uploadIes(file)
      setUpload(data)
      setForm({ ...EMPTY, source_luminous_flux_lm: data.parsed_info.suggested_source_luminous_flux_lm ?? '' })
    } catch (reason) { setError(reason.message) }
    finally { setUploading(false) }
  }

  async function handleGenerate() {
    const fields = [['source_luminous_flux_lm', '原始实测总光通量'], ['target_power_w', '目标功率'], ['target_luminous_flux_lm', '目标光通量']]
    if (!form.target_model.trim()) return setError('请填写目标型号。')
    const invalid = fields.find(([key]) => !Number.isFinite(Number(form[key])) || Number(form[key]) <= 0)
    if (invalid) return setError(`请填写大于 0 的${invalid[1]}。`)
    if (!Number.isFinite(Number(form.target_luminous_length_mm)) || Number(form.target_luminous_length_mm) <= 0) return setError('请填写大于 0 的发光面长度，用于亮度限制曲线计算。')
    if (!Number.isFinite(Number(form.target_luminous_width_mm)) || Number(form.target_luminous_width_mm) <= 0) return setError('请填写大于 0 的发光面宽度，用于亮度限制曲线计算。')
    if (!CHANGES[form.change_type].allow) return setError('该变更会改变配光形状，请重新实测。')
    setGenerating(true); setError(''); setResult(null)
    const payload = {
      uploaded_file_id: upload.uploaded_file_id,
      source_luminous_flux_lm: Number(form.source_luminous_flux_lm),
      target_power_w: Number(form.target_power_w),
      target_luminous_flux_lm: Number(form.target_luminous_flux_lm),
      target_model: form.target_model,
      change_type: form.change_type,
      report_supplement: Object.fromEntries(Object.entries(form.report_supplement || {}).filter(([key, value]) => value !== '' && key !== 'company_logo_name').map(([key,value]) => [key, ['voltage_v','current_a','power_factor','cct_k','cri_ra','fixture_length_mm','fixture_width_mm','fixture_height_mm','calculation_height_m','plane_extent_m'].includes(key) ? Number(value) : value])),
    }
    if (form.source_report_id) payload.source_report_id = form.source_report_id
    if (Object.keys(form.source_field_mapping || {}).length) payload.source_field_mapping = form.source_field_mapping
    payload.target_luminous_length_mm = Number(form.target_luminous_length_mm)
    payload.target_luminous_width_mm = Number(form.target_luminous_width_mm)
    try {
      const generated = await generateIes(payload)
      setResult(generated)
      requestAnimationFrame(() => document.getElementById('generation-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
    catch (reason) { setError(reason.message || '生成请求失败，请确认后端服务正在运行。') }
    finally { setGenerating(false) }
  }

  return <>
    <header className="hero"><div className="hero-inner">
      <div className="brand"><span className="brand-mark">IES</span><span>PHOTOMETRIC TOOLS</span></div>
      <div className="hero-copy"><p className="eyebrow light">海波AI 赋能LED 照明行业</p><h1>内部 IES<br/><em>快速换算工具</em></h1><p>基于原始实测数据，按目标光通量比例生成用于前期方案模拟的估算版 IES 文件。</p></div>
      <div className="formula"><span>SCALING PRINCIPLE</span><code>目标光通量<br/>───────── = 缩放比例<br/>原始光通量</code></div>
    </div></header>
    <main>
      <div className="disclaimer"><span aria-hidden="true">!</span><p><strong>内部估算工具</strong>　输出仅适用于前期方案模拟、内部评估和客户初步沟通，不可作为正式测试报告、认证文件或验收依据。</p></div>
      {error && <div className="notice danger error-banner" role="alert"><strong>操作未完成：</strong>{error}<button onClick={() => setError('')} aria-label="关闭错误提示">×</button></div>}
      <UploadForm file={file} onFileChange={selectFile} onUpload={handleUpload} loading={uploading}/>
      <IesInfoPanel upload={upload}/>
      {upload && <TargetForm form={form} setForm={setForm} onGenerate={handleGenerate} loading={generating} upload={upload} generateError={error}/>} 
      <ResultPanel result={result}/>
    </main>
    <footer>
      <div className="footer-inner">
        <div className="footer-brand"><span className="footer-mark">IES</span><span>IES SCALING TOOL · MVP</span></div>
        <div className="footer-contact">
          <span className="footer-contact-label">你的 AI 使用顾问</span>
          <a className="footer-contact-tel" href="tel:13601845391">周海波 13601845391</a>
        </div>
      </div>
      <p className="footer-note">所有正式交付项目均应重新进行光度实测</p>
    </footer>
  </>
}
