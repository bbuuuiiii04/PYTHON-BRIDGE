with open('tests/test_anlz_reader.py', 'r') as f:
    content = f.read()

# Fix recursive call
content = content.replace('return _detect_drop_beats_helper(energies, track_max)', 'return _detect_drop_beats(energies, track_max)')

# Fix FakeTag mood
content = content.replace(
    'self.content = SimpleNamespace(entries=entries) if entries is not None else None',
    'self.content = SimpleNamespace(entries=entries, mood=1) if entries is not None else None'
)

with open('tests/test_anlz_reader.py', 'w') as f:
    f.write(content)
