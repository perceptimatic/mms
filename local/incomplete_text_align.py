import sys
import re
from collections import defaultdict, Counter
from minineedle import semiglobal
from copy import deepcopy

def cut_print(text, length=100):
    mid = length // 2
    truncated = (text[:mid] + " [...] " + text[-mid:]) if len(text) > length else text
    print(truncated)

class DecText():
    def __init__(self, doc_text):
        self.doc_text = re.sub("\n+", "\n", doc_text.strip())
        self.ali_info = []
        self.ali_text = ""
        self._extract_dec_ali_info()

    def _extract_dec_ali_info(self):
        for line in self.doc_text.splitlines():
            try:
                file, spk, start, end, word, utt_num = line.strip().split(maxsplit=5)
            except ValueError:
                continue
            start = int(round(float(start) * 100, 0))
            end = int(round(float(end) * 100, 0))
            utt_num = int(utt_num)
            
            self.ali_info.append(((file, spk, start, end), word, utt_num))

        self.ali_info = sorted(self.ali_info, key=lambda x: x[0][2])
        self.ali_text += " ".join([v[1] for v in self.ali_info])

class BeamHypothesis():
    def __init__(self, dec_starts, alis, scores, utt_nums):
        self.dec_starts = dec_starts
        self.alis = alis
        self.scores = scores
        self.utt_nums = utt_nums

        self.bt_dec_starts = []
        self.bt_alis = []
        self.bt_scores = []
        self.bt_utt_nums = []

    def update(self, new_dec_start, new_alis, score, utt_num):
        self.dec_starts.append(new_dec_start)
        self.alis.append(new_alis)
        self.scores.append(score)
        self.utt_nums.append(utt_num + sum(self.bt_utt_nums))

    def backtrack(self):
        self.bt_utt_nums.append(self.utt_nums.pop())
        self.bt_dec_starts.append(self.dec_starts.pop())
        self.bt_alis.append(self.alis.pop())
        self.bt_scores.append(self.scores.pop())

    def clean_backtrack(self):
        self.bt_dec_starts = []
        self.bt_alis = []
        self.bt_scores = []
        self.bt_utt_nums = []

    def repair_backtrack(self):
        self.bt_dec_starts.reverse()
        self.bt_alis.reverse()
        self.bt_scores.reverse()
        self.bt_utt_nums.reverse()

        self.dec_starts.extend(self.bt_dec_starts)
        self.alis.extend(self.bt_alis)
        self.scores.extend(self.bt_scores)
        self.utt_nums.extend(self.bt_utt_nums)

        self.bt_dec_starts = []
        self.bt_alis = []
        self.bt_scores = []
        self.bt_utt_nums = []

    def flatten_alis(self):
        self.alis = [ali for ali_sublist in self.alis for ali in ali_sublist]

