#!/usr/bin/env bash

local="$(pwd -P)/local"

usage="Usage: $0 [-h] [-o] [-d DIR] [-e DIR] [-o DIR] [-w NAT] [-a POSNUM] [-b NUM] [-l NNINT] [-t NUM] [-m NUM] [-s NAT] [-i DIR] [-r]"
data=perrony_raw_data
exp=exp/mms
out=eafs
width=100
alpha_inv=1
beta=1
lm_ord=0
merge_thresh=1
min_len=0.1
max_len=30
dec_partitions=(train test dev)
bootstrap_samples=0

help="Decode + create .eaf files with an mms-lsah model

Options
    -h          Display this help message and exit
    -d DIR      The data directory (default: '$data')
    -e DIR      The experiment directory (default: '$exp')
    -o DIR      The .eaf output directory (default: '$out')
    -w NAT      pyctcdecode's beam width (default: $width)
    -a POSNUM   pyctcdecode's alpha, inverted (default: $alpha_inv)
    -b NUM      pyctcdecode's beta (default: $beta)
    -l NNINT    n-gram LM order. 0 is greedy; 1 is prefix with no LM (default: $lm_ord)
    -t NUM      The max time elapsed before merging segments by the same speaker (default: $merge_thresh)
    -m NUM      The maximum segment length (default: $min_len)
    -M NUM      The maximum segment length (default: $max_len)
    -s NAT      Bootstrap samples. 0 is no bootstrap (default: $bootstrap_samples)
    -i DIR      The path to the model, or Hugging Face id (default: '$id_model')
    -r          Whether to remove the interviewer from the diarization"

while getopts "hd:e:o:w:a:b:l:t:m:M:s:i:r" name; do
    case $name in
        h)
            echo "$usage"
            echo ""
            echo "$help"
            exit 0;;
        d)
            data="$OPTARG";;
        e)
            exp="$OPTARG";;
        o)
            out="$OPTARG";;
        w)
            width="$OPTARG";;
        a)
            alpha_inv="$OPTARG";;
        b)
            beta="$OPTARG";;
        l)
            lm_ord="$OPTARG";;
        t)
            merge_thresh="$OPTARG";;
        m)
            min_len="$OPTARG";;
        M)
            max_len="$OPTARG";;
        s)
            bootstrap_samples="$OPTARG";;
        i)
            id_model="$OPTARG";;
        r)
            remove_inter=true;;
        *)
            echo -e "$usage"
            exit 1;;
    esac
done
shift $(($OPTIND - 1))
if [ ! -d "$data" ]; then
    echo -e "'$data' is not a directory! set -d appropriately!"
    exit 1
fi
if [ ! -d "$exp" ]; then
    echo -e "'$exp' is not a directory! set -e appropriately!"
    exit 1
fi
if ! mkdir -p "$out" 2> /dev/null; then
    echo -e "Could not create '$out'! set -o appropriately!"
    exit 1
fi
if ! [ "$width" -gt 0 ] 2> /dev/null; then
    echo -e "$width is not a natural number! set -w appropriately!"
    exit 1
fi
if (( "$(bc -l <<< "$alpha_inv < 0")" )); then
    echo -e "$alpha_inv is not greater than 0! set -a appropriately!"
    exit 1
fi
if ! [[ "$beta" =~ ^-?[0-9]+\.?[0-9]*$ ]] 2> /dev/null; then
    echo -e "$beta is not a real number! set -b appropriately, or add a leading zero!"
    exit 1
fi
if ! [ "$lm_ord" -ge 0 ] 2> /dev/null; then
    echo -e "$lm_ord is not a non-negative int! set -l appropriately!"
    exit 1
fi
if (( "$(bc -l <<< "$merge_thresh < 0")" )); then
    echo -e "$merge_thresh is not greater than 0! set -t appropriately!"
    exit 1
fi
if (( "$(bc -l <<< "$max_len < 0")" )); then
    echo -e "$max_len is not greater than 0! set -m appropriately!"
    exit 1
fi
if ! [ "$bootstrap_samples" -ge 0 ] 2> /dev/null; then
    echo -e "$bootstrap_samples is not a non-negative int! set -n appropriately!"
    exit 1
fi

set -eo pipefail

#TEST
part=
out_dir="data/train"
remove_tsv_path="intervals_w_spks_to_remove.tsv"
spk_num_tsv_path="file_spk_num.tsv"

function split_file () {
    file="$1"
    wav_file="$2"
    out_dir="$3"
    wav_name="$(basename "$wav_file" .wav)"
    file_dur="$(soxi -D "$wav_file")"

    # utterance consists of one line of the ali file in the format [speaker] [start] [end]
    while read -r utterance; do
        IFS=$'\t' read -ra utt_data <<< "$utterance"
        speaker_name="${utt_data[0]}"
        utt_start="${utt_data[1]}"
        utt_end="${utt_data[2]}"
        printf -v output_name "%s_%08.0f_%08.0f_%s" \
             "$speaker_name" "$(bc -l <<< "$utt_start * 100")" "$(bc -l <<< "$utt_end * 100")" "$(sed 's/_w//' <<< $wav_name)"
        sox "$wav_file" -b 16 -r 16k -c 1 "$out_dir/$output_name.wav" trim "$utt_start" ="$utt_end"
        echo "test" > "$out_dir/$output_name.txt"

    done < "$file"
}

