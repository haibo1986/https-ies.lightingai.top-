from __future__ import annotations

import base64
import math
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .photometric_engine import PhotometricEngine, contour_segments
from .standard_report import H, W, INK, LINE, MUTED, _font, _text


RED = colors.HexColor("#e11b22")
BLUE = colors.HexColor("#1547ff")
GREEN = colors.HexColor("#147a51")
TOTAL_PAGES = 13


def _engine(ph: dict[str, Any]) -> PhotometricEngine:
    return PhotometricEngine(ph["vertical_angles"],[p["c_angle"] for p in ph["planes"]],[p["candela"] for p in ph["planes"]])


def _profiles(ph: dict[str, Any], normalized=False):
    engine=_engine(ph); factor=1000/ph["target_flux_lm"] if normalized else 1
    return [[(a,v*factor) for a,v in engine.axis_profile(0,180)],[(a,v*factor) for a,v in engine.axis_profile(90,270)]]


def _nice_max(value: float) -> float:
    if value <= 0: return 1
    magnitude=10**math.floor(math.log10(value)); return math.ceil(value/magnitude*1.2)*magnitude


def _draw_polar_reference(c: canvas.Canvas, ph: dict[str, Any], cx: float, cy: float, radius: float, normalized=False) -> None:
    profiles=_profiles(ph,normalized); maximum=_nice_max(max(v for profile in profiles for _,v in profile))
    c.setLineWidth(.45); c.setStrokeColor(INK)
    for ratio in (.2,.4,.6,.8,1):
        c.circle(cx,cy,radius*ratio,fill=0,stroke=1); _text(c,cx,cy-radius*ratio+1,f"{maximum*ratio:.0f}",5.4,MUTED,"center")
    # Reference convention: gamma 0 degrees points down and +/-180 points up.
    for angle in range(-180,181,15):
        rad=math.radians(angle); c.line(cx,cy,cx+radius*math.sin(rad),cy-radius*math.cos(rad))
        if angle < 180:
            _text(c,cx+(radius+4.2*mm)*math.sin(rad),cy-(radius+4.2*mm)*math.cos(rad),str(angle),5.2,INK,"center")
    for profile,color in zip(profiles,(RED,BLUE)):
        path=c.beginPath()
        for index,(angle,value) in enumerate(profile):
            rad=math.radians(angle); r=value/maximum*radius; x,y=cx+r*math.sin(rad),cy-r*math.cos(rad)
            path.moveTo(x,y) if index==0 else path.lineTo(x,y)
        c.setStrokeColor(color);c.setLineWidth(1.35);c.drawPath(path,fill=0,stroke=1)
    _text(c,cx-radius,cy-radius-13*mm,"C0-C180",6.3,RED);_text(c,cx-35*mm,cy-radius-13*mm,"C90-C270",6.3,BLUE)
    _text(c,cx+radius,cy-radius-13*mm,"Unit: cd/klm" if normalized else "Unit: cd",6.3,INK,"right")


def _draw_cart_reference(c: canvas.Canvas, ph: dict[str, Any], x: float, y: float, width: float, height: float) -> None:
    profiles=_profiles(ph); maximum=_nice_max(max(v for profile in profiles for _,v in profile))
    c.setLineWidth(.45);c.setStrokeColor(INK);c.rect(x,y,width,height,fill=0,stroke=1)
    for angle in range(-180,181,60):
        px=x+(angle+180)/360*width;c.line(px,y,px,y+height);_text(c,px,y-5*mm,str(angle),5.6,INK,"center")
    for i in range(1,6):
        py=y+i/5*height;c.line(x,py,x+width,py);_text(c,x-2*mm,py,f"{maximum*i/5:.0f}",5.4,INK,"right")
    for profile,color in zip(profiles,(RED,BLUE)):
        path=c.beginPath()
        for index,(angle,value) in enumerate(profile):
            px=x+(angle+180)/360*width;py=y+value/maximum*height
            path.moveTo(px,py) if index==0 else path.lineTo(px,py)
        c.setStrokeColor(color);c.setLineWidth(1.35);c.drawPath(path,fill=0,stroke=1)
    _text(c,x,y-11*mm,"C0-C180",6.3,RED);_text(c,x+35*mm,y-11*mm,"C90-C270",6.3,BLUE);_text(c,x+width,y-11*mm,"Unit: cd",6.3,INK,"right")
    _text(c,x+width/2,y-5*mm,"Gamma angle [deg]",5.5,MUTED,"center")
    _text(c,x-10*mm,y+height/2,"I [cd]",5.5,MUTED,"center")