def get_subhyps(hyp, ref, branch, utt_nums):
    new_hyps = [BeamHypothesis(deepcopy(hyp.dec_starts), deepcopy(hyp.alis), deepcopy(hyp.scores), deepcopy(hyp.utt_nums)) for k in range(branch)]
    dec_text = " ".join(decodings.ali_text.split(" ")[hyp.dec_starts[-1]:])
    alignment = semiglobal.SemiGlobal(ref, dec_text)
    alignment.k_align(branch)
    for k in range(branch):
        ref_ali = "".join([str(x) for x in alignment._change_gap_char(alignment.alignments[k]._alseq1)])
        dec_ali = "".join([str(x) for x in alignment._change_gap_char(alignment.alignments[k]._alseq2)])

        char_correspondance = list(zip(ref_ali, dec_ali))
        word_index_correspondance = []
        word_correspondance = []
        word_alis = defaultdict(list)
        utt_alis = []
        ref_word_num = 0
        dec_word_num = 0

        ref_word_correspondance = ""
        dec_word_correspondance = ""
        for pair in char_correspondance:
            if pair[0] != " ":
                ref_word_correspondance += pair[0]
            if pair[1] != " ":
                dec_word_correspondance += pair[1]
            if pair[0] == " " or pair[1] == " ":
                word_correspondance.append((ref_word_correspondance, dec_word_correspondance))
                word_index_correspondance.append((ref_word_num, dec_word_num))
                if pair[0] == " ":
                    ref_word_num += 1
                if pair[1] == " ":
                    dec_word_num += 1
                ref_word_correspondance = ""
                dec_word_correspondance = ""
        word_correspondance.append((ref_word_correspondance, dec_word_correspondance))
        word_index_correspondance.append((ref_word_num, dec_word_num))

        # print(word_correspondance)
        # print(word_index_correspondance)

        #TESTING
        global out_message

        for i, (ref_index, dec_index) in enumerate(word_index_correspondance):
            if not all(x == "-" for x in word_correspondance[i][0]):
                dec_ali_info, _, dec_utt_num = decodings.ali_info[hyp.dec_starts[-1] + dec_index]
                word_alis[ref_index].append((dec_ali_info, word_correspondance[i][0].replace("-", ""), dec_utt_num))
        
        # print(word_alis)

        ref_alis = []
        for ref_index, info_list in word_alis.items():
            file = info_list[0][0][0]
            spk = Counter({info[0][1] for info in info_list}).most_common(1)[0][0]
            word_start = info_list[0][0][2]
            word_end = info_list[-1][0][3]
            word = "".join([info[1] for info in info_list])
            dec_utt_num = Counter({info[2] for info in info_list}).most_common(1)[0][0]
            word_merged_info = (file, spk, word_start, word_end)
            ref_alis.append((word_merged_info, word, dec_utt_num))
            
        # print(ref_alis)
        prev_utt = -1
        utt_start = 0
        utt_end = 0
        utt_text = ""
        for i, (word_merged_info, word, dec_utt_num) in enumerate(ref_alis):
            file, spk, word_start, word_end = word_merged_info
            if i == 0:
                utt_start = word_start
                utt_end = word_end
                utt_text = word
                prev_utt = dec_utt_num
            else:
                if prev_utt != dec_utt_num:
                    utt_merged_info = (file, spk, utt_start, utt_end)
                    utt_alis.append((utt_merged_info, utt_text))
                    utt_start = word_start
                    utt_end = word_end
                    utt_text = word
                    prev_utt = dec_utt_num
                else:
                    utt_text += " " + word
                    utt_end = word_end
        utt_end = word_end
        utt_merged_info = (file, spk, utt_start, utt_end)
        utt_alis.append((utt_merged_info, utt_text))

        # print(utt_alis)

        if " ".join([ali[1] for ali in utt_alis]) != ref:
            print(" ".join([ali[1] for ali in utt_alis]))
            print(ref)
            sys.exit()
        # sys.exit()

        dec_start = next((i for i, char in enumerate(dec_ali) if char != "-")) if any(c not in "-" for c in dec_ali) else len(ref)
        text_ali_penalty = ((dec_start) / len(ref)) ** 0.5
        normed_score = round((alignment.alignments[k]._score / len(ref)) - (text_ali_penalty), 4)

        # print(utt_alis)
        # print(collapsed_utt_alis)
        if k == 0 and out_message:
            print(f"__________________ {k} __________________")
            if text_ali_penalty != 0:
                print("unpenalized:", str(round((alignment.alignments[k]._score / len(ref_ali)), 4)))
                print("text alignment penalty:", str(round(-text_ali_penalty, 4)))
            print("score: ", str(normed_score))
            cut_print(f"ref_ali: {ref_ali}")
            cut_print(f"dec_ali: {dec_ali}")
            cut_print(f"ref text: {ref}")
            cut_print(f"dec text: {dec_text}")
            # if len(word_correspondance) > 6:
            #     print("word corr: " + str(word_correspondance[:3]) + "..." + str(word_correspondance[-3:]))
            # else:
            #     print("word corr: " + str(word_correspondance))    
            # print("word alis: " + str(word_alis))
            # print("utt alis: " + str(utt_alis))
            print("_______________________________________")

        # print(dec_word_num + 1)
        new_hyps[k].update(min(len(decodings.ali_text.split(" ")) - 1, hyp.dec_starts[-1] + dec_word_num + 1), utt_alis, normed_score, utt_nums)
    
    return new_hyps

