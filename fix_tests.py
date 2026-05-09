import re
with open('tests/test_anlz_reader.py', 'r') as f:
    content = f.read()

content = content.replace('_extract_pssi_drop_beats', '_extract_pssi_phrases')
content = content.replace('_extract_waveform_drop_beats', '_extract_waveform_phrases')

# Fix assertions for _extract_pssi_phrases
content = re.sub(r'self\.assertEqual\(_extract_pssi_phrases\(([^)]+)\), \[', r'self.assertEqual(_extract_pssi_phrases(\1)[1], [', content)
content = re.sub(r'self\.assertEqual\(_extract_pssi_phrases\(([^)]+)\), \[\]\)', r'self.assertEqual(_extract_pssi_phrases(\1)[1], [])', content)

# Fix assertions for _extract_waveform_phrases
content = re.sub(r'self\.assertNotEqual\(_extract_waveform_phrases\(([^)]+)\), pssi_drops\)', r'self.assertNotEqual(_extract_waveform_phrases(\1)[0], pssi_drops)', content)
content = re.sub(r'self\.assertEqual\(_extract_waveform_phrases\(([^)]+)\), \[', r'self.assertEqual(_extract_waveform_phrases(\1)[0], [', content)

with open('tests/test_anlz_reader.py', 'w') as f:
    f.write(content)
