# /home/numa/projets/appel-offre/tests/test_llm_settings.py
"""Tests des réglages LLM runtime (persistance fichier, masquage, priorité fichier > env).

Exécution : `python -m unittest tests.test_llm_settings` depuis la racine du dépôt,
ou dans le conteneur : `docker compose exec ao-oneid python -m pytest /tests/`.
Nécessite fastapi installé (présent dans le conteneur, pas obligatoirement en hôte).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


class LlmSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["OUT_DIR"] = self.tmp.name
        os.environ["LLM_SETTINGS_FILE"] = str(Path(self.tmp.name) / "llm_settings.json")
        os.environ["GB10_API_KEY"] = "sk-envkey"
        os.environ["GB10_BASE"] = "https://env.example/v1"
        os.environ["GB10_MODEL"] = "env-model"
        # Import différé (les env vars sont lues au module load).
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        # Purge un import précédent.
        for m in ("main",):
            if m in sys.modules:
                del sys.modules[m]
        import main  # noqa: E402
        self.main = main

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_normalize_base(self) -> None:
        self.assertEqual(self.main._normalize_base("  https://x/v1/  "), "https://x/v1")
        self.assertEqual(self.main._normalize_base(""), "")

    def test_mask_key(self) -> None:
        self.assertEqual(self.main._mask_key(""), "")
        self.assertEqual(self.main._mask_key("short"), "*****")
        self.assertEqual(self.main._mask_key("sk-abcdefghij"), "sk-a…ghij")

    def test_active_llm_env_fallback(self) -> None:
        # Ré-importer pour être sûr que SETTINGS_FILE pointe vers le tmpdir courant.
        cfg = self.main.active_llm()
        self.assertEqual(cfg["source"], "env")
        self.assertEqual(cfg["api_key"], "sk-envkey")
        self.assertEqual(cfg["model"], "env-model")

    def test_save_and_reload_overrides_env(self) -> None:
        self.main.save_llm_settings({
            "base_url": "https://file.example/v1/",
            "model": "file-model",
            "api_key": "sk-filekey",
            "updated_at": 42.0,
            "updated_by": "test",
        })
        cfg = self.main.active_llm()
        self.assertEqual(cfg["source"], "file")
        self.assertEqual(cfg["base_url"], "https://file.example/v1")
        self.assertEqual(cfg["model"], "file-model")
        self.assertEqual(cfg["api_key"], "sk-filekey")
        # Le fichier contient bien la clé (pas de chiffrement dans cette version).
        raw = json.loads(Path(os.environ["LLM_SETTINGS_FILE"]).read_text())
        self.assertEqual(raw["api_key"], "sk-filekey")


if __name__ == "__main__":
    unittest.main()
