import { useEffect, useState } from 'react'
import './ReportSupplementForm.css'
import { fetchCustomerLibrary, saveCustomer as saveCustomerApi } from '../api.js'

const FIELD_GROUPS = [
  { title: '报告身份', tag: 'DOCUMENT', fields: [
    ['company_name','企业名称','text','例如：某某照明科技有限公司'],
    ['company_website','企业网址','text','www.example.com'],
    ['company_phone','联系电话','text','0760-00000000'],
    ['manufacturer','生产厂家','text','留空则使用企业名称'],
    ['report_number','报告编号','text','留空则自动生成'],
    ['report_date','报告日期','date','','留空则自动填生成日期'],
    ['product_description','产品描述','text','例如：户外线性洗墙灯'],
  ]},
  { title: '电气与颜色', tag: 'ELECTRICAL', fields: [
    ['voltage_v','输入电压','number','V','灯具实际输入电压，如 24 / 220'],
    ['current_a','输入电流','number','A','灯具整灯输入电流（不是单颗 LED 电流，那是估算器里的 mA）'],
    ['power_factor','功率因数','number','0-1','如 0.95'],
    ['cct_k','相关色温','number','K','如 3000 / 4000 / 5700'],
    ['cri_ra','显色指数','number','Ra','一般 70–95，如 80'],
  ]},
  { title: '灯具外形', tag: 'MECHANICAL', fields: [
    ['fixture_length_mm','灯具长度','number','mm','灯具外壳长度（非发光面），仅用于报告信息展示，不参与计算'],
    ['fixture_width_mm','灯具宽度','number','mm','灯具外壳宽度（非发光面），仅用于报告信息展示，不参与计算'],
    ['fixture_height_mm','灯具高度','number','mm','灯具外壳高度（非发光面），仅用于报告信息展示，不参与计算'],
    ['calculation_height_m','等照度计算高度','number','m','建议：洗墙灯 1–4m · 投光灯 3–25m · 路灯按杆高 6–12m（行业经验值）；仅影响报告等照度图，不影响 IES 数据'],
    ['plane_extent_m','平面计算半径','number','m','一般取计算高度的 3 倍左右；仅影响报告等照度图'],
  ]},
]

export default function ReportSupplementForm({ value, onChange, luminousDims }) {
  const [customers, setCustomers] = useState([])
  const [customerName, setCustomerName] = useState('')
  const [saving, setSaving] = useState(false)
  const [customerMessage, setCustomerMessage] = useState('')
  useEffect(() => { fetchCustomerLibrary().then(data => setCustomers(data.customers || [])).catch(() => setCustomers([])) }, [])
  const applyCustomer = event => {
    const name = event.target.value
    setCustomerName(name); setCustomerMessage('')
    const template = customers.find(item => item.name === name)
    if (template) onChange({ ...value, ...template.fields })
  }
  const saveCustomer = async () => {
    const name = customerName.trim()
    if (!name) return
    const fields = Object.fromEntries(FIELD_GROUPS.flatMap(group => group.fields.map(([key]) => [key, value[key]])))
    setSaving(true); setCustomerMessage('')
    try {
      const data = await saveCustomerApi({ name, fields })
      setCustomers(data.customers || [])
      setCustomerMessage(`已保存「${name}」，以后可在客户列表中选择。`)
    } catch (reason) { setCustomerMessage(`保存失败：${reason.message}`) }
    finally { setSaving(false) }
  }
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
    <div className="customer-row">
      <select value={customerName} onChange={applyCustomer} aria-label="选择客户模板"><option value="">— 选择客户模板一键填入 —</option>{customers.map(customer => <option key={customer.name} value={customer.name}>{customer.name}</option>)}</select>
      <input value={customerName} onChange={event => setCustomerName(event.target.value)} placeholder="客户名称，如 中山市某照明公司" aria-label="客户名称"/>
      <button type="button" className="button secondary" onClick={saveCustomer} disabled={saving || !customerName.trim()}>{saving ? '保存中…' : '存为客户模板'}</button>
      {customerMessage && <span className={`customer-message${customerMessage.startsWith('保存失败') ? ' error' : ''}`}>{customerMessage}</span>}
    </div>
    {FIELD_GROUPS.map(group => <section className="supplement-group" key={group.tag}>
      <div className="supplement-label"><span>{group.tag}</span><strong>{group.title}</strong>{group.tag==='MECHANICAL'&&luminousDims?.length&&<button type="button" className="button secondary copy-dims" onClick={()=>onChange({...value,fixture_length_mm:luminousDims.length,fixture_width_mm:luminousDims.width})}>长宽与发光面相同</button>}</div>
      <div className="supplement-grid">{group.fields.map(([name,label,type,placeholder,hint]) => <label key={name}><span>{label}</span><div className="supplement-input"><input name={name} type={type} step={type === 'number' ? 'any' : undefined} min={type === 'number' ? '0' : undefined} value={value[name] || ''} onChange={update} placeholder={placeholder}/>{type === 'number' && placeholder && !['0-1','Ra'].includes(placeholder) && <i>{placeholder}</i>}</div>{hint && <small className="supplement-hint">{hint}</small>}</label>)}</div>
    </section>)}
    <div className="brand-upload"><div><strong>公司 Logo</strong><span>PNG/JPG，建议透明背景，不超过 2 MB</span></div><label>{value.company_logo_name || '选择 Logo'}<input type="file" accept="image/png,image/jpeg" onChange={addLogo}/></label>{value.company_logo_data_url && <img src={value.company_logo_data_url} alt="公司Logo预览"/>}</div>
    <label className="supplement-notes"><span>报告备注</span><textarea name="notes" maxLength="500" value={value.notes || ''} onChange={update} placeholder="可填写应用场景、估算边界或客户项目备注。"/></label>
  </div>
}
