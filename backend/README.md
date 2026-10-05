# Model Checker core

The first milestone validates a finite `BehavioralModel` and generates TLA+
module and TLC configuration text. It does not run TLC yet.

The JSON shape is demonstrated by `tests/fixtures/buggy_model.json` and
`tests/fixtures/fixed_model.json`. Variable names, transition names, and
property names use ASCII identifiers. Enum values are nonempty printable ASCII
strings. Integer variables require inclusive `min` and `max` bounds.

From `backend/`, with Python 3.11+, Pydantic v2 and pytest available:

```powershell
python -m pytest -q
```

To generate files from a model dictionary:

```python
from model_checker import generate_tla

files = generate_tla(model)
print(files.tla)
print(files.cfg)
```

`generate_tla` validates the input before compilation. A caller can save the
texts as `Model.tla` and `Model.cfg`; the module name must match the `.tla`
filename. `forbidden_state` is compiled as a negated TLC invariant.
