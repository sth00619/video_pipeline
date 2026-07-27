import hashlib

from PIL import Image

from app.workers.images_worker import ImagesWorker


def test_regenerated_surface_replaces_preserved_source_and_fingerprint(tmp_path):
    original = tmp_path / "scene.png"
    regenerated = tmp_path / "scene_raw.png"
    Image.new("RGB", (960, 540), "#23344A").save(original)
    Image.new("RGB", (960, 540), "#F6F4D2").save(regenerated)
    source = tmp_path / "scene_source.png"
    Image.new("RGB", (960, 540), "#101820").save(source)
    scene = {
        "source_image_path": str(source),
        "info_surface_final_fingerprint": "old",
        "info_surface_final_sha256": "old",
        "final_image_path": str(original),
    }

    ImagesWorker()._replace_with_regenerated_surface_source(scene, str(regenerated), str(original))

    assert scene["source_image_path"] == str(source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(original.read_bytes()).hexdigest()
    assert "info_surface_final_fingerprint" not in scene
    assert "info_surface_final_sha256" not in scene
    assert "final_image_path" not in scene
