package com.pipeline.video.domain;

public enum Autonomy {
    MANUAL,   // 모든 게이트에서 사람이 승인
    GUIDED,   // 시놉시스 + 최종 미리보기만 사람이 승인
    AUTO      // 0→100 자동 (모든 게이트 자동 통과, 로그 기록)
}
