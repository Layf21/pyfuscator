#! /bin/env python

import argparse
import dis
import hashlib
import importlib.util
import marshal
import struct
from functools import partial, wraps
from random import choice, choices, getrandbits, randbytes, randint, random, shuffle
from types import CodeType

import bytecode
from bytecode import (
    BasicBlock,
    BinaryOp,
    Bytecode,
    Compare,
    ConcreteBytecode,
    ControlFlowGraph,
    Instr,
    Label,
)

bytecode.concrete._set_docstring = lambda a, b: None # docstring would leak the first const if it is a string

def load_file(filename):
    with open(filename, encoding="utf-8") as f:
        return compile(f.read(), filename, "exec")

salt = random() # needs to be global and static so hashed cells are valid across functions
stacksize = None # keep track of the current stack size (ugly global i know)

def convert_code(c, t):
    if isinstance(c, CodeType):
        if t == CodeType:
            return c
        if t == ConcreteBytecode:
            return ConcreteBytecode.from_code(c)
        if t == Bytecode:
            return Bytecode.from_code(c)
        if t == ControlFlowGraph:
            return ControlFlowGraph.from_bytecode(Bytecode.from_code(c))
    elif isinstance(c, ConcreteBytecode):
        if t == CodeType:
            return c.to_code(stacksize=stacksize, compute_exception_stack_depths=False)
        if t == ConcreteBytecode:
            return c
        if t == Bytecode:
            return c.to_bytecode()
        if t == ControlFlowGraph:
            return ControlFlowGraph.from_bytecode(c.to_bytecode())
    elif isinstance(c, Bytecode):
        if t == CodeType:
            return c.to_code(stacksize=stacksize, compute_exception_stack_depths=False)
        if t == ConcreteBytecode:
            return c.to_concrete_bytecode()
        if t == Bytecode:
            return c
        if t == ControlFlowGraph:
            return ControlFlowGraph.from_bytecode(c)
    elif isinstance(c, ControlFlowGraph):
        if t == CodeType:
            return c.to_code(stacksize=stacksize, compute_exception_stack_depths=False)
        if t == ConcreteBytecode:
            return c.to_bytecode().to_concrete_bytecode()
        if t == Bytecode:
            return c.to_bytecode()
        if t == ControlFlowGraph:
            return c
    raise ValueError(f"{t} is not a valid target type")

def cast_arg(argtype):
    def ensure_type(func):
        @wraps(func)
        def inner(c):
            return func(convert_code(c, argtype))
        return inner
    return ensure_type



# --- Bytecode manipulation

@cast_arg(Bytecode)
def obfuscate_consts(bc: Bytecode):
    global stacksize
    stacksize += 3

    def create_int_instr(val: int):
        a = getrandbits(64)
        b = val ^ a
        assert a^b == val
        return [
            Instr("LOAD_CONST", a),
            Instr("LOAD_CONST", b),
            Instr("BINARY_OP", BinaryOp.XOR)
        ]

    def create_str_instr(string: str):
        if not string:
            return [Instr("LOAD_CONST", "")]
        data = string.encode("utf-8", errors="surrogatepass")

        a = randbytes(len(data))
        b = bytes(x ^ y for x, y in zip(a, data))

        instrs = []

        for i in range(len(data)):
            # accumulator <<= 8
            if i != 0:
                instrs.extend([
                    Instr("LOAD_CONST", 8),
                    Instr("BINARY_OP", BinaryOp.LSHIFT),
                ])

            # current_byte = a[i] ^ b[i]
            instrs.extend([
                Instr("LOAD_CONST", a[i]),
                Instr("LOAD_CONST", b[i]),
                Instr("BINARY_OP", BinaryOp.XOR),
            ])

            if i != 0:
                # accumulator |= current_byte
                instrs.append(
                    Instr("BINARY_OP", BinaryOp.OR)
                )

        # accumulator.to_bytes(len(data), "big").decode("utf-8")
        instrs.extend([
            Instr("LOAD_ATTR", (True, "to_bytes")),
            Instr("LOAD_CONST", len(data)),
            Instr("LOAD_CONST", "big"),
            Instr("CALL", 2),

            Instr("LOAD_ATTR", (True, "decode")),
            Instr("LOAD_CONST", "utf-8"),
            Instr("CALL", 1),
        ])

        return instrs

    def create_bool_instr(b: bool):
        if b:
            k = getrandbits(32)
            return [
                Instr("LOAD_CONST", k),
                Instr("LOAD_CONST", k),
                Instr("COMPARE_OP", Compare.EQ_CAST)
            ]
        else:
            x = getrandbits(32)
            y = getrandbits(32)
            while x == y:
                y = getrandbits(32)

            return [
                Instr("LOAD_CONST", y),
                Instr("LOAD_CONST", x),
                Instr("COMPARE_OP", Compare.EQ_CAST)
            ]

    i = 0
    while i < len(bc):
        if type(bc[i]) == Instr and bc[i].name == "LOAD_CONST":
            replacement = None
            if type(bc[i].arg) == str:
                replacement = create_str_instr(bc[i].arg)
            elif type(bc[i].arg) == bool:
                replacement = create_bool_instr(bc[i].arg)
            elif type(bc[i].arg) == int:
                replacement = create_int_instr(bc[i].arg)
            if replacement:
                bc[i:i+1] = replacement
                i += len(replacement)-1
        i += 1
    return bc


