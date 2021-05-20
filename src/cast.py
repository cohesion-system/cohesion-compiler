"""CAST (Cohesion AST) is an intermediate AST.

To build the CAST we need to "lift" all green-colored python nodes
into the CAST, with un-transformed Python ASTs as nodes below CAST
nodes.

The CAST then gets transformed into a workflow (such as ASF) and the
python AST subtrees become lambda functions invoked by that workflow.

"""


import ast
import typing
import coloring
import astor
import gensym
import config

class SourceLocation:
    def __init__(self, line=0, col=0):
        self.line = line
        self.col = col
    def __str__(self):
        return f"@[{self.line},{self.col}]"

class CAST:
    def __init__(self, loc=None):
        self.loc = SourceLocation()

        # If defined, locEnd means that the cast node represents a
        # source location *range* rather than just a single location.
        self.locEnd = None

    def set_loc(self, node):
        """Set location of this node from a Py-AST node or another CAST node"""
        if isinstance(node, ast.AST):
            self.loc.line = node.lineno
            self.loc.col = node.col_offset
        elif isinstance(node, CAST):
            self.loc.line = node.loc.line
            self.loc.col = node.loc.col
        return self

    def set_loc_range(self, nodes):
        """Use given list of nodes to set loc and locEnd to the maximum range
        of source represented by the list of nodes

        """
        minLoc = SourceLocation(nodes[0].lineno, nodes[0].col_offset)
        maxLoc = SourceLocation(nodes[0].lineno, nodes[0].col_offset)
        
        class NodeLocRangeFinder(ast.NodeVisitor):
            def __init__(self, minLoc, maxLoc):
                self.minLoc = minLoc
                self.maxLoc = maxLoc

            def visit(self, node):
                if ('lineno' not in dir(node)):
                    return
                # min
                if node.lineno < self.minLoc.line:
                    self.minLoc.line = node.lineno
                elif node.lineno == self.minLoc.line:
                    self.minLoc.col = min(self.minLoc.col, node.col_offset)
                # max
                if node.lineno > self.maxLoc.line:
                    self.maxLoc.line = node.lineno
                elif node.lineno == self.maxLoc.line:
                    self.maxLoc.col = max(self.maxLoc.col, node.col_offset)

        for node in nodes:
            NodeLocRangeFinder(minLoc, maxLoc).visit(node)

        self.loc = minLoc
        self.locEnd = maxLoc
        return self

class Module(CAST):
    """List of CAST Def nodes"""
    def __init__(self, body: typing.List[CAST]):
        super().__init__()
        self.body = body

class PythonAST(CAST):
    """Hold a list of Python AST nodes.  There should be no calls from the
    python ast out to any green functions.

    """
    def __init__(self, astNodes: typing.List[ast.AST]):
        super().__init__()
        self.astNodes = astNodes

class ForLoop(CAST):
    """
    Translation of a Python for loop.  This is always a variable
    iterating over a collection (unlike C or C++ for loops).

    """
    def __init__(self, target: ast.AST, collection: ast.AST, body: CAST, elsebody: CAST = None):
        super().__init__()
        self.target = target
        self.collection = collection
        self.body = body
        # loop-else is an unusual python feature: the body runs when
        # the loop exited normally, i.e. it did not break.  Imagine
        # the break inside an "if"; this is like the else for all the
        # ifs in the loop.
        self.elsebody = elsebody

class WhileLoop(CAST):
    """Python while loop"""
    def __init__(self, test: ast.AST, body: CAST):
        super().__init__()
        self.test = test
        self.body = body

class Break(CAST):
    """Break statement in a loop"""
    pass
        
class Arg(CAST):
    """Workflow function argument"""
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        # TODO: handle default values

class Def(CAST):
    """(Workflow) Function definition.
    """
    def __init__(self, name: str, args: typing.List[Arg], body: CAST):
        super().__init__()
        self.name = name
        self.args = args
        self.body = body


class Call(CAST):
    """Call from a workflow.  Green-colored call nodes in python AST are
    lifted into this node.  The target function could be a workflow or a
    task.

    """
    def __init__(self, func: ast.AST, args: typing.List[ast.AST]):
        super().__init__()
        self.func = func
        self.args = args
        self.timeoutSec = None
        self.heartbeatSec = None
        self.retry = []

