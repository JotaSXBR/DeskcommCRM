import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import coolify


class TestValidarRef(unittest.TestCase):
    def test_aceita_numerada(self):
        self.assertEqual(coolify.validar_ref("1.29.0"), "1.29.0")

    def test_recusa_moveis(self):
        for ref in ("latest", "main", "stable", "v1.29.0", "", "1.29"):
            with self.subTest(ref=ref):
                with self.assertRaises(ValueError):
                    coolify.validar_ref(ref)


class TestTagsCompose(unittest.TestCase):
    COMPOSE = (
        '    image: ghcr.io/melgarafael/deskcommcrm:1.28.0\n'
        '    image: ghcr.io/melgarafael/deskcomm-worker:1.28.0\n'
        '    image: ghcr.io/melgarafael/deskcomm-scheduler:1.28.0\n'
        '    image: devlikeapro/waha:latest-2026.7.2\n'
        '    image: hiett/serverless-redis-http@sha256:5b0b\n'
        '    image: redis:7-alpine\n'
    )

    def test_extrair_tags(self):
        tags = coolify.extrair_tags_imagens(self.COMPOSE)
        self.assertEqual(tags, {
            "deskcommcrm": "1.28.0",
            "deskcomm-worker": "1.28.0",
            "deskcomm-scheduler": "1.28.0",
        })

    def test_trocar_so_deskcomm(self):
        novo = coolify.trocar_tags_deskcomm(self.COMPOSE, "1.29.0")
        self.assertIn("ghcr.io/melgarafael/deskcommcrm:1.29.0", novo)
        self.assertIn("ghcr.io/melgarafael/deskcomm-worker:1.29.0", novo)
        self.assertIn("ghcr.io/melgarafael/deskcomm-scheduler:1.29.0", novo)
        self.assertIn("devlikeapro/waha:latest-2026.7.2", novo)
        self.assertIn("serverless-redis-http@sha256:5b0b", novo)
        self.assertIn("redis:7-alpine", novo)
        self.assertNotIn("1.28.0", novo.replace("latest-2026.7.2", ""))


class TestCompararVersoes(unittest.TestCase):
    def test_nada_a_fazer(self):
        self.assertEqual(coolify.comparar_versoes("1.28.0", "1.28.0"), "nada_a_fazer")

    def test_update(self):
        self.assertEqual(coolify.comparar_versoes("1.28.0", "1.29.0"), "update")

    def test_alvo_anterior_recusa(self):
        with self.assertRaises(ValueError):
            coolify.comparar_versoes("1.29.0", "1.28.0")


class TestMesclarEnv(unittest.TestCase):
    def test_painel_prevalece_em_preservadas(self):
        painel = {"SRH_TOKEN": "do-painel", "RESEND_API_KEY": "re_painel", "DOMAIN": "velho"}
        arquivo = {"SRH_TOKEN": "", "DOMAIN": "crm.novo.com.br"}
        out = coolify.mesclar_env_update(painel, arquivo)
        self.assertEqual(out["SRH_TOKEN"], "do-painel")
        self.assertEqual(out["RESEND_API_KEY"], "re_painel")
        self.assertEqual(out["DOMAIN"], "crm.novo.com.br")

    def test_nao_inventa_segredo(self):
        out = coolify.mesclar_env_update({}, {"DOMAIN": "x"})
        self.assertNotIn("SRH_TOKEN", out)
        self.assertNotIn("IMPERSONATE_COOKIE_SECRET", out)


class TestBaselineMudou(unittest.TestCase):
    def test_mudou(self):
        self.assertTrue(coolify.baseline_mudou(b"a", b"b"))

    def test_igual(self):
        self.assertFalse(coolify.baseline_mudou(b"a", b"a"))

    def test_sem_referencia_aplica(self):
        self.assertTrue(coolify.baseline_mudou(b"a", None))


