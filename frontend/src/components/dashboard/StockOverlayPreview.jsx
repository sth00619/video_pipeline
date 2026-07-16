import { useEffect, useRef, useState } from 'react'

const ANCHORS = [
  ['top_left', '좌상단'],
  ['top_right', '우상단'],
  ['bottom_left', '좌하단'],
  ['bottom_right', '우하단'],
  ['center', '중앙'],
]

function parseNumber(value, fallback = 0) {
  const parsed = Number(String(value).replace(/,/g, ''))
  return Number.isFinite(parsed) ? parsed : fallback
}

export default function StockOverlayPreview() {
  const canvasRef = useRef(null)
  const [imageSrc, setImageSrc] = useState('/demo_composited_preview.png')
  const [market, setMarket] = useState('KR')
  const [name, setName] = useState('코스피')
  const [value, setValue] = useState('2650.31')
  const [change, setChange] = useState('21.05')
  const [changePct, setChangePct] = useState('0.80')
  const [placementMode, setPlacementMode] = useState('anchor')
  const [anchor, setAnchor] = useState('top_right')
  const [margin, setMargin] = useState('40')
  const [x, setX] = useState('1430')
  const [y, setY] = useState('40')

  useEffect(() => {
    const image = new Image()
    image.onload = () => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      const width = 960
      const height = 540
      canvas.width = width
      canvas.height = height
      ctx.clearRect(0, 0, width, height)

      const imageRatio = image.width / image.height
      const canvasRatio = width / height
      let drawW = width
      let drawH = height
      let offsetX = 0
      let offsetY = 0
      if (imageRatio > canvasRatio) {
        drawH = height
        drawW = height * imageRatio
        offsetX = (width - drawW) / 2
      } else {
        drawW = width
        drawH = width / imageRatio
        offsetY = (height - drawH) / 2
      }
      ctx.drawImage(image, offsetX, offsetY, drawW, drawH)

      const scale = width / 1920
      const cardW = 455 * scale
      const cardH = 220 * scale
      const safeMargin = parseNumber(margin, 40) * scale
      let cardX = parseNumber(x, 1430) * scale
      let cardY = parseNumber(y, 40) * scale
      if (placementMode === 'anchor') {
        if (anchor === 'top_left') [cardX, cardY] = [safeMargin, safeMargin]
        if (anchor === 'top_right') [cardX, cardY] = [width - cardW - safeMargin, safeMargin]
        if (anchor === 'bottom_left') [cardX, cardY] = [safeMargin, height - cardH - safeMargin]
        if (anchor === 'bottom_right') [cardX, cardY] = [width - cardW - safeMargin, height - cardH - safeMargin]
        if (anchor === 'center') [cardX, cardY] = [(width - cardW) / 2, (height - cardH) / 2]
      }

      const roundedRect = (left, top, w, h, radius) => {
        ctx.beginPath()
        ctx.roundRect(left, top, w, h, radius)
      }
      const positive = parseNumber(change) >= 0
      const accent = market === 'KR'
        ? (positive ? '#e53935' : '#1e88e5')
        : (positive ? '#26a65b' : '#e53935')
      ctx.save()
      roundedRect(cardX, cardY, cardW, cardH, 18 * scale)
      ctx.fillStyle = 'rgba(18, 22, 30, .92)'
      ctx.fill()
      ctx.fillStyle = accent
      roundedRect(cardX + 30 * scale, cardY + 25 * scale, 8 * scale, cardH - 50 * scale, 4 * scale)
      ctx.fill()
      ctx.textBaseline = 'middle'
      ctx.font = `700 ${24 * scale}px Pretendard, Arial, sans-serif`
      ctx.fillStyle = '#d2d8e2'
      ctx.fillText(name || '지수', cardX + 62 * scale, cardY + 42 * scale)
      ctx.font = `700 ${62 * scale}px Pretendard, Arial, sans-serif`
      ctx.fillStyle = '#f5f7fa'
      ctx.fillText(parseNumber(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }), cardX + 62 * scale, cardY + 108 * scale)
      ctx.font = `700 ${27 * scale}px Pretendard, Arial, sans-serif`
      ctx.fillStyle = accent
      const arrow = positive ? '▲' : '▼'
      const signedChange = `${positive ? '+' : ''}${parseNumber(change).toFixed(2)}`
      const signedPct = `${positive ? '+' : ''}${parseNumber(changePct).toFixed(2)}%`
      ctx.fillText(`${arrow} ${signedChange} (${signedPct})`, cardX + 62 * scale, cardY + 171 * scale)
      ctx.restore()
    }
    image.src = imageSrc
  }, [imageSrc, market, name, value, change, changePct, placementMode, anchor, margin, x, y])

  const handleImage = (event) => {
    const file = event.target.files?.[0]
    if (file) setImageSrc(URL.createObjectURL(file))
  }

  return (
    <section className="bg-navy-800 rounded-xl border border-navy-700 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="font-semibold">수치 오버레이 미리보기</h2>
          <p className="text-xs text-gray-400 mt-1">AI 이미지에는 숫자를 그리지 않고, 검증된 카드 PNG를 별도 레이어로 합성합니다.</p>
        </div>
        <label className="text-xs text-accent-cyan hover:underline cursor-pointer">
          배경 이미지 선택
          <input type="file" accept="image/*" onChange={handleImage} className="hidden" />
        </label>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-4">
        <div className="rounded-lg overflow-hidden border border-navy-700 bg-black">
          <canvas ref={canvasRef} className="w-full h-auto block" />
        </div>
        <div className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <label>시장<select value={market} onChange={e => setMarket(e.target.value)} className="field"><option value="KR">한국</option><option value="US">미국</option></select></label>
            <label>이름<input value={name} onChange={e => setName(e.target.value)} className="field" /></label>
            <label>현재값<input value={value} onChange={e => setValue(e.target.value)} className="field" /></label>
            <label>변화량<input value={change} onChange={e => setChange(e.target.value)} className="field" /></label>
            <label>변화율(%)<input value={changePct} onChange={e => setChangePct(e.target.value)} className="field" /></label>
          </div>

          <div className="border-t border-navy-700 pt-3">
            <div className="font-semibold text-gray-200 mb-2">배치 방식</div>
            <div className="flex gap-3 mb-2">
              <label className="flex items-center gap-1"><input type="radio" checked={placementMode === 'anchor'} onChange={() => setPlacementMode('anchor')} /> 앵커</label>
              <label className="flex items-center gap-1"><input type="radio" checked={placementMode === 'pixel'} onChange={() => setPlacementMode('pixel')} /> 픽셀 좌표</label>
            </div>
            {placementMode === 'anchor' ? (
              <div className="grid grid-cols-2 gap-2">
                <label>위치<select value={anchor} onChange={e => setAnchor(e.target.value)} className="field"><option value="top_left">좌상단</option><option value="top_right">우상단</option><option value="bottom_left">좌하단</option><option value="bottom_right">우하단</option><option value="center">중앙</option></select></label>
                <label>여백<input value={margin} onChange={e => setMargin(e.target.value)} className="field" /></label>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <label>X (1920 기준)<input value={x} onChange={e => setX(e.target.value)} className="field" /></label>
                <label>Y (1080 기준)<input value={y} onChange={e => setY(e.target.value)} className="field" /></label>
              </div>
            )}
            <p className="text-[11px] text-accent-cyan mt-2">
              {placementMode === 'anchor' ? '권장: 해상도·크롭이 바뀌어도 카드가 안전영역을 유지합니다.' : '고정 템플릿 검증용: 이미지 구도가 바뀌면 위치가 깨질 수 있습니다.'}
            </p>
          </div>
        </div>
      </div>
      <style>{`.field{display:block;width:100%;margin-top:4px;background:#172238;border:1px solid #2d3d59;border-radius:6px;padding:6px;color:#fff;outline:none}`}</style>
    </section>
  )
}