class handler:
    """An `except` clause of a try statement (not an independent cast node).
    """
    def __init__(self, types: typing.List[str], name: str, body: CAST):
        self.types = types
        self.name = name
        self.body = body

class Try(CAST):
    """try/except.  The `else` and `finally` clauses are currently unsupported.
    """
    def __init__(self, body: CAST, handlers: typing.List[handler]):
        super().__init__()
        self.body = body
        self.handlers = handlers

    
class Assign(CAST):
    def __init__(self, target: str, value: Call):
        super().__init__()
        self.target = target
        self.value = value

class If(CAST):
    def __init__(self, test, thenBody, elseBody):
        super().__init__()
        self.test = test
        self.thenBody = thenBody
        self.elseBody = elseBody

class Return(CAST):
    def __init__(self, value: ast.AST):
        super().__init__()
        v = None
        if value != None:
            v = varFromEnv(value)
        self.value = v

class Parallel(CAST):

    """Explicit 'static' parallelism -- run each node in parallel.
    (Currently not generated; we'll have to introduce some new
    syntax.)

    """
    def __init__(self, node):
        super().__init__()
        self.nodes = node

class Map(CAST):
    """Data parallelism -- run body once for each item in collection,
    setting variable to that item.

    """
    def __init__(self, variable, collection, body):
        super().__init__()
        pass



# AST -> CAST.
#
# Sequences of blue nodes get wrapped as-is in `PythonAST`.
#
# Green control-flow nodes get "lifted" out of Python into CAST nodes.
# The CAST still is a tree (as opposed to ASFAST which is basically a
# list).
#
# There are no colors any more in the CAST.
#


def transform_list(nodes: typing.List[ast.AST]) -> typing.List[CAST]:
    if nodes == None:
        return None
    result: typing.List[CAST] = []
    curr_blue = None
    for n in nodes:
        #print("--- visiting ----- %s" % n.__class__.__name__)
        if coloring.is_green(n):
            # add curr_blue list to ast
            if curr_blue != None:
                pa = PythonAST(curr_blue)
                result.append(pa)
                curr_blue = None
            # handle green node
            result.append(transform_node(n))
        else:
            if curr_blue == None:
                curr_blue = []
            curr_blue.append(n)
    if curr_blue: # last node was blue
        result.append(PythonAST(curr_blue))
    return result


def transform_green_node(node: ast.AST) -> CAST:
    if not coloring.is_green(node):
        raise Exception("Transform error")

    c = node.__class__
    if c == ast.FunctionDef:
        return Def(name = node.name,
                   args = [Arg(a.arg) for a in node.args.args],
                   body = transform_list(node.body))
    elif c == ast.For:
        return ForLoop(target = astor.to_source(node.target).rstrip(),
                       collection = astor.to_source(node.iter).rstrip(),
                       body = transform_list(node.body))
    elif c == ast.While:
        return WhileLoop(test = node.test,
                         body = transform_list(node.body))
    elif c == ast.If:
        return If(test = node.test,
                  thenBody = transform_list(node.body),
                  elseBody = transform_list(node.orelse))
    elif c == ast.Call:
        argVars = []
        # args should only be vars -- lift.calls lifts out all expressions in (green) function arguments
        # TODO: this pessimises inline constants by adding unnecessary assignments
        for a in node.args:
            argVars.append(varFromEnv(a))

        result = Call(func = astor.to_source(node.func).rstrip(),
                      args = argVars)

        keywordArgs = []
        for k in node.keywords:
            arg = k.arg.lower()
            if arg == 'timeout' or arg == 'timeoutseconds':
                result.timeoutSec = getNumber(k.value)
            elif arg == 'heartbeat' or arg == 'heartbeatseconds':
                result.heartbeatSec = getNumber(k.value)
            elif arg == 'retry':
                result.retry = getRetrier(k.value)

        return result
    
    elif c == ast.Module:
        return Module(body = transform_list(node.body))
    elif c == ast.Assign:
        # TODO for now just support single assignment
        return Assign(varFromEnv(node.targets[0]), transform_node(node.value))

    elif c == ast.Expr:
        # I'm not sure why this Expr node exists and not just directly
        # the Call or whatever.  So we don't model it in the CAST, we
        # just pass thru to whatever node is inside it (e.g. Call)
        return transform_node(node.value)

    elif c == ast.Return:
        return Return(node.value)

    elif c == ast.Break:
        return Break()

    elif c == ast.Try:
        handlers = []
        for eh in node.handlers:
            types = []
            if isinstance(eh.type, ast.Tuple):
                types += [t.id for t in eh.type.elts]
            else:
                types += [astor.to_source(eh.type).rstrip()]

            handlers.append(handler(types = types,
                                    name = eh.name,
                                    body = transform_list(eh.body)))
        return Try(body = transform_list(node.body), handlers = handlers)
    
    else:
        raise Exception("Unhandled node type: %s" % c.__name__)


