#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画面上のキーボード(Keyboard ウィンドウ)の、キーの配置と、キーを押したときに送るもの

Switch のソフトウェアキーボードと同じ並びの配置を持ち、それぞれの文字を「マイコンのキーボード機能で打つ半角の文字」に直す。
送れるのは半角の文字だけなので(Commands/SwitchKeyboard.py)、かな・カナは、ローマ字に直して送る
(Switch 側が、ローマ字入力の、かな・カナのモードになっている必要がある)。画面(tkinter)には触れない。

- ページ: PAGE_HIRAGANA / PAGE_KATAKANA / PAGE_LOWER / PAGE_UPPER / PAGE_SYMBOL
- かな・カナのページには、濁点・半濁点・小さい字のページがある(「小字゛゜」で切り替える)
- 半角の文字に直せない文字(「※」など)は、送れない(sendable が False)

Switch 側の入力モード(かな / カナ / 英字)は、キーボードのキーで切り替えられる。実機(Switch のキーボード画面。
日本語・ローマ字入力)で、キーを送って画面の変化を見て確かめた動き(2026-10-11):
    「ひらがな/カタカナ」のキー: かな → カナ、カナ → かな、英字 → かな
    「半角/全角」のキー        : かな → 英字、カナ → 英字、英字 → かな
    → 「ひらがな/カタカナ」「半角/全角」の順に押すと、どのモードからでも、英字になる(mode_keys)
    打っている途中の文字(確定前)は、モードを切り替えると、そのまま確定される。英字のモードで空白を打つと、その前までが確定される
    記号は、かな・カナのモードで [ ] , . - / ~ を打つと 「 」 、 。 ー ・ 〜 になり、英字のモードでは、半角の記号がそのまま入る
