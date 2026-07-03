package com.pipeline.video.service;

import com.pipeline.video.domain.User;
import com.pipeline.video.domain.UserRole;
import com.pipeline.video.dto.RegisterRequest;
import com.pipeline.video.dto.UserResponse;
import com.pipeline.video.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회원가입 서비스.
 * 영상 작업자(EDITOR)는 자유 가입, 관리자 권한은 DB에서 수동 승급.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Transactional
    public UserResponse register(RegisterRequest request) {
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new IllegalStateException("이미 사용 중인 아이디입니다.");
        }
        if (userRepository.existsByEmail(request.getEmail())) {
            throw new IllegalStateException("이미 사용 중인 이메일입니다.");
        }
        if (request.getPassword() == null || request.getPassword().length() < 6) {
            throw new IllegalStateException("비밀번호는 6자 이상이어야 합니다.");
        }

        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .role(UserRole.EDITOR)  // 기본 EDITOR, ADMIN은 DB에서 수동 승급
                .build();

        User saved = userRepository.save(user);
        log.info("회원가입 완료: username={}, role={}", saved.getUsername(), saved.getRole());
        return UserResponse.from(saved);
    }

    public UserResponse getByUsername(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("사용자를 찾을 수 없습니다: " + username));
        return UserResponse.from(user);
    }
}