def _logo(c: canvas.Canvas, data: dict[str, Any]) -> None:
    raw = data.get("company_logo_data_url", "")
    if raw.startswith("data:image/") and "," in raw:
        try:
            image = ImageReader(BytesIO(base64.b64decode(raw.split(",", 1)[1])))
            c.drawImage(image, 17 * mm, H - 27 * mm, width=42 * mm, height=13 * mm, preserveAspectRatio=True, anchor="sw", mask="auto")
            return
        except Exception:
            pass
    c.setStrokeColor(GREEN); c.setLineWidth(1.2); c.rect(17 * mm, H - 27 * mm, 38 * mm, 13 * mm, fill=0, stroke=1)
    _text(c, 36 * mm, H - 23 * mm, data["company"], 10, GREEN, "center")


def _header(c: canvas.Canvas, data: dict[str, Any], page: int, title: str) -> None:
    _logo(c, data)
    _text(c, 61 * mm, H - 18 * mm, data["company"], 8.5)
    _text(c, 61 * mm, H - 23 * mm, data.get("company_website") or "", 6.5, MUTED)
    _text(c, 61 * mm, H - 27 * mm, data.get("company_phone") or "", 6.5, MUTED)
    _text(c, W - 17 * mm, H - 22 * mm, f"第 {page} 页  共 {TOTAL_PAGES} 页", 8, INK, "right")
    c.setStrokeColor(INK); c.setLineWidth(.45); c.line(17 * mm, H - 31 * mm, W - 17 * mm, H - 31 * mm)
    _text(c, 17 * mm, H - 36 * mm, f"报告编号：{data['report_number']}", 7.2)
    _text(c, W - 17 * mm, H - 36 * mm, f"生成时间：{data['generated_on']}", 7.2, INK, "right")
    _text(c, W / 2, H - 53 * mm, title, 15, INK, "center")


def _footer(c: canvas.Canvas, data: dict[str, Any]) -> None:
    ph = data["photometric"]
    c.setStrokeColor(INK); c.line(17 * mm, 35 * mm, W - 17 * mm, 35 * mm)
    left = [("C角度范围", f"{ph['horizontal_range'][0]:g} - {ph['horizontal_range'][1]:g} Deg"),("C角度间隔", f"{_step([p['c_angle'] for p in ph['planes']])} Deg"),("数据类型", "ESTIMATED"),("数据来源", "目标估算 IES")]
    right = [("G角度范围", f"{ph['vertical_range'][0]:g} - {ph['vertical_range'][1]:g} Deg"),("G角度间隔", f"{ph['minimum_vertical_step']} Deg"),("生成系统", "IES Photometric Tool"),("备注", "非重新实测")]
    for index, (label, value) in enumerate(left): _text(c, 17 * mm, (29 - index * 5) * mm, f"{label}：{value}", 6.6)
    for index, (label, value) in enumerate(right): _text(c, 108 * mm, (29 - index * 5) * mm, f"{label}：{value}", 6.6)


def _step(values: list[float]) -> str:
    gaps = [b-a for a,b in zip(values, values[1:]) if b>a]
    return f"{min(gaps):g}" if gaps else "0"


