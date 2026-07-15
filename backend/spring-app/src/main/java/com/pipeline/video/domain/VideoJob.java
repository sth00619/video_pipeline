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
    @Column(columnDefinition = "varchar(255)")
    private Category category;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, columnDefinition = "varchar(255)")
    private JobStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, columnDefinition = "varchar(255)")
    private Autonomy autonomy;

    @Enumerated(EnumType.STRING)
    @Column(columnDefinition = "varchar(255)")
    private Format format;

    @Enumerated(EnumType.STRING)
    @Column(columnDefinition = "varchar(255)")
    private RenderProfile renderProfile;

    @Column(columnDefinition = "TEXT")
    private String policyJson;

    private BigDecimal budgetCap;
    private BigDecimal costAccumulated;

    private boolean makeShorts;
    private Integer shortsCount;

    private Integer longformTargetMinutes;

    private String sourceVideoPath;
    private String outputPath;

    @Column(length = 255)
    private String youtubeUrl;

    private String createdBy;

    @Column(name = "channel_id", length = 50)
    private String channelId;

    @CreationTimestamp
    private LocalDateTime createdAt;

    @UpdateTimestamp
    private LocalDateTime updatedAt;
}
