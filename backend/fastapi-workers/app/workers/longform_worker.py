"""
Phase 3-5 v6 — 롱폼 조립 (초반 AI 움짤 + 나머지 zoompan)

구조 개선:
  - 초반 30~60초만 Fal.ai Kling image-to-video AI 움짤 생성 (목표 분량별 자동 계산)
  - 나머지 씬은 FFmpeg zoompan 필터로 정적 이미지에 줌인 생동감 부여
  - 자막 수치/퍼센트 노란색 강조 활성화
  - 목표 분량별 초반 AI 움짤 길이:
    5분 → 앞 30초 / 10분 → 앞 45초 / 15분 → 앞 60초 / 20분 → 앞 60초
"""
import json
import os
import re
import logging
import subprocess
from pathlib import Path
from app.utils.process_manager import register_process, unregister_process, is_job_stopped

logger = logging.getLogger(__name__)

def _run_subprocess(cmd: str, job_id: int) -> int:
    """FFmpeg 등의 명령어를 subprocess.Popen으로 실행하고 중지 트래킹 등록"""
    if is_job_stopped(job_id):
        raise RuntimeError(f"Job {job_id} is stopped. Aborting execution.")
    logger.info(f"Running tracked subprocess: {cmd}")
    p = subprocess.Popen(cmd, shell=True)
    register_process(job_id, p)
    try:
        ret = p.wait()
        return ret
    finally:
        unregister_process(job_id, p)

NANUM_BOLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
NANUM_REGULAR = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


