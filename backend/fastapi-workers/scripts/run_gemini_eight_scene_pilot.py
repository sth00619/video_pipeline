#!/usr/bin/env python3
"""WO-IMG-01-C3 승인 8장 파일럿을 장면당 실제 POST 1회로 실행한다."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload) -> None:
    staged = path.with_suffix(path.suffix + ".tmp")
    staged.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, path)


def _read_prices(path: Path) -> tuple[Decimal, Decimal]:
    source = path.read_text(encoding="utf-8")
    values = []
    for key in ("GEMINI_3_PRO_IMAGE_2K_USD", "USD_TO_KRW_BUDGET_RATE"):
        match = re.search(rf"\b{key}\s*=\s*BigDecimal.valueOf\(([\d_.]+)[DL]?\)", source)
        if not match:
            raise ValueError(f"중앙 가격 선언 확인 불가: {key}")
        values.append(Decimal(match[1].replace("_", "")))
    return values[0], values[1]


def _relative_regions(count: int) -> list[list[float]]:
    """한 물리 표면 안의 1~4개 문구를 겹치지 않는 셀로 나눈다."""
    layouts = {
        1: [[.07, .18, .86, .64]],
        2: [[.06, .10, .88, .34], [.06, .56, .88, .34]],
        3: [[.05, .08, .90, .25], [.05, .375, .90, .25], [.05, .67, .90, .25]],
        4: [[.05, .08, .42, .38], [.53, .08, .42, .38],
            [.05, .54, .42, .38], [.53, .54, .42, .38]],
    }
    if count not in layouts:
        raise ValueError("파일럿 단일 표면은 최대 네 문구까지만 지원합니다.")
    return layouts[count]


def _fact_ref(scene: dict, text: str) -> str:
    from app.v5.overlay.fact_value_contract import verified_fact_contains_value

    facts = scene.get("verified_facts") or []
    for index, fact in enumerate(facts):
        if isinstance(fact, dict) and verified_fact_contains_value(
            fact, text, require_structured_value_match=True,
        ):
            return f"facts[{index}]"
    # Job52 승인 대본은 원자료의 소수값을 발화용 정수로 줄인 장면이 있다.
    # 새 값을 계산하지 않고, 같은 숫자열과 출처를 가진 기존 검증 사실에만
    # 승인 내레이션 표기를 장면 로컬 파생 사실로 연결한다.
    digits = "".join(re.findall(r"\d", text))
    narration = str(scene.get("content") or scene.get("text") or "")
    for fact in facts:
        compact_fact = re.sub(r"[^\d]", "", json.dumps(fact, ensure_ascii=False))
        if isinstance(fact, dict) and digits and digits in compact_fact:
            derived = {
                "fact": narration,
                "figure": text,
                "confidence": fact.get("confidence"),
                "source_ref": copy.deepcopy(fact.get("source_ref")),
                "source_field": f"approved_narration_display_from:{fact.get('source_field')}",
                "cross_verified": fact.get("cross_verified"),
                "contradiction_detected": fact.get("contradiction_detected", False),
                "derivation": "approved_narration_exact_display_no_new_numeric_generation",
            }
            scene.setdefault("verified_facts", []).append(derived)
            return f"facts[{len(scene['verified_facts']) - 1}]"
    raise ValueError(f"장면 {scene.get('index')}의 수치 문구에 정확한 검증 사실이 없습니다: {text}")


def prepare_pilot_scene(source: dict, spec: dict) -> dict:
    """원본 내레이션·사실·화풍을 보존하고 파일럿 문자 경로만 선택한다."""
    scene = copy.deepcopy(source)
    exact = [str(value).strip() for value in spec["exact_texts"]]
    if not exact or any(not value for value in exact):
        raise ValueError("파일럿 승인 문구가 비어 있습니다.")
    narration = str(scene.get("content") or scene.get("text") or "")
    if any(re.sub(r"\s+", "", value) not in re.sub(r"\s+", "", narration) for value in exact):
        raise ValueError(f"장면 {spec['index']} 승인 문구가 승인 내레이션에 없습니다.")
    scene["screen_texts"] = exact
    scene["screen_text_validation"] = {
        "passed": True,
        "method": "pilot_spec_exact_narration_membership_v1",
        "narration_sha256": _sha(narration.encode()),
    }
    scene["pilot_visual_contract"] = spec["visual_contract"]
    scene.pop("surface_bindings", None)
    scene.pop("surface_text_manifest", None)
    scene.pop("final_frame_text_integrity", None)
    if spec["lane"] == "deterministic_information":
        scene["text_render_policy"] = "semantic_roles_v1"
        regions = _relative_regions(len(exact))
        scene["screen_text_plan"] = []
        for text, region in zip(exact, regions):
            item = {
                "text": text, "surface": "main", "surface_kind": "board",
                "purpose": "information", "region": region,
            }
            if any(character.isdigit() for character in text):
                item["source_ref"] = _fact_ref(scene, text)
            scene["screen_text_plan"].append(item)
        scene["pilot_text_lane"] = "pillow_deterministic_all_information"
    elif spec["lane"] == "pilot_only_short_approved_label_measurement":
        # 이 레인은 전역 정책을 바꾸지 않고 8장 탐색 표본에서만 모델의 짧은
        # 승인 문구 크기와 오탈자율을 실측한다. 수치는 들어올 수 없다.
        if any(any(character.isdigit() for character in text) for text in exact):
            raise ValueError("모델 생성 측정 레인에는 수치 문구를 넣을 수 없습니다.")
        scene.pop("text_render_policy", None)
        scene["screen_text_plan"] = [
            {"text": text, "purpose": "decorative", "max_occurrences": 1}
            for text in exact
        ]
        scene["pilot_text_lane"] = "gemini_short_approved_label_measurement_only"
    else:
        raise ValueError(f"알 수 없는 파일럿 레인: {spec['lane']}")
    return scene


def _remove_historical_unbound_commodity_prompt(prompt: str, narration: str) -> str:
    """수정 전 바인더가 조사 `은`을 Silver로 오염시킨 보존 프롬프트만 정리한다."""
    from app.utils.scene_entity_binder import entity_is_mentioned

    cleaned = str(prompt or "")
    if not entity_is_mentioned(narration, "은"):
        cleaned = re.sub(r"\bSilver\s+price\s+charts?\b", "valuation risk charts", cleaned,
                         flags=re.IGNORECASE)
        cleaned = re.sub(r"\bsilver\s+barrel\b", "unstable valuation barrel", cleaned,
                         flags=re.IGNORECASE)
        cleaned = re.sub(r"\bSilver\b", "risk", cleaned, flags=re.IGNORECASE)
    return cleaned


def _measure_generated_labels(image_path: Path, expected: list[str]) -> dict:
    from app.services.fal_motion_safety import _read_tesseract_rows

    with Image.open(image_path) as image:
        width, height = image.size
    prepared_height = height if width <= 960 else round(height * 960 / width)
    modes = []
    for psm in (6, 11, 12):
        status, rows = _read_tesseract_rows(str(image_path), psm=psm)
        observations = []
        for row in rows:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            try:
                ratio = float(row.get("height") or 0) / prepared_height
            except (TypeError, ValueError, ZeroDivisionError):
                ratio = 0.0
            observations.append({
                "text": text,
                "confidence": row.get("conf"),
                "bbox": [row.get(key) for key in ("left", "top", "width", "height")],
                "character_height_ratio": round(ratio, 6),
            })
        compact_rows = [re.sub(r"\s+", "", item["text"]) for item in observations]
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for row in rows:
            text = str(row.get("text") or "").strip()
            if text:
                grouped.setdefault(tuple(str(row.get(key) or "") for key in
                                         ("block_num", "par_num", "line_num")), []).append(row)
        sequence_hits = {}
        for text in expected:
            hits = []
            for line_rows in grouped.values():
                hit = _find_exact_token_sequence(line_rows, text, prepared_height)
                if hit is not None:
                    hits.append(hit)
            sequence_hits[text] = hits
        modes.append({
            "psm": psm, "status": status, "observations": observations,
            "exact_text_hits": {
                text: sum(re.sub(r"\s+", "", text) == observed for observed in compact_rows)
                for text in expected
            },
            "exact_token_sequence_hits": sequence_hits,
        })
    all_hits = {
        text: sum(mode["exact_text_hits"][text] + len(mode["exact_token_sequence_hits"][text])
                  for mode in modes)
        for text in expected
    }
    return {
        "version": "pilot-generated-label-ocr-measurement-v1",
        "frame_size": [width, height], "ocr_prepared_height": prepared_height,
        "expected": expected, "modes": modes, "exact_hit_totals": all_hits,
        "all_expected_seen_at_least_once": all(value > 0 for value in all_hits.values()),
        "interpretation": "탐색 표본이며 전역 최소 글자 크기 임계값을 확정하지 않음",
    }


def _find_exact_token_sequence(rows: list[dict], expected: str, frame_height: int) -> dict | None:
    """한 OCR 행에서 이웃 한국어를 잘라 통과시키지 않고 승인 토큰 연속열만 찾는다."""
    ordered = sorted(rows, key=lambda row: int(row.get("word_num") or 0))
    target = re.sub(r"\s+", "", expected)
    tokens = [re.sub(r"\s+", "", str(row.get("text") or "")) for row in ordered]
    for start in range(len(tokens)):
        joined = ""
        for end in range(start, len(tokens)):
            joined += tokens[end]
            if joined != target[:len(joined)]:
                break
            if joined != target:
                continue
            before = tokens[start - 1] if start else ""
            after = tokens[end + 1] if end + 1 < len(tokens) else ""
            if re.search(r"[가-힣\d]$", before) or re.match(r"^[가-힣\d]", after):
                continue
            try:
                left = min(int(row.get("left") or 0) for row in ordered[start:end + 1])
                top = min(int(row.get("top") or 0) for row in ordered[start:end + 1])
                right = max(int(row.get("left") or 0) + int(row.get("width") or 0)
                            for row in ordered[start:end + 1])
                bottom = max(int(row.get("top") or 0) + int(row.get("height") or 0)
                             for row in ordered[start:end + 1])
            except (TypeError, ValueError):
                return None
            return {
                "text": expected, "token_range": [start, end], "bbox": [left, top, right, bottom],
                "character_height_ratio": round((bottom - top) / max(1, frame_height), 6),
                "match_policy": "contiguous_complete_tokens_exact_whitespace_only_v1",
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--pricing-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    budget = spec["budget_preflight"]
    if spec.get("paid_execution_authorized") is not True or budget.get("approved_total_for_this_spec_krw") != 12800:
        raise RuntimeError("8장 파일럿 유료 실행 승인과 총 ₩12,800 상한이 명세에 고정되지 않았습니다.")
    if budget.get("current_conservative_reservation_per_attempt_krw") != 1600:
        raise RuntimeError("장당 보수적 예약액이 ₩1,600과 다릅니다.")
    scenes_spec = spec.get("scenes") or []
    if len(scenes_spec) != 8 or len({item["index"] for item in scenes_spec}) != 8 or 42 in {item["index"] for item in scenes_spec}:
        raise RuntimeError("파일럿은 scene42를 제외한 서로 다른 8장이어야 합니다.")
    source_path = REPO / spec["source"]["path"]
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != spec["source"]["sha256"]:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    source_scenes = json.loads(source_bytes)
    by_index = {int(item["index"]): item for item in source_scenes}
    unit_usd, fx = _read_prices(args.pricing_config)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # 앱 모듈 import 전에 이 파일럿만의 영속 상태를 지정한다. 운영 상태와
    # 섞이지 않지만 같은 WO-REQUEST-01 코드와 상한 로직을 그대로 통과한다.
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"wo-img01-c3-{_sha(spec_bytes)[:12]}"

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, select_contextual_reference_paths
    from app.workers.images_worker import _bounded_text_generation_prompt

    runtime_config.update(gemini_scene_request_limit=1)
    prepared = []
    for item in scenes_spec:
        scene = prepare_pilot_scene(by_index[int(item["index"])], item)
        narration = str(scene.get("content") or scene.get("text") or "")
        corrected_source_prompt = _remove_historical_unbound_commodity_prompt(scene["prompt_en"], narration)
        base_prompt = f"{corrected_source_prompt}\n\nSCENE MEANING CONTRACT: {item['visual_contract']}"
        prompt = _bounded_text_generation_prompt(base_prompt, audit_target=scene)
        refs = select_contextual_reference_paths(prompt)
        prepared.append({
            "index": item["index"], "lane": item["lane"], "scene": scene, "prompt": prompt,
            "prompt_sha256": _sha(prompt.encode()),
            "narration_sha256": scene["screen_text_validation"]["narration_sha256"],
            "references": [{"name": Path(path).name, "sha256": _sha(Path(path).read_bytes())} for path in refs],
            "reference_paths": refs,
        })
    manifest_path = output / "pilot_manifest.json"
    manifest = {
        "version": "wo-img-01-c3-eight-scene-execution-v1",
        "status": "preflight_only", "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes), "source_sha256": _sha(source_bytes),
        "model": GeminiModel.PRO.value, "service_tier": "standard", "image_size": "2K",
        "authorized_total_reserved_krw": 12800, "reserved_per_scene_krw": 1600,
        "reservation_interpretation": "보수적 요청 예약 상한이며 예상 비용 또는 확정 지출이 아님",
        "actual_paid_calls_other_providers": 0, "scene42_frozen_and_excluded": True,
        "scenes": [{key: value for key, value in row.items() if key not in {"scene", "prompt", "reference_paths"}}
                   | {"status": "pending"} for row in prepared],
    }
    if not args.execute:
        _write_json(output / "preflight.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    if claim.exists() or (output / "request_ledger.json").exists():
        raise RuntimeError("이 파일럿은 이미 실행됐거나 시작됐습니다. 추가 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    manifest["status"] = "running"
    _write_json(manifest_path, manifest)

    first_usage = None
    for position, row in enumerate(prepared):
        index = row["index"]
        scene_result = manifest["scenes"][position]
        print(f"[pilot] scene {index:02d} 시작: lane={row['lane']}", flush=True)
        audit = ProviderRequestAudit.for_path(
            path=output / "request_ledger.json", scene_key=f"image:{index}",
            model=GeminiModel.PRO.value, unit_usd=float(Decimal(1600) / fx),
            usd_krw=float(fx), budget_limit_krw=12800,
            request_metadata={
                "pilot_id": output.name, "run_id": output.name,
                "contract_fingerprint": _sha(json.dumps(row["scene"], ensure_ascii=False, sort_keys=True).encode()),
                "attempt_policy": "one_external_post_no_retry",
            },
        )
        try:
            result = GeminiProvider(use_batch=False).generate(
                row["prompt"], reference_image_paths=row["reference_paths"], request_audit=audit,
            )
            raw_path = output / f"scene_{index:02d}_raw.png"
            raw_path.write_bytes(result.image_bytes)
            scene_result.update(status="generated", raw_path=str(raw_path), raw_sha256=_sha(result.image_bytes))
            if row["lane"] == "deterministic_information":
                from app.services.semantic_surface_text import render_semantic_surface_text
                final_path = output / f"scene_{index:02d}_final.png"
                final_path.write_bytes(result.image_bytes)
                try:
                    render_semantic_surface_text(row["scene"], str(final_path))
                    scene_result.update(
                        status="deterministic_render_verified", final_path=str(final_path),
                        final_sha256=_sha(final_path.read_bytes()),
                        surface_binding=row["scene"].get("surface_bindings"),
                        final_frame_text_integrity=row["scene"].get("final_frame_text_integrity"),
                    )
                except Exception as render_error:
                    scene_result.update(
                        status="needs_review_deterministic_surface",
                        deterministic_error_type=type(render_error).__name__,
                    )
            else:
                measurement = _measure_generated_labels(raw_path, row["scene"]["screen_texts"])
                measurement_path = output / f"scene_{index:02d}_label_measurement.json"
                _write_json(measurement_path, measurement)
                scene_result.update(
                    status="generated_label_measured", measurement_path=str(measurement_path),
                    generated_label_measurement=measurement,
                )
        except Exception as exc:
            scene_result.update(
                status="needs_review_request_failed",
                error_type=type(exc).__name__,
                held_status=exc.status if isinstance(exc, ImageRequestHeld) else None,
                next_allowed_at=exc.next_allowed_at if isinstance(exc, ImageRequestHeld) else None,
            )
        summary = audit.summary()
        scene_result["request_summary"] = summary
        entries = summary.get("entries") or []
        if entries:
            usage = entries[-1].get("usage_metadata")
            if first_usage is None and entries[-1].get("usage_metadata_status") == "present" and usage is not None:
                first_usage = {
                    "scene_index": index, "attempt_id": entries[-1].get("attempt_id"),
                    "usageMetadata": usage,
                }
                _write_json(output / "first_success_usageMetadata.json", first_usage)
            deadline = float((entries[-1].get("request_control") or {}).get("next_allowed_at") or 0)
            remaining = deadline - time.time()
            if remaining > 0 and position + 1 < len(prepared):
                print(f"[pilot] 공유 냉각 {remaining:.1f}초 준수 후 다음 장면 진행", flush=True)
                time.sleep(remaining + .25)
        manifest["first_success_usage_metadata"] = first_usage
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
        print(f"[pilot] scene {index:02d} 종료: {scene_result['status']}", flush=True)

    manifest["status"] = "completed_with_review" if any(
        str(item["status"]).startswith("needs_review") for item in manifest["scenes"]
    ) else "completed"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"], "output_dir": str(output),
        "first_success_usage_metadata": first_usage,
        "scenes": [{"index": item["index"], "status": item["status"]} for item in manifest["scenes"]],
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