def _finish(c: canvas.Canvas, data: dict[str, Any]) -> None:
    _footer(c, data); c.showPage()


def _summary_block(c: canvas.Canvas, x: float, y: float, title: str, rows: list[tuple[str, str]], width: float) -> None:
    _text(c, x, y, title, 10)
    c.setStrokeColor(INK); c.line(x, y - 2 * mm, x + width, y - 2 * mm)
    for i, (label, value) in enumerate(rows):
        _text(c, x, y - (8 + i * 6) * mm, f"{label}：{value}", 7.3)


def _draw_planar_iso(c: canvas.Canvas, data: dict[str, Any], spatial=False) -> None:
    ph, calc = data["photometric"], data["calculation"]
    engine=_engine(ph)
    x, y, size = 43 * mm, 72 * mm, 125 * mm
    c.setStrokeColor(INK); c.rect(x, y, size, size, fill=0, stroke=1)
    height,extent=calc["height_m"],calc["plane_extent_m"]
    if spatial:
        xs=[30*i/80 for i in range(81)];ys=[.25+(30-.25)*i/80 for i in range(81)]
        grid=[[engine.spatial_illuminance(px,depth,0) for px in xs] for depth in ys]
    else:
        xs,ys,grid=engine.grid(extent,81,lambda px,py:engine.horizontal_illuminance(px,py,height))
    maximum=max(max(row) for row in grid)
    palette = [colors.HexColor(v) for v in ("#e11b22","#ff6d00","#d6a400","#2d9f48","#00a4a6","#1677ff","#7048c8","#bd34d1","#995c30","#333333")]
    if spatial:
        reference=max(engine.spatial_illuminance(0,10,0),1e-9)
        levels=[reference*f/10 for f in range(10,0,-1)]
    else:
        reference=maximum
        levels=[maximum*f/10 for f in range(10,0,-1)]
    for i in range(11):
        c.setStrokeColor(colors.HexColor("#b8b8b8")); c.setLineWidth(.35)
        c.line(x+i*size/10,y,x+i*size/10,y+size); c.line(x,y+i*size/10,x+size,y+i*size/10)
        if spatial:
            _text(c,x+i*size/10,y-4*mm,f"{i*3:g}",5.5,INK,"center")
            _text(c,x-2*mm,y+size-i*size/10,f"{i*3:g}",5.5,INK,"right")
        else:
            value=-extent+2*extent*i/10
            _text(c,x+i*size/10,y-4*mm,f"{value:g}",5.5,INK,"center")
            _text(c,x-2*mm,y+i*size/10,f"{value:g}",5.5,INK,"right")
    for i,level in enumerate(levels):
        c.setStrokeColor(palette[i]);c.setLineWidth(1.05)
        for first,second in contour_segments(xs,ys,grid,level):
            def map_point(point):
                px=x+(point[0]-xs[0])/(xs[-1]-xs[0])*size;py=y+(point[1]-ys[0])/(ys[-1]-ys[0])*size
                if spatial: py=y+size-(point[1]-ys[0])/(ys[-1]-ys[0])*size
                return px,py
            a,b=map_point(first),map_point(second);c.line(a[0],a[1],b[0],b[1])
        col=i%2; row=i//2; lx=(30+col*88)*mm;ly=(59-row*3.8)*mm
        _text(c,lx,ly,f"{level:.3f} ({(10-i)*10}% Emax)",5.5,palette[i])
    _text(c,x+size/2,y-9*mm,"Distance [m]",5.8,MUTED,"center")
    _text(c,x-13*mm,y+size/2,"Distance [m]",5.8,MUTED,"center")
    note=(f"Unit of illumination: lx   C0-C180 section   Depth: 0-30 m   Eref(10 m): {reference:.3f} lx" if spatial
          else f"Unit of illumination: lx   Height of plane: {height:g} m   Emax: {maximum:.3f} lx")
    _text(c,W/2,66*mm,note,6.4,MUTED,"center")


