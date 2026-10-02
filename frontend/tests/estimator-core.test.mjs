import { test } from 'node:test'
import assert from 'node:assert/strict'
import { computeEstimate, parseCurve, interpolate, rangeFor } from '../src/estimator-core.js'

// 添鑫3535 曲线（相对值，300mA=100）
const points = [[50,16.5],[75,25.3],[100,33.9],[125,41.2],[150,50.4],[175,57.9],[200,67.1],[225,75.7],[250,82.2],[275,92.0],[300,100.0],[325,108.6],[350,117.0],[375,125.5],[395,133.4]].map(([current,flux])=>({current,flux}))
const baseValues = {source_current:'300',target_current:'350',source_count:'7',target_count:'10',reference_current:'300',reference_flux:'218',thermal:'same',optical:'unchanged',source_transmission:'100',target_transmission:'100',source_duty:'100',target_duty:'',target_efficacy:'',source_length_mm:'',source_modules:'',target_modules:''}
const mainDims = {length:300,width:50}
const est = (values, sourceFlux='', autoSource=null) => computeEstimate({scenario:'combined',values:{...baseValues,...values},points,sourceFlux,targetPower:'21',sourceLengthDefault:300,mainDims,autoSource})

test('绝对路径基准：300→350mA、7→10颗 = 目标 2550.6 / 原始 1526',()=>{
  const r=est({})
  assert.equal(Math.round(r.result),2551)
  assert.equal(r.sourceFluxAbs,1526)
  assert.equal(r.changeType,'led_count_change')
  assert.equal(r.error,'')
})

test('绝对路径：目标参数变化时目标光通量实时变化',()=>{
  assert.equal(Math.round(est({target_current:'395'}).result),2908)   // 117→133.4
  assert.equal(Math.round(est({target_count:'12'}).result),3061)
  assert.equal(Math.round(est({reference_flux:'240'}).result),2808)   // 218→240 基准
  assert.notEqual(Math.round(est({reference_current:'350'}).result),2551) // 基准点电流变化
})

test('绝对路径：原始参数变化只影响原始光通量估算（目标不变，两者都有可见反馈）',()=>{
  const base=est({})
  const a=est({source_current:'350'}) // 100→117
  assert.equal(Math.round(a.result),Math.round(base.result))
  assert.equal(a.sourceFluxAbs,1785)  // 117/100*218*7=1785.4
  const b=est({source_count:'8'})
  assert.equal(Math.round(b.result),Math.round(base.result))
  assert.equal(b.sourceFluxAbs,1744)  // 100/100*218*8=1744
})

test('比例路径（有原始光通量 1526）：六个参数全部实时参与或按规则不参与',()=>{
  const base=est({},'1526')
  assert.equal(Math.round(base.result),2551) // 1526*1.17*10/7=2550.6
  assert.notEqual(Math.round(est({target_current:'395'},'1526').result),2551)
  assert.notEqual(Math.round(est({source_current:'350'},'1526').result),2551)
  assert.notEqual(Math.round(est({target_count:'12'},'1526').result),2551)
  assert.notEqual(Math.round(est({source_count:'8'},'1526').result),2551)
  // 基准点不参与比例路径（数学正确，界面有说明文字）
  assert.equal(Math.round(est({reference_flux:'240'},'1526').result),2551)
  assert.equal(Math.round(est({reference_current:'350'},'1526').result),2551)
})

test('模式粘性：自动回填的原始光通量不会引起路径翻转；用户手改后才切回比例路径',()=>{
  const first=est({})
  // 表单被同步填入 1526 后（autoSource=1526），仍按绝对路径计算，双值都显示
  const sticky=est({},'1526',1526)
  assert.equal(Math.round(sticky.result),Math.round(first.result))
  assert.equal(sticky.sourceFluxAbs,1526)
  // 用户手动改成 1600 → 回到比例路径
  const manual=est({},'1600',1526)
  assert.equal(manual.sourceFluxAbs,null)
  assert.equal(Math.round(manual.result),Math.round(1600*117/100*10/7))
})

test('无原始光通量且无基准点 → 明确引导错误',()=>{
  const r=est({reference_current:'',reference_flux:''})
  assert.equal(r.result,null)
  assert.match(r.error,/基准光通量/)
})

test('「调整LED电流」场景无原始光通量 → 引导改用颗数和电流都变',()=>{
  const r=computeEstimate({scenario:'current',values:baseValues,points,sourceFlux:'',targetPower:'21',sourceLengthDefault:300,mainDims,autoSource:null})
  assert.equal(r.result,null)
  assert.match(r.error,/颗数和电流都变/)
})

test('颗数/模组/PWM 场景缺少原始光通量 → 引导先填原始光通量',()=>{
  for(const scenario of ['count','module','pwm']){
    const r=computeEstimate({scenario,values:baseValues,points,sourceFlux:'',targetPower:'21',sourceLengthDefault:300,mainDims,autoSource:null})
    assert.equal(r.result,null)
    assert.match(r.error,/原始实测总光通量/)
  }
})

test('光学结构变化 → 阻止估算',()=>{
  const r=est({optical:'changed'})
  assert.equal(r.result,null)
  assert.match(r.error,/重新实测/)
})

test('电流超出曲线范围 → 不自动外推并提示范围',()=>{
  const r=est({source_current:'500'})
  assert.equal(r.result,null)
  assert.match(r.error,/50–395/)
})

test('parseCurve / interpolate / rangeFor 基础行为',()=>{
  const parsed=parseCurve('100,33\n300,88\n300,90\n700,170')
  assert.equal(parsed.length,3) // 重复电流去重（保留首个）
  assert.equal(parsed[1].flux,88)
  assert.equal(interpolate(parsed,200),60.5)
  assert.equal(interpolate(parsed,50),null)
  assert.deepEqual(rangeFor(1000,'medium'),[900,1100])
})
