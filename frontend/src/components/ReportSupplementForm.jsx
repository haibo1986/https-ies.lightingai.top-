import './ReportSupplementForm.css'

const FIELD_GROUPS = [
  { title: '报告身份', tag: 'DOCUMENT', fields: [
    ['company_name','企业名称','text','例如：某某照明科技有限公司'],
    ['company_website','企业网址','text','www.example.com'],
    ['company_phone','联系电话','text','0760-00000000'],
    ['manufacturer','生产厂家','text','留空则使用企业名称'],
    ['report_number','报告编号','text','留空则自动生成'],
    ['report_date','报告日期','date',''],
    ['product_description','产品描述','text','例如：户外线性洗墙灯'],
  ]},
  { title: '电气与颜色', tag: 'ELECTRICAL', fields: [
    ['voltage_v','输入电压','number','V'],['current_a','输入电流','number','A'],
    ['power_factor','功率因数','number','0-1'],['cct_k','相关色温','number','K'],['cri_ra','显色指数','number','Ra'],
  ]},
  { title: '灯具外形', tag: 'MECHANICAL', fields: [
    ['fixture_length_mm','灯具长度','number','mm'],['fixture_width_mm','灯具宽度','number','mm'],['fixture_height_mm','灯具高度','number','mm'],
    ['calculation_height_m','等照度计算高度','number','m'],['plane_extent_m','平面计算半径','number','m'],
  ]},
]

export default function ReportSupplementForm({ value, onChange }) {
  const update = event => onChange({ ...value, [event.target.name]: event.target.value })
  const addLogo = event => {
    const file = event.target.files?.[0]
    if (!file || file.size > 2 * 1024 * 1024) return
    const reader = new FileReader()
    reader.onload = () => onChange({ ...value, company_logo_data_url: reader.result, company_logo_name: file.name })
    reader.readAsDataURL(file)
  }
  return <div className="supplement-shell">
    <div className="supplement-head"><div><span>REPORT METADATA</span><strong>标准报告补充信息</strong><p>这些字段由用户提供，并在报告中与 IES 计算数据分开标识；全部可选。</p></div><i>USER INPUT</i></div>
    {FIELD_GROUPS.map(group => <section className="supplement-group" key={group.tag}>
      <div className="supplement-label"><span>{group.tag}</span><strong>{group.title}</strong></div>
      <div className="supplement-grid">{group.fields.map(([name,label,type,placeholder]) => <label key={name}><span>{label}</span><div className="supplement-input"><input name={name} type={type} step={type === 'number' ? 'any' : undefined} min={type === 'number' ? '0' : undefined} value={value[name] || ''} onChange={update} placeholder={placeholder}/>{type === 'number' && placeholder && !['0-1','Ra'].includes(placeholder) && <i>{placeholder}</i>}</div></label>)}</div>
    </section>)}
    <div className="brand-upload"><div><strong>公司 Logo</strong><span>PNG/JPG，建议透明背景，不超过 2 MB</span></div><label>{value.company_logo_name || '选择 Logo'}<input type="file" accept="image/png,image/jpeg" onChange={addLogo}/></label>{value.company_logo_data_url && <img src={value.company_logo_data_url} alt="公司Logo预览"/>}</div>
    <label className="supplement-notes"><span>报告备注</span><textarea name="notes" maxLength="500" value={value.notes || ''} onChange={update} placeholder="可填写应用场景、估算边界或客户项目备注。"/></label>
  </div>
}
