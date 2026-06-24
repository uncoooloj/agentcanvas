import unittest


class AgentCanvasImportTests(unittest.TestCase):
    def test_import_agentcanvas(self):
        import agentcanvas

        self.assertEqual(agentcanvas.__version__, "0.1.1")


if __name__ == "__main__":
    unittest.main()
