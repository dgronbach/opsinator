# -*- mode: python ; coding: utf-8 -*-
#
# Custom PyInstaller spec file using the MERGE() multipackage feature.
#
# Without this, building opsinator.py and opsinator_engine.py separately
# (two plain `pyinstaller` commands) gives each one its OWN complete copy
# of every shared library (numpy, certifi, etc.) - duplicated disk space
# for anything both programs depend on.
#
# MERGE() instead builds both from one spec file and de-duplicates: the
# FIRST app listed keeps its own bundled copies (so it stays fast and
# self-contained); any LATER app that needs the same file gets an
# "external reference" pointing back at the first app's folder instead
# of its own copy.
#
# opsinator (the lightweight launcher) is listed first on purpose, so it
# never has to follow an external reference - it stays at its current
# fast-launch speed. opsinator_engine (already the slow one, due to
# TensorFlow) absorbs the small extra lookup cost instead.
#
# IMPORTANT: because of how external references work, the two output
# folders (dist/opsinator and dist/opsinator_engine) must always be
# shipped as SIBLING folders, in the same parent directory, exactly as
# we already planned. Moving one without the other will break it.

block_cipher = None

opsinator_a = Analysis(
    ['opsinator.py'],
    pathex=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

engine_a = Analysis(
    ['opsinator_engine.py'],
    pathex=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

MERGE(
    (opsinator_a, 'opsinator', 'opsinator'),
    (engine_a, 'opsinator_engine', 'opsinator_engine'),
)

opsinator_pyz = PYZ(opsinator_a.pure, opsinator_a.zipped_data, cipher=block_cipher)
opsinator_exe = EXE(
    opsinator_pyz,
    opsinator_a.scripts,
    [],
    exclude_binaries=True,
    name='opsinator',
    console=False,
)
opsinator_coll = COLLECT(
    opsinator_exe,
    opsinator_a.binaries,
    opsinator_a.zipfiles,
    opsinator_a.datas,
    name='opsinator',
)

engine_pyz = PYZ(engine_a.pure, engine_a.zipped_data, cipher=block_cipher)
engine_exe = EXE(
    engine_pyz,
    engine_a.scripts,
    [],
    exclude_binaries=True,
    name='opsinator_engine',
    console=True,
)
engine_coll = COLLECT(
    engine_exe,
    engine_a.binaries,
    engine_a.zipfiles,
    engine_a.datas,
    name='opsinator_engine',
)
