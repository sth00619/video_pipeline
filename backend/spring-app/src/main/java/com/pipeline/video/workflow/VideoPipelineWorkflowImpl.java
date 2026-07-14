package com.pipeline.video.workflow;

import io.temporal.activity.ActivityOptions;
import io.temporal.common.RetryOptions;
import io.temporal.spring.boot.WorkflowImpl;
import io.temporal.workflow.Workflow;
import org.slf4j.Logger;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;

/**
 * 롱폼 파이프라인 Workflow 구현체.
 *
 * 흐름:
 *   키워드 게이트 승인 대기
 *     → 스크립트 생성 (Activity)
 *     → 스크립트 게이트 승인 대기 (MANUAL/GUIDED만)
 *     → TTS 생성 (Activity)
 *     → TTS 게이트 승인 대기 (MANUAL/GUIDED만)
 *     → 이미지 생성 (Activity)
 *     → 이미지 게이트 승인 대기 (MANUAL/GUIDED만)
 *     → 롱폼 조립 (Activity)
 *     → 미리보기 게이트 승인 대기
 *     → 완료
 *
 * 게이트 대기:
 *   approveGate(gateName) Signal을 받을 때까지 Workflow가 일시 중단됩니다.
 *   대기 중에 서버가 재시작돼도 Temporal이 이 상태를 복원합니다.
 *   AUTO 모드에서는 GateService.approve()가 즉시 Signal을 보내므로
 *   실질적으로 게이트 없이 자동 진행됩니다.
 *
 * 내결함성:
 *   각 Activity는 실패 시 최대 3회 자동 재시도합니다.
 *   Activity 완료 이력은 Temporal에 저장되므로, 서버 재시작 후
 *   완료된 Activity는 다시 실행하지 않고 다음 단계부터 재개합니다.
 */
@WorkflowImpl(taskQueues = "video-pipeline-queue")
public class VideoPipelineWorkflowImpl implements VideoPipelineWorkflow {

    private static final Logger log = Workflow.getLogger(VideoPipelineWorkflowImpl.class);

    // 승인된 게이트 이름을 추적 (Signal 수신 시 추가됨)
    private final Set<String> approvedGates = new HashSet<>();
    // 거부된 게이트 이름 (reject Signal 수신 시 설정됨)
    private String rejectedGate = null;

    // Activity 옵션 — 각 단계는 최대 2시간 (이미지/롱폼 생성이 오래 걸릴 수 있음)
    //
    // [긴급 버그 수정] 기존에 setHeartbeatTimeout(10분)을 설정해뒀는데, Activity
    // 구현체 어디에서도 실제로 heartbeat를 보내는 코드가 없었습니다. Temporal은
    // heartbeat 타임아웃이 설정되어 있으면 그 시간 안에 신호가 안 오면 Activity가
    // 죽은 것으로 간주하고 처음부터 다시 실행합니다. 3-Round 팩트체크 스크립트
    // 생성은 10분을 넘기는 경우가 있어서, 실제로는 정상 진행 중인데도 Temporal이
    // "멈췄다"고 오판해 같은 단계를 여러 번 중복 실행했습니다 (스크립트+TTS가
    // 3번씩 생성되고 비용이 3배로 나간 원인).
    //
    // 추가로 MaximumAttempts도 3 → 1로 낮췄습니다. ScriptService.generate() 등은
    // 내부적으로 AUTO 모드에서 confirm()까지 연쇄 호출하는 멱등하지 않은 로직이라,
    // Temporal이 "실패로 착각해서" 자동 재시도하면 스크립트 생성+게이트 승인+TTS
    // 트리거까지 통째로 중복됩니다. 재시도가 안전해지려면 각 서비스를 멱등하게
    // 만드는 리팩터가 필요한데, 그건 별도 작업이 필요하므로 우선 재시도 자체를
    // 끄는 쪽으로 안전하게 갑니다 (실패 시 사람이 Temporal UI에서 수동으로
    // 재시도 여부를 판단하는 게 지금은 더 안전합니다).
    private final VideoPipelineActivities activities = Workflow.newActivityStub(
            VideoPipelineActivities.class,
            ActivityOptions.newBuilder()
                    // A 20-minute job can need a long sequential Pro image render.
                    // This is a ceiling only; automatic retries remain disabled below.
                    .setStartToCloseTimeout(Duration.ofHours(6))
                    .setRetryOptions(RetryOptions.newBuilder()
                            .setMaximumAttempts(1)
                            .build())
                    .build()
    );

