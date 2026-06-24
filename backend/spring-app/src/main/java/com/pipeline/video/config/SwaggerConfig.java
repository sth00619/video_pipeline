package com.pipeline.video.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI openAPI() {
        String jwtScheme = "Bearer Auth";

        SecurityRequirement requirement = new SecurityRequirement().addList(jwtScheme);

        SecurityScheme scheme = new SecurityScheme()
                .name(jwtScheme)
                .type(SecurityScheme.Type.HTTP)
                .scheme("bearer")
                .bearerFormat("JWT");

        return new OpenAPI()
                .info(new Info()
                        .title("AI Video Pipeline API")
                        .description("AI 영상 자동화 파이프라인 — Phase 2 (쇼츠 구간 게이트 + 자율성 다이얼)")
                        .version("0.2.0"))
                .addSecurityItem(requirement)
                .components(new Components().addSecuritySchemes(jwtScheme, scheme));
    }
}
