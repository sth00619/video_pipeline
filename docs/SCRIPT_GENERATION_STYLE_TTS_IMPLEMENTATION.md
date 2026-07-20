# Script-generation style and TTS implementation

## Safety boundary

This implementation never changes a generated script's facts, numbers, dates,
companies, sources, or causal claims. `script_delivery.py` operates only after
the narration is final and attaches production metadata. It does not rewrite
`content`, `text`, or `text_for_tts`.

## Implemented flow

1. `ScriptWorker` keeps the verified-fact boundary and unit validation.
2. The generation prompt requires a four-phase delivery arc: Hook (0–8%),
   Context (to 55%), Twist (to 85%), Resolution (to 100%). The request is
   explicitly limited to delivery, rhythm and listener comprehension; it must
   not add/remove/reinterpret source information.
3. After visual scene splitting, `annotate_sections()` supplies phase timing,
   `emotion_tag`, `character_action`, `edit_marker`, sentence metadata and
   unmodified `text_for_tts`.
4. `elevenlabs_mapper.py` maps 4 phases × 5 emotions to conservative v3 tags
   and `Natural`/`Robust` delivery hints. Tags stay metadata until the TTS
   request layer elects to use them, avoiding accidental change to narration.
5. `validate_delivery()` reports forbidden promotional phrasing, raw percent
   input in TTS, phase distribution and emotion repetition. It reports rather
   than silently rewriting prose.

## Default style mix

- KOSPI long form: economic-storytelling 0.7 / knowledge delivery 0.3
- KOSPI shorts: 0.8 / 0.2
- US long form: 0.6 / 0.4
- US shorts: 0.7 / 0.3

These weights only influence pacing/transition instructions. They do not change
the verified fact bundle or authorize imitation of any creator.

## Verification

- narration-preservation assertion passed;
- 20 phase/emotion mapper combinations passed;
- delivery validation passed for a factual percentage sentence;
- Python compilation passed;
- Spring compilation remains successful.
