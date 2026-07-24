package com.pipeline.video.repository;

import com.pipeline.video.domain.PersonAsset;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonAssetRepository extends JpaRepository<PersonAsset, String> { }
