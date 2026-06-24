package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "video_job")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VideoJob {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    private String keyword;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private JobStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Autonomy autonomy;

    @Enumerated(EnumType.STRING)
    private Format format;

    @Enumerated(EnumType.STRING)
    private RenderProfile renderProfile;

    // GenerationPolicy 전체를 JSON으로 저장 (확장성)
    @Column(columnDefinition = "TEXT")
    private String policyJson;

    // 비용
    private BigDecimal budgetCap;
    private BigDecimal costAccumulated;

    // 쇼츠 옵션
    private boolean makeShorts;
    private Integer shortsCount;

    // 롱폼 목표 길이 (분) — Phase 3-5에서 사용
    private Integer longformTargetMinutes;

    // 입력 영상 경로 (쇼츠 생성 시 업로드된 원본)
    private String sourceVideoPath;

    // 최종 영상 경로
    private String outputPath;

    private String createdBy;

    @CreationTimestamp
    private LocalDateTime createdAt;

    @UpdateTimestamp
    private LocalDateTime updatedAt;
}