mkdir -p "$out_dir"

for wav_file in "$data"/"$part"/*.mp3; do
    tws_file="eafs/$(basename "$wav_file" .wav).tws"
    split_file "$merge" "$wav_file" "$out_dir"
done

exit 20

:> "$out_dir/.done"

#TEST

only=false
dec_partitions=(HB_split)

for part in HB_split; do
    if ! [ -f "$data/$part/metadata.csv" ]; then
        echo "Creating metadata.csv in '$data/$part'"
        mkdir -p "$data/$part"
        ./mms.py compile-metadata "$data/$part"
        if $only; then exit 0; fi
    fi

    if ! [ -f "$data/$part/trn" ]; then
        echo "Creating reference trn file in '$data/$part'"
        :> "$data/$part/trn"
        for file in "$data"/"$part"/*.wav; do
            filename="$(basename "$file" .wav)"
            printf "%s (%s)\n" "$(< "${file%%.wav}.txt")" "$filename" >> "$data/$part/trn"
        done
        if $only; then exit 0; fi
    fi
done


if [ "$lm_ord" = 0 ]; then
    for part in "${dec_partitions[@]}"; do
        if  ! [ -f "$exp/decode_incomplete_text_ali_work/${part}_greedy.tws" ]; then
            echo "Greedily decoding '$data/$part'"
            mkdir -p "$exp/decode_incomplete_text_ali_work"
            ./mms.py word-decode \
                "$exp" "$data/$part" "$exp/decode_incomplete_text_ali_work/${part}_greedy.csv_"
            mv "$exp/decode_incomplete_text_ali_work/${part}_greedy.csv"{_,}
            python3 "$local"/csv_to_tws.py "$exp/decode_incomplete_text_ali_work/${part}_greedy."{csv,tws_}
            mv "$exp/decode_incomplete_text_ali_work/${part}_greedy.tws"{_,}
            if $only; then exit 0; fi
        fi
    done
else

    if [ ! -f "prep/ngram_lm.py" ]; then
        echo "Initializing Git submodule"
        git submodule update --init --remote prep
        if $only; then exit 0; fi
    fi

    for part in "${dec_partitions[@]}"; do
        if  ! [ -f "$exp/decode/logits/$part/.done" ]; then
            echo "Dumping logits of '$data/$part'"
            mkdir -p "$exp/decode/logits/$part"
            ./mms.py decode \
                --logits-dir "$exp/decode/logits/$part" \
                "$exp" "$data/$part" "/dev/null"
            touch "$exp/decode/logits/$part/.done"
            if $only; then exit 0; fi
        fi
    done

    if [ "$lm_ord" = 1 ]; then
        name="w${width}_nolm"
        alpha_inv=1
        beta=1
        lm_args=( )
    else
        name="w${width}_lm${lm_ord}_ainv${alpha_inv}_b${beta}"
        lm="$exp/lm/${lm_ord}gram.arpa"
        lm_args=( --lm "$lm" )
        if ! [ -f "$lm" ]; then
            echo "Constructing '$lm'"
            mkdir -p "$exp/lm"
            ./prep/ngram_lm.py -o $lm_ord -t 0 1 -f "etc/lm_text.txt" > "${lm}_"
            mv "$lm"{_,}
            if $only; then exit 0; fi
        fi
    fi

    if ! [ -f "$exp/token2id" ]; then
        echo "Constructing '$exp/token2id'"
        ./mms.py vocab-to-token2id "$exp/"{vocab.json,token2id}
        if $only; then exit 0; fi
    fi

    for part in "${dec_partitions[@]}"; do
        if ! [ -f "$exp/decode/${part}_${name}.trn" ]; then
            echo "Decoding $part"
            ./logits-to-trn-via-torchctcdecode.py \
                --char "${lm_args[@]}" \
                --words "etc/lm_words_torchaudio.txt" \
                --width $width \
                --beta $beta \
                --alpha-inv $alpha_inv \
                --part "$part" \
                --token2id "$exp/token2id" \
                "$exp/decode/"{logits/$part,${part}_$name.trn}
            if $only; then exit 0; fi
        fi
    done
fi

for part in "${dec_partitions[@]}"; do
    if  ! [ -f "$exp/decode_incomplete_text_ali_work/${part}_lang_id.trn" ]; then
        echo "Identifying languages in '$data/$part'"
        mkdir -p "$exp/decode_incomplete_text_ali_work"
        ./mms.py get-language \
            "$id_model" "$data/$part" "$exp/decode_incomplete_text_ali_work/${part}_lang_id.csv_"
        mv "$exp/decode_incomplete_text_ali_work/${part}_lang_id.csv"{_,}
        ./mms.py metadata-to-trn \
            "$exp/decode_incomplete_text_ali_work/${part}_lang_id."{csv,trn_}
        mv "$exp/decode_incomplete_text_ali_work/${part}_lang_id.trn"{_,}
        if $only; then exit 0; fi
    fi
done

#TEST

out_dir="eafs/v3"
mkdir -p "$out_dir"
python3 "$local"/trn_to_eaf.py "exp/decoding_exp/decode/tangram_split_greedy.trn" "exp/decoding_exp/decode/tangram_split_lang_id.trn" "$out_dir"