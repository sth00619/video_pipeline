"""v4 서사형 다이어그램의 결정론적 RGBA 렌더러."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
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
        x,y=((w*.84,h*.3),(w*.15,h*.55),(w*.5,h*.92))[i]; _line(d,(w*.5,h*.54),(x,y-h*.04),SKY,3); _text(im,(x,y),item.label,h//13,RED if item.emphasis else INK,spec=spec)
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
    w,h=size; im=Image.new("RGBA",size); d=ImageDraw.Draw(im); _text(im,(w//2,int(h*.08)),spec.title,h//12,CHALK,spec=spec,readable=False); nodes=spec.items[:5]
    for i,item in enumerate(nodes):
        x=w*(.14+.18*i); y=h*(.38 if i%2==0 else .6); d.rectangle((x-w*.075,y-h*.07,x+w*.075,y+h*.07),outline=CHALK,width=3); _text(im,(x,y),item.label,int(h*.05),CHALK,spec=spec)
        if i: _line(d,(w*(.14+.18*(i-1)) + w*.075,h*(.38 if (i-1)%2==0 else .6)),(x-w*.075,y),CHALK,3)
    if spec.stamp: _text(im,(w//2,int(h*.84)),spec.stamp,h//10,RED,spec=spec,readable=False)
    return im
RENDERERS={"stage_locks":_stage,"blueprint_callouts":_blueprint,"map_clouds":_map,"flow_chalk":_flow}
def render_diagram(spec: DiagramSpec, size):
    if not spec.items: raise ValueError("검증된 다이어그램 항목이 없습니다")
    try: return RENDERERS[spec.kind](spec,size)
    except KeyError as exc: raise ValueError(f"알 수 없는 다이어그램 종류: {spec.kind}") from exc
