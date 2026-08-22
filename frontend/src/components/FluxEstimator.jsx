import {useEffect, useState} from 'react'
import './FluxEstimator.css'
import CurveImageDigitizer from './CurveImageDigitizer.jsx'
import { fetchLedLibrary, saveLedModel } from '../api.js'

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
const initial={source_current:'',target_current:'',source_count:'',target_count:'',source_length_mm:'',target_length_mm:'',target_width_mm:'',source_modules:'',target_modules:'',source_duty:'100',target_duty:'',target_efficacy:'',curve_text:'',thermal:'same',optical:'unchanged',source_transmission:'100',target_transmission:'100'}
const n=value=>Number(value)
const positive=value=>Number.isFinite(n(value))&&n(value)>0

function parseCurve(text){
  const points=text.split(/\r?\n/).map(line=>line.trim()).filter(Boolean).map(line=>line.split(/[\s,;，\t]+/).map(Number)).filter(row=>row.length>=2&&row.every(Number.isFinite)).map(([current,flux])=>({current,flux})).sort((a,b)=>a.current-b.current)
  return points.filter((point,index)=>index===0||point.current!==points[index-1].current)
}
function interpolate(points,current){
  if(points.length<2||current<points[0].current||current>points.at(-1).current)return null
  const exact=points.find(point=>point.current===current);if(exact)return exact.flux
  const upper=points.findIndex(point=>point.current>current);const a=points[upper-1],b=points[upper]
  return a.flux+(current-a.current)*(b.flux-a.flux)/(b.current-a.current)
}
function rangeFor(value,confidence){const spread=confidence==='high'?.05:confidence==='medium'?.1:.2;return [value*(1-spread),value*(1+spread)]}
const fmt=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:0})

