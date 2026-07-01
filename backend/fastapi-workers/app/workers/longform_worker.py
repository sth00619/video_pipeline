"""
Phase 3-5A v3 — 롱폼 조립 + TTS 기반 자막 오버레이

주식 플랫폼 특화:
  - TTS chunks의 start/duration 기반 자막 동기화
  - 자막 스타일: 하단 중앙, 반투명 박스, NanumGothic
  - 자막이 없는 구간은 투명 처리
"""
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

NANUM_FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


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

        # 1. 씬별 클립 생성
        clip_list_path = str(temp_dir / "clips.txt")
        clip_paths = []

        for i, scene in enumerate(scenes):
            img_path = scene.get("image_path", "")
            duration = float(scene.get("duration", 15.0))
            clip_path = str(temp_dir / f"clip_{i:03d}.mp4")

            if not os.path.exists(img_path):
                cmd = (
                    f'ffmpeg -f lavfi '
                    f'-i "color=c=0f3460:s=1920x1080:r=30" '
                    f'-t {duration:.3f} '
                    f'-c:v libx264 -pix_fmt yuv420p '
                    f'-y "{clip_path}" -loglevel error'
                )
            else:
                cmd = (
                    f'ffmpeg -framerate 1 -loop 1 -i "{img_path}" '
                    f'-t {duration:.3f} '
                    f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
                    f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:0f3460,'
                    f'setsar=1,fps=30" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-y "{clip_path}" -loglevel error'
                )

            ret = os.system(cmd)
            if ret != 0:
                logger.warning(f"clip_{i:03d} 실패, 폴백 생성")
                os.system(
                    f'ffmpeg -f lavfi -i "color=c=1a1a2e:s=1920x1080:r=30" '
                    f'-t {duration:.3f} -c:v libx264 -pix_fmt yuv420p '
                    f'-y "{clip_path}" -loglevel error'
                )
            clip_paths.append(clip_path)

        # 2. concat
        with open(clip_list_path, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        silent_video = str(temp_dir / "silent.mp4")
        ret = os.system(
            f'ffmpeg -f concat -safe 0 -i "{clip_list_path}" '
            f'-c:v libx264 -preset fast -pix_fmt yuv420p '
            f'-y "{silent_video}" -loglevel error'
        )

        # 3. 자막 SRT 생성 (TTS chunks 기반)
        srt_path = str(temp_dir / "subtitles.srt")
        self._generate_srt(chunks, srt_path)

        # 4. 음성 + 자막 합성
        font = NANUM_FONT if os.path.exists(NANUM_FONT) else ""

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            if font and os.path.exists(srt_path):
                # 음성 + 자막 동시 적용
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'-vf "subtitles=\'{srt_path}\':'
                    f'force_style=\'FontName=NanumGothic,'
                    f'FontSize=22,'
                    f'PrimaryColour=&Hffffff,'
                    f'OutlineColour=&H000000,'
                    f'BorderStyle=3,'
                    f'BackColour=&H80000000,'
                    f'Outline=2,'
                    f'Shadow=0,'
                    f'Alignment=2,'
                    f'MarginV=40\'" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-c:a aac -b:a 192k -shortest '
                    f'-y "{output_path}" -loglevel error'
                )
            else:
                # 자막 없이 음성만
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'-c:v copy -c:a aac -b:a 192k -shortest '
                    f'-y "{output_path}" -loglevel error'
                )
        else:
            if font and os.path.exists(srt_path):
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" '
                    f'-vf "subtitles=\'{srt_path}\':'
                    f'force_style=\'FontName=NanumGothic,FontSize=22,'
                    f'PrimaryColour=&Hffffff,BorderStyle=3,'
                    f'BackColour=&H80000000,Alignment=2,MarginV=40\'" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-y "{output_path}" -loglevel error'
                )
            else:
                merge_cmd = f'cp "{silent_video}" "{output_path}"'

        ret = os.system(merge_cmd)
        if ret != 0:
            logger.error("자막 합성 실패, 자막 없이 재시도")
            fallback = (
                f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                f'-c:v copy -c:a aac -b:a 192k -shortest '
                f'-y "{output_path}" -loglevel error'
            )
            os.system(fallback)

        if not os.path.exists(output_path):
            raise RuntimeError("롱폼 영상 생성 실패")

        # 실제 duration 확인
        probe = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{output_path}"'
        ).read().strip()
        actual_duration = float(probe) if probe else total_duration

        file_size = os.path.getsize(output_path)
        has_subtitles = font and os.path.exists(srt_path)
        logger.info(f"롱폼 조립 완료: size={file_size/1024/1024:.1f}MB, "
                    f"actual={actual_duration:.0f}s, subtitles={has_subtitles}")

        # temp 정리
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
            "has_subtitles": bool(has_subtitles),
            "resolution": "1920x1080",
        }

    def _generate_srt(self, chunks: list, srt_path: str):
        """TTS chunks → SRT 자막 파일 생성"""
        def to_srt_time(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, chunk in enumerate(chunks, 1):
                start = chunk.get("start", 0)
                duration = chunk.get("duration", 3.0)
                end = start + duration
                text = chunk.get("text", "").strip()
                if not text:
                    continue
                # 자막 한 줄 최대 40자
                if len(text) > 40:
                    mid = len(text) // 2
                    # 공백 기준으로 나누기
                    split_at = text.rfind(" ", 0, mid) if " " in text[:mid] else mid
                    text = text[:split_at] + "\n" + text[split_at:].strip()

                f.write(f"{i}\n")
                f.write(f"{to_srt_time(start)} --> {to_srt_time(end)}\n")
                f.write(f"{text}\n\n")

        logger.info(f"SRT 자막 생성: {len(chunks)}개 항목")
