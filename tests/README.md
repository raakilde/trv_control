# TRV Control Tests

## Running Tests

### Install test dependencies:
```bash
pip install -r requirements_test.txt
```

### Run all tests:
```bash
pytest tests/
```

### Run with coverage:
```bash
pytest --cov=custom_components.trv_control --cov-report=html tests/
```

### Run specific test file:
```bash
pytest tests/test_climate.py
pytest tests/test_config_flow.py
```

### Run with verbose output:
```bash
pytest -v tests/
```

## Test Coverage

The test suite covers:
- Config flow (adding rooms, adding TRVs)
- Climate entity initialization
- Temperature control (sending to multiple TRVs)
- HVAC mode control
- Window sensor detection
- Return temperature valve control
- Independent TRV control
- State attributes

## Test Structure

```
tests/
├── __init__.py
├── conftest.py          # Pytest fixtures
├── const.py             # Test constants
├── test_config_flow.py  # Config flow tests
└── test_climate.py      # Climate entity tests
```
