"""Create the approved Goldie reference sheet once, before production renders."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

import requests

PROMPT = """Character reference sheet for an ORIGINAL Korean finance mascot named Goldie.
2D Korean webtoon illustration, bold clean dark-brown outlines, saturated cel shading, plain light-gray studio background.
Goldie is an anthropomorphic gold coin with embossed dotted rim, expressive eyes and eyebrows, rosy cheeks, white-gloved hands,
thin dark legs and brown shoes. Show front view in navy analyst vest and gold tie, three-quarter view, and five facial expressions
(confident, shocked, dizzy, furious, excited). Every view is exactly the same character and proportions. No text, labels, numbers,
logos or watermarks. 16:9 composition. Never imitate another channel's mascot."""


def _image(response: dict) -> bytes | None:
    for candidate in response.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or {}
            if inline.get("data"):
                return base64.b64decode(inline["data"])
    image = response.get("output_image") or response.get("outputImage") or {}
    if image.get("data"):
        return base64.b64decode(image["data"])
    for step in response.get("steps") or []:
        for item in step.get("content") or []:
            if item.get("type") == "image" and item.get("data"):
                return base64.b64decode(item["data"])
    return None


def generate(output: Path, model: str) -> None:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
    payload = {"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9", "imageSize": "2K"}}}
    response = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", json=payload, headers={"Content-Type": "application/json", "x-goog-api-key": key}, timeout=180)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini character-sheet request failed ({response.status_code}): {response.text[:800]}")
    response.raise_for_status()
    raw = _image(response.json())
    if not raw:
        raise RuntimeError("Gemini did not return an image")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/app/assets/character/goldie_sheet_v1.png")
    parser.add_argument("--model", default="gemini-3-pro-image")
    args = parser.parse_args()
    generate(Path(args.out), args.model)
