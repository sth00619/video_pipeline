package com.pipeline.video;

import org.junit.jupiter.api.Test;

class VideoPipelineApplicationTests {

	@Test
	void applicationEntrypointIsAvailableWithoutInfrastructure() {
		VideoPipelineApplication.class.getDeclaredMethods();
	}

}
