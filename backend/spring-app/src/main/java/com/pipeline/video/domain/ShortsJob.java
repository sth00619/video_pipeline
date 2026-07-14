package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import jakarta.persistence.Transient;

import java.time.LocalDateTime;

/** A durable, independently editable Shorts project. */
@Entity
@Table(name = "shorts_job")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class ShortsJob {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private Long parentJobId;
    private String sourceType; // LONGFORM or UPLOAD
    @Column(nullable = false) private String title;
    @Column(columnDefinition = "TEXT") private String sourceVideoPath;
    @Column(columnDefinition = "TEXT") private String transcriptJson;
    @Column(columnDefinition = "TEXT") private String timelineJson;
    @Column(columnDefinition = "TEXT") private String selectionJson;
    @Column(columnDefinition = "TEXT") private String resultJson;
    @Column(columnDefinition = "TEXT") private String outputPath;
    private String status; // ANALYZING, EDITING, RENDERING, READY, FAILED
    private String createdBy;
    @Transient private Boolean downloadReady;
    @CreationTimestamp private LocalDateTime createdAt;
    @UpdateTimestamp private LocalDateTime updatedAt;
}
