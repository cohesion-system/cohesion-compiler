
import sys
import argparse
import typing
import ast
import tempfile
import pathlib

import coloring
import gensym
import variables
import emit
from aws import asfast
import cast
import lift
import astor
import config

def read(cfg: config.Config, sourceFile: str) -> str:
    """
    Return contents of source file.
    """
    with open(sourceFile) as f:
        return f.read()

def parse(cfg: config.Config, source: str) -> ast.AST:
    """
    Parses source string into a Python AST.
    """
    return ast.parse(source)

def dump(cfg: config.Config, tree: ast.AST) -> ast.AST:
    """
    Returns the tree with no changes; also dumps it to stdout.
    """
    print(ast.dump(tree, False, False))
    return tree

def srcdump(cfg: config.Config, tree: ast.AST) -> ast.AST:
    print(astor.to_source(tree))
    return tree


def aggregate(cfg: config.Config, tree: ast.AST) -> cast.Aggregate:
    agg = cast.Aggregate(None)
    agg.pythonAst = tree
    return agg

def summary(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    numWorkflows = 1
    numStates = len(agg.workflowAst.defs[0].states)
    numFuncs = len(agg.pythonFunctions)
    print("Generated %s Step Function with %s states, and generated %s lambdas" % (numWorkflows, numStates, numFuncs))

def coco(cfg: config.Config, source: str):
    """Main compiler entry point.  Just a simple pipeline of passes.
    First set of passes is on Python AST, and the rest is on a hybrid
    object we call an "Aggregate".

    """
    passes = [
        { 'enabled': cfg.get('from_file'), 'func': read, 'desc': "Path to source string" },
        { 'enabled': True,  'func': parse,              'desc': "Source string to AST" },

        #
        # The following passes operate on the Python AST (AST in, AST out)
        #
        { 'enabled': False, 'func': dump,               'desc': "AST debugging dump"},
        { 'enabled': True,  'func': gensym.gensym_init, 'desc': "Initialize name table to allow generating unique names"},
        { 'enabled': False, 'func': gensym.gensym_dump, 'desc': "Unique names debug dump"},

        #
        # Color the tree: green for stuff that will change.  Blue for stuff to leave unchanged.
        #
        { 'enabled': True,  'func': coloring.bluegreen, 'desc': "blue-green coloring"},
        { 'enabled': False, 'func': coloring.dump,      'desc': "coloring debug dump"},

        #
        # A few "lift X out of Y" transforms: lift green calls out of
        # expressions; lift expressions out of if and loop tests; lift
        # expressions out of call args
        #
        { 'enabled': True,  'func': lift.calls, 'desc': "Lift remote calls out of Python exprs"},

        #
        # Move variables into state dictionary
        #
        { 'enabled': True,  'func': variables.rewrite, 'desc': "Rewrite variable accesses to use a dictionary"},

        #
        # Translate back to source, for a debug dump
        #
        { 'enabled': False, 'func': srcdump, 'desc': "Src debugging dump"},
        
        #
        # AST -> Aggregate(ast = AST, everything else null)
        #
        # The following passes all operate on the "Aggregate", which
        # is a struct containing the Python AST, the CAST (Cohesion
        # AST), the backend-workflow AST (ASFAST) and a list of Python
        # functions (as Python ASTs).
        #
        { 'enabled': True, 'func': aggregate, 'desc': "Place Python AST into Aggregate wrapper object" },

        #
        # AST -> Aggregate{CAST,[<empty list of lambdas>]}
        #
        { 'enabled': True,  'func': cast.build, 'desc': "Build CAST"},
        { 'enabled': False, 'func': cast.dump,  'desc': "Debug dump CAST"},
        
        #
        # Eliminate PythonAST nodes, by moving them into separate functions
        #
        { 'enabled': True, 'func': cast.remove_python, 'desc': "Eliminate PythonAST nodes from CAST" },
        
        #
        # Generic backend, emit registry of functions and step
        # functions -- just a list of metadata for what we've
        # outputted.
        #
        { 'enabled': True,  'func': emit.emit_registry,   'desc': "Emit platform-independent YAML metadata for Python and Workflow Functions"},

        #
        # Platform-specific backend: AWS step functions + AWS lambda
        #
        { 'enabled': True,  'func': asfast.build,        'desc': "Build AWS Step Functions AST (ASFAST)"},
        { 'enabled': True,  'func': asfast.remove_pass,  'desc': "Remove extra pass nodes from step function"},
        { 'enabled': True,  'func': asfast.build_graphs, 'desc': "Build AWS Step Functions Visualization Graph"},
        { 'enabled': False, 'func': asfast.dump,         'desc': "Debug dump of AWS Step Functions AST"},
        { 'enabled': True,  'func': asfast.emit_json,    'desc': "Emit JSON for AWS Step Functions and their visualizations"},

        { 'enabled': True,  'func': asfast.generate_router_func, 'desc': "Generate Python router function"},
        { 'enabled': True,  'func': asfast.wrap_lambdas, 'desc': "Wrap Python functions in Lambda signature"},
        { 'enabled': True,  'func': asfast.emit_lambdas, 'desc': "Emit cloud functions as Lambdas"},

        { 'enabled': True,  'func': summary, 'desc': 'Just print a summary of what we did' },


        #
        # Platform-specific backend for emitting deployment code.
        # Initial support: a generic yaml with all the info, aws-sam,
        # maybe serverless.yaml, CFN?, CDK, Pulumi?, etc.
        #
    ]
    i = source
    for p in passes:
        if p['enabled']:
            func = p['func']
            i = func(cfg, i)
    return i

def cli():
    """
    Cohesion compiler as CLI tool.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help = "source file to compile")
    parser.add_argument("-c", "--config", help = "path to config.json [default ./config.json]", default="config.json")
    parser.add_argument("-o", "--output", default = "build", help = "output directory")
    args = parser.parse_args()    

    cfg = config.Config(args.config)
    cfg.set('from_file', True)
    cfg.set('output_dir', args.output)

    pathlib.Path(args.output).mkdir(parents=True, exist_ok=True)
    
    coco(cfg, args.source)

