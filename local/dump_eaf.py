#!/usr/bin/env python

import sys
import pympi
import argparse
import re


DEFT_PATTERNS = (
    r"OrthographicWords",
    r"MorphemeBreak",
    r"Gloss",
    r".*[Tt]ranslation.*",
)

def pos_int(val: str) -> int:
    val = int(val)
    if val < 1:
        raise argparse.ArgumentTypeError("not positive")
    return val


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Convert eaf file to segments and transcripts"
    )
    parser.add_argument(
        "in_file",
        metavar="IN",
        nargs="?",
        default="-",
    )
    parser.add_argument(
        "out_file",
        metavar="OUT",
        nargs="?",
        type=argparse.FileType("wt"),
        default=sys.stdout,
    )
    parser.add_argument("--float-precision", type=pos_int, default=2)
    parser.add_argument("--min-utt-dur-ms", type=pos_int, default=250)
    parser.add_argument("--min-diff-between-utts-ms", type=pos_int, default=0)
    parser.add_argument(
        "--exclude-tier-patterns",
        type=re.compile,
        nargs="*",
        default=[re.compile(x) for x in DEFT_PATTERNS],
    )
    options = parser.parse_args(args)

    eaf = pympi.Eaf(options.in_file)
    for tier_name in eaf.get_tier_names():
        bad = False
        for pattern in options.exclude_tier_patterns:
            if pattern.match(tier_name):
                bad = True
                break
        if bad:
            continue
        tier_name_ = tier_name.replace(" ", "_")
        lsms, lems, lutt = None, None, None
        for anno in eaf.get_annotation_data_for_tier(tier_name):
            if eaf.get_parameters_for_tier(tier_name)["TIER_ID"] == "Sentence":
                # anno may have 3 or 4 elements, just want the first 3
                spk = eaf.get_parameters_for_tier(tier_name)["TIER_ID"]
                sms, ems, utt = anno[:3]
                utt = utt.strip()
                # just get rid of any annotation that may be a problem
                # if any(pattern.search(utt) for pattern in PROBLEM_PATTERNS):
                #     continue
                if not utt:
                    continue
                if lutt is not None:
                    if sms - lems < options.min_diff_between_utts_ms:
                        lems, lutt = ems, lutt + " " + utt
                        continue
                    lems += options.min_diff_between_utts_ms
                    lsms = max(0, lsms - options.min_diff_between_utts_ms)
                    print(
                        f"{spk}\t"
                        f"{lsms / 1000:.{options.float_precision}f}\t"
                        f"{lems / 1000:.{options.float_precision}f}\t"
                        f"{lutt}",
                        file=options.out_file,
                    )
                if ems - sms >= options.min_utt_dur_ms:
                    lsms, lems, lutt = sms, ems, utt
        if lutt is not None:
            # we don't pad the end of the very last utterance
            lsms = max(0, lsms - options.min_diff_between_utts_ms)
            print(
                f"{spk}\t"
                f"{lsms / 1000:.{options.float_precision}f}\t"
                f"{lems / 1000:.{options.float_precision}f}\t"
                f"{lutt}",
                file=options.out_file,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
