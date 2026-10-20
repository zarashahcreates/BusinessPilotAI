"""A tiny in-memory stand-in for Streamlit (and Plotly) used ONLY for smoke-testing page code
where the real packages are unavailable. It cannot verify real rendering or real Streamlit API
compatibility — see README 'Testing' for what must still be checked with a real install."""
from __future__ import annotations

import sys
import types


class RerunException(Exception):
    pass


class SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class _Anything:
    """Accepts any constructor args and any method call (used for Plotly)."""
    def __init__(self, *a, **k): self.args, self.kwargs = a, k
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return lambda *a, **kw: self


class _Progress:
    def progress(self, *a, **k): pass
    def empty(self): pass


class FakeSt:
    def __init__(self):
        self.session_state = SessionState()
        self.clicked: set[str] = set()
        self.uploads: list = []
        self.log: list[tuple[str, str]] = []      # (kind, text) of everything displayed
        self.sidebar = self
        self.column_config = _Anything()

    # --- context-manager behaviour for containers
    def __enter__(self): return self
    def __exit__(self, *a): return False

    # --- display
    def _show(self, kind, *a, **k): self.log.append((kind, " ".join(str(x) for x in a[:1])))
    def markdown(self, *a, **k): self._show("markdown", *a)
    def caption(self, *a, **k): self._show("caption", *a)
    def write(self, *a, **k): self._show("write", *a)
    def header(self, *a, **k): self._show("header", *a)
    def subheader(self, *a, **k): self._show("subheader", *a)
    def text(self, *a, **k): self._show("text", *a)
    def info(self, *a, **k): self._show("info", *a)
    def success(self, *a, **k): self._show("success", *a)
    def warning(self, *a, **k): self._show("warning", *a)
    def error(self, *a, **k): self._show("error", *a)
    def divider(self): pass
    def image(self, *a, **k): self._show("image", "")
    def metric(self, label, value, **k): self.log.append(("metric", f"{label}={value}"))
    def dataframe(self, df, **k): self.log.append(("dataframe", f"{len(df)} rows"))
    def plotly_chart(self, fig, **k): self.log.append(("chart", k.get("key", "")))
    def set_page_config(self, **k): pass
    def spinner(self, *a, **k): return self
    def progress(self, *a, **k): return _Progress()
    def stop(self): raise RerunException("stop")
    def rerun(self): raise RerunException("rerun")

    # --- layout
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [self] * n
    def tabs(self, names): return [self] * len(names)
    def expander(self, *a, **k): return self
    def container(self, **k): return self

    # --- widgets
    def _val(self, key, default):
        if key is None:
            return default
        if key not in self.session_state:
            self.session_state[key] = default
        return self.session_state[key]

    def button(self, label, key=None, on_click=None, args=(), **k):
        if key in self.clicked:
            if on_click:
                on_click(*args)
            return True
        return False
    download_button = lambda self, *a, **k: False  # noqa: E731
    def text_input(self, label, key=None, value="", **k): return self._val(key, value)
    def text_area(self, label, key=None, value="", **k): return self._val(key, value)
    def radio(self, label, options, key=None, **k): return self._val(key, options[0])
    def selectbox(self, label, options, key=None, **k): return self._val(key, options[0])
    def multiselect(self, label, options, default=None, key=None, **k): return self._val(key, default or [])
    def slider(self, label, lo, hi, value=None, key=None, **k): return self._val(key, value if value is not None else lo)
    def checkbox(self, label, value=False, key=None, **k): return self._val(key, value)
    def date_input(self, label, value=None, key=None, **k): return self._val(key, value)
    def file_uploader(self, *a, **k): return self.uploads
    def data_editor(self, df, **k): return df


def install() -> FakeSt:
    fake = FakeSt()
    mod = types.ModuleType("streamlit")
    for name in dir(fake):
        if not name.startswith("__"):
            setattr(mod, name, getattr(fake, name))
    mod.session_state = fake.session_state
    mod.__fake__ = fake
    sys.modules["streamlit"] = mod
    # Plotly stand-in (only if the real package is not installed)
    try:
        import plotly.graph_objects  # noqa: F401
    except ImportError:
        pl = types.ModuleType("plotly")
        go = types.ModuleType("plotly.graph_objects")
        go.__getattr__ = lambda name: _Anything          # type: ignore[attr-defined]
        pl.graph_objects = go
        sys.modules["plotly"], sys.modules["plotly.graph_objects"] = pl, go
    return fake
