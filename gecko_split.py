import argparse
import glob
import os
from pydub import AudioSegment
import random
from pydub.generators import WhiteNoise
import json


def partition(l, pred):
    yes, no = [], []
    for e in l:
        if pred(e):
            yes.append(e.rstrip('\n\r'))
        else:
            no.append(e.rstrip('\n\r'))
    return yes, no


def terms_to_string(terms):
    sentence = ' '.join(term["text"] for term in terms)
    return sentence.replace(' ,', ',').replace(' .', '.')


def main():
    parser = argparse.ArgumentParser(description='Split audio based on gecko transcript.')
    parser.add_argument('--output', required=True, help='output directory')
    parser.add_argument('--media', required=True, help='input directory')
    parser.add_argument('--name', required=True, help='name of project')
    parser.add_argument('--min', default=200, type=int, help='min duration of clip')
    parser.add_argument('--max', default=13000, type=int, help='max duration of clip')
    parser.add_argument('--lead', default=50, help='amount to trim at beginning')
    parser.add_argument('--trail', default=100, help='amount to trim at end')
    parser.add_argument('--partition', default=.9, help='max duration of clip')
    args = parser.parse_args()

    output_dir = '{0}/{1}'.format(args.output, args.name)
    audio_dir = '{0}/wavs/22050/{1}'.format(args.media, args.name)
    transcript_dir = '{0}/transcripts/{1}'.format(args.media, args.name)
    gecko_dir = '{0}/gecko/{1}'.format(args.media, args.name)

    print(output_dir, audio_dir, transcript_dir, gecko_dir)

    white_noise = WhiteNoise().to_audio_segment(duration=100*1000).low_pass_filter(10000).high_pass_filter(200)
    white_noise = white_noise.apply_gain(-60 - white_noise.dBFS).set_frame_rate(22050)

    half_sec_silence = AudioSegment.silent(duration=500)
    quarter_sec_silence = AudioSegment.silent(duration=250)

    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    if not os.path.isdir(output_dir+'/wavs'):
        os.mkdir(output_dir+'/wavs')

    pad_silence = False
    train_txt = []
    dummy_txt = []

    train_set = []
    val_set = []
    wg_set = []

    flowtron_txt = []

    cntr = 0

    for filepath in sorted(glob.glob("{0}/*.transcript.json".format(transcript_dir)), key=os.path.getmtime):
        print(filepath)
        transcript_basename = os.path.basename(filepath)
        gecko_path = '{0}/{1}'.format(gecko_dir, transcript_basename)
        audio_basename = os.path.splitext(os.path.splitext(transcript_basename)[0])[0]
        audio_path = '{0}/{1}'.format(audio_dir, audio_basename)
        audio_file = AudioSegment.from_wav(audio_path)

        base_clip_name = os.path.splitext(os.path.basename(audio_path))[0]

        is_auto_transcript = True

        if os.path.exists(gecko_path):
            print('gecko transcript exits', gecko_path)
            filepath = gecko_path
            is_auto_transcript = False


        with open(filepath) as json_file:
            json_data = json.load(json_file)
            print(filepath)
            for i, monologue in enumerate(json_data["monologues"]):

                sentence = terms_to_string(monologue["terms"])
                if sentence[-1] != '.' or sentence[-1] != ',' or sentence[-1] != '?':
                    sentence = sentence + '.'

                clip_name = "{0}_{1:0>4d}.wav".format(base_clip_name, i)

                clip_path = "{0}/wavs/{1}".format(output_dir, clip_name)

                start = max(monologue["start"] * 1000 - args.lead, 0)
                end = monologue["end"] * 1000 + args.trail

                duration = end - start

                is_empty = len(sentence) == 0 or sentence.isspace()

                include = args.min <= duration <= args.max and not is_empty

                if duration > 9000:
                    cntr = cntr + 1
                    print("long clips: ", cntr)

                print('path:', clip_path, 'Sentence:', sentence, 'duration:', duration, "include:", include)

                if not include:
                    continue
                if pad_silence:
                    clip_audio = quarter_sec_silence + audio_file[start:end] + half_sec_silence
                else:
                    clip_audio = audio_file[start:end]

                clip_audio.export(clip_path, format="wav")

                wg_set.append('{}/wavs/{}'.format(output_dir, clip_name, sentence))
                train_txt.append('{}/wavs/{}|{}'.format(output_dir, clip_name, sentence))
                dummy_txt.append('{}/{}|{}'.format('DUMMY', clip_name, sentence))
                flowtron_txt.append('{}/wavs/{}|{}|0'.format(output_dir, clip_name, sentence))

    dummy_filelist = '{}/dummy_{}_all.txt'.format(output_dir, args.name)
    complete_filelist = '{}/{}_all.txt'.format(output_dir, args.name)
    train_filelist = '{}/{}_train.txt'.format(output_dir, args.name)
    validate_filelist = '{}/{}_val.txt'.format(output_dir, args.name)
    wg_filelist = '{}/{}_wg.txt'.format(output_dir, args.name)

    with open(complete_filelist, 'w', encoding='utf-8') as f:
        f.write('\n'.join(train_txt))
    with open(dummy_filelist, 'w', encoding='utf-8') as f:
        f.write('\n'.join(dummy_txt))

    lines = train_txt  # open(complete_filelist, 'r', encoding='utf-8').readlines()
    lines1, lines2 = partition(lines, lambda x: random.random() < args.partition)

    train_set.extend(lines1)
    val_set.extend(lines2)

    flowtron_train, flowtron_val = partition(flowtron_txt, lambda x: random.random() < args.partition)

    flowtron_val_file = '{}/{}_flowtron_val.txt'.format(output_dir, args.name)
    flowtron_train_file = '{}/{}_flowtron_train.txt'.format(output_dir, args.name)

    with open(wg_filelist, 'w', encoding='utf-8') as f:
        f.write('\n'.join(wg_set))

    with open(flowtron_train_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(flowtron_train))
    with open(flowtron_val_file, 'w', encoding='utf-8') as f:
        f.writelines('\n'.join(flowtron_val))

    with open(train_filelist, 'w', encoding='utf-8') as f:
        f.write('\n'.join(train_set))
    with open(validate_filelist, 'w', encoding='utf-8') as f:
        f.writelines('\n'.join(val_set))


if __name__ == "__main__":
    main()

