import hashlib
import json

from PIL import Image, ImageDraw

from app.services.scene_layers import (
    compose_character_foreground,
    load_layer_manifest,
    write_layer_manifest,
)


def _pose(path):
    image = Image.new("RGBA", (120, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 110, 110), fill="#F7BD22")
    # This deliberately protrudes toward the information surface like a hand.
    draw.rounded_rectangle((0, 105, 118, 142), radius=16, fill="#F7BD22")
    draw.rectangle((38, 125, 82, 235), fill="#0B2340")
    image.save(path)


def test_foreground_alpha_is_above_surface_and_emits_a_real_mask(tmp_path):
    plate = tmp_path / "surface.png"
    pose = tmp_path / "poses" / "pointing.png"
    output = tmp_path / "scene.png"
    pose.parent.mkdir()
    Image.new("RGB", (1920, 1080), "#243A52").save(plate)
    _pose(pose)
    (pose.parent / "identity_manifest.json").write_text(json.dumps({
        "version": "3.0", "canonical_character_id": "coin-identity-1",
    }), encoding="utf-8")

    metadata = compose_character_foreground(
        str(plate), str(pose.parent), "pointing", str(output), placement="right third",
    )

    assert metadata["z_order"] == ["clean_background", "verified_info_surface", "character_foreground", "editorial_text"]
    assert metadata["canonical_character_id"] == "coin-identity-1"
    assert metadata["pose_asset_sha256"] == hashlib.sha256(pose.read_bytes()).hexdigest()
    mask = Image.open(metadata["foreground_mask_path"])
    assert mask.getbbox() is not None
    # At an opaque foreground pixel the final frame contains mascot colour,
    # rather than the blue information-surface plate beneath it.
    opaque_pixel = next((index for index, alpha in enumerate(mask.getdata()) if alpha > 250))
    x, y = opaque_pixel % mask.width, opaque_pixel // mask.width
    assert Image.open(output).convert("RGB").getpixel((x, y))[0] > 200


def test_layer_manifest_is_resume_safe(tmp_path):
    output = tmp_path / "scene.png"
    payload = {"surface_image_path": "/tmp/plate.png", "z_order": ["background", "foreground"]}
    write_layer_manifest(str(output), payload)
    assert load_layer_manifest(str(output)) == payload
