package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Table(name = "asset")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Asset {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long jobId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, columnDefinition = "varchar(255)")
    private AssetType assetType;

    private String localPath;
    private String s3Key;

    // 씬 인덱스, 시작/종료 시간, 텍스트, 프롬프트 등 자유 필드
    @Column(columnDefinition = "TEXT")
    private String metaJson;

    @CreationTimestamp
    private LocalDateTime createdAt;
}
