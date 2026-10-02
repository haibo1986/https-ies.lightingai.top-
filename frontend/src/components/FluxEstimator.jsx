import {useEffect, useState} from 'react'
import './FluxEstimator.css'
import CurveImageDigitizer from './CurveImageDigitizer.jsx'
import { fetchLedLibrary, saveLedModel } from '../api.js'
import { computeEstimate, parseCurve, rangeFor } from '../estimator-core.js'

const SCENARIOS=[
  {id:'current',title:'调整LED电流',desc:'颗数保持不变，导入电流—相对光通量数据'},
  {id:'count',title:'调整LED颗数',desc:'单颗电流不变，自动检查颗数密度'},
  {id:'combined',title:'颗数和电流都变',desc:'同时应用颗数比例与LED电流曲线'},
  {id:'module',title:'灯具长度 / 模组变化',desc:'相同结构重复扩展，并更新IES发光尺寸'},
]
const MORE=[
  {id:'pwm',title:'PWM调光',desc:'峰值电流不变，仅改变占空比'},
  {id:'efficacy',title:'按功率和光效估算',desc:'缺少LED数据时的低置信度备用方式'},
]
const OPTICAL_SCENARIOS=new Set(['current','count','combined','module'])
const initial={source_current:'',target_current:'',source_count:'',target_count:'',source_length_mm:'',target_length_mm:'',target_width_mm:'',source_modules:'',target_modules:'',source_duty:'100',target_duty:'',target_efficacy:'',curve_text:'',reference_current:'',reference_flux:'',thermal:'same',optical:'unchanged',source_transmission:'100',target_transmission:'100'}
const n=value=>Number(value)
const positive=value=>Number.isFinite(n(value))&&n(value)>0
const fmt=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:0})