class LongformWorker:

    def assemble(self, tts_meta_json: str, scenes_meta_json: str,
                 gifs_meta_json: str, job_id: int = 0) -> dict:

        tts_meta = json.loads(tts_meta_json)
        audio_path = tts_meta.get("audio_path", "")
        total_duration = tts_meta.get("total_duration", 0)
        chunks = tts_meta.get("chunks", [])

        raw_scenes = json.loads(scenes_meta_json)
        scenes = [json.loads(s) if isinstance(s, str) else s for s in raw_scenes]

        raw_gifs = json.loads(gifs_meta_json)
        gifs = [json.loads(g) if isinstance(g, str) else g for g in raw_gifs]

        logger.info(f"롱폼 조립 시작: job_id={job_id}, scenes={len(scenes)}, "
                    f"chunks={len(chunks)}, total={total_duration:.0f}s")

        job_dir = Path(f"/app/data/jobs/{job_id}/longform")
        job_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = job_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        output_path = str(job_dir / "final.mp4")

        # 1. 씬별 재생 시간(duration) 동적 분배 (비디오 길이 = 오디오 길이 일치화)
        if total_duration > 0 and len(scenes) > 0:
            total_chars = sum(len(scene.get("content", "") or scene.get("text", "") or "") for scene in scenes)
            for scene in scenes:
                char_len = len(scene.get("content", "") or scene.get("text", "") or "")
                if total_chars > 0:
                    scene["duration"] = round((char_len / total_chars) * total_duration, 3)
                else:
                    scene["duration"] = round(total_duration / len(scenes), 3)

        # Kling 비디오 프로바이더 로드 (하이브리드 모드)
        video_provider = None
        try:
            from app.providers.factory import get_video_provider
            video_provider = get_video_provider()
            logger.info("하이브리드 Kling 비디오 프로바이더 로드 성공")
        except Exception as e:
            logger.warning(f"Kling 비디오 프로바이더 로드 실패 (FFmpeg 폴백 사용): {e}")

        # 초반 AI 움짤 대상 씬 수 계산
        intro_kling_count = _get_intro_kling_count(total_duration, len(scenes))
        logger.info(f"초반 Kling AI 움짤 대상: {intro_kling_count}씬 (전체 {len(scenes)}씬 중)")

        # 씬별 클립 생성
        clip_list_path = str(temp_dir / "clips.txt")
        clip_paths = []

        for i, scene in enumerate(scenes):
            if is_job_stopped(job_id):
                raise RuntimeError(f"Job {job_id} stopped by user.")

            img_path = scene.get("image_path", "")
            raw_dur = scene.get("duration")
            duration = float(raw_dur) if raw_dur is not None else 15.0
            clip_path = str(temp_dir / f"clip_{i:03d}.mp4")
            section = scene.get("section", "default")
            bg_color = {
                "intro": "1a1a2e", "background": "16213e",
                "data": "0f3460", "scenario": "1b1464",
                "action": "0d3b2e", "conclusion": "1a1a2e",
            }.get(section, "0d1b2a")

            # 초반 씬만 Kling AI 움짤, 나머지는 zoompan 효과
            if video_provider and i < intro_kling_count:
                try:
                    logger.info(f"씬 {i} Kling AI 움짤 생성 (초반 {intro_kling_count}씬)")
                    prompt = scene.get("prompt", "") or scene.get("text", "") or "professional financial chart animation cinematic"
                    video_provider.generate(
                        prompt=prompt,
                        duration=min(int(duration), 5),
                        output_path=clip_path,
                        image_path=img_path,
                        image_url=None
                    )
                    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 1000:
                        temp_kling = clip_path + ".temp.mp4"
                        try:
                            os.rename(clip_path, temp_kling)
                            std_cmd = (
                                f'ffmpeg -i "{temp_kling}" -vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
                                f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30" '
                                f'-t {duration:.3f} -c:v libx264 -preset fast -pix_fmt yuv420p -an -y "{clip_path}" -loglevel error'
                            )
                            _run_subprocess(std_cmd, job_id)
                        except Exception as ex:
                            logger.warning(f"씬 {i} Kling 표준화 중 오류 발생, 원본 사용 시도: {ex}")
                            if os.path.exists(temp_kling) and not os.path.exists(clip_path):
                                os.rename(temp_kling, clip_path)
                        finally:
                            if os.path.exists(temp_kling):
                                try:
                                    os.remove(temp_kling)
                                except Exception:
                                    pass
                        
                        clip_paths.append(clip_path)
                        logger.info(f"씬 {i} Kling AI 움짤 완성 (표준 규격 변환 완료)")
                        continue
                except Exception as e:
                    logger.warning(f"씬 {i} Kling AI 생성 실패, zoompan 폴백: {e}")

            # 나머지 씬: FFmpeg zoompan 효과
            if os.path.exists(img_path):
                _ffmpeg_zoompan(img_path, clip_path, duration, bg_color, job_id)
            else:
                _run_subprocess(
                    f'ffmpeg -f lavfi -i "color=c={bg_color}:s=1920x1080:r=30" '
                    f'-t {duration:.3f} -c:v libx264 -pix_fmt yuv420p '
                    f'-y "{clip_path}" -loglevel error',
                    job_id
                )
            clip_paths.append(clip_path)

        # 2. concat
        with open(clip_list_path, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        silent_video = str(temp_dir / "silent.mp4")
        _run_subprocess(
            f'ffmpeg -f concat -safe 0 -i "{clip_list_path}" '
            f'-c:v libx264 -preset fast -pix_fmt yuv420p '
            f'-y "{silent_video}" -loglevel error',
            job_id
        )

        # 3. ASS 자막 생성 (경제사냥꾼 스타일)
        ass_path = str(temp_dir / "subtitles.ass")
        self._generate_ass(chunks, ass_path)

        # 4. 음성 + BGM + 자막 합성
        font_available = os.path.exists(NANUM_BOLD) or os.path.exists(NANUM_REGULAR)
        ass_exists = os.path.exists(ass_path) and os.path.getsize(ass_path) > 200
        audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0

        # BGM 파일 탐색 (bgm_worker가 생성한 파일)
        bgm_path = f"/app/data/jobs/{job_id}/bgm.mp3"
        bgm_exists = os.path.exists(bgm_path) and os.path.getsize(bgm_path) > 0

        if audio_exists:
            vf_filter = f'-vf "ass=\'{ass_path}\'" ' if (font_available and ass_exists) else ''
            vcodec = '-c:v libx264 -preset fast -pix_fmt yuv420p' if vf_filter else '-c:v copy'

            if bgm_exists:
                # 3-트랙 믹싱: 나레이션(100%) + BGM(12%, ≈-18dB)
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" -i "{bgm_path}" '
                    f'-filter_complex "[1:a]volume=1.0[narr];[2:a]volume=0.12,aloop=loop=-1:size=2e+09[bgm];'
                    f'[narr][bgm]amix=inputs=2:duration=first:dropout_transition=3[mixed]" '
                    f'{vf_filter}'
                    f'{vcodec} '
                    f'-map 0:v -map "[mixed]" '
                    f'-c:a aac -b:a 192k -shortest '
                    f'-y "{output_path}" -loglevel error'
                )
                logger.info("BGM 믹싱 적용: 나레이션 + BGM(-18dB)")
            else:
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'{vf_filter}'
                    f'{vcodec} '
                    f'-map 0:v -map 1:a '
                    f'-c:a aac -b:a 192k -shortest '
                    f'-y "{output_path}" -loglevel error'
                )
        else:
            if font_available and ass_exists:
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" '
                    f'-vf "ass=\'{ass_path}\'" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-y "{output_path}" -loglevel error'
                )
            else:
                merge_cmd = f'cp "{silent_video}" "{output_path}"'

        ret = _run_subprocess(merge_cmd, job_id)
        if ret != 0:
            logger.error("자막/BGM 합성 실패, 폴백")
            if audio_exists:
                _run_subprocess(
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'-map 0:v -map 1:a '
                    f'-c:v copy -c:a aac -shortest '
                    f'-y "{output_path}" -loglevel error',
                    job_id
                )
            else:
                _run_subprocess(f'cp "{silent_video}" "{output_path}"', job_id)

        if not os.path.exists(output_path):
            raise RuntimeError("롱폼 영상 생성 실패")

        probe = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{output_path}"'
        ).read().strip()
        actual_duration = float(probe) if probe else total_duration

        file_size = os.path.getsize(output_path)
        has_subtitles = font_available and ass_exists
        logger.info(f"롱폼 조립 완료: size={file_size/1024/1024:.1f}MB, "
                    f"actual={actual_duration:.0f}s, subtitles={has_subtitles}")

        for cp in clip_paths:
            if os.path.exists(cp):
                os.remove(cp)
        if os.path.exists(silent_video):
            os.remove(silent_video)

        return {
            "job_id": job_id,
            "video_path": output_path,
            "duration_seconds": round(actual_duration, 1),
            "scene_count": len(scenes),
            "gif_count": len(gifs),
            "has_subtitles": has_subtitles,
            "resolution": "1920x1080",
        }

    def _generate_ass(self, chunks: list, ass_path: str):
        """
        ASS 자막 — 경제사냥꾼 스타일
        - NanumGothicBold 72px (이전 52px → 더 큼)
        - 검정 불투명 박스 배경 (BorderStyle=3)
        - 흰색 굵은 텍스트
        - 하단 중앙 배치 (Alignment=2)
        - 최대 20자 1줄
        """
        font_name = "NanumGothicBold" if os.path.exists(NANUM_BOLD) else "NanumGothic"

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,{font_name},76,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,3,0,0,2,40,40,80,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
        # 스타일 설명:
        # Fontsize=72 → 이전 52에서 증가 (경제사냥꾼 수준)
        # BorderStyle=3 → 불투명 박스 배경 (OutlineColour 무시, BackColour 사용)
        # BackColour=&H80000000 → 반투명 검정 박스 (Alpha=80)
        # Bold=-1 → 굵게
        # Outline=0, Shadow=0 → 박스 모드에서 외곽선/그림자 없음
        # Alignment=2 → 하단 중앙
        # MarginV=50 → 하단 50px 여백

        def to_ass_time(s: float) -> str:
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h}:{m:02d}:{sec:05.2f}"

        lines = [header]
        for chunk in chunks:
            text = chunk.get("text", "").strip()
            if not text:
                continue

            start_sec = chunk.get("start", 0.0)
            dur = chunk.get("duration", 3.0)
            end_sec = start_sec + dur

            # 수치/퍼센트/포인트 노란색 강조 활성화
            display = self._trim_to_limit(self._highlight_stock_numbers(text))

            start_str = to_ass_time(start_sec)
            end_str = to_ass_time(end_sec)
            lines.append(f"Dialogue: 0,{start_str},{end_str},Main,,0,0,0,,{display}")

        # UTF-8-SIG 저장
        with open(ass_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines))

        logger.info(f"ASS 자막 생성: {len(chunks)}개 항목")
    @staticmethod
    def _trim_to_limit(text: str) -> str:
        return text

    @staticmethod
    def _highlight_stock_numbers(text: str) -> str:
        """주식 수치 노란색 강조 (ASS 인라인 태그)"""
        text = re.sub(r'([+-]?\d+\.?\d*퍼센트)', lambda m: '{\\c&H00FFFF&}' + m.group(1) + '{\\c&HFFFFFF&}', text)
        text = re.sub(r'(\d+포인트)', lambda m: '{\\c&H00FFFF&}' + m.group(1) + '{\\c&HFFFFFF&}', text)
        text = re.sub(r'(\d+(?:억|만|천)?(?:원|달러))', lambda m: '{\\c&H00FFFF&}' + m.group(1) + '{\\c&HFFFFFF&}', text)
        return text


