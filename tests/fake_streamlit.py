# -*- coding: utf-8 -*-
"""Streamlit simulado para pruebas de humo: ejecuta el código de las páginas y detecta excepciones de Python.

NO valida el aspecto visual ni el comportamiento real del navegador.
"""
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


class Dummy:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)

    def __iter__(self):
        return iter(())


class FakeSt(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SessionState()
        self.query_params = {}
        self.clicks = set()
        self.calls = []
        self.html = []
        self.errors = []
        self.comp_calls = []
        self.comp_values = {}
        self.components = types.SimpleNamespace(v1=types.SimpleNamespace(html=self._comp_html, declare_component=self._declare))
        self.column_config = types.SimpleNamespace()

    def reset(self):
        self.session_state.clear(); self.clicks.clear(); self.html.clear(); self.errors.clear(); self.calls.clear(); self.comp_calls.clear(); self.comp_values.clear()

    def _comp_html(self, h, **kw):
        self.html.append(h)

    def _declare(self, name, path=None, **kw):
        """declare_component simulado: registra cada llamada y devuelve el valor configurado en comp_values[key]."""
        def call(**kwargs):
            self.comp_calls.append((name, kwargs))
            return self.comp_values.get(kwargs.get("key"), kwargs.get("default"))
        return call

    # contenedores
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [Dummy(self) for _ in range(n)]

    def tabs(self, labels):
        return [Dummy(self) for _ in labels]

    def container(self, *a, **kw):
        return Dummy(self)

    expander = popover = form = status = spinner = container

    def fragment(self, *a, **kw):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    def rerun(self):
        raise RerunException()

    def stop(self):
        raise RerunException()

    def set_page_config(self, **kw):
        pass

    def cache_data(self, *a, **kw):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

    cache_resource = cache_data

    # widgets
    def _click(self, key, on_click, args, kwargs=None):
        if key in self.clicks:
            self.clicks.discard(key)
            if on_click:
                on_click(*(args or ()), **(kwargs or {}))
            return True
        return False

    def button(self, label, key=None, on_click=None, args=None, kwargs=None, **kw):
        return self._click(key or label, on_click, args, kwargs)

    def form_submit_button(self, label="", key=None, on_click=None, args=None, kwargs=None, **kw):
        return self._click(key or label, on_click, args, kwargs)

    def download_button(self, *a, **kw):
        return False

    def text_input(self, label, value="", key=None, **kw):
        return self.session_state.get(key, value) if key else value

    text_area = text_input

    def number_input(self, label, min_value=None, max_value=None, value=0, key=None, **kw):
        return self.session_state.get(key, value) if key else value

    def slider(self, label, min_value=None, max_value=None, value=None, key=None, **kw):
        v = value if value is not None else min_value
        return self.session_state.get(key, v) if key else v

    def selectbox(self, label, options, index=0, key=None, **kw):
        options = list(options)
        if key and key in self.session_state:
            return self.session_state[key]
        return options[index] if index is not None and options else None

    def radio(self, label, options, index=0, key=None, **kw):
        options = list(options)
        if key and key in self.session_state:
            return self.session_state[key]
        return options[index or 0] if options else None

    def multiselect(self, label, options, default=None, key=None, **kw):
        return self.session_state.get(key, list(default or [])) if key else list(default or [])

    def toggle(self, label, value=False, key=None, **kw):
        if key:
            self.session_state.setdefault(key, value)
            return self.session_state[key]
        return value

    checkbox = toggle

    def pills(self, *a, key=None, **kw):
        return self.session_state.get(key)

    def file_uploader(self, *a, **kw):
        return None

    def date_input(self, label, value=None, **kw):
        return value

    def audio_input(self, *a, **kw):
        return None

    def camera_input(self, *a, **kw):
        return None

    # salida
    def markdown(self, body="", **kw):
        self.html.append(str(body))

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        def sink(*a, **kw):
            if name in ("error",):
                self.errors.append(str(a[0]) if a else "")
            return Dummy(self)
        return sink


def install():
    fake = FakeSt()
    sys.modules["streamlit"] = fake
    sys.modules["streamlit.components"] = fake.components
    sys.modules["streamlit.components.v1"] = fake.components.v1
    if "altair" not in sys.modules:
        sys.modules["altair"] = types.ModuleType("altair")
    return fake
