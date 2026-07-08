package com.pipeline.video.repository;

import com.pipeline.video.domain.ChannelProfile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface ChannelProfileRepository extends JpaRepository<ChannelProfile, String> {
}
