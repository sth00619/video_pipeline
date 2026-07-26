# FastAPI 워커 작업 규칙

- TTS는 ElevenLabs with-timestamps 엔드포인트를 사용한다. 텍스트 정규화를 비활성화하는 `latency_optimization=4`는 사용하지 않는다.
- 한국어 숫자는 오디오용으로 한글 표기까지 확장한다(예: `52,300원` → `오만이천삼백원`). 자막은 숫자 표기를 유지한다. 소수점(`16.5`)을 문장 경계로 오인하지 않는 number-safe splitter를 사용한다.
- `%`는 반드시 `퍼센트`로만 변환하고 `포인트`로 변환하지 않는다.
- TTS 입력 전 스크립트 원문을 변형하지 않는다. 자막 싱크가 어긋날 수 있다.
- 오디오 태그 정규식은 `\[[^\[\]]{1,40}\]\s?`를 사용해 태그 뒤 공백까지 소비한다.
- 파이프라인 중지 플래그는 Redis에 저장한다. 프로세스 간 전파되지 않는 in-memory Python `set`은 사용하지 않는다.
- Kling 캐릭터 이미지는 base64 data URI로 전달한다. `image_url=None`을 하드코딩하지 않는다.
- 런타임 파라미터는 `runtime_config.py`와 `/pipeline/config` API 패턴으로 관리하여 Docker 리빌드 없이 조정한다.
