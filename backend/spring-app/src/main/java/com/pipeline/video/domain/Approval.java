package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Table(name = "approval")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Approval {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long jobId;

    // 어떤 게이트인지 (SYNOPSIS / SCRIPT / ASSET / PREVIEW / SHORTS_PREVIEW)
    @Column(nullable = false)
    private String gate;

    // APPROVED / REJECTED / AUTO_APPROVED
    @Column(nullable = false)
    private String result;

    private String approvedBy;

    @Column(columnDefinition = "TEXT")
    private String comment;

    @CreationTimestamp
    private LocalDateTime createdAt;
}
