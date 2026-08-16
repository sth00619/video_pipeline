package com.pipeline.video.controller;

import com.pipeline.video.domain.ReferenceChannel;
import com.pipeline.video.domain.ReferenceChannelStatus;
import com.pipeline.video.domain.ReferenceChannelTier;
import com.pipeline.video.security.JwtUtil;
import com.pipeline.video.service.ReferenceChannelService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReferenceChannelController.class)
@Import(ReferenceChannelControllerTest.MethodSecurityConfiguration.class)
class ReferenceChannelControllerTest {

    @TestConfiguration
    @EnableMethodSecurity
    static class MethodSecurityConfiguration {
    }

    @jakarta.annotation.Resource
    MockMvc mockMvc;

    @MockitoBean
    ReferenceChannelService service;

    @MockitoBean
    JwtUtil jwtUtil;

    @Test
    void adminCanUseCrudEndpoints() throws Exception {
        ReferenceChannel channel = channel();
        when(service.list(false)).thenReturn(java.util.List.of(channel));
        when(service.create(any(), eq("admin"))).thenReturn(channel);
        when(service.update(anyLong(), any())).thenReturn(channel);
        when(service.softDelete(anyLong())).thenReturn(channel);

        mockMvc.perform(get("/api/admin/reference-channels")
                        .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].channelId").value("UCverified"));

        mockMvc.perform(post("/api/admin/reference-channels")
                        .with(user("admin").roles("ADMIN"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("""
                                {"displayName":"검증 채널","channelRef":"@verified","displayOrder":10}
                                """))
                .andExpect(status().isOk());

        mockMvc.perform(put("/api/admin/reference-channels/1")
                        .with(user("admin").roles("ADMIN"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("""
                                {"displayName":"수정 채널","tier":"LARGE","displayOrder":20,"active":true}
                                """))
                .andExpect(status().isOk());

        mockMvc.perform(delete("/api/admin/reference-channels/1")
                        .with(user("admin").roles("ADMIN"))
                        .with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    void editorCannotUseCrudEndpoints() throws Exception {
        mockMvc.perform(get("/api/admin/reference-channels")
                        .with(user("editor").roles("EDITOR")))
                .andExpect(status().isForbidden());

        mockMvc.perform(post("/api/admin/reference-channels")
                        .with(user("editor").roles("EDITOR"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{" +
                                "\"displayName\":\"채널\"," +
                                "\"channelRef\":\"@channel\"}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(put("/api/admin/reference-channels/1")
                        .with(user("editor").roles("EDITOR"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"displayName\":\"채널\"}"))
                .andExpect(status().isForbidden());

        mockMvc.perform(delete("/api/admin/reference-channels/1")
                        .with(user("editor").roles("EDITOR"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedRequestReturns401() throws Exception {
        mockMvc.perform(get("/api/admin/reference-channels"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidRequestReturns400WithKoreanMessage() throws Exception {
        mockMvc.perform(post("/api/admin/reference-channels")
                        .with(user("admin").roles("ADMIN"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"displayName\":\"\",\"channelRef\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("필수")));
    }

    private static ReferenceChannel channel() {
        return ReferenceChannel.builder()
                .id(1L)
                .displayName("검증 채널")
                .channelId("UCverified")
                .youtubeTitle("검증 채널")
                .tier(ReferenceChannelTier.LARGE)
                .validationStatus(ReferenceChannelStatus.VALID)
                .active(true)
                .displayOrder(10)
                .build();
    }
}
