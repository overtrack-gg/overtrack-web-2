import dataclasses


def patch():
    orig_asdict_inner = dataclasses._asdict_inner
    def _asdict_inner(obj, dict_factory):
        if isinstance(obj, tuple) and hasattr(obj, '_fields'):
            return type(obj)(*[_asdict_inner(v, dict_factory) for v in obj])
        else:
            return orig_asdict_inner(obj, dict_factory)
    dataclasses._asdict_inner = _asdict_inner

    orig_astuple_inner = dataclasses._astuple_inner
    def _astuple_inner(obj, tuple_factory):
        if isinstance(obj, tuple) and hasattr(obj, '_fields'):
            return type(obj)(*[_astuple_inner(v, tuple_factory) for v in obj])
        else:
            return orig_astuple_inner(obj, tuple_factory)
    dataclasses._astuple_inner = _astuple_inner
