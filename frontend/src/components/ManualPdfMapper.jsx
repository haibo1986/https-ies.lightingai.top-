import {useState} from 'react'
import {downloadUrl} from '../api.js'
import './ManualPdfMapper.css'

const FIELDS=[['model','灯具型号'],['power_w','输入功率'],['luminous_flux_lm','总光通量'],['efficacy_lm_w','光效'],['max_candela_cd','最大光强']]

export default function ManualPdfMapper({reportId,value={},onChange}){
  const[active,setActive]=useState('model'),[start,setStart]=useState(null)
  const click=event=>{
    const rect=event.currentTarget.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width,y=(event.clientY-rect.top)/rect.height
    if(!start){setStart({x,y});return}
    const box={page:1,x:Math.min(start.x,x),y:Math.min(start.y,y),w:Math.max(Math.abs(x-start.x),.01),h:Math.max(Math.abs(y-start.y),.01)}
    onChange({...value,[active]:box});setStart(null)
    const index=FIELDS.findIndex(([key])=>key===active);if(index<FIELDS.length-1)setActive(FIELDS[index+1][0])
  }
  return <div className="pdf-mapper">
    <div className="mapper-heading"><div><strong>人工标定原报告字段</strong><p>该版式尚无模板。选择字段后，在报告首页依次点击区域左上角和右下角。</p></div><span>{Object.keys(value).length}/5</span></div>
    <div className="mapper-fields">{FIELDS.map(([key,label])=><button type="button" key={key} className={`${active===key?'active':''} ${value[key]?'done':''}`} onClick={()=>{setActive(key);setStart(null)}}>{value[key]?'✓ ':''}{label}</button>)}</div>
    <div className={`mapper-page ${start?'marking':''}`} onClick={click} role="button" tabIndex="0" aria-label="在PDF首页标定字段位置">
      <img src={downloadUrl(`/api/source-report/${reportId}/page/1.png`)} alt="原始PDF首页" draggable="false"/>
      {Object.entries(value).map(([key,box])=><span key={key} className={`mapped-box ${active===key?'active':''}`} style={{left:`${box.x*100}%`,top:`${box.y*100}%`,width:`${box.w*100}%`,height:`${box.h*100}%`}}>{FIELDS.find(item=>item[0]===key)?.[1]}</span>)}
      {start&&<i className="mapper-start" style={{left:`${start.x*100}%`,top:`${start.y*100}%`}}/>}
    </div>
    <p className="mapper-status">{start?'已记录左上角，请点击该字段区域的右下角。':Object.keys(value).length===5?'✓ 五个字段已完成，可以生成原版式报告。':`当前标定：${FIELDS.find(item=>item[0]===active)?.[1]}`}</p>
  </div>
}
