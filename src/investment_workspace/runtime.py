"""Per-attempt context, bounded work and committed deterministic calculation caches."""

import time
import math
from contextvars import ContextVar
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from decimal import Decimal

from .storage import digest, dumps, committed

_CURRENT = ContextVar('investment_run', default=None)


class BudgetExceeded(ValueError):
    pass


def json_values(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_values(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(v) for v in value]
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value


class RunContext:
    def __init__(self, root, code_hash, previous, *, as_of=None, max_units=None, max_seconds=None, artifacts=None, verify=False):
        if max_units is not None and (type(max_units) is not int or max_units<0) or max_seconds is not None and (not math.isfinite(max_seconds) or max_seconds<0):
            raise ValueError('work/runtime budgets must be nonnegative')
        self.root, self.code_hash, self.as_of = root, code_hash, as_of
        self.max_units, self.max_seconds = max_units, max_seconds
        self.began = time.monotonic()
        self.cache = deepcopy(previous.get('calculations', {}))
        self.units = self.hits = self.verified = 0
        self.deferred, self.timings, self.dependencies = [], {}, []
        self.artifacts, self.verify = artifacts or {}, verify

    def consume(self, owner, key):
        if (self.max_units is not None and self.units >= self.max_units or
                self.max_seconds is not None and time.monotonic() - self.began >= self.max_seconds):
            record = {'owner': owner, 'key': key, 'reason': 'BUDGET_EXHAUSTED'}
            if record not in self.deferred:
                self.deferred.append(record)
            raise BudgetExceeded('BUDGET_EXHAUSTED: ' + owner + ' ' + key)
        self.units += 1

    def cached(self, owner, key, inputs, compute):
        raw = json_values(inputs)
        fingerprint = digest(dumps({'code': self.code_hash, 'schema': '4.0', 'inputs': raw}))
        cache_key = owner + ':' + key
        existing = self.cache.get(cache_key)
        self.dependencies.append({'owner': owner, 'key': key, 'input_fingerprint': fingerprint})
        if existing and existing['fingerprint'] == fingerprint and digest(dumps(existing['output'])) == existing['output_hash']:
            self.hits += 1
            if self.verify:
                self.consume(owner, key)
                actual = json_values(compute())
                if actual != existing['output']:
                    raise ValueError('committed cache arithmetic mismatch: ' + cache_key)
                self.verified += 1
            return deepcopy(existing['output'])
        self.consume(owner, key)
        output = json_values(compute())
        self.cache[cache_key] = {'fingerprint': fingerprint, 'output': output, 'output_hash': digest(dumps(output))}
        return deepcopy(output)

    def blob(self, sha, suffix):
        path = 'data/evidence/blobs/' + sha + suffix
        return self.artifacts.get(path) if path in self.artifacts else committed(self.root, path)

    @contextmanager
    def phase(self, name):
        start = time.monotonic()
        try:
            yield
        finally:
            self.timings[name] = round(time.monotonic() - start, 6)


@contextmanager
def context(runtime):
    token = _CURRENT.set(runtime)
    try:
        yield runtime
    finally:
        _CURRENT.reset(token)


def current():
    return _CURRENT.get()


def assessment_date(bundle):
    ctx = current()
    return ctx.as_of if ctx and ctx.as_of else bundle.market_cutoff


def cached(owner, key, inputs, compute):
    ctx = current()
    return ctx.cached(owner, key, inputs, compute) if ctx else json_values(compute())
