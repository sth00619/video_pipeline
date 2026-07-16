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
    private Category category;

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

    /** null이면 channel profile의 기본 캐릭터를 상속한다. */
    @Column(name = "character_override", length = 100)
    private String characterOverride;

    @Builder.Default
    private boolean dataVisualsEnabled = true;

    /** GUIDED 작업에서 TTS 생성 전에 사용자가 선택한 목소리. */
    @Column(name = "tts_voice_id", length = 100)
    private String ttsVoiceId;

    @CreationTimestamp
    private LocalDateTime createdAt;

    @UpdateTimestamp
    private LocalDateTime updatedAt;
}