dec_tws_path = sys.argv[1]
ref_txt_path = sys.argv[2]
out_trn_path = sys.argv[3]

# turn these into options
branch = 1
beam_width = 1
retries = 10
cutoff = 0.6
# turn these into options

with open(dec_tws_path) as f:
    decodings = DecText(f.read())

refs = []

with open(ref_txt_path) as f:
    for line in f:
        line = line.strip()
        if line:
            refs.append(line)

# print(decodings.doc_text[:500])
# print(decodings.ali_info[:10])
# print(decodings.ali_text[:100])

# print(refs)

hyps = [BeamHypothesis([0], [], [], [])]
subhyps = []
unaligned = 0
unaligned_text = ""

for i, ref in enumerate(refs):
    # print("utt_num:", utt_num)
    # print("ref:", ref)
    if i == 0:
        out_message = True
        for hyp in hyps:
            subhyps = get_subhyps(hyp, ref, branch, 1)
            out_message = False
            # print([hyp.dec_starts for hyp in subhyps])
            # print([hyp.scores for hyp in subhyps])
            # print([hyp.alis for hyp in subhyps])
        # sys.exit()
    else:
        for j in range(retries):
            new_subhyps = []
            out_message = True
            for subhyp in subhyps:
                backtrack_position = sum(subhyp.bt_utt_nums)
                new_ref = " ".join(refs[max(0, i-backtrack_position):i+1])
                branch_hyps = get_subhyps(subhyp, new_ref, branch, backtrack_position+1)
                out_message = False
                new_subhyps.extend(branch_hyps)
                # print([hyp.dec_starts for hyp in branch_hyps])
                # print([hyp.scores for hyp in branch_hyps])
                # print([hyp.alis for hyp in branch_hyps])
            new_subhyps = sorted(new_subhyps, key= lambda x: x.scores[-1], reverse=True)[:beam_width]
            if [subhyp for subhyp in new_subhyps if subhyp.scores[-1] > cutoff]:
                for new_subhyp in new_subhyps:
                    new_subhyp.clean_backtrack()
                subhyps = new_subhyps
                break
            elif j != (retries - 1):
                for subhyp in subhyps:
                    subhyp.backtrack()
                backtrack_position = sum(subhyp.bt_utt_nums)
                print("moving back " + str(subhyp.utt_nums[-1]) + " utt(s)")
                cut_print(f"retrying alignment using: {" ".join(refs[max(0, i-backtrack_position):i+1])}")
                cut_print(f"now aligning to: {" ".join(decodings.ali_text.split(" ")[subhyp.dec_starts[-1]:])}")
            else:
                for subhyp in subhyps:
                    subhyp.repair_backtrack()
                unaligned += 1
                unaligned_text += ref + f" (ref {i})" + "\n"
                print(f"{ref} not aligned to any point in the decoding")
                print("_______________________________________________")

print(f"# of unaligned utts: {unaligned}")
print(f"{unaligned_text}")

out_text = []


with open(out_trn_path, "w") as f:
    hyp = subhyps[0]
    hyp.flatten_alis()
    for info, utt in hyp.alis:
        file, spk, start, end = info
        f.write(f"{utt} ({spk}_{start}_{end}_{file})\n")
        out_text.append(utt)
    if unaligned:
        f.write("\n\n\n")
        f.write(f"# of unaligned utts: {unaligned}\n")
        f.write("unaligned text:\n")
        f.write(unaligned_text)

# if " ".join(out_text) != " ".join(refs):
#     refs_words = " ".join(refs).split(" ")
#     out_words = " ".join(out_text).split(" ")

#     print("ref doesnt match output")
# else:
#     print("ref matches output")
