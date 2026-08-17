import {useEffect,useRef,useState} from 'react'
import './CurveImageDigitizer.css'
import './DigitizerMessage.css'

const STEP_TEXT={origin:'点击左下角的坐标原点',xMax:'点击右下角的X轴最大刻度点',yMax:'点击左上角的Y轴最大刻度点',point:'沿曲线点击5–12个代表点'}
const calibrated=value=>Boolean(value.origin&&value.xMax&&value.yMax)

export default function CurveImageDigitizer({onConfirm}){
  const canvasRef=useRef(null),nextId=useRef(1)
  const[image,setImage]=useState(null),[mode,setMode]=useState('origin'),[calibration,setCalibration]=useState({origin:null,xMax:null,yMax:null}),[points,setPoints]=useState([]),[ranges,setRanges]=useState({xMin:'0',xMax:'1000',yMin:'0',yMax:'250'}),[message,setMessage]=useState(''),[imported,setImported]=useState(false)

  useEffect(()=>{if(!image)return;let active=true;const bitmap=new Image();bitmap.onload=()=>{if(!active)return;const canvas=canvasRef.current,ctx=canvas?.getContext('2d');if(!canvas||!ctx)return;canvas.width=bitmap.naturalWidth;canvas.height=bitmap.naturalHeight;ctx.drawImage(bitmap,0,0);const scale=Math.max(1,bitmap.naturalWidth/700);ctx.lineWidth=2*scale;ctx.font=`${13*scale}px sans-serif`;const line=(a,b,color,dashed=true)=>{ctx.save();ctx.strokeStyle=color;ctx.setLineDash(dashed?[7*scale,5*scale]:[]);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.restore()};if(calibration.origin&&mode==='xMax')line(calibration.origin,{x:bitmap.naturalWidth,y:calibration.origin.y},'#14835f');if(calibration.origin&&calibration.xMax&&mode==='yMax')line(calibration.origin,{x:calibration.origin.x,y:0},'#14835f');if(calibrated(calibration)){line(calibration.origin,calibration.xMax,'#0d5c45');line(calibration.origin,calibration.yMax,'#0d5c45')}const mark=(point,color,label)=>{if(!point)return;ctx.beginPath();ctx.arc(point.x,point.y,6*scale,0,Math.PI*2);ctx.fillStyle='#fff';ctx.fill();ctx.strokeStyle=color;ctx.stroke();ctx.fillStyle=color;ctx.fillText(label,point.x+10*scale,point.y-9*scale)};mark(calibration.origin,'#0d5c45','O 原点');mark(calibration.xMax,'#0d5c45','X 最大');mark(calibration.yMax,'#0d5c45','Y 最大');points.forEach((point,index)=>mark(point,'#c07823',String(index+1)))};bitmap.src=image.src;return()=>{active=false;bitmap.onload=null}},[image,mode,calibration,points])

  const reset=()=>{setCalibration({origin:null,xMax:null,yMax:null});setPoints([]);setMode('origin');setMessage('请先点击坐标图左下角的0/0交点。');setImported(false)}
  const loadImage=event=>{const file=event.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{const src=String(reader.result||'');const probe=new Image();probe.onload=()=>{setImage({src,name:file.name,width:probe.naturalWidth,height:probe.naturalHeight});reset()};probe.src=src};reader.readAsDataURL(file)}
  const updateRange=event=>{setRanges(current=>({...current,[event.target.name]:event.target.value}));setPoints([]);setImported(false)}
  const canvasClick=event=>{
    if(!image)return
    const canvas=canvasRef.current,rect=canvas.getBoundingClientRect(),point={x:(event.clientX-rect.left)*canvas.width/rect.width,y:(event.clientY-rect.top)*canvas.height/rect.height},xTolerance=canvas.width*.055,yTolerance=canvas.height*.055
    setImported(false)
    if(mode==='origin'){setCalibration({origin:point,xMax:null,yMax:null});setMode('xMax');setMessage('原点已标记。现在请点击右下角的X轴最大刻度点，不要点击曲线。');return}
    if(mode==='xMax'){
      if(point.x<calibration.origin.x+canvas.width*.25||Math.abs(point.y-calibration.origin.y)>yTolerance){setMessage('X轴点无效：它应在原点右侧，并与原点基本处于同一水平线。请重新点击右下角最大刻度点。');return}
      setCalibration(current=>({...current,xMax:point}));setMode('yMax');setMessage('X轴验证通过。现在请点击左上角的Y轴最大刻度点。');return
    }
    if(mode==='yMax'){
      if(point.y>calibration.origin.y-canvas.height*.25||Math.abs(point.x-calibration.origin.x)>xTolerance){setMessage('Y轴点无效：它应在原点上方，并与原点基本处于同一垂直线。请重新点击左上角最大刻度点。');return}
      if(!(Number(ranges.xMax)>Number(ranges.xMin)&&Number(ranges.yMax)>Number(ranges.yMin))){setMessage('坐标范围无效：最大值必须大于最小值。');return}
      setCalibration(current=>({...current,yMax:point}));setMode('point');setMessage('坐标轴验证通过，可以沿黑色曲线点击5–12个数据点。');return
    }
    if(!calibrated(calibration))return
    const insideX=point.x>=calibration.origin.x&&point.x<=calibration.xMax.x,insideY=point.y>=calibration.yMax.y&&point.y<=calibration.origin.y
    if(!insideX||!insideY){setMessage('该点位于已标定的坐标区域之外，请点击图表内部的曲线。');return}
    const current=Number(ranges.xMin)+(point.x-calibration.origin.x)/(calibration.xMax.x-calibration.origin.x)*(Number(ranges.xMax)-Number(ranges.xMin))
    const flux=Number(ranges.yMin)+(calibration.origin.y-point.y)/(calibration.origin.y-calibration.yMax.y)*(Number(ranges.yMax)-Number(ranges.yMin))
    if(!Number.isFinite(current)||!Number.isFinite(flux))return
    setPoints(list=>[...list,{...point,id:nextId.current++,current,flux}]);setMessage('数据点已采集。继续沿曲线取点，完成后检查下方数值。')
  }
  const updatePoint=(id,key,value)=>{setPoints(list=>list.map(point=>point.id===id?{...point,[key]:Number(value)}:point));setImported(false)}
  const removePoint=id=>{setPoints(list=>list.filter(point=>point.id!==id));setImported(false)}
  const confirm=()=>{const text=[...points].sort((a,b)=>a.current-b.current).map(point=>`${point.current.toFixed(2)},${point.flux.toFixed(2)}`).join('\n');if(text){onConfirm(text);setImported(true);setMessage('数据点已导入估算器。请继续填写原始与目标电流。')}}
  const messageClass=/无效|之外|错误/.test(message)?'error':calibrated(calibration)?'success':''

  return <details className="digitizer"><summary><span><b>从曲线截图半自动取点</b><small>先标定坐标轴，再点击曲线；图片只在浏览器本地处理</small></span><i aria-hidden="true">展开操作说明与工具⌄</i></summary><div className="digitizer-body">
    <section className="digitizer-guide" aria-labelledby="digitizer-guide-title"><div><span>HOW TO USE</span><h4 id="digitizer-guide-title">如何正确取点</h4><p>前三次点击都是坐标轴位置，不是曲线数据点。</p></div><ol><li className={mode==='origin'?'active':''}><b>O</b><span>点击左下角<br/><small>0mA / 0%交点</small></span></li><li className={mode==='xMax'?'active':''}><b>X</b><span>点击右下角<br/><small>X轴最大刻度 / 0%</small></span></li><li className={mode==='yMax'?'active':''}><b>Y</b><span>点击左上角<br/><small>0mA / Y轴最大刻度</small></span></li><li className={mode==='point'?'active':''}><b>●</b><span>点击黑色曲线<br/><small>建议采集5–12个点</small></span></li></ol></section>
    <div className="axis-ranges"><label>X轴最小值<input name="xMin" type="number" value={ranges.xMin} onChange={updateRange}/><span>mA</span></label><label>X轴最大值<input name="xMax" type="number" value={ranges.xMax} onChange={updateRange}/><span>mA</span></label><label>Y轴最小值<input name="yMin" type="number" value={ranges.yMin} onChange={updateRange}/><span>%</span></label><label>Y轴最大值<input name="yMax" type="number" value={ranges.yMax} onChange={updateRange}/><span>%</span></label></div>
    <label className="image-picker"><span>选择曲线截图（PNG/JPG/WebP）</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={loadImage}/></label>
    {image&&<><div className="digitizer-toolbar"><div><span>当前操作</span><strong>{STEP_TEXT[mode]}</strong></div><button type="button" onClick={reset}>重新标定坐标轴</button></div>{message&&<div className={`calibration-message ${messageClass}`} role="status">{message}</div>}<div className={`curve-canvas mode-${mode}`}><canvas ref={canvasRef} onClick={canvasClick} aria-label="曲线图片半自动取点画布" aria-describedby="curve-canvas-help"/></div><p id="curve-canvas-help" className="digitizer-help"><b>绿色O/X/Y</b>表示坐标轴标定点，<b>橙色数字</b>表示曲线数据点。软件会检查O–X是否水平、O–Y是否垂直，标定错误时不会进入取点阶段。</p>{points.length>0&&<div className="point-table"><div className="point-head"><b>已采集 {points.length} 个点</b><span>请与截图刻度核对，可直接修正</span></div>{points.map((point,index)=><div className="point-row" key={point.id}><span>{index+1}</span><label><input type="number" value={point.current.toFixed(2)} onChange={event=>updatePoint(point.id,'current',event.target.value)}/>mA</label><label><input type="number" value={point.flux.toFixed(2)} onChange={event=>updatePoint(point.id,'flux',event.target.value)}/>%</label><button type="button" onClick={()=>removePoint(point.id)}>删除</button></div>)}<button type="button" className="button primary import-points" disabled={points.length<2} onClick={confirm}>{imported?'✓ 已导入估算器':'确认并导入这些数据点'}</button></div>}</>}
  </div></details>
}