def _draw_luminance_limit(c: canvas.Canvas, data: dict[str, Any]) -> None:
    ph=data["photometric"];p=data["product"];engine=_engine(ph)
    area=max(.000001,p["luminous_length_mm"]*p["luminous_width_mm"]/1_000_000)
    angles=(45,50,55,60,65,70,75,80,85)
    columns=[27]+[49+i*16 for i in range(len(angles))]
    table_top=H-67*mm
    c.setStrokeColor(INK);c.setLineWidth(.45);c.rect(24*mm,H-120*mm,165*mm,56*mm,fill=0,stroke=1)
    for i,xv in enumerate(columns):
        _text(c,xv*mm,table_top,"C/G" if i==0 else str(angles[i-1]),6.1,INK,"center")
    rows=[]
    for c_angle in (0,90): rows.append((f"C{c_angle}",[f"{engine.luminance(c_angle,a,area):.0f}" for a in angles]))
    rows.extend([
        ("Dazzle Quality",["Illuminance","-","-","-","-","-","-","-","-"]),
        ("1.15 / A",["-","-","-","-","2000","1000","500","<=300","-"]),
        ("1.50 / B",["-","-","-","-","2000","1000","500","<=300","-"]),
        ("1.85 / C",["-","-","-","-","2000","1000","500","<=300","-"]),
        ("2.20 / D",["-","-","-","-","2000","1000","500","<=300","-"]),
        ("2.55 / E",["-","-","-","-","2000","1000","500","<=300","-"]),
    ])
    for r,(label,values) in enumerate(rows):
        yy=table_top-(r+1)*5.5*mm;_text(c,29.5*mm,yy,label,5.3,INK,"center")
        for i,value in enumerate(values):_text(c,(49+i*16)*mm,yy,value,5.3,INK,"center")
        c.setStrokeColor(LINE);c.line(24*mm,yy-1.5*mm,189*mm,yy-1.5*mm)

    chart_x,chart_y,chart_w,chart_h=33*mm,64*mm,150*mm,72*mm
    xmin,xmax=500,40000
    def px(value):return chart_x+(math.log10(max(xmin,value))-math.log10(xmin))/(math.log10(xmax)-math.log10(xmin))*chart_w
    def py(gamma):return chart_y+(gamma-45)/40*chart_h
    c.setStrokeColor(INK);c.rect(chart_x,chart_y,chart_w,chart_h,fill=0,stroke=1)
    for value in (500,700,1000,2000,3000,5000,7000,10000,20000,30000,40000):
        xx=px(value);c.setStrokeColor(LINE);c.line(xx,chart_y,xx,chart_y+chart_h)
        _text(c,xx,chart_y-4*mm,f"{value:g}",4.8,INK,"center")
    for gamma in angles:
        yy=py(gamma);c.setStrokeColor(LINE);c.line(chart_x,yy,chart_x+chart_w,yy)
        _text(c,chart_x-2*mm,yy,str(gamma),5.2,INK,"right")
    # Reference-report a-h evaluation grid. These are presentation guides;
    # the measured/estimated luminaire curves remain engine-derived.
    for i,(top_value,bottom_value) in enumerate(zip((600,700,850,1000,1200,1450,1750,2100),(5000,7000,9000,12000,16000,22000,30000,40000))):
        c.setStrokeColor(colors.HexColor("#d98b82"));c.setLineWidth(.65);c.line(px(bottom_value),py(45),px(top_value),py(85))
        _text(c,px(top_value),py(85)+2*mm,chr(97+i),5.2,RED,"center")
    for cg,color in ((0,RED),(90,BLUE)):
        path=c.beginPath()
        for i,gamma in enumerate(angles):
            point=(px(engine.luminance(cg,gamma,area)),py(gamma));path.moveTo(*point) if i==0 else path.lineTo(*point)
        c.setStrokeColor(color);c.setLineWidth(1.35);c.drawPath(path,fill=0,stroke=1)
    _text(c,chart_x+chart_w/2,chart_y-9*mm,"Luminance [cd/m2] - logarithmic scale",5.8,MUTED,"center")
    _text(c,chart_x-10*mm,chart_y+chart_h/2,"Gamma [deg]",5.8,MUTED,"center")
    _text(c,35*mm,55*mm,"C0-C180",6,RED);_text(c,66*mm,55*mm,"C90-C270",6,BLUE)
    _text(c,183*mm,55*mm,f"Projected luminous area model: {area:.4f} m2",5.8,MUTED,"right")


