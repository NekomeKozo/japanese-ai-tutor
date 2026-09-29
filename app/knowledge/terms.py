import re
from collections import Counter

from app.knowledge.normalize import match_text

STOP = set('a an the is are be been i you it to of in on for and or with what when how do does can please explain japanese grammar meaning difference between use means mean work make instead reading'.split())
ALIASES = {
    'te form': 'て形', 'te-form': 'て形', 'tai form': 'たい', 'want to': 'たい',
    'nagara': 'ながら', 'tari': 'たり', 'desu': 'です', 'masu': 'ます',
    'wa particle': 'は', 'ga particle': 'が', 'ni particle': 'に', 'de particle': 'で',
}


def terms(text: str, *, expand=False) -> Counter:
    text = match_text(text)
    if expand:
        text += ' ' + ' '.join(value for key, value in ALIASES.items() if key in text)
    result = Counter('w:' + word for word in re.findall(r'[a-z][a-z0-9]{1,40}', text) if word not in STOP)
    for run in re.findall(r'[\u3040-\u30ff\u3400-\u9fff]+', text):
        for n in (2, 3):
            result.update('j:' + run[i:i+n] for i in range(len(run)-n+1))
        # Single particles/kanji are useful when explicitly separated in text.
        if len(run) == 1:
            result['j:' + run] += 1
    return result
