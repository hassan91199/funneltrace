# Demo video

Records the real app, then adds a synthetic voice and captions. Outputs go to `docs/demo/`.

```bash
python -m venv .venv && .venv/bin/pip install -r demo/requirements.txt   # needs ffmpeg and Google Chrome
.venv/bin/python demo/narrate.py    # script.json -> build/*.mp3 + timings (needs internet: edge-tts)
# start the API and frontend against an EMPTY database (see the root README), then:
.venv/bin/python demo/record.py     # drives the real UI, writes build/raw.webm + build/cues.json
.venv/bin/python demo/compose.py docs/demo/demo.mp4
(cd backend && PYTHONPATH=. python ../demo/hubspot_check.py --delete)  # verify + remove sandbox contacts
```

`record.py` waits for the real scoring, drafting and CRM sync, so narration follows the screen
instead of a fixed schedule. Edit `script.json` to change the words, then rerun `narrate.py`.
The thumbnail is `thumbnail/mockup.html`, rendered at 1000x750 with headless Chrome.
