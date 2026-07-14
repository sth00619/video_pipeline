package com.pipeline.video;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class VideoPipelineApplication {

	public static void main(String[] args) {
		SpringApplication.run(VideoPipelineApplication.class, args);
	}
}
