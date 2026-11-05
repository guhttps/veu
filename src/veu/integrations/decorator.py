"""Decorador que protege qualquer função que chama um modelo de IA, com qualquer biblioteca.

    from veu import protect

    @protect
    def responder(pergunta: str) -> str:
        return meu_llm.gerar(pergunta)          # recebe a pergunta com [CPF_1], [PESSOA_1]...

    responder("Sou a Maria Souza, CPF 529.982.247-25")   # devolve a resposta com os dados reais

Funciona com funções síncronas, assíncronas e geradoras (streaming). Os argumentos de texto,
listas e dicts (como listas de mensagens) são anonimizados; o retorno é restaurado.
"""

from __future__ import annotations

import functools
import inspect
import types
from collections.abc import Callable, Iterable
from typing import Any

from veu.core import Veu


def _restore(result: Any, session) -> Any:
    if isinstance(result, str):
        return session.restore(result)
    if isinstance(result, (dict, list, tuple)):
        return session.restore_data(result)
    if isinstance(result, types.GeneratorType):
        return _restore_iterator(result, session)
    if isinstance(result, types.AsyncGeneratorType):
        return _restore_async_iterator(result, session)
    return result


def _restore_iterator(iterator, session):
    restorer = session.restorer()
    for item in iterator:
        if isinstance(item, str):
            output = restorer.feed(item)
            if output:
                yield output
        else:
            yield session.restore_data(item) if isinstance(item, (dict, list, tuple)) else item
    tail = restorer.flush()
    if tail:
        yield tail


async def _restore_async_iterator(iterator, session):
    restorer = session.restorer()
    async for item in iterator:
        if isinstance(item, str):
            output = restorer.feed(item)
            if output:
                yield output
        else:
            yield session.restore_data(item) if isinstance(item, (dict, list, tuple)) else item
    tail = restorer.flush()
    if tail:
        yield tail


def protect(func: Callable | None = None, *, veu: Veu | None = None, arguments: Iterable[str] | None = None,
            restore: bool = True):
    """Anonimiza os argumentos da função e restaura o retorno.

    arguments: nomes dos parâmetros a anonimizar (padrão: todos os de texto, lista ou dict).
    restore: False devolve o retorno sem restaurar (por exemplo, para guardar a versão anônima).
    Cada chamada usa um cofre próprio.
    """

    def decorate(function: Callable) -> Callable:
        signature = inspect.signature(function)
        selected = set(arguments) if arguments is not None else None
        instance_holder: dict[str, Veu] = {}

        def instance() -> Veu:
            if veu is not None:
                return veu
            if "default" not in instance_holder:
                instance_holder["default"] = Veu()
            return instance_holder["default"]

        def prepare(args, kwargs):
            session = instance().session()
            bound = signature.bind(*args, **kwargs)
            for name, value in bound.arguments.items():
                if selected is not None and name not in selected:
                    continue
                if isinstance(value, (str, list, dict, tuple)):
                    bound.arguments[name] = session.anonymize_data(value) if not isinstance(value, str) \
                        else session.anonymize(value)
            return session, bound

        if inspect.isasyncgenfunction(function):
            @functools.wraps(function)
            async def async_gen_wrapper(*args, **kwargs):
                session, bound = prepare(args, kwargs)
                iterator = function(*bound.args, **bound.kwargs)
                if not restore:
                    async for item in iterator:
                        yield item
                    return
                async for item in _restore_async_iterator(iterator, session):
                    yield item
            return async_gen_wrapper

        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def async_wrapper(*args, **kwargs):
                session, bound = prepare(args, kwargs)
                result = await function(*bound.args, **bound.kwargs)
                return _restore(result, session) if restore else result
            return async_wrapper

        if inspect.isgeneratorfunction(function):
            @functools.wraps(function)
            def gen_wrapper(*args, **kwargs):
                session, bound = prepare(args, kwargs)
                iterator = function(*bound.args, **bound.kwargs)
                if not restore:
                    yield from iterator
                    return
                yield from _restore_iterator(iterator, session)
            return gen_wrapper

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            session, bound = prepare(args, kwargs)
            result = function(*bound.args, **bound.kwargs)
            return _restore(result, session) if restore else result
        return wrapper

    return decorate(func) if func is not None else decorate
