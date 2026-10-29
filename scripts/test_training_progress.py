"""Status parsing only; synthetic logs are not training/recognition evidence."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.pilot.service import parse_training_tail
class ProgressParsingTests(unittest.TestCase):
    def test_partial_tail_and_carriage_returns_do_not_swap_epoch_batch(self):
        text='72/765 1.2s/it 1:00<2:30\r\x1b[K       3/30 0G 1.2 2.3 1.1 4 640: 10% 73/765 1.2s/it\r\x1b[K       3/30 0G 1.1 2.2 1.0 1 640: 10% 74/765 1.1s/it'
        self.assertEqual(parse_training_tail(text),{'current_epoch':3,'maximum_epochs':30,'batch':74,'batches':765})
    def test_validation_and_export_text_are_not_epoch_progress(self):
        self.assertEqual(parse_training_tail('Class Images Instances Box(P R mAP50)\nall 139 318\nExport success 4.2s'),{})
    def test_invalid_epoch_is_ignored(self):self.assertEqual(parse_training_tail('50/30 0G 0.2 1.0 20/765'),{})
if __name__=='__main__':unittest.main()
