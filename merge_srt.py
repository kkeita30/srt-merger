import sys
import srt
import fugashi

tagger = fugashi.Tagger()

PUNCT_REMOVE = set("、。，．")

_KANJI_DIGIT = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"零":0,"〇":0}
_KANJI_UNIT  = {"十":10,"百":100,"千":1000}


def remove_punct(text):
    return "".join(c for c in text if c not in PUNCT_REMOVE)


def _parse_kanji_num(s):
    """
    純漢数字文字列を整数に変換する。
    算用数字が混在する場合は None を返して変換しない。
    """
    has_kanji  = any(c in _KANJI_DIGIT or c in _KANJI_UNIT or c == "万" for c in s)
    has_arabic = any("0" <= c <= "9" for c in s)
    if not has_kanji or has_arabic:
        return None

    result  = 0   # 万より上の積み上げ
    current = 0   # 万未満の積み上げ
    pending = None  # 直前の一桁数字

    for c in s:
        if c in _KANJI_DIGIT:
            pending = _KANJI_DIGIT[c]
        elif c in _KANJI_UNIT:
            unit = _KANJI_UNIT[c]
            current += (1 if pending is None else pending) * unit
            pending = None
        elif c == "万":
            if pending is not None:
                current += pending
                pending = None
            result += current * 10000
            current = 0

    if pending is not None:
        current += pending
    result += current
    return result


def convert_kanji_numbers(text):
    tokens = list(tagger(text))
    result = []
    i = 0
    while i < len(tokens):
        # 連続する数詞トークンをまとめる
        if tokens[i].feature.pos1 == "名詞" and tokens[i].feature.pos2 == "数詞":
            kanji_group = []
            while i < len(tokens) and tokens[i].feature.pos1 == "名詞" and tokens[i].feature.pos2 == "数詞":
                kanji_group.append(tokens[i].surface)
                i += 1
            combined = "".join(kanji_group)
            # 「十百千万」を含まない かつ 1文字だけの場合は変換しない
            has_unit = any(c in "十百千万" for c in combined)
            if not has_unit and len(combined) == 1:
                result.append(combined)
                continue
            converted = _parse_kanji_num(combined)
            result.append(str(converted) if converted is not None else combined)
        else:
            result.append(tokens[i].surface)
            i += 1
    return "".join(result)


def postprocess(text):
    text = remove_punct(text)
    text = convert_kanji_numbers(text)
    text = text.replace(" ", "").replace("\u3000", "")
    return text


def should_merge(prev_text, next_text):
    # ルール1: 結合したとき1形態素になる場合（単語の途中切れ）
    tokens_prev = list(tagger(prev_text))
    tokens_combined = list(tagger(prev_text + next_text))
    if len(tokens_combined) < len(tokens_prev):
        return True  # 結合で形態素が減った＝途中切れだった

    # ルール2: 次ブロックの先頭が助詞・助動詞
    if len(tokens_prev) >= len(tokens_combined):
        return False
    first_token = tokens_combined[len(tokens_prev)]
    first_pos = first_token.feature.pos1

    if first_pos in ["助詞", "助動詞"]:
        pass  # そのままTrue判定へ
    elif first_pos == "動詞":
        first_cForm = first_token.feature.cForm if hasattr(first_token.feature, 'cForm') else ""
        if first_cForm not in ["連用形-一般", "未然形-一般"]:
            return False
    else:
        return False

    if len(prev_text + next_text) <= 40:
        return True

    return False


def merge_subtitles(input_path):
    with open(input_path, encoding="utf-8") as f:
        subs = list(srt.parse(f.read()))

    merged = []
    i = 0
    while i < len(subs):
        current_text = subs[i].content.strip()
        current_start = subs[i].start
        current_end = subs[i].end
        i += 1  # 現在ブロックを消費

        while i < len(subs):
            next_text = subs[i].content.strip()
            judge = should_merge(remove_punct(current_text), remove_punct(next_text))
            if judge:
                current_text += next_text
                current_end = subs[i].end
                i += 1  # マージしたら次へ進み再判定
            else:
                break  # マージ不要なら終了

        merged.append(srt.Subtitle(
            index=len(merged) + 1,
            start=current_start,
            end=current_end,
            content=postprocess(current_text),
        ))

    extend_timestamps(merged)
    return merged


def dummy_convert(input_path, gap_sec=10):
    with open(input_path, encoding="utf-8") as f:
        subs = list(srt.parse(f.read()))

    groups = []
    i = 0
    while i < len(subs):
        group_start = subs[i].start
        group_end = subs[i].end
        i += 1

        while i < len(subs):
            gap = (subs[i].start - group_end).total_seconds()
            if gap <= gap_sec:
                group_end = subs[i].end
                i += 1
            else:
                break

        groups.append(srt.Subtitle(
            index=len(groups) + 1,
            start=group_start,
            end=group_end,
            content="※※※",
        ))

    return groups


def extend_timestamps(merged):
    for i in range(len(merged) - 1):
        gap = (merged[i + 1].start - merged[i].end).total_seconds()
        if gap < 10:
            merged[i].end = merged[i + 1].start
    return merged


def print_blocks(merged, count=30):
    print(f"合計ブロック数: {len(merged)}\n")
    for sub in merged[:count]:
        print(f"{sub.index}")
        print(f"{srt.timedelta_to_srt_timestamp(sub.start)} --> {srt.timedelta_to_srt_timestamp(sub.end)}")
        print(sub.content)
        print()


if __name__ == "__main__":
    import os

    args = sys.argv[1:]
    preview = "--preview" in args
    dummy = "--dummy" in args

    gap_sec = 10
    for a in args:
        if a.startswith("--gap="):
            gap_sec = float(a.split("=", 1)[1])
    args = [a for a in args if a not in ("--preview", "--dummy") and not a.startswith("--gap=")]

    if len(args) == 0:
        print("使い方: python merge_srt.py input.srt [output.srt] [--preview] [--dummy]", file=sys.stderr)
        sys.exit(1)

    input_path = args[0]

    if len(args) >= 2:
        output_path = args[1]
    else:
        base, ext = os.path.splitext(input_path)
        suffix = "_dummy" if dummy else "_merged"
        output_path = base + suffix + ext

    result = dummy_convert(input_path, gap_sec=gap_sec) if dummy else merge_subtitles(input_path)

    if preview:
        print("[プレビューモード] 先頭30ブロックを表示（保存しません）")
        print_blocks(result, count=30)
    else:
        with open(output_path, encoding="utf-8", mode="w") as f:
            f.write(srt.compose(result))
        print(f"保存完了: {output_path}")
        print_blocks(result, count=30)
