---
license: mit
language:
  - de
  - gsw
library_name: ctranslate2
base_model: gcoli/whisper-large-v3-turbo-swiss-german-mit
tags:
  - automatic-speech-recognition
  - whisper
  - faster-whisper
  - swiss-german
---

# Swiss German Whisper turbo for faster-whisper (mirror)

An unchanged copy of the CTranslate2 version of
[gcoli/whisper-large-v3-turbo-swiss-german-mit](https://huggingface.co/gcoli/whisper-large-v3-turbo-swiss-german-mit)
(its `ct2/` folder), revision
[`{short}`](https://huggingface.co/gcoli/whisper-large-v3-turbo-swiss-german-mit/tree/{revision}).
It is kept here so that [Verbalis](https://github.com/malaxy25/verbalis), which uses it as its default model,
always gets exactly this tested version. Verbalis checks monthly whether the original has a newer one.

```python
from faster_whisper import WhisperModel

model = WhisperModel("malaxy/whisper-large-v3-turbo-swiss-german-ct2", device="cpu", compute_type="int8")
segments, info = model.transcribe("meeting.wav", language="de")
```

## Credits and licence

All credit for the model goes to its authors – see `ORIGINAL_README.md` (the original model card) and
`training_provenance.json`.

- Fine-tune: gcoli/whisper-large-v3-turbo-swiss-german-mit, MIT.
- Base model: OpenAI Whisper large-v3-turbo, MIT.
- Training data: FHNW/i4ds Swiss Parliaments Corpus (Bern) and Gemeinderat Zürich Audio Corpus, MIT –
  thanks to FHNW/i4ds for the corpora. Part of the labels came from OpenAI Whisper large-v3 (Apache 2.0).
- This copy: MIT, unchanged files.

The original card notes its limits: trained on parliamentary speech from Bern and Zürich; spontaneous
conversation and other dialects were not measured there; Whisper can leave out or invent text.
