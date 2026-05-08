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

from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
from tqdm import tqdm

from .args import Options
from .data import load_partition

def get_language(options: Options):

    if torch.cuda.is_available():
        device = torch.cuda.current_device()
    else:
        device = "cpu"

    model = Wav2Vec2ForSequenceClassification.from_pretrained(
        options.language_model_id
    ).to(device)
    processor = Wav2Vec2Processor.from_pretrained(
        options.pretrained_model_id
    )

    ds = load_partition(options, "decode", processor)

    metadata_csv = options.metadata_csv.open("w")
    metadata_csv.write("file_name,sentence\n")

    for elem in tqdm(ds):
        input_dict = processor(
            elem["input_values"],
            sampling_rate=processor.feature_extractor.sampling_rate,
            return_tensors="pt",
            padding=True,
        )
        logits = model(input_dict.input_values.to(device)).logits.cpu()
        lang_id = logits.argmax(-1)[0].item()
        detected_lang = model.config.id2label[lang_id]
        metadata_csv.write(f"{elem['file_name']},{detected_lang}\n")

    return 0
