package com.pipeline.video.config;

import com.pipeline.video.domain.User;
import com.pipeline.video.domain.UserRole;
import com.pipeline.video.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 초기 admin 계정 시딩.
 * 기존 InMemoryUserDetailsManager(admin/admin1234) → DB 기반으로 전환하면서
 * 최초 실행 시 admin 계정이 없으면 자동 생성.
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class DataSeeder implements CommandLineRunner {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Override
    public void run(String... args) {
        if (!userRepository.existsByUsername("admin")) {
            User admin = User.builder()
                    .username("admin")
                    .password(passwordEncoder.encode("admin1234"))
                    .email("admin@stockvideo.local")
                    .role(UserRole.ADMIN)
                    .build();
            userRepository.save(admin);
            log.info("초기 admin 계정 생성 완료 (username=admin, password=admin1234)");
        }
    }
}
