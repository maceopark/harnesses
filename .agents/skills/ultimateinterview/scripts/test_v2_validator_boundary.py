#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

VALIDATOR_PATH = Path(__file__).resolve().with_name("validator_boundary.py")
VALIDATOR_MODULE_NAME = "_ultimateinterview_v2_validator_boundary"
_spec = importlib.util.spec_from_file_location(VALIDATOR_MODULE_NAME, VALIDATOR_PATH)
assert _spec is not None
assert _spec.loader is not None
boundary = importlib.util.module_from_spec(_spec)
sys.modules[VALIDATOR_MODULE_NAME] = boundary
_spec.loader.exec_module(boundary)

ROOT = ".agents/skills/ultimateinterview"
RUNNER = CliRunner()


def test_validator_boundary_is_loaded_from_this_skill_tree() -> None:
    # Given
    expected_path = VALIDATOR_PATH.resolve()

    # When
    actual_path = Path(boundary.__file__).resolve()

    # Then
    assert boundary.__name__ == VALIDATOR_MODULE_NAME
    assert actual_path == expected_path


def _paths_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "changed-paths.txt"
    _ = path.write_text(content, encoding="utf-8")
    return path


def _production_file(tmp_path: Path, source: str, name: str = "safe.py") -> str:
    relative = f"{ROOT}/scripts/{name}"
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(source, encoding="utf-8")
    return relative


def _run(tmp_path: Path, paths: str) -> str:
    result = RUNNER.invoke(
        boundary.app,
        ["--workspace-root", str(tmp_path), "--changed-paths", str(_paths_file(tmp_path, paths))],
    )
    assert result.exit_code == 1
    return result.output


