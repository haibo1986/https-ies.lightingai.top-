import { useState } from 'react'
import { downloadUrl } from '../api.js'
import PhotometricChart from './PhotometricChart.jsx'
import './ResultPanel.css'
import './CoreFiles.css'

const number = (value, digits = 2) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })

export default function ResultPanel({ result }) {
  const [tab, setTab] = useState('ies')
  if (!result) return null
  if (!result.allow_generate) return <div className="notice danger appear" role="alert"><strong>已阻止生成：</strong>{result.risk_message}</div>
  const preview = result.ies_preview || {}
  const tabs = [['ies', 'IES 预览'], ['report', '报告预览'], ['files', '文件中心']]

  return <section id="generation-result" className="card result-center appear" aria-labelledby="result-title">
    <header className="result-head">
      <div className="result-check" aria-hidden="true">✓</div>
      <div><p className="eyebrow">GENERATION COMPLETE</p><h2 id="result-title">IES 与专业光度报告已生成</h2><p>缩放比例 <strong>{Number(result.scale_factor).toFixed(4)}</strong> · 风险等级 <strong>{result.risk_level}</strong> · 校验 <strong>{preview.validation_passed ? '全部通过' : '存在异常'}</strong></p></div>
      <span className="estimate-badge">ESTIMATED · 非实验室实测</span>
    </header>
    <p className="result-warning">输出仅用于方案模拟与内部评估，不可替代光度实验室的重新测试、认证或验收文件。</p>
    <div className="result-tabs" role="tablist" aria-label="生成结果">
      {tabs.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
    </div>

    {tab === 'ies' && <div className="result-panel" role="tabpanel">
      <div className="preview-metrics">
        <div><span>目标型号</span><strong>{preview.target_model}</strong></div>
        <div><span>目标功率</span><strong>{number(preview.target_power_w)} W</strong></div>
        <div><span>目标光通量</span><strong>{number(preview.target_luminous_flux_lm)} lm</strong></div>
        <div><span>最大光强</span><strong>{number(preview.max_candela)} cd</strong></div>
      </div>
      <div className="validation-list"><h3>文件检查</h3>{preview.validation?.map(item => <span key={item.label} className={item.ok ? 'ok' : 'bad'}>{item.ok ? '✓' : '×'} {item.label}</span>)}</div>
      {preview.photometry && <div className="result-chart"><PhotometricChart photometry={preview.photometry}/></div>}
      <details className="raw-ies"><summary>查看 IES 原始文本（前 120 行）</summary><pre>{preview.text}</pre></details>
    </div>}

    {tab === 'report' && <div className="result-panel" role="tabpanel">
      <div className="report-preview-head"><div><h3>目标型号专业光度报告</h3><p>包含经典配光页面、亮度限制、等照度、区域光通量和完整光强矩阵。</p></div><a className="button secondary" href={downloadUrl(result.pdf_report_url)} target="_blank" rel="noreferrer">单独打开 PDF</a></div>
      <iframe className="report-frame" title="专业估算光度报告预览" src={downloadUrl(result.pdf_report_url)}/>
    </div>}

    {tab === 'files' && <div className="result-panel file-center" role="tabpanel">
      <section><div className="file-group-title"><span>01</span><div><h3>原始来源文件</h3><p>保留原文件，不参与改写。</p></div></div>
        {result.source_report ? <a className="file-row" href={downloadUrl(result.source_report.preview_url)} target="_blank" rel="noreferrer"><div><strong>{result.source_report.file_name}</strong><small>原始光度测试 PDF</small></div><span>预览原件 ↗</span></a> : <p className="empty-file">本次未附加原始光度测试 PDF。</p>}
      </section>
      <section><div className="file-group-title"><span>02</span><div><h3>核心交付文件</h3><p>以目标型号命名，IES 与 PDF 为本次生成的重点文件。</p></div></div>
        <div className="core-file-grid">
          <a className="core-file ies" href={downloadUrl(result.ies_download_url)}><b>IES</b><div><strong>{result.ies_file}</strong><span>目标型号配光文件</span></div><small>下载文件 ↓</small></a>
          <a className="core-file pdf" href={downloadUrl(result.pdf_report_download_url)}><b>PDF</b><div><strong>{result.pdf_report_file}</strong><span>经典版式专业估算光度报告</span></div><small>下载文件 ↓</small></a>
        </div>
        <details className="supporting-files"><summary>其他辅助文件</summary><div className="file-grid">
          {result.template_pdf_download_url && <a className="file-tile" href={downloadUrl(result.template_pdf_download_url)}><b>PDF</b><span>原版式估算报告</span><small>下载</small></a>}
          <a className="file-tile" href={downloadUrl(result.html_report_download_url)}><b>HTML</b><span>网页预览</span><small>下载</small></a>
          <a className="file-tile" href={downloadUrl(result.markdown_report_url)}><b>MD</b><span>内部说明</span><small>下载</small></a>
        </div></details>
      </section>
    </div>}
  </section>
}
