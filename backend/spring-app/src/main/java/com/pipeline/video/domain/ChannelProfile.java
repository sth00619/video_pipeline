package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Table(name = "channel_profile")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ChannelProfile {

    @Id
    @Column(name = "channel_id", length = 50)
    private String channelId;

    @Column(name = "channel_name", nullable = false, length = 100)
    private String channelName;

    @Column(name = "character_image_path", length = 500)
    private String characterImagePath;

    @Column(name = "character_style_prompt", columnDefinition = "TEXT")
    private String characterStylePrompt;

    @Column(name = "voice_id", length = 100)
    private String voiceId;

    @CreationTimestamp
    private LocalDateTime createdAt;
}