@pytest.mark.parametrize(
    ("paths", "expected"),
    (
        ("", "invalid-changed-path: blank"),
        ("\n", "invalid-changed-path: blank"),
        (f"{ROOT}/scripts/safe.py\n{ROOT}/scripts/safe.py\n", "invalid-changed-path: duplicate"),
        ("../escape.py\n", "invalid-changed-path: escaping"),
        (f"{ROOT}//scripts/safe.py\n", "invalid-changed-path: noncanonical"),
        (f"{ROOT}/scripts/./safe.py\n", "invalid-changed-path: noncanonical"),
    ),
)
def test_changed_paths_rejects_blank_duplicate_or_escaping_entries(
    tmp_path: Path, paths: str, expected: str
) -> None:
    # Given
    _ = _production_file(tmp_path, "VALUE = 1\n")

    # When
    output = _run(tmp_path, paths)

    # Then
    assert expected in output


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("import subprocess\n", "forbidden-import: subprocess"),
        ("import asyncio.subprocess\n", "forbidden-import: asyncio.subprocess"),
        ("import multiprocessing\n", "forbidden-import: multiprocessing"),
        ("import pty\n", "forbidden-import: pty"),
        ("import socket\n", "forbidden-import: socket"),
        ("import http.client\n", "forbidden-import: http.client"),
        ("import http\n", "forbidden-import: http"),
        ("import urllib.request\n", "forbidden-import: urllib.request"),
        ("import requests\n", "forbidden-import: requests"),
        ("import httpx\n", "forbidden-import: httpx"),
        ("import boto3\n", "forbidden-import: boto3"),
        ("import os\nos.system('x')\n", "forbidden-call: os.system"),
        ("from os import system\n", "forbidden-import: os.system"),
        ("from os import popen as launch\n", "forbidden-import: os.popen"),
        ("from os import spawnv as launch\n", "forbidden-import: os.spawnv"),
        ("from os import *\n", "forbidden-import: os.*"),
        ("from os import popen as launch\nlaunch('x')\n", "forbidden-call: os.popen"),
        ("from os import spawnv as launch\nlaunch(0, 'x', ())\n", "forbidden-call: os.spawnv"),
        ("import pty\npty.spawn([])\n", "forbidden-call: pty.spawn"),
        ("import importlib\nimportlib.import_module('x')\n", "forbidden-call: importlib.import_module"),
        ("import importlib\n", "forbidden-import: importlib"),
        ("import os\nrunner = os.system\nrunner('x')\n", "forbidden-call: os.system"),
        ("import os\ndef dispatch(callback):\n    callback('x')\ndispatch(os.system)\n", "forbidden-call: os.system"),
        ("import os\nrunners = {'system': os.system}\nrunners['system']('x')\n", "forbidden-call: os.system"),
        ("import os\ndef dispatch(callback=os.system):\n    callback('x')\ndispatch()\n", "forbidden-call: os.system"),
        ("import functools\nimport os\nfunctools.partial(os.system, 'x')()\n", "forbidden-call: os.system"),
        ("import builtins\nrunner = builtins.eval\nrunner('1')\n", "forbidden-call: builtins.eval"),
        ("import os\nos.__dict__['system']('x')\n", "forbidden-call: os.__dict__.system"),
        ("__import__('x')\n", "forbidden-call: __import__"),
        ("eval('1')\n", "forbidden-call: eval"),
        ("from builtins import eval as execute\nexecute('1')\n", "forbidden-call: builtins.eval"),
        ("from math import *\n", "forbidden-import: math.*"),
        ("globals.__call__()\n", "forbidden-call: globals.__call__"),
        ("namespace = globals\nnamespace.__call__()\n", "forbidden-call: globals.__call__"),
        ("__import__.__call__('os')\n", "forbidden-call: __import__.__call__"),
        ("module_loader = __import__\nmodule_loader.__call__('os')\n", "forbidden-call: __import__.__call__"),
    ),
)
def test_ast_boundary_rejects_forbidden_imports_calls_and_aliases(
    tmp_path: Path, source: str, expected: str
) -> None:
    # Given
    relative = _production_file(tmp_path, source)

    # When
    output = _run(tmp_path, f"{relative}\n")

    # Then
    assert expected in output


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "import sys\nsys.modules['os'].system('x')\n",
            "forbidden-reflection: sys.modules.os.system",
        ),
        (
            "import sys\nregistry = sys.modules\nrunner = registry['os'].system\nrunner('x')\n",
            "forbidden-reflection: sys.modules.os.system",
        ),
        (
            "import os\ndef f():\n    pass\nrunner = f.__globals__['os'].system\nrunner('x')\n",
            "forbidden-call: f.__globals__",
        ),
        (
            "import os\ndef f():\n    pass\nfunction_alias = f\nnamespace = function_alias.__globals__\nrunner = namespace['os'].system\nrunner('x')\n",
            "forbidden-call: f.__globals__",
        ),
        (
            "def make_generator():\n    yield 1\nstream = make_generator()\nframe = stream.gi_frame\n",
            "forbidden-call: stream.gi_frame",
        ),
        (
            "def make_generator():\n    yield 1\nstream = make_generator()\nstream_alias = stream\nframe = stream_alias.gi_frame\n",
            "forbidden-call: stream.gi_frame",
        ),
        (
            "async def make_coroutine():\n    return 1\ntask = make_coroutine()\nframe = task.cr_frame\n",
            "forbidden-call: task.cr_frame",
        ),
        (
            "async def make_coroutine():\n    return 1\ntask = make_coroutine()\ntask_alias = task\nframe = task_alias.cr_frame\n",
            "forbidden-call: task.cr_frame",
        ),
        (
            "def make_generator():\n    yield 1\nstream = make_generator()\nframe = stream.gi_frame\nbuiltins = frame.f_builtins\n",
            "forbidden-call: stream.gi_frame.f_builtins",
        ),
        (
            "def make_generator():\n    yield 1\nstream = make_generator()\nframe = stream.gi_frame\nframe_alias = frame\nbuiltins = frame_alias.f_builtins\n",
            "forbidden-call: stream.gi_frame.f_builtins",
        ),
        (
            "loader = (lambda: None).__globals__['__builtins__']['__import__']\nloader('os')\n",
            "forbidden-call: <lambda>.__globals__",
        ),
        (
            "callback = lambda: None\ncallback_alias = callback\nnamespace = callback_alias.__globals__\nbuiltins = namespace['__builtins__']\nloader = builtins['__import__']\nloader('os')\n",
            "forbidden-call: <lambda>.__globals__",
        ),
    ),
)
def test_ast_boundary_rejects_direct_and_aliased_reflection(
    tmp_path: Path, source: str, expected: str
) -> None:
    # Given
    relative = _production_file(tmp_path, source)

    # When
    output = _run(tmp_path, f"{relative}\n")

    # Then
    assert expected in output


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "import operator as accessors\nimport sys\n"
            "registry = accessors.attrgetter('modules')(sys)\n"
            "os_module = accessors.itemgetter('os')(registry)\n"
            "accessors.attrgetter('system')(os_module)('x')\n",
            "forbidden-call: operator.attrgetter",
        ),
        (
            "from operator import attrgetter as attribute, itemgetter as item\n"
            "import sys\n"
            "registry = attribute('modules')(sys)\n"
            "os_module = item('os')(registry)\n"
            "attribute('system')(os_module)('x')\n",
            "forbidden-import: operator.attrgetter",
        ),
        (
            "import operator as accessors\nimport sys\n"
            "attribute = accessors.attrgetter\n"
            "nested_attribute = attribute\n"
            "item = accessors.itemgetter\n"
            "nested_item = item\n"
            "registry = nested_attribute('modules')(sys)\n"
            "os_module = nested_item('os')(registry)\n"
            "system = nested_attribute('system')(os_module)\n"
            "system('x')\n",
            "forbidden-call: operator.attrgetter",
        ),
    ),
)
def test_ast_boundary_rejects_operator_getter_reflection_gadgets(
    tmp_path: Path, source: str, expected: str
) -> None:
    # Given
    relative = _production_file(tmp_path, source)

    # When
    output = _run(tmp_path, f"{relative}\n")

    # Then
    assert expected in output


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "import operator\nimport os\noperator.methodcaller('system', 'x')(os)\n",
            "forbidden-call: operator.methodcaller",
        ),
        (
            "import operator as accessors\nimport os\n"
            "method = accessors.methodcaller\nmethod('system', 'x')(os)\n",
            "forbidden-call: operator.methodcaller",
        ),
        (
            "from operator import methodcaller as method\nimport os\n"
            "method('system', 'x')(os)\n",
            "forbidden-import: operator.methodcaller",
        ),
        (
            "import operator as accessors\nimport os\n"
            "method = accessors.methodcaller\nnested_method = method\n"
            "nested_method('system', 'x')(os)\n",
            "forbidden-call: operator.methodcaller",
        ),
        (
            "object.__subclasses__()\n",
            "forbidden-call: object.__subclasses__",
        ),
        (
            "kind = object\nsubclasses = kind.__subclasses__\nsubclasses()\n",
            "forbidden-call: object.__subclasses__",
        ),
        (
            "from builtins import object as kind\nkind.__subclasses__()\n",
            "forbidden-call: builtins.object.__subclasses__",
        ),
        (
            "kind = object\nsubclasses = kind.__subclasses__\n"
            "nested_subclasses = subclasses\nnested_subclasses()\n",
            "forbidden-call: object.__subclasses__",
        ),
    ),
)
def test_ast_boundary_rejects_operator_methodcaller_and_type_introspection_gadgets(
    tmp_path: Path, source: str, expected: str
) -> None:
    # Given
    relative = _production_file(tmp_path, source)

    # When
    output = _run(tmp_path, f"{relative}\n")

    # Then
    assert expected in output


