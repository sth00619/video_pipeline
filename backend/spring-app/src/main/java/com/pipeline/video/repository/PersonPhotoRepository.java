package com.pipeline.video.repository;

import com.pipeline.video.domain.PersonPhoto;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PersonPhotoRepository extends JpaRepository<PersonPhoto, String> {
    List<PersonPhoto> findByPersonIdOrderByCreatedAtDesc(String personId);
    List<PersonPhoto> findByPersonIdAndApprovedTrueOrderByCreatedAtDesc(String personId);
}
