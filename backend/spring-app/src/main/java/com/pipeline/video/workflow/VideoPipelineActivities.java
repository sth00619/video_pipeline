package com.pipeline.video.workflow;

import io.temporal.activity.ActivityInterface;
import io.temporal.activity.ActivityMethod;

/**
 * 롱폼 파이프라인 각 단계를 Temporal Activity로 선언합니다.
 *
 * Activity는 Workflow와 달리 비결정적 코드(외부 API 호출, DB 접근 등)를
 * 실행할 수 있습니다. 각 Activity가 실패하면 Temporal이 자동으로 재시도합니다.
 *
 * 기존 서비스 메서드들(ScriptService.generate 등)을 그대로 위임 호출하므로
 * 기존 비즈니스 로직은 변경 없음.
 */
@ActivityInterface
public interface VideoPipelineActivities {

    /** 키워드 확정 후 스크립트 생성 */
    @ActivityMethod
    void generateScript(Long jobId);

    /** 스크립트 확정 후 TTS 음성 생성 */
    @ActivityMethod
    void generateTts(Long jobId);

    /** TTS 확정 후 씬 이미지 생성 */
    @ActivityMethod
    void generateImages(Long jobId);

    /** 이미지 확정 후 롱폼 영상 조립 */
    @ActivityMethod
    void assembleLongform(Long jobId);

    /** 롱폼 확정 후 YouTube 업로드 */
    @ActivityMethod
    void publishVideo(Long jobId);

    /** DB Job 상태를 FAILED로 업데이트 (보상 트랜잭션용) */
    @ActivityMethod
    void markJobFailed(Long jobId, String reason);
}
