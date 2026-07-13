package com.pipeline.video.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "elevenlabs_voice")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ElevenLabsVoice {

    @Id
    @Column(name = "voice_id", length = 50)
    private String voiceId;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @Column(name = "category", length = 50)
    private String category;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;

    @Column(name = "preview_url", length = 500)
    private String previewUrl;

    @Column(name = "audition_url", length = 500)
    private String auditionUrl;
}
