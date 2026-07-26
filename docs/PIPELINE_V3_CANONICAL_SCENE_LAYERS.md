# Canonical Scene-Layer Pipeline v3

The pipeline no longer asks an image model to simultaneously preserve a
character identity, draw a scene, reserve a chart surface, and understand
foreground occlusion. Each final cartoon still has this fixed order:

`clean illustrated background → verified in-world data surface → canonical character alpha layer → editorial text`

## Required artifacts per pose-library scene

- `scene_NNN_bg.png`: clean plate, generated with an explicit ban on mascot,
  person, arm, hand, finger, pointer, text, and numbers.
- `scene_NNN_bg_source.png`: immutable source for deterministic information
  surface retries.
- `scene_NNN.png`: final composited still.
- `scene_NNN.foreground-mask.png`: full-frame alpha mask of the canonical
  character. It includes any palm/finger/pointer pixels.
- `scene_NNN.scene-layers.json`: z-order, actual foreground bounds, pose asset
  checksum, canonical character id, and resume inputs.

The alpha character layer is always assembled after the surface renderer.
Therefore the character's opaque hand pixels naturally cover a screen, paper,
or chart when they overlap. The surface detector is no longer expected to
infer a generated hand from a flattened scene.

## Identity lock

`character_library_worker` writes `identity_manifest.json` for every pose
library. It contains a channel-specific canonical character id, the shared
cartoon style lock, and checksums for generated pose assets. The final scene
manifest records both the canonical id and selected pose checksum. A scene
using a legacy integrated generation path is not identity-locked and must not
be mixed with these canonical pose-library scenes in an approved sequence.

## Information graphics

Verified graphics are only written onto the clean plate's detected physical
prop. The palette is restrained to navy ink, warm gold emphasis, muted gray,
and a single red risk accent—no turquoise dashboard UI. Too-small, occluded,
or unsupported surfaces continue to use the explicit one-to-one data cutaway
fallback instead of a floating chart.

## Resume behaviour

On retry or resume, the worker re-renders the information surface from the
background source and then rebuilds the foreground alpha composition. It never
writes a revised chart over the final frame, which prevents a revised graphic
from covering a glove, palm, or finger.
