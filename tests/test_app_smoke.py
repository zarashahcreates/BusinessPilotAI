"""Smoke tests that run the real page code against a fake Streamlit (see tests/fake_streamlit.py).
Skipped automatically when the real Streamlit is installed; use tests/test_app_real_streamlit.py then."""
import importlib, sys, tempfile, unittest
from tests import helpers  # noqa: F401

try:
    import streamlit  # noqa: F401
    REAL = True
except ImportError:
    REAL = False


@unittest.skipIf(REAL, "real Streamlit installed; see test_app_real_streamlit.py")
class Smoke(unittest.TestCase):
    def setUp(self):
        from tests import fake_streamlit
        from businesspilot import config
        self.fake = fake_streamlit.install()
        self.Rerun = fake_streamlit.RerunException
        config.DATA_DIR = type(config.DATA_DIR)(tempfile.mkdtemp()); config.DB_PATH = config.DATA_DIR / "t.db"
        for m in [m for m in sys.modules if m.startswith("businesspilot.ui")]:
            del sys.modules[m]
        self.state = importlib.import_module("businesspilot.ui.state")
        self.PD = importlib.import_module("businesspilot.ui.pages_data")
        self.PA = importlib.import_module("businesspilot.ui.pages_analysis")
        self.state.init()

    def run_page(self, fn):
        for _ in range(6):
            self.fake.log.clear()
            try:
                return fn()
            except self.Rerun:
                continue
        self.fail("page kept rerunning")

    def kinds(self):
        return [k for k, _ in self.fake.log]

    def test_empty_states_do_not_crash(self):
        for fn in (self.PD.render_home, self.PD.render_upload, self.PD.render_review, self.PA.render_analyze, self.PA.render_insights, self.PA.render_reports, self.PD.render_history):
            self.run_page(fn); self.assertNotIn("error", self.kinds())

    def test_full_journey_with_demo_data(self):
        self.PD.load_demo()
        self.assertTrue(self.state.has_data())
        self.run_page(self.PD.render_upload); self.assertNotIn("error", self.kinds())
        self.run_page(self.PD.render_review)
        self.assertNotIn("error", self.kinds()); self.assertTrue(any("Quality score" in t for k, t in self.fake.log if k == "metric"))
        self.run_page(self.PA.render_analyze)
        k = self.kinds(); self.assertNotIn("error", k)
        metrics = [t for kk, t in self.fake.log if kk == "metric"]
        self.assertTrue(any(t.startswith("Total revenue=") for t in metrics), metrics)
        charts = [t for kk, t in self.fake.log if kk == "chart"]
        for key in ("an_trend", "an_prod", "an_exp", "an_cust", "fc_main", "fc_bt"):
            self.assertIn(key, charts)
        self.run_page(self.PA.render_insights)
        self.assertNotIn("error", self.kinds()); self.assertTrue(any("off" in t for kk, t in self.fake.log if kk == "info"))
        # generate and save reports
        self.fake.clicked.add("w_gen")
        self.run_page(self.PA.render_reports)
        s = self.fake.session_state
        self.assertEqual(set(s.exports), {"pdf", "docx", "xlsx"}); self.assertNotIn("error", self.kinds())
        self.fake.clicked.clear()
        self.PD.save_current("Smoke test")
        self.assertIsNotNone(s.analysis_id)
        from businesspilot import db
        self.assertEqual(db.list_analyses()[0]["n_reports"], 3)
        self.run_page(self.PD.render_history); self.assertNotIn("error", self.kinds())
        # reopen from history, then start a new analysis without losing anything
        aid = s.analysis_id
        self.state.reset_all(); self.assertFalse(self.state.has_data())
        self.PD.open_saved(aid)
        self.assertTrue(self.state.has_data()); self.assertEqual(s.nav, "Analyze")
        self.run_page(self.PA.render_analyze); self.assertNotIn("error", self.kinds())

    def test_start_new_requires_confirmation_when_unsaved(self):
        self.PD.load_demo()
        self.PD.start_new_flow("t")
        s = self.fake.session_state
        self.assertTrue(s.confirm_new); self.assertTrue(self.state.has_data())     # nothing was discarded
        self.PD.save_current("keep")
        s.confirm_new = False
        self.PD.start_new_flow("t")
        self.assertFalse(self.state.has_data())                                      # saved work -> safe to reset

    def test_changing_mapping_updates_results(self):
        self.PD.load_demo()
        s = self.fake.session_state
        b1 = self.state.current_bundle(); self.assertTrue(b1.avail["expenses"])
        cols = dict(s.mapping.columns); cols.pop("expenses")
        from businesspilot.schema import Mapping
        s.mapping = Mapping(columns=cols)
        b2 = self.state.current_bundle()
        self.assertFalse(b2.avail["expenses"]); self.assertIsNot(b1, b2)

    def test_memo_prevents_recomputation(self):
        self.PD.load_demo()
        self.assertIs(self.state.current_bundle(), self.state.current_bundle())

    def test_app_entrypoint_runs(self):
        for m in ("app",):
            sys.modules.pop(m, None)
        importlib.import_module("app")
        self.assertTrue(any("BusinessPilot" in t for k, t in self.fake.log if k == "markdown"))


if __name__ == "__main__":
    unittest.main()
