# Pyright patterns

Use this reference for cases that need more than straightforward parameter and return annotations.

## Generic identity and container transforms

Preserve input-output relationships instead of returning `object` or a broad union.

```python
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def first(items: Iterable[T]) -> T:
    return next(iter(items))
```

For Python 3.12+ projects, use PEP 695 syntax when it matches the repository's established style.

## Decorators

Use `ParamSpec` when a decorator preserves a callable's parameters.

```python
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def traced(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)

    return wrapper
```

Use `Concatenate` only when the decorator adds or removes known leading parameters.

## Structural interfaces

Use a small `Protocol` when callers require behavior rather than a concrete class.

```python
from typing import Protocol


class SupportsClose(Protocol):
    def close(self) -> None: ...
```

Do not create large protocols that duplicate an implementation class. Include only behavior the consumer actually uses.

## Dictionary-shaped records

Use `TypedDict` for stable external or internal mappings that remain dictionaries at runtime.

```python
from typing import NotRequired, TypedDict


class UserPayload(TypedDict):
    id: int
    name: str
    nickname: NotRequired[str]
```

Distinguish a missing key from a key whose value may be `None`.

## Overloads

Use overloads when the return type changes predictably based on literal arguments or distinct input forms.

Keep one runtime implementation. Do not use overloads to disguise unrelated behaviors that should be separate functions.

## Narrowing unknown values

Prefer `object` for values that may be anything but must be inspected before use.

```python
def parse_count(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("count must be an integer")
```

Use `Any` only when operations must remain unchecked.

## Casts

Use `cast()` only when runtime logic or an external contract already guarantees the target type and Pyright cannot express or infer it.

Place the cast at the boundary. Avoid chains of casts and never cast solely to silence a legitimate mismatch.

## Async and generators

- `async def` annotations describe the awaited result, not `Coroutine[...]`.
- Annotate synchronous generators as `Iterator[T]` or `Generator[YieldT, SendT, ReturnT]`.
- Annotate async generators as `AsyncIterator[T]` or `AsyncGenerator[YieldT, SendT]`.
- Use `Awaitable[T]` or `Coroutine[...]` for values that hold awaitables, not for an ordinary `async def` return annotation.

## Context managers

Use `ContextManager[T]` or `AsyncContextManager[T]` for values accepted as context managers. For functions decorated with `contextmanager`, annotate the generator function according to the decorator's expected input type, usually `Iterator[T]`.

## Class and instance attributes

Annotate attributes where they are declared or initialized. Use:

- `ClassVar[T]` for state shared by the class and excluded from instance fields
- `Final[T]` for non-reassignable names
- `Self` for fluent APIs and alternate constructors returning the current subclass

Do not annotate mutable class attributes as ordinary instance fields.

## Runtime annotation consumers

Frameworks such as dependency-injection systems, validation libraries, ORMs, and web frameworks may inspect annotations at runtime. Before hiding imports behind `TYPE_CHECKING` or using strings, verify the framework's resolution behavior and existing project conventions.

## Third-party libraries

Check, in order:

1. bundled `py.typed` annotations
2. official stubs
3. maintained `types-*` packages
4. a narrow local protocol or typed adapter
5. a local stub for stable APIs
6. a narrow boundary cast

Do not create a large local stub from memory. Base it on the installed library version and only cover the used surface.

## Suppressions

Prefer fixing the contract. When a suppression is truly required:

- make it rule-specific
- keep it on the smallest possible expression or line
- include a short reason when the cause is not obvious
- do not disable a rule project-wide for one dependency defect
