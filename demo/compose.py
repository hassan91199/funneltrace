"""Step 3: combine the recording, the narration clips and captions into demo.mp4.

Captions go in a bar below the app so they never cover the UI. Narration clips are
placed at the cue times record.py wrote, so the voice follows what is on screen.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / "build"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BUILD / "demo.mp4"
BAR = 100  # px of caption bar under the 900px-high app


def stamp(t: float) -> str:
    return f"{int(t // 3600):02}:{int(t % 3600 // 60):02}:{int(t % 60):02},{round(t % 1 * 1000):03}"


def main() -> None:
    narration = json.loads((BUILD / "narration.json").read_text())
    cues = json.loads((BUILD / "cues.json").read_text())
    duration = cues["_duration"] + 0.5

    srt, n = [], 0
    for scene in narration:
        start = cues[scene["id"]]["start"]
        for phrase in scene["phrases"]:
            n += 1
            srt.append(
                f"{n}\n{stamp(start + phrase['start'])} --> {stamp(start + phrase['end'] + 0.25)}\n"
                f"{phrase['text']}\n"
            )
    (BUILD / "captions.srt").write_text("\n".join(srt))

    style = (
        "FontName=DejaVu Sans,FontSize=10,Bold=1,PrimaryColour=&HFFFFFF&,BorderStyle=1,"
        "Outline=0,Shadow=0,Alignment=2,MarginV=9"
    )
    video = (
        f"[0:v]pad=1440:{900 + BAR}:0:0:color=0x0b0d11,"
        f"subtitles={BUILD / 'captions.srt'}:force_style='{style}'[v]"
    )
    inputs, delays = ["-i", str(BUILD / "raw.webm")], []
    for i, scene in enumerate(narration, start=1):
        inputs += ["-i", str(BUILD / scene["audio"])]
        ms = round(cues[scene["id"]]["start"] * 1000)
        delays.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(narration) + 1))
    audio = (
        ";".join(delays)
        + f";{mix}amix=inputs={len(narration)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=9[a]"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{video};{audio}",
         "-map", "[v]", "-map", "[a]", "-t", f"{duration:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUT)],
        check=True,
    )
    print(f"wrote {OUT} ({duration:.1f}s)")


main()
