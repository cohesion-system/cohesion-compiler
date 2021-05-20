"""Blue-Green coloring for a Python AST.  The colors are defined as
follows.

Every node in the AST is classified into one of two colors, blue and
green.

A node is green iff:
(a) it is a function call to a cohesion task, or
(b) it is a function call to a green function, or
(c) it has a green child node (e.g. it is a function definition that
    contains a call to a cohesion task, or a loop whose body contains
    such a call)

A node is blue if it is not green.

Subtrees that are blue will be left entirely unchanged from source to
output.  These are subtrees that have no cohesion calls in them,
statically and dynamically.

(We're making some assumptions here that "weird" ways of calling
functions aren't used, for example eval, exec, dynamically looking up
function symbols, etc.  In other words we're assuming that we can
statically figure out the dynamic call graph, at least the parts that
call tasks.  To mitigate this, we actually define the cohesion.* calls
to panic at runtime, and issue compile-time warnings for use of
exec/eval.)

Green subtrees are where tasks are invoked.  Tasks are invoked thru
the synchronous cohesion.* interface, which allows the programmer to
call lambdas as if they are local functions.  Actually, green subtrees
aren't subtrees -- they are a path from a function definition to a
green function call.

Green nodes "explode" into step functions.  Python loops become step
function loops, if statements become step function if states, and so
on; all other nodes under green nodes become python code again, but
now that code is "exploded" into many pieces.

Green nodes will be translated to the Cohesion AST (cast): ast.If to
cast.If, ast.Call to cast.Call, ast.For to cast.Loop, and so on.  In a
green sub tree, functions get split into CAST nodes and pure-Python
AST nodes; the python nodes get emitted as functions and the cast
nodes as step functions.

Function calls to blue functions will remain unmodified; function
calls to green functions will either be (nested) step function calls
or step function states (most commonly lambda invocations).

"""

import typing
import ast
import config

def nameReferences(name: ast.AST, moduleName: str) -> bool:
    """
    Does NAME reference MODULENAME?
    i.e. is NAME either MODULENAME or MODULENAME.something.something?
    """
    if isinstance(name, ast.Name) and name.id == moduleName:
        return True
    elif isinstance(name, ast.Attribute):
        return nameReferences(name.value, moduleName)
    else:
        return False

