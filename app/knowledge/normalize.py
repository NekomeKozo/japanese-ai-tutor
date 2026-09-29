import re
import unicodedata


def normalize(text: str) -> str:
    """NFC preserves width distinctions, kana, kanji and meaningful punctuation."""
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub('[\u200b\ufeff\u00ad]', '', text)
    text = ''.join(c for c in text if c in '\n\t' or unicodedata.category(c) != 'Cc')
    text = '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def match_text(text: str) -> str:
    return unicodedata.normalize('NFKC', text).casefold()
