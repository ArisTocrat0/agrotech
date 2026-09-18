"""Rebuild the supervised classifier from local labelled datasets, without prompts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from src.config import load_config
    from src.recognition.embeddings import DinoEmbeddingModel
    from src.recognition.reference_index import build_reference_index
    from src.recognition.autolearn import train_head
    config = load_config()['model']
    model = DinoEmbeddingModel(config['name'], 'auto', config['batch_size'])
    index = build_reference_index(ROOT / 'data/Сорняки', ROOT / 'artifacts/reference_index.pt',
                                  config['name'], model=model, crop_references=ROOT / 'data/Культуры')
    classifier = train_head(index, ROOT / 'artifacts/learned_classifier.pt')
    report = json.dumps(classifier.report, ensure_ascii=False, indent=2, allow_nan=False)
    (ROOT / 'artifacts/learning_report.json').write_text(report, encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()
