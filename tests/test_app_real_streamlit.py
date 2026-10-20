"""Runs the real app with Streamlit's AppTest. Only executes where Streamlit is installed.
NOTE: written without access to a Streamlit install, so it has not been run by the author."""
import unittest
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "streamlit not installed")
class RealApp(unittest.TestCase):
    def test_home_and_demo_flow(self):
        at = AppTest.from_file("app.py", default_timeout=60).run()
        self.assertFalse(at.exception, at.exception)
        at.sidebar.radio(key="nav").set_value("Upload").run()
        at.button(key="w_demo").click().run()
        self.assertFalse(at.exception, at.exception)
        at.sidebar.radio(key="nav").set_value("Analyze").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("Total revenue" in m.label for m in at.metric))


if __name__ == "__main__":
    unittest.main()
