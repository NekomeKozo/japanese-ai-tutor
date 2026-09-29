"""Write private metadata only; stdout contains aggregate counts."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.knowledge.extractors import inventory


def private_output(path):
    root = Path(__file__).resolve().parents[1] / 'knowledge_base'
    if root.is_symlink():
        raise ValueError('Private output root must not be a symlink')
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Generated artifacts must be under ignored knowledge_base/')
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=Path('reference'))
    parser.add_argument('--output', type=Path, default=Path('knowledge_base/inventory.json'))
    args = parser.parse_args()
    sources = inventory(args.reference)
    private_output(args.output).write_text(json.dumps([s.model_dump() for s in sources], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'files': len(sources), 'formats': dict(Counter(s.format for s in sources))}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Inventory failed:', type(exc).__name__)
        raise SystemExit(1)
