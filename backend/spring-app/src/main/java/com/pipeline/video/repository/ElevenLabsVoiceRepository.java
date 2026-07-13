package com.pipeline.video.repository;

import com.pipeline.video.domain.ElevenLabsVoice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface ElevenLabsVoiceRepository extends JpaRepository<ElevenLabsVoice, String> {
}
