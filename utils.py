import re

L = "A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ"
PART = re.compile(rf"^[{L}]+([ʻʼ’‘'`´\-][{L}]+)*$")
VOWELS = set("aeiouAEIOUаеёиоуыэюяАЕЁИОУЫЭЮЯўЎ")


def valid_name(raw):
    """Ism-familiya to'g'ri bo'lsa tozalangan holda qaytaradi, bo'lmasa None."""
    s = " ".join((raw or "").split())
    if not (5 <= len(s) <= 50):
        return None
    parts = s.split(" ")
    if not (2 <= len(parts) <= 4):          # ism + familiya (+ otasining ismi)
        return None
    if re.search(r"(.)\1{2,}", s.lower()):  # "aaaa", "!!!!" kabi
        return None
    out = []
    for p in parts:
        if not PART.match(p):               # raqam, emoji, belgi, havola yo'q
            return None
        if len(re.findall(rf"[{L}]", p)) < 2:
            return None
        if not any(ch in VOWELS for ch in p):   # "qwrt zxcv" kabi
            return None
        out.append(p[:1].upper() + p[1:].lower())
    return " ".join(out)
