"""Pastikan file workflow valid dan tidak membocorkan rahasia."""
import os

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_workflow_valid():
    with open(os.path.join(BASE, '.github', 'workflows', 'pantau.yml'), encoding='utf-8') as f:
        w = yaml.safe_load(f)
    pemicu = w.get('on') or w.get(True)
    assert len(pemicu['schedule']) == 2 and 'workflow_dispatch' in pemicu
    langkah = w['jobs']['pantau']['steps']
    env = next(s for s in langkah if s.get('name') == 'Jalankan tugas')['env']
    assert set(env) >= {'SUPABASE_URL', 'SUPABASE_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'}
    assert all(v.startswith('${{') for v in env.values())           # rahasia hanya dari GitHub Secrets
    assert os.path.exists(os.path.join(BASE, 'requirements-tugas.txt'))
