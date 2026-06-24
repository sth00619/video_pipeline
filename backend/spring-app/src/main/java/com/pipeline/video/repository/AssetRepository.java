package com.pipeline.video.repository;

import com.pipeline.video.domain.Asset;
import com.pipeline.video.domain.AssetType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface AssetRepository extends JpaRepository<Asset, Long> {
    List<Asset> findByJobIdOrderByCreatedAtAsc(Long jobId);
    List<Asset> findByJobIdAndAssetType(Long jobId, AssetType assetType);
    Optional<Asset> findFirstByJobIdAndAssetType(Long jobId, AssetType assetType);
}