export default function FluxEstimator({sourceFlux,targetPower,parsedInfo,targetDims,onApply}){
  const ESTIMATOR_KEY='ies-estimator-values'
  const[open,setOpen]=useState(false),[scenario,setScenario]=useState(''),[values,setValues]=useState(()=>{try{return{...initial,...JSON.parse(localStorage.getItem(ESTIMATOR_KEY)||'{}')}}catch{return initial}})
  const[library,setLibrary]=useState([]),[libraryLoaded,setLibraryLoaded]=useState(false),[modelName,setModelName]=useState(''),[saving,setSaving]=useState(false),[libraryMessage,setLibraryMessage]=useState('')
  const[autoSource,setAutoSource]=useState(null)
  const update=e=>setValues(current=>({...current,[e.target.name]:e.target.value}))
  useEffect(()=>{try{localStorage.setItem(ESTIMATOR_KEY,JSON.stringify(values))}catch{/* 忽略存储失败 */}},[values])
  useEffect(()=>{if(open&&!libraryLoaded){setLibraryLoaded(true);fetchLedLibrary().then(data=>setLibrary(data.models||[])).catch(()=>setLibrary([]))}},[open])
  const applyModel=event=>{const name=event.target.value;setModelName(name);setLibraryMessage('');const model=library.find(item=>item.name===name);if(model)setValues(current=>({...current,curve_text:model.points.map(([c,f])=>`${c},${f}`).join('\n'),reference_current:model.reference?String(model.reference.current_ma):'',reference_flux:model.reference?String(model.reference.flux_lm):''}))}
  const saveModel=async()=>{const name=modelName.trim();if(!name||points.length<2)return;setSaving(true);setLibraryMessage('');try{const payload={name,note:'自定义数据',points:points.map(point=>[point.current,point.flux])};if(positive(values.reference_current)&&positive(values.reference_flux))payload.reference={current_ma:n(values.reference_current),flux_lm:n(values.reference_flux)};const data=await saveLedModel(payload);setLibrary(data.models||[]);setLibraryMessage(`已保存「${name}」，以后可在型号列表中选择。`)}catch(reason){setLibraryMessage(`保存失败：${reason.message}`)}finally{setSaving(false)}}
  const nativeToMm=value=>n(value)*(parsedInfo.units_type===2?1000:304.8)
  const sourceLengthDefault=parsedInfo.length?nativeToMm(parsedInfo.length):''
  const points=parseCurve(values.curve_text)
  // 发光面尺寸的唯一数据源是主表单；估算器只读取，不再提供重复输入
  const mainDims={length:n(targetDims?.length)||null,width:n(targetDims?.width)||null}
  const estimate=computeEstimate({scenario,values,points,sourceFlux,targetPower,sourceLengthDefault,mainDims,autoSource})
  const {result,sourceFluxAbs,error,warning,confidence,changeType}=estimate
  // 实时同步：有有效估算结果时自动写入表单（目标光通量、原始光通量[绝对路径]、变更类型），
  // 参数每次调整都会重新计算并同步；结果无效时保留表单现值、由错误提示引导。
  useEffect(()=>{
    if(result==null)return
    onApply({flux:Math.round(result),sourceFlux:sourceFluxAbs,changeType})
    if(sourceFluxAbs!=null)setAutoSource(Math.round(sourceFluxAbs))
  },[result,sourceFluxAbs,changeType])
  const resultRange=result?rangeFor(result,confidence):null
  const readCurve=async event=>{
    const file=event.target.files?.[0]
    if(!file)return
    try{
      let text=''
      if(/\.xlsx?$/i.test(file.name)){
        const XLSX=await import('xlsx')
        const workbook=XLSX.read(await file.arrayBuffer(),{type:'array'})
        const sheet=workbook.Sheets[workbook.SheetNames[0]]
        text=XLSX.utils.sheet_to_csv(sheet,{FS:',',blankrows:false})
      }else text=await file.text()
      setValues(current=>({...current,curve_text:text}))
    }finally{event.target.value=''}
  }

  return <div className="flux-estimator">
    <button type="button" className="estimator-trigger" onClick={()=>setOpen(value=>!value)} aria-expanded={open}><span><b>不知道目标光通量？</b><small>根据LED颗数、电流曲线、模组或调光状态进行估算</small></span><i aria-hidden="true">{open?'收起':'打开估算器 →'}</i></button>
    {open&&<div className="estimator-panel"><div className="estimator-step"><span>01</span><div><b>你改变了什么？</b><small>选择最接近目标灯具的变化方式</small></div></div><div className="scenario-grid">{SCENARIOS.map(item=><button type="button" key={item.id} className={scenario===item.id?'selected':''} onClick={()=>setScenario(item.id)}><b>{item.title}</b><small>{item.desc}</small></button>)}</div><div className="more-scenarios"><span>更多方式</span>{MORE.map(item=><button type="button" key={item.id} className={scenario===item.id?'selected':''} onClick={()=>setScenario(item.id)}>{item.title}</button>)}</div>
      {scenario&&<div className="estimator-workspace"><div className="estimator-inputs"><div className="estimator-step"><span>02</span><div><b>补充计算依据</b><small>这里只显示当前场景需要的数据</small></div></div>
        {(scenario==='current'||scenario==='combined')&&<><div className="mini-grid"><Field label="原始单颗电流" name="source_current" value={values.source_current} onChange={update} unit="mA"/><Field label="目标单颗电流" name="target_current" value={values.target_current} onChange={update} unit="mA"/></div>{scenario==='combined'&&<div className="mini-grid"><Field label="原始LED颗数" name="source_count" value={values.source_count} onChange={update} unit="颗"/><Field label="目标LED颗数" name="target_count" value={values.target_count} onChange={update} unit="颗"/></div>}<label className="select-label"><span>常用 LED 型号（可选）</span><select value={modelName} onChange={applyModel}><option value="">— 选择型号自动填入曲线 —</option>{library.map(model=><option key={model.name} value={model.name}>{model.name}{model.note?` · ${model.note}`:''}</option>)}</select></label><label className="curve-input"><span>导入 LED 电流—相对光通量数据</span><textarea name="curve_text" value={values.curve_text} onChange={update} placeholder={'每行一个数据点，例如：\n100,33\n300,88\n700,170\n1000,218'}/><input type="file" accept=".xlsx,.xls,.csv,.txt,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv" onChange={readCurve}/><small>支持 Excel（.xlsx/.xls）和 TXT/CSV；默认读取第一个工作表的前两列。已识别 {points.length} 个有效点。</small></label><div className="save-model-row"><input name="model_name" value={modelName} onChange={event=>setModelName(event.target.value)} placeholder="输入型号名称，如 2835-60mA方案"/><button type="button" className="button secondary" onClick={saveModel} disabled={saving||!modelName.trim()||points.length<2}>{saving?'保存中…':'存为常用型号'}</button></div><div className="mini-grid"><Field label="基准点电流（可选）" name="reference_current" value={values.reference_current} onChange={update} unit="mA"/><Field label="基准点光通量（可选）" name="reference_flux" value={values.reference_flux} onChange={update} unit="lm"/></div><small>曲线中某一点的绝对光通量，例如「300mA 时 218lm」。未填原始实测总光通量时用它直接算灯总光通量；已填时按比例路径计算，基准点不参与。</small>{libraryMessage&&<small className={`model-message${libraryMessage.startsWith('保存失败')?' error':''}`}>{libraryMessage}</small>}<CurveImageDigitizer onConfirm={curveText=>setValues(current=>({...current,curve_text:curveText}))}/><label className="select-label"><span>散热与结温条件</span><select name="thermal" value={values.thermal} onChange={update}><option value="same">与原灯具基本相同</option><option value="unknown">散热或结温未知</option></select></label></>}
        {scenario==='count'&&<><div className="mini-grid"><Field label="原始LED颗数" name="source_count" value={values.source_count} onChange={update} unit="颗"/><Field label="目标LED颗数" name="target_count" value={values.target_count} onChange={update} unit="颗"/><Field label="原始发光长度" name="source_length_mm" value={values.source_length_mm||sourceLengthDefault} onChange={update} unit="mm"/></div><small>目标发光面长度/宽度直接取上方主表单的填写值，不用重复填写。</small></>}
        {scenario==='module'&&<><div className="mini-grid"><Field label="原始模组数量" name="source_modules" value={values.source_modules} onChange={update} unit="个"/><Field label="目标模组数量" name="target_modules" value={values.target_modules} onChange={update} unit="个"/></div><small>目标发光口尺寸取上方主表单的填写值（{mainDims.length?`已填 ${mainDims.length}×${mainDims.width} mm`:'尚未填写，请先在上方填写'}），会同步写入 IES。</small></>}
        {scenario==='pwm'&&<><div className="mini-grid"><Field label="原始PWM占空比" name="source_duty" value={values.source_duty} onChange={update} unit="%"/><Field label="目标PWM占空比" name="target_duty" value={values.target_duty} onChange={update} unit="%"/></div><p className="context-note">适用于DALI、0–10V、智能调光、日夜模式或应急模式中，LED峰值电流保持不变的情况。</p></>}
        {scenario==='efficacy'&&<Field label="预计目标光效" name="target_efficacy" value={values.target_efficacy} onChange={update} unit="lm/W"/>}
        {OPTICAL_SCENARIOS.has(scenario)&&<label className="select-label"><span>透镜与光学结构</span><select name="optical" value={values.optical} onChange={update}><option value="unchanged">完全不变</option><option value="transmission">仅材料透过率变化</option><option value="changed">透镜或光学结构变化</option></select></label>}{OPTICAL_SCENARIOS.has(scenario)&&values.optical==='transmission'&&<div className="mini-grid"><Field label="原材料透过率" name="source_transmission" value={values.source_transmission} onChange={update} unit="%"/><Field label="目标材料透过率" name="target_transmission" value={values.target_transmission} onChange={update} unit="%"/></div>}
      </div><aside className="estimate-result" aria-live="polite"><span className="result-kicker">ESTIMATED OUTPUT</span><b>估算目标光通量</b><strong>{result?fmt(result):'—'}<small> lm</small></strong>{resultRange&&<p>建议范围 {fmt(resultRange[0])}–{fmt(resultRange[1])} lm</p>}{sourceFluxAbs!=null&&<p className="source-estimate">原始光通量估算：<b>{fmt(sourceFluxAbs)} lm</b>（已同步填入表单）</p>}<div className={`confidence ${confidence}`}>置信度：{confidence==='high'?'高':confidence==='medium'?'中等':'低'}</div>{error&&<div className="estimate-message error">{error}</div>}{warning&&!error&&<div className="estimate-message warning">{warning}</div>}{result!=null&&!error&&<p className="synced-note">✓ 已实时同步到表单（目标光通量{sourceFluxAbs!=null?'、原始光通量':''}、变更类型）</p>}</aside></div>}
    </div>}
  </div>
}

function Field({label,name,value,onChange,unit}){return <label className="estimator-field"><span>{label}</span><div><input name={name} type="number" min="0" step="any" value={value} onChange={onChange}/><i>{unit}</i></div></label>}
