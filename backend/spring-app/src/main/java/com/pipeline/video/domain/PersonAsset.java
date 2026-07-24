package com.pipeline.video.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "person_asset")
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class PersonAsset {
    @Id
    @Column(name = "person_id", length = 80)
    private String personId;

    @Column(name = "name_ko", nullable = false, length = 120)
    private String nameKo;

    @Column(name = "name_en", length = 120)
    private String nameEn;

    /** JSON array; PostgreSQL ARRAY would tie this entity to one dialect. */
    @Column(name = "aliases_json", columnDefinition = "TEXT")
    private String aliasesJson;
}
