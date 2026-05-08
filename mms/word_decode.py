# Copyright 2024 Sean Robertson

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import torch
import sys

from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
from tqdm import tqdm

from .args import Options
from .data import load_partition

SPACE_PATTERN = re.compile(r"\s+")


def decode(options: Options):

    if torch.cuda.is_available():
        device = torch.cuda.current_device()
    else:
        device = "cpu"

    model = Wav2Vec2ForCTC.from_pretrained(
        options.model_dir, target_lang=options.lang
    ).to(device)
    processor = Wav2Vec2Processor.from_pretrained(
        options.model_dir, target_lang=options.lang
    )

    ds = load_partition(options, "decode", processor)

    metadata_csv = options.metadata_csv.open("w")
    metadata_csv.write("file_name,word,start,end\n")

    if options.logits_dir is not None:
        options.logits_dir.mkdir(exist_ok=True)

    for elem in tqdm(ds):
        sampling_rate = processor.feature_extractor.sampling_rate
        input_dict = processor(
            elem["input_values"],
            sampling_rate=sampling_rate,
            return_tensors="pt",
            padding=True,
        )
        logits = model(input_dict.input_values.to(device)).logits.cpu()
        if options.logits_dir is not None:
            pt = options.logits_dir / (os.path.splitext(elem["file_name"])[0] + ".pt")
            torch.save(logits[0, :, : processor.tokenizer.vocab_size], pt)
        greedy_path = logits.argmax(-1)[0]
        out = processor.decode(greedy_path, output_word_offsets=True)
        time_offset = model.config.inputs_to_logits_ratio / processor.feature_extractor.sampling_rate
        word_offsets = [
        {
            "text": d["word"],
            "start": round(d["start_offset"] * time_offset, 2),
            "end": round(d["end_offset"] * time_offset, 2),
        }
        for d in out.word_offsets
        ]
        for utt in word_offsets:
            metadata_csv.write(f"{elem['file_name']},{utt["text"]},{utt["start"]},{utt["end"]}\n")
    return 0