@cast_arg(Bytecode)
def insert_dead_code(bc: Bytecode, frequency=0.2): # this is to easy to strip out, more variation needed
    global stacksize
    stacksize += 2

    i = 5 # skips RESUME etc.
    while i < len(bc):
        if not isinstance(bc[i], Instr) or bc[i].name == "END_FOR": # I do not know why END_FOR breaks
            i += 1
            continue
        if random() < frequency:
            r = random()
            if r < 0.3:
                consts = [i.arg for i in bc if isinstance(i, Instr) and i.name == "LOAD_CONST"]
                if len(consts) < 1:
                    continue

                bc.insert(i, Instr("LOAD_CONST", choice(consts)))
                i += 1
                bc.insert(i, Instr("POP_TOP"))
                i += 1

            else:
                eod = Label()
                a = randbytes(32)
                b = randbytes(32)
                while b == a:
                    b = randbytes(32)
                bc[i:i] = [
                    Instr("LOAD_CONST", a),
                    Instr("LOAD_CONST", b),
                    Instr("COMPARE_OP", Compare.EQ),
                    Instr("POP_JUMP_IF_FALSE", eod)
                ]
                i += 4

                ded_code = list(filter(lambda x: isinstance(x, Instr) and not x.has_jump(), choices(bc, k=randint(0, 30))))
                bc[i:i] = ded_code
                i += len(ded_code)

                bc.insert(i, eod)
                i += 1
        i += 1

    return bc

# --- control flow manipulation

@cast_arg(ControlFlowGraph)
def print_cfg(cfg: ControlFlowGraph):
    print()
    for b in cfg:
        print(f"[{cfg.get_block_index(b)}] --> [{cfg.get_block_index(b.next_block) if b.next_block else "/"}] (--> [{cfg.get_block_index(b.get_jump()) if b.get_jump() is not None else "/"}])")
        for i in b:
            if isinstance(i, Instr):
                a = f"[{cfg.get_block_index(i.arg)}]" if isinstance(i.arg, BasicBlock) else i.arg
                print("    "+i.name, a)
            else:
                print("    "+str(i))


@cast_arg(ControlFlowGraph)
def split_cfg(cfg: ControlFlowGraph, frequency=0.05):
    # kinda bad as large blocks get subdivided less, this will not target a uniform block size
    i = 0
    while i < len(cfg):
        if random() < frequency*len(cfg[i]):
            if len(cfg[i]) < 5:
                i += 1
                continue
            cfg.split_block(cfg[i], randint(1, len(cfg[i])-1))
            i += 1
        i += 1
    return cfg



