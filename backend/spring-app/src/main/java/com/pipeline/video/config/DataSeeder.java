package com.pipeline.video.config;

import com.pipeline.video.domain.User;
import com.pipeline.video.domain.UserRole;
import com.pipeline.video.repository.UserRepository;
import com.pipeline.video.repository.ChannelProfileRepository;
import com.pipeline.video.domain.ChannelProfile;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;

/**
 * 초기 admin 계정 시딩.
 *
 * [보안 수정] 기존에는 비밀번호가 "admin1234"로 소스코드에 그대로 하드코딩되어
 * 있었습니다. 이 리포지토리는 GitHub(sth00619/video_pipeline)에 공개되어 있으므로,
 * JWT 시크릿 키(application.properties)와 마찬가지로 사실상 공개된 비밀번호였습니다.
 * DB만 접근 가능해도가 아니라, 로그인 화면에 admin/admin1234로 그냥 들어갈 수 있는
 * 문제였습니다.
 *
 * 수정 방향:
 *   - ADMIN_SEED_PASSWORD 환경변수가 설정되어 있으면 그 값을 사용
 *   - 설정 안 되어 있으면 매 기동 시 무작위 16자 비밀번호를 생성해서 로그에
 *     "최초 1회만" 출력합니다 (컨테이너 최초 기동 로그를 확인해서 바로 바꾸도록 유도).
 *   - 이미 admin 계정이 있으면 아무것도 하지 않습니다 (기존 비밀번호 보존).
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class DataSeeder implements CommandLineRunner {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final ChannelProfileRepository channelProfileRepository;

    @Value("${ADMIN_SEED_PASSWORD:}")
    private String configuredPassword;

    private static final String SEED_CHARS =
            "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#%";

    @Override
    public void run(String... args) {
        seedChannelProfiles();
        if (userRepository.existsByUsername("admin")) {
            return;
        }

        String password = (configuredPassword != null && !configuredPassword.isBlank())
                ? configuredPassword
                : generateRandomPassword(16);

        User admin = User.builder()
                .username("admin")
                .password(passwordEncoder.encode(password))
                .email("admin@stockvideo.local")
                .role(UserRole.ADMIN)
                .build();
        userRepository.save(admin);

        if (configuredPassword != null && !configuredPassword.isBlank()) {
            log.info("초기 admin 계정 생성 완료 (username=admin, ADMIN_SEED_PASSWORD 환경변수 값 사용)");
        } else {
            // 무작위 생성 비밀번호는 이 최초 1회 로그에서만 확인 가능합니다.
            // 반드시 지금 로그인해서 비밀번호를 바꾸거나, .env에 ADMIN_SEED_PASSWORD를
            // 설정하고 컨테이너를 다시 띄우세요.
            log.warn("=================================================================");
            log.warn(" 초기 admin 계정이 무작위 비밀번호로 생성되었습니다.");
            log.warn(" username: admin");
            log.warn(" password: {}", password);
            log.warn(" 이 비밀번호는 지금 이 로그에서만 확인할 수 있습니다.");
            log.warn(" 지금 바로 로그인해서 비밀번호를 변경하거나,");
            log.warn(" .env에 ADMIN_SEED_PASSWORD=원하는비밀번호 를 추가하고 재기동하세요.");
            log.warn("=================================================================");
        }
    }

    private void seedChannelProfiles() {
        if (channelProfileRepository.count() > 0) return;
        channelProfileRepository.save(ChannelProfile.builder()
                .channelId("channel_a").channelName("채널 A · 동전 캐릭터")
                .characterKey("coin_character")
                .characterStylePrompt("friendly Korean finance educator, green coin mascot, editorial 2D comic style")
                .voiceId("JBFqnCBsd6RMkjVDRZzb").build());
        channelProfileRepository.save(ChannelProfile.builder()
                .channelId("channel_b").channelName("채널 B · 돈뭉치 캐릭터")
                .characterKey("money_bundle_character")
                .characterStylePrompt("friendly Korean finance educator, money bundle mascot, editorial 2D comic style")
                .voiceId("EXAVITQu4vr4xnSDxMaL").build());
        log.info("기본 채널 프로필 2개를 생성했습니다. 관리자 화면에서 캐릭터/음성을 변경할 수 있습니다.");
    }

    private String generateRandomPassword(int length) {
        SecureRandom random = new SecureRandom();
        StringBuilder sb = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            sb.append(SEED_CHARS.charAt(random.nextInt(SEED_CHARS.length())));
        }
        return sb.toString();
    }
}
