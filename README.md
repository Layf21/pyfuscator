# pyfuscate

Python bytecode obfuscator. Takes a `.py` file, compiles it, mangles it at the bytecode level and writes a `.pyc` which is substantially harder to reverse.

Requires the `bytecode` library, only tested with python 3.14. 

> This is just a small side project/poc/toy, do not rely on it for anything serious! There are likely a lot of bugs and unhandled edge cases, I did not use a test suite. This is not a professional obfuscator. Just use cython + Tigress/OLLVM/VMProtect/Themidia instead.

```
pip install bytecode
python pyfuscate.py script.py out.pyc
```

## What it does

Obfuscation runs as a pipeline of steps, called a recipe. The default recipe is `sfcdnvm`. Each character is one step:

| Flag | Step | What it does |
|------|------|--------------|
| `s` | split CFG | Chops basic blocks into smaller pieces at random points |
| `f` | flatten CFG | Replaces all jumps with a central dispatcher |
| `c` | obfuscate consts | Integers become XOR pairs, strings become bytewise XOR chains, booleans become comparisons |
| `d` | dead code | Inserts unreachable junk instructions |
| `n` | strip names | Renames globals that end in `__obf` to hashed identifiers |
| `v` | strip varnames | Renames all local variables to hashed identifiers |
| `m` | strip metadata | Clears filename, line numbers, and the line table |

Steps run left to right, so order matters. Flattening after splitting (`sf`) gives the dispatcher more blocks to work with. Obfuscating consts after flattening (`fc`) also hits the dispatcher's own constants.

## Usage

```
python pyfuscate.py [-h] [-r RECIPE] [--dis-before] [--dis-after] [--dis] [--dis-depth N] [--exec] infile [outfile]
```

```
positional arguments:
  infile          source .py file
  outfile         output path (default: out.pyc)

options:
  -r, --recipe    obfuscation recipe string (default: sfcdnvm)
  --dis-before    disassemble original bytecode before obfuscating
  --dis-after     disassemble obfuscated bytecode after
  --dis           both of the above
  --dis-depth N   limit dis recursion depth (default: unlimited)
  --exec          execute the obfuscated code after writing (for testing)
```

Running the obfuscated file:
```
python out.pyc
```

Importing an obfuscated file is still possible just like you would expect:
```py
import out
```

Keep in mind that the globals will be renamed if and only if they end in __obf, so you can't access them with the same name.


`test_small.out.txt` contains an example output generated with the default recipe (`./pyfuscate.py --dis test_small.py`). As one can see, the size jumped from ~40 Instructions to way over 1000 and readability dropped massively.

## Caveats

- **Really unstable.** Do not use this in production. I did not run any exhaustive tests. Things like exceptions or generators are especially likely to break.
- **Bad performance.** Loading constants, especially strings, control flow flattening and dead code worsen performance noticeably. File size also increases drastically.
- **--exec** is a bit broken when it comes to imports/globals. Not sure why, but executing the generated .pyc often works while --exec does not.
- **Parsing .pyc files instead of .py files** is possible, but that functionality is not exposed to the command line, as I feel like that scenario is rare and harder to set up because of python version mismatches. 
- **Tested with 3.14 only.** The bytecode format changes between minor versions. This is likely not going to work on 3.12 or 3.13 without minor changes.
- **No encryption.** The bytecode runs in a standard CPython interpreter. Anyone with enough patience can reverse it. The goal is to raise the bar, not to make reversal impossible.
- **No anti debugger.** Extracting data is still relatively easy by attaching a debugger and reading out the decoded values at key parts.
- **No "cross-code" obfuscation.** All obfuscatrion methods used are applied per code object, thus they can also be undone by only looking at one code object. Implementing methods which reach across multiple functions would increase both deobfuscation and obfuscation complexity. This also means that the broad function structure (function count, what function calls what other functions, argument count etc.) can still be extracted easily.
- **All on bytecode level.** No AST parsing takes place, which might be beneficial in some cases but probably leads to instability in most.