# TODO: problem! we risk coloring random extra nodes green -- e.g.
#
# def foo()
#    Lambda.something()
#    for i in [1,2,3]:
#        blue(i)
#
# that for loop should not be green but we will color it green
#
# solution:
#
# Keep a stack of nodes.  This stack is the path of nodes from root
# (function node, i think) to the current node.  When we find a
# cohesion call, color everything in the stack green.  No
# current_color etc.  We still need to run multiple times because a
# function may get colored only after we've visited calls to it.
#
class BlueGreenWalker(ast.NodeVisitor):
    """Walks an ast and does one pass of blue-green coloring.  See
    definition under the coloring.bluegreen function.  Only coloring
    is done, no other node transformations.  Blue is represented as
    False and green as True.

    This node walker has to walk the tree multiple times until it
    identifies no change.

    """
    def __init__(self, moduleName: str):
        if len(moduleName) == 0:
            moduleName = 'cohesion'
        self.moduleName = moduleName

        self.changes_made = False
        self.green_functions = set([])

        # Path of ast nodes from current node to enclosing function,
        # with the function def node at the bottom of the stack
        self.node_stack = []

    def _make_green(self, node: ast.AST):
        """Turn a node green.  If it's a function, add it to the green
        functions list.

        """
        if is_green(node):
            return
        node.color = True
        self.changes_made = True
        if isinstance(node, ast.FunctionDef):
            self.green_functions.add(node.name)

    def _make_all_green(self, nodes: typing.List[ast.AST]):
        for n in nodes:
            self._make_green(n)
            
    def visit_Module(self, node):
        self.generic_visit(node)
        # Just color all modules green so we always descend into them
        if not is_green(node):
            node.color = True
            self.changes_made = True

    def _push_and_visit(self, node):
        self.node_stack.append(node)
        self.generic_visit(node)
        self.node_stack.pop()
            
    def visit_FunctionDef(self, node):
        self._push_and_visit(node)

    def visit_Expr(self, node):
        self._push_and_visit(node)

    def visit_For(self, node):
        self._push_and_visit(node)

    def visit_While(self, node):
        self._push_and_visit(node)

    def visit_If(self, node):
        self._push_and_visit(node)

    def visit_Assign(self, node):
        self._push_and_visit(node)

    def visit_AnnAssign(self, node):
        self._push_and_visit(node)

    def visit_Try(self, node):
        self._push_and_visit(node)

    def visit_Call(self, node):
        if is_green(node):
            # already visited, nothing to do
            return

        self.node_stack.append(node)
        
        # callee is a lambda or other cohesion thing, or
        # callee is already colored green previously (i.e. indirectly calls)
        #
        # This analysis fails when you make indirect/dynamic calls
        # (through function pointers, eval, etc).
        if (nameReferences(node.func, self.moduleName) or
            (isinstance(node.func, ast.Name) and (node.func.id in self.green_functions))):
            self._make_all_green(self.node_stack)
            
        self.node_stack.pop()

        # we also need to visit our arguments. But a green call inside
        # our args doesn't automatically make this call green, so we
        # do it after popping this call off the stack.
        self.generic_visit(node)

    def visit_Return(self, node):
        if is_green(node):
            return

        # a return is green iff the function it's in is green

        # so we find the top-most functiondef on the stack, and check if it's green -> then we're green too.
        funcdef = None
        for n in self.node_stack:
            if isinstance(n, ast.FunctionDef):
                funcdef = n
        if funcdef == None:
            raise Exception("return outside a function?")

        self.node_stack.append(node)
        if is_green(funcdef):
            self._make_all_green(self.node_stack)
        self.node_stack.pop()

        self.generic_visit(node)
        
    def visit_Break(self, node):
        if is_green(node):
            return
        # break is a lot like return -- it's green if the containing loop is green
        loopdef = None
        for n in self.node_stack:
            if isinstance(n, ast.While):
                loopdef = n
            elif isinstance(n, ast.For):
                loopdef = n
        if loopdef == None:
            raise Exception("break outside a loop")
        self.node_stack.append(node)
        if is_green(loopdef):
            self._make_all_green(self.node_stack)
        self.node_stack.pop()
        # no need for generic_visit, we're done
        

    # TODO(v2) handle coloring of python lambda expression (i.e. does
    # it call a green func)

    # TODO(v2) handle coloring of async function def (i.e. does it
    # call a green function)

    # TODO(vN) handle await.  A few options to handle it, could do it
    # by pessimistically waiting or by using the SQS waitForTaskToken
    # task





def bluegreen(cfg: config.Config, tree: ast.AST) -> ast.AST:
    """
    Coloring pass.  See top of this file for explanation.

    This pass invokes the blue-green node transformer until there are no changes.

    The blue/green information is used in later passes to split the function.

    """

    # TODO we actually need a name mangling pass before this one, to
    # make function names unique; otherwise our coloring analysis can
    # break when there are non-unique function names.

    moduleName = 'cohesion'

    w = BlueGreenWalker(moduleName)

    while True:
        w.changes_made = False
        w.visit(tree)
        if not w.changes_made:
            break

    return tree


def is_green(node: ast.AST) -> bool:
    return ('color' in node.__dict__) and (node.color == True)

class DumpWalker(ast.NodeVisitor):
    """
    Partial dump of the AST for debugging blue/green colors.
    """
    def __init__(self):
        self.out = ""

    def _print_green(self, msg):
        self.out += ("\033[1;32;40m%s\033[0m" % msg)
    def _print(self, msg):
        self.out += msg

    def visit_FunctionDef(self, node):
        if is_green(node):
            self._print_green("[")

        self._print("FunctionDef %s " % node.name)
        self.generic_visit(node)
        
        if is_green(node):
            self._print_green("]")

    def visit_For(self, node):
        if is_green(node):
            self._print_green("[")

        self._print("FOR %s " % node.target.id)
        self.generic_visit(node)
        
        if is_green(node):
            self._print_green("]")
            
    def visit_Call(self, node):
        if is_green(node):
            self._print_green("[")

        self._print("Call %s" % ast.dump(node.func, False))
        self.generic_visit(node)
        
        if is_green(node):
            self._print_green("]")

    def visit_Assign(self, node):
        if is_green(node):
            self._print_green("[")

        self._print("Assign ")
        self._print(ast.dump(node.targets[0]))
        self._print(" = ")
        self.generic_visit(node.value)
        
        if is_green(node):
            self._print_green("]")


def dump(cfg: config.Config, tree: ast.AST) -> ast.AST:
    """
    Partial dump pass, to debug colors.
    """
    w = DumpWalker()
    w.visit(tree)
    print(w.out)
    return tree
