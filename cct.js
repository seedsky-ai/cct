#!/usr/bin/env node
// cct.js — the npm bin cross-platform shim: it does one thing = find Python 3, hand over to cct.py.
// Why start from Node: the only runtime npm install is guaranteed to have is node (engines >=16);
// the old bash wrapper installed on Windows but would not run, and that is what package.json's
// os allowlist (EBADPLATFORM) was blocking — since 0.1.1 the entry point is this file, and the
// allowlist was dropped with it.
'use strict';
const { spawn, spawnSync } = require('child_process');
const os = require('os');
const path = require('path');

const PROBE = 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)';

function candidates() {
  // CCT_PYTHON explicitly given > the platform-conventional names. Windows does not probe
  // python3: the Microsoft Store placeholder alias python3.exe steers you to the Store, too
  // dirty to even probe; python / py -3 is the right way.
  if (process.env.CCT_PYTHON) return [[process.env.CCT_PYTHON]];
  if (process.platform === 'win32') return [['python'], ['py', '-3']];
  const cands = [['python3'], ['python']];
  if (process.platform === 'darwin') {
    // On a mac without CLT, /usr/bin/python3 is a stub: even a spawnSync probe pops the
    // "install the command line developer tools" GUI dialog (audit confirmed) → skip the
    // python3 candidate in that form. Homebrew/pyenv python3 does not go through the stub,
    // so it is probed as usual.
    const w = spawnSync('/usr/bin/which', ['python3'], { encoding: 'utf8' });
    if ((w.stdout || '').trim() === '/usr/bin/python3'
        && spawnSync('/usr/bin/xcode-select', ['-p'], { stdio: 'ignore' }).status !== 0) {
      cands.shift();
    }
  }
  return cands;
}

function findPython() {
  for (const c of candidates()) {
    try {
      const r = spawnSync(c[0], [...c.slice(1), '-c', PROBE], { stdio: 'ignore' });
      if (r.status === 0) return c;
    } catch (e) { /* try the next candidate */ }
  }
  return null;
}

const py = findPython();
if (!py) {
  console.error('✗ Python >=3.8 required (no usable interpreter found; set CCT_PYTHON to specify one)');
  if (process.platform === 'win32') {
    console.error('  Windows: install from https://www.python.org/downloads/ and check "Add python.exe to PATH"');
  } else if (process.platform === 'darwin') {
    console.error('  macOS: xcode-select --install (command line tools) or brew install python3');
  } else {
    console.error('  Linux: apt install python3 / yum install python3');
  }
  process.exit(1);
}

// Do not inject PYTHONUTF8: it leaks through cct.py into the wrapped claude and its descendant
// processes (settled by audit); encoding is handled by cct.py/picker.py/relay_anthropic.py each
// doing its own reconfigure + explicit encoding.
const child = spawn(
  py[0],
  [...py.slice(1), path.join(__dirname, 'cct.py'), ...process.argv.slice(2)],
  { stdio: 'inherit' }
);
// Ctrl+C belongs to the claude inside and to cct.py (which has an exit receipt to print);
// the shim plays dead and just waits for the exit code.
process.on('SIGINT', () => {});
process.on('SIGTERM', () => { try { child.kill('SIGTERM'); } catch (e) { /* already exited */ } });
child.on('error', (e) => {
  console.error('✗ failed to launch Python:', e.message);
  process.exit(1);
});
// Death by signal (code=null) folds to 128+n per bash's convention (SIGKILL→137 etc.), else 130
child.on('exit', (code, sig) =>
  process.exit(code === null ? 128 + (os.constants.signals[sig] || 2) : code));