@cast_arg(ControlFlowGraph)
def flatten_cfg(cfg: ControlFlowGraph):
    global stacksize
    stacksize += 4

    # flattening functzion calls would get messy, so i don't do it. Not yet sure if exceptions break when doing this.
    # SEND might also be weird, not sure. Just don't use generators :-)


    def insert_block(cfg: ControlFlowGraph, n, instructions=None) -> BasicBlock:
        if len(cfg) == n:
            cfg.add_block(instructions)
            return
        block = BasicBlock(instructions)

        if n < len(cfg._blocks):
            block.next_block = cfg._blocks[n]
        if n > 0 and cfg._blocks[n-1].next_block is not None:
            cfg._blocks[n-1].next_block = block

        cfg._blocks.insert(n, block)

        for existing_block in cfg._blocks[n+1:]:
            cfg._block_index[id(existing_block)] += 1

        cfg._block_index[id(block)] = n

        return block

    jumpmap = {}
    def gen_to_dispatcher(cfg: ControlFlowGraph, n, target):
        key = getrandbits(64)
        while key in jumpmap:
            key = getrandbits(64)
        jumpmap[key] = target
        return insert_block(cfg, n, [
            Instr("LOAD_CONST", key),
            Instr("JUMP_BACKWARD", dispatcher)
        ])

    def gen_dispatcher(cfg: ControlFlowGraph, jumpmap, n):
        items = list(jumpmap.items())
        shuffle(items)

        jumpout_blocks = {}
        for key, target in items:
            jumpout_blocks[key] = insert_block(cfg, n, [
                Instr("POP_TOP"),
                Instr("JUMP_FORWARD", target)
            ])


        """ # Should ideally not be reached.
        insert_block(cfg, n, [
            Instr("PUSH_NULL"), 
            Instr("LOAD_CONST", "Dispatcher failed:"),
            Instr("LOAD_NAME", "print"), 
            Instr("SWAP", 4),
            Instr("CALL", 2),
            Instr("POP_TOP"),
            Instr("LOAD_NAME", "exit"), 
            Instr("PUSH_NULL"), 
            Instr("LOAD_CONST", 1),
            Instr("CALL", 1),
            Instr("POP_TOP"),
            Instr("LOAD_CONST", None),
            Instr("RETURN_VALUE")
        ])
        """

        for key, target in items:
            insert_block(cfg, n, [
                Instr("COPY", 1),
                Instr("LOAD_CONST", key),
                Instr("COMPARE_OP", Compare.EQ_CAST),
                Instr("POP_JUMP_IF_TRUE",jumpout_blocks[key])
            ])


    key = getrandbits(64)
    jumpmap[key] = cfg[0] # store entrypoint
    dispatcher = insert_block(cfg, 0) # placeholder
    insert_block(cfg, 0, [Instr("LOAD_CONST", key)]) # entry hook that jumps to the original cfg[0] via dispatcher
    
    # Preserve all entry setup instructions (e.g. RESUME, MAKE_CELL) in cfg[0]
    l = []
    while cfg[2] and cfg[2][0].name in ("RESUME", "COPY_FREE_VARS", "MAKE_CELL"):
        l.append(cfg[2].pop(0))
    cfg[0][0:0] = l

    i = 2
    end = len(cfg)
    while i < end:
        b = cfg[i]
        jump_target = b.get_jump()
        next_target = b.next_block

        if b.get_last_non_artificial_instruction() and b.get_last_non_artificial_instruction().name == "FOR_ITER":
            # Keep FOR_ITER's exit jump direct to preserve loop stack state
            if next_target:
                gen_to_dispatcher(cfg, i + 1, next_target)
                i += 1
                end += 1
            i += 1
            continue

        if next_target:
            gen_to_dispatcher(cfg, i+1, next_target)
            i += 1
            end += 1

        if jump_target:
            b.get_last_non_artificial_instruction().arg = gen_to_dispatcher(cfg, i+1, jump_target)
            if b.get_last_non_artificial_instruction().is_uncond_jump():
                b.get_last_non_artificial_instruction().name = "JUMP_FORWARD"
            i += 1
            end += 1
        i += 1

    gen_dispatcher(cfg, jumpmap, 2)

    return cfg


# --- Post processing

@cast_arg(CodeType)
def strip_metadata(c: CodeType):
    return c.replace(
        co_filename="", 
        co_name="", 
        co_firstlineno=0xdead,
        co_linetable=b"", 
    )

@cast_arg(CodeType)
def strip_varnames(c: CodeType):
    def name(i):
        h = hashlib.blake2b(
            f"{salt}:{i}".encode(),
            digest_size=16
        ).hexdigest()
        return "_" + h
    return c.replace(
        co_varnames=tuple(name(i) for i in c.co_varnames), 
        co_cellvars=tuple(name(i) for i in c.co_cellvars), 
        co_freevars=tuple(name(i) for i in c.co_freevars)
    )

