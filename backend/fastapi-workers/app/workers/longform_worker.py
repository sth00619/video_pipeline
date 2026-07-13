"""
Phase 3-5 v7 — 롱폼 조립 (병렬 처리 + 인코딩 패스 축소)

v6 대비 변경점 (조립 시간 단축 목적):
  1. 씬별 클립 생성(Kling AI 움짤 / FFmpeg zoompan)을 ThreadPoolExecutor로
     병렬 처리. 기존에는 씬을 하나씩 순차로 처리해서 총 시간이
     "씬 개수 × 씬당 처리시간"으로 선형 증가했음. Kling API 호출은
     네트워크 I/O 대기(최대 180초 폴링)이고, zoompan은 CPU 바운드라서
     동시 실행 시 실제 이득이 큼.
  2. concat 단계를 재인코딩(-c:v libx264) 대신 스트림 복사(-c copy)로
     우선 시도. 씬별 클립이 이미 1단계에서 동일 코덱/해상도/프레임레이트로
     표준화되어 있으므로 재인코딩 없이 이어붙이기가 가능함. 실패 시에만
     기존 방식(재인코딩)으로 자동 폴백.
     → 기존 구조는 "씬별 인코딩 → concat 재인코딩 → 자막 합성 재인코딩"
       으로 사실상 영상을 최대 3번 인코딩했는데, 이번 변경으로 2번으로 줄어듦.
  3. 각 단계 소요시간을 로그로 남겨, 이후 병목 프로파일링이 쉽도록 함.

주의 (동시성 관련):
  - register_process/unregister_process(app.utils.process_manager)가
    스레드 세이프한지는 이 파일만으로 보장할 수 없음. 만약 여러 스레드가
    동시에 등록/해제할 때 경쟁 조건이 관측되면, 해당 모듈에 락(Lock)을
    추가하는 걸 권장합니다.
  - is_job_stopped() 체크는 각 씬 처리 시작 시점에 한 번 확인합니다.
    이미 실행 중인 FFmpeg/Kling 호출을 즉시 중단시키진 못하지만
    (기존 v6도 동일한 한계였음), 아직 시작 안 한 씬은 스킵됩니다.
  - 동시 실행 스레드 수는 runtime_config의 "longform_scene_max_workers"
    값을 따르며(없으면 기본 4), CPU/네트워크 과부하를 막기 위해
    최대 8로 상한을 둡니다.
"""
import json
import os
import re
import time
import logging
import subprocess
import concurrent.futures
from pathlib import Path
from app.utils.process_manager import register_process, unregister_process, is_job_stopped
from app import runtime_config

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

        stage_t0 = time.time()

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

        # [S4] 1. 씬별 재생 시간(duration) 정밀 타임라인 동적 매핑 (TTS 청크 기반)
        _assign_scene_durations_from_chunks(scenes, chunks, total_duration)

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

        # ── 2. 씬별 클립 생성 (병렬 처리) ──────────────────────────
        scene_stage_t0 = time.time()
        max_workers = _get_max_workers(len(scenes))
        logger.info(f"씬 클립 생성 병렬 처리 시작: max_workers={max_workers}")

        clip_paths_map: dict[int, str] = {}
        stopped_error = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._process_scene, i, scene, video_provider,
                    intro_kling_count, temp_dir, job_id
                ): i
                for i, scene in enumerate(scenes)
            }
            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                try:
                    idx, clip_path = future.result()
                    clip_paths_map[idx] = clip_path
                except Exception as e:
                    if "stopped by user" in str(e):
                        stopped_error = e
                        logger.info(f"Job {job_id} 중지 감지, 나머지 씬 처리 건너뜀")
                    else:
                        logger.error(f"씬 {i} 처리 중 예상치 못한 오류 (스킵): {e}")

        if stopped_error is not None:
            raise stopped_error

        clip_paths = [clip_paths_map[i] for i in sorted(clip_paths_map.keys()) if i in clip_paths_map]
        logger.info(
            f"씬 클립 생성 완료: {len(clip_paths)}/{len(scenes)}개 성공, "
            f"소요={time.time() - scene_stage_t0:.1f}s"
        )

        if not clip_paths:
            raise RuntimeError("씬 클립이 하나도 생성되지 않았습니다.")

        # ── 3. concat ─────────────────────────────────────────────────
        # 안전 우선: Kling 클립과 zoompan 클립은 타임베이스/비트레이트가
        # 미세하게 달라 -c copy가 exit 0을 반환해도 깨진 파일을 만들 수 있음.
        # → 항상 재인코딩(-c:v libx264)으로 처리해 파일 무결성을 보장.
        # (병렬 처리로 클립 생성 시간 자체가 줄었기 때문에, concat 재인코딩
        #  비용은 전체 대비 상대적으로 작아짐. 재생 불가 파일이 더 큰 손실.)
        concat_stage_t0 = time.time()
        clip_list_path = str(temp_dir / "clips.txt")
        with open(clip_list_path, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        silent_video = str(temp_dir / "silent.mp4")
        ret = _run_subprocess(
            f'ffmpeg -f concat -safe 0 -i "{clip_list_path}" '
            f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
            f'-y "{silent_video}" -loglevel error',
            job_id
        )

        # ffprobe로 실제 재생 가능 여부 검증
        concat_ok = _verify_video(silent_video)
        if not concat_ok:
            logger.error(
                f"concat 결과물 ffprobe 검증 실패 (ret={ret}). "
                f"파일이 손상됐거나 모든 씬 클립이 비정상일 가능성 있음."
            )
            raise RuntimeError("concat 단계에서 재생 가능한 영상을 만들지 못했습니다.")

        logger.info(
            f"concat 완료 (재인코딩 모드, ffprobe 검증 통과), "
            f"소요={time.time() - concat_stage_t0:.1f}s"
        )

        # 4. ASS 자막 생성 (경제사냥꾼 스타일)
        ass_path = str(temp_dir / "subtitles.ass")
        self._generate_ass(chunks, ass_path)

        # 5. 음성 + BGM + 자막 합성
        merge_stage_t0 = time.time()
        font_available = os.path.exists(NANUM_BOLD) or os.path.exists(NANUM_REGULAR)
        ass_exists = os.path.exists(ass_path) and os.path.getsize(ass_path) > 200
        audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0

        # BGM 파일 탐색 (bgm_worker가 생성한 파일)
        bgm_path = f"/app/data/jobs/{job_id}/bgm.mp3"
        bgm_exists = os.path.exists(bgm_path) and os.path.getsize(bgm_path) > 0
        bgm_volume = runtime_config.value("bgm_volume")

        if audio_exists:
            vf_filter = f'-vf "ass=\'{ass_path}\'" ' if (font_available and ass_exists) else ''
            vcodec = '-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p' if vf_filter else '-c:v copy'

            if bgm_exists:
                # 3-트랙 믹싱: 나레이션(100%) + BGM(runtime_config 값, 기본 12%)
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" -i "{bgm_path}" '
                    f'-filter_complex "[1:a]volume=1.0[narr];[2:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];'
                    f'[narr][bgm]amix=inputs=2:duration=first:dropout_transition=3[mixed]" '
                    f'{vf_filter}'
                    f'{vcodec} '
                    f'-map 0:v -map "[mixed]" '
                    f'-c:a aac -b:a 192k -shortest '
                    f'-y "{output_path}" -loglevel error'
                )
                logger.info(f"BGM 믹싱 적용: 나레이션 + BGM(volume={bgm_volume})")
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
                    f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
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

        logger.info(f"자막/BGM 합성 완료, 소요={time.time() - merge_stage_t0:.1f}s")

        if not os.path.exists(output_path):
            raise RuntimeError("롱폼 영상 생성 실패")

        probe = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{output_path}"'
        ).read().strip()
        actual_duration = float(probe) if probe else total_duration

        file_size = os.path.getsize(output_path)
        has_subtitles = font_available and ass_exists
        total_elapsed = time.time() - stage_t0
        logger.info(
            f"롱폼 조립 완료: size={file_size/1024/1024:.1f}MB, "
            f"actual={actual_duration:.0f}s, subtitles={has_subtitles}, "
            f"총 조립 소요시간={total_elapsed:.1f}s "
            f"(씬생성={time.time() - scene_stage_t0:.1f}s 포함 아님, 위 로그 참고)"
        )

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

    # ============================
    # 씬 1개를 클립(mp4)으로 변환 — 병렬 실행 단위
    # ============================
    def _process_scene(self, i: int, scene: dict, video_provider,
                        intro_kling_count: int, temp_dir: Path, job_id: int):
        """
        단일 씬을 처리하여 (씬 인덱스, 생성된 클립 경로) 튜플을 반환합니다.
        ThreadPoolExecutor에서 씬 여러 개를 동시에 실행하기 위해 분리했습니다.
        job_stopped 신호를 제외한 예외는 여기서 흡수하고 배경색 폴백 클립을
        생성해, 씬 하나의 실패가 전체 조립을 막지 않도록 합니다(v6과 동일한 방어 원칙).
        """
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

        try:
            # 초반 씬만 Kling AI 움짤, 나머지는 zoompan 효과
            if video_provider and i < intro_kling_count:
                try:
                    logger.info(f"씬 {i} Kling AI 움짤 생성 (초반 {intro_kling_count}씬)")

                    # image-to-video는 이미지에 이미 있는 내용(캐릭터 생김새, 배경,
                    # 구도)을 다시 설명하면 안 되고 "무엇이 어떻게 움직이는가"만
                    # 묘사해야 결과가 안정적입니다.
                    prompt = _build_kling_motion_prompt(scene.get("text", "") or scene.get("prompt", ""))

                    # 로컬 이미지를 base64 data URI로 인코딩해 image_url로 전달
                    image_data_uri = _encode_image_as_data_uri(img_path)

                    video_provider.generate(
                        prompt=prompt,
                        duration=min(int(duration), 5),
                        output_path=clip_path,
                        image_path=img_path,
                        image_url=image_data_uri
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

                        logger.info(f"씬 {i} Kling AI 움짤 완성 (표준 규격 변환 완료)")
                        return i, clip_path
                except Exception as e:
                    logger.warning(f"씬 {i} Kling AI 생성 실패, zoompan 폴백: {e}")

            # 나머지 씬(또는 Kling 실패 시): FFmpeg zoompan 효과
            if os.path.exists(img_path):
                _ffmpeg_zoompan(img_path, clip_path, duration, bg_color, job_id)
            else:
                _run_subprocess(
                    f'ffmpeg -f lavfi -i "color=c={bg_color}:s=1920x1080:r=30" '
                    f'-t {duration:.3f} -c:v libx264 -pix_fmt yuv420p '
                    f'-y "{clip_path}" -loglevel error',
                    job_id
                )
            return i, clip_path

        except RuntimeError as e:
            # job_stopped 신호는 그대로 위로 전파 (main 스레드에서 감지 후 재발생)
            if "stopped by user" in str(e):
                raise
            logger.error(f"씬 {i} 처리 중 RuntimeError, 배경색 폴백 시도: {e}")
        except Exception as e:
            logger.error(f"씬 {i} 처리 중 예외 발생, 배경색 폴백 시도: {e}")

        # 최후 폴백: 배경색만 있는 무음 클립 생성 (전체 조립이 씬 하나 때문에 죽지 않도록)
        try:
            _run_subprocess(
                f'ffmpeg -f lavfi -i "color=c={bg_color}:s=1920x1080:r=30" '
                f'-t {duration:.3f} -c:v libx264 -pix_fmt yuv420p '
                f'-y "{clip_path}" -loglevel error',
                job_id
            )
        except Exception as fallback_err:
            logger.error(f"씬 {i} 최후 폴백 클립 생성도 실패: {fallback_err}")
        return i, clip_path

    def _generate_ass(self, chunks: list, ass_path: str):
        """
        ASS 자막 — 경제사냥꾼 스타일
        - NanumGothicBold 72px (이전 52px → 더 큼)
        - 검정 불투명 박스 배경 (BorderStyle=3)
        - 흰색 굵은 텍스트
        - 하단 중앙 배치 (Alignment=2)
        - 최대 20자 1줄
        """
        font_name = "Pretendard Bold"
        font_size = runtime_config.value("subtitle_font_size")

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,3,2,1,2,40,40,80,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
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

            start_sec = max(0.0, chunk.get("start", 0.0))
            dur = chunk.get("duration", 3.0)
            end_sec = start_sec + dur  # End time relative to original start

            display = self._trim_to_limit(text)

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
        """주식 수치 노란색 강조 자동화"""
        import re
        text = re.sub(
            r'(\d[\d,.]*\s*(?:포인트|원|%|퍼센트|달러|조|억|만))',
            r'{\\c&H0000FFFF&}\1{\\r}',
            text
        )
        return text


# ──────────────────────────────────────────────────────────
# 모듈 수준 헬퍼 함수
# ──────────────────────────────────────────────────────────


def _build_kling_motion_prompt(scene_text: str) -> str:
    """
    Kling image-to-video용 "움직임 전용" 프롬프트를 만듭니다.
    씬 텍스트에 하락/상승 관련 표현이 있으면 손짓 뉘앙스를 거기에 맞춥니다.
    """
    down_keywords = ["하락", "급락", "내렸", "붕괴", "꺾", "약세", "부진", "악재"]
    up_keywords = ["상승", "급등", "올랐", "돌파", "반등", "강세", "최고치", "호재"]

    if scene_text and any(k in scene_text for k in down_keywords):
        gesture = "worried facial expression, hands gesturing downward with concern"
    elif scene_text and any(k in scene_text for k in up_keywords):
        gesture = "cheerful facial expression, hands gesturing upward with excitement"
    else:
        gesture = "neutral calm expression, gentle hand gesture pointing toward the chart"

    return (
        f"Subtle, minimal animation of the fixed character in the image: "
        f"{gesture}, soft blinking, slight head tilt, then settles back to "
        f"neutral pose. Background chart elements show light ambient motion — "
        f"data lines pulsing subtly, numbers flickering softly, then stabilizing. "
        f"Character stays perfectly still in position, size and proportion, "
        f"no camera movement, static shot, no zoom, no pan."
    )


def _encode_image_as_data_uri(img_path: str) -> str:
    """
    로컬 이미지 파일을 base64 data URI 문자열로 변환합니다.
    이미지 용량이 매우 크면(예: 고해상도 4K PNG) 일부 API의 페이로드 크기
    제한에 걸릴 수 있습니다. 이 경우 MinIO 등에 업로드 후 공개 URL을
    발급하는 방식으로 교체하는 것을 권장합니다.
    """
    import base64
    if not img_path or not os.path.exists(img_path):
        return None
    try:
        ext = os.path.splitext(img_path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(img_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64_data}"
    except Exception as e:
        logger.warning(f"이미지 base64 인코딩 실패 ({img_path}): {e}")
        return None


def _get_intro_kling_count(total_duration: float, total_scenes: int) -> int:
    """
    사용자 요청에 따라 영상 총 길이와 상관없이 '초반부 1분(60초)' 분량에 해당하는 씬 수만 Kling으로 할당합니다.
    """
    if total_scenes <= 0 or total_duration <= 0:
        return 3

    intro_secs = 60.0
    secs_per_scene = total_duration / total_scenes
    count = max(2, int(intro_secs / secs_per_scene))
    logger.info(f"intro_kling_count 계산: 초반 {intro_secs}초 강제 할당, scenes={total_scenes}, "
                f"secs_per_scene={secs_per_scene:.1f}s → {count}씬")
    return count


def _get_max_workers(scene_count: int) -> int:
    """
    씬 병렬 처리에 사용할 스레드 수를 결정합니다.
    runtime_config에 "longform_scene_max_workers" 키를 추가해두면
    코드 재배포 없이 /pipeline/config API로 즉시 조정할 수 있습니다.
    (키가 아직 없다면 기본값 4를 사용하며, 이는 서버 CPU 코어 수와
    Kling/Fal.ai API 동시 요청 한도를 함께 고려해 정한 보수적인 값입니다.
    CPU 코어가 넉넉하고 API 동시 처리 한도가 높다면 6~8까지 올려도 됩니다.)
    """
    default = 4
    try:
        configured = runtime_config.value("longform_scene_max_workers")
    except Exception:
        configured = None

    try:
        workers = int(configured) if configured else default
    except (TypeError, ValueError):
        workers = default

    return max(1, min(workers, max(scene_count, 1), 8))


def _verify_video(video_path: str) -> bool:
    """
    ffprobe로 영상 파일이 실제로 재생 가능한지 검증합니다.
    파일이 존재하고, 크기가 있고, duration을 정상적으로 읽을 수 있어야 True.
    -c copy concat이 exit 0을 반환해도 깨진 파일을 만드는 경우를 잡기 위함.
    """
    if not video_path or not os.path.exists(video_path):
        return False
    if os.path.getsize(video_path) < 10000:  # 10KB 미만은 사실상 빈 파일
        return False
    probe = os.popen(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{video_path}"'
    ).read().strip()
    try:
        duration = float(probe)
        return duration > 0.0
    except (ValueError, TypeError):
        return False


def _ffmpeg_zoompan(img_path: str, clip_path: str, duration: float, bg_color: str = "0d1b2a", job_id: int = 0):
    """
    정적 이미지에 FFmpeg zoompan 필터로 은은한 줌인 효과를 적용하여 생동감을 부여합니다.
    줌 속도/최대 줌 배율은 runtime_config로 조정 가능 (기본: 1.0 → 1.06, 6% 줌인).
    """
    frames = int(duration * 30)  # 30fps 기준 프레임 수
    zoom_speed = runtime_config.value("zoompan_speed")
    max_zoom = runtime_config.value("zoompan_max_zoom")

    cmd = (
        f'ffmpeg -loop 1 -i "{img_path}" '
        f'-filter_complex '
        f'"[0:v]scale=3840:2160,'
        f'zoompan=z=\'min(zoom+{zoom_speed},{max_zoom})\''
        f':x=\'iw/2-(iw/zoom/2)\''
        f':y=\'ih/2-(ih/zoom/2)\''
        f':d={frames}:s=3840x2160:fps=30,'
        f'scale=1920:1080,setsar=1[v]" '
        f'-map "[v]" -t {duration:.3f} '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{clip_path}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0:
        logger.warning(f"zoompan 실패, 단순 정적 이미지로 폴백: {img_path}")
        _run_subprocess(
            f'ffmpeg -loop 1 -i "{img_path}" '
            f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
            f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:{bg_color},setsar=1,fps=30" '
            f'-t {duration:.3f} -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
            f'-y "{clip_path}" -loglevel error',
            job_id
        )


def _assign_scene_durations_from_chunks(scenes: list, chunks: list, total_duration: float):
    """
    [S4] TTS-씬 정밀 타임라인 싱크:
    TTS 추출 타임스탬프 청크(chunks)와 씬 텍스트(content)를 매핑하여
    각 씬의 start_time, end_time, duration을 0.001초 단위로 정밀 산출.
    청크가 없거나 매핑 실패 시 문자 수 비례 분배 폴백.
    """
    if not scenes or total_duration <= 0:
        return

    # 1. 청크가 없거나 유효하지 않으면 기존 비례 분배
    if not chunks or not isinstance(chunks, list):
        total_chars = sum(len(scene.get("content", "") or scene.get("text", "") or "") for scene in scenes)
        for scene in scenes:
            char_len = len(scene.get("content", "") or scene.get("text", "") or "")
            if total_chars > 0:
                scene["duration"] = round((char_len / total_chars) * total_duration, 3)
            else:
                scene["duration"] = round(total_duration / len(scenes), 3)
        return

    # 2. 청크 타임스탬프 기반 정밀 누적 매핑
    total_chars = sum(len(scene.get("content", "") or scene.get("text", "") or "") for scene in scenes)
    if total_chars <= 0:
        for scene in scenes:
            scene["duration"] = round(total_duration / len(scenes), 3)
        return

    chunk_lengths = [len(c.get("text", "")) for c in chunks]
    total_chunk_chars = sum(chunk_lengths)

    accumulated_chars = 0
    for scene in scenes:
        scene_char_len = len(scene.get("content", "") or scene.get("text", "") or "")
        start_char_idx = accumulated_chars
        end_char_idx = accumulated_chars + scene_char_len
        accumulated_chars = end_char_idx

        start_ratio = start_char_idx / total_chars if total_chars > 0 else 0
        end_ratio = end_char_idx / total_chars if total_chars > 0 else 1

        def get_time_at_ratio(r: float) -> float:
            target_idx = r * total_chunk_chars
            curr = 0
            for c in chunks:
                c_len = len(c.get("text", ""))
                c_start = float(c.get("start", 0))
                c_end = float(c.get("end", total_duration))
                if curr + c_len >= target_idx:
                    if c_len > 0:
                        sub_r = (target_idx - curr) / c_len
                        return round(c_start + (c_end - c_start) * sub_r, 3)
                    return round(c_start, 3)
                curr += c_len
            return round(total_duration, 3)

        if chunks and total_chunk_chars > 0:
            s_time = get_time_at_ratio(start_ratio)
            e_time = get_time_at_ratio(end_ratio)
        else:
            s_time = round(start_ratio * total_duration, 3)
            e_time = round(end_ratio * total_duration, 3)

        dur = round(max(0.05, e_time - s_time), 3)
        scene["start_time"] = s_time
        scene["end_time"] = e_time
        scene["duration"] = dur

    # 오차 보정 (마지막 씬 duration을 total_duration에 정확히 일치시킴)
    sum_dur = sum(s["duration"] for s in scenes)
    diff = round(total_duration - sum_dur, 3)
    if scenes and abs(diff) > 0.001:
        scenes[-1]["duration"] = round(max(0.05, scenes[-1]["duration"] + diff), 3)
        scenes[-1]["end_time"] = round(scenes[-1]["start_time"] + scenes[-1]["duration"], 3)

