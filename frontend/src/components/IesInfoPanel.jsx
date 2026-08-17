import PhotometricChart from './PhotometricChart.jsx'
import './IesInfoPanel.css'

const number=(value,digits=2)=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:digits})
const distributionLabels={rotational_symmetric:'旋转对称配光',approximately_symmetric:'近似对称配光',asymmetric:'非对称配光'}
const photometricTypes={1:'Type C',2:'Type B',3:'Type A'}
const unitTypes={1:'英尺（ft）',2:'米（m）'}
const tiltLabels={NONE:'无倾斜修正',INCLUDE:'文件内含修正数据'}
const closestBeam=(beams,target)=>beams.length?beams.reduce((best,item)=>Math.abs(item.positive_c_angle-target)<Math.abs(best.positive_c_angle-target)?item:best,beams[0]):null

export default function IesInfoPanel({upload}){
  if(!upload)return null
  const info={file_name:upload.file_name,...upload.parsed_info}
  const photometry=upload.photometry||{}
  const totalFlux=info.suggested_source_luminous_flux_lm
  const efficacy=totalFlux&&info.input_watts?totalFlux/info.input_watts:null
  const beams=photometry.beam_angles_50||[]
  const beam0=closestBeam(beams,0)
  const beam90=closestBeam(beams,90)
  const beamText=beam0?`${number(beam0.beam_angle_50,1)}°${beam90&&beam90!==beam0?` × ${number(beam90.beam_angle_50,1)}°`:''}`:'无法计算'
  const beamPlanes=beam0?`${beam0.label}${beam90&&beam90!==beam0?` / ${beam90.label}`:''}`:'缺少有效交点'
  const peak=photometry.peak_direction
  const dimensionUnit=info.units_type===2?' m':' ft'
  const metadata=Object.entries(info.keywords||{}).filter(([,value])=>value).slice(0,8)
  const rawFields=[
    ['原始文件',info.file_name],['IES 标准版本',info.ies_version],['倾斜修正',tiltLabels[info.tilt_type]||info.tilt_type],
    ['光度类型',photometricTypes[info.photometric_type]||`Type ${info.photometric_type}`],['灯数量',info.number_of_lamps],
    ['每灯光通量',`${number(info.lumens_per_lamp)} lm`],['光强数据倍率',`${number(info.candela_multiplier,4)}×`],
    ['垂直角采样',`${info.num_vertical_angles} 点 · ${number(photometry.vertical_range?.[0],1)}°–${number(photometry.vertical_range?.[1],1)}°`],
    ['水平 C 平面',`${info.num_horizontal_angles} 个 · C${number(photometry.horizontal_range?.[0],1)}°–C${number(photometry.horizontal_range?.[1],1)}°`],
    ['最小垂直间隔',photometry.minimum_vertical_step==null?'—':`${number(photometry.minimum_vertical_step,2)}°`],
    ['尺寸单位',unitTypes[info.units_type]||info.units_type],['灯具尺寸',`${number(info.length,3)} × ${number(info.width,3)} × ${number(info.height,3)}${dimensionUnit}`],
    ['Ballast Factor',number(info.ballast_factor,4)],['Ballast-Lamp Factor',number(info.ballast_lamp_photometric_factor,4)],
  ]

  return <section className="card step-card appear">
    <div className="step-number complete">✓</div>
    <div className="card-content ies-analysis">
      <div className="layer-heading summary-heading"><div><p className="eyebrow">01 / CORE SUMMARY</p><h2>IES 光度摘要</h2><p>第一层 · 影响选型与判断的核心结果</p></div><span className={`status-pill ${info.supports_auto_conversion?'success':'warning'}`}>{info.supports_auto_conversion?'可自动带入光通量':'需手动填写光通量'}</span></div>
      <div className="summary-grid">
        <article><span>输入功率</span><strong>{number(info.input_watts)}<small> W</small></strong></article>
        <article><span>灯具总光通量</span><strong>{number(totalFlux)}<small> lm</small></strong></article>
        <article><span>光效</span><strong>{number(efficacy)}<small> lm/W</small></strong></article>
        <article><span>最大光强</span><strong>{number(info.max_candela)}<small> cd</small></strong></article>
        <article><span>最大光强方向</span><strong className="direction">{peak?`C${number(peak.c_angle,1)}° / γ${number(peak.gamma_angle,1)}°`:'—'}</strong></article>
      </div>
      <div className="key-conclusions">
        <article><div><span>50%光强光束角</span><small>按各平面峰值光强的50%定义</small></div><div className="conclusion-value"><strong>{beamText}</strong><small>{beamPlanes}</small></div></article>
        <article><div><span>配光类型</span><small>根据不同 C 平面的光强差异判断</small></div><strong className="distribution-badge">{distributionLabels[photometry.distribution_type]||'—'}</strong></article>
      </div>
      {info.is_absolute_photometry&&<div className="notice warning">这是绝对光度文件，IES 中没有可直接使用的总光通量，请填写实测总光通量。</div>}
      <PhotometricChart photometry={photometry}/>
      <details className="raw-details">
        <summary><span className="raw-title"><em>03 / RAW PARAMETERS</em><b>IES 原始技术参数</b><small>第三层 · 版本、TILT、采样范围、倍率与灯具尺寸</small></span><span className="expand-prompt"><b>点击展开查看 {rawFields.length} 项参数</b><i aria-hidden="true">⌄</i></span></summary>
        <dl className="raw-grid">{rawFields.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value??'—'}</dd></div>)}</dl>
        {metadata.length>0&&<div className="metadata"><h3>文件标签</h3><dl>{metadata.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></div>}
      </details>
    </div>
  </section>
}
