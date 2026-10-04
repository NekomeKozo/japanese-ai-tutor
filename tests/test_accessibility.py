"""Contrast and native form semantics; not a WCAG certification."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'frontend'


def luminance(hex_color):
    rgb = [int(hex_color[i:i+2], 16)/255 for i in (1,3,5)]
    rgb = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(rgb,(.2126,.7152,.0722)))


def ratio(a,b):
    values = sorted([luminance(a),luminance(b)])
    return (values[1]+.05)/(values[0]+.05)


def test_core_text_and_control_contrast():
    css = (ROOT/'styles.css').read_text(encoding='utf-8')
    tokens = dict(re.findall(r'--([\w-]+):(#[a-f\d]{6})',css))
    for text,bg in [('ink','page'),('muted','page'),('muted','surface'),('accent','soft'),('on-accent','accent'),('error','error-bg')]:
        a = tokens.get(text,'#ffffff')
        b = tokens.get(bg,'#ffffff')
        assert ratio(a,b) >= 4.5, (text,bg,ratio(a,b))
    assert ratio(tokens['control-border'],'#ffffff') >= 3
    assert ratio(tokens['focus'],'#ffffff') >= 3
    assert 'input::placeholder,textarea::placeholder { color:var(--muted); opacity:1; }' in css


class Controls(HTMLParser):
    def __init__(self):
        super().__init__(); self.labels=set(); self.controls=[]; self.label_depth=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='label':
            self.label_depth+=1
            if attrs.get('for'): self.labels.add(attrs['for'])
        if tag in ('input','select','textarea'):
            self.controls.append((attrs,self.label_depth>0))
    def handle_endtag(self,tag):
        if tag=='label': self.label_depth-=1


def test_static_forms_have_native_labels():
    for name in ['index.html','access.html']:
        parsed=Controls(); parsed.feed((ROOT/name).read_text(encoding='utf-8'))
        for attrs,wrapped in parsed.controls:
            assert wrapped or attrs.get('id') in parsed.labels or attrs.get('aria-label'), (name,attrs.get('id'))