class TestRegistroOperacao(unittest.TestCase):
    def test_marcar_etapa(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            op = coolify.novo_registro_operacao("1.29.0", d)
            self.assertEqual(op["etapas"], [])
            op2 = coolify.marcar_etapa(op, "snapshot", True, "compose-1.b64")
            self.assertEqual(op2["etapas"], [{"etapa": "snapshot", "ok": True, "detalhe": "compose-1.b64"}])

    def test_resume_pula_db_apply_concluido(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            op = coolify.novo_registro_operacao("1.29.0", d)
            op = coolify.marcar_etapa(op, "snapshot", True, "compose-1.b64")
            op = coolify.marcar_etapa(op, "sync-compose", True, "200")
            op = coolify.marcar_etapa(op, "db-apply", True, "tables=109")
            self.assertEqual(coolify.proxima_etapa(op), "env-sync")


class TestTextoImagensPainel(unittest.TestCase):
    def test_applications_quando_sem_raw(self):
        payload = {"applications": [
            {"name": "app", "image": "ghcr.io/melgarafael/deskcommcrm:1.28.0"},
            {"name": "waha", "image": "devlikeapro/waha:latest-2026.7.2"},
        ]}
        tags = coolify.extrair_tags_imagens(coolify.texto_imagens_painel(payload))
        self.assertEqual(tags, {"deskcommcrm": "1.28.0"})

    def test_raw_quando_presente(self):
        import base64
        compose = "    image: ghcr.io/melgarafael/deskcomm-worker:1.29.0\n"
        payload = {"docker_compose_raw": base64.b64encode(compose.encode()).decode(),
                   "applications": []}
        tags = coolify.extrair_tags_imagens(coolify.texto_imagens_painel(payload))
        self.assertEqual(tags, {"deskcomm-worker": "1.29.0"})


class TestContainersNovosOk(unittest.TestCase):
    PS = (
        "app-x|ghcr.io/melgarafael/deskcommcrm:1.34.0|Up 21 seconds (healthy)\n"
        "worker-x|ghcr.io/melgarafael/deskcomm-worker:1.34.0|Up 51 seconds (healthy)\n"
        "scheduler-x|ghcr.io/melgarafael/deskcomm-scheduler:1.34.0|Up 15 seconds\n"
        "waha-x|devlikeapro/waha:latest-2026.7.2|Up 51 seconds\n"
    )

    def test_todos_novos_up(self):
        self.assertTrue(coolify.containers_novos_ok(self.PS, "1.34.0"))

    def test_falta_um_ou_tag_antiga(self):
        antigo = self.PS.replace("deskcomm-scheduler:1.34.0", "deskcomm-scheduler:1.28.0")
        self.assertFalse(coolify.containers_novos_ok(antigo, "1.34.0"))
        self.assertFalse(coolify.containers_novos_ok("", "1.34.0"))


class TestExtrairEnvLista(unittest.TestCase):
    def test_prefere_real_value(self):
        itens = [{"key": "A", "real_value": "real", "value": "mascarado"},
                 {"key": "B", "value": "so-value"},
                 {"key": "", "value": "sem-chave"},
                 "nao-dict"]
        self.assertEqual(coolify.extrair_env_lista(itens), {"A": "real", "B": "so-value"})

    def test_nao_lista_vira_vazio(self):
        self.assertEqual(coolify.extrair_env_lista({"data": []}), {})
        self.assertEqual(coolify.extrair_env_lista(None), {})


class TestDiffEnv(unittest.TestCase):
    def test_so_novas_e_alteradas(self):
        atual = {"A": "1", "B": "2", "C": "3"}
        desejado = {"A": "1", "B": "nova", "D": "4"}
        self.assertEqual(coolify.diff_env(atual, desejado), {"B": "nova", "D": "4"})

    def test_iguais_vazio(self):
        self.assertEqual(coolify.diff_env({"A": "1"}, {"A": "1"}), {})
        self.assertEqual(coolify.diff_env({}, {}), {})


if __name__ == "__main__":
    unittest.main()