    @Override
    public void run(Long jobId) {
        log.info("VideoPipeline Workflow 시작: jobId={}", jobId);

        try {
            // 1. 키워드 게이트 승인 대기
            // (KeywordService가 키워드 생성 완료 후 KEYWORD_PENDING으로 전환,
            //  사람이 승인하거나 AUTO 모드이면 GateService가 즉시 Signal 전송)
            waitForGate("KEYWORD");
            if (isRejected()) return;

            // 2. 스크립트 생성
            log.info("스크립트 생성 Activity 시작: jobId={}", jobId);
            activities.generateScript(jobId);

            // 3. 스크립트 게이트 승인 대기
            waitForGate("SCRIPT");
            if (isRejected()) return;

            // 4. TTS 생성
            log.info("TTS 생성 Activity 시작: jobId={}", jobId);
            activities.generateTts(jobId);

            // 5. TTS 게이트 승인 대기
            waitForGate("TTS");
            if (isRejected()) return;

            // 6. 이미지 생성
            log.info("이미지 생성 Activity 시작: jobId={}", jobId);
            activities.generateImages(jobId);

            // 7. 이미지 게이트 승인 대기
            waitForGate("IMAGES");
            if (isRejected()) return;

            // 8. 롱폼 조립
            log.info("롱폼 조립 Activity 시작: jobId={}", jobId);
            activities.assembleLongform(jobId);

            // 9. 미리보기 게이트 승인 대기
            waitForGate("PREVIEW");
            if (isRejected()) return;

            // 10. 완료 (YouTube 업로드는 별도 트리거로 분리)
            log.info("VideoPipeline Workflow 완료: jobId={}", jobId);

        } catch (Exception e) {
            log.error("VideoPipeline Workflow 오류: jobId={}, error={}", jobId, e.getMessage());
            // 보상 트랜잭션: DB Job 상태를 FAILED로 마킹
            // Activity로 실행해서 이것 자체도 재시도 가능하게 함
            ActivityOptions quickOptions = ActivityOptions.newBuilder()
                    .setStartToCloseTimeout(Duration.ofSeconds(30))
                    .setRetryOptions(RetryOptions.newBuilder().setMaximumAttempts(3).build())
                    .build();
            VideoPipelineActivities compensate = Workflow.newActivityStub(
                    VideoPipelineActivities.class, quickOptions);
            compensate.markJobFailed(jobId, e.getMessage());
            throw e;
        }
    }

    @Override
    public void approveGate(String gateName) {
        log.info("게이트 승인 Signal 수신: gate={}", gateName);
        approvedGates.add(gateName);
    }

    @Override
    public void rejectGate(String gateName) {
        log.info("게이트 거부 Signal 수신: gate={}", gateName);
        rejectedGate = gateName;
    }

    /**
     * 특정 게이트의 승인 Signal을 받을 때까지 Workflow를 일시 중단합니다.
     *
     * Workflow.await()는 Temporal의 핵심 기능 중 하나입니다.
     * 일반 Thread.sleep과 달리, 이 대기 상태도 Temporal 이력에 저장되어
     * 서버 재시작 후에도 복원됩니다. 최대 72시간(3일) 대기하며,
     * 그 이후에도 승인이 없으면 TimeoutException이 발생합니다.
     */
    private void waitForGate(String gateName) {
        log.info("게이트 승인 대기: gate={}", gateName);
        boolean approved = Workflow.await(
                Duration.ofHours(72),
                () -> approvedGates.contains(gateName) || rejectedGate != null
        );
        if (!approved) {
            throw new RuntimeException("게이트 승인 타임아웃 (72시간): " + gateName);
        }
        log.info("게이트 통과: gate={}", gateName);
    }

    private boolean isRejected() {
        if (rejectedGate != null) {
            log.info("게이트 거부로 Workflow 종료: gate={}", rejectedGate);
            return true;
        }
        return false;
    }
}
