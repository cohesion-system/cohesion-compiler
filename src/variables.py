"""Preparation pass for function splitting: rewrite all variable
load/store/deletes to a dict.

a=b      -> env['a'] = env['b']
delete x -> delete env['x']

This makes the AST invalid code, since we haven't defined the dict
anywhere just yet.  The pass after this one adds the state dict.
"""



import typing
import ast

import coloring
import config

#
# Rewrite variables to a reside in a dictionary.
#
# This prepares for function splitting.
#
# TODO: So far we're avoiding re-writing function names, so that we
# don't have to put every function name into the env dictionary.  We
# should eventually do that.  The following code doesn't work:
#
#    def foo():
#        print("hi")
#
#    def bar():
#        f = foo
#        cohesion.L.some_lambda()
#        f()
# 
# Definitely something we should fix, but for now this case should be
# rare.
#
class VariableRewriter(ast.NodeTransformer):

    def __init__(self):
        self.green = 0

    # Keep track of whether we're in green or blue functions because
    # we only need to edit green ones
    def visit_FunctionDef(self, node):
        oldcolor = self.green
        self.green = coloring.is_green(node)
        self.generic_visit(node)
        self.green = oldcolor
        return node

    def visit_Call(self, node):
        node.args = [self.visit(a) for a in node.args]
        node.keywords = [self.visit(kw) for kw in node.keywords]
        # Avoid tranforming the func, so don't visit node.func and
        # don't generic_visit node.
        return node

    def visit_Try(self, node):
        # don't transform handler type
        node.body = [self.visit(b) for b in node.body]
        for h in node.handlers:
            h.body = [self.visit(b) for b in h.body]
        return node

    # Change every name x to env['x'], but only in green functions.
    def visit_Name(self, node):
        if self.green:
            rewritten = ast.Subscript(value=ast.Name(id='env', ctx=ast.Load()),
                                      slice=ast.Index(value=ast.Str(s=node.id)),
                                      ctx=node.ctx)
            return ast.copy_location(rewritten, node)
        else:
            return node


def rewrite(cfg: config.Config, tree: ast.AST) -> ast.AST:
    VariableRewriter().visit(tree)
    return tree
