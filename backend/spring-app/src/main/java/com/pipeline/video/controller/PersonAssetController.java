package com.pipeline.video.controller;

import com.pipeline.video.domain.PersonAsset;
import com.pipeline.video.domain.PersonPhoto;
import com.pipeline.video.domain.PhotoLicenseType;
import com.pipeline.video.repository.PersonAssetRepository;
import com.pipeline.video.service.PersonAssetService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.net.MalformedURLException;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/assets/person")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class PersonAssetController {
    private final PersonAssetService personAssetService;
    private final PersonAssetRepository personAssetRepository;

    @GetMapping
    public List<PersonAsset> list() { return personAssetRepository.findAll(); }

    @PostMapping
    public ResponseEntity<PersonAsset> create(@RequestBody Map<String, String> request) {
        return ResponseEntity.ok(personAssetService.savePerson(
                request.get("personId"), request.get("nameKo"), request.get("nameEn"), request.get("aliasesJson")));
    }

    @GetMapping("/{personId}/photos")
    public List<PersonPhoto> photos(@PathVariable String personId) { return personAssetService.photos(personId); }

    @PostMapping(value = "/{personId}/photos", consumes = "multipart/form-data")
    public ResponseEntity<PersonPhoto> upload(@PathVariable String personId,
                                                @RequestPart("file") MultipartFile file,
                                                @RequestParam PhotoLicenseType licenseType,
                                                @RequestParam(required = false) String licenseRef,
                                                @RequestParam(required = false) String creditText,
                                                @RequestParam(required = false) String authorName,
                                                @RequestParam(required = false) String emotionTag,
                                                @RequestParam(required = false) String pose,
                                                @RequestParam(required = false) String cutoutModel) throws IOException {
        return ResponseEntity.ok(personAssetService.registerPhoto(personId, file, licenseType, licenseRef,
                creditText, authorName, emotionTag, pose, cutoutModel));
    }

    @PostMapping("/{personId}/photos/{photoId}/approve")
    public ResponseEntity<PersonPhoto> approve(@PathVariable String personId, @PathVariable String photoId,
                                                @RequestParam(defaultValue = "admin") String username) {
        return ResponseEntity.ok(personAssetService.approve(personId, photoId, username));
    }

    @PostMapping("/{personId}/photos/{photoId}/reject")
    public ResponseEntity<PersonPhoto> reject(@PathVariable String personId, @PathVariable String photoId) {
        return ResponseEntity.ok(personAssetService.reject(personId, photoId));
    }

    @GetMapping("/{personId}/photos/{photoId}/content")
    public ResponseEntity<Resource> content(@PathVariable String personId, @PathVariable String photoId)
            throws MalformedURLException {
        Resource resource = new UrlResource(personAssetService.photoContentPath(personId, photoId).toUri());
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_PNG)
                .body(resource);
    }
}
