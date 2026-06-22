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
    @Column(nullable = false)
    private RenderProfile renderProfile;

    // 시놉시스, 스크립트 (생성 후 채워짐)
    @Column(columnDefinition = "TEXT")
    private String synopsis;

    @Column(columnDefinition = "TEXT")
    private String script;

    // 쇼츠 생성 여부
    private boolean makeShorts;
    private Integer shortsCount;

    // 예산 관리
    private BigDecimal budgetCap;
    private BigDecimal costAccumulated;

    // 생성자 (로그인 사용자 이름)
    private String createdBy;

    // 최종 영상 파일 경로 (MinIO)
    private String outputPath;

    @CreationTimestamp
    private LocalDateTime createdAt;

    @UpdateTimestamp
    private LocalDateTime updatedAt;
}