"""
from __future__ import annotations

PAGE_HIRAGANA = "hiragana"
PAGE_KATAKANA = "katakana"
PAGE_LOWER = "lower"
PAGE_UPPER = "upper"
PAGE_SYMBOL = "symbol"
PAGES = (PAGE_HIRAGANA, PAGE_KATAKANA, PAGE_LOWER, PAGE_UPPER, PAGE_SYMBOL)
# ページを選ぶボタンの文字
PAGE_LABELS = {PAGE_HIRAGANA: "あ", PAGE_KATAKANA: "ア", PAGE_LOWER: "a", PAGE_UPPER: "A", PAGE_SYMBOL: "1#※"}
# 濁点・半濁点・小さい字のページがあるページ
KANA_PAGES = (PAGE_HIRAGANA, PAGE_KATAKANA)
ROWS = 5
COLUMNS = 11

# Switch 側の入力モード
MODE_KANA = "kana"
MODE_KATAKANA = "katakana"
MODE_ALNUM = "alnum"
MODE_LABELS = {MODE_KANA: "かな", MODE_KATAKANA: "カナ", MODE_ALNUM: "英字"}
# ページ → そのページのキーを打つときの、Switch 側の入力モード
PAGE_MODES = {
    PAGE_HIRAGANA: MODE_KANA, PAGE_KATAKANA: MODE_KATAKANA, PAGE_LOWER: MODE_ALNUM, PAGE_UPPER: MODE_ALNUM,
    PAGE_SYMBOL: MODE_ALNUM,
}
# モードを切り替えるキー(名前は Commands.SwitchKeyboard の KEY と同じ)
KEY_HIRAGANA = "JP_HIRAGANA"
KEY_HANZEN = "JP_HANZEN"
# 今のモードが分からないときに、そのモードにするキーの並び(初めの 2 つで、どのモードからでも英字になる)
_RESET_KEYS = {
    MODE_ALNUM: (KEY_HIRAGANA, KEY_HANZEN),
    MODE_KANA: (KEY_HIRAGANA, KEY_HANZEN, KEY_HANZEN),
    MODE_KATAKANA: (KEY_HIRAGANA, KEY_HANZEN, KEY_HANZEN, KEY_HIRAGANA),
}
# 今のモードが分かっているときに、切り替えるキーの並び(今のモード, 目的のモード)
_STEP_KEYS = {
    (MODE_ALNUM, MODE_KANA): (KEY_HANZEN,),
    (MODE_ALNUM, MODE_KATAKANA): (KEY_HANZEN, KEY_HIRAGANA),
    (MODE_KANA, MODE_ALNUM): (KEY_HANZEN,),
    (MODE_KANA, MODE_KATAKANA): (KEY_HIRAGANA,),
    (MODE_KATAKANA, MODE_KANA): (KEY_HIRAGANA,),
    (MODE_KATAKANA, MODE_ALNUM): (KEY_HANZEN,),
}

# 配置(1 行が 11 文字。空白は、キーのないマス)。Switch のソフトウェアキーボードと同じ並び
_HIRAGANA = (
    "「わらやまはなたさかあ",
    "」をり　みひにちしきい",
    "ーんるゆむふぬつすくう",
    "?、れ　めへねてせけえ",
    "!。ろよもほのとそこお",
)
# 濁点・半濁点・小さい字(右から、が行・ざ行・だ行・ば行・ぱ行・小さい母音・小さい「やゆよ」・そのほか)
_HIRAGANA_SMALL = (
    "　　　っゃぁぱばだざが",
    "　　　ゎ　ぃぴびぢじぎ",
    "　　　ゔゅぅぷぶづずぐ",
    "　　　　　ぇぺべでぜげ",
    "　　　　ょぉぽぼどぞご",
)
_LOWER = ("abcdefghijk", "lmnopqrstuv", "wxyz　　　　　　　", "　　　　　　　　　　　", "　　　　　　　　　　　")
_SYMBOL = (
    "1234567890-",
    "!@#$%^&*()_",
    "~`=\\+{}|[]¥",
    "<>;:\"',.?/〜",
    "ヵヶ【】・※〃ゝ々仝〆",
)

# かな 1 文字 → ローマ字(Switch のローマ字入力で、その 1 文字になる打ち方。小さい字は x を付ける)
_ROMAJI = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "si", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "ti", "つ": "tu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "hu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "wo", "ん": "nn",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "zi", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "di", "づ": "du", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ぁ": "xa", "ぃ": "xi", "ぅ": "xu", "ぇ": "xe", "ぉ": "xo",
    "ゃ": "xya", "ゅ": "xyu", "ょ": "xyo", "っ": "xtu", "ゎ": "xwa", "ゔ": "vu",
}  # fmt: skip
# かなのページの記号 → 半角の文字(ローマ字入力のモードで打つと、その記号になるキー)
_PUNCTUATION = {"「": "[", "」": "]", "ー": "-", "、": ",", "。": ".", "・": "/", "〜": "~", "～": "~", "　": " "}
_HIRAGANA_START, _HIRAGANA_END, _KATAKANA_OFFSET = 0x3041, 0x3096, 0x60


def to_katakana(text: str) -> str:
    """ひらがなを、カタカナにする(ほかの文字は、そのまま)"""
    return "".join(chr(ord(c) + _KATAKANA_OFFSET) if _HIRAGANA_START <= ord(c) <= _HIRAGANA_END else c for c in text)


def to_hiragana(text: str) -> str:
    """カタカナを、ひらがなにする(ほかの文字は、そのまま)"""
    return "".join(
        chr(ord(c) - _KATAKANA_OFFSET)
        if _HIRAGANA_START + _KATAKANA_OFFSET <= ord(c) <= _HIRAGANA_END + _KATAKANA_OFFSET
        else c
        for c in text
    )


def page_rows(page: str, small: bool = False) -> list:
    """
    ページの配置を、5 行 × 11 列の文字のリストで返す(キーのないマスは、空文字)
    small: かな・カナのページで、濁点・半濁点・小さい字のページにするか(ほかのページでは、使わない)
    知らないページは KeyError
    """
    if page == PAGE_HIRAGANA:
        rows = _HIRAGANA_SMALL if small else _HIRAGANA
    elif page == PAGE_KATAKANA:
        rows = [to_katakana(row) for row in (_HIRAGANA_SMALL if small else _HIRAGANA)]
    elif page == PAGE_LOWER:
        rows = _LOWER
    elif page == PAGE_UPPER:
        rows = [row.upper() for row in _LOWER]
    elif page == PAGE_SYMBOL:
        rows = _SYMBOL
    else:
        raise KeyError(page)
    return [["" if c == "　" else c for c in row] for row in rows]


def typed_text(character: str) -> str | None:
    """
    その 1 文字を打つために送る、半角の文字(列)を返す。送れない文字は None
    (半角の英字・数字・記号は、そのまま。かな・カナは、ローマ字。全角の英数字・記号は、半角にする)
    """
    if len(character) != 1:
        return None
    code = ord(character)
    if 0x20 <= code <= 0x7E:
        return character
    if 0xFF01 <= code <= 0xFF5E:
        # 全角の英数字・記号(!〜~)は、半角にする
        return chr(code - 0xFEE0)
    if character in _PUNCTUATION:
        return _PUNCTUATION[character]
    return _ROMAJI.get(to_hiragana(character))


def sendable(character: str) -> bool:
    """その文字を送れるか"""
    return typed_text(character) is not None


def convert_text(text: str) -> tuple[str, list]:
    """
    文字列を、送る半角の文字列に直す。戻り値: (送る文字列, 送れない文字(出てきた順。重複なし))
    送れない文字があるときは、送る文字列は、その文字を除いたもの(呼ぶ側は、送らないこと)
    """
    parts, invalid = [], []
    for character in text:
        typed = typed_text(character)
        if typed is None:
            if character not in invalid:
                invalid.append(character)
        else:
            parts.append(typed)
    return "".join(parts), invalid


def mode_keys(current: str | None, target: str) -> tuple:
    """
    Switch 側の入力モードを、current から target にするために押すキーの並び(KEY_HIRAGANA / KEY_HANZEN)を返す。
    current: 今のモード(分からないときは None。どのモードからでも target になる並びを返す)
    同じモードなら、空。知らないモードは KeyError
    """
    if current == target:
        return ()
    if current is None:
        return _RESET_KEYS[target]
    return _STEP_KEYS[(current, target)]


def character_mode(character: str, current: str | None = None) -> str | None:
    """
    その 1 文字を打つときの、Switch 側の入力モードを返す(送れない文字は None)。
    ひらがな → かな、カタカナ → カナ、半角・全角の英数字と記号 → 英字。
    「 」 、 。 ー ・ 〜 は、かな・カナのどちらでも打てるので、current がそのどちらかなら、そのまま(それ以外は、かな)
    """
    if typed_text(character) is None:
        return None
    code = ord(character)
    if 0x20 <= code <= 0x7E or 0xFF01 <= code <= 0xFF5E or character == "\u3000":
        return MODE_ALNUM
    if _HIRAGANA_START <= code <= _HIRAGANA_END:
        return MODE_KANA
    if _HIRAGANA_START + _KATAKANA_OFFSET <= code <= _HIRAGANA_END + _KATAKANA_OFFSET:
        return MODE_KATAKANA
    return current if current in (MODE_KANA, MODE_KATAKANA) else MODE_KANA


def segment_text(text: str) -> tuple[list, list]:
    """
    文字列を、Switch 側の入力モードごとの区切りに分ける。
    戻り値: ([(モード, 送る半角の文字列), ...], 送れない文字(出てきた順。重複なし))
    例: "ポケモンGet!" → [(MODE_KATAKANA, "pokemonn"), (MODE_ALNUM, "Get!")]
    """
    segments, invalid = [], []
    mode = None
    for character in text:
        target = character_mode(character, mode)
        if target is None:
            if character not in invalid:
                invalid.append(character)
            continue
        typed = typed_text(character)
        if segments and target == mode:
            segments[-1] = (mode, segments[-1][1] + typed)
        else:
            segments.append((target, typed))
            mode = target
    return segments, invalid


def has_kana(text: str) -> bool:
    """文字列に、かな・カナ(ローマ字に直して送る文字)が含まれるか"""
    return any(to_hiragana(c) in _ROMAJI or c in ("ー", "「", "」", "、", "。", "・") for c in text)
