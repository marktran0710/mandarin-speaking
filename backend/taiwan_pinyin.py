"""
Taiwan Mandarin (國語/臺灣華語) pronunciation overrides for pypinyin.

Call apply() once at startup (imported in main.py, ai_feedback.py, etc.).
Two main differences from Mainland Standard (普通話):
  1. Some words have entirely different base readings (e.g. 垃圾 lè sè vs lā jī).
  2. Taiwan preserves full tones for syllables that became neutral (輕聲) in
     Mainland Mandarin (e.g. 喜歡 xǐ huān vs xǐ huan).
"""

from pypinyin import load_phrases_dict


def apply():
    load_phrases_dict({
        # ── Different base reading ────────────────────────────────────────
        "垃圾": [["lè"], ["sè"]],

        # ── Directional complements keep full tone in Taiwan ──────────────
        "出來": [["chū"], ["lái"]],
        "進來": [["jìn"], ["lái"]],
        "回來": [["huí"], ["lái"]],
        "起來": [["qǐ"], ["lái"]],
        "下來": [["xià"], ["lái"]],
        "上來": [["shàng"], ["lái"]],
        "過來": [["guò"], ["lái"]],
        "出去": [["chū"], ["qù"]],
        "進去": [["jìn"], ["qù"]],
        "回去": [["huí"], ["qù"]],

        # ── Common compound words: neutral → full tone ────────────────────
        "告訴": [["gào"], ["sù"]],
        "知道": [["zhī"], ["dào"]],
        "喜歡": [["xǐ"], ["huān"]],
        "朋友": [["péng"], ["yǒu"]],
        "東西": [["dōng"], ["xī"]],
        "地方": [["dì"], ["fāng"]],
        "意思": [["yì"], ["sī"]],
        "客氣": [["kè"], ["qì"]],
        "窗戶": [["chuāng"], ["hù"]],
        "時候": [["shí"], ["hòu"]],
        "先生": [["xiān"], ["shēng"]],
        "學生": [["xué"], ["shēng"]],
        "事情": [["shì"], ["qíng"]],
        "麻煩": [["má"], ["fán"]],
        "厲害": [["lì"], ["hài"]],
        "豆腐": [["dòu"], ["fǔ"]],
        "謝謝": [["xiè"], ["xiè"]],
        "頭髮": [["tóu"], ["fà"]],
        "石頭": [["shí"], ["tóu"]],
        "木頭": [["mù"], ["tóu"]],
        "饅頭": [["mán"], ["tóu"]],
        "念頭": [["niàn"], ["tóu"]],
        "拳頭": [["quán"], ["tóu"]],
        "枕頭": [["zhěn"], ["tóu"]],
        "沒有": [["méi"], ["yǒu"]],
        "規矩": [["guī"], ["jǔ"]],
        "力氣": [["lì"], ["qì"]],
        "運氣": [["yùn"], ["qì"]],
        "消息": [["xiāo"], ["xī"]],
        "熱鬧": [["rè"], ["nào"]],
        "笑話": [["xiào"], ["huà"]],
        "故事": [["gù"], ["shì"]],
        "將來": [["jiāng"], ["lái"]],
        "眼睛": [["yǎn"], ["jīng"]],
        "耳朵": [["ěr"], ["duǒ"]],
        "腦袋": [["nǎo"], ["dài"]],
        "嘴巴": [["zuǐ"], ["bā"]],
        "肚子": [["dù"], ["zǐ"]],
        "鼻子": [["bí"], ["zǐ"]],
        "脖子": [["bó"], ["zǐ"]],
        "帽子": [["mào"], ["zǐ"]],
        "椅子": [["yǐ"], ["zǐ"]],
        "桌子": [["zhuō"], ["zǐ"]],
        "箱子": [["xiāng"], ["zǐ"]],
        "盒子": [["hé"], ["zǐ"]],
        "鞋子": [["xié"], ["zǐ"]],
        "杯子": [["bēi"], ["zǐ"]],
        "瓶子": [["píng"], ["zǐ"]],
        "本子": [["běn"], ["zǐ"]],
        "句子": [["jù"], ["zǐ"]],
        "日子": [["rì"], ["zǐ"]],
        "樣子": [["yàng"], ["zǐ"]],
        "孩子": [["hái"], ["zǐ"]],
        "兔子": [["tù"], ["zǐ"]],
        "獅子": [["shī"], ["zǐ"]],
        "猴子": [["hóu"], ["zǐ"]],
    })
