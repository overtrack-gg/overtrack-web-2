from typing import Optional, Type

from pynamodb.expressions.condition import *
from pynamodb.expressions.operand import Path, Value

from overtrack_models.orm.apex_game_summary import ApexGameSummary


class MockResultIteratorExt:
    def __init__(self, items, last_evaluated: int = 0, limit: Optional[int] = None):
        self._items = items
        self._index = 0
        self.iter = iter(items)
        self.last_evaluated = last_evaluated
        self.limit = limit
        self.total_count = len(items)

    def __iter__(self):
        return self

    def __next__(self):
        self.last_evaluated += 1
        self._index += 1
        return next(self.iter)

    @property
    def last_evaluated_key(self):
        if self.last_evaluated <= self.limit:
            return str(self.last_evaluated)
        else:
            return None

    # @property
    # def page_iter(self):
    #     class _PageIter:
    #         @property
    #         def key_names(self):
    #             return ['index']
    #     return _PageIter()

class MockIndex:

    def __init__(self, cached_data, hash_key_attr_name: str, model_class: Type):
        self.cached_data = cached_data
        self.hash_key_attr_name = hash_key_attr_name
        self.model_class = model_class

    def query(
            self,
            hash_key,
            range_key_condition=None,
            filter_condition=None,
            newest_first=None,
            limit=None,
            last_evaluated_key=None,
            page_size=None,
            attributes_to_get=None,
    ) -> MockResultIteratorExt:
        merged_filter = range_key_condition
        if merged_filter is None:
            merged_filter = filter_condition
        else:
            merged_filter &= filter_condition

        def evaluate_filter(g, f: Condition) -> bool:
            if f is None:
                return True
            elif not isinstance(f, Condition):
                raise ValueError('f must be a Condition')

            if isinstance(f, Not):
                return not evaluate_filter(g, f.values)
            elif isinstance(f, And):
                return all(evaluate_filter(g, v) for v in f.values)
            elif isinstance(f, Or):
                return any(evaluate_filter(g, v) for v in f.values)

            values = []
            for v in f.values:
                if isinstance(v, Path):
                    attr_name = v.path[0]
                    values.append(getattr(
                        g,
                        g._dynamo_to_python_attrs.get(attr_name, attr_name)
                    ))
                elif isinstance(v, Value):
                    assert len(v.values) == 1
                    assert len(v.values[0]) == 1

                    typ, val = next(iter(v.values[0].items()))
                    if typ == 'N':
                        val = float(val)
                    elif typ == 'S':
                        val = str(val)
                    else:
                        raise ValueError(f"Don't know how to decode type {typ!r}")

                    values.append(val)

            if isinstance(f, Between):
                return values[1] <= values[0] <= values[2]
            elif isinstance(f, Comparison):
                if f.operator == '=':
                    return values[0] == values[1]
                elif f.operator == '<>':
                    return values[0] != values[1]
                elif f.operator == '<':
                    return values[0] < values[1]
                elif f.operator == '<=':
                    return values[0] <= values[1]
                elif f.operator == '>':
                    return values[0] > values[1]
                elif f.operator == '>=':
                    return values[0] >= values[1]
                else:
                    raise ValueError(f"Don't know how to evaluate {f.operator}")
            elif isinstance(f, Exists):
                return values[0] is not None
            elif isinstance(f, NotExists):
                return values[0] is None
            elif isinstance(f, In):
                return values[0] in values[1:]
            else:
                raise ValueError(f"Don't know how to evaluate {type(f)}")

        if not last_evaluated_key:
            last_evaluated_key = 0
        last_evaluated_key = int(last_evaluated_key)

        items = [
            g
            for g in self.cached_data
            if getattr(g, self.hash_key_attr_name, None) == hash_key and evaluate_filter(g, merged_filter)
        ]
        if newest_first:
            items.sort(key=lambda g: g.time, reverse=True)

        return MockResultIteratorExt(
            items[last_evaluated_key:],
            last_evaluated_key,
            min(last_evaluated_key + limit, len(items)) if limit else len(items)
        )

    def scan(self, *args, **kwargs):
        return self.query(*args, **kwargs)

    def get(self, *args, **kwargs):
        try:
            return next(self.query(*args, **kwargs))
        except StopIteration:
            raise self.model_class.DoesNotExist()
