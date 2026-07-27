# 통합 킷 적용 가이드 (최종본)

이전에 나뉘어 전달된 tts_sync_script_kit / voice_batch_test_kit을 하나로 합친 최종본입니다.
**이 zip과 CODEX_WORK_ORDER_FINAL.md만 쓰시면 됩니다.** 이전 문서들은 무시하세요.

## 순서
P0 (음성 배치 도구 구동) → P1 (담당자 피드백 루프) → P2 (싱크 근본 해결) → P3 (사람 녹음, 선택)

## 구조
```
final_kit/
├── CODEX_WORK_ORDER_FINAL.md      ← Codex에 넘길 것. 이것 하나로 충분.
├── voices.json                     ← voice_id 2개 채워 넣을 곳
├── sample_scripts/                 ← 테스트용 대본 3개
├── backend_fastapi/tts/
│   ├── forced_alignment_srt.py     ← TTS + 싱크 코어
│   └── sync_verifier.py            ← 싱크 검증/진단
├── script_analysis/
│   └── script_pattern_analyzer.py  ← (스크립트 작업용, 별도 병행 중이면 참고)
└── scripts/
    ├── voice_sample_batch.py       ← P0/P1에서 사용
    └── align_human_recording.py    ← P3에서 사용
```