# ──────────────────────────────────────────────────────────
# 모듈 수준 헬퍼 함수
# ──────────────────────────────────────────────────────────

# 목표 분량별 초반 AI 움짤 길이 (초 단위)
_INTRO_KLING_SECONDS = {
    5: 30,
    10: 45,
    15: 60,
    20: 60,
}


def _get_intro_kling_count(total_duration: float, total_scenes: int) -> int:
    """
    영상 총 길이 기반으로 초반 AI 움짤(Kling) 대상 씬 수를 계산합니다.
    - 5분 이하 → 앞 30초
    - 10분 이하 → 앞 45초
    - 15분 이하 → 앞 60초
    - 20분 초과 → 앞 60초
    """
    if total_scenes <= 0 or total_duration <= 0:
        return 3  # 기본 3씬

    target_minutes = total_duration / 60.0
    if target_minutes <= 5:
        intro_secs = 30
    elif target_minutes <= 10:
        intro_secs = 45
    elif target_minutes <= 15:
        intro_secs = 60
    else:
        intro_secs = 60

    secs_per_scene = total_duration / total_scenes
    count = max(2, int(intro_secs / secs_per_scene))
    logger.info(f"intro_kling_count 계산: total={total_duration:.0f}s, scenes={total_scenes}, "
                f"secs_per_scene={secs_per_scene:.1f}s, intro_secs={intro_secs}s → {count}씬")
    return count


