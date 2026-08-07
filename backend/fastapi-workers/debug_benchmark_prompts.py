import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from run_five_benchmark_scenes import BENCHMARK_SCENES
from app.utils.art_direction import direct_scenes
from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.images_worker import ImagesWorker

directed = direct_scenes(BENCHMARK_SCENES)
planned = attach_v5_scene_contracts(directed)
worker = ImagesWorker()

for i, (meta, item) in enumerate(zip(BENCHMARK_SCENES, planned)):
    prompt_en = worker._build_prompt_from_narration(
        narration=meta['content'],
        scene_type=item['archetype'],
        title=item['specific_props'],
        visual_mode="archetype_explainer",
        core_entities=meta['core_entities'],
        core_figures=meta['core_figures']
    )
    print(f"=" * 80)
    print(f"Scene {i+1}: {meta['title']}")
    print(f"Input Narration: \"{meta['content']}\"")
    print(f"Core Entities: {meta['core_entities']}")
    print(f"Core Figures: {meta['core_figures']}")
    print(f"Assigned Archetype: {item['archetype']}")
    print(f"Archetype Reason: {item['archetype_reason']}")
    print(f"Prompt_EN Full Text:\n{prompt_en}\n")