def transform_node(node: ast.AST) -> CAST:
    if not coloring.is_green(node):
        return PythonAST([node]).set_loc(node)
    else:
        #print("Transforming a %s" % node.__class__.__name__)
        n = transform_green_node(node)
        if not isinstance(node, ast.Module):
            n.set_loc(node)
        return n

# TODO we should move this to top level
class Aggregate:
    def __init__(self, cast: CAST):
        self.pythonAst = None
        self.cast = cast
        self.pythonFunctions = {} # map: name -> ast.FunctionDef (how do i type-annotate this?)
        self.workflowAst = None # contains ASFAST in later passes
        self.cloudFunctions = {} # contains pythonFunctions wrapped into lambdas, in later passes
        self.pythonRouterFuncName = None
        self.workflowGraphs = {} # Workflow visualizations (name -> graph)

    def addPythonFunction(self, node: ast.FunctionDef):
        self.pythonFunctions[node.name] = node

def build(cfg: config.Config, agg: Aggregate) -> Aggregate:
    agg.cast = transform_node(agg.pythonAst)
    return agg

def dump(cfg: config.Config, agg: Aggregate) -> Aggregate:
    print(dump_cast(agg.cast, 0))
    return agg

def dump_cast(node: CAST, indent: int) -> str:
    i = "    " * indent
    out = i
    c = node.__class__
    if c == Def:
        out += "DEF %s(%s):\t%s\n" % (node.name, node.args, node.loc)
        out += "\n".join([dump_cast(n, indent + 1) for n in node.body])
    elif c == ForLoop:
        out += "FOR %s in %s:\n" % (node.target, node.collection)
        out += "\n".join([dump_cast(n, indent + 1) for n in node.body])
    elif c == WhileLoop:
        out += "WHILE %s:\n" % (node.test)
        out += "\n".join([dump_cast(n, indent + 1) for n in node.body])
    elif c == If:
        out += "IF %s:\n" % node.test
        out += "\n".join([dump_cast(n, indent + 1) for n in node.thenBody])
        out += "%sELSE:\n" % i
        out += "\n".join([dump_cast(n, indent + 1) for n in node.elseBody])
    elif c == Call:
        out += "CALL %s(%s)(timeout=%s, hb=%s, retry=%s)\n" % (node.func, node.args, node.timeoutSec, node.heartbeatSec, node.retry)
    elif c == Module:
        out += "\n".join([dump_cast(n, indent + 1) for n in node.body])
    elif c == PythonAST:
        res = "".join([astor.to_source(n) for n in node.astNodes])

        # indent every line output by astor by indent (astor doesn't accept a base indent level)
        src = "\n".join(["%s%s" % (i, line) for line in res.split("\n")])
        out = "%s{python\n%s}" % (i,src)
    elif c == Assign:
        out += "%s := %s" % (node.target, dump_cast(node.value, indent))
    elif c == Return:
        out += "RETURN %s" % (node.value)
    elif c == Break:
        out += "BREAK"
    elif c == Try:
        out += "TRY:\n"
        out += "\n".join([dump_cast(n, indent + 1) for n in node.body])
        for handler in node.handlers:
            out += "%sEXCEPT %s as %s:\n" % (i, handler.typ, handler.name)
            out += "\n".join([dump_cast(n, indent + 1) for n in handler.body])
    else:
        raise Exception("Unhandled node type: %s" % c.__name__)

    return out


