"""v4 서사형 다이어그램의 결정론적 RGBA 렌더러."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
from math import cos, sin, tau
from random import Random
from PIL import Image, ImageDraw
from .channel_typography import draw_display_text

INK=(7,26,58,255); CREAM=(255,244,214,255); YELLOW=(246,190,40,255); RED=(201,75,60,255); CHALK=(245,240,224,255); SKY=(84,191,255,255)

@dataclass(frozen=True)
class DiagramItem:
    label: str
    value: str | None = None
    state: str | None = None
    emphasis: bool = False

@dataclass(frozen=True)
class DiagramSpec:
    kind: str
    title: str
    items: list[DiagramItem] = field(default_factory=list)
    meaning_line: str = ""
    stamp: str | None = None
    seed: str = "0"
    # DIEGETIC_WARP가 쿼드의 실제 픽셀 크기에서 파생한 가독성 보정값이다.
    support_font_scale: float = 1.0
    support_stroke_scale: float = 1.0

def _text(image, xy, text, px, fill=INK, *, spec=None, readable=True):
    # 공용 타이포그래피의 최소 크기와 이중 외곽선을 그대로 사용한다.
    font_scale = max(1.0, px / 30)
    if readable and spec is not None:
        font_scale *= max(1.0, float(spec.support_font_scale))
    stroke_scale = max(1.0, float(getattr(spec, "support_stroke_scale", 1.0))) if readable else 1.0
    draw_display_text(image, xy, str(text), role="support", fill=fill, align="center", scale=font_scale, stroke_scale=stroke_scale)
def _rng(seed): return Random(int.from_bytes(sha256(seed.encode()).digest()[:4], "big"))
def _line(draw, a, b, fill, width=4): draw.line((a,b), fill=fill, width=width)

def _stage(spec, size):
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); _text(im,(w//2,int(h*.08)),spec.title,h//10,spec=spec,readable=False)
    # 원근 워프와 6% 보드 inset이 겹쳐도 외곽 셀·라벨이 잘리지 않도록
    # 논리 캔버스 좌우에 10% 안전 마진을 둔다.
    side_margin = .10
    usable_width = w * (1 - 2 * side_margin)
    for i,item in enumerate(spec.items[:4]):
        # 두 행의 라벨 외곽선이 다음 행의 아치와 충돌하지 않도록
        # 상단 .30, 행간 .36을 사용한다. 모두 캔버스 높이 안에서
        # 계산되므로 아이템 수가 3개에서 4개로 늘어도 같은 계약을 지킨다.
        cx=int(w * side_margin + usable_width * ((i%2)*.5+.25)); cy=int(h*((i//2)*.36+.30)); r=min(w,h)//11
        d.arc((cx-r,cy-r*1.45,cx+r,cy+r*.1),180,360,fill=INK,width=max(3,r//6))
        d.rounded_rectangle((cx-r,cy,cx+r,cy+r*2),radius=r//5,fill=YELLOW if item.emphasis else CREAM,outline=INK,width=max(3,r//7))
        d.ellipse((cx-r//7,cy+r*.6,cx+r//7,cy+r*.9),fill=INK); _text(im,(cx,cy+r*2.55),item.label,r//2,spec=spec)
        if item.value: _text(im,(cx,cy+r*3.1),item.value,r//3,RED if item.emphasis else INK,spec=spec)
    if spec.meaning_line: _text(im,(w//2,int(h*.94)),spec.meaning_line,h//15,spec=spec,readable=False)
    return im
def _blueprint(spec,size):
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); _text(im,(w//2,int(h*.08)),spec.title,h//11,SKY,spec=spec,readable=False)
    d.polygon([(w*.3,h*.72),(w*.5,h*.32),(w*.7,h*.72)],outline=SKY,width=5); d.rectangle((w*.3,h*.72,w*.7,h*.8),outline=SKY,width=5)
    for i,item in enumerate(spec.items[:3]):
        x,y=((w*.84,h*.3),(w*.15,h*.55),(w*.5,h*.89))[i]; _line(d,(w*.5,h*.54),(x,y-h*.04),SKY,3); _text(im,(x,y),item.label,h//13,RED if item.emphasis else INK,spec=spec)
        if item.value: _text(im,(x,y+int(h*.075)),item.value,h//15,RED if item.emphasis else INK,spec=spec)
    return im
def _map(spec,size):
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); rng=_rng(spec.seed)
    for i,item in enumerate(spec.items[:3]):
        cx,cy=((w*.27,h*.4),(w*.65,h*.3),(w*.53,h*.7))[i]; r=min(w,h)*(.16 if item.emphasis else .12)
        for k in range(6):
            x=cx+rng.uniform(-r,r); y=cy+rng.uniform(-r*.5,r*.5); d.ellipse((x-r*.5,y-r*.35,x+r*.5,y+r*.35),fill=(100,120,140,230))
        _text(im,(cx,cy-r*.12),item.value or "",int(r*.55),CHALK,spec=spec); _text(im,(cx,cy+r*.35),item.label,int(r*.28),CHALK,spec=spec)
    return im
def _flow(spec,size):
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); _text(im,(w//2,int(h*.08)),spec.title,h//12,CHALK,spec=spec,readable=False); nodes=spec.items[:3]
    for i,item in enumerate(nodes):
        x=w*(.18+.30*i); y=h*.53; half_w=w*.105; half_h=h*.105
        d.rounded_rectangle((x-half_w,y-half_h,x+half_w,y+half_h),radius=max(12,int(h*.024)),fill=(20,69,52,210),outline=CHALK,width=max(4,h//100))
        _text(im,(x,y-int(h*.052)),item.label,int(h*.048),CHALK,spec=spec)
        if item.value: _text(im,(x,y+int(h*.025)),item.value,int(h*.033),YELLOW if item.emphasis else CHALK,spec=spec)
        if i:
            previous_x=w*(.18+.30*(i-1)); start=(previous_x+half_w+int(w*.018),y); end=(x-half_w-int(w*.018),y)
            _line(d,start,end,CHALK,max(4,h//110))
            arrow_x=end[0]; d.polygon([(arrow_x,y),(arrow_x-int(w*.025),y-int(h*.035)),(arrow_x-int(w*.025),y+int(h*.035))],fill=CHALK)
    if spec.stamp: _text(im,(w//2,int(h*.84)),spec.stamp,h//10,RED,spec=spec,readable=False)
    return im
def _stage_rich(spec, size):
    """보드 면적을 충분히 채우는 단계형 카드 다이어그램을 렌더링한다."""
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im)
    _text(im,(w//2,int(h*.08)),spec.title,h//10,spec=spec,readable=False)
    items = spec.items[:4]
    positions = [(w * (.20 + .30 * i), h * .47) for i in range(len(items))] if len(items) <= 3 else [
        (w * (.30 + .40 * (i % 2)), h * (.32 + .36 * (i // 2))) for i in range(len(items))
    ]
    card_w = int(w * (.22 if len(items) <= 3 else .25)); card_h = int(h * (.30 if len(items) <= 3 else .24))
    for i,item in enumerate(items):
        cx,cy=map(int,positions[i]); left=cx-card_w//2; top=cy-card_h//2
        d.rounded_rectangle((left,top,left+card_w,top+card_h),radius=max(16,card_h//9),fill=YELLOW if item.emphasis else CREAM,outline=INK,width=max(5,card_h//24))
        lock_r=max(24,card_h//6); lock_cy=top+int(card_h*.43)
        d.arc((cx-lock_r,lock_cy-lock_r*1.25,cx+lock_r,lock_cy+lock_r*.10),180,360,fill=INK,width=max(5,lock_r//5))
        d.rounded_rectangle((cx-lock_r,lock_cy,cx+lock_r,lock_cy+lock_r*2),radius=max(8,lock_r//5),fill=(255,255,255,220),outline=INK,width=max(4,lock_r//6))
        d.ellipse((cx-lock_r//7,lock_cy+lock_r*.62,cx+lock_r//7,lock_cy+lock_r*.94),fill=INK)
        _text(im,(cx,top+int(card_h*.13)),item.label,max(32,card_h//7),spec=spec)
        if item.value: _text(im,(cx,top+int(card_h*.88)),item.value,max(28,card_h//8),RED if item.emphasis else INK,spec=spec)
        if i and len(items) <= 3:
            previous_x=int(positions[i-1][0]); start=(previous_x+card_w//2+int(w*.012),cy); end=(left-int(w*.012),cy)
            _line(d,start,end,INK,max(5,h//90)); d.polygon([(end[0],cy),(end[0]-int(w*.022),cy-int(h*.025)),(end[0]-int(w*.022),cy+int(h*.025))],fill=INK)
    if spec.meaning_line: _text(im,(w//2,int(h*.88)),spec.meaning_line,h//15,spec=spec,readable=False)
    return im


def _blueprint_rich(spec, size):
    """수치와 품목을 독립 카드로 표시하는 설계도형 다이어그램을 렌더링한다."""
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im)
    _text(im,(w//2,int(h*.08)),spec.title,h//11,SKY,spec=spec,readable=False)
    for x in range(int(w*.16),int(w*.85),max(18,int(w*.06))): _line(d,(x,int(h*.18)),(x,int(h*.84)),(84,191,255,78),2)
    for y in range(int(h*.20),int(h*.85),max(18,int(h*.10))): _line(d,(int(w*.14),y),(int(w*.86),y),(84,191,255,78),2)
    d.polygon([(w*.33,h*.70),(w*.5,h*.29),(w*.67,h*.70)],outline=SKY,width=max(5,h//90)); d.rectangle((w*.33,h*.70,w*.67,h*.77),outline=SKY,width=max(5,h//90))
    points=((w*.79,h*.34),(w*.21,h*.52),(w*.50,h*.77))
    for i,item in enumerate(spec.items[:3]):
        x,y=map(int,points[i]); box_w=int(w*.23); box_h=int(h*.17); box=(x-box_w//2,y-box_h//2,x+box_w//2,y+box_h//2)
        _line(d,(int(w*.5),int(h*.53)),(x,y),SKY,max(4,h//150))
        d.ellipse((x-11,y-11,x+11,y+11),fill=SKY,outline=INK,width=2)
        d.rounded_rectangle(box,radius=max(12,h//45),fill=(232,248,255,220),outline=SKY,width=max(4,h//150))
        _text(im,(x,y-int(box_h*.22)),item.label,max(30,h//16),RED if item.emphasis else INK,spec=spec)
        if item.value: _text(im,(x,y+int(box_h*.22)),item.value,max(28,h//18),RED if item.emphasis else INK,spec=spec)
    return im


def _map_rich(spec, size):
    """방송 화면을 채우는 관세율 구름·화살표 다이어그램을 렌더링한다."""
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); rng=_rng(spec.seed)
    _text(im,(w//2,int(h*.10)),spec.title,max(42,h//12),CHALK,spec=spec,readable=False)
    items=spec.items[:3]
    positions = [(w*.28,h*.48),(w*.68,h*.43)] if len(items) <= 2 else [(w*.24,h*.43),(w*.68,h*.36),(w*.50,h*.72)]
    radius = min(w,h) * (.20 if len(items) <= 2 else .145)
    for i,item in enumerate(items):
        cx,cy=map(int,positions[i]); r=int(radius * (1.10 if item.emphasis else 1.0))
        for k in range(8):
            angle=(k/8)*tau; x=cx+int(cos(angle)*r*.56); y=cy+int(sin(angle)*r*.30)
            d.ellipse((x-r*.45,y-r*.30,x+r*.45,y+r*.30),fill=(100,120,140,242),outline=(232,242,245,235),width=max(3,r//20))
        d.rounded_rectangle((cx-int(r*.70),cy-int(r*.25),cx+int(r*.70),cy+int(r*.34)),radius=max(14,r//7),fill=(20,69,82,185))
        _text(im,(cx,cy-int(r*.10)),item.value or "",max(36,int(r*.50)),CHALK,spec=spec)
        _text(im,(cx,cy+int(r*.22)),item.label,max(28,int(r*.25)),CHALK,spec=spec)
        for drop in range(4):
            dx=int((drop-1.5)*r*.27); d.line((cx+dx,cy+int(r*.58),cx+dx-int(r*.08),cy+int(r*.82)),fill=SKY,width=max(4,r//18))
    if len(items) >= 2:
        start=(int(positions[0][0]+radius*.95),int(h*.46)); end=(int(positions[1][0]-radius*.95),int(h*.44))
        _line(d,start,end,SKY,max(5,h//85)); d.polygon([(end[0],end[1]),(end[0]-int(w*.03),end[1]-int(h*.03)),(end[0]-int(w*.03),end[1]+int(h*.03))],fill=SKY)
    _text(im,(w//2,int(h*.87)),"USTR · 2024",max(28,h//18),CHALK,spec=spec,readable=False)
    return im


RENDERERS={"stage_locks":_stage_rich,"blueprint_callouts":_blueprint_rich,"map_clouds":_map_rich,"flow_chalk":_flow}
def render_diagram(spec: DiagramSpec, size):
    if not spec.items: raise ValueError("검증된 다이어그램 항목이 없습니다")
    try: return RENDERERS[spec.kind](spec,size)
    except KeyError as exc: raise ValueError(f"알 수 없는 다이어그램 종류: {spec.kind}") from exc
