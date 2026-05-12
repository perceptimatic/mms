import sys
from pathlib import Path

cvs_file = sys.argv[1]
tws_file = sys.argv[2]

current_utt_info = ""
utt_num = -1

with open(cvs_file, "r") as f:
    with open(tws_file, "w") as g:
        next(f)
        for line in f:
            info, word, word_start, word_end = line.split(",")
            spk, file_start, file_end, file = info.split("_")
            word_start = float(word_start)
            word_end = float(word_end)
            file_start = int(file_start) / 100
            file_end = int(file_end) / 100

            if info != current_utt_info:
                utt_num += 1
                current_utt_info = info
            
            g.write(Path(file).stem + "\t" + 
                    spk + "\t" + str(round(file_start + word_start,2)) +
                    "\t" + str(round(file_start + word_end,2)) + 
                    "\t" + word + "\t" + str(utt_num) + "\n")