class CASTVisitor:
    def visit(self, node: CAST):
        method = "visit_" + node.__class__.__name__
        f = getattr(self, method, self.generic_visit)
        return f(node)
    def generic_visit(self, node):
        for k in node.__dict__:
            v = node.__dict__[k]
            if isinstance(v, CAST):
                self.visit(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, CAST):
                        self.visit(item)


class CASTTransformer(CASTVisitor):
    def generic_visit(self, node):
        for k in node.__dict__:
            v = node.__dict__[k]
            if isinstance(v, CAST):
                setattr(node, k, self.visit(v))
            if isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], CAST): # assume all items in list have same type
                    newitems = []
                    for olditem in v:
                        newitems.append(self.visit(olditem))
                    setattr(node, k, newitems)
        return node



class PythonASTLifter(CASTTransformer):
    def __init__(self, aggregate):
        self.aggregate = aggregate
        self.wfName = "func"
        if isinstance(self.aggregate.cast, Def):
            self.wfName = self.aggregate.cast.name + "_func"
        elif isinstance(self.aggregate.cast, Module):
            s = self.aggregate.cast.body[0]
            if isinstance(s, Def):
                self.wfName = s.name + "_func"
        
    def visit_PythonAST(self, node: PythonAST) -> Call:
        funcName = gensym.gensym(self.wfName)
        funcNode = (ast.parse("def %s(event, context):\n pass" % funcName)).body[0]
        funcNode.body = node.astNodes

        # The env arg passing is handled in the asfast transform pass
        replacement = Call(func = funcName, args = [])
        replacement.set_loc_range(node.astNodes)

        # add function to aggregate
        self.aggregate.addPythonFunction(funcNode)

        # call the new function from the CAST
        return replacement
        
def remove_python(cfg: config.Config, agg: Aggregate) -> Aggregate:
    PythonASTLifter(agg).visit(agg.cast)
    return agg



def varFromEnv(node: ast.AST) -> str:
    """env['x'] -> x"""

    if not isinstance(node, ast.Subscript):
        raise Exception("Error: expected %s node, got %s (%s)" % (ast.Subscript.__name__, node.__class__.__name__, ast.dump(node)))

    if node.value.id != "env":
        raise Exception("Error: Expected 'env', got '%s'" % ast.value.id)

    if not isinstance(node.slice, ast.Index):
        raise Exception("Internal Error: expected index")
    
    if not isinstance(node.slice.value, ast.Str):
        raise Exception("Internal Error: expected str")

    return node.slice.value.s


def getNumber(node: ast.AST) -> int:
    if isinstance(node, ast.Num):
        return node.n
    else:
        raise Exception("Syntax error: expected num, got %s" % (node.__class__.__name__))

def getString(node: ast.AST) -> str:
    if isinstance(node, ast.Str):
        return node.s
    else:
        raise Exception("Syntax error: expected string, got %s" % (node.__class__.__name__))
    
def getRetrier(node: ast.AST) -> list:
    if not isinstance(node, ast.List):
        raise Exception("Syntax error: expected list of retriers, got %s instead" % (node.__class__.__name__))
    
    result = []
    retriers = node.elts
    for r in retriers:
        if not isinstance(r, ast.Dict):
            raise Exception("Syntax error: expected retrier, got %s instead" % (node.__class__.__name__))

        result.append({})
        for i in range(len(r.keys)):
            k = r.keys[i]
            v = r.values[i]
            
            key = varFromEnv(k)
            if key == "Error":
                value = getString(v)
                result[-1]["ErrorEquals"] = [value]
            elif key == "IntervalSeconds":
                result[-1]["IntervalSeconds"] = getNumber(v)
            elif key == "MaxAttempts":
                result[-1]["MaxAttempts"] = getNumber(v)
            elif key == "BackoffRate":
                result[-1]["BackoffRate"] = getNumber(v)
            else:
                raise Exception("Syntax error: Unknown retry parameter %s" % key)


    return result
