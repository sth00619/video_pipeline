package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Table(name = "person_photo")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class PersonPhoto {
    @Id
    @Column(name = "photo_id", length = 80)
    private String photoId;

    @Column(name = "person_id", nullable = false, length = 80)
    private String personId;

    @Column(name = "original_path", nullable = false, length = 700)
    private String originalPath;

    @Column(name = "cutout_path", length = 700)
    private String cutoutPath;

    @Enumerated(EnumType.STRING)
    @Column(name = "license_type", nullable = false, length = 30)
    private PhotoLicenseType licenseType;

    @Column(name = "license_ref", columnDefinition = "TEXT")
    private String licenseRef;

    @Column(name = "credit_text", columnDefinition = "TEXT")
    private String creditText;

    @Column(name = "author_name", length = 200)
    private String authorName;

    @Column(name = "emotion_tag", length = 30)
    private String emotionTag;

    @Column(name = "pose", length = 30)
    private String pose;

    @Column(name = "content_sha256", length = 64)
    private String contentSha256;

    @Column(name = "cutout_model", length = 60)
    @Builder.Default
    private String cutoutModel = "isnet-general-use";

    @Column(name = "approved", nullable = false)
    @Builder.Default
    private boolean approved = false;

    @Enumerated(EnumType.STRING)
    @Column(name = "rights_review_status", nullable = false, length = 30)
    @Builder.Default
    private RightsReviewStatus rightsReviewStatus = RightsReviewStatus.PENDING;

    @Column(name = "approved_by", length = 100)
    private String approvedBy;

    private LocalDateTime approvedAt;

    @Column(name = "transformation_log", columnDefinition = "TEXT")
    private String transformationLog;

    @CreationTimestamp
    private LocalDateTime createdAt;
}
