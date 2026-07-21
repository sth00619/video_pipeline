"""
Phase 3-5 v7 — 롱폼 조립 (병렬 처리 + 인코딩 패스 축소)

v6 대비 변경점 (조립 시간 단축 목적):
  1. 씬별 클립 생성(Fal/Kling AI 움짤 / 정지 이미지 렌더)을 ThreadPoolExecutor로
     병렬 처리. 기존에는 씬을 하나씩 순차로 처리해서 총 시간이
     "씬 개수 × 씬당 처리시간"으로 선형 증가했음. Kling API 호출은
     네트워크 I/O 대기(최대 180초 폴링)와 정지 이미지 인코딩을 병렬화해
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
import hashlib
import math
import logging
import subprocess
import concurrent.futures
import shutil
from pathlib import Path
from app.utils.process_manager import register_process, unregister_process, is_job_stopped, stop_job_processes
from app import runtime_config
from app.utils.quality_gate import assess_images, assess_subtitles, persist_quality_report
from app.utils.art_direction import assess_art_diversity
from app.utils.fal_billing import get_fal_credit_status
from app.utils.stock_overlay import Anchor, IndexData, Market, overlay_filter, render_index_card
from app.utils.market_charts import render_market_chart
from app.utils.data_surface_locator import locate_data_surface
from app.utils.budget import load_preflight, record_cost
from app.utils.intro_motion import select_intro_motion_scene_indices
from app.utils.output_qc import build_output_qc_report
from app.services.kling_prompt_builder import build_kling_motion_prompt
from app.services.bubble_overlay import write_speech_bubble_overlay
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Final-frame editorial policy. Verified market charts remain enabled, while
# floating index cards and generated speech bubbles are intentionally omitted.
# Bottom ASS subtitles are assembled separately and are unaffected.
RENDER_VERIFIED_INDEX_CARDS = False
RENDER_SPEECH_BUBBLES = False
OVERLAY_POLICY_VERSION = 3

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


def _probe_duration(media_path: str) -> float:
    """조립 단계가 추정값이 아닌 실제 미디어 길이를 사용하도록 한다."""
    if not media_path or not os.path.exists(media_path):
        return 0.0
    raw = os.popen(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{media_path}"'
    ).read().strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


class LongformWorker:

    def _resolve_clip_count(self, budget_remaining_krw: int, requested_max: int) -> int:
        usd_krw = float(runtime_config.value("usd_krw") or 1400.0)
        kling_cost_per_clip = float(runtime_config.value("kling_cost_per_clip_usd")) * usd_krw
        candidates = sorted({max(0, requested_max), min(8, requested_max), min(5, requested_max), 1}, reverse=True)
        for count in candidates:
            if kling_cost_per_clip * count <= budget_remaining_krw * 0.25:
                # Kling이 남은 예산의 25% 이하 차지하도록 제약
                return count
        return 0

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
        result_cache_path = job_dir / "result.json"

        # A Temporal retry can arrive after FFmpeg finished but before Spring
        # received the HTTP response (for example during a container restart).
        # Reuse that verified final artifact instead of starting Fal/Kling or
        # re-encoding the same job a second time.  Include source file state so
        # an explicit scene/TTS regeneration correctly invalidates the cache.
        def source_state(path: str) -> dict:
            try:
                stat = os.stat(path)
                return {"path": path, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            except OSError:
                return {"path": path, "missing": True}

        assembly_fingerprint = hashlib.sha256(json.dumps({
            "assembly_contract": "integrated-data-motion-v5",
            "tts": tts_meta_json,
            "scenes": scenes_meta_json,
            "gifs": gifs_meta_json,
            "audio": source_state(audio_path),
            "images": [source_state(str(scene.get("image_path", ""))) for scene in scenes],
            "motion_policy": {
                "enabled": bool(runtime_config.value("intro_motion_enabled")),
                "clip_count": int(runtime_config.value("intro_motion_clip_count")),
                "clip_seconds": int(runtime_config.value("intro_motion_clip_seconds")),
                "manual_values": [scene.get("use_kling") for scene in scenes],
            },
            "overlay_policy": {
                "version": OVERLAY_POLICY_VERSION,
                "verified_index_cards": RENDER_VERIFIED_INDEX_CARDS,
                "speech_bubbles": RENDER_SPEECH_BUBBLES,
                "market_charts": True,
            },
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            cached = json.loads(result_cache_path.read_text(encoding="utf-8"))
            if cached.get("input_fingerprint") == assembly_fingerprint and _verify_video(output_path):
                logger.info("Reusing verified completed longform result for job %s", job_id)
                return cached["result"]
        except (OSError, ValueError, KeyError, TypeError):
            pass

        # Do not assemble a partial video. Validate the full scene set before
        # starting FFmpeg; this is critical for 200+ scene jobs.
        if not scenes:
            raise RuntimeError("조립할 씬이 없습니다.")
        expected_indices = set(range(len(scenes)))
        actual_indices = [int(scene.get("index", i)) for i, scene in enumerate(scenes)]
        if set(actual_indices) != expected_indices or len(actual_indices) != len(set(actual_indices)):
            raise RuntimeError(
                f"씬 인덱스가 연속적이지 않습니다: expected=0..{len(scenes) - 1}, actual={actual_indices[:12]}"
            )
        missing_images = [
            int(scene.get("index", i))
            for i, scene in enumerate(scenes)
            if not _verify_image(scene.get("image_path", ""))
        ]
        if missing_images:
            raise RuntimeError(f"이미지 생성이 완료되지 않은 씬이 있어 조립을 중단합니다: {missing_images[:20]}")

        # [S4] 1. 씬별 재생 시간(duration) 정밀 타임라인 동적 매핑 (TTS 청크 기반)
        _assign_scene_durations_from_chunks(scenes, chunks, total_duration)

        # Editorial overlay policy: generic AI/text overlays remain disabled.
        # Only scenes carrying an explicitly verified index_data payload may
        # receive a deterministic card in _process_scene.
        data_card_count = sum(
            1 for scene in scenes
            if RENDER_VERIFIED_INDEX_CARDS
            and isinstance(scene.get("index_data"), dict)
            and scene["index_data"].get("verified") is True
        )
        market_chart_count = sum(
            1 for scene in scenes
            if isinstance(scene.get("market_chart"), dict) and scene["market_chart"].get("verified") is True
        )
        logger.info(
            f"editorial overlays: verified index cards={data_card_count}, market charts={market_chart_count} (scenes={len(scenes)})"
        )

        # Kling 비디오 프로바이더 로드 (하이브리드 모드)
        fal_status = get_fal_credit_status()
        video_provider = None
        try:
            if not fal_status["available"]:
                raise RuntimeError(f"Fal billing preflight: {fal_status['reason']}")
            from app.providers.factory import get_video_provider
            video_provider = get_video_provider()
            logger.info("하이브리드 Kling 비디오 프로바이더 로드 성공")
        except Exception as e:
            logger.warning(f"Kling 비디오 프로바이더 로드 실패 (FFmpeg 폴백 사용): {e}")

        # Contiguous opening-only Fal motion.  Later scenes are deliberately
        # static to preserve chart, caption, and numerical alignment.
        # Do not invoke any video generator unless the Fal billing preflight
        # confirms usable credit. Gemini Pro images still assemble normally.
        if not fal_status["available"] or not bool(runtime_config.value("intro_motion_enabled")):
            video_provider = None
            logger.info("Fal motion disabled: %s", "configuration" if fal_status["available"] else fal_status["reason"])
        max_clips_cap = (
            max(0, int(runtime_config.value("intro_motion_clip_count")))
            if bool(runtime_config.value("intro_motion_enabled")) else 0
        )
        if bool(runtime_config.value("intro_motion_test_mode")):
            max_clips_cap = min(max_clips_cap, 2)
            logger.info("intro_motion_test_mode is active. Kling clip count capped to 2.")

        # Dynamic budget clip auto-downgrade check
        max_budget_krw = int(runtime_config.value("max_budget_per_video_krw") or 40000)
        budget_remaining_krw = max_budget_krw
        budget_preflight = load_preflight(job_id)
        if budget_preflight:
            planned_kling = budget_preflight.get("kling_clip_count", 0)
            usd_krw = float(runtime_config.value("usd_krw") or 1400.0)
            kling_cost_per_clip_usd = float(runtime_config.value("kling_cost_per_clip_usd") or 0.35)
            buffer_multiplier = 1.0 + float(budget_preflight.get("retry_buffer_pct", 10.0)) / 100.0
            planned_kling_cost = round(planned_kling * kling_cost_per_clip_usd * usd_krw * buffer_multiplier)
            non_kling_cost = float(budget_preflight.get("estimated_cost_krw", 0)) - planned_kling_cost
            budget_remaining_krw = max(0, max_budget_krw - non_kling_cost)

        resolved_cap = self._resolve_clip_count(budget_remaining_krw, max_clips_cap)
        max_clips_cap = min(max_clips_cap, resolved_cap)
        logger.info(f"Budget auto-downgrade check: remaining={budget_remaining_krw} -> cap={max_clips_cap}")

        if budget_preflight:
            max_clips_cap = min(max_clips_cap, max(0, int(budget_preflight.get("kling_clip_count", max_clips_cap))))
            logger.info("Budget preflight applies Fal motion cap=%s, estimate=₩%s", max_clips_cap, budget_preflight.get("estimated_cost_krw"))

        max_clips_cap = _cap_intro_motion_for_short_video(total_duration, max_clips_cap)

        intro_kling_indices, intro_motion_target, intro_motion_actual = _select_intro_kling_scenes(
            scenes, total_duration, max_clips_cap
        )
        logger.info(
            "Opening Fal motion plan: target=%.1fs, actual=%.1fs, scenes=%s/%s, indices=%s",
            intro_motion_target, intro_motion_actual, len(intro_kling_indices), len(scenes),
            sorted(intro_kling_indices),
        )
        # If the editor has selected one or more scenes, use exactly those;
        # otherwise retain the safe automatic intro selection. Both paths are
        # capped to the configured opening-motion budget.
        # Java DTOs serialize optional Boolean fields as explicit null.  A
        # null is not an editor choice and must not disable the automatic
        # opening-motion plan for every scene.
        has_manual_kling_selection = _has_manual_kling_selection(scenes)

        # ── 2. 씬별 클립 생성 (병렬 처리) ──────────────────────────
        scene_stage_t0 = time.time()
        max_workers = _get_max_workers(len(scenes))
        logger.info(f"씬 클립 생성 병렬 처리 시작: max_workers={max_workers}")

        clip_paths_map: dict[int, str] = {}
        clip_modes: dict[int, str] = {}
        clip_failures: dict[int, str] = {}
        stopped_error = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._process_scene, i, scene, video_provider,
                    i in intro_kling_indices and (
                        bool(scene.get("use_kling")) if has_manual_kling_selection else True
                    ), temp_dir, job_id
                ): i
                for i, scene in enumerate(scenes)
            }
            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                try:
                    idx, clip_path, clip_mode, failure_reason = future.result()
                    clip_paths_map[idx] = clip_path
                    clip_modes[idx] = clip_mode
                    if failure_reason:
                        clip_failures[idx] = failure_reason
                except Exception as e:
                    stopped_error = e
                    if "stopped by user" in str(e):
                        logger.info(f"Job {job_id} 중지 감지, 나머지 씬 처리 건너뜀")
                    else:
                        # Do not deliver a final video containing silently
                        # substituted scenes. Stop active FFmpeg work and let the
                        # caller mark this job FAILED without automatic retry.
                        logger.error(f"씬 {i} 처리 오류. Job {job_id} 전체 중지: {e}")
                        stop_job_processes(job_id)
                    for pending in futures:
                        pending.cancel()
                    break

        if stopped_error is not None:
            raise stopped_error

        if set(clip_paths_map) != expected_indices:
            missing_clips = sorted(expected_indices - set(clip_paths_map))
            raise RuntimeError(f"씬 클립이 누락되어 조립을 중단합니다: {missing_clips[:20]}")
        clip_paths = [clip_paths_map[i] for i in sorted(clip_paths_map)]
        requested_motion_indices = {
            i for i in intro_kling_indices
            if not has_manual_kling_selection or bool(scenes[i].get("use_kling"))
        }
        actual_kling_count = sum(
            1 for i in requested_motion_indices if clip_modes.get(i) == "kling"
        )
        minimum_kling_count = _minimum_motion_delivery(len(requested_motion_indices))
        if actual_kling_count < minimum_kling_count:
            raise RuntimeError(
                "Fal/Kling opening-motion delivery gate failed: "
                f"requested={len(requested_motion_indices)}, actual={actual_kling_count}, "
                f"required={minimum_kling_count}, failures={json.dumps(clip_failures, ensure_ascii=False)}. "
                "Refusing to deliver a silently static video."
            )
        logger.info(
            f"씬 클립 생성 완료: {len(clip_paths)}/{len(scenes)}개 성공, "
            f"소요={time.time() - scene_stage_t0:.1f}s"
        )

        if not clip_paths:
            raise RuntimeError("씬 클립이 하나도 생성되지 않았습니다.")

        # ── 3. concat ─────────────────────────────────────────────────
        # 안전 우선: Fal 클립과 정지 이미지 클립은 타임베이스/비트레이트가
        # 미세하게 달라 -c copy가 exit 0을 반환해도 깨진 파일을 만들 수 있음.
        # → 항상 재인코딩(-c:v libx264)으로 처리해 파일 무결성을 보장.
        # (병렬 처리로 클립 생성 시간 자체가 줄었기 때문에, concat 재인코딩
        #  비용은 전체 대비 상대적으로 작아짐. 재생 불가 파일이 더 큰 손실.)
        concat_stage_t0 = time.time()
        clip_list_path = str(temp_dir / "clips.txt")
        with open(clip_list_path, "w") as f:
            for cp in clip_paths:
                # FFmpeg's concat demuxer parses Windows drive-colons as a
                # protocol unless the path uses POSIX separators and escapes
                # the drive separator.
                clip_ref = Path(cp).as_posix()
                if os.name == "nt" and len(clip_ref) > 1 and clip_ref[1] == ":":
                    clip_ref = clip_ref[0] + r"\:" + clip_ref[2:]
                f.write(f"file '{clip_ref}'\n")

        silent_video = str(temp_dir / "silent.mp4")
        clip_manifest_path = temp_dir / "clip_manifest.json"
        clip_manifest = [
            {"path": cp, "size": os.path.getsize(cp), "mtime_ns": os.stat(cp).st_mtime_ns}
            for cp in clip_paths
        ]
        can_reuse_silent = False
        try:
            previous_manifest = json.loads(clip_manifest_path.read_text(encoding="utf-8"))
            can_reuse_silent = previous_manifest == clip_manifest and _verify_video(silent_video)
        except (OSError, ValueError, TypeError):
            can_reuse_silent = False

        if can_reuse_silent:
            ret = 0
            logger.info("재생 가능한 silent.mp4와 씬 manifest를 재사용합니다.")
        else:
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
        if not can_reuse_silent:
            clip_manifest_path.write_text(json.dumps(clip_manifest, ensure_ascii=False), encoding="utf-8")

        # Kling은 5초 클립만 반환한다. 어떤 씬이 짧게 끝나도 최종 -shortest가
        # 나레이션을 자르지 않도록 마지막 프레임을 복제해 오디오 길이를 보장한다.
        audio_duration = _probe_duration(audio_path)
        target_duration = audio_duration or float(total_duration or 0.0)
        silent_duration = _probe_duration(silent_video)
        if target_duration > 0 and silent_duration + 0.05 < target_duration:
            pad_seconds = target_duration - silent_duration
            padded_video = str(temp_dir / "silent_padded.mp4")
            logger.warning(
                f"시각 트랙이 나레이션보다 짧음: video={silent_duration:.2f}s, "
                f"audio={target_duration:.2f}s. 마지막 프레임 {pad_seconds:.2f}s 패딩"
            )
            pad_ret = _run_subprocess(
                f'ffmpeg -i "{silent_video}" '
                f'-vf "tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}" '
                f'-t {target_duration:.3f} -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
                f'-an -y "{padded_video}" -loglevel error',
                job_id,
            )
            if pad_ret != 0 or not _verify_video(padded_video):
                raise RuntimeError("나레이션 길이 보정 영상 생성 실패")
            os.replace(padded_video, silent_video)

        logger.info(
            f"concat 완료 (재인코딩 모드, ffprobe 검증 통과), "
            f"소요={time.time() - concat_stage_t0:.1f}s"
        )

        # 4. ASS 자막 생성 (경제사냥꾼 스타일)
        ass_path = str(temp_dir / "subtitles.ass")
        self._generate_ass(chunks, ass_path, scenes)

        # 5. 음성 + BGM + 자막 합성
        merge_stage_t0 = time.time()
        assembly_stage_path = str(temp_dir / "final.partial.mp4")
        if os.path.exists(assembly_stage_path):
            os.remove(assembly_stage_path)
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
                    f'[narr][bgm]amix=inputs=2:duration=first:dropout_transition=3[mixed];'
                    f'[mixed]loudnorm=I=-16:LRA=11:TP=-1.5:linear=true[master]" '
                    f'{vf_filter}'
                    f'{vcodec} '
                    f'-map 0:v -map "[master]" '
                    f'-c:a aac -b:a 192k -ar 44100 -ac 2 -movflags +faststart -shortest '
                    f'-y "{assembly_stage_path}" -loglevel error'
                )
                logger.info(f"BGM 믹싱 적용: 나레이션 + BGM(volume={bgm_volume})")
            else:
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'-filter_complex "[1:a]loudnorm=I=-16:LRA=11:TP=-1.5:linear=true[master]" '
                    f'{vf_filter}'
                    f'{vcodec} '
                    f'-map 0:v -map "[master]" '
                    f'-c:a aac -b:a 192k -ar 44100 -ac 2 -movflags +faststart -shortest '
                    f'-y "{assembly_stage_path}" -loglevel error'
                )
        else:
            if font_available and ass_exists:
                merge_cmd = (
                    f'ffmpeg -i "{silent_video}" '
                    f'-vf "ass=\'{ass_path}\'" '
                    f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
                    f'-y "{assembly_stage_path}" -loglevel error'
                )
            else:
                merge_cmd = None

        if merge_cmd is None:
            shutil.copy2(silent_video, assembly_stage_path)
            ret = 0
        else:
            ret = _run_subprocess(merge_cmd, job_id)
        if ret != 0 or not _verify_video(assembly_stage_path):
            if os.path.exists(assembly_stage_path):
                os.remove(assembly_stage_path)
            logger.error("자막/BGM 합성 실패, 폴백")
            if audio_exists:
                fallback_ret = _run_subprocess(
                    f'ffmpeg -i "{silent_video}" -i "{audio_path}" '
                    f'-map 0:v -map 1:a '
                    f'-c:v copy -c:a aac -ar 44100 -ac 2 -shortest '
                    f'-y "{assembly_stage_path}" -loglevel error',
                    job_id
                )
                if fallback_ret != 0 or not _verify_video(assembly_stage_path):
                    raise RuntimeError("자막/BGM 조립 및 안전한 오디오 폴백이 모두 실패했습니다.")
            else:
                shutil.copy2(silent_video, assembly_stage_path)
                if not _verify_video(assembly_stage_path):
                    raise RuntimeError("최종 영상 임시 파일 검증에 실패했습니다.")

        if not _verify_video(assembly_stage_path):
            raise RuntimeError("최종 영상 임시 파일이 재생 가능한 상태가 아닙니다.")
        os.replace(assembly_stage_path, output_path)

        logger.info(f"자막/BGM 합성 완료, 소요={time.time() - merge_stage_t0:.1f}s")

        if not _verify_video(output_path):
            raise RuntimeError("롱폼 영상 생성 실패")

        probe = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{output_path}"'
        ).read().strip()
        actual_duration = float(probe) if probe else total_duration

        file_size = os.path.getsize(output_path)
        has_subtitles = font_available and ass_exists
        subtitle_quality = assess_subtitles(
            chunks, float(total_duration or actual_duration),
            int(runtime_config.value("subtitle_max_chars")),
        )
        visual_quality = assess_images(scenes)
        duration_delta = round(abs(actual_duration - float(total_duration or actual_duration)), 3)
        quality_report = {
            "score": min(subtitle_quality["score"], visual_quality["score"]),
            "duration_delta_seconds": duration_delta,
            "duration_ok": duration_delta <= 0.2,
            "subtitles": subtitle_quality,
            "images": visual_quality,
            "art_direction": assess_art_diversity(scenes),
            "has_subtitles": has_subtitles,
            "data_card_count": data_card_count,
            "market_chart_count": market_chart_count,
            "verified_data_cards_expected": data_card_count,
            "verified_data_cards_rendered": data_card_count,
            "verified_market_charts_expected": market_chart_count,
            "verified_market_charts_rendered": market_chart_count,
            "planned_kling_clip_count": len(requested_motion_indices),
            "kling_clip_count": actual_kling_count,
            "motion_delivery_ok": actual_kling_count >= minimum_kling_count,
        }
        output_qc = build_output_qc_report(
            job_id=job_id,
            output_path=output_path,
            audio_path=audio_path,
            tts_meta=tts_meta,
            scenes=scenes,
            expected_data_cards=data_card_count,
            rendered_data_cards=data_card_count,
            expected_market_charts=market_chart_count,
            rendered_market_charts=market_chart_count,
            planned_kling=len(requested_motion_indices),
            actual_kling=actual_kling_count,
            fal_failures=clip_failures,
        )
        quality_report["output_qc"] = output_qc
        logger.info(
            "Verified overlay delivery cards=%s/%s charts=%s/%s; output_qc=%s",
            data_card_count, data_card_count, market_chart_count, market_chart_count,
            output_qc["passed"],
        )
        persist_quality_report(job_id, "longform", quality_report)
        total_elapsed = time.time() - stage_t0
        logger.info(
            f"롱폼 조립 완료: size={file_size/1024/1024:.1f}MB, "
            f"actual={actual_duration:.0f}s, subtitles={has_subtitles}, "
            f"총 조립 소요시간={total_elapsed:.1f}s "
            f"(씬생성={time.time() - scene_stage_t0:.1f}s 포함 아님, 위 로그 참고)"
        )

        # Kling clips are billed artifacts and must survive a successful
        # assembly.  Temporal retries and QC-only reassemblies can then reuse
        # the exact motion output instead of charging Fal again.  Static clips
        # are cheap and remain disposable.
        _cleanup_scene_clips(clip_paths, clip_modes)
        if os.path.exists(silent_video):
            os.remove(silent_video)

        result = {
            "job_id": job_id,
            "video_path": output_path,
            "duration_seconds": round(actual_duration, 1),
            "scene_count": len(scenes),
            "gif_count": len(gifs),
            "data_card_count": data_card_count,
            "market_chart_count": market_chart_count,
            "planned_kling_clip_count": len(requested_motion_indices),
            "kling_clip_count": actual_kling_count,
            "has_subtitles": has_subtitles,
            "resolution": "1920x1080",
            "quality_report": quality_report,
        }
        cache_tmp = result_cache_path.with_suffix(".tmp")
        cache_tmp.write_text(
            json.dumps({"input_fingerprint": assembly_fingerprint, "result": result}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(cache_tmp, result_cache_path)
        return result

    # ============================
    # 씬 1개를 클립(mp4)으로 변환 — 병렬 실행 단위
    # ============================
    def _process_scene(self, i: int, scene: dict, video_provider,
                        use_kling: bool, temp_dir: Path, job_id: int):
        """
        단일 씬을 처리하여 (씬 인덱스, 생성된 클립 경로) 튜플을 반환합니다.
        ThreadPoolExecutor에서 씬 여러 개를 동시에 실행하기 위해 분리했습니다.
        Kling 인트로 실패는 정적 이미지로 안전하게 대체할 수 있지만, 이미지/FFmpeg
        조립 자체의 오류는 호출자에게 전파합니다. 빈 배경 씬을 몰래 넣지 않고
        작업 전체를 중지하는 정책입니다.
        """
        if is_job_stopped(job_id):
            raise RuntimeError(f"Job {job_id} stopped by user.")

        img_path = scene.get("image_path", "")
        raw_dur = scene.get("duration")
        duration = float(raw_dur) if raw_dur is not None else 15.0
        clip_path = str(temp_dir / f"clip_{i:03d}.mp4")
        if not _verify_image(img_path):
            raise RuntimeError(f"scene {i} image is missing or corrupt: {img_path}")
        # An interrupted assembly can leave a valid *static* clip behind.  It
        # must never satisfy a later request for an opening Kling scene.
        motion_requested = bool(video_provider and use_kling)
        expected_source_type = "kling" if motion_requested else "static"
        clip_fingerprint = _scene_clip_fingerprint(scene, img_path, duration, expected_source_type)
        if _can_reuse_scene_clip(
            clip_path,
            duration,
            motion_requested=motion_requested,
            expected_source_type=expected_source_type,
            expected_fingerprint=clip_fingerprint,
        ):
            logger.info("Reusing completed %s scene clip %s", expected_source_type, i)
            return i, clip_path, expected_source_type, None
        section = scene.get("section", "default")
        bg_color = {
            "intro": "1a1a2e", "background": "16213e",
            "data": "0f3460", "scenario": "1b1464",
            "action": "0d3b2e", "conclusion": "1a1a2e",
        }.get(section, "0d1b2a")

        try:
            # Only planned opening scenes use Fal image-to-video.  Every other
            # scene (including Fal failures) is rendered as a static image.
            if video_provider and use_kling:
                try:
                    logger.info(f"씬 {i} Kling AI 움짤 생성")

                    # image-to-video는 이미지에 이미 있는 내용(캐릭터 생김새, 배경,
                    # 구도)을 다시 설명하면 안 되고 "무엇이 어떻게 움직이는가"만
                    # 묘사해야 결과가 안정적입니다.
                    prompt_dict = build_kling_motion_prompt(scene.get("motion_type"))
                    prompt = prompt_dict["prompt"]
                    negative_prompt = prompt_dict["negative_prompt"]

                    motion_duration = min(
                        max(int(duration), 1),
                        max(1, min(int(runtime_config.value("intro_motion_clip_seconds")), 5)),
                    )

                    # 로컬 이미지를 Fal CDN에 업로드하고 공개 URL 확보
                    # Fal.ai v2.6 image-to-video의 start_image_url은 인터넷에서 접근 가능한
                    # https:// URL만 허용합니다. MinIO presigned URL(minio:9000)은 Docker
                    # 내부 네트워크 주소라 Fal 서버에서 접근 불가합니다.
                    start_image_url = _upload_image_for_fal(img_path)
                    if not start_image_url:
                        raise RuntimeError(f"씬 {i}: Fal CDN 이미지 업로드 실패. 정지 이미지 폴백.")

                    asset = video_provider.generate(
                        prompt=prompt,
                        duration=motion_duration,
                        output_path=clip_path,
                        image_path=img_path,
                        image_url=start_image_url,
                        negative_prompt=negative_prompt,
                        fal_only=True,
                    )
                    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 1000:
                        temp_kling = clip_path + ".temp.mp4"
                        try:
                            os.rename(clip_path, temp_kling)
                            # Kling 동작은 최대 5초만 사용하고, 나머지는 마지막
                            # 프레임을 유지한다. 따라서 긴 씬도 정확한 길이를 가진다.
                            freeze_duration = max(0.0, duration - motion_duration)
                            std_cmd = (
                                f'ffmpeg -i "{temp_kling}" -vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
                                f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,'
                                f'tpad=stop_mode=clone:stop_duration={freeze_duration:.3f}" '
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

                        if _verify_video(clip_path) and abs(_probe_duration(clip_path) - duration) <= 0.15:
                            if _requires_verified_index_card(scene) and not _requires_verified_market_chart(scene) and not _apply_verified_index_card(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} verified index card overlay failed")
                            if _requires_verified_market_chart(scene) and not _apply_verified_market_chart(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} verified market chart overlay failed")
                            if not _apply_speech_bubble_overlay(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} speech bubble overlay failed")
                            record_cost(job_id, "kling")
                            
                            # Write Kling audit params for reproducibility
                            _write_kling_audit(job_id, i, {
                                "fal_request_id": asset.meta.get("fal_request_id") if asset and asset.meta else None,
                                "prompt": prompt,
                                "negative_prompt": negative_prompt,
                                "duration": motion_duration,
                                "start_image_url_prefix": start_image_url[:80] if start_image_url else None,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                            
                            logger.info(f"씬 {i} Kling AI 움짤 완성 (표준 규격 변환 완료)")
                            _write_scene_clip_meta(clip_path, "kling", clip_fingerprint)
                            return i, clip_path, "kling", None
                        raise RuntimeError("Kling 표준화 클립 검증 실패")
                except Exception as e:
                    logger.warning(f"씬 {i} Fal 모션 생성 실패, 정지 이미지 + 크로스페이드 페이드 필터 폴백: {e}")
                    if os.path.exists(img_path):
                        try:
                            _ffmpeg_static_image_with_fade(img_path, clip_path, duration, bg_color, job_id)
                            if _requires_verified_index_card(scene) and not _requires_verified_market_chart(scene) and not _apply_verified_index_card(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} verified index card overlay failed")
                            if _requires_verified_market_chart(scene) and not _apply_verified_market_chart(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} verified market chart overlay failed")
                            if not _apply_speech_bubble_overlay(scene, clip_path, temp_dir, i, duration, job_id):
                                raise RuntimeError(f"scene {i} speech bubble overlay failed")
                            if _verify_video(clip_path):
                                logger.info(f"씬 {i} Fal 모션 실패 페이드 폴백 완료")
                                _write_scene_clip_meta(clip_path, "fal_fallback_static", clip_fingerprint)
                                return i, clip_path, "fal_fallback_static", str(e)
                        except Exception as fallback_err:
                            logger.error(f"씬 {i} 페이드 폴백 실패, 일반 정적 복구 시도: {fallback_err}")

            # 나머지 씬(또는 Kling 실패 시): 정적 이미지 효과 (흔들림 방지 및 화질 극대화)
            if os.path.exists(img_path):
                _ffmpeg_static_image(img_path, clip_path, duration, bg_color, job_id)
            else:
                raise RuntimeError(f"scene {i} image disappeared during assembly")
            if not _verify_video(clip_path):
                raise RuntimeError(f"scene {i} clip failed validation after rendering")
            if _requires_verified_index_card(scene) and not _requires_verified_market_chart(scene) and not _apply_verified_index_card(scene, clip_path, temp_dir, i, duration, job_id):
                raise RuntimeError(f"scene {i} verified index card overlay failed")
            if _requires_verified_market_chart(scene) and not _apply_verified_market_chart(scene, clip_path, temp_dir, i, duration, job_id):
                raise RuntimeError(f"scene {i} verified market chart overlay failed")
            if not _apply_speech_bubble_overlay(scene, clip_path, temp_dir, i, duration, job_id):
                raise RuntimeError(f"scene {i} speech bubble overlay failed")
            if not _verify_video(clip_path):
                raise RuntimeError(f"scene {i} clip failed validation after overlay")
            _write_scene_clip_meta(clip_path, "static", clip_fingerprint)
            return i, clip_path, "static", None

        except Exception as e:
            logger.error(f"scene {i} processing failed; aborting job: {e}")
            raise

    def _generate_ass(self, chunks: list, ass_path: str, scenes: list | None = None):
        """
        ASS 자막 — 경제사냥꾼 스타일
        - NanumGothicBold 72px (이전 52px → 더 큼)
        - 검정 불투명 박스 배경 (BorderStyle=3)
        - 흰색 굵은 텍스트
        - 하단 중앙 배치 (Alignment=2)
        - 최대 20자 1줄
        """
        # Docker 이미지에 설치된 글꼴을 명시해 환경별 폴백을 없앤다.
        # Fontconfig family name is NanumGothic; bold weight is controlled by
        # the ASS Bold field below. "NanumGothicBold" would fall back to
        # DejaVu Sans in the Docker image despite the font file being present.
        font_name = "NanumGothic"
        font_size = runtime_config.value("subtitle_font_size")
        theme = runtime_config.value("subtitle_theme")

        if theme == "knowledge":
            # 반투명 다크 바 + 흰 글자 + 금색 강조 포인트.
            style = (
                f"Style: Main,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,"
                "&H003A3122,&H88120E0B,-1,0,0,0,100,100,0,0,3,0,0,2,60,60,72,1"
            )
        else:
            # 흰 굵은 글자와 검정 외곽선. 불투명 박스 없이 장면을 살린다.
            style = (
                f"Style: Main,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,"
                "&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,2,2,50,50,78,1"
            )

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
{style}
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
        def to_ass_time(s: float) -> str:
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h}:{m:02d}:{sec:05.2f}"

        # A scene may carry subtitle_text when an editor intentionally changed
        # only what appears on screen.  Exclude the overlapping TTS chunks and
        # render that scene-level override instead; narration audio is left
        # untouched. This makes the "caption only" button safe and literal.
        overrides = []
        for scene in scenes or []:
            caption = str(scene.get("subtitle_text") or "").strip()
            if not caption:
                continue
            start = float(scene.get("start_time", scene.get("start", 0.0)) or 0.0)
            duration = float(scene.get("duration", 0.0) or 0.0)
            if duration > 0:
                overrides.append((start, start + duration, caption))

        def is_overridden_chunk(chunk: dict) -> bool:
            start = float(chunk.get("start", 0.0) or 0.0)
            end = start + float(chunk.get("duration", 0.0) or 0.0)
            midpoint = (start + end) / 2.0
            return any(override_start <= midpoint < override_end
                       for override_start, override_end, _ in overrides)

        lines = [header]
        for chunk in chunks:
            if is_overridden_chunk(chunk):
                continue
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

        for start_sec, end_sec, caption in overrides:
            display = self._trim_to_limit(caption)
            lines.append(
                f"Dialogue: 0,{to_ass_time(start_sec)},{to_ass_time(end_sec)},Main,,0,0,0,,{display}"
            )

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


CHARACTER_ACTION_MOTION = {
    "pointer_up": "the character raises the pointer prop slightly toward the existing top-right chart area, then holds steady",
    "arms_crossed": "the character keeps arms crossed with one slow concerned head tilt and minimal shoulder movement",
    "hands_open": "the character opens hands outward in one small explanatory gesture, then returns to the reference pose",
    "neutral": "the character gives one calm blink and one subtle nod",
}

EMOTION_FACIAL = {
    "neutral": "calm neutral expression",
    "highlight": "focused confident expression with a slight brow raise",
    "surprised": "eyes slightly wider and a brief open-mouth reaction",
    "worried": "worried expression with a gently furrowed brow",
    "happy": "gentle smile with a cheerful expression",
}

BACKGROUND_AMBIENT = {
    "data_overlay": "existing background chart lines pulse very softly while every number and label remains perfectly static and legible",
    "emphasis_zoom": "a very subtle background light glow appears briefly around the character without any camera movement",
    "scene_change": "a very subtle ambient light shift occurs in the background",
}


def _build_kling_motion_prompt(scene: dict) -> str:
    """Build a locked-camera, metadata-driven Fal image-to-video prompt.

    The generated image is a reference frame, not a suggestion.  Position,
    proportions, camera framing, charts, and all text/numbers are protected to
    reduce character drift and jitter before the frozen tail is appended.
    """
    action = str(scene.get("character_action") or "neutral")
    emotion = str(scene.get("emotion_tag") or "neutral")
    marker = str(scene.get("edit_marker") or "scene_change")
    body_motion = CHARACTER_ACTION_MOTION.get(action, CHARACTER_ACTION_MOTION["neutral"])
    face = EMOTION_FACIAL.get(emotion, EMOTION_FACIAL["neutral"])
    ambient = BACKGROUND_AMBIENT.get(marker, BACKGROUND_AMBIENT["scene_change"])

    return (
        "Minimal, subtle animation of the fixed gold coin character in the reference image. "
        f"{face}. {body_motion}. {ambient}. "
        "The character's body position, size, proportions, outline, and pose remain identical to the reference image. "
        "Absolutely no camera motion, no zoom, no pan, no dolly, no shake, and no transition. "
        "Static locked-off camera. No morphing of facial features. No changes to clothing, colors, "
        "background composition, charts, text, or numerical values. Duration 5 seconds, seamless-loop friendly, "
        "and end in the neutral reference pose."
    )


def _upload_image_for_fal(img_path: str) -> str | None:
    """
    로컬 이미지를 Fal.ai 자체 CDN 스토리지에 업로드하고 공개 URL을 반환합니다.

    [왜 fal_client.upload_file인가]
    - Fal.ai image-to-video는 start_image_url로 인터넷에서 접근 가능한 URL 필요
    - MinIO presigned URL은 http://minio:9000/... 형태 (Docker 내부 네트워크 호스트명)
      → Fal.ai 서버(외부 인터넷)에서 접근 불가능 → 이미지 로드 실패 → 생성 실패
    - fal_client.upload_file()은 파일을 Fal CDN에 올리고 공개 https:// URL을 반환
      → Fal 서버에서 직접 접근 가능한 유일하게 신뢰할 수 있는 경로

    [FAL_KEY 설정]
    fal_client는 FAL_KEY 환경변수를 자동으로 읽습니다 (Authorization: Key <값> 헤더).
    requirements.txt에 fal-client>=0.5.0 추가됨.
    """
    if not img_path or not os.path.exists(img_path):
        logger.warning(f"이미지 파일 없음, Fal 업로드 스킵: {img_path}")
        return None
    try:
        import fal_client  # fal-client>=0.5.0 (requirements.txt)
        url = fal_client.upload_file(img_path)
        logger.info(f"Fal CDN 업로드 완료: {url[:80]}...")
        return url
    except Exception as e:
        logger.warning(f"Fal CDN 이미지 업로드 실패 ({img_path}): {e}")
        return None



def _select_intro_kling_scenes(
    scenes: list[dict], total_duration: float, max_clips_cap: int
) -> tuple[set[int], float, float]:
    """Allocate Fal clips to a contiguous opening window in real seconds."""
    return select_intro_motion_scene_indices(
        scenes,
        total_duration,
        short_seconds=float(runtime_config.value("intro_motion_seconds_short")),
        long_seconds=float(runtime_config.value("intro_motion_seconds_long")),
        short_threshold=float(runtime_config.value("intro_motion_short_threshold")),
        max_clips=max(0, int(max_clips_cap)),
        clip_seconds=float(runtime_config.value("intro_motion_clip_seconds")),
    )


def _cap_intro_motion_for_short_video(total_duration: float, max_clips_cap: int) -> int:
    """Keep a one-minute proof visibly animated without spending on 40 seconds."""
    cap = max(0, int(max_clips_cap))
    if 0 < float(total_duration) <= 90:
        capped = min(cap, 4)
        if capped != cap:
            logger.info(
                "Short-video Fal policy: duration=%.1fs, clip cap reduced %s -> %s",
                total_duration, cap, capped,
            )
        return capped
    return cap


def _get_max_workers(scene_count: int) -> int:
    """
    씬 병렬 처리에 사용할 스레드 수를 결정합니다.
    runtime_config에 "longform_scene_max_workers" 키를 추가해두면
    코드 재배포 없이 /pipeline/config API로 즉시 조정할 수 있습니다.
    (키가 아직 없다면 기본값 4를 사용하며, 이는 서버 CPU 코어 수와
    Kling/Fal.ai API 동시 요청 한도를 함께 고려해 정한 보수적인 값입니다.
    CPU 코어가 넉넉하고 API 동시 처리 한도가 높다면 6~8까지 올려도 됩니다.)
    """
    default = 6
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
    # Very short valid clips can be smaller than 10KB; ffprobe duration is
    # the authoritative decodability check, with 1KB as the truncation floor.
    if os.path.getsize(video_path) < 1000:
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


def _can_reuse_scene_clip(
    clip_path: str,
    duration: float,
    *,
    motion_requested: bool,
    expected_source_type: str | None = None,
    expected_fingerprint: str | None = None,
) -> bool:
    """Reuse only a clip whose sidecar proves its origin and exact inputs."""
    if expected_source_type is None or expected_fingerprint is None:
        return False
    meta_path = Path(f"{clip_path}.meta.json")
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if metadata.get("source_type") != expected_source_type:
        return False
    if metadata.get("input_fingerprint") != expected_fingerprint:
        return False
    return _verify_video(clip_path) and abs(_probe_duration(clip_path) - duration) <= 0.15


def _scene_clip_fingerprint(
    scene: dict, image_path: str, duration: float, source_type: str
) -> str:
    """Hash every input that can change a rendered scene clip."""
    try:
        stat = os.stat(image_path)
        image_identity = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    except OSError:
        image_identity = {"size": None, "mtime_ns": None}
    contract = {
        "schema": 3,
        "source_type": source_type,
        "duration": round(float(duration), 3),
        "image": image_identity,
        "motion_type": scene.get("motion_type"),
        "market_chart": scene.get("market_chart"),
        "index_data": scene.get("index_data"),
        "bubble_text": scene.get("bubble_text"),
        "subtitle_text": scene.get("subtitle_text"),
        "overlay_policy": {
            "version": OVERLAY_POLICY_VERSION,
            "verified_index_cards": RENDER_VERIFIED_INDEX_CARDS,
            "speech_bubbles": RENDER_SPEECH_BUBBLES,
            "market_charts": True,
        },
    }
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cleanup_scene_clips(clip_paths: list[str], clip_modes: dict[int, str]) -> None:
    """Delete reproducible static clips, retaining every billed Kling clip."""
    for index, clip_path in enumerate(clip_paths):
        if clip_modes.get(index) == "kling":
            continue
        if os.path.exists(clip_path):
            os.remove(clip_path)


def _write_scene_clip_meta(clip_path: str, source_type: str, fingerprint: str) -> None:
    meta_path = Path(f"{clip_path}.meta.json")
    temp_path = meta_path.with_suffix(meta_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(
            {
                "source_type": source_type,
                "input_fingerprint": fingerprint,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temp_path, meta_path)


def _has_manual_kling_selection(scenes: list[dict]) -> bool:
    """Treat only an explicit boolean as an editor motion selection."""
    return any(scene.get("use_kling") is not None for scene in scenes)


def _minimum_motion_delivery(requested_count: int) -> int:
    """Require at least 75% of the planned opening motion before delivery."""
    if requested_count <= 0:
        return 0
    return max(1, math.ceil(requested_count * 0.75))


def _verify_image(image_path: str) -> bool:
    """Return true only for a non-trivial, decodable image file."""
    if not image_path or not os.path.exists(image_path):
        return False
    try:
        # Tiny files are usually empty/truncated; valid flat-color PNGs from
        # the mock provider can legitimately be below the image worker's
        # 15KB cache threshold, so assembly uses a lower safety floor.
        if os.path.getsize(image_path) <= 1000:
            return False
        from PIL import Image
        with Image.open(image_path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def _write_kling_audit(job_id: int, scene_idx: int, params: dict):
    audit_file = Path(f"/app/data/jobs/{job_id}/kling_audit.jsonl")
    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"scene_idx": scene_idx, **params}, ensure_ascii=False)
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as ex:
        logger.warning(f"Failed to write Kling audit log: {ex}")


def _ffmpeg_static_image_with_fade(img_path: str, clip_path: str, duration: float, bg_color: str = "0d1b2a", job_id: int = 0):
    """
    정적 이미지를 페이드 인/아웃(0.5초) 효과를 추가하여 FFmpeg로 고화질 비디오 클립으로 인코딩합니다.
    """
    total_frames = int(duration * 30)
    fade_out_start = max(0, total_frames - 15)
    cmd = (
        f'ffmpeg -loop 1 -i "{img_path}" '
        f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
        f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:{bg_color},setsar=1,fps=30,'
        f'fade=in:0:15,fade=out:{fade_out_start}:15" '
        f'-t {duration:.3f} -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{clip_path}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0 or not _verify_video(clip_path):
        raise RuntimeError(f"static image clip with fade render failed: {img_path}")


def _ffmpeg_static_image(img_path: str, clip_path: str, duration: float, bg_color: str = "0d1b2a", job_id: int = 0):
    """
    정적 이미지를 FFmpeg로 흔들림 없이(static) 고화질 비디오 클립으로 인코딩합니다.
    """
    cmd = (
        f'ffmpeg -loop 1 -i "{img_path}" '
        f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
        f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:{bg_color},setsar=1,fps=30" '
        f'-t {duration:.3f} -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{clip_path}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0 or not _verify_video(clip_path):
        raise RuntimeError(f"static image clip render failed: {img_path}")


def _requires_verified_index_card(scene: dict) -> bool:
    if not RENDER_VERIFIED_INDEX_CARDS:
        return False
    payload = scene.get("index_data") or scene.get("overlay_data")
    return isinstance(payload, dict) and payload.get("verified") is True


def _apply_verified_index_card(scene: dict, clip_path: str, temp_dir: Path, index: int, duration: float, job_id: int) -> bool:
    """Overlay a card only when a scene carries explicitly verified values."""
    payload = scene.get("index_data") or scene.get("overlay_data")
    if not isinstance(payload, dict) or payload.get("verified") is not True:
        return False
    try:
        source = str(payload.get("source") or payload.get("data_source") or "").strip()
        if not source:
            return False
        data = IndexData(
            name=str(payload["name"]),
            value=float(payload["value"]),
            change=float(payload["change"]),
            change_pct=float(payload["change_pct"]),
            market=Market(str(payload.get("market", "kr")).lower()),
        )
        card_path = str(temp_dir / f"index_card_{index:03d}.png")
        render_index_card(data, card_path, scale=2)
        placement = scene.get("overlay_placement") or {}
        mode = str(placement.get("mode") or "anchor").lower()
        margin = max(0, int(placement.get("margin", 40)))
        xy = None
        anchor = Anchor.TOP_RIGHT
        if mode == "pixel":
            xy = (int(placement.get("x", 0)), int(placement.get("y", 0)))
        else:
            anchor = Anchor(str(placement.get("anchor", "top_right")).lower())
        filt = overlay_filter(1920, 1080, 0, 0, anchor=anchor, margin=margin, xy=xy)
        staged = clip_path + ".index-card.mp4"
        cmd = (
            f'ffmpeg -i "{clip_path}" -loop 1 -i "{card_path}" '
            f'-filter_complex "[0:v][1:v]{filt}:format=auto[v]" '
            f'-map "[v]" -t {duration:.3f} -an -c:v libx264 -preset fast -crf 18 '
            f'-pix_fmt yuv420p -y "{staged}" -loglevel error'
        )
        ret = _run_subprocess(cmd, job_id)
        if ret != 0 or not _verify_video(staged):
            if os.path.exists(staged):
                os.remove(staged)
            return False
        os.replace(staged, clip_path)
        logger.info("scene %s verified index card overlay applied (source=%s, mode=%s)", index, source, mode)
        return True
    except (KeyError, TypeError, ValueError, OSError) as exc:
        logger.warning("scene %s verified index card overlay skipped: %s", index, exc)
        return False


def _requires_verified_market_chart(scene: dict) -> bool:
    payload = scene.get("market_chart")
    return (
        isinstance(payload, dict)
        and payload.get("verified") is True
        and isinstance(payload.get("points"), list)
        and len(payload["points"]) >= 5
        and bool(payload.get("source"))
    )


def _apply_verified_market_chart(scene: dict, clip_path: str, temp_dir: Path, index: int, duration: float, job_id: int) -> bool:
    """Render and overlay a collected price series; never ask the image model for a factual chart."""
    payload = scene.get("market_chart")
    if not _requires_verified_market_chart(scene):
        return False
    chart_path = str(temp_dir / f"market_chart_{index:03d}.png")
    try:
        resolved_surface = _resolve_market_chart_surface(
            (scene.get("art_direction") or {}).get("data_surface"),
            str(scene.get("image_path") or scene.get("path") or ""),
        )
        render_payload = dict(payload)
        render_payload["render_surface"] = {
            "width": resolved_surface["width"],
            "height": resolved_surface["height"],
        }
        if not render_market_chart(render_payload, chart_path):
            logger.warning("scene %s market chart renderer returned no valid file", index)
            return False
        if not os.path.exists(chart_path) or os.path.getsize(chart_path) < 4_000:
            return False
        ok = _apply_market_chart_overlay(
            clip_path,
            chart_path,
            duration,
            job_id,
            resolved_surface,
        )
        if ok:
            logger.info(
                "scene %s verified market chart overlay applied (series=%s source=%s)",
                index, payload.get("series_key"), payload.get("source"),
            )
        return ok
    except (TypeError, ValueError, OSError) as exc:
        logger.warning("scene %s verified market chart overlay failed: %s", index, exc)
        return False


def _apply_data_card_overlay(clip_path: str, card_path: str, duration: float, job_id: int) -> bool:
    """Place deterministic Korean data-card text above the subtitle-safe area."""
    if not card_path or not os.path.exists(card_path) or not _verify_video(clip_path):
        return False
    staged = clip_path + ".card.mp4"
    cmd = (
        f'ffmpeg -i "{clip_path}" -loop 1 -i "{card_path}" '
        f'-filter_complex "[0:v][1:v]overlay=70:55:format=auto[v]" '
        f'-map "[v]" -t {duration:.3f} -an '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{staged}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0 or not _verify_video(staged):
        if os.path.exists(staged):
            os.remove(staged)
        return False
    os.replace(staged, clip_path)
    return True


def _resolve_market_chart_surface(surface: dict | None, source_image_path: str = "") -> dict[str, int]:
    """Return the actual 1920×1080 safe rectangle for both renderer and FFmpeg."""
    surface = surface if isinstance(surface, dict) else {}
    resolved = {
        "x": int(surface.get("x", 1120)), "y": int(surface.get("y", 65)),
        "width": int(surface.get("width", 720)), "height": int(surface.get("height", 390)),
    }
    detected = locate_data_surface(source_image_path, surface)
    if not detected:
        return resolved
    try:
        from PIL import Image
        with Image.open(source_image_path) as source:
            source_w, source_h = source.size
        resolved = {
            "x": round(detected["x"] * 1920 / source_w),
            "y": round(detected["y"] * 1080 / source_h),
            "width": round(detected["width"] * 1920 / source_w),
            "height": round(detected["height"] * 1080 / source_h),
        }
        logger.info("detected data surface: %s", resolved)
    except (OSError, ValueError, ZeroDivisionError):
        pass
    return resolved


def _apply_market_chart_overlay(
    clip_path: str,
    chart_path: str,
    duration: float,
    job_id: int,
    surface: dict | None = None,
) -> bool:
    """Center a real chart within the detected in-world panel, not fixed pixels."""
    if not chart_path or not os.path.exists(chart_path) or not _verify_video(clip_path):
        return False
    staged = clip_path + ".chart.mp4"
    surface = surface if isinstance(surface, dict) else {}
    x = int(surface.get("x", 1120)); y = int(surface.get("y", 65))
    width = int(surface.get("width", 720)); height = int(surface.get("height", 390))
    cmd = (
        f'ffmpeg -i "{clip_path}" -loop 1 -i "{chart_path}" '
        f'-filter_complex "[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease[chart];'
        f'[0:v][chart]overlay={x}+({width}-w)/2:{y}+({height}-h)/2:format=auto[v]" '
        f'-map "[v]" -t {duration:.3f} -an '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{staged}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0 or not _verify_video(staged):
        if os.path.exists(staged):
            os.remove(staged)
        return False
    os.replace(staged, clip_path)
    return True


def _apply_speech_bubble_overlay(
    scene: dict,
    clip_path: str,
    temp_dir: Path,
    index: int,
    duration: float,
    job_id: int,
) -> bool:
    """Place exact bubble text after all generated-video work is complete."""
    if not RENDER_SPEECH_BUBBLES:
        return True
    text = str(scene.get("bubble_text") or "").strip()
    if not text:
        return True
    bubble_path = str(temp_dir / f"speech_bubble_{index:03d}.png")
    side = "left" if scene.get("market_chart") else "right"
    if not write_speech_bubble_overlay(bubble_path, text, character_side=side):
        logger.warning("scene %s speech bubble renderer returned no valid file", index)
        return False
    staged = clip_path + ".bubble.mp4"
    cmd = (
        f'ffmpeg -i "{clip_path}" -loop 1 -i "{bubble_path}" '
        f'-filter_complex "[0:v][1:v]overlay=0:0:format=auto[v]" '
        f'-map "[v]" -t {duration:.3f} -an '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-y "{staged}" -loglevel error'
    )
    ret = _run_subprocess(cmd, job_id)
    if ret != 0 or not _verify_video(staged):
        if os.path.exists(staged):
            os.remove(staged)
        return False
    os.replace(staged, clip_path)
    return True


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
                c_end = float(c.get("end", c_start + c.get("duration", 0.0)))
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

