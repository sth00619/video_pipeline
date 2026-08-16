package com.pipeline.video.repository;

import com.pipeline.video.domain.ReferenceChannel;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ReferenceChannelRepository extends JpaRepository<ReferenceChannel, Long> {
    List<ReferenceChannel> findAllByOrderByDisplayOrderAscIdAsc();
    List<ReferenceChannel> findByActiveTrueOrderByDisplayOrderAscIdAsc();
    Optional<ReferenceChannel> findByChannelId(String channelId);
    boolean existsByChannelId(String channelId);
}
