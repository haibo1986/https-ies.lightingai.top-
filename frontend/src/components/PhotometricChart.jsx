import './PhotometricChart.css'
import './PhotometricAxes.css'

const SIZE=520, CENTER=260, RADIUS=205
const polarPoint=(angle,value,max)=>{const rad=angle*Math.PI/180,r=max?value/max*RADIUS:0;return [CENTER+r*Math.sin(rad),CENTER-r*Math.cos(rad)]}
const segment=(angles,values,max,mirror=false)=>angles.map((angle,index)=>{const[x,y]=polarPoint(mirror?-angle:angle,values[index],max);return `${index?'L':'M'}${x.toFixed(2)} ${y.toFixed(2)}`}).join(' ')
const closestAxis=(axes,target)=>axes.reduce((best,axis)=>Math.abs(axis.positive_c_angle-target)<Math.abs(best.positive_c_angle-target)?axis:best,axes[0])
const format=value=>value==null?'—':`${Number(value).toFixed(1)}°`

export default function PhotometricChart({photometry}){
  const planes=photometry?.planes||[]
  const allAxes=photometry?.beam_angles_50||[]
  if(!planes.length||!allAxes.length)return null
  const principalAxes=[closestAxis(allAxes,0),closestAxis(allAxes,90)].filter((axis,index,list)=>list.findIndex(item=>item.positive_c_angle===axis.positive_c_angle)===index)
  const planeAt=angle=>planes.find(plane=>plane.c_angle===angle)||planes[0]
  const max=Math.max(...planes.flatMap(plane=>plane.candela),1)
  const axisData=principalAxes.map((axis,index)=>({axis,index,positive:planeAt(axis.positive_c_angle),negative:planeAt(axis.negative_data_c_angle??axis.negative_c_angle)}))
  const completePath=({positive,negative})=>`${segment([...photometry.vertical_angles].reverse(),[...negative.candela].reverse(),max,true)} ${segment(photometry.vertical_angles,positive.candela,max).replace(/^M/,'L')}`
  const markers=[]
  axisData.forEach(({positive,negative,index})=>{
    ;[[positive,false],[negative,true]].forEach(([plane,mirror])=>{
      ;[['crossing_angle','threshold','50'],['crossing_angle_10','threshold_10','10']].forEach(([angleKey,valueKey,level])=>{
        if(plane[angleKey]==null)return
        const[x,y]=polarPoint(mirror?-plane[angleKey]:plane[angleKey],plane[valueKey],max)
        markers.push(<circle key={`${index}-${mirror}-${level}`} className={`threshold-marker axis-${index} level-${level}`} cx={x} cy={y} r={level==='50'?5:4}/>)
      })
    })
  })

  return <section className="photometry" aria-labelledby="photometry-title">
    <div className="layer-heading"><div><p className="eyebrow">02 / DISTRIBUTION ANALYSIS</p><h2 id="photometry-title">光强分布曲线</h2><p>第二层 · 对比主要平面的光束宽度、方向与10%/50%光强边界</p></div></div>
    <div className="photometry-layout">
      <div className="polar-column"><svg className="polar-chart" viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="C0–C180平面与C90–C270平面叠加光强分布曲线">
        <g className="chart-grid">{[.25,.5,.75,1].map(r=><circle key={r} cx={CENTER} cy={CENTER} r={RADIUS*r}/>)}<line x1={CENTER} y1="45" x2={CENTER} y2="475"/><line x1="45" y1={CENTER} x2="475" y2={CENTER}/>{[-60,-30,30,60].map(angle=>{const[x,y]=polarPoint(angle,max,max);return <line key={angle} x1={CENTER} y1={CENTER} x2={x} y2={y}/>})}</g>
        {axisData.map((item,index)=><path key={item.axis.label} className={`curve axis-${index}`} d={completePath(item)}/>)}{markers}
        <text x="260" y="25" textAnchor="middle">0°</text><text x="25" y="266" textAnchor="middle">−90°</text><text x="495" y="266" textAnchor="middle">+90°</text>
      </svg><div className="curve-legend">{axisData.map((item,index)=><span key={item.axis.label}><i className={`axis-swatch axis-${index}`} aria-hidden="true"/>{item.axis.label}</span>)}<span><i className="dot fifty" aria-hidden="true"/>50%交点</span><span><i className="dot ten" aria-hidden="true"/>10%交点</span></div></div>
      <div className="angle-analysis"><p className="analysis-kicker">ANGLE ANALYSIS</p>{axisData.map(({axis},index)=><article key={axis.label} className={`axis-card axis-${index}`}><h3>{axis.label}</h3><dl><div><dt>50%光强光束角</dt><dd>{format(axis.beam_angle_50)}</dd></div><div><dt>10%光强角（光场角）</dt><dd>{format(axis.field_angle_10)}</dd></div></dl></article>)}<p className="method-note">角度以各平面峰值光强为基准，测量点之间采用线性插值。</p></div>
    </div>
    {allAxes.length>principalAxes.length&&<details className="all-planes"><summary>查看其他 {allAxes.length-principalAxes.length} 个 C 平面角度</summary><div>{allAxes.filter(axis=>!principalAxes.includes(axis)).map(axis=><span key={axis.label}><b>{axis.label}</b><i>50% {format(axis.beam_angle_50)}</i><i>10% {format(axis.field_angle_10)}</i></span>)}</div></details>}
  </section>
}