export default function FluxEstimator({sourceFlux,targetPower,parsedInfo,onApply}){
  const[open,setOpen]=useState(false),[scenario,setScenario]=useState(''),[values,setValues]=useState(initial)
  const[library,setLibrary]=useState([]),[libraryLoaded,setLibraryLoaded]=useState(false),[modelName,setModelName]=useState(''),[saving,setSaving]=useState(false),[libraryMessage,setLibraryMessage]=useState('')
  const update=e=>setValues(current=>({...current,[e.target.name]:e.target.value}))
  useEffect(()=>{if(open&&!libraryLoaded){setLibraryLoaded(true);fetchLedLibrary().then(data=>setLibrary(data.models||[])).catch(()=>setLibrary([]))}},[open])
  const applyModel=event=>{const name=event.target.value;setModelName(name);setLibraryMessage('');const model=library.find(item=>item.name===name);if(model)setValues(current=>({...current,curve_text:model.points.map(([c,f])=>`${c},${f}`).join('\n')}))}
  const saveModel=async()=>{const name=modelName.trim();if(!name||points.length<2)return;setSaving(true);setLibraryMessage('');try{const data=await saveLedModel({name,note:'自定义数据',points:points.map(point=>[point.current,point.flux])});setLibrary(data.models||[]);setLibraryMessage(`已保存「${name}」，以后可在型号列表中选择。`)}catch(reason){setLibraryMessage(`保存失败：${reason.message}`)}finally{setSaving(false)}}
  const nativeToMm=value=>n(value)*(parsedInfo.units_type===2?1000:304.8)
  const sourceLengthDefault=parsedInfo.length?nativeToMm(parsedInfo.length):''
  const sourceWidthDefault=parsedInfo.width?nativeToMm(parsedInfo.width):''
  const points=parseCurve(values.curve_text)
  let result=null,error='',warning='',confidence='high',changeType='power_only',targetLength=null,targetWidth=null
  const source=n(sourceFlux)
  const opticalFactor=values.optical==='transmission'&&positive(values.source_transmission)&&positive(values.target_transmission)?n(values.target_transmission)/n(values.source_transmission):1
  if(scenario&&positive(source)){
    if(values.optical==='changed')error='透镜或光学结构变化会改变配光形状，不能使用简单换算，请重新实测。'
    else if(scenario==='current'||scenario==='combined'){
      if(!positive(values.source_current)||!positive(values.target_current))error='请填写原始和目标单颗电流。'
      else if(points.length<2)error='请导入或粘贴至少两个“电流,相对光通量”数据点。'
      else{const a=interpolate(points,n(values.source_current)),b=interpolate(points,n(values.target_current));if(a==null||b==null)error=`电流必须位于曲线范围 ${points[0].current}–${points.at(-1).current} mA 内，软件不会自动外推。`;else{let factor=b/a;if(scenario==='combined'){if(!positive(values.source_count)||!positive(values.target_count))error='请填写原始和目标LED颗数。';else factor*=n(values.target_count)/n(values.source_count)}if(!error)result=source*factor*opticalFactor;confidence=values.thermal==='unknown'?'low':'medium';changeType=scenario==='combined'?'led_count_change':'power_only';warning=values.thermal==='unknown'?'散热和结温未知，结果范围已扩大；建议补充同型号LED温度曲线或实测温度。':'按热条件基本相同估算；提高电流后如温升明显，实际光通量可能偏低。'}}
    }else if(scenario==='count'){
      if(!positive(values.source_count)||!positive(values.target_count))error='请填写原始和目标LED颗数。'
      else{result=source*n(values.target_count)/n(values.source_count)*opticalFactor;changeType='led_count_change';const sl=n(values.source_length_mm||sourceLengthDefault),tl=n(values.target_length_mm||sourceLengthDefault);if(sl>0&&tl>0){const sourceDensity=n(values.source_count)/(sl/1000),targetDensity=n(values.target_count)/(tl/1000),drop=1-targetDensity/sourceDensity;if(drop>.25){error=`LED密度下降${Math.round(drop*100)}%，可能明显产生亮暗斑；请调整方案或重新实测。`;result=null}else if(drop>.1){warning=`LED密度下降${Math.round(drop*100)}%（${sourceDensity.toFixed(1)}→${targetDensity.toFixed(1)}颗/m），可能影响近场洗墙均匀性。`;confidence='medium'}targetLength=tl;targetWidth=n(values.target_width_mm||sourceWidthDefault)||null}}
    }else if(scenario==='module'){
      if(!positive(values.source_modules)||!positive(values.target_modules))error='请填写原始和目标模组数量。'
      else if(!positive(values.target_length_mm)||!positive(values.target_width_mm))error='请填写目标发光口长度和宽度，软件将同步写入IES。'
      else{result=source*n(values.target_modules)/n(values.source_modules)*opticalFactor;changeType='length_change';targetLength=n(values.target_length_mm);targetWidth=n(values.target_width_mm);confidence='medium';warning='发光尺寸会同步写入IES，但模组间距变化仍可能影响近场均匀性。'}
    }else if(scenario==='pwm'){
      if(!positive(values.source_duty)||!positive(values.target_duty)||n(values.source_duty)>100||n(values.target_duty)>100)error='PWM占空比必须在0–100%之间。'
      else{result=source*n(values.target_duty)/n(values.source_duty);warning='仅适用于峰值电流不变的PWM调光，不适用于模拟调流。'}
    }else if(scenario==='efficacy'){
      if(!positive(targetPower)||!positive(values.target_efficacy))error='请先填写目标功率和预计目标光效。'
      else{result=n(targetPower)*n(values.target_efficacy);confidence='low';warning='功率×光效属于低置信度备用估算，未直接反映LED电流、驱动效率和温升。'}
    }
  }
  const resultRange=result?rangeFor(result,confidence):null
  const apply=()=>result&&onApply({flux:Math.round(result),changeType,targetLength,targetWidth})
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
        {(scenario==='current'||scenario==='combined')&&<><div className="mini-grid"><Field label="原始单颗电流" name="source_current" value={values.source_current} onChange={update} unit="mA"/><Field label="目标单颗电流" name="target_current" value={values.target_current} onChange={update} unit="mA"/></div>{scenario==='combined'&&<div className="mini-grid"><Field label="原始LED颗数" name="source_count" value={values.source_count} onChange={update} unit="颗"/><Field label="目标LED颗数" name="target_count" value={values.target_count} onChange={update} unit="颗"/></div>}<label className="select-label"><span>常用 LED 型号（可选）</span><select value={modelName} onChange={applyModel}><option value="">— 选择型号自动填入曲线 —</option>{library.map(model=><option key={model.name} value={model.name}>{model.name}{model.note?` · ${model.note}`:''}</option>)}</select></label><label className="curve-input"><span>导入 LED 电流—相对光通量数据</span><textarea name="curve_text" value={values.curve_text} onChange={update} placeholder={'每行一个数据点，例如：\n100,33\n300,88\n700,170\n1000,218'}/><input type="file" accept=".xlsx,.xls,.csv,.txt,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv" onChange={readCurve}/><small>支持 Excel（.xlsx/.xls）和 TXT/CSV；默认读取第一个工作表的前两列。已识别 {points.length} 个有效点。</small></label><div className="save-model-row"><input name="model_name" value={modelName} onChange={event=>setModelName(event.target.value)} placeholder="输入型号名称，如 2835-60mA方案"/><button type="button" className="button secondary" onClick={saveModel} disabled={saving||!modelName.trim()||points.length<2}>{saving?'保存中…':'存为常用型号'}</button></div>{libraryMessage&&<small className={`model-message${libraryMessage.startsWith('保存失败')?' error':''}`}>{libraryMessage}</small>}<CurveImageDigitizer onConfirm={curveText=>setValues(current=>({...current,curve_text:curveText}))}/><label className="select-label"><span>散热与结温条件</span><select name="thermal" value={values.thermal} onChange={update}><option value="same">与原灯具基本相同</option><option value="unknown">散热或结温未知</option></select></label></>}
        {scenario==='count'&&<><div className="mini-grid"><Field label="原始LED颗数" name="source_count" value={values.source_count} onChange={update} unit="颗"/><Field label="目标LED颗数" name="target_count" value={values.target_count} onChange={update} unit="颗"/><Field label="原始发光长度" name="source_length_mm" value={values.source_length_mm||sourceLengthDefault} onChange={update} unit="mm"/><Field label="目标发光长度" name="target_length_mm" value={values.target_length_mm||sourceLengthDefault} onChange={update} unit="mm"/><Field label="目标发光宽度" name="target_width_mm" value={values.target_width_mm||sourceWidthDefault} onChange={update} unit="mm"/></div></>}
        {scenario==='module'&&<div className="mini-grid"><Field label="原始模组数量" name="source_modules" value={values.source_modules} onChange={update} unit="个"/><Field label="目标模组数量" name="target_modules" value={values.target_modules} onChange={update} unit="个"/><Field label="目标发光口长度" name="target_length_mm" value={values.target_length_mm} onChange={update} unit="mm"/><Field label="目标发光口宽度" name="target_width_mm" value={values.target_width_mm} onChange={update} unit="mm"/></div>}
        {scenario==='pwm'&&<><div className="mini-grid"><Field label="原始PWM占空比" name="source_duty" value={values.source_duty} onChange={update} unit="%"/><Field label="目标PWM占空比" name="target_duty" value={values.target_duty} onChange={update} unit="%"/></div><p className="context-note">适用于DALI、0–10V、智能调光、日夜模式或应急模式中，LED峰值电流保持不变的情况。</p></>}
        {scenario==='efficacy'&&<Field label="预计目标光效" name="target_efficacy" value={values.target_efficacy} onChange={update} unit="lm/W"/>}
        {OPTICAL_SCENARIOS.has(scenario)&&<label className="select-label"><span>透镜与光学结构</span><select name="optical" value={values.optical} onChange={update}><option value="unchanged">完全不变</option><option value="transmission">仅材料透过率变化</option><option value="changed">透镜或光学结构变化</option></select></label>}{OPTICAL_SCENARIOS.has(scenario)&&values.optical==='transmission'&&<div className="mini-grid"><Field label="原材料透过率" name="source_transmission" value={values.source_transmission} onChange={update} unit="%"/><Field label="目标材料透过率" name="target_transmission" value={values.target_transmission} onChange={update} unit="%"/></div>}
      </div><aside className="estimate-result" aria-live="polite"><span className="result-kicker">ESTIMATED OUTPUT</span><b>估算目标光通量</b><strong>{result?fmt(result):'—'}<small> lm</small></strong>{resultRange&&<p>建议范围 {fmt(resultRange[0])}–{fmt(resultRange[1])} lm</p>}<div className={`confidence ${confidence}`}>置信度：{confidence==='high'?'高':confidence==='medium'?'中等':'低'}</div>{error&&<div className="estimate-message error">{error}</div>}{warning&&!error&&<div className="estimate-message warning">{warning}</div>}<button type="button" className="button primary" onClick={apply} disabled={!result||Boolean(error)}>使用这个估算值</button></aside></div>}
    </div>}
  </div>
}

function Field({label,name,value,onChange,unit}){return <label className="estimator-field"><span>{label}</span><div><input name={name} type="number" min="0" step="any" value={value} onChange={onChange}/><i>{unit}</i></div></label>}