def _ffmpeg_zoompan(img_path: str, clip_path: str, duration: float, bg_color: str = "0d1b2a", job_id: int = 0):
    """
    정적 이미지에 FFmpeg zoompan 필터로 은은한 줌인 효과를 적용하여 생동감을 부여합니다.
    - 이미지 스케일을 2000x1125로 올린 후 zoompan으로 중심에서 천천히 줌인
    - 줌 배율: 1.0 → 1.06 (6% 줌인, 너무 과하지 않게)
    """
    frames = int(duration * 30)  # 30fps 기준 프레임 수
    zoom_speed = 0.0008  # 줌 속도 (값이 작을수록 느리게 줌인)
    max_zoom = 1.06

    cmd = (
        f'ffmpeg -loop 1 -i "{img_path}" '
        f'-filter_complex '
        f'"[0:v]scale=2000:1125,'
        f'zoompan=z=\'min(zoom+{zoom_speed},{max_zoom})\''
        f':x=\'iw/2-(iw/zoom/2)\''
        f':y=\'ih/2-(ih/zoom/2)\''
        f':d={frames}:s=1920x1080:fps=30,'
        f'setsar=1[v]" '
        f'-map "[v]" -t {duration:.3f} '
        f'-c:v libx264 -preset fast -pix_fmt yuv420p '
        f'-y "{clip_path}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0:
        logger.warning(f"zoompan 실패, 단순 정적 이미지로 폴백: {img_path}")
        _run_subprocess(
            f'ffmpeg -loop 1 -i "{img_path}" '
            f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
            f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:{bg_color},setsar=1,fps=30" '
            f'-t {duration:.3f} -c:v libx264 -preset fast -pix_fmt yuv420p '
            f'-y "{clip_path}" -loglevel error',
            job_id
        )
