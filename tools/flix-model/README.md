---
license: apache-2.0
language:
  - de
  - gsw
library_name: ctranslate2
base_model: Flix-AI/flix-swissgerman-full
tags:
  - automatic-speech-recognition
  - whisper
  - faster-whisper
  - swiss-german
---

# Flix Swiss German for faster-whisper (CTranslate2)

[Flix-AI/flix-swissgerman-full](https://huggingface.co/Flix-AI/flix-swissgerman-full) converted
to the [CTranslate2](https://github.com/OpenNMT/CTranslate2) format, so it can be used with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) without converting it yourself.
Used by [Verbalis](https://github.com/malaxy25/verbalis), which downloads it on first use.

```python
from faster_whisper import WhisperModel

model = WhisperModel("malaxy25/flix-swissgerman-ct2", device="cpu", compute_type="int8")
segments, info = model.transcribe("meeting.wav", language="de")
```

## How it was made

```bash
ct2-transformers-converter --model Flix-AI/flix-swissgerman-full --output_dir flix-swissgerman-ct2 \
    --copy_files tokenizer.json preprocessor_config.json --quantization float16
```

The weights are stored as float16; `compute_type` can still be chosen when loading
(`int8` on CPU, `float16` on GPU).

## Credits and licence

- Fine-tune: Flix-AI, Apache 2.0 – all credit for the model goes to the original authors.
- Base model: OpenAI Whisper large-v3, MIT.
- This conversion: Apache 2.0, unchanged weights in a different format.

The model writes Swiss German as Standard German (a translation, not a verbatim transcript).
