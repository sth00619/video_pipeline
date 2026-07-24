package com.pipeline.video.service;

import com.pipeline.video.domain.*;
import com.pipeline.video.repository.PersonAssetRepository;
import com.pipeline.video.repository.PersonPhotoRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class PersonAssetService {
    private static final Path ROOT = Path.of("/app/data/person_assets");
    private final PersonAssetRepository personAssetRepository;
    private final PersonPhotoRepository personPhotoRepository;

    public PersonAsset savePerson(String personId, String nameKo, String nameEn, String aliasesJson) {
        requireId(personId);
        if (nameKo == null || nameKo.isBlank()) throw new IllegalArgumentException("인물 한글 이름은 필수입니다.");
        return personAssetRepository.save(PersonAsset.builder()
                .personId(personId.trim()).nameKo(nameKo.trim()).nameEn(blankToNull(nameEn))
                .aliasesJson(blankToNull(aliasesJson)).build());
    }

    public PersonPhoto registerPhoto(String personId, MultipartFile upload, PhotoLicenseType licenseType,
                                     String licenseRef, String creditText, String authorName,
                                     String emotionTag, String pose, String cutoutModel) throws IOException {
        requireId(personId);
        if (!personAssetRepository.existsById(personId)) throw new IllegalArgumentException("등록되지 않은 인물입니다.");
        if (upload == null || upload.isEmpty()) throw new IllegalArgumentException("사진 파일이 필요합니다.");
        if (licenseType == null || licenseType == PhotoLicenseType.UNKNOWN) {
            throw new IllegalArgumentException("라이선스가 확인된 사진만 등록할 수 있습니다.");
        }
        if ((licenseType == PhotoLicenseType.CC_BY || licenseType == PhotoLicenseType.CC_BY_SA ||
                licenseType == PhotoLicenseType.KOGL_TYPE1 || licenseType == PhotoLicenseType.PRESS_KIT ||
                licenseType == PhotoLicenseType.STOCK_LICENSED || licenseType == PhotoLicenseType.AGENCY_LICENSED)
                && (licenseRef == null || licenseRef.isBlank())) {
            throw new IllegalArgumentException("출처 또는 계약 참조가 필요합니다.");
        }
        if ((licenseType == PhotoLicenseType.CC_BY || licenseType == PhotoLicenseType.CC_BY_SA ||
                licenseType == PhotoLicenseType.KOGL_TYPE1)
                && (creditText == null || creditText.isBlank())) {
            throw new IllegalArgumentException("저작자 표시가 필요한 라이선스는 크레딧 문구가 필요합니다.");
        }
        BufferedImage decoded;
        try (InputStream input = upload.getInputStream()) { decoded = ImageIO.read(input); }
        if (decoded == null) throw new IllegalArgumentException("지원하지 않는 이미지 파일입니다.");
        String photoId = UUID.randomUUID().toString().replace("-", "");
        Path directory = ROOT.resolve(personId).normalize();
        if (!directory.startsWith(ROOT)) throw new IllegalArgumentException("잘못된 인물 ID입니다.");
        Files.createDirectories(directory);
        Path target = directory.resolve(photoId + ".png");
        ImageIO.write(decoded, "png", target.toFile());
        return personPhotoRepository.save(PersonPhoto.builder()
                .photoId(photoId).personId(personId).originalPath(target.toString())
                .licenseType(licenseType).licenseRef(blankToNull(licenseRef)).creditText(blankToNull(creditText))
                .authorName(blankToNull(authorName)).emotionTag(blankToNull(emotionTag)).pose(blankToNull(pose))
                .contentSha256(sha256(target)).cutoutModel(blankToNull(cutoutModel) == null ? "isnet-general-use" : cutoutModel)
                .approved(false).rightsReviewStatus(RightsReviewStatus.PENDING)
                .transformationLog("원본 등록; 생성형 얼굴 편집 금지").build());
    }

    public PersonPhoto approve(String personId, String photoId, String username) {
        PersonPhoto photo = findPhoto(personId, photoId);
        photo.setApproved(true);
        photo.setRightsReviewStatus(RightsReviewStatus.APPROVED);
        photo.setApprovedBy(username);
        photo.setApprovedAt(LocalDateTime.now());
        return personPhotoRepository.save(photo);
    }

    public PersonPhoto reject(String personId, String photoId) {
        PersonPhoto photo = findPhoto(personId, photoId);
        photo.setApproved(false);
        photo.setRightsReviewStatus(RightsReviewStatus.REJECTED);
        return personPhotoRepository.save(photo);
    }

    public List<PersonPhoto> photos(String personId) { return personPhotoRepository.findByPersonIdOrderByCreatedAtDesc(personId); }

    public Path photoContentPath(String personId, String photoId) {
        PersonPhoto photo = findPhoto(personId, photoId);
        Path source = Path.of(photo.getOriginalPath()).normalize();
        if (!source.startsWith(ROOT) || !Files.isRegularFile(source)) {
            throw new IllegalArgumentException("사진 원본을 찾을 수 없습니다.");
        }
        return source;
    }

    private PersonPhoto findPhoto(String personId, String photoId) {
        PersonPhoto photo = personPhotoRepository.findById(photoId)
                .orElseThrow(() -> new IllegalArgumentException("사진을 찾을 수 없습니다."));
        if (!photo.getPersonId().equals(personId)) throw new IllegalArgumentException("인물과 사진이 일치하지 않습니다.");
        return photo;
    }

    private static void requireId(String personId) {
        if (personId == null || !personId.matches("[a-z0-9_]{2,80}")) {
            throw new IllegalArgumentException("personId는 소문자 영문·숫자·밑줄만 사용할 수 있습니다.");
        }
    }

    private static String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }

    private static String sha256(Path path) throws IOException {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        } catch (Exception exception) { throw new IOException("사진 해시 생성 실패", exception); }
    }
}