def generate_classic_pdf(data: dict[str, Any], output_path: str | Path) -> str:
    c=canvas.Canvas(str(output_path),pagesize=A4,pageCompression=1); c.setTitle(f"{data['product']['model']} 光度数据报告")
    p,e,ph=data["product"],data["electrical"],data["photometric"]

    # 1 Summary, with the former image area replaced by two large plots.
    _header(c,data,1,"灯具光度数据报告")
    _summary_block(c,17*mm,H-67*mm,"灯具属性",[("生产工厂",p["manufacturer"]),("灯具规格",p["model"]),("发光面长度",f"{p['luminous_length_mm']:.1f} mm"),("发光面宽度",f"{p['luminous_width_mm']:.1f} mm"),("相关色温",f"{p.get('cct_k') or '-'} K"),("显色指数",f"Ra {p.get('cri_ra') or '-'}")],82*mm)
    _summary_block(c,108*mm,H-67*mm,"电气参数",[("电压",f"{e.get('voltage_v') or '-'} V"),("电流",f"{e.get('current_a') or '-'} A"),("功率",f"{e['power_w']:.2f} W"),("功率因数",str(e.get('power_factor') or '-')),("光源光通量",f"{ph['target_flux_lm']:.2f} lm")],85*mm)
    _summary_block(c,17*mm,H-116*mm,"光度结果",[("灯具光通量",f"{ph['target_flux_lm']:.3f} lm"),("灯具光效",f"{ph['efficacy_lm_w']:.2f} lm/W"),("最大光强",f"{ph['max_candela_cd']:.2f} cd"),("最大光强角",f"C={ph['peak_direction']['c_angle']:g} Gamma={ph['peak_direction']['gamma_angle']:g}"),("中心光强",f"{ph['center_intensity']:.2f} cd"),("光束角",", ".join(str(b['beam_angle_50']) for b in ph['beam_angles_50'][:2])+" deg")],176*mm)
    _draw_polar_reference(c,ph,63*mm,78*mm,31*mm); _draw_cart_reference(c,ph,111*mm,55*mm,78*mm,49*mm)
    _text(c,63*mm,38*mm,"极坐标配光曲线",7,MUTED,"center"); _text(c,150*mm,38*mm,"直角坐标配光曲线",7,MUTED,"center"); _finish(c,data)

    # 2 Combined intensity curves.
    _header(c,data,2,"光强分布曲线"); _draw_polar_reference(c,ph,W/2,H-118*mm,50*mm); _draw_cart_reference(c,ph,38*mm,62*mm,135*mm,52*mm); _finish(c,data)
    # 3 Normalized cd/klm.
    _header(c,data,3,"归一化光强分布曲线"); _draw_polar_reference(c,ph,W/2,H-143*mm,68*mm,normalized=True); _finish(c,data)
    # 4 Planar isolux.
    _header(c,data,4,"平面等照度曲线"); _draw_planar_iso(c,data); _finish(c,data)

    # 5 Luminance limitation.
    _header(c,data,5,"亮度限制曲线"); _draw_luminance_limit(c,data); _finish(c,data)

    # 6 Distance cone.
    _header(c,data,6,"照度距离曲线");engine=_engine(ph);x0,y0=W/2,53*mm;top=H-70*mm
    beam=min((b for b in ph["beam_angles_50"] if b.get("beam_angle_50")),key=lambda b:abs(b["positive_c_angle"]),default=None)
    beam_angle=beam["beam_angle_50"] if beam else 0
    center=engine.intensity(0,0);peak=ph["max_candela_cd"]
    c.setStrokeColor(INK);c.line(x0,top,x0-40*mm,y0);c.line(x0,top,x0+40*mm,y0)
    for i,height_m in enumerate(range(1,11)):
        yy=top-(i+1)*(top-y0)/10;width=(top-yy)/max(1,top-y0)*40*mm
        center_lux=center/height_m**2;max_lux=peak/height_m**2;diameter=2*height_m*math.tan(math.radians(beam_angle/2)) if beam_angle else 0
        c.setFillColor(colors.yellow);c.setStrokeColor(INK);c.ellipse(x0-width*.72,yy-1.8*mm,x0+width*.72,yy+1.8*mm,fill=1,stroke=1)
        _text(c,17*mm,yy+1.5*mm,f"{height_m*3.28084:.2f} ft",5.4)
        _text(c,43*mm,yy+1.5*mm,f"{center_lux*.092903:.2f}, {max_lux*.092903:.2f} fc",5.4)
        _text(c,17*mm,yy-2.4*mm,f"{height_m:.2f} m",5.4)
        _text(c,43*mm,yy-2.4*mm,f"{center_lux:.2f}, {max_lux:.2f} lx",5.4)
        _text(c,170*mm,yy+1.5*mm,f"{diameter*3.28084:.2f} ft",5.4,INK,"right")
        _text(c,191*mm,yy-2.4*mm,f"{diameter:.2f} m",5.4,INK,"right")
    _text(c,17*mm,43*mm,"Height",6.2,MUTED);_text(c,43*mm,43*mm,"Ecenter, Emax",6.2,MUTED)
    _text(c,W/2,43*mm,f"Beam angle: {beam_angle:.1f} deg (C0-C180)",6.2,MUTED,"center");_text(c,191*mm,43*mm,"Diameter",6.2,MUTED,"right")
    _finish(c,data)
    # 7 Spatial isolux.
    _header(c,data,7,"空间等照度曲线"); _draw_planar_iso(c,data,spatial=True); _finish(c,data)

    # 8 Zonal lumen table.
    _header(c,data,8,"区域光通量表"); headers=("Gamma [deg]","Imean [cd]","Zonal Flux [lm]","Sum Flux [lm]","Zonal Flux [%]","Sum Flux [%]")
    positions=(22,53,85,118,151,184)
    for x,h in zip(positions,headers): _text(c,x*mm,H-68*mm,h,5.8,INK,"center")
    total=ph["integrated_downward_flux_lm"]
    for r,z in enumerate(ph["zonal_flux"]):
        y=H-(77+r*8.3)*mm; vals=(f"{z['gamma_angle']:.0f}",f"{z['mean_intensity_cd']:.2f}",f"{z['flux_lm']:.2f}",f"{z['cumulative_lm']:.2f}",f"{z['percent']:.2f}",f"{z['cumulative_lm']/total*100:.2f}")
        for x,v in zip(positions,vals): _text(c,x*mm,y,v,5.8,INK,"center")
        c.setStrokeColor(LINE); c.line(17*mm,y-2.2*mm,W-17*mm,y-2.2*mm)
    _finish(c,data)

    # 9 Numeric quality audit; no invented utilization coefficients.
    _header(c,data,9,"光度数据质量与计算校验")
    engine=_engine(ph);integrated=engine.integrated_flux();declared=ph["target_flux_lm"];error=abs(integrated-declared)/declared*100
    audits=[("IES声明光通量",f"{declared:.3f} lm"),("独立球面积分光通量",f"{integrated:.3f} lm"),("积分相对误差",f"{error:.3f}%"),("IES最大光强",f"{ph['max_candela_cd']:.3f} cd"),("插值引擎最大采样值",f"{max(engine.intensity(cg,g) for cg in range(360) for g in range(91)):.3f} cd"),("C0/G0采样核对",f"{engine.intensity(0,0):.3f} cd"),("C180/G0采样核对",f"{engine.intensity(180,0):.3f} cd"),("C90/G45采样核对",f"{engine.intensity(90,45):.3f} cd"),("发光面面积",f"{p['luminous_length_mm']*p['luminous_width_mm']/1_000_000:.6f} m²"),("结论","通过" if error<=1 else "需复核")]
    for i,(label,value) in enumerate(audits):
        yy=H-(75+i*13)*mm;_text(c,28*mm,yy,label,7,MUTED);_text(c,102*mm,yy,value,8);c.setStrokeColor(LINE);c.line(25*mm,yy-3*mm,W-25*mm,yy-3*mm)
    _text(c,25*mm,64*mm,"本页所有结果由统一插值引擎独立计算；报告不再输出未经标准验证的利用系数。",7,GREEN);_finish(c,data)

    # 10-12 Full C-Gamma matrix, 31 vertical angles per page.
    angles=ph["vertical_angles"]; planes=ph["planes"]
    chunks=[list(range(i,min(i+31,len(angles)))) for i in range(0,len(angles),31)]
    while len(chunks)<3: chunks.append([])
    for page,indices in enumerate(chunks[:3],start=10):
        _header(c,data,page,"C-Gamma 完整光强数据表")
        table_x=17*mm; col=(W-34*mm)/(len(planes)+1); y=H-68*mm
        _text(c,table_x,y,"G/C",5.5)
        for j,plane in enumerate(planes): _text(c,table_x+(j+1)*col,y,f"C{plane['c_angle']:g}",5.3,INK,"right")
        for r,i in enumerate(indices):
            yy=y-(r+1)*6.05*mm; _text(c,table_x,yy,f"G{angles[i]:g}",5.2)
            for j,plane in enumerate(planes): _text(c,table_x+(j+1)*col,yy,f"{plane['candela'][i]:.1f}",4.8,INK,"right")
            if r%2==0: c.setStrokeColor(colors.HexColor("#eeeeee"));c.line(table_x,yy-1.5*mm,W-17*mm,yy-1.5*mm)
        _text(c,W-17*mm,43*mm,"Unit: cd",6,MUTED,"right"); _finish(c,data)

    # 13 Traceability and statement.
    _header(c,data,13,"换算依据与使用声明")
    rows=[("原始 IES",data['conversion']['source_file']),("目标型号",p['model']),("原始实测光通量",f"{ph['source_flux_lm']:.3f} lm"),("目标估算光通量",f"{ph['target_flux_lm']:.3f} lm"),("光强缩放倍率",f"{data['conversion']['scale_factor']:.6f}"),("发光面尺寸",f"{p['luminous_length_mm']:.1f} × {p['luminous_width_mm']:.1f} mm"),("风险等级",data['conversion']['risk_level'])]
    for i,(label,value) in enumerate(rows):
        y=H-(75+i*12)*mm;_text(c,25*mm,y,label,7,MUTED);_text(c,78*mm,y,value,7.5);c.setStrokeColor(LINE);c.line(22*mm,y-3*mm,W-22*mm,y-3*mm)
    _text(c,22*mm,98*mm,"工程限制",10)
    for i,line in enumerate((data['conversion']['risk_message'],"本报告假设配光形状不变，仅按目标光通量同比缩放绝对光强。","透镜、光学结构、安装方式或 LED 排布变化时，应重新进行光度实测。","正式认证、招投标和验收不得使用本报告替代实验室报告。")): _text(c,27*mm,(86-i*10)*mm,f"• {line}",7.5)
    _text(c,22*mm,42*mm,data['disclaimer'],8,GREEN); _finish(c,data)
    c.save(); return str(output_path)