@cast_arg(CodeType)
def strip_names(c: CodeType, marker="__obf"):
    def name(i):
        h = hashlib.blake2b(
            f"{salt}:{i}".encode(),
            digest_size=16
        ).hexdigest()
        return "_" + h
    return c.replace(
        co_names=tuple(name(i) if i.endswith(marker) else i for i in c.co_names)
    )

def apply_recursively(c: CodeType, f):
    new_consts = list(c.co_consts)
    for i in range(len(new_consts)):
        if type(new_consts[i]) == CodeType:
            new_consts[i] = apply_recursively(new_consts[i], f)
    return f(c.replace(co_consts=tuple(new_consts)))


# --- main


def write_pyc(code, filename):
    with open(filename, "wb") as f:
        # Magic number
        f.write(importlib.util.MAGIC_NUMBER)
        f.write(struct.pack("<I", 0))
        f.write(struct.pack("<I", getrandbits(32)))
        f.write(struct.pack("<I", getrandbits(32)))

        marshal.dump(code, f)
    
recipe_map = {
    "s": split_cfg, 
    "f": flatten_cfg, 
    "c": obfuscate_consts, 
    "d": insert_dead_code, 
    "n": strip_names, 
    "v": strip_varnames, 
    "m": strip_metadata
}
def obfuscate_once(c: CodeType, recipe="sfcdnvm"):
    global stacksize
    stacksize = c.co_stacksize
    print("Obfuscating "+c.co_name)


    for i, op in enumerate(recipe):
        f = recipe_map[op]
        print(f"[{i+1}/{len(recipe)}] {f.__name__}{' '*max(len(x.__name__) for x in recipe_map.values())}", end="\r", flush=True)
        c = f(c)
    print()
    
    return convert_code(c, CodeType)

def obfuscate(c, recipe="sfcdnvm"):
    return apply_recursively(c, partial(obfuscate_once, recipe=recipe))


def main():
    parser = argparse.ArgumentParser(
        prog="pyfuscate",
        description="Turn .py files into obfuscated .pyc files."
    )
    parser.add_argument(
        "infile",
        help="Python source file to obfuscate"
    )
    parser.add_argument(
        "outfile",
        nargs="?",
        default="out.pyc",
        help="Output .pyc file (default: out.pyc)"
    )
    parser.add_argument(
        "-r", "--recipe",
        default="sfcdnvm",
        help='Obfuscation steps to apply (default: "sfcrdnvm"). '
             'Characters: s=split cfg, f=flatten cfg, c=obfuscate consts, '
             'r=replace instructions, d=dead code, n=strip names, '
             'v=strip varnames, m=strip metadata'
    )
    parser.add_argument(
        "--dis-before",
        action="store_true",
        help="Print dis.dis output of the original bytecode before obfuscation"
    )
    parser.add_argument(
        "--dis-after",
        action="store_true",
        help="Print dis.dis output of the obfuscated bytecode after obfuscation"
    )
    parser.add_argument(
        "--dis",
        action="store_true",
        help="Shorthand for --dis-before and --dis-after"
    )
    parser.add_argument(
        "--dis-depth",
        type=int,
        default=None,
        help="Recursion depth for dis.dis (default: unlimited)"
    )
    parser.add_argument(
        "--exec",
        action="store_true",
        dest="execute",
        help="Execute the obfuscated code after writing (for testing)"
    )

    args = parser.parse_args()

    invalid = [c for c in args.recipe if c not in "sfcrdnvm"]
    if invalid:
        parser.error(f"Invalid recipe character(s): {''.join(invalid)}")

    code = load_file(args.infile)

    if args.dis_before or args.dis:
        print("=== dis.dis BEFORE obfuscation ===")
        dis.dis(code, depth=args.dis_depth)
        print()

    obfuscated_code = obfuscate(code, args.recipe)

    if args.dis_after or args.dis:
        print("=== dis.dis AFTER obfuscation ===")
        dis.dis(obfuscated_code, depth=args.dis_depth)
        print()

    print(f"Writing to {args.outfile}")
    write_pyc(obfuscated_code, args.outfile)
    print("Done.")

    if args.execute:
        print("=== Executing obfuscated code ===")
        exec(obfuscated_code)  # noqa: S102


if __name__ == "__main__":
    main()