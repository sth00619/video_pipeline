import os
import sys
import subprocess
import numpy as np
from PIL import Image
import shutil

def verify_motion(video_path: str):
    """
    Verifies that the intro (0-65s) has high motion (mean diff > 2.0)
    and the body (90s+) has zero motion outside of cuts (< 0.5).
    """
    print(f"Analyzing motion profile for: {video_path}")
    temp_dir = "temp_motion_frames"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Extract 1 frame per second from the video
    cmd = f'ffmpeg -i "{video_path}" -vf "fps=1" -vsync vfr "{temp_dir}/frame_%04d.png" -loglevel error -y'
    subprocess.run(cmd, shell=True, check=True)
    
    frames = sorted([f for f in os.listdir(temp_dir) if f.endswith(".png")])
    if len(frames) < 10:
        print("Error: Too few frames extracted.")
        shutil.rmtree(temp_dir)
        sys.exit(1)
        
    diffs = []
    for i in range(len(frames) - 1):
        img1 = Image.open(os.path.join(temp_dir, frames[i])).convert("L")
        img2 = Image.open(os.path.join(temp_dir, frames[i+1])).convert("L")
        
        arr1 = np.array(img1, dtype=np.float32)
        arr2 = np.array(img2, dtype=np.float32)
        
        mean_diff = np.mean(np.abs(arr1 - arr2))
        diffs.append(mean_diff)
        
    shutil.rmtree(temp_dir)
    
    # Check intro segment (first 60 seconds)
    intro_diffs = diffs[:60]
    # Check body segment (after 90 seconds)
    body_diffs = diffs[90:]
    
    mean_intro = np.mean(intro_diffs) if intro_diffs else 0
    # Filter out cuts (very high difference between frames)
    body_no_cuts = [d for d in body_diffs if d < 5.0]
    mean_body = np.mean(body_no_cuts) if body_no_cuts else 0
    
    print(f"Intro mean frame difference (0-60s): {mean_intro:.3f}")
    print(f"Body mean frame difference (90s+, no cuts): {mean_body:.3f}")
    
    intro_pass = mean_intro > 2.0
    body_pass = mean_body < 0.5
    
    print(f"Intro motion check: {'PASS' if intro_pass else 'FAIL'}")
    print(f"Body static check: {'PASS' if body_pass else 'FAIL'}")
    
    if not intro_pass or not body_pass:
         sys.exit(1)
    print("Verification completed successfully.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_motion_profile.py <video_path>")
        sys.exit(1)
    verify_motion(sys.argv[1])