def test_ast_boundary_allows_non_reflective_operator_calls(tmp_path: Path) -> None:
    # Given
    relative = _production_file(tmp_path, "import operator\nRESULT = operator.eq(1, 1)\n")

    # When
    result = RUNNER.invoke(
        boundary.app,
        ["--workspace-root", str(tmp_path), "--changed-paths", str(_paths_file(tmp_path, f"{relative}\n"))],
    )

    # Then
    assert result.exit_code == 0, result.output


def test_changed_paths_rejects_symlinked_python_source_before_read(tmp_path: Path) -> None:
    # Given
    target_relative = _production_file(tmp_path, "import subprocess\n", "target.py")
    relative = f"{ROOT}/scripts/safe.py"
    linked_source = tmp_path / relative
    linked_source.symlink_to(tmp_path / target_relative)

    # When
    output = _run(tmp_path, f"{relative}\n")

    # Then
    assert f"symlink-changed-path: {relative}" in output


def test_boundary_scans_every_listed_production_module(tmp_path: Path) -> None:
    # Given
    safe = _production_file(tmp_path, "VALUE = 1\n", "safe.py")
    forbidden = _production_file(tmp_path, "import socket\n", "later.py")

    # When
    output = _run(tmp_path, f"{safe}\n{forbidden}\n")

    # Then
    assert "forbidden-import: socket" in output


def test_boundary_skips_only_named_legacy_runtime_exceptions(tmp_path: Path) -> None:
    # Given
    regression = _production_file(tmp_path, "import subprocess\n", "regression_check.py")
    ordinary = _production_file(tmp_path, "VALUE = 1\n")

    # When
    result = RUNNER.invoke(
        boundary.app,
        ["--workspace-root", str(tmp_path), "--changed-paths", str(_paths_file(tmp_path, f"{regression}\n{ordinary}\n"))],
    )

    # Then
    assert result.exit_code == 0, result.output
