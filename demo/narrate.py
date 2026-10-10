"""Step 1: synthesize one narration clip per scene and time each caption phrase.

Writes build/<scene>.mp3 and build/narration.json (clip duration plus start/end of
every phrase, taken from the voice's own word timings). Needs internet: edge-tts
calls Microsoft's online voices.
"""
import asyncio
import json
import subprocess
from pathlib import Path

import aiohttp
import edge_tts

HERE = Path(__file__).parent
BUILD = HERE / "build"


def clip_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout)


async def fetch(text: str, voice: str, path: Path) -> list:
    """The service throttles bursts with a 403, so wait and retry."""
    for attempt in range(8):
        words = []
        try:
            comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
            with open(path, "wb") as audio:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        audio.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        start = chunk["offset"] / 1e7
                        words.append((start, start + chunk["duration"] / 1e7))
            return words
        except aiohttp.WSServerHandshakeError as exc:
            wait = 20 * (attempt + 1)
            print(f"  {exc.status} from the voice service, retrying in {wait}s")
            await asyncio.sleep(wait)
    raise SystemExit("voice service kept refusing; try again later")


async def synth(scene: dict, voice: str) -> dict:
    text = " ".join(scene["phrases"])
    path = BUILD / f"{scene['id']}.mp3"
    cache = BUILD / f"{scene['id']}.words.json"
    key = {"voice": voice, "text": text}
    if path.exists() and cache.exists() and json.loads(cache.read_text())["key"] == key:
        words = json.loads(cache.read_text())["words"]
    else:
        words = await fetch(text, voice, path)
        cache.write_text(json.dumps({"key": key, "words": words}))
        await asyncio.sleep(3)
    counts = [len(p.split()) for p in scene["phrases"]]
    total = clip_seconds(path)
    if len(words) != sum(counts):
        raise SystemExit(f"{scene['id']}: {len(words)} word timings for {sum(counts)} words")
    phrases, i = [], 0
    for text_part, n in zip(scene["phrases"], counts):
        phrases.append({"text": text_part, "start": words[i][0], "end": words[i + n - 1][1]})
        i += n
    return {"id": scene["id"], "audio": path.name, "seconds": total, "phrases": phrases}


async def main() -> None:
    BUILD.mkdir(exist_ok=True)
    script = json.loads((HERE / "script.json").read_text())
    scenes = [await synth(s, script["voice"]) for s in script["scenes"]]
    (BUILD / "narration.json").write_text(json.dumps(scenes, indent=2))
    for s in scenes:
        print(f"{s['id']:8} {s['seconds']:5.1f}s  {len(s['phrases'])} phrases")
    print(f"total narration {sum(s['seconds'] for s in scenes):.1f}s")


asyncio.run(main())